from __future__ import annotations

import pytest

from plexus.engram import OPEN


def _facts(client, graph, status=None):
    q = "MATCH (f:Fact) RETURN f.id, f.value, f.status, f.valid_from, f.valid_to ORDER BY f.valid_from"
    return client.graph(graph).ro_query(q).result_set


def _edges(client, graph, rel):
    return client.graph(graph).ro_query(f"MATCH (a)-[r:{rel}]->(b) RETURN a.id, b.id").result_set


def test_first_assertion_creates_fact_with_provenance(eng, client, graph, proj):
    s = eng.start_session("a1", "planner")
    ep = eng.remember_episode(s, "user", "we use postgres")
    r = eng.assert_fact("Acme Notes API", "database", "PostgreSQL 16", proj, "a1", episode_id=ep, now=1000)
    assert r["superseded"] == [] and r["duplicate_of"] is None and r["contradicts"] == []
    f = (
        client.graph(graph)
        .ro_query(
            "MATCH (f:Fact {id:$id})-[:ABOUT]->(e:Entity), (f)-[:IN_SCOPE]->(s:Scope),"
            " (f)-[:ASSERTED_BY]->(a:Agent),"
            " (f)-[:DERIVED_FROM]->(x:Episode) "
            "RETURN e.name, s.name, a.id, x.id, f.status, f.valid_from, f.valid_to,"
            " f.confidence, f.predicate",
            {"id": r["fact_id"]},
        )
        .result_set
    )
    assert f == [["Acme Notes API", "acme", "a1", ep, "active", 1000, OPEN, 1.0, "database"]]


def test_supersede_chain_and_as_of(eng, client, graph, proj):
    r1 = eng.assert_fact("Acme Notes API", "database", "MySQL", proj, "a1", now=1000)
    r2 = eng.assert_fact("Acme Notes API", "database", "PostgreSQL", proj, "a1", now=2000)
    r3 = eng.assert_fact("Acme Notes API", "database", "SQLite", proj, "a1", now=3000)
    assert r2["superseded"] == [r1["fact_id"]] and r3["superseded"] == [r2["fact_id"]]
    assert r2["fact_id"] not in (r1["fact_id"], r3["fact_id"])
    # exactly one active, windows are contiguous, SUPERSEDES edges form the chain v3->v2->v1
    hist = eng.fact_history("Acme Notes API", "database", proj)
    assert [(h["value"], h["status"], h["valid_from"], h["valid_to"]) for h in hist] == [
        ("MySQL", "superseded", 1000, 2000),
        ("PostgreSQL", "superseded", 2000, 3000),
        ("SQLite", "active", 3000, OPEN),
    ]
    assert sorted(_edges(client, graph, "SUPERSEDES")) == sorted(
        [[r2["fact_id"], r1["fact_id"]], [r3["fact_id"], r2["fact_id"]]]
    )
    # as_of at three timestamps returns the version valid then (and only that one)
    for t, want in [(1500, "MySQL"), (2500, "PostgreSQL"), (3500, "SQLite")]:
        got = eng.recall("Acme Notes API database", proj, k=5, as_of=t)
        assert [g["value"] for g in got] == [want], (t, got)
    # boundaries: valid_from inclusive, valid_to exclusive
    assert [g["value"] for g in eng.recall("database", proj, k=5, as_of=2000)] == ["PostgreSQL"]
    assert [g["value"] for g in eng.recall("database", proj, k=5, as_of=999)] == []
    # default recall = now: only the active version
    assert [g["value"] for g in eng.recall("database", proj, k=5)] == ["SQLite"]


