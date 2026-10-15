"""Slice 2: Fact.surprise is computed once, at write time, inside the single assert statement."""

from __future__ import annotations

import math

import pytest

from plexus.embed import HashEmbedder
from plexus.engram.service import fact_text, normalize

from .conftest import cypher


def stored(client, graph, fact_id):
    return cypher(client, graph, "MATCH (f:Fact {id:$f}) RETURN f.surprise", f=fact_id)[0][0]


def test_first_fact_in_an_empty_scope_gets_the_maximum_novelty(eng, scope, client, graph):
    r = eng.assert_fact("API", "database", "PostgreSQL 16", scope, "alice", now=1000)
    assert r["surprise"] == pytest.approx(0.5)
    assert stored(client, graph, r["fact_id"]) == pytest.approx(0.5)


def test_novelty_is_one_minus_the_best_cosine_to_active_facts_in_the_same_scope(eng, scope, client, graph):
    emb = HashEmbedder()
    eng.assert_fact("Acme Notes API", "hosting region", "us east primary", scope, "alice", now=1000)
    r = eng.assert_fact("Acme Notes API", "hosting zone", "us east primary", scope, "alice", now=2000)
    a = emb.embed([fact_text("Acme Notes API", normalize("hosting region"), "us east primary")])[0]
    b = emb.embed([fact_text("Acme Notes API", normalize("hosting zone"), "us east primary")])[0]
    cos = sum(x * y for x, y in zip(a, b, strict=True))
    assert 0.0 < 1 - cos < 0.5, "fixture must sit strictly between the bounds"
    assert r["surprise"] == pytest.approx(1 - cos, abs=1e-4)
    assert stored(client, graph, r["fact_id"]) == pytest.approx(1 - cos, abs=1e-4)


def test_an_unrelated_fact_is_capped_at_half(eng, scope):
    eng.assert_fact("API", "database", "PostgreSQL 16", scope, "alice", now=1000)
    r = eng.assert_fact("Frontend", "bundler", "esbuild", scope, "alice", now=2000)
    assert r["surprise"] == pytest.approx(0.5)


def test_facts_in_other_scopes_do_not_reduce_novelty(eng, scope):
    other = eng.create_scope("project", "other", inherits=[scope], now=1)
    eng.assert_fact("Acme Notes API", "hosting region", "us east primary", other, "alice", now=1000)
    r = eng.assert_fact("Acme Notes API", "hosting zone", "us east primary", scope, "alice", now=2000)
    assert r["surprise"] == pytest.approx(0.5), "the near fact lives in another scope"


def test_superseding_a_current_fact_scores_point_six(eng, scope, client, graph):
    f1 = eng.assert_fact("API", "database", "PostgreSQL 16", scope, "alice", now=1000)
    r = eng.assert_fact("API", "database", "PostgreSQL 17", scope, "alice", now=2000)
    assert r["superseded"] == [f1["fact_id"]]
    assert r["surprise"] == pytest.approx(0.6)
    assert stored(client, graph, r["fact_id"]) == pytest.approx(0.6)


def test_forced_supersede_of_another_agents_fact_also_scores_point_six(eng, scope):
    eng.assert_fact("API", "database", "PostgreSQL 16", scope, "alice", now=1000)
    r = eng.assert_fact("API", "database", "PostgreSQL 17", scope, "bob", now=2000, supersede=True)
    assert r["superseded"] and r["surprise"] == pytest.approx(0.6)


def test_contradicting_another_agents_fact_scores_point_nine(eng, scope, client, graph):
    f1 = eng.assert_fact("API", "database", "PostgreSQL 16", scope, "alice", now=1000)
    r = eng.assert_fact("API", "database", "MySQL 8", scope, "bob", now=2000)
    assert r["contradicts"] == [f1["fact_id"]]
    assert r["surprise"] == pytest.approx(0.9)
    assert stored(client, graph, r["fact_id"]) == pytest.approx(0.9)


def test_a_duplicate_creates_no_fact_and_stores_nothing(eng, scope, client, graph):
    f1 = eng.assert_fact("API", "database", "PostgreSQL 16", scope, "alice", now=1000)
    before = stored(client, graph, f1["fact_id"])
    r = eng.assert_fact("API", "database", "PostgreSQL 16", scope, "bob", now=2000)
    assert r["duplicate_of"] == f1["fact_id"] and r["surprise"] is None
    assert stored(client, graph, f1["fact_id"]) == before


def test_surprise_is_always_within_zero_and_one(eng, scope):
    for i in range(4):
        r = eng.assert_fact(f"Thing {i}", "kind", f"value number {i}", scope, "alice", now=1000 + i)
        assert 0.0 <= r["surprise"] <= 1.0 and not math.isnan(r["surprise"])
