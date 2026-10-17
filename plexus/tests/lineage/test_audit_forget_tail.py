"""Audit B1: the tail of lineage/forget_source must not carry the fact list as a key.

Before: ``WITH src, fs, collect(...)`` after ``UNWIND fs`` hashes the whole list once per row, so the tail is
quadratic (forget_source: 2,500 facts ~480 ms, 5,000 ~2 s). After: one
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


def _f_params(source_id, **over):
    return {**_q_params(source_id), "reason": "r", **over}


def _norm_f(rows):
    if not rows:
        return rows
    r = dict(rows[0])
    for k in ("fact_ids", "decision_ids", "handoff_ids"):
        r[k] = sorted(r[k])
    # P13: the baseline has no multi-source columns; on these single-source fixtures they must be empty
    assert r.pop("unlinked", []) == [] and r.pop("unlinked_total", 0) == 0
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


def test_forget_source_matches_baseline_on_the_world(world, client, graph):
    w = world
    world.relay.handoff("planner", "builder", "t-build", "pass on", fact_ids=[w.cache], now=4500)
    old, new, st_old, st_new = _old_then_new(
        client, graph, "lineage/forget_source", _f_params(w.bad), _norm_f
    )
    assert new == old
    assert new[0]["decisions_total"] == 1 and new[0]["handoffs_total"] == 1
    assert st_new == st_old
    assert [x[1] for x in st_new[0] if x[0] in (w.cache, w.sessstore)] == ["forgotten", "forgotten"]
    assert [d[1] for d in st_new[1]] == [True]


def test_forget_source_matches_baseline_on_a_scale_fixture(client, empty_graph):
    seed_scale(client, empty_graph, 300)
    old, new, st_old, st_new = _old_then_new(
        client, empty_graph, "lineage/forget_source", _f_params("SRC", max_detail=50), _norm_f
    )
    assert new == old
    assert new[0]["decisions_total"] == new[0]["handoffs_total"] == 300
    assert len(new[0]["decision_ids"]) == 50
    assert st_new == st_old


def test_forget_source_empty_and_unknown_source(client, empty_graph):
    seed_scale(client, empty_graph, 0)
    client.graph(empty_graph).query("CREATE (:Source {id: 'EMPTY', uri: 'u:e', kind: 'doc', created_at: 1})")
    old = old_client(client)
    try:
        for src, n_rows in (("EMPTY", 1), ("NOPE", 0)):
            a = old.rw(empty_graph, "lineage/forget_source", _f_params(src))
            b = client.rw(empty_graph, "lineage/forget_source", _f_params(src))
            assert len(a) == len(b) == n_rows
            assert _norm_f(a) == _norm_f(b)
        row = client.rw(empty_graph, "lineage/forget_source", _f_params("EMPTY"))[0]
        assert row["fact_ids"] == [] and row["decisions_total"] == 0 and row["truncated"] is False
    finally:
        old.close()


# -- scale -----------------------------------------------------------------------------------------


def _timed(fn):
    t0 = time.perf_counter()
    out = fn()
    return out, (time.perf_counter() - t0) * 1000


def test_forget_source_5000_facts_with_decision_and_handoff_completes(client, empty_graph, capsys):
    seed_scale(client, empty_graph, 5000)
    rows, ms = _timed(
        lambda: client.rw(empty_graph, "lineage/forget_source", _f_params("SRC"), timeout_ms=T_MAX_MS)
    )
    r = rows[0]
    with capsys.disabled():
        print(f"\n[B1] forget_source 5,000 facts: {ms:.0f} ms")
    assert len(r["fact_ids"]) == 5000 and r["decisions_total"] == r["handoffs_total"] == 5000
    assert ms < 1500  # old query: 1.6-2.1 s at 5,000 facts


@pytest.mark.parametrize("name", ["lineage/forget_source"])
def test_tail_does_not_carry_the_fact_list_as_a_key(client, name):
    """Plan-text guard: no ``WITH src, fs,`` after the cascade (the list-as-grouping-key shape)."""
    text = client.library.get(name).statements[0]
    assert "WITH src, fs," not in text
    assert text.count("CALL {") >= 2
