"""Audit P2, carried over to the one-statement ``lineage/why_edges`` (P9-f, integ): the DERIVED_FROM ancestry must
start at the root's Facts, not at every DERIVED_FROM edge.

Before the audit: ``UNWIND $frontier AS fid MATCH (f:Fact {id: fid})-[:DERIVED_FROM]->(x)`` in ONE MATCH was planned as
Unwind -> Conditional Traverse over EVERY DERIVED_FROM edge (then a filter): 5,004 records for a one-element
frontier, per level, per ``why``; the audit bound the Fact first (``why_derived_level``). P9-f folded the level loop
into ``why_edges`` (12 unrolled one-hop steps over nodes already bound by the previous step), which keeps that shape:
the profile below pins it, and the rows are compared with the baseline's ``why_derived_level`` loop (edf9a91).
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
    return sorted((r["s"], r["sl"], r["rel"], r["t"], r["tl"]) for r in rows)


def _old_ancestry(old, graph, root_id, depth=12):
    """The ancestry rows the baseline's ``Lineage._derived_edges`` produced: one ``why_derived_level`` per hop."""
    base = {
        r["t"]
        for r in old.ro(graph, "lineage/why_edges", {"id": root_id, "limit": 1000})
        if r["rel"] == "BASED_ON"
    }
    frontier = sorted(base | {root_id})
    seen, out = set(frontier), []
    for _ in range(depth):
        level = old.ro(graph, "lineage/why_derived_level", {"frontier": frontier, "limit": 1000})
        out += [dict(r) for r in level]
        frontier = sorted({r["t"] for r in level if r["rel"] == "DERIVED_FROM" and r["tl"] == "Fact"} - seen)
        if not frontier:
            break
        seen.update(frontier)
    return out


def _new_ancestry(client, graph, root_id, depth=12):
    params = {"id": root_id, "limit": 1000, "depth": depth, "derived_limit": 1000 * depth}
    return [r for r in client.ro(graph, "lineage/why_edges", params) if r["lv"] > 0]


def test_why_edges_ancestry_of_one_fact_does_not_scan_all_derived_from_edges(client, empty_graph):
    _seed(client, empty_graph)
    params = {"id": "A", "limit": 1000, "depth": 12, "derived_limit": 12000}
    ops = profile_ops(client, empty_graph, "lineage/why_edges", params)
    worst = max_records(ops)
    assert worst.records < 20, "scan over all DERIVED_FROM edges: " + "\n".join(map(str, ops))


def test_why_edges_ancestry_matches_the_baseline_level_loop(client, empty_graph):
    _seed(client, empty_graph)
    old = old_client(client)
    try:
        for root_id in ("A", "B", "NE7", "NOPE"):
            assert _rows(_new_ancestry(client, empty_graph, root_id)) == _rows(
                _old_ancestry(old, empty_graph, root_id)
            ), root_id
    finally:
        old.close()
    rows = _rows(_new_ancestry(client, empty_graph, "A"))
    assert rows == sorted(
        [
            ("A", "Fact", "DERIVED_FROM", "B", "Fact"),
            ("A", "Fact", "DERIVED_FROM", "E", "Episode"),
            ("B", "Fact", "ASSERTED_BY", "ag1", "Agent"),
            ("ag2", "Agent", "HAD", "S1", "Session"),
            ("S1", "Session", "HAS_EPISODE", "E", "Episode"),
        ]
    )


def test_why_edges_ancestry_matches_the_baseline_on_the_world(world, client, graph):
    w = world
    old = old_client(client)
    try:
        ids = [r[0] for r in cypher(client, graph, "MATCH (f:Fact) RETURN f.id")]
        for root_id in (w.sessstore, w.db1, *ids):
            new = _new_ancestry(client, graph, root_id)
            assert _rows(new) == _rows(_old_ancestry(old, graph, root_id)), root_id
        assert any(r["rel"] == "DERIVED_FROM" for r in _new_ancestry(client, graph, w.sessstore))
    finally:
        old.close()
