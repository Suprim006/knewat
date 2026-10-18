from __future__ import annotations

import pytest


def _count(client, graph, label):
    return client.graph(graph).ro_query(f"MATCH (n:{label}) RETURN count(n)").result_set[0][0]


def test_resolve_exact_is_case_and_space_insensitive(eng, client, graph):
    a = eng.resolve_entity("Acme Notes API", "service")
    b = eng.resolve_entity("  acme   NOTES api ", "service")
    assert a == b
    assert _count(client, graph, "Entity") == 1
    info = eng.resolve_entity_ex("ACME notes API", "service")
    assert info["matched_by"] == "exact" and info["created"] is False and info["name"] == "Acme Notes API"


def test_resolve_creates_distinct_entities(eng, client, graph):
    a = eng.resolve_entity("Acme Notes API", "service")
    b = eng.resolve_entity("Postgres", "tech")
    assert a != b
    assert _count(client, graph, "Entity") == 2


def test_resolve_fulltext_and_kind_guard(eng, client, graph):
    a = eng.resolve_entity("Acme Notes API service", "service")
    info = eng.resolve_entity_ex("Acme Notes API", "service")  # token subset, Jaccard 0.75
    assert info["id"] == a and info["matched_by"] == "fulltext"
    # a different kind never merges, and a weak token overlap does not either
    assert eng.resolve_entity("Acme Notes API", "person") != a
    assert eng.resolve_entity("Acme Billing Gateway", "service") != a


def test_resolve_vector_match(client, graph):
    from knewat.embed import HashEmbedder
    from knewat.engram import Engram

    # word-level hashing: a single repeated token is "near" (same direction) but not the same name
    e = Engram(client, graph, HashEmbedder(), entity_threshold=0.15)
    a = e.resolve_entity("postgres", "tech")
    info = e.resolve_entity_ex("postgres postgres", "tech")
    assert info["id"] == a and info["matched_by"] in ("fulltext", "vector")
    # far away stays separate
    assert e.resolve_entity("redis", "tech") != a


def test_resolve_rejects_empty(eng):
    with pytest.raises(ValueError):
        eng.resolve_entity("   ")


def test_create_scope_is_idempotent_and_inherits(eng, client, graph):
    g = eng.create_scope("global", "global")
    assert eng.create_scope("global", "global") == g
    p = eng.create_scope("project", "acme", inherits=[g])
    assert eng.create_scope("project", "acme", inherits=[g]) == p
    u = eng.create_scope("user", "alice", inherits=[p])
    assert _count(client, graph, "Scope") == 3
    rows = client.graph(graph).ro_query(
        "MATCH (:Scope {id:$u})-[:INHERITS*1..3]->(a:Scope) RETURN a.name ORDER BY a.name", {"u": u}
    )
    assert [r[0] for r in rows.result_set] == ["acme", "global"]


def test_create_scope_unknown_parent_writes_nothing(eng, client, graph):
    with pytest.raises(LookupError):
        eng.create_scope("project", "x", inherits=["missing"])
    assert _count(client, graph, "Scope") == 0
    with pytest.raises(ValueError):
        eng.create_scope("team", "x")
