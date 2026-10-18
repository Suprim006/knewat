"""Slice 4: ``facts_to_verify``, ``docs_to_update`` and ``set_review_date``."""

from __future__ import annotations

import json

import pytest

P = "C:/repo/app/payments.py"
Q = "C:/repo/app/other.py"
DOC = "C:/repo/docs/payments.md"


def _anchored(stale, mem, path=P, symbol="", pred="timeout", value="30 seconds", **kw):
    f = mem.fact(pred, value, **kw)
    stale.anchor_fact(f, path, symbol)
    return f


def _change(stale, path, h0, h1, **kw):
    stale.mark_changed([{"path": path, "new_hash": h0}])
    return stale.mark_changed([{"path": path, "new_hash": h1}], **kw)


# -- facts_to_verify -------------------------------------------------------------------------------------
def test_nothing_is_suspect_in_a_fresh_memory(stale, mem):
    mem.fact("owner", "alice")
    assert stale.facts_to_verify() == []


def test_a_suspect_fact_comes_with_its_reason_anchors_and_decision_count(stale, mem, clock):
    f = _anchored(stale, mem)
    mem.decision(f)
    _change(stale, P, "h0", "h1", commit="abc123", at=1_500_000)
    (row,) = stale.facts_to_verify()
    assert row["fact_id"] == f and row["verify_state"] == "suspect" and row["suspect_since"] == 1_500_000
    assert row["reason"] == f"changed in abc123 ({P})"
    assert row["decisions_count"] == 1 and row["anchors"] == [P]
    assert (row["entity"], row["predicate"], row["value"]) == ("Payments", "timeout", "30 seconds")
    assert row["change"]["commit"] == "abc123" and row["change"]["paths"] == [P]


def test_a_change_without_a_commit_reads_working_tree(stale, mem):
    _anchored(stale, mem)
    _change(stale, P, "h0", "h1")
    assert stale.facts_to_verify()[0]["reason"] == f"changed in working tree ({P})"


def test_the_reason_names_the_newest_change(stale, mem):
    _anchored(stale, mem)
    _change(stale, P, "h0", "h1", commit="c1", at=1_500_000)
    stale.mark_changed([{"path": P, "new_hash": "h2"}], commit="c2", at=1_600_000)
    assert stale.facts_to_verify()[0]["reason"] == f"changed in c2 ({P})"


def test_facts_with_decisions_come_first_then_the_longest_suspect(stale, mem):
    old = _anchored(stale, mem, pred="a", value="1")
    stale.mark_changed([{"path": P, "new_hash": "h0"}])
    stale.mark_changed([{"path": P, "new_hash": "h1"}], commit="c1", at=1_100_000)
    other = _anchored(stale, mem, path=Q, pred="b", value="2")
    heavy = _anchored(stale, mem, path=Q, pred="c", value="3")
    mem.decision(heavy)
    mem.decision(heavy, text="another")
    flagged = mem.decision(other, text="was flagged")
    stale.client.graph(stale.graph).query("MATCH (d:Decision {id:$d}) SET d.flagged = true", {"d": flagged})
    stale.mark_changed([{"path": Q, "new_hash": "q0"}])
    stale.mark_changed([{"path": Q, "new_hash": "q1"}], commit="c2", at=1_050_000)
    got = [(r["fact_id"], r["decisions_count"]) for r in stale.facts_to_verify()]
    assert got == [
        (heavy, 2),
        (other, 0),
        (old, 0),
    ]  # 'other' is suspect since 1_050_000, 'old' since 1_100_000


def test_a_passed_review_date_makes_a_fact_due_and_a_future_one_does_not(stale, mem, clock):
    due, later = mem.fact("url", "https://a.example"), mem.fact("url", "https://b.example", subject="Site B")
    stale.set_review_date(due, 1_200_000)
    stale.set_review_date(later, 9_000_000)
    clock.t = 1_300_000
    (row,) = stale.facts_to_verify()
    assert row["fact_id"] == due and row["reason"] == "review date passed"
    assert row["verify_state"] == "verified" and row["suspect_since"] == 1_200_000 and row["anchors"] == []
    clock.t = 9_500_000
    assert {r["fact_id"] for r in stale.facts_to_verify()} == {due, later}


def test_set_review_date_validates_and_can_be_cleared(stale, mem, clock):
    f = mem.fact("url", "https://a.example")
    with pytest.raises(LookupError):
        stale.set_review_date("nope", 5)
    with pytest.raises(ValueError):
        stale.set_review_date(f, -1)
    stale.set_review_date(f, 1_100_000)
    clock.t = 2_000_000
    assert len(stale.facts_to_verify()) == 1
    stale.set_review_date(f, 9_999_999_999_999)
    assert stale.facts_to_verify() == []


def test_superseded_and_forgotten_suspects_are_not_listed(stale, mem, lin):
    old = _anchored(stale, mem)
    _change(stale, P, "h0", "h1", commit="c1")
    new = mem.fact("timeout", "60 seconds")
    assert [r["fact_id"] for r in stale.facts_to_verify()] == []
    assert old and new


