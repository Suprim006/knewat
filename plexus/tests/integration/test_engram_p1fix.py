"""P1-fix regression tests for assert_fact / entity resolution (review findings P1-01, 03, 04, 08, 10)."""

from __future__ import annotations

import pytest

from plexus.embed import EmbeddingDimensionError
from plexus.engram import Engram, UnknownReference

COMMON = " ".join(f"w{i}" for i in range(40))  # 40 shared tokens: one changed digit stays within 0.08


def _count(client, graph, q):
    return client.graph(graph).ro_query(q).result_set[0][0]


# -- P1-01: paraphrase duplicates must not swallow updates -----------------------------------------


def test_near_identical_values_with_different_numbers_are_an_update_not_a_duplicate(eng, proj):
    r1 = eng.assert_fact("Acme", "release", f"{COMMON} build 12", proj, "a1", now=1000)
    r2 = eng.assert_fact("Acme", "release", f"{COMMON} build 13", proj, "a1", now=2000)
    assert r2["duplicate_of"] is None
    assert r2["superseded"] == [r1["fact_id"]]
    hist = eng.fact_history("Acme", "release", proj)
    assert [(h["status"], h["valid_from"], h["valid_to"]) for h in hist][0][0] == "superseded"
    assert len(hist) == 2


def test_numeric_difference_from_other_agent_is_a_contradiction(eng, proj):
    r1 = eng.assert_fact("Acme", "port", f"{COMMON} 8080", proj, "a1", now=1000)
    r2 = eng.assert_fact("Acme", "port", f"{COMMON} 8081", proj, "a2", now=2000)
    assert r2["duplicate_of"] is None and r2["contradicts"] == [r1["fact_id"]]


def test_reordered_value_with_same_numbers_is_still_a_paraphrase_duplicate(eng, client, graph, proj):
    r1 = eng.assert_fact("Acme", "release", "build 12 acme service", proj, "a1", now=1000)
    r2 = eng.assert_fact("Acme", "release", "service acme build 12", proj, "a2", now=2000)
    assert r2["duplicate_of"] == r1["fact_id"]
    assert _count(client, graph, "MATCH (f:Fact) RETURN count(f)") == 1


def test_same_words_different_version_tokens_never_duplicate(eng, proj):
    r1 = eng.assert_fact("Acme", "api", "release v1 of the notes api", proj, "a1", now=1)
    r2 = eng.assert_fact("Acme", "api", "release v2 of the notes api", proj, "a1", now=2)
    assert r2["duplicate_of"] is None and r2["superseded"] == [r1["fact_id"]]


# -- P1-03: A/B/A ----------------------------------------------------------------------------------


def test_aba_reassert_closes_own_earlier_value_and_links_supersedes(eng, client, graph, proj):
    ra = eng.assert_fact("Acme", "engine", "mysql", proj, "A", now=1000)
    rb = eng.assert_fact("Acme", "engine", "postgres", proj, "B", now=2000)
    assert rb["contradicts"] == [ra["fact_id"]]
    rc = eng.assert_fact("Acme", "engine", "postgres", proj, "A", now=3000)
    assert rc["duplicate_of"] == rb["fact_id"]
    assert rc["superseded"] == [ra["fact_id"]]
    hist = {h["value"]: h for h in eng.fact_history("Acme", "engine", proj)}
    assert (hist["mysql"]["status"], hist["mysql"]["valid_to"]) == ("superseded", 3000)
    assert hist["postgres"]["status"] == "active"
    edge = client.graph(graph).ro_query("MATCH (a:Fact)-[:SUPERSEDES]->(b:Fact) RETURN a.id, b.id").result_set
    assert [list(e) for e in edge] == [[rb["fact_id"], ra["fact_id"]]]
    assert [r["value"] for r in eng.recall("Acme engine", proj, k=5)] == ["postgres"]


def test_dup_path_does_not_close_other_agents_facts(eng, proj):
    r1 = eng.assert_fact("Acme", "engine", "postgres", proj, "A", now=1000)
    r2 = eng.assert_fact("Acme", "engine", "mysql", proj, "B", now=2000)
    r3 = eng.assert_fact("Acme", "engine", "postgres", proj, "A", now=3000)  # exact dup of own fact
    assert r3["duplicate_of"] == r1["fact_id"] and r3["superseded"] == []
    assert {h["status"] for h in eng.fact_history("Acme", "engine", proj)} == {"active"}
    assert r2["contradicts"] == [r1["fact_id"]]


