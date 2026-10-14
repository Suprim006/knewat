"""Tests that need the real bge-small model (slow: first run downloads ~130 MB to PLEXUS_EMBED_CACHE)."""

from __future__ import annotations

import pytest

from plexus.embed import FastEmbedder
from plexus.engram import Engram

pytestmark = pytest.mark.slow


@pytest.fixture(scope="module")
def fast() -> FastEmbedder:
    return FastEmbedder()


@pytest.fixture
def feng(client, graph, fast) -> Engram:
    return Engram(client, graph, fast)


@pytest.fixture
def fproj(feng):
    g = feng.create_scope("global", "global")
    return feng.create_scope("project", "acme", inherits=[g])


def _count_facts(client, graph):
    return client.graph(graph).ro_query("MATCH (f:Fact) RETURN count(f)").result_set[0][0]


def test_paraphrase_duplicate_is_not_a_new_fact(feng, client, graph, fproj):
    r1 = feng.assert_fact("Acme Notes API", "database", "PostgreSQL 16", fproj, "a1", now=1000)
    r2 = feng.assert_fact("Acme Notes API", "database", "Postgres version 16", fproj, "a2", now=2000)
    assert r2["duplicate_of"] == r1["fact_id"] and r2["superseded"] == [] and r2["contradicts"] == []
    assert _count_facts(client, graph) == 1
    asserted = client.graph(graph).ro_query(
        "MATCH (:Fact)-[:ASSERTED_BY]->(a:Agent) RETURN a.id ORDER BY a.id"
    )
    assert [r[0] for r in asserted.result_set] == ["a1", "a2"]


def test_close_but_different_values_are_not_duplicates(feng, client, graph, fproj):
    r1 = feng.assert_fact("Acme Notes API", "database", "PostgreSQL 16", fproj, "a1", now=1000)
    r2 = feng.assert_fact("Acme Notes API", "database", "PostgreSQL 15", fproj, "a1", now=2000)
    r3 = feng.assert_fact("Acme Notes API", "database", "MySQL 8", fproj, "a2", now=3000)
    assert r2["duplicate_of"] is None and r2["superseded"] == [r1["fact_id"]]
    assert r3["duplicate_of"] is None and r3["contradicts"] == [r2["fact_id"]]


def test_entity_paraphrase_resolves_by_vector(feng):
    a = feng.resolve_entity("PostgreSQL", "tech")
    info = feng.resolve_entity_ex("Postgres", "tech")
    assert info["id"] == a and info["matched_by"] == "vector"
    assert feng.resolve_entity("Redis", "tech") != a


def test_semantic_recall_finds_the_right_fact(feng, fproj):
    feng.assert_fact("Acme Notes API", "database", "PostgreSQL 16", fproj, "a1", now=1000)
    feng.assert_fact("Acme Notes API", "deploy day", "Fridays are forbidden", fproj, "a1", now=1000)
    feng.assert_fact("Acme Notes API", "language", "Python 3.12", fproj, "a1", now=1000)
    got = feng.recall("Which database does the notes API use?", fproj, k=3)
    assert got[0]["value"] == "PostgreSQL 16"
    got = feng.recall("When may we deploy?", fproj, k=3)
    assert got[0]["predicate"] == "deploy day"
