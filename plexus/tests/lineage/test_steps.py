from __future__ import annotations

import pytest

from plexus.lineage import StepOrderError, UnknownStep

from .conftest import cypher


def test_record_step_chains_next_and_by(lin, client, graph, clock):
    s1 = lin.record_step("alice", 1, at=100)
    s2 = lin.record_step("alice", 2, at=200)
    s3 = lin.record_step("alice")  # auto -> 3
    assert len({s1, s2, s3}) == 3
    q = "MATCH (s:Step)-[:BY]->(:Agent {id:'alice'}) RETURN s.n, s.at, s.agent_id ORDER BY s.n"
    assert cypher(client, graph, q) == [[1, 100, "alice"], [2, 200, "alice"], [3, clock.t, "alice"]]
    chain = cypher(client, graph, "MATCH (a:Step)-[:NEXT]->(b:Step) RETURN a.id, b.id ORDER BY a.n")
    assert chain == [[s1, s2], [s2, s3]]


def test_record_step_is_per_agent_and_idempotent(lin, client, graph):
    a1 = lin.record_step("alice", 1, at=1)
    b1 = lin.record_step("bob", 1, at=2)
    assert a1 != b1
    assert lin.record_step("alice", 1, at=999) == a1  # same (agent, n): no second node
    assert cypher(client, graph, "MATCH (s:Step) RETURN count(s)") == [[2]]
    assert cypher(client, graph, "MATCH (:Step)-[r:NEXT]->(:Step) RETURN count(r)") == [[0]]


def test_record_step_rejects_out_of_order(lin):
    lin.record_step("alice", 5, at=1)
    with pytest.raises(StepOrderError):
        lin.record_step("alice", 3, at=2)


def test_record_step_uses_clock_when_no_at(lin, client, graph, clock):
    lin.record_step("alice")
    assert cypher(client, graph, "MATCH (s:Step) RETURN s.at") == [[clock.t]]


def test_create_source_is_idempotent_by_uri(lin, client, graph):
    s1 = lin.create_source("https://docs.example/pg", kind="url", trust=0.9)
    s2 = lin.create_source("https://docs.example/pg", kind="url", trust=0.5)
    s3 = lin.create_source("https://other.example/x")
    assert s1 == s2 != s3
    q = "MATCH (s:Source {id:$i}) RETURN s.uri, s.kind, s.trust"
    assert cypher(client, graph, q, i=s1) == [["https://docs.example/pg", "url", 0.5]]
    assert cypher(client, graph, "MATCH (s:Source) WHERE s.new IS NOT NULL RETURN count(s)") == [[0]]


def test_link_step_writes_and_reads_via_real_services(lin, eng, relay, client, graph):
    glob = eng.create_scope("global", "global")
    relay.register_agent("alice", "alice", "planner", "test")
    relay.create_tasks([{"id": "t1", "title": "plan"}])
    f1 = eng.assert_fact("Acme", "db", "postgres", glob, "alice", now=10)["fact_id"]
    f2 = eng.assert_fact("Acme", "cache", "redis", glob, "alice", now=11)["fact_id"]
    dec = relay.record_decision("alice", "t1", "use pg", [f1], now=12)
    step = lin.record_step("alice", 1, at=12)
    assert lin.link_step(step, wrote_ids=[dec, "t1", f1], read_ids=[f2, f2]) == {"read": 1, "wrote": 3}
    lin.link_step(step, wrote_ids=[dec], read_ids=[f2])  # idempotent
    wrote = cypher(client, graph, "MATCH (:Step {id:$s})-[:WROTE]->(x) RETURN x.id", s=step)
    assert sorted(r[0] for r in wrote) == sorted([dec, "t1", f1])
    q = "MATCH (:Step {id:$s})-[r:READ]->(x) RETURN x.id, count(r)"
    assert cypher(client, graph, q, s=step) == [[f2, 1]]


def test_link_step_is_all_or_nothing(lin, eng, client, graph):
    glob = eng.create_scope("global", "global")
    f1 = eng.assert_fact("Acme", "db", "postgres", glob, "alice", now=10)["fact_id"]
    step = lin.record_step("alice", 1, at=12)
    with pytest.raises(UnknownStep, match="nope"):
        lin.link_step(step, wrote_ids=[f1], read_ids=["nope"])
    assert cypher(client, graph, "MATCH (:Step)-[r:WROTE|READ]->() RETURN count(r)") == [[0]]
    with pytest.raises(UnknownStep, match="no-step"):
        lin.link_step("no-step", wrote_ids=[f1])


def test_link_step_bounds(lin):
    step = lin.record_step("alice", 1)
    with pytest.raises(ValueError):
        lin.link_step(step, read_ids=[str(i) for i in range(201)])


def test_link_assert_result(lin, eng, client, graph):
    glob = eng.create_scope("global", "global")
    s1 = lin.record_step("alice", 1, at=10)
    r1 = eng.assert_fact("Acme", "db", "postgres", glob, "alice", now=10)
    lin.link_assert_result(s1, r1)
    s2 = lin.record_step("alice", 2, at=20)
    r2 = eng.assert_fact("Acme", "db", "postgres", glob, "alice", now=20)  # duplicate
    assert r2["duplicate_of"] == r1["fact_id"]
    lin.link_assert_result(s2, r2)
    s3 = lin.record_step("alice", 3, at=30)
    r3 = eng.assert_fact("Acme", "db", "mysql", glob, "alice", now=30)  # supersedes r1
    assert r3["superseded"] == [r1["fact_id"]]
    lin.link_assert_result(s3, r3)
    q = "MATCH (s:Step)-[r:READ|WROTE]->(f:Fact) RETURN s.n, type(r), f.id ORDER BY s.n, type(r)"
    assert cypher(client, graph, q) == [
        [1, "WROTE", r1["fact_id"]],
        [2, "READ", r1["fact_id"]],
        [3, "READ", r1["fact_id"]],
        [3, "WROTE", r3["fact_id"]],
    ]
