"""P9-b / P1: lineage traversals are level-wise over distinct nodes: a diamond lineage is cheap and deep.

Fixture: depth 12, fan-in 3 (about 3**12 = 531k DERIVED_FROM paths, 60 distinct facts).
"""

from __future__ import annotations

import pytest

from plexus.lineage import Lineage
from tests.plan_util import max_records, profile_ops

from .conftest import cypher
from .diamond import TimedClient, build_lineage

LEVELS, WIDTH = 12, 5
SERVER_BUDGET_MS = 200


@pytest.fixture
def diamond(client, graph):
    return build_lineage(client, graph, levels=LEVELS, width=WIDTH, fan_in=3)


@pytest.fixture
def timed(client, graph, clock):
    tc = TimedClient(client)
    return tc, Lineage(tc, graph, clock=clock)


def _all(diamond) -> list[str]:
    return sorted(f for layer in diamond["layers"] for f in layer)


def test_forget_source_reaches_depth_12_on_a_diamond_lineage_fast(diamond, timed):
    tc, lin = timed
    res = lin.forget_source(diamond["source"], now=999, depth=12)
    assert res["fact_ids"] == _all(diamond)  # all 60, each once
    assert res["decision_ids"] == [diamond["decision"]]
    assert tc.server_ms < SERVER_BUDGET_MS, tc.server_ms


def test_forget_source_default_depth_is_eight(diamond, lin, client, graph):
    res = lin.forget_source(diamond["source"], now=999)
    assert res["fact_ids"] == sorted(f for layer in diamond["layers"][:8] for f in layer)
    assert res["decision_ids"] == []  # the decision rests on the level-12 fact, beyond depth 8


def test_forget_source_depth_one_and_validation(diamond, lin):
    assert lin.forget_source(diamond["source"], now=1, depth=1)["fact_ids"] == sorted(diamond["layers"][0])
    for bad in (0, 13, -1):
        with pytest.raises(ValueError):
            lin.forget_source(diamond["source"], now=1, depth=bad)


def test_quarantine_and_release_round_trip_at_depth_12(diamond, timed, client, graph):
    tc, lin = timed
    res = lin.quarantine(diamond["source"], now=999, depth=12)
    assert res["fact_ids"] == _all(diamond)
    assert res["decision_ids"] == [diamond["decision"]]
    assert tc.server_ms < SERVER_BUDGET_MS, tc.server_ms
    back = lin.release_quarantine(diamond["source"], depth=12)
    assert back["fact_ids"] == _all(diamond)
    statuses = cypher(client, graph, "MATCH (f:Fact) RETURN DISTINCT f.status")
    assert statuses == [["active"]]


def test_a_fact_reachable_at_two_depths_is_reported_once_and_expanded_from_its_shortest_use(
    lin, eng, client, graph
):
    glob = eng.create_scope("global", "global")
    src = lin.create_source("https://x.example/uneven")
    ids = [eng.assert_fact("U", f"p{i}", f"v{i}", glob, "a1", now=100 + i)["fact_id"] for i in range(4)]
    a, b, c, d = ids
    lin.derive_from(a, [src])
    lin.derive_from(b, [a])
    lin.derive_from(c, [b, src])  # c is at depth 1 (via src) and depth 3 (via a, b)
    lin.derive_from(d, [c])
    assert lin.forget_source(src, now=999, depth=4)["fact_ids"] == sorted(ids)


def test_why_follows_derived_from_to_the_source_at_depth_12(diamond, timed):
    tc, lin = timed
    res = lin.why(diamond["decision"], max_elements=2000, depth=12)
    assert diamond["source"] in res["sources"]
    derived = {(e["from"], e["to"]) for e in res["edges"] if e["rel"] == "DERIVED_FROM"}
    # from the decision top fact: level 12 -> 3 edges, 11 -> 9, levels 10..2 -> 15 each, 1 -> 5 to the source
    assert len(derived) == 3 + 9 + 15 * 9 + 5
    assert res["truncated"] is False
    assert tc.server_ms < SERVER_BUDGET_MS, tc.server_ms


def test_why_depth_default_six_and_bounds(diamond, lin):
    res = lin.why(diamond["decision"], max_elements=2000)
    assert diamond["source"] not in res["sources"]  # the source is 12 hops below the decision's fact
    deep = [e for e in res["edges"] if e["rel"] == "DERIVED_FROM"]
    assert len(deep) == 3 + 9 + 15 * 4  # depth 6: levels 12, 11, then 10..7
    for bad in (0, 13):
        with pytest.raises(ValueError):
            lin.why(diamond["decision"], depth=bad)


def test_plan_shape_cascade_touches_edges_not_paths(diamond, client, graph):
    total_edges = WIDTH + (LEVELS - 1) * WIDTH * 3
    params = {"source_id": diamond["source"], "now": 1, "limit": 5000, "max_detail": 500, "depth": 12}
    for name, extra in (("lineage/quarantine", {}), ("lineage/forget_source", {"reason": "r"})):
        ops = profile_ops(client, graph, name, {**params, **extra})
        top = max_records(ops)
        assert top.records <= total_edges, f"{name}: {top}"
        client.graph(graph).query("MATCH (f:Fact) SET f.status = 'active', f.valid_to = 9999999999999")
