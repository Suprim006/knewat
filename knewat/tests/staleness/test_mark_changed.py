"""Slice 2: ``mark_changed``: code changes make the facts that depend on them suspect."""

from __future__ import annotations

import json

import pytest

from knewat.codescan.paths import anchor_id

from .conftest import cypher

P = "C:/repo/app/payments.py"
Q = "C:/repo/app/other.py"


def _state(client, graph, fid):
    return cypher(
        client,
        graph,
        "MATCH (f:Fact {id:$f}) RETURN coalesce(f.verify_state,'verified'), coalesce(f.suspect_since,0)",
        f=fid,
    )[0]


def _changes(client, graph):
    return cypher(client, graph, "MATCH (c:Change) RETURN c.id, c.commit, c.at, c.paths, c.agent_id")


def _anchor(client, graph, path, symbol=""):
    rows = cypher(
        client,
        graph,
        "MATCH (a:CodeAnchor {id:$i}) RETURN a.hash, a.updated_at, a.kind",
        i=anchor_id(path, symbol),
    )
    return rows[0] if rows else None


def _fa(stale, mem, path=P, symbol="", pred="timeout", value="30 seconds", **kw):
    f = mem.fact(pred, value, **kw)
    stale.anchor_fact(f, path, symbol)
    return f


# -- baseline and no-op ---------------------------------------------------------------------------------
def test_first_sight_without_old_hash_is_a_baseline(stale, mem, client, graph):
    f = _fa(stale, mem)
    out = stale.mark_changed([{"path": P, "new_hash": "h0"}], agent_id="hook")
    assert out["change_id"] is None and out["suspect_fact_ids"] == [] and out["unchanged"] == 1
    assert _anchor(client, graph, P)[0] == "h0"
    assert _state(client, graph, f) == ["verified", 0]
    assert _changes(client, graph) == []


def test_rerun_with_the_same_hashes_changes_nothing(stale, mem, client, graph, clock):
    f = _fa(stale, mem)
    stale.mark_changed([{"path": P, "new_hash": "h0"}])
    clock.advance(1000)
    first = stale.mark_changed([{"path": P, "new_hash": "h1"}], commit="c1")
    assert first["suspect_fact_ids"] == [f]
    before = (_changes(client, graph), _anchor(client, graph, P), _state(client, graph, f))
    clock.advance(1000)
    again = stale.mark_changed([{"path": P, "new_hash": "h1"}], commit="c1")
    assert again["change_id"] is None and again["suspect_fact_ids"] == [] and again["unchanged"] == 1
    assert (_changes(client, graph), _anchor(client, graph, P), _state(client, graph, f)) == before
    assert len(before[0]) == 1


# -- file level -----------------------------------------------------------------------------------------
def test_a_changed_file_makes_its_anchored_facts_suspect(stale, mem, client, graph, clock):
    f1, f2 = _fa(stale, mem), _fa(stale, mem, pred="retries", value="3")
    other = _fa(stale, mem, path=Q, subject="Billing")
    stale.mark_changed([{"path": P, "new_hash": "h0"}, {"path": Q, "new_hash": "q0"}])
    clock.advance(5000)
    out = stale.mark_changed(
        [{"path": P, "new_hash": "h1"}, {"path": Q, "new_hash": "q0"}], commit="abc123", agent_id="hook"
    )
    assert sorted(out["suspect_fact_ids"]) == sorted([f1, f2])
    assert out["unchanged"] == 1 and out["truncated"] is False and out["change_id"]
    assert _state(client, graph, f1) == ["suspect", 1_005_000]
    assert _state(client, graph, other) == ["verified", 0]
    assert _anchor(client, graph, P)[:2] == ["h1", 1_005_000]
    rows = _changes(client, graph)
    assert len(rows) == 1
    cid, commit, at, paths, agent = rows[0]
    assert cid == out["change_id"] and (commit, at, agent) == ("abc123", 1_005_000, "hook")
    assert json.loads(paths) == [P]
    assert cypher(
        client,
        graph,
        "MATCH (:Change {id:$c})-[r:SUSPECTED]->(f:Fact) RETURN f.id, r.at ORDER BY f.id",
        c=cid,
    ) == sorted([[f1, 1_005_000], [f2, 1_005_000]])
    assert cypher(client, graph, "MATCH (:Change)-[:TOUCHED]->(a:CodeAnchor) RETURN a.path") == [[P]]


def test_a_first_sighting_with_a_different_old_hash_counts_as_a_change(stale, mem, client, graph):
    src = mem.source(Q, "code")
    f = mem.fact("limit", "10", source_id=src)
    out = stale.mark_changed([{"path": Q, "new_hash": "n1", "old_hash": "o1"}], commit="c9")
    assert out["suspect_fact_ids"] == [f] and out["change_id"]
    same = stale.mark_changed([{"path": P, "new_hash": "n1", "old_hash": "n1"}])
    assert same["change_id"] is None  # old == new: nothing changed


