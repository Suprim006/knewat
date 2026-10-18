"""FIX-P7 P7-07: plan-shape regression for ``staleness/facts_to_verify``.

``UNWIND $ids AS fid MATCH (f:Fact {id: fid})-[:ABOUT]->(e)`` was planned as a traverse from EVERY fact,
with the id test as a late filter (O(ids x facts)). The id must be an index seek first, then the traversal.
"""

from __future__ import annotations

import pytest
from tests.plan_util import BIG, explain_lines, max_records, profile_ops, seed_big_scope

from plexus.engram.service import OPEN


@pytest.fixture
def big(client, graph):
    return seed_big_scope(client, graph)


def params(ids, scope_id=""):
    return {"ids": ids, "scope_id": scope_id, "open_to": OPEN, "limit": 5000}


def test_facts_to_verify_seeks_the_fact_ids_in_the_index(client, graph, big):
    lines = explain_lines(client, graph, "staleness/facts_to_verify", params(["F0", "F1"]))
    seeks = [ln for ln in lines if ln.startswith("Node By Index Scan") and "Fact" in ln]
    assert seeks, "no index seek on Fact.id:\n" + "\n".join(lines)
    assert not any(ln.startswith("All Node Scan") for ln in lines), "\n".join(lines)


@pytest.mark.parametrize("scope_id", ["", "S"])
def test_facts_to_verify_work_follows_the_ids_not_the_graph(client, graph, big, scope_id):
    ids = ["F0", "F1", "F7"]
    ops = profile_ops(client, graph, "staleness/facts_to_verify", params(ids, scope_id))
    worst = max_records(ops)
    assert worst.records < BIG // 10, f"enumerates the graph: {worst}\n" + "\n".join(map(str, ops))
