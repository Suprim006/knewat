"""P5-fix Engram: Q2 (fact_history limit, entity-anchored lookups), Q8 (no orphan Entity)."""

from __future__ import annotations

import pytest

from plexus.engram import UnknownReference


def _count(client, graph, label):
    return client.graph(graph).ro_query(f"MATCH (n:{label}) RETURN count(n)").result_set[0][0]


def test_q2_fact_history_is_bounded_and_keeps_the_newest_versions_oldest_first(eng, proj):
    ids = [
        eng.assert_fact("Acme", "build", f"build number {i}x", proj, "a1", now=1000 + i)["fact_id"]
        for i in range(6)
    ]
    assert len(eng.fact_history("Acme", "build", proj)) == 6
    last3 = eng.fact_history("Acme", "build", proj, limit=3)
    assert [h["fact_id"] for h in last3] == ids[3:]  # newest three, still oldest first
    assert [h["status"] for h in last3] == ["superseded", "superseded", "active"]
    assert eng.fact_history("Acme", "build", proj, limit=1)[0]["fact_id"] == ids[-1]


def test_q2_fact_history_rejects_a_bad_limit(eng, proj):
    for bad in (0, -1, 10_001):
        with pytest.raises(ValueError, match="limit"):
            eng.fact_history("Acme", "build", proj, limit=bad)


def test_q2_current_fact_lookup_still_classifies_per_entity_predicate_and_scope(eng, proj, glob):
    a = eng.assert_fact("Acme", "db", "PostgreSQL", proj, "a1", now=1000)
    other_scope = eng.assert_fact("Acme", "db", "MySQL", glob, "a2", now=1100)
    other_pred = eng.assert_fact("Acme", "cache", "Redis", proj, "a2", now=1200)
    other_entity = eng.assert_fact("Beta", "db", "SQLite", proj, "a2", now=1300)
    for r in (other_scope, other_pred, other_entity):
        assert r["superseded"] == [] and r["contradicts"] == [] and r["duplicate_of"] is None
    again = eng.assert_fact("Acme", "db", "PostgreSQL", proj, "a3", now=2000)
    assert again["duplicate_of"] == a["fact_id"]
    upd = eng.assert_fact("Acme", "db", "Oracle", proj, "a1", now=3000)
    # a3 endorsed the fact, so it is no longer a1's alone: a1's change is a contradiction, not an update
    assert upd["superseded"] == [] and upd["contradicts"] == [a["fact_id"]]


# -- Q8: a rejected assert_fact leaves nothing behind (not even the subject Entity) --------------------


def test_q8_assert_fact_with_unknown_scope_creates_no_entity(eng, client, graph, proj):
    before = _count(client, graph, "Entity")
    with pytest.raises(UnknownReference):
        eng.assert_fact("OrphanSubject", "color", "red", "no-such-scope", "a1", now=1000)
    assert _count(client, graph, "Entity") == before
    assert _count(client, graph, "Agent") == 0


@pytest.mark.parametrize("kw", [{"episode_id": "no-such-episode"}, {"source_id": "no-such-source"}])
def test_q8_assert_fact_with_unknown_episode_or_source_creates_no_entity(eng, client, graph, proj, kw):
    with pytest.raises(UnknownReference):
        eng.assert_fact("OrphanSubject", "color", "red", proj, "a1", now=1000, **kw)
    assert _count(client, graph, "Entity") == 0


def test_q8_known_references_still_create_the_entity(eng, client, graph, proj):
    eng.assert_fact("NewSubject", "color", "red", proj, "a1", now=1000)
    assert _count(client, graph, "Entity") == 1
