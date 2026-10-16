"""P9-b / P4: ``Lineage.impact``, the read-only blast radius, agrees with what quarantine would change."""

from __future__ import annotations

import pytest

from plexus.lineage import Lineage, UnknownNode

from .conftest import cypher
from .diamond import TimedClient, build_lineage


def _snapshot(client, graph):
    return cypher(client, graph, "MATCH (n) RETURN labels(n)[0], n.id, n.status, n.flagged ORDER BY n.id")


def test_impact_source_matches_the_quarantine_blast_radius_and_writes_nothing(world, lin, client, graph):
    w = world
    before = _snapshot(client, graph)
    got = lin.impact("source", w.bad)
    assert _snapshot(client, graph) == before  # read-only
    assert got["kind"] == "source" and got["id"] == w.bad
    q = lin.quarantine(w.bad, now=9999)
    assert got["facts"]["ids"] == q["fact_ids"] and got["facts"]["total"] == len(q["fact_ids"]) == 2
    assert got["facts"]["by_status"] == {"active": 2}
    assert got["readers"]["agents"] == q["agents"]
    assert got["readers"]["steps_total"] == len({x["step_id"] for x in q["readers"]})
    assert got["decisions"] == {"total": 1, "ids": [w.decision]}
    assert got["tasks"] == {"total": 1, "ids": ["t-build"]}
    assert got["handoffs"] == {"total": q["handoffs_total"], "ids": q["handoff_ids"]}
    assert got["truncated"] is False


def test_impact_fact_includes_the_fact_and_its_descendants(world, lin):
    w = world
    got = lin.impact("fact", w.cache)
    assert got["facts"]["ids"] == sorted([w.cache, w.sessstore])
    assert got["decisions"]["ids"] == [w.decision]
    leaf = lin.impact("fact", w.sessstore)
    assert leaf["facts"]["ids"] == [w.sessstore] and leaf["decisions"]["total"] == 0


def test_impact_counts_every_status_and_caps_the_lists(world, lin):
    w = world
    lin.quarantine(w.bad, now=9999)
    got = lin.impact("source", w.bad, max_detail=1)
    assert got["facts"]["by_status"] == {"quarantined": 2}
    assert got["facts"]["total"] == 2 and len(got["facts"]["ids"]) == 1


def test_impact_unknown_and_bad_arguments(lin):
    with pytest.raises(UnknownNode):
        lin.impact("source", "nope")
    with pytest.raises(UnknownNode):
        lin.impact("fact", "nope")
    with pytest.raises(ValueError):
        lin.impact("decision", "x")
    with pytest.raises(ValueError):
        lin.impact("source", "x", depth=13)


def test_impact_depth_12_on_a_diamond_lineage_is_fast(client, graph, clock):
    d = build_lineage(client, graph, levels=12, width=5, fan_in=3)
    tc = TimedClient(client)
    lin = Lineage(tc, graph, clock=clock)
    got = lin.impact("source", d["source"], depth=12)
    assert got["facts"]["total"] == 60 and got["decisions"]["ids"] == [d["decision"]]
    assert tc.server_ms < 200, tc.server_ms
    assert lin.impact("source", d["source"])["facts"]["total"] == 40  # default depth 8
    up = lin.impact(
        "fact", d["layers"][0][0], depth=12
    )  # f1-0 itself, 3 facts on level 2, all 5 on levels 3..12
    assert up["facts"]["total"] == 1 + 3 + 5 * 10 and d["top"] in up["facts"]["ids"]


def test_plan_shape_impact_touches_edges_not_paths(client, graph):
    from tests.plan_util import max_records, profile_ops

    d = build_lineage(client, graph, levels=12, width=5, fan_in=3)
    total_edges = 5 + 11 * 5 * 3
    for kind, ident in (("source", d["source"]), ("fact", d["layers"][0][0])):
        params = {"id": ident, "depth": 12, "limit": 5000, "limit_plus": 5001}
        ops = profile_ops(client, graph, f"lineage/impact_{kind}", params)
        assert max_records(ops).records <= total_edges, (kind, max_records(ops))
