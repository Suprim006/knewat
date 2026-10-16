"""P9-f: ``impact`` on a 5,000-fact blast (Crucible L6 family A's largest question) answers, exactly and fast.

Before P9-f the statement chained three ``UNWIND fs`` joins whose aggregations grouped by the 5,000-element
fact list, and the server cancelled it after 10 s (L6 results in docs/BASELINE.md).
"""

from __future__ import annotations

import time

import pytest

from plexus.lineage import Lineage

from .blast import build_blast


@pytest.fixture
def blast(client, graph):
    return build_blast(client, graph, n=5000, levels=12)


def test_impact_on_a_5000_fact_blast_is_exact_and_well_under_5_s(client, graph, blast):
    lin = Lineage(client, graph)
    t0 = time.perf_counter()
    r = lin.impact("source", blast["source"], depth=12, max_detail=5000)
    wall = time.perf_counter() - t0
    assert wall < 5.0, f"impact took {wall:.2f} s on 5,000 facts"
    assert r["facts"]["total"] == 5000 and r["truncated"] is False
    assert r["facts"]["ids"] == sorted(blast["facts"])
    assert r["readers"]["steps_total"] == blast["steps"]
    assert r["readers"]["agents"] == blast["agents"]
    assert r["decisions"] == {
        "total": len(blast["decisions"]),
        "ids": blast["decisions"],
        "ids_truncated": False,
    }
    assert r["handoffs"] == {
        "total": len(blast["handoffs"]),
        "ids": blast["handoffs"],
        "ids_truncated": False,
    }
    assert r["tasks"] == {"total": len(blast["tasks"]), "ids": blast["tasks"], "ids_truncated": False}
