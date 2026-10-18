"""P5-fix Q3 (source-anchored DERIVED_FROM cascade keeps its semantics) and Q11 (bounded cascade reports)."""

from __future__ import annotations

import pytest

from .conftest import cypher


def _chain(lin, eng, n, scope=None):
    glob = scope or eng.create_scope("global", "global")
    src = lin.create_source("https://x.example/deep")
    ids = [eng.assert_fact("Deep", f"p{i}", f"v{i}", glob, "a1", now=100 + i)["fact_id"] for i in range(n)]
    lin.derive_from(ids[0], [src])
    for prev, cur in zip(ids, ids[1:], strict=False):
        lin.derive_from(cur, [prev])
    return src, ids


def _status(client, graph, fid):
    return cypher(client, graph, "MATCH (f:Fact {id:$i}) RETURN f.status", i=fid)[0][0]


def test_q3_quarantine_depth_parameter_and_release_restores_the_same_set(lin, eng, client, graph):
    src, ids = _chain(lin, eng, 7)
    res = lin.quarantine(src, now=999, depth=5)
    assert res["fact_ids"] == sorted(ids[:5])
    assert _status(client, graph, ids[5]) == "active"
    assert lin.release_quarantine(src, depth=5)["fact_ids"] == sorted(ids[:5])
    assert {_status(client, graph, i) for i in ids} == {"active"}


def test_q3_a_fact_reached_by_two_paths_is_reported_once(lin, eng, client, graph):
    glob = eng.create_scope("global", "global")
    src = lin.create_source("https://x.example/diamond")
    a, b, c = (eng.assert_fact("D", f"p{i}", f"v{i}", glob, "a1", now=100 + i)["fact_id"] for i in range(3))
    lin.derive_from(a, [src])
    lin.derive_from(b, [src])
    lin.derive_from(c, [a, b, src])  # c reaches the source directly and through a and through b
    res = lin.forget_source(src, now=999)
    assert res["fact_ids"] == sorted([a, b, c])


def test_q3_forget_walks_through_an_already_forgotten_fact(lin, eng, client, graph):
    src, ids = _chain(lin, eng, 3)
    client.graph(graph).query("MATCH (f:Fact {id:$i}) SET f.status = 'forgotten'", {"i": ids[1]})
    res = lin.forget_source(src, now=999)
    assert res["fact_ids"] == sorted(
        [ids[0], ids[2]]
    )  # ids[1] is skipped but still links ids[2] to the source


def test_q3_quarantined_facts_are_forgotten_and_forgotten_are_not_quarantined(lin, eng, client, graph):
    src, ids = _chain(lin, eng, 3)
    lin.quarantine(src, now=999)
    assert lin.quarantine(src, now=1000)["fact_ids"] == []
    assert lin.forget_source(src, now=1001)["fact_ids"] == sorted(ids)
    assert lin.quarantine(src, now=1002)["fact_ids"] == []


# -- Q11: the report is bounded ------------------------------------------------------------------------


def test_q11_quarantine_caps_readers_decisions_and_handoffs_but_not_the_agent_list(world, lin, relay):
    w = world
    full = lin.quarantine(w.good, now=20_000)
    lin.release_quarantine(w.good)
    d2 = relay.record_decision("planner", "t-build", "second decision on the db", [w.db1], now=4100)
    h1 = relay.handoff("planner", "builder", "t-build", "pass on", fact_ids=[w.db1], now=4200)
    h2 = relay.handoff("planner", "researcher", "t-build", "pass on again", fact_ids=[w.db2], now=4300)
    full = lin.quarantine(w.good, now=20_001)
    lin.release_quarantine(w.good)
    assert len(full["readers"]) >= 3 and len(full["decision_ids"]) == 2 and len(full["handoff_ids"]) == 2
    assert {w.decision, d2} == set(full["decision_ids"]) and {h1, h2} == set(full["handoff_ids"])

    capped = lin.quarantine(w.good, now=20_002, max_detail=1)
    assert (
        len(capped["readers"]) == 1 and len(capped["decision_ids"]) == 1 and len(capped["handoff_ids"]) == 1
    )
    assert capped["readers_total"] == len(full["readers"])
    assert capped["decisions_total"] == 2 and capped["handoffs_total"] == 2
    assert capped["detail_truncated"] is True
    assert capped["agents"] == full["agents"] == ["builder", "planner", "researcher"]  # never cut
    assert capped["fact_ids"] == full["fact_ids"]  # the write is not affected by the display cap


def test_q11_report_is_complete_under_the_default_cap(world, lin):
    res = lin.quarantine(world.bad, now=20_000)
    assert res["detail_truncated"] is False
    assert res["readers_total"] == len(res["readers"]) == 2
    assert res["decisions_total"] == 1 and res["handoffs_total"] == 0


def test_q11_forget_source_caps_the_reported_decisions(world, lin, relay, client, graph):
    w = world
    relay.record_decision("planner", "t-build", "another on the cache", [w.cache], now=4100)
    capped = lin.forget_source(w.bad, now=20_000, max_detail=1)
    assert len(capped["decision_ids"]) == 1 and capped["decisions_total"] == 2
    assert capped["detail_truncated"] is True
    flagged = cypher(client, graph, "MATCH (d:Decision {flagged: true}) RETURN count(d)")
    assert flagged == [[2]]  # every decision is still flagged; only the report is cut


@pytest.mark.parametrize("bad", [0, -1, 5001])
def test_q11_max_detail_is_validated(world, lin, bad):
    with pytest.raises(ValueError, match="max_detail"):
        lin.quarantine(world.bad, max_detail=bad)
    with pytest.raises(ValueError, match="max_detail"):
        lin.forget_source(world.bad, max_detail=bad)