def test_scope_filter_includes_inherited_scopes(stale, mem, eng):
    other_proj = eng.create_scope("project", "beta", inherits=[mem.glob], now=1)
    in_acme = _anchored(stale, mem, pred="a", value="1")
    in_glob = eng.assert_fact("Payments", "g", "1", mem.glob, "alice", now=2)["fact_id"]
    stale.anchor_fact(in_glob, P)
    in_beta = eng.assert_fact("Payments", "b", "1", other_proj, "alice", now=2)["fact_id"]
    stale.anchor_fact(in_beta, P)
    _change(stale, P, "h0", "h1")
    assert {r["fact_id"] for r in stale.facts_to_verify()} == {in_acme, in_glob, in_beta}
    assert {r["fact_id"] for r in stale.facts_to_verify(mem.proj)} == {in_acme, in_glob}
    assert {r["fact_id"] for r in stale.facts_to_verify(other_proj)} == {in_beta, in_glob}


def test_limit_and_implicit_anchors(stale, mem):
    src = mem.source(DOC)
    facts = [mem.fact(f"p{i}", f"v{i}", source_id=src) for i in range(3)]
    stale.mark_changed([{"path": DOC, "new_hash": "d0"}])
    stale.mark_changed([{"path": DOC, "new_hash": "d1"}], commit="c9")
    rows = stale.facts_to_verify(limit=2)
    assert len(rows) == 2 and {r["fact_id"] for r in rows} <= set(facts)
    assert rows[0]["anchors"] == [DOC] and rows[0]["reason"] == f"changed in c9 ({DOC})"
    with pytest.raises(ValueError):
        stale.facts_to_verify(limit=0)


def test_the_ranking_hook_can_reorder(client, graph, eng, clock, mem):
    from plexus.staleness import Staleness

    a, b = _anchored(Staleness(client, graph, engram=eng, clock=clock), mem, pred="a", value="1"), None
    s = Staleness(client, graph, engram=eng, clock=clock, rank=lambda rows: list(reversed(rows)))
    b = _anchored(s, mem, pred="b", value="2")
    _change(s, P, "h0", "h1", commit="c1")
    plain = [r["fact_id"] for r in Staleness(client, graph, engram=eng, clock=clock).facts_to_verify()]
    assert [r["fact_id"] for r in s.facts_to_verify()] == list(reversed(plain)) and {a, b} == set(plain)


# -- docs_to_update --------------------------------------------------------------------------------------
def _doc_setup(stale, mem, symbol="pay"):
    doc = mem.source(DOC)
    stale.describe_code(doc, P, symbol=symbol, hash="p0")
    stale.mark_changed([{"path": DOC, "new_hash": "d0"}, {"path": P, "symbol": symbol, "new_hash": "p0"}])
    return doc


def test_a_doc_describing_changed_code_is_listed_with_the_changes(stale, mem):
    doc = _doc_setup(stale, mem)
    assert stale.docs_to_update() == []
    stale.mark_changed([{"path": P, "symbol": "pay", "new_hash": "p1"}], commit="c3", at=1_700_000)
    (row,) = stale.docs_to_update()
    assert (row["source_id"], row["uri"]) == (doc, DOC)
    assert row["changes"] == [
        {
            "change_id": row["changes"][0]["change_id"],
            "commit": "c3",
            "at": 1_700_000,
            "paths": [P],
            "anchor": f"{P}#pay",
        }
    ]


def test_since_filters_old_changes(stale, mem):
    _doc_setup(stale, mem)
    stale.mark_changed([{"path": P, "symbol": "pay", "new_hash": "p1"}], commit="c3", at=1_700_000)
    assert len(stale.docs_to_update(since=1_699_999)) == 1
    assert len(stale.docs_to_update(since=1_700_000)) == 1  # P7-12: `since` is inclusive (at >= since)
    assert stale.docs_to_update(since=1_700_001) == []


def test_a_doc_edited_after_the_code_change_drops_off(stale, mem):
    _doc_setup(stale, mem)
    stale.mark_changed([{"path": P, "symbol": "pay", "new_hash": "p1"}], commit="c3", at=1_700_000)
    assert len(stale.docs_to_update()) == 1
    stale.mark_changed([{"path": DOC, "new_hash": "d1"}], commit="c4", at=1_800_000)
    assert stale.docs_to_update() == []
    stale.mark_changed([{"path": P, "symbol": "pay", "new_hash": "p2"}], commit="c5", at=1_900_000)
    (row,) = stale.docs_to_update()  # the code moved again after the doc edit
    assert [c["commit"] for c in row["changes"]] == ["c5"]


def test_docs_are_ordered_newest_change_first_and_limited(stale, mem):
    d1 = mem.source("C:/repo/docs/a.md")
    d2 = mem.source("C:/repo/docs/b.md")
    stale.describe_code(d1, P, hash="p0")
    stale.describe_code(d2, Q, hash="q0")
    stale.mark_changed([{"path": P, "new_hash": "p0"}, {"path": Q, "new_hash": "q0"}])
    stale.mark_changed([{"path": P, "new_hash": "p1"}], commit="c1", at=1_100_000)
    stale.mark_changed([{"path": Q, "new_hash": "q1"}], commit="c2", at=1_200_000)
    assert [r["source_id"] for r in stale.docs_to_update()] == [d2, d1]
    assert [r["source_id"] for r in stale.docs_to_update(limit=1)] == [d2]
    with pytest.raises(ValueError):
        stale.docs_to_update(limit=0)


def test_paths_of_a_multi_file_change_are_all_listed(stale, mem):
    _doc_setup(stale, mem, symbol="")
    stale.mark_changed(
        [{"path": P, "new_hash": "p1"}, {"path": Q, "new_hash": "q9", "old_hash": "q0"}], at=1_700_000
    )
    (row,) = stale.docs_to_update()
    assert sorted(row["changes"][0]["paths"]) == sorted([P, Q])
    assert json.dumps(row)