# -- P1-08: duplicate assertion is timestamped -----------------------------------------------------


def test_asserted_by_edges_carry_the_assertion_time_including_duplicates(eng, client, graph, proj):
    r1 = eng.assert_fact("Acme", "database", "postgres", proj, "a1", now=1000)
    eng.assert_fact("Acme", "database", "postgres", proj, "a2", now=2500)
    eng.assert_fact("Acme", "database", "postgres", proj, "a2", now=9000)  # repeat: keeps first time
    rows = (
        client.graph(graph)
        .ro_query(
            "MATCH (f:Fact {id:$f})-[r:ASSERTED_BY]->(a:Agent) RETURN a.id, r.at ORDER BY a.id",
            {"f": r1["fact_id"]},
        )
        .result_set
    )
    assert [list(r) for r in rows] == [["a1", 1000], ["a2", 2500]]
    assert _count(client, graph, "MATCH ()-[r:DUPLICATES]->() RETURN count(r)") == 0


# -- P1-04: entity collapse ------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("a", "b"),
    [
        ("service-1", "service-2"),
        ("PostgreSQL 15", "PostgreSQL 16"),
        ("Acme Notes API v1", "Acme Notes API v2"),
    ],
)
def test_entities_differing_only_in_numbers_stay_distinct(eng, a, b):
    ea = eng.resolve_entity_ex(a, "service")
    eb = eng.resolve_entity_ex(b, "service")
    assert ea["id"] != eb["id"] and eb["created"] is True


def test_default_entity_threshold_is_tighter():
    from plexus.engram.service import ENTITY_NEAR

    assert ENTITY_NEAR == 0.10


def test_vector_entity_match_requires_same_numeric_tokens(eng):
    """Even when the vector is within the threshold, differing number tokens block the merge."""
    e1 = Engram(eng.client, eng.graph, eng.embedder, entity_threshold=1.0)  # accept anything vector-near
    a = e1.resolve_entity_ex("alpha beta gamma delta 3", "thing")
    b = e1.resolve_entity_ex("alpha beta gamma delta 4", "thing")
    assert a["id"] != b["id"]


# -- P1-10: unknown references ---------------------------------------------------------------------


def test_unknown_episode_or_source_raises_and_writes_nothing(eng, client, graph, proj):
    with pytest.raises(UnknownReference) as exc:
        eng.assert_fact("Acme", "database", "pg", proj, "ghost", episode_id="no-such-episode", now=1)
    assert exc.value.kind == "episode" and exc.value.ids == ["no-such-episode"]
    with pytest.raises(UnknownReference) as exc:
        eng.assert_fact("Acme", "database", "pg", proj, "ghost", source_id="no-such-source", now=1)
    assert exc.value.kind == "source"
    with pytest.raises(UnknownReference) as exc:
        eng.assert_fact("Acme", "database", "pg", "no-such-scope", "ghost", now=1)
    assert exc.value.kind == "scope"
    assert isinstance(exc.value, LookupError)  # backward compatible with the old LookupError
    assert _count(client, graph, "MATCH (f:Fact) RETURN count(f)") == 0
    assert _count(client, graph, "MATCH (a:Agent) RETURN count(a)") == 0  # not even the Agent was merged


# -- embedding dimension guard ---------------------------------------------------------------------


def test_wrong_dimension_embedder_is_rejected_before_writing(client, graph):
    class Bad:
        dim = 3

        def embed(self, texts):
            return [[1.0, 0.0, 0.0] for _ in texts]

    bad = Engram(client, graph, Bad())
    with pytest.raises(EmbeddingDimensionError):
        bad.assert_fact("Acme", "database", "pg", "x", "a1", now=1)
    with pytest.raises(EmbeddingDimensionError):
        bad.resolve_entity("Acme")
    assert _count(client, graph, "MATCH (n) RETURN count(n)") == 0
