from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor

from plexus.engram import Engram
from plexus.graph.client import GraphClient


def test_20_threads_same_fact_exactly_one_active(eng, client, graph, proj):
    n = 20
    barrier_clients = [
        GraphClient(host=client.host, port=client.port, password="", library=client.library) for _ in range(n)
    ]
    try:
        workers = [Engram(c, graph, eng.embedder) for c in barrier_clients]

        def go(i):
            return workers[i].assert_fact(
                "Acme Notes API", "database", "PostgreSQL", proj, f"agent-{i}", now=1000 + i
            )

        with ThreadPoolExecutor(max_workers=n) as pool:
            results = list(pool.map(go, range(n)))
    finally:
        for c in barrier_clients:
            c.close()

    g = client.graph(graph)
    active = g.ro_query("MATCH (f:Fact {status:'active'}) RETURN count(f)").result_set[0][0]
    total = g.ro_query("MATCH (f:Fact) RETURN count(f)").result_set[0][0]
    entities = g.ro_query("MATCH (e:Entity) RETURN count(e)").result_set[0][0]
    asserters = g.ro_query("MATCH (:Fact)-[r:ASSERTED_BY]->(a:Agent) RETURN count(DISTINCT a)").result_set[0][
        0
    ]
    assert (active, total, entities) == (1, 1, 1)
    assert asserters == n  # every agent is credited on the single fact
    fact_ids = {r["fact_id"] for r in results}
    assert len(fact_ids) == 1
    assert sum(1 for r in results if r["duplicate_of"] is None) == 1
    assert sum(1 for r in results if r["duplicate_of"] is not None) == n - 1


def test_20_threads_distinct_values_same_agent_keep_one_active(eng, client, graph, proj):
    """Racing supersedes by one agent: whatever the order, the chain stays linear with one active head."""
    n = 20
    cs = [
        GraphClient(host=client.host, port=client.port, password="", library=client.library) for _ in range(n)
    ]
    try:
        workers = [Engram(c, graph, eng.embedder) for c in cs]
        eng.resolve_entity("Acme Notes API")  # avoid measuring the entity-creation race here

        def go(i):
            return workers[i].assert_fact(
                "Acme Notes API", "version", f"release number {i} {'x' * i}", proj, "solo", now=2000 + i
            )

        with ThreadPoolExecutor(max_workers=n) as pool:
            list(pool.map(go, range(n)))
    finally:
        for c in cs:
            c.close()
    g = client.graph(graph)
    assert g.ro_query("MATCH (f:Fact {status:'active'}) RETURN count(f)").result_set == [[1]]
    assert g.ro_query("MATCH (f:Fact) RETURN count(f)").result_set == [[n]]
    assert g.ro_query("MATCH ()-[r:SUPERSEDES]->() RETURN count(r)").result_set == [[n - 1]]