def test_duplicate_same_value_other_agent_adds_asserted_by(eng, client, graph, proj):
    r1 = eng.assert_fact("Acme Notes API", "language", "Python 3.12", proj, "a1", now=1000)
    r2 = eng.assert_fact("acme notes api", "Language", "  python   3.12 ", proj, "a2", now=2000)
    assert r2["duplicate_of"] == r1["fact_id"] and r2["fact_id"] == r1["fact_id"]
    assert r2["superseded"] == [] and r2["contradicts"] == []
    assert len(_facts(client, graph)) == 1
    agents = sorted(b for a, b in _edges(client, graph, "ASSERTED_BY"))
    assert agents == ["a1", "a2"]
    # same agent repeating itself does not add a second edge
    eng.assert_fact("Acme Notes API", "language", "Python 3.12", proj, "a2", now=3000)
    assert len(_edges(client, graph, "ASSERTED_BY")) == 2
    assert _facts(client, graph)[0][2:] == ["active", 1000, OPEN]


def test_contradiction_other_agent_keeps_both_active(eng, client, graph, proj):
    r1 = eng.assert_fact("Acme Notes API", "database", "PostgreSQL", proj, "a1", now=1000)
    r2 = eng.assert_fact("Acme Notes API", "database", "MySQL", proj, "a2", now=2000)
    assert r2["contradicts"] == [r1["fact_id"]] and r2["superseded"] == []
    assert [f[2] for f in _facts(client, graph)] == ["active", "active"]
    assert _edges(client, graph, "CONTRADICTS") == [[r2["fact_id"], r1["fact_id"]]]
    # both are recalled now
    got = {g["value"] for g in eng.recall("database", proj, k=5)}
    assert got == {"PostgreSQL", "MySQL"}
    # a1 changing its own mind supersedes only its own fact; a2's stays and is contradicted
    r3 = eng.assert_fact("Acme Notes API", "database", "Oracle", proj, "a1", now=3000)
    assert r3["superseded"] == [r1["fact_id"]] and r3["contradicts"] == [r2["fact_id"]]


def test_supersede_flag_overrides_other_agents(eng, client, graph, proj):
    r1 = eng.assert_fact("Acme Notes API", "database", "PostgreSQL", proj, "a1", now=1000)
    r2 = eng.assert_fact("Acme Notes API", "database", "MySQL", proj, "a2", now=2000, supersede=True)
    assert r2["superseded"] == [r1["fact_id"]] and r2["contradicts"] == []
    assert [f[2] for f in _facts(client, graph)] == ["superseded", "active"]


def test_different_scope_and_predicate_do_not_interact(eng, client, graph, glob, proj):
    eng.assert_fact("Acme Notes API", "database", "PostgreSQL", proj, "a1", now=1000)
    r = eng.assert_fact("Acme Notes API", "database", "MySQL", glob, "a2", now=2000)
    assert r["contradicts"] == [] and r["superseded"] == []
    r = eng.assert_fact("Acme Notes API", "cache", "Redis", proj, "a2", now=2000)
    assert r["contradicts"] == [] and r["superseded"] == []
    assert len(_facts(client, graph)) == 3


def test_confidence_and_source(eng, client, graph, proj):
    client.graph(graph).query("CREATE (:Source {id:'src1', uri:'doc://x', kind:'doc', trust:1.0})")
    r = eng.assert_fact("Acme", "owner", "Alice", proj, "a1", source_id="src1", confidence=0.6, now=5)
    rows = (
        client.graph(graph)
        .ro_query(
            "MATCH (f:Fact {id:$id})-[:DERIVED_FROM]->(s:Source) RETURN s.id, f.confidence",
            {"id": r["fact_id"]},
        )
        .result_set
    )
    assert rows == [["src1", 0.6]]
    # a missing source/episode id is an error (P1-10) and writes nothing
    with pytest.raises(LookupError):
        eng.assert_fact("Acme", "owner", "Bob", proj, "a1", source_id="nope", episode_id="nope", now=6)
    assert [f[1] for f in _facts(client, graph)] == ["Alice"]


def test_unknown_scope_raises_and_writes_no_fact(eng, client, graph):
    with pytest.raises(LookupError):
        eng.assert_fact("Acme", "owner", "Alice", "no-such-scope", "a1")
    assert _facts(client, graph) == []
