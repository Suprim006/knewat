"""Audit P1: the tail of lineage/quarantine must not carry the fact list as a grouping key.

Before: ``WITH src, fs, collect(...)`` after ``UNWIND fs`` hashes the whole list once per row, so the tail is
quadratic (quarantine: 1,200 facts 1.5 s, 2,500 facts timeout; forget_source: 2,500 facts ~380 ms). After: one
``CALL { WITH fs ... }`` per aggregate. The equivalence tests run the baseline queries (git archive edf9a91)
against the same data and compare the rows.
"""

from __future__ import annotations

import time

import pytest

from .audit_util import old_client, reset_scale, seed_scale
from .conftest import cypher

T_MAX_MS = 10_000  # FalkorDB TIMEOUT_MAX on the test server


def _q_params(source_id, **over):
    p = {"source_id": source_id, "now": 20_000, "limit": 5000, "depth": 8, "max_detail": 500}
    p.update(over)
    return p


def _norm_q(rows):
    """quarantine row -> comparable: ordered reads kept exactly, id lists sorted (order is unspecified)."""
    if not rows:
        return rows
    r = dict(rows[0])
    for k in ("fact_ids", "decision_ids", "handoff_ids", "agent_ids"):
        r[k] = sorted(r[k])
    return [r]


def _state(client, graph):
    return cypher(
        client,
        graph,
        "MATCH (f:Fact) RETURN f.id, f.status, f.prior_status, f.valid_to ORDER BY f.id",
    ), cypher(client, graph, "MATCH (d:Decision) RETURN d.id, d.flagged ORDER BY d.id")


def _old_then_new(client, graph, name, params, norm):
    """Run baseline then current query on the same data (reset in between); return both rows + states."""
    old = old_client(client)
    try:
        rows_old = old.rw(graph, name, params)
        st_old = _state(client, graph)
    finally:
        old.close()
    reset_scale(client, graph)
    rows_new = client.rw(graph, name, params)
    st_new = _state(client, graph)
    return norm(rows_old), norm(rows_new), st_old, st_new


# -- equivalence -----------------------------------------------------------------------------------


def test_quarantine_matches_baseline_on_the_world(world, client, graph):
    w = world
    # a handoff carrying one of the quarantined facts, and a second reader
    world.relay.handoff("planner", "builder", "t-build", "pass on", fact_ids=[w.cache], now=4500)
    world.lin.link_step(w.b1, read_ids=[w.cache])
    old, new, st_old, st_new = _old_then_new(client, graph, "lineage/quarantine", _q_params(w.bad), _norm_q)
    assert new == old
    assert new[0]["reads_total"] >= 3 and new[0]["decisions_total"] == 1 and new[0]["handoffs_total"] == 1
    assert len(new[0]["fact_ids"]) == 2 and new[0]["truncated"] is False
    assert st_new == st_old


def test_quarantine_matches_baseline_on_a_scale_fixture_with_truncation(client, empty_graph):
    seed_scale(client, empty_graph, 300)
    for limit in (5000, 100):
        old, new, st_old, st_new = _old_then_new(
            client, empty_graph, "lineage/quarantine", _q_params("SRC", limit=limit, max_detail=50), _norm_q
        )
        if limit == 5000:
            assert new == old
        else:  # which 100 of the 300 are cut is up to the engine: counts and flags must agree
            assert new[0]["truncated"] is old[0]["truncated"] is True
            assert len(new[0]["fact_ids"]) == len(old[0]["fact_ids"]) == 100
        assert new[0]["reads_total"] == (300 if limit == 5000 else 100)
        assert len(new[0]["reads"]) == 50 and new[0]["decisions_total"] == new[0]["reads_total"]
        assert [x[1] for x in st_new[0]].count("quarantined") == len(new[0]["fact_ids"])
        reset_scale(client, empty_graph)


def test_quarantine_empty_source_returns_one_row_unknown_source_none(client, empty_graph):
    seed_scale(client, empty_graph, 0)
    client.graph(empty_graph).query("CREATE (:Source {id: 'EMPTY', uri: 'u:e', kind: 'doc', created_at: 1})")
    old = old_client(client)
    try:
        for src, n_rows in (("EMPTY", 1), ("NOPE", 0)):
            a = old.rw(empty_graph, "lineage/quarantine", _q_params(src))
            b = client.rw(empty_graph, "lineage/quarantine", _q_params(src))
            assert len(a) == len(b) == n_rows
            assert _norm_q(a) == _norm_q(b)
        assert (
            b == [] and client.rw(empty_graph, "lineage/quarantine", _q_params("EMPTY"))[0]["fact_ids"] == []
        )
    finally:
        old.close()


def _timed(fn):
    t0 = time.perf_counter()
    out = fn()
    return out, (time.perf_counter() - t0) * 1000


def test_quarantine_5000_facts_with_reader_decision_handoff_completes(client, empty_graph, capsys):
    """Audit: old query timed out at 2,500 facts; the allowed cap is 5,000."""
    seed_scale(client, empty_graph, 5000)
    rows, ms = _timed(
        lambda: client.rw(empty_graph, "lineage/quarantine", _q_params("SRC"), timeout_ms=T_MAX_MS)
    )
    r = rows[0]
    with capsys.disabled():
        print(f"\n[P1] quarantine 5,000 facts: {ms:.0f} ms")
    assert len(r["fact_ids"]) == 5000 and r["truncated"] is True  # size(fs) >= limit
    assert r["reads_total"] == r["decisions_total"] == r["handoffs_total"] == 5000
    assert len(r["reads"]) == 500 and len(r["agent_ids"]) == 20
    assert ms < T_MAX_MS / 2  # old query: timeout at 2,500 facts


@pytest.mark.parametrize("name", ["lineage/quarantine"])
def test_tail_does_not_carry_the_fact_list_as_a_key(client, name):
    """Plan-text guard: no ``WITH src, fs,`` after the cascade (the list-as-grouping-key shape)."""
    text = client.library.get(name).statements[0]
    assert "WITH src, fs," not in text
    assert text.count("CALL {") >= 2