def test_suspect_since_is_kept_and_every_change_is_recorded(stale, mem, client, graph, clock):
    f = _fa(stale, mem)
    stale.mark_changed([{"path": P, "new_hash": "h0"}])
    clock.advance(100)
    c1 = stale.mark_changed([{"path": P, "new_hash": "h1"}], commit="c1")["change_id"]
    clock.advance(100)
    out = stale.mark_changed([{"path": P, "new_hash": "h2"}], commit="c2")
    assert out["suspect_fact_ids"] == [f] and out["change_id"] != c1
    assert _state(client, graph, f) == ["suspect", 1_000_100]
    n = cypher(client, graph, "MATCH (:Change)-[r:SUSPECTED]->(:Fact {id:$f}) RETURN count(r)", f=f)
    assert n == [[2]]


def test_only_active_facts_are_affected(stale, mem, client, graph):
    old = _fa(stale, mem, value="30 seconds")
    new = mem.fact("timeout", "60 seconds")  # supersedes the first
    stale.anchor_fact(new, P)
    stale.mark_changed([{"path": P, "new_hash": "h0"}])
    out = stale.mark_changed([{"path": P, "new_hash": "h1"}])
    assert out["suspect_fact_ids"] == [new]
    assert _state(client, graph, old) == ["verified", 0]


# -- symbols --------------------------------------------------------------------------------------------
def test_function_level_changes_only_hit_that_functions_facts(stale, mem, client, graph):
    on_f = _fa(stale, mem, symbol="f", pred="f behaviour", value="adds")
    on_g = _fa(stale, mem, symbol="g", pred="g behaviour", value="subtracts")
    on_file = _fa(stale, mem, pred="module purpose", value="math")
    base = [
        {"path": P, "new_hash": "file0"},
        {"path": P, "symbol": "f", "new_hash": "f0"},
        {"path": P, "symbol": "g", "new_hash": "g0"},
    ]
    assert stale.mark_changed(base)["change_id"] is None
    out = stale.mark_changed(
        [
            {"path": P, "new_hash": "file1"},
            {"path": P, "symbol": "f", "new_hash": "f1"},
            {"path": P, "symbol": "g", "new_hash": "g0"},
        ],
        commit="c1",
    )
    assert sorted(out["suspect_fact_ids"]) == sorted([on_f, on_file])
    assert _state(client, graph, on_g) == ["verified", 0]
    assert out["unchanged"] == 1


def test_a_file_level_change_covers_symbols_only_when_no_symbol_entries_are_sent(stale, mem, client, graph):
    on_f = _fa(stale, mem, symbol="f", pred="f behaviour", value="adds")
    stale.mark_changed([{"path": P, "new_hash": "file0"}, {"path": P, "symbol": "f", "new_hash": "f0"}])
    out = stale.mark_changed([{"path": P, "new_hash": "file1"}])  # a doc-style file entry only
    assert out["suspect_fact_ids"] == [on_f]


def test_unchanged_symbols_are_not_covered_when_symbol_entries_are_sent(stale, mem):
    on_f = _fa(stale, mem, symbol="f", pred="f behaviour", value="adds")
    stale.mark_changed([{"path": P, "new_hash": "file0"}, {"path": P, "symbol": "f", "new_hash": "f0"}])
    out = stale.mark_changed([{"path": P, "new_hash": "file1"}, {"path": P, "symbol": "f", "new_hash": "f0"}])
    assert out["suspect_fact_ids"] == [] and on_f


def test_a_removed_symbol_makes_its_facts_suspect(stale, mem):
    on_f = _fa(stale, mem, symbol="f", pred="f behaviour", value="adds")
    stale.mark_changed([{"path": P, "symbol": "f", "new_hash": "f0"}])
    out = stale.mark_changed([{"path": P, "symbol": "f", "new_hash": "", "old_hash": "f0"}])
    assert out["suspect_fact_ids"] == [on_f]


# -- implicit anchoring through Sources -----------------------------------------------------------------
def test_facts_derived_from_a_changed_source_file_are_suspect_without_any_anchor(stale, mem, client, graph):
    uri = "C:/repo/README.md"
    src = mem.source(uri)
    direct = mem.fact("port", "8080", source_id=src)
    hop = mem.fact("proxy", "nginx")
    mem.lin.derive_from(hop, [direct])
    unrelated = mem.fact("owner", "alice")
    stale.mark_changed([{"path": uri, "new_hash": "r0"}])
    assert cypher(client, graph, "MATCH (s:Source {id:$s}) RETURN s.content_hash", s=src)[0][0] == "r0", (
        "the Source records the file's hash"
    )
    out = stale.mark_changed([{"path": uri, "new_hash": "r1"}], commit="c5")
    assert sorted(out["suspect_fact_ids"]) == sorted([direct, hop])
    assert _state(client, graph, unrelated) == ["verified", 0]
    assert cypher(client, graph, "MATCH (:Change)-[:TOUCHED]->(s:Source) RETURN s.id") == [[src]]


