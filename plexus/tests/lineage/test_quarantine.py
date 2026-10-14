from __future__ import annotations

import pytest

from plexus.engram import OPEN
from plexus.lineage import UnknownNode

from .conftest import cypher


def _fact(client, graph, fid):
    q = "MATCH (f:Fact {id:$i}) RETURN f.status, f.valid_to, f.prior_status"
    return cypher(client, graph, q, i=fid)[0]


def test_quarantine_reports_blast_radius(world, lin, relay):
    w = world
    hid = relay.handoff(
        "planner", "builder", "t-build", "pass the cache facts on", fact_ids=[w.cache], now=4500
    )
    res = lin.quarantine(w.bad, now=20_000)
    assert res["mode"] == "quarantine" and res["truncated"] is False
    assert res["fact_ids"] == sorted([w.cache, w.sessstore])
    assert res["decision_ids"] == [w.decision]
    assert res["handoff_ids"] == [hid]
    # planner's step 1 recalled every active fact, so it READ both quarantined facts; nobody else did
    assert res["agents"] == ["planner"]
    assert [(r["agent_id"], r["step_n"], r["at"], r["fact_id"]) for r in res["readers"]] == sorted(
        [("planner", 1, 3000, w.cache), ("planner", 1, 3000, w.sessstore)], key=lambda x: x[3]
    )


def test_quarantine_hides_facts_reversibly_and_changes_nothing_else(world, lin, eng, client, graph):
    w = world
    lin.quarantine(w.bad, now=20_000)
    for fid in (w.cache, w.sessstore):
        assert _fact(client, graph, fid) == [
            "quarantined",
            OPEN,
            "active",
        ]  # window untouched, old status kept
    assert _fact(client, graph, w.db2)[0] == "active" and _fact(client, graph, w.other)[0] == "active"
    recalled = {r["fact_id"] for r in eng.recall("what does Acme use", w.proj, k=8)}
    assert w.cache not in recalled and w.sessstore not in recalled and w.db2 in recalled
    assert lin.as_of("Acme Notes API", "cache", 5000, w.proj) is None
    flagged = cypher(client, graph, "MATCH (d:Decision {id:$d}) RETURN d.flagged", d=w.decision)
    assert flagged == [[None]]  # quarantine reports decisions, it does not modify them


def test_quarantine_is_idempotent_and_release_restores(world, lin, eng, client, graph):
    w = world
    lin.quarantine(w.bad, now=20_000)
    assert lin.quarantine(w.bad, now=30_000)["fact_ids"] == []
    res = lin.release_quarantine(w.bad)
    assert res["fact_ids"] == sorted([w.cache, w.sessstore])
    assert _fact(client, graph, w.cache) == ["active", OPEN, None]
    assert w.cache in {r["fact_id"] for r in eng.recall("what does Acme use", w.proj, k=8)}
    assert lin.release_quarantine(w.bad)["fact_ids"] == []


def test_quarantine_keeps_superseded_status_for_release(world, lin, client, graph):
    w = world
    res = lin.quarantine(w.good, now=20_000)
    assert res["fact_ids"] == sorted([w.db1, w.db2])
    assert _fact(client, graph, w.db1) == ["quarantined", 6000, "superseded"]
    lin.release_quarantine(w.good)
    assert _fact(client, graph, w.db1) == ["superseded", 6000, None]
    assert _fact(client, graph, w.db2)[0] == "active"
    # blast radius of the good source: planner, builder and researcher all read a version of the database fact
    again = lin.quarantine(w.good, now=21_000)
    assert again["agents"] == ["builder", "planner", "researcher"]


def test_forget_after_quarantine_wins_and_release_does_not_resurrect(world, lin, client, graph):
    w = world
    lin.quarantine(w.bad, now=20_000)
    forgotten = lin.forget_source(w.bad, now=25_000)
    assert forgotten["fact_ids"] == sorted([w.cache, w.sessstore])
    assert lin.release_quarantine(w.bad)["fact_ids"] == []
    assert _fact(client, graph, w.cache)[0] == "forgotten"


def test_forget_source_mode_quarantine_dispatches(world, lin):
    w = world
    res = lin.forget_source(w.bad, mode="quarantine", now=20_000)
    assert res["mode"] == "quarantine" and res["agents"] == ["planner"]


def test_quarantine_unknown_source_and_bounds(world, lin, eng):
    with pytest.raises(UnknownNode):
        lin.quarantine("nope")
    with pytest.raises(UnknownNode):
        lin.release_quarantine("nope")
    with pytest.raises(ValueError):
        lin.quarantine(world.bad, limit=5001)


def test_quarantine_is_bounded_by_limit(lin, eng, client, graph):
    glob = eng.create_scope("global", "global")
    src = lin.create_source("https://x.example/poison")
    for i in range(9):
        fid = eng.assert_fact("Poison", f"p{i}", f"v{i}", glob, "a1", now=100 + i)["fact_id"]
        lin.derive_from(fid, [src])
    first = lin.quarantine(src, now=999, limit=4)
    assert len(first["fact_ids"]) == 4 and first["truncated"] is True
    assert cypher(client, graph, "MATCH (f:Fact {status:'quarantined'}) RETURN count(f)") == [[4]]
    rest = lin.quarantine(src, now=999, limit=10)
    assert len(rest["fact_ids"]) == 5 and rest["truncated"] is False
