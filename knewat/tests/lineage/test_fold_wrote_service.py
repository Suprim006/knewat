"""P9-int: the service-level write statements take a ``step_id`` and create the WROTE edge themselves."""

from __future__ import annotations

from plexus.embed import HashEmbedder
from plexus.engram import Engram
from plexus.lineage import Lineage
from plexus.relay import Relay


def test_service_level_wrote_needs_no_link_step(client, graph, clock):
    eng, rel, lin = (
        Engram(client, graph, HashEmbedder()),
        Relay(client, graph, clock=clock),
        Lineage(client, graph, clock=clock),
    )
    rel.register_agent("a", "a", "builder", "t")
    rel.create_tasks([{"id": "t1", "title": "x"}])
    st = lin.record_step("a")
    gid = eng.create_scope("global", "global", now=1)
    r = eng.assert_fact("Cache", "engine", "Redis", gid, "a", step_id=st)
    d = rel.record_decision("a", "t1", "use it", [r["fact_id"]], step_id=st)
    h = rel.handoff("a", "a", "t1", "n", [], [r["fact_id"]], step_id=st)
    got = (
        client.graph(graph)
        .ro_query("MATCH (:Step {id: $s})-[:WROTE]->(x) RETURN collect(x.id)", {"s": st})
        .result_set[0][0]
    )
    assert sorted(got) == sorted([r["fact_id"], d, h])
    # without a step id nothing is linked (the runtime's after-write link does that)
    r2 = eng.assert_fact("Cache", "ttl", "60 s", gid, "a")
    assert client.graph(graph).ro_query(
        "MATCH (:Step)-[:WROTE]->(:Fact {id: $i}) RETURN count(*)", {"i": r2["fact_id"]}
    ).result_set == [[0]]
