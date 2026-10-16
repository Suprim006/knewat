"""P9-d: UNIQUE(Entity.norm_name) as the backstop behind ``engram/resolve_entity``."""

from __future__ import annotations

import logging

import pytest
from redis.exceptions import ResponseError

from plexus.embed import HashEmbedder
from plexus.engram import Engram
from plexus.graph.schema import ENTITY_KEY, apply_schema, wait_for_constraints

DUP_MSG = "unique constraint violation on node of type Entity"


def _norm_name_status(client, graph) -> str | None:
    rows = client.ro(graph, "schema/list_constraints")
    found = [r["status"] for r in rows if r["label"] == "Entity" and r["properties"] == ["norm_name"]]
    return found[0] if found else None


def test_entity_norm_name_constraint_is_operational_and_enforced(client, graph):
    assert ENTITY_KEY == ("Entity", "norm_name")
    assert _norm_name_status(client, graph) == "OPERATIONAL"
    g = client.graph(graph)
    g.query("CREATE (:Entity {id: '1', norm_name: 'x'})")
    with pytest.raises(ResponseError, match="(?i)unique constraint"):
        g.query("CREATE (:Entity {id: '2', norm_name: 'x'})")
    g.query("MERGE (e:Entity {norm_name: 'x'}) ON CREATE SET e.id = '3'")  # MERGE on an existing key is fine
    assert g.ro_query("MATCH (e:Entity) RETURN count(e), collect(e.id)").result_set == [[1, ["1"]]]


def test_apply_schema_twice_keeps_the_entity_constraint(client, empty_graph):
    apply_schema(client, empty_graph)
    apply_schema(client, empty_graph)
    assert _norm_name_status(client, empty_graph) == "OPERATIONAL"


def test_entities_without_norm_name_do_not_collide(client, graph):
    g = client.graph(graph)
    g.query("CREATE (:Entity {id: 'a'}), (:Entity {id: 'b'})")  # older tests / fixtures build such nodes
    assert g.ro_query("MATCH (e:Entity) RETURN count(e)").result_set[0][0] == 2


def test_legacy_duplicates_do_not_break_apply_schema(client, empty_graph, caplog):
    """Two Entities with one norm_name already exist: the constraint ends FAILED, apply_schema and entity
    resolution keep working (the migration report lists the duplicates), and a warning says so."""
    g = client.graph(empty_graph)
    g.query("CREATE INDEX FOR (n:Entity) ON (n.norm_name)")
    g.query("CREATE (:Entity {id: '1', norm_name: 'x'}), (:Entity {id: '2', norm_name: 'x'})")
    with caplog.at_level(logging.WARNING, logger="plexus.graph.schema"):
        apply_schema(client, empty_graph)
    assert _norm_name_status(client, empty_graph) == "FAILED"
    assert any("norm_name" in r.getMessage() for r in caplog.records)
    eng = Engram(client, empty_graph, HashEmbedder())
    assert eng.resolve_entity_ex("x")["matched_by"] == "exact"  # still resolves (to one of the two)


def test_wait_for_constraints_still_raises_for_a_failed_id_constraint(client, empty_graph):
    from plexus.graph.schema import SchemaError

    g = client.graph(empty_graph)
    g.query("CREATE INDEX FOR (n:Task) ON (n.id)")
    g.query("CREATE (:Task {id: 't'}), (:Task {id: 't'})")
    with pytest.raises(SchemaError, match="FAILED"):
        apply_schema(client, empty_graph)


# -- retry on a constraint error --------------------------------------------------------------------------


class _FlakyRw:
    """Wraps ``client.rw``: the first ``fail`` calls to resolve_entity raise ``exc``, the rest go through."""

    def __init__(self, client, fail: int, exc: Exception):
        self.client, self.fail, self.exc, self.real = client, fail, exc, client.rw
        self.params: list[dict] = []

    def __call__(self, graph, name, params=None, **kw):
        if name == "engram/resolve_entity":
            self.params.append(dict(params))
            if len(self.params) <= self.fail:
                raise self.exc
        return self.real(graph, name, params, **kw)


def test_resolve_retries_once_on_a_unique_constraint_error(client, graph):
    eng = Engram(client, graph, HashEmbedder())
    flaky = _FlakyRw(client, 1, ResponseError(DUP_MSG))
    client.rw = flaky
    try:
        r = eng.resolve_entity_ex("Payment Service", "service")
    finally:
        client.rw = flaky.real
    assert (r["created"], r["matched_by"]) == (True, "new")
    assert len(flaky.params) == 2
    assert flaky.params[0]["entity_id"] != flaky.params[1]["entity_id"]  # the retry is a fresh attempt


def test_resolve_gives_up_after_one_retry(client, graph):
    eng = Engram(client, graph, HashEmbedder())
    flaky = _FlakyRw(client, 2, ResponseError(DUP_MSG))
    client.rw = flaky
    try:
        with pytest.raises(ResponseError, match="(?i)unique constraint"):
            eng.resolve_entity_ex("Payment Service", "service")
    finally:
        client.rw = flaky.real
    assert len(flaky.params) == 2


def test_resolve_does_not_retry_other_errors(client, graph):
    eng = Engram(client, graph, HashEmbedder())
    flaky = _FlakyRw(client, 1, ResponseError("Query timed out"))
    client.rw = flaky
    try:
        with pytest.raises(ResponseError, match="timed out"):
            eng.resolve_entity_ex("Payment Service", "service")
    finally:
        client.rw = flaky.real
    assert len(flaky.params) == 1


def test_wait_for_constraints_default_covers_the_entity_key(client, graph):
    wait_for_constraints(client, graph)  # id constraints + Entity.norm_name, already operational
