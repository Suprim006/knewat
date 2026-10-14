from __future__ import annotations

import pytest

from plexus.lineage import UnknownNode

from .conftest import cypher


def _status(client, graph, fid):
    return cypher(client, graph, "MATCH (f:Fact {id:$i}) RETURN f.status, f.valid_to", i=fid)[0]


def test_forget_source_cascades_over_derived_chain(world, lin, client, graph, clock):
    w = world
    clock.t = 20_000
    res = lin.forget_source(w.bad)
    assert res["mode"] == "forget" and res["truncated"] is False
    # the cache fact comes straight from the source, the session-store fact through DERIVED_FROM -> cache fact
    assert res["fact_ids"] == sorted([w.cache, w.sessstore])
    assert res["decision_ids"] == [w.decision] and res["handoff_ids"] == []
    for fid in (w.cache, w.sessstore):
        assert _status(client, graph, fid) == ["forgotten", 20_000]


def test_forget_source_leaves_unrelated_facts_untouched(world, lin, client, graph):
    w = world
    lin.forget_source(w.bad, now=20_000)
    assert _status(client, graph, w.db1) == ["superseded", 6000]
    assert _status(client, graph, w.db2)[0] == "active"
    assert _status(client, graph, w.other)[0] == "active"


def test_forget_source_removes_facts_from_engram_recall_but_keeps_the_rest(world, lin, eng):
    w = world
    before = {r["fact_id"] for r in eng.recall("what does Acme use", w.proj, k=8)}
    assert {w.cache, w.sessstore, w.db2, w.other} <= before
    lin.forget_source(w.bad, now=20_000)
    after = {r["fact_id"] for r in eng.recall("what does Acme use", w.proj, k=8)}
    assert after == before - {w.cache, w.sessstore}
    assert eng.recall("cache", w.proj, k=8, as_of=3000)  # as_of recall still works for other facts...
    assert w.cache not in {r["fact_id"] for r in eng.recall("cache", w.proj, k=8, as_of=3000)}
    assert (
        lin.as_of("Acme Notes API", "cache", 3000, w.proj) is None
    )  # ...and time travel cannot resurrect it


def test_forget_source_flags_decisions_but_does_not_delete(world, lin, client, graph):
    w = world
    lin.forget_source(w.bad, now=20_000)
    rows = cypher(
        client, graph, "MATCH (d:Decision {id:$d}) RETURN d.text, d.flagged, d.flag_reason", d=w.decision
    )
    assert rows == [["use postgres and redis", True, f"derived from forgotten source {w.bad}"]]
    assert cypher(
        client, graph, "MATCH (:Decision {id:$d})-[r:BASED_ON]->() RETURN count(r)", d=w.decision
    ) == [[2]]
    shown = lin.why(w.decision)
    assert next(n for n in shown["nodes"] if n["id"] == w.decision)["props"]["flagged"] is True
    cache = next(f for f in shown["facts"] if f["id"] == w.cache)
    assert cache["props"]["status"] == "forgotten"  # the explanation survives, marked forgotten


def test_forget_source_is_idempotent(world, lin):
    w = world
    first = lin.forget_source(w.bad, now=20_000)
    again = lin.forget_source(w.bad, now=30_000)
    assert first["fact_ids"] and again["fact_ids"] == [] and again["decision_ids"] == []


def test_forget_source_min_valid_to_keeps_superseded_window(world, lin, client, graph):
    w = world
    res = lin.forget_source(w.good, now=20_000)
    assert res["fact_ids"] == sorted([w.db1, w.db2])
    assert _status(client, graph, w.db1) == ["forgotten", 6000]  # already closed earlier: min() keeps 6000
    assert _status(client, graph, w.db2) == ["forgotten", 20_000]
    assert res["decision_ids"] == [w.decision]  # the decision rested on db1


def test_forget_source_reports_handoffs_that_carry_forgotten_facts(world, lin, relay):
    w = world
    hid = relay.handoff("planner", "builder", "t-build", "use the cache", fact_ids=[w.cache], now=4500)
    res = lin.forget_source(w.bad, now=20_000)
    assert res["handoff_ids"] == [hid]


def test_forget_source_unknown_and_bad_args(world, lin):
    with pytest.raises(UnknownNode):
        lin.forget_source("no-source")
    with pytest.raises(ValueError):
        lin.forget_source(world.bad, mode="shred")
    with pytest.raises(ValueError):
        lin.forget_source(world.bad, limit=5001)
    with pytest.raises(ValueError):
        lin.forget_source(world.bad, limit=0)


def test_forget_source_depth_limit_is_five_hops(lin, eng, client, graph):
    glob = eng.create_scope("global", "global")
    src = lin.create_source("https://x.example/deep")
    ids = []
    for i in range(7):
        ids.append(eng.assert_fact("Deep", f"p{i}", f"v{i}", glob, "a1", now=100 + i)["fact_id"])
    lin.derive_from(ids[0], [src])
    for prev, cur in zip(ids, ids[1:], strict=False):
        lin.derive_from(cur, [prev])
    res = lin.forget_source(src, now=999)
    assert res["fact_ids"] == sorted(ids[:5])  # 1..5 hops reach ids[0]..ids[4]; ids[5], ids[6] are deeper
    assert _status(client, graph, ids[5])[0] == "active"


def test_forget_source_is_bounded_by_limit(lin, eng, client, graph):
    glob = eng.create_scope("global", "global")
    src = lin.create_source("https://x.example/many")
    ids = [eng.assert_fact("Many", f"p{i}", f"v{i}", glob, "a1", now=100 + i)["fact_id"] for i in range(12)]
    for fid in ids:
        lin.derive_from(fid, [src])
    first = lin.forget_source(src, now=999, limit=5)
    assert len(first["fact_ids"]) == 5 and first["truncated"] is True
    n = cypher(client, graph, "MATCH (f:Fact {status:'forgotten'}) RETURN count(f)")
    assert n == [[5]]  # the bound limits the write itself
    second = lin.forget_source(src, now=999, limit=5)
    third = lin.forget_source(src, now=999, limit=5)
    assert len(second["fact_ids"]) == 5 and len(third["fact_ids"]) == 2 and third["truncated"] is False
    assert sorted(first["fact_ids"] + second["fact_ids"] + third["fact_ids"]) == sorted(ids)


def test_forget_source_does_not_touch_other_sources(world, lin, client, graph):
    w = world
    lin.forget_source(w.good, now=20_000)
    assert cypher(client, graph, "MATCH (s:Source) RETURN count(s)") == [[2]]
    assert _status(client, graph, w.cache)[0] == "active"
