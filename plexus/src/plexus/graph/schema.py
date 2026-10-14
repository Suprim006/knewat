"""Apply the schema (indexes, full-text, vector, UNIQUE constraints) to a graph, idempotently."""

from __future__ import annotations

import time

from redis.exceptions import ResponseError

from plexus.graph.client import GraphClient

SCHEMA_QUERIES = ("schema/indexes", "schema/fulltext", "schema/vector")

# Labels whose `id` is UNIQUE (graph model v1 §2). Each needs its exact-match index first (schema/indexes).
UNIQUE_LABELS = ("Task", "Fact", "Agent", "Decision", "Handoff")

# FalkorDB 6.0.2 messages when the object is already there (verified live):
#   CREATE INDEX ...            -> "Attribute 'id' is already indexed"
#   GRAPH.CONSTRAINT CREATE ... -> "Constraint already exists"
ALREADY_EXISTS = ("already indexed", "constraint already exists")


class SchemaError(RuntimeError):
    pass


def _constraint_status(client: GraphClient, graph: str) -> dict[tuple[str, tuple[str, ...]], str]:
    rows = client.ro(graph, "schema/list_constraints")
    return {(r["label"], tuple(r["properties"])): r["status"] for r in rows if r["type"] == "UNIQUE"}


def wait_for_constraints(
    client: GraphClient,
    graph: str,
    labels: tuple[str, ...] = UNIQUE_LABELS,
    timeout_s: float = 30.0,
    poll_s: float = 0.05,
) -> None:
    """Block until every ``labels`` UNIQUE(id) constraint is OPERATIONAL; raise on FAILED or timeout."""
    deadline = time.monotonic() + timeout_s
    status: dict[str, str] = {}
    while True:
        found = _constraint_status(client, graph)
        status = {label: found.get((label, ("id",)), "MISSING") for label in labels}
        failed = [label for label, s in status.items() if s == "FAILED"]
        if failed:
            raise SchemaError(f"constraint(s) FAILED on {graph}: {', '.join(failed)}")
        if all(s == "OPERATIONAL" for s in status.values()):
            return
        if time.monotonic() >= deadline:
            raise SchemaError(f"constraints not OPERATIONAL on {graph} after {timeout_s}s: {status}")
        time.sleep(poll_s)


def apply_schema(client: GraphClient, graph: str, timeout_s: float = 30.0) -> None:
    """Create indexes and UNIQUE(id) constraints on ``graph``. Safe to run any number of times.

    Only errors whose message says the object already exists are ignored; everything else raises.
    """
    for name in SCHEMA_QUERIES:
        client.rw_script(graph, name, tolerate=ALREADY_EXISTS)

    g = client.graph(graph)
    for label in UNIQUE_LABELS:
        try:
            g.create_node_unique_constraint(
                label, "id"
            )  # GRAPH.CONSTRAINT CREATE ... UNIQUE NODE <Label> PROPERTIES 1 id
        except ResponseError as exc:
            if not any(t in str(exc).lower() for t in ALREADY_EXISTS):
                raise
    wait_for_constraints(client, graph, timeout_s=timeout_s)
