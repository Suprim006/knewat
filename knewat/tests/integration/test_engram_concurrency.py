from __future__ import annotations

import threading
from typing import Any

from knewat.engram import Engram
from knewat.graph.client import GraphClient


def _race(client, graph, embedder, n, fn) -> list[Any]:
    """Run ``fn(engram, i)`` on n threads (own connection each), released together by a Barrier."""
    clients = [
        GraphClient(host=client.host, port=client.port, password="", library=client.library) for _ in range(n)
    ]
    barrier = threading.Barrier(n)
    results: list[Any] = [None] * n
    errors: list[BaseException] = []

    def worker(i: int):
        try:
            barrier.wait(timeout=60)
            results[i] = fn(Engram(clients[i], graph, embedder), i)
        except BaseException as exc:  # noqa: BLE001 - re-raised below
            errors.append(exc)

    threads = [threading.Thread(target=worker, args=(i,)) for i in range(n)]
    try:
        for t in threads:
            t.start()
        for t in threads:
            t.join()
    finally:
        for c in clients:
            c.close()
    assert not errors, errors
    return results


def test_20_threads_same_fact_exactly_one_active(eng, client, graph, proj):
    n = 20
    results = _race(
        client,
        graph,
        eng.embedder,
        n,
        lambda w, i: w.assert_fact(
            "Acme Notes API", "database", "PostgreSQL", proj, f"agent-{i}", now=1000 + i
        ),
    )

    g = client.graph(graph)
    active = g.ro_query("MATCH (f:Fact {status:'active'}) RETURN count(f)").result_set[0][0]
    total = g.ro_query("MATCH (f:Fact) RETURN count(f)").result_set[0][0]
    entities = g.ro_query("MATCH (e:Entity) RETURN count(e)").result_set[0][0]
    asserters = g.ro_query("MATCH (:Fact)-[r:ASSERTED_BY]->(a:Agent) RETURN count(DISTINCT a)").result_set[0][
        0
    ]
    assert (active, total, entities) == (1, 1, 1)
    assert asserters == n  # every agent is credited on the single fact
    assert len({r["fact_id"] for r in results}) == 1
    assert sum(1 for r in results if r["duplicate_of"] is None) == 1
    assert sum(1 for r in results if r["duplicate_of"] is not None) == n - 1
    # every ASSERTED_BY edge is timestamped with that agent's own `now`
    at = g.ro_query("MATCH (:Fact)-[r:ASSERTED_BY]->(a:Agent) RETURN a.id, r.at").result_set
    assert {a: t for a, t in at} == {f"agent-{i}": 1000 + i for i in range(n)}


def _chain(client, graph):
    """Facts of the (single) supersede chain, oldest first, by following SUPERSEDES from the head."""
    g = client.graph(graph)
    rows = g.ro_query("MATCH (f:Fact) RETURN f.id, f.valid_from, f.valid_to, f.status").result_set
    facts = {r[0]: r for r in rows}
    edges = dict(g.ro_query("MATCH (a:Fact)-[:SUPERSEDES]->(b:Fact) RETURN a.id, b.id").result_set)
    assert len(edges) == len(facts) - 1  # a linear chain: every fact but the oldest supersedes exactly one
    heads = [i for i in facts if i not in edges.values()]
    assert len(heads) == 1
    order = [heads[0]]
    while order[-1] in edges:
        order.append(edges[order[-1]])
    assert len(order) == len(facts)
    return [facts[i] for i in reversed(order)]


def test_20_threads_distinct_values_same_agent_keep_one_active(eng, client, graph, proj):
    """Racing supersedes by one agent: whatever the order, the chain is linear, with contiguous windows."""
    n = 20
    eng.resolve_entity("Acme Notes API")  # avoid measuring the entity-creation race here
    _race(
        client,
        graph,
        eng.embedder,
        n,
        lambda w, i: w.assert_fact(
            "Acme Notes API", "version", f"release number {i} {'x' * i}", proj, "solo", now=2000 + i
        ),
    )
    g = client.graph(graph)
    assert g.ro_query("MATCH (f:Fact {status:'active'}) RETURN count(f)").result_set == [[1]]
    assert g.ro_query("MATCH (f:Fact) RETURN count(f)").result_set == [[n]]
    assert g.ro_query("MATCH ()-[r:SUPERSEDES]->() RETURN count(r)").result_set == [[n - 1]]

    chain = _chain(client, graph)
    open_to = 9_999_999_999_999
    assert [f[3] for f in chain] == ["superseded"] * (n - 1) + ["active"]
    assert chain[-1][2] == open_to
    for older, newer in zip(chain, chain[1:], strict=False):
        assert older[1] <= older[2], "a closed window must not be negative"
        assert older[2] == newer[1], "the old version ends exactly when the next one starts"
    assert all(a[1] <= b[1] for a, b in zip(chain, chain[1:], strict=False))  # valid_from never goes back


def test_20_threads_two_values_two_agents_each_keeps_a_consistent_window(eng, client, graph, proj):
    """Two agents racing different values: only contradictions, never a lost or half-closed version."""
    n = 20
    eng.resolve_entity("Acme")
    _race(
        client,
        graph,
        eng.embedder,
        n,
        lambda w, i: w.assert_fact(
            "Acme", "engine", f"value-{i % 2}-{i}", proj, f"agent-{i % 2}", now=3000 + i
        ),
    )
    g = client.graph(graph)
    # each agent's own earlier values are superseded, so each agent has exactly one active belief
    rows = g.ro_query(
        "MATCH (f:Fact {status:'active'})-[:ASSERTED_BY]->(a:Agent) RETURN a.id, count(f) ORDER BY a.id"
    ).result_set
    assert [list(r) for r in rows] == [["agent-0", 1], ["agent-1", 1]]
    bad = g.ro_query("MATCH (f:Fact) WHERE f.valid_to < f.valid_from RETURN count(f)").result_set[0][0]
    assert bad == 0
