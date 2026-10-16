"""P9-f: assert_fact / record_decision / handoff write their Step, BY / NEXT, WROTE / READ and DERIVED_FROM
in the same statement as the memory node (Crucible L6-F). Service-level checks of what that leaves behind."""

from __future__ import annotations

import pytest

from plexus.common import StepIntent
from plexus.embed import HashEmbedder
from plexus.engram import Engram
from plexus.engram.errors import UnknownReference
from plexus.lineage import Lineage
from plexus.relay import Relay
from plexus.relay.errors import UnknownReference as RelayUnknown


def q(client, graph, cypher, **p):
    return client.graph(graph).ro_query(cypher, p or None).result_set


@pytest.fixture
def svc(client, graph):
    eng, relay, lin = Engram(client, graph, HashEmbedder()), Relay(client, graph), Lineage(client, graph)
    scope = eng.create_scope("global", "global", now=1)
    relay.register_agent("a", "a", "worker", "test")
    relay.register_agent("b", "b", "worker", "test")
    relay.create_tasks([{"id": "t", "title": "t"}])
    src = lin.create_source("urn:src", now=1)
    return eng, relay, lin, scope, src


def test_assert_fact_writes_its_step_and_derived_from_in_one_statement(client, graph, svc):
    eng, relay, lin, scope, src = svc
    i1 = StepIntent("a", -1, 100)
    r1 = eng.assert_fact("S", "p", "one", scope, "a", source_id=src, now=100, step_intent=i1)
    assert i1.used_id == r1["step_id"] == i1.id
    i2 = StepIntent("a", -1, 200)
    r2 = eng.assert_fact("S", "q", "two", scope, "a", now=200, derived_from=[r1["fact_id"]], step_intent=i2)
    rows = q(client, graph, "MATCH (s:Step)-[:BY]->(:Agent {id: 'a'}) RETURN s.id, s.n, s.at ORDER BY s.n")
    assert rows == [[i1.id, 1, 100], [i2.id, 2, 200]]
    assert q(client, graph, "MATCH (:Step {id: $a})-[:NEXT]->(s:Step) RETURN s.id", a=i1.id) == [[i2.id]]
    for intent, r in ((i1, r1), (i2, r2)):
        assert q(client, graph, "MATCH (:Step {id: $s})-[:WROTE]->(f:Fact) RETURN f.id", s=intent.id) == [
            [r["fact_id"]]
        ]
    assert q(client, graph, "MATCH (:Fact {id: $f})-[:DERIVED_FROM]->(o) RETURN o.id", f=r2["fact_id"]) == [
        [r1["fact_id"]]
    ]
    # a new value supersedes "one": the Step READ the fact it closed; a duplicate is READ, not WROTE
    i3 = StepIntent("a", -1, 300)
    r3 = eng.assert_fact("S", "p", "uno", scope, "a", now=300, step_intent=i3)
    assert r3["superseded"] == [r1["fact_id"]]
    assert q(client, graph, "MATCH (:Step {id: $s})-[r:READ]->(f) RETURN f.id, r.via", s=i3.id) == [
        [r1["fact_id"], "use"]
    ]
    i4 = StepIntent("a", -1, 400)
    r4 = eng.assert_fact("S", "p", "uno", scope, "a", now=400, step_intent=i4)
    assert r4["duplicate_of"] == r3["fact_id"]
    assert q(client, graph, "MATCH (:Step {id: $s})-[:WROTE]->(x) RETURN count(x)", s=i4.id) == [[0]]
    assert q(client, graph, "MATCH (:Step {id: $s})-[:READ]->(f) RETURN f.id", s=i4.id) == [[r3["fact_id"]]]


def test_explicit_step_numbers_are_reused_or_moved_forward(client, graph, svc):
    eng, relay, lin, scope, src = svc
    a = StepIntent("a", 5, 100)
    eng.assert_fact("S", "p", "one", scope, "a", now=100, step_intent=a)
    again = StepIntent("a", 5, 150)  # the same n: the existing Step is reused
    did = relay.record_decision("a", "t", "go", [], step_intent=again)
    assert again.used_id == a.id
    assert q(client, graph, "MATCH (:Step {id: $s})-[:WROTE]->(d:Decision) RETURN d.id", s=a.id) == [[did]]
    behind = StepIntent("a", 3, 200)  # behind the latest step: takes the next number (append-only NEXT chain)
    hid = relay.handoff("a", "b", "t", "here", fact_ids=[], step_intent=behind)
    assert q(
        client, graph, "MATCH (s:Step {id: $s})-[:WROTE]->(:Handoff {id: $h}) RETURN s.n", s=behind.id, h=hid
    ) == [[6]]


def test_a_rejected_write_leaves_no_step_and_no_entity(client, graph, svc):
    eng, relay, lin, scope, src = svc
    before = q(client, graph, "MATCH (n) RETURN count(n)")
    with pytest.raises(UnknownReference):
        eng.assert_fact(
            "New subject", "p", "v", scope, "a", derived_from=["nope"], step_intent=StepIntent("a", -1, 1)
        )
    with pytest.raises(RelayUnknown):
        relay.record_decision("a", "t", "go", ["nope"], step_intent=StepIntent("a", -1, 1))
    assert q(client, graph, "MATCH (n) RETURN count(n)") == before


def test_no_intent_writes_no_step(client, graph, svc):
    eng, relay, lin, scope, src = svc
    r = eng.assert_fact("S", "p", "one", scope, "a", now=100)
    assert r["step_id"] is None
    relay.record_decision("a", "t", "go", [r["fact_id"]])
    assert q(client, graph, "MATCH (s:Step) RETURN count(s)") == [[0]]
