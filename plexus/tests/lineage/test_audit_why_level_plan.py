"""Audit P2: lineage/why_derived_level must start at the frontier Facts, not at every DERIVED_FROM edge.

Before: ``UNWIND $frontier AS fid MATCH (f:Fact {id: fid})-[:DERIVED_FROM]->(x)`` in ONE MATCH is planned as
Unwind -> Conditional Traverse over EVERY DERIVED_FROM edge (then a filter): 5,004 records for a one-element
frontier, per level, per ``why``. After: ``MATCH (f0:Fact {id: fid}) WITH f0 MATCH (f0)-[:DERIVED_FROM]->(x)``
(Node By Index Scan, then a traversal from the bound node).
"""

from __future__ import annotations

from tests.plan_util import max_records, profile_ops

from .audit_util import old_client
from .conftest import cypher

NOISE = 5000  # unrelated Fact -> Fact DERIVED_FROM edges
NOISE_EP = 2000  # unrelated Fact -> Episode <- Session <- Agent chains (branches 3 and 4)


def _seed(client, graph):
    g = client.graph(graph)
    for label in ("Fact", "Episode", "Session", "Agent"):
        g.query(f"CREATE INDEX FOR (n:{label}) ON (n.id)")
    # the chain under test: A -> B (fact, asserted by ag1), A -> E (episode, in session S1, had by ag2)
    g.query(
        """CREATE (a:Fact {id: 'A'}), (b:Fact {id: 'B'}), (ag1:Agent {id: 'ag1'}), (ag2:Agent {id: 'ag2'}),
                  (e:Episode {id: 'E'}), (s:Session {id: 'S1'})
           CREATE (a)-[:DERIVED_FROM]->(b), (b)-[:ASSERTED_BY]->(ag1), (a)-[:DERIVED_FROM]->(e),
                  (s)-[:HAS_EPISODE]->(e), (ag2)-[:HAD]->(s)"""
    )
    for lo in range(0, NOISE, 1000):
        g.query(
            "UNWIND range($lo, $hi) AS i CREATE (:Fact {id: 'N' + toString(i)})-[:DERIVED_FROM]->"
            "(:Fact {id: 'M' + toString(i)})",
            {"lo": lo, "hi": lo + 999},
        )
    g.query(
        """UNWIND range(0, $n - 1) AS i
           CREATE (:Fact {id: 'NE' + toString(i)})-[:DERIVED_FROM]->(e:Episode {id: 'NEp' + toString(i)})
           CREATE (e)<-[:HAS_EPISODE]-(s:Session {id: 'NS' + toString(i)})
           CREATE (s)<-[:HAD]-(:Agent {id: 'NA' + toString(i)})""",
        {"n": NOISE_EP},
    )


def _rows(rows):
    return sorted((r["s"], r["sl"], r["rel"], r["t"], r["tl"], r["prio"]) for r in rows)


def test_why_derived_level_one_element_frontier_does_not_scan_all_derived_from_edges(client, empty_graph):
    _seed(client, empty_graph)
    ops = profile_ops(client, empty_graph, "lineage/why_derived_level", {"frontier": ["A"], "limit": 1000})
    worst = max_records(ops)
    assert worst.records < 20, "scan over all DERIVED_FROM edges: " + "\n".join(map(str, ops))


def test_why_derived_level_matches_baseline_rows(client, empty_graph):
    _seed(client, empty_graph)
    old = old_client(client)
    try:
        for frontier in (["A"], ["A", "B", "NOPE"], ["B"], [], ["NE7", "A"]):
            params = {"frontier": frontier, "limit": 1000}
            a = old.ro(empty_graph, "lineage/why_derived_level", params)
            b = client.ro(empty_graph, "lineage/why_derived_level", params)
            assert _rows(b) == _rows(a), frontier
    finally:
        old.close()
    rows = _rows(client.ro(empty_graph, "lineage/why_derived_level", {"frontier": ["A"], "limit": 1000}))
    assert rows == sorted(
        [
            ("A", "Fact", "DERIVED_FROM", "B", "Fact", 3),
            ("A", "Fact", "DERIVED_FROM", "E", "Episode", 3),
            ("B", "Fact", "ASSERTED_BY", "ag1", "Agent", 4),
            ("ag2", "Agent", "HAD", "S1", "Session", 4),
            ("S1", "Session", "HAS_EPISODE", "E", "Episode", 4),
        ]
    )


def test_why_derived_level_matches_baseline_on_the_world(world, client, graph):
    w = world
    old = old_client(client)
    try:
        ids = [r[0] for r in cypher(client, graph, "MATCH (f:Fact) RETURN f.id")]
        for frontier in (ids, [w.sessstore], [w.db1]):
            params = {"frontier": frontier, "limit": 1000}
            a = old.ro(graph, "lineage/why_derived_level", params)
            b = client.ro(graph, "lineage/why_derived_level", params)
            assert _rows(b) == _rows(a)
            assert any(r["rel"] == "DERIVED_FROM" for r in b)
    finally:
        old.close()
