"""Audit C5: ``lineage/record_step.previous_id`` is the id of the preceding Step when a Step was created, else null.

Before: it was ``last.id`` on every path, so an idempotent repeat of n=2 answered 'x2' (itself) and a refused
or older n answered the agent's latest step.
"""

from __future__ import annotations

from .conftest import cypher


def _step(client, graph, step_id, n, at=1):
    p = {"agent_id": "ag", "step_id": step_id, "n": n, "at": at}
    return client.rw(graph, "lineage/record_step", p)[0]


def test_previous_id_is_the_preceding_step_only_when_a_step_is_created(client, graph):
    r1 = _step(client, graph, "x1", 1)
    assert (r1["created"], r1["step_id"], r1["previous_id"]) == (True, "x1", None)
    r2 = _step(client, graph, "x2", 2)
    assert (r2["created"], r2["step_id"], r2["previous_id"]) == (True, "x2", "x1")

    again2 = _step(client, graph, "y2", 2)  # idempotent repeat of the latest step
    assert (again2["created"], again2["step_id"], again2["previous_id"]) == (False, "x2", None)
    again1 = _step(client, graph, "y1", 1)  # idempotent repeat of an older step
    assert (again1["created"], again1["step_id"], again1["previous_id"]) == (False, "x1", None)
    refused = _step(client, graph, "y0", 0)  # out of order: a later n exists
    assert (refused["created"], refused["step_id"], refused["previous_id"]) == (False, None, None)

    r3 = _step(client, graph, "x3", 3)
    assert (r3["created"], r3["step_id"], r3["previous_id"]) == (True, "x3", "x2")
    chain = cypher(client, graph, "MATCH (a:Step)-[:NEXT]->(b:Step) RETURN a.id, b.id ORDER BY a.n")
    assert chain == [["x1", "x2"], ["x2", "x3"]]
