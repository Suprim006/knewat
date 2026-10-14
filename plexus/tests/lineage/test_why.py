from __future__ import annotations

import pytest

from plexus.lineage import UnknownNode
from plexus.lineage.explain import bound_edges, paths_from


def _fact(res, fid):
    return next(f for f in res["facts"] if f["id"] == fid)


def test_why_decision_returns_exact_facts_agents_and_sources(world, lin):
    w = world
    res = lin.why(w.decision)
    assert res["kind"] == "Decision" and res["root"] == w.decision
    assert sorted(f["id"] for f in res["facts"]) == sorted([w.db1, w.cache])
    assert res["agents"] == sorted(["planner", "researcher"])  # decider + asserter (and their steps)
    assert res["sources"] == sorted([w.good, w.bad])
    assert res["episodes"] == [w.ep]
    assert res["steps"] == sorted([w.p2, w.r1, w.r2])  # steps that wrote the decision and the two facts
    assert res["truncated"] is False


def test_why_decision_per_fact_evidence(world, lin):
    w = world
    res = lin.why(w.decision)
    db1 = _fact(res, w.db1)
    assert db1["asserted_by"] == ["researcher"]
    assert db1["sources"] == [w.good] and db1["episodes"] == [w.ep]
    assert db1["superseded_by"] == [w.db2] and db1["supersedes"] == []
    assert db1["written_by_steps"] == [w.r1]
    assert db1["props"]["value"] == "PostgreSQL 16" and db1["props"]["status"] == "superseded"
    cache = _fact(res, w.cache)
    assert cache["sources"] == [w.bad] and cache["episodes"] == []
    assert cache["written_by_steps"] == [w.r2]
    assert cache["props"]["predicate"] == "cache"


def test_why_decision_nodes_edges_consistent(world, lin):
    w = world
    res = lin.why(w.decision)
    ids = {n["id"] for n in res["nodes"]}
    assert w.decision in ids and res["nodes"][0]["id"] == w.decision
    assert all(e["from"] in ids and e["to"] in ids for e in res["edges"])
    assert len(ids) == len(res["nodes"])
    kinds = {(e["rel"]) for e in res["edges"]}
    assert {"DECIDED", "BASED_ON", "ASSERTED_BY", "DERIVED_FROM", "WROTE", "BY", "SUPERSEDES"} <= kinds
    labels = {n["id"]: n["label"] for n in res["nodes"]}
    assert labels[w.good] == "Source" and labels[w.ep] == "Episode" and labels["planner"] == "Agent"
    src = next(n for n in res["nodes"] if n["id"] == w.good)
    assert src["props"]["uri"] == "https://docs.example/postgres"
    assert all(None not in n["props"].values() for n in res["nodes"])
    assert not any("embedding" in n["props"] for n in res["nodes"])


def test_why_paths_are_connected_chains_from_the_root(world, lin):
    w = world
    res = lin.why(w.decision)
    assert res["paths"]
    stored = {(e["from"], e["rel"], e["to"]) for e in res["edges"]}
    for path in res["paths"]:
        assert path[0]["from"] == w.decision
        for a, b in zip(path, path[1:], strict=False):
            assert a["to"] == b["from"]
        for hop in path:
            edge = (
                (hop["to"], hop["rel"], hop["from"])
                if hop["reverse"]
                else (hop["from"], hop["rel"], hop["to"])
            )
            assert edge in stored
    # one path reaches the bad source: decision -BASED_ON-> cache -DERIVED_FROM-> source
    assert any(
        [h["rel"] for h in p] == ["BASED_ON", "DERIVED_FROM"] and p[-1]["to"] == w.bad for p in res["paths"]
    )
    # and one reaches the researcher through the episode's session
    assert any(p[-1]["to"] == "researcher" and "HAD" in [h["rel"] for h in p] for p in res["paths"])


def test_why_fact_including_derived_chain(world, lin):
    w = world
    res = lin.why(w.sessstore)
    assert res["kind"] == "Fact"
    f = _fact(res, w.sessstore)
    assert f["derived_from_facts"] == [w.cache]
    assert f["sources"] == [w.bad]  # reached through the cache fact
    assert f["asserted_by"] == ["researcher"] and f["written_by_steps"] == [w.r2]
    assert res["sources"] == [w.bad]


def test_why_fact_superseding_and_superseded(world, lin):
    w = world
    new = _fact(lin.why(w.db2), w.db2)
    assert new["supersedes"] == [w.db1] and new["superseded_by"] == []
    assert new["written_by_steps"] == [w.r3]
    old = lin.why(w.db1)
    assert [n["id"] for n in old["nodes"] if n["label"] == "Fact"].count(
        w.db2
    ) == 1  # the newer version is visible


def test_why_unknown_and_wrong_kind(world, lin):
    with pytest.raises(UnknownNode):
        lin.why("no-such-id")
    with pytest.raises(UnknownNode, match="Agent"):
        lin.why("planner")


def test_why_is_bounded(world, lin):
    w = world
    res = lin.why(w.decision, max_elements=10)
    assert len(res["nodes"]) + len(res["edges"]) <= 10
    assert res["truncated"] is True
    ids = {n["id"] for n in res["nodes"]}
    assert all(e["from"] in ids and e["to"] in ids for e in res["edges"])
    with pytest.raises(ValueError):
        lin.why(w.decision, max_elements=1)


def test_why_large_decision_stays_within_200_elements(world, eng, relay, lin):
    w = world
    ids = [
        eng.assert_fact("Acme Notes API", f"setting {i}", f"value {i}", w.proj, "researcher", now=8000 + i)[
            "fact_id"
        ]
        for i in range(60)
    ]
    dec = relay.record_decision("planner", "t-build", "use everything", ids, now=9000)
    res = lin.why(dec)
    assert len(res["nodes"]) + len(res["edges"]) <= 200
    assert res["truncated"] is True
    assert len(res["paths"]) <= 50


def test_bound_edges_unit():
    rows = [
        {"s": "r", "sl": "Decision", "rel": "BASED_ON", "t": "a", "tl": "Fact", "prio": 1},
        {"s": "r", "sl": "Decision", "rel": "BASED_ON", "t": "a", "tl": "Fact", "prio": 1},  # duplicate
        {"s": "a", "sl": "Fact", "rel": "ABOUT", "t": "e", "tl": "Entity", "prio": 5},
    ]
    edges, labels, truncated = bound_edges(rows, "r", 10)
    assert len(edges) == 2 and labels == {"a": "Fact", "e": "Entity"} and not truncated
    edges, labels, truncated = bound_edges(rows, "r", 3)  # root + a + one edge
    assert len(edges) == 1 and truncated


def test_paths_unit_never_hops_through_an_agent():
    label = {"r": "Decision", "f": "Fact", "a": "Agent", "g": "Fact"}
    edges = [
        {"from": "r", "rel": "BASED_ON", "to": "f"},
        {"from": "f", "rel": "ASSERTED_BY", "to": "a"},
        {"from": "g", "rel": "ASSERTED_BY", "to": "a"},
    ]
    assert paths_from("r", {"f"}, label, edges) == [
        [
            {"from": "r", "rel": "BASED_ON", "to": "f", "reverse": False},
            {"from": "f", "rel": "ASSERTED_BY", "to": "a", "reverse": False},
        ]
    ]
