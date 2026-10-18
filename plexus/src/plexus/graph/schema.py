"""Apply the schema (indexes, full-text, vector, UNIQUE constraints) to a graph, idempotently."""

from __future__ import annotations

import logging
import time

from redis.exceptions import ResponseError

from plexus.graph.client import GraphClient

log = logging.getLogger(__name__)

SCHEMA_QUERIES = ("schema/indexes", "schema/fulltext", "schema/vector")

# Labels whose `id` is UNIQUE (graph model v1 §2). Each needs its exact-match index first (schema/indexes).
UNIQUE_LABELS = ("Task", "Fact", "Agent", "Decision", "Handoff")

# Entity.norm_name is UNIQUE too, the backstop behind `engram/resolve_entity`. A graph that already holds
# two entities with one norm_name leaves this constraint FAILED: reported as a warning
# (`plexus migrate entities`), never raised, so a legacy tenant keeps starting.
ENTITY_KEY = ("Entity", "norm_name")

# FalkorDB 6.0.2 messages when the object is already there (verified live):
#   CREATE INDEX ...            -> "Attribute 'id' is already indexed"
#   GRAPH.CONSTRAINT CREATE ... -> "Constraint already exists"
ALREADY_EXISTS = ("already indexed", "constraint already exists")
# A schema command that meets another process's in-flight index/constraint build on the same graph fails
# with this (6.0.2); it is transient, so apply_schema retries it until timeout_s.
BUSY = "another write is in progress"


def _retry_busy(fn, deadline: float, poll_s: float = 0.05):  # noqa: ANN001, ANN202 - tiny local helper
    while True:
        try:
            return fn()
        except ResponseError as exc:
            if BUSY not in str(exc).lower() or time.monotonic() >= deadline:
                raise
            time.sleep(poll_s)


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
    *,
    soft: tuple[tuple[str, str], ...] = (ENTITY_KEY,),
) -> None:
    """Block until every ``labels`` UNIQUE(id) constraint is OPERATIONAL; raise on FAILED or timeout.

    The ``soft`` (label, property) constraints are waited for the same way but never raise: a FAILED one
    (legacy duplicates) or a slow build is logged as a warning instead.
    """
    deadline = time.monotonic() + timeout_s
    status: dict[str, str] = {}
    while True:
        found = _constraint_status(client, graph)
        status = {label: found.get((label, ("id",)), "MISSING") for label in labels}
        soft_status = {f"{lab}.{prop}": found.get((lab, (prop,)), "MISSING") for lab, prop in soft}
        failed = [label for label, s in status.items() if s == "FAILED"]
        if failed:
            raise SchemaError(f"constraint(s) FAILED on {graph}: {', '.join(failed)}")
        hard_ok = all(s == "OPERATIONAL" for s in status.values())
        soft_done = all(s in ("OPERATIONAL", "FAILED") for s in soft_status.values())
        timed_out = time.monotonic() >= deadline
        if hard_ok and (soft_done or timed_out):
            for key, s in soft_status.items():
                if s != "OPERATIONAL":
                    log.warning(
                        "constraint UNIQUE(%s) on %s is %s: `plexus migrate entities` lists the duplicates",
                        key,
                        graph,
                        s,
                    )
            return
        if timed_out:
            raise SchemaError(f"constraints not OPERATIONAL on {graph} after {timeout_s}s: {status}")
        time.sleep(poll_s)


def apply_schema(client: GraphClient, graph: str, timeout_s: float = 30.0) -> None:
    """Create indexes and UNIQUE constraints on ``graph``. Safe to run any number of times.

    Only errors whose message says the object already exists are ignored; "another write is in progress" (a
    concurrent schema build on the same graph) is retried until ``timeout_s``; everything else raises.
    """
    deadline = time.monotonic() + timeout_s
    for name in SCHEMA_QUERIES:
        _retry_busy(lambda name=name: client.rw_script(graph, name, tolerate=ALREADY_EXISTS), deadline)

    g = client.graph(graph)
    for label, prop in [(label, "id") for label in UNIQUE_LABELS] + [ENTITY_KEY]:
        try:
            # GRAPH.CONSTRAINT CREATE ... UNIQUE NODE <Label> PROPERTIES 1 <prop>
            _retry_busy(lambda label=label, prop=prop: g.create_node_unique_constraint(label, prop), deadline)
        except ResponseError as exc:
            if not any(t in str(exc).lower() for t in ALREADY_EXISTS):
                raise
    wait_for_constraints(client, graph, timeout_s=timeout_s)
