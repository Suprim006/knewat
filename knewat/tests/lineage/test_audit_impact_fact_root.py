"""Audit C4: ``lineage/impact_fact`` must keep the root fact when `limit` cuts the result.

Before: the generator appended the root LAST (``reach + [src]``), so ``limit=1`` returned only a descendant
(``['F3']``) while ``Lineage.impact`` documents that the fact itself is part of ``facts``.
"""

from __future__ import annotations

from knewat.lineage import Lineage

from .conftest import cypher


def _seed(client, graph):
    client.graph(graph).query(
        """CREATE (f1:Fact {id: 'F1', status: 'active', valid_from: 1}),
                  (f2:Fact {id: 'F2', status: 'active', valid_from: 2}),
                  (f3:Fact {id: 'F3', status: 'active', valid_from: 3})
           CREATE (f2)-[:DERIVED_FROM]->(f1), (f3)-[:DERIVED_FROM]->(f1)"""
    )


def test_impact_fact_query_keeps_the_root_when_truncated(client, graph):
    _seed(client, graph)
    cut = client.ro(graph, "lineage/impact_fact", {"id": "F1", "depth": 8, "limit": 1})[0]
    assert cut["fact_ids"] == ["F1"] and cut["truncated"] is True
    full = client.ro(graph, "lineage/impact_fact", {"id": "F1", "depth": 8, "limit": 10})[0]
    assert sorted(full["fact_ids"]) == ["F1", "F2", "F3"] and full["truncated"] is False
    assert full["fact_ids"][0] == "F1"  # root first


def test_lineage_impact_fact_with_limit_one_reports_the_fact_itself(client, graph):
    _seed(client, graph)
    got = Lineage(client, graph).impact("fact", "F1", limit=1)
    assert got["facts"]["ids"] == ["F1"] and got["truncated"] is True
    assert cypher(client, graph, "MATCH (f:Fact) RETURN count(f)")[0][0] == 3