def test_a_fact_that_is_both_anchored_and_derived_is_listed_once(stale, mem):
    src = mem.source(P, "code")
    f = mem.fact("timeout", "30 seconds", source_id=src)
    stale.anchor_fact(f, P)
    stale.mark_changed([{"path": P, "new_hash": "h0"}])
    assert stale.mark_changed([{"path": P, "new_hash": "h1"}])["suspect_fact_ids"] == [f]


# -- decisions and docs ---------------------------------------------------------------------------------
def test_the_result_lists_decisions_built_on_the_suspects(stale, mem):
    f = _fa(stale, mem)
    d = mem.decision(f, text="use a 30 s timeout")
    stale.mark_changed([{"path": P, "new_hash": "h0"}])
    out = stale.mark_changed([{"path": P, "new_hash": "h1"}])
    assert out["decisions"] == [{"id": d, "text": "use a 30 s timeout"}] and out["decisions_total"] == 1


def test_docs_that_describe_changed_code_are_listed(stale, mem):
    doc = mem.source("C:/repo/docs/payments.md")
    stale.describe_code(doc, P, symbol="pay", hash="p0")
    stale.mark_changed([{"path": P, "symbol": "pay", "new_hash": "p0"}])
    out = stale.mark_changed([{"path": P, "symbol": "pay", "new_hash": "p1"}], commit="c2")
    assert out["docs_to_update"] == [
        {"source_id": doc, "uri": "C:/repo/docs/payments.md", "anchor": f"{P}#pay"}
    ]
    assert out["suspect_fact_ids"] == [] and out["change_id"]  # a Change exists even without any suspect fact


def test_a_doc_edited_in_the_same_call_is_not_listed(stale, mem):
    docp = "C:/repo/docs/payments.md"
    doc = mem.source(docp)
    stale.describe_code(doc, P, hash="p0")
    stale.mark_changed([{"path": P, "new_hash": "p0"}, {"path": docp, "new_hash": "d0"}])
    out = stale.mark_changed([{"path": P, "new_hash": "p1"}, {"path": docp, "new_hash": "d1"}])
    assert out["docs_to_update"] == []


# -- bounds ---------------------------------------------------------------------------------------------
def test_more_than_200_changes_are_rejected(stale):
    changes = [{"path": f"C:/repo/f{i}.py", "new_hash": "x"} for i in range(201)]
    with pytest.raises(ValueError):
        stale.mark_changed(changes)


def test_a_relative_path_is_rejected_and_nothing_is_written(stale, client, graph):
    with pytest.raises(ValueError):
        stale.mark_changed([{"path": P, "new_hash": "a"}, {"path": "rel/x.py", "new_hash": "b"}])
    assert _anchor(client, graph, P) is None


def test_truncation_marks_at_most_limit_facts_and_a_rerun_continues(stale, mem, client, graph):
    facts = [_fa(stale, mem, pred=f"p{i}", value=f"v{i}") for i in range(5)]
    stale.mark_changed([{"path": P, "new_hash": "h0"}])
    ch = [{"path": P, "new_hash": "h1"}]
    first = stale.mark_changed(ch, commit="c1", at=2_000_000, limit=2)
    assert first["truncated"] is True and len(first["suspect_fact_ids"]) == 2
    assert _anchor(client, graph, P)[0] == "h0"  # the change is still pending
    second = stale.mark_changed(ch, commit="c1", at=2_000_000, limit=2)
    assert second["truncated"] is True and len(second["suspect_fact_ids"]) == 2
    third = stale.mark_changed(ch, commit="c1", at=2_000_000, limit=2)
    assert third["truncated"] is False and len(third["suspect_fact_ids"]) == 1
    got = first["suspect_fact_ids"] + second["suspect_fact_ids"] + third["suspect_fact_ids"]
    assert sorted(got) == sorted(facts)
    assert _anchor(client, graph, P)[0] == "h1"
    assert len(_changes(client, graph)) == 1 and first["change_id"] == third["change_id"]
    assert stale.mark_changed(ch, commit="c1", at=2_000_000)["change_id"] is None  # fully applied now


def test_event_time_defaults_to_now_and_can_be_set(stale, mem, client, graph):
    f = _fa(stale, mem)
    stale.mark_changed([{"path": P, "new_hash": "h0"}])
    stale.mark_changed([{"path": P, "new_hash": "h1"}], at=999_000)
    assert _state(client, graph, f) == ["suspect", 999_000]
