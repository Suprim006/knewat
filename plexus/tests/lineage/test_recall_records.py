from __future__ import annotations

import pytest

from plexus.lineage import UnknownStep

from .conftest import cypher


def test_record_recall_creates_node_and_edges(world, client, graph):
    w = world
    rows = cypher(
        client,
        graph,
        "MATCH (r:Recall {id:$r})-[:BY]->(a:Agent), (r)-[:IN_STEP]->(s:Step) "
        "RETURN r.query, r.scope_id, r.agent_id, r.k, r.at, a.id, s.id",
        r=w.recall1,
    )
    assert rows == [[w.q1, w.proj, "planner", 8, 3000, "planner", w.p1]]
    ret = cypher(
        client,
        graph,
        "MATCH (:Recall {id:$r})-[x:RETURNED]->(f:Fact) RETURN f.id, x.rank, x.score ORDER BY x.rank",
        r=w.recall1,
    )
    assert [(f, rank) for f, rank, _ in ret] == [(r["fact_id"], i) for i, r in enumerate(w.results1, 1)]
    assert [s for _, _, s in ret] == pytest.approx([r["score"] for r in w.results1])
    assert {w.db1, w.cache, w.sessstore, w.other} == {r[0] for r in ret}


def test_record_recall_adds_read_edges(world, client, graph):
    w = world
    read = cypher(client, graph, "MATCH (:Step {id:$s})-[:READ]->(f:Fact) RETURN f.id", s=w.p1)
    assert {r[0] for r in read} == {r["fact_id"] for r in w.results1}
    assert cypher(client, graph, "MATCH (:Step {id:$s})-[:READ]->(f:Fact) RETURN f.id", s=w.b1) == [[w.db1]]


def test_record_recall_without_step_and_empty_results(lin, eng, client, graph):
    glob = eng.create_scope("global", "global")
    rid = lin.record_recall("alice", None, "nothing here", glob, 5, [])
    assert cypher(
        client, graph, "MATCH (r:Recall {id:$r})-[:BY]->(:Agent {id:'alice'}) RETURN count(r)", r=rid
    ) == [[1]]
    assert cypher(client, graph, "MATCH (:Recall)-[x:RETURNED|IN_STEP]->() RETURN count(x)") == [[0]]


def test_record_recall_is_all_or_nothing(lin, world, client, graph):
    w = world
    before = cypher(client, graph, "MATCH (r:Recall) RETURN count(r)")
    with pytest.raises(UnknownStep, match="ghost"):
        lin.record_recall("planner", w.p1, "q", w.proj, 2, [{"fact_id": w.db1}, {"fact_id": "ghost"}])
    with pytest.raises(UnknownStep, match="no-such-step"):
        lin.record_recall("planner", "no-such-step", "q", w.proj, 2, [{"fact_id": w.db1}])
    assert cypher(client, graph, "MATCH (r:Recall) RETURN count(r)") == before


def test_record_recall_dedupes_and_bounds(lin, world):
    w = world
    rid = lin.record_recall("planner", w.p1, "q", w.proj, 3, [{"fact_id": w.db1}, {"fact_id": w.db1}])
    rows = cypher(w.client, w.graph, "MATCH (:Recall {id:$r})-[x:RETURNED]->() RETURN count(x)", r=rid)
    assert rows == [[1]]
    with pytest.raises(ValueError):
        lin.record_recall("planner", w.p1, "q", w.proj, 3, [{"fact_id": str(i)} for i in range(201)])


def test_derive_from(world, lin, client, graph):
    w = world
    assert lin.derive_from(w.other, [w.good, w.db1, w.ep]) == 3
    assert lin.derive_from(w.other, [w.good]) == 1  # idempotent (MERGE)
    q = "MATCH (:Fact {id:$f})-[r:DERIVED_FROM]->(x) RETURN count(r)"
    assert cypher(client, graph, q, f=w.other) == [[3]]
    with pytest.raises(UnknownStep):
        lin.derive_from(w.other, [w.good, "ghost"])
    with pytest.raises(ValueError):
        lin.derive_from(w.other, [w.other])
