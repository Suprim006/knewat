"""P5-int Q5: ``view/subgraph`` is driven by per-label ``created_at`` range indexes, not an All Node Scan.

Seeds 900 nodes (300 each of ToolCall, Step, Fact; one of every other label) with ``created_at`` 1..300 and
checks, on the real plan (GRAPH.EXPLAIN / GRAPH.PROFILE):

* every label has a ``created_at`` index and the query has one branch per label;
* the plan has no All Node Scan and no node-by-label scan;
* a time window or a label filter makes the scan produce about the matching rows (graph: 900 nodes);
* the answer equals the old query's (inlined below as the reference) for every filter combination.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from plexus.api.view_api import INVENTORY_LABELS
from plexus.graph.queries import QueryLibrary
from tests.plan_util import explain_lines, max_records, profile_ops

OPEN = 9_999_999_999_999
QUERIES = Path(__file__).resolve().parents[2] / "queries"
BIG_LABELS = ("ToolCall", "Step", "Fact")
N = 300

# The query as it was before P5-int (an unlabeled MATCH + filter). Only the node-selection head matters here.
OLD_HEAD = """
MATCH (n)
WHERE n.created_at >= $since AND n.created_at <= $until AND (size($labels) = 0 OR labels(n)[0] IN $labels)
WITH n ORDER BY n.created_at DESC, n.id LIMIT $limit
RETURN collect(n.id) AS ids
"""


@pytest.fixture
def seeded(client, graph):
    g = client.graph(graph)
    for lab in BIG_LABELS:
        g.query(
            f"UNWIND range(1, $n) AS i CREATE (:{lab} {{id: $lab + '-' + toString(i), created_at: i}})",
            {"n": N, "lab": lab},
        )
    for lab in INVENTORY_LABELS:
        if lab not in BIG_LABELS:
            g.query(f"CREATE (:{lab} {{id: $lab, created_at: 150}})", {"lab": lab})
    g.query(
        """MATCH (f:Fact), (s:Step) WHERE f.id = 'Fact-' + right(s.id, size(s.id) - 5)
           AND toInteger(right(f.id, size(f.id) - 5)) <= 40
           CREATE (f)-[:IN_STEP]->(s)"""
    )
    return graph


def params(**kw):
    return {"labels": [], "since": 0, "until": OPEN, "limit": 50, **kw}


def test_every_label_has_a_branch_and_a_created_at_index():
    text = (QUERIES / "view" / "subgraph.cypher").read_text(encoding="utf-8")
    branches = set(re.findall(r"MATCH \(n:(\w+)\) WHERE n\.created_at", text))
    idx = (QUERIES / "schema" / "indexes.cypher").read_text(encoding="utf-8")
    id_labels = set(re.findall(r"CREATE INDEX FOR \(n:(\w+)\) ON \(n\.id\)", idx))
    created_labels = set(re.findall(r"CREATE INDEX FOR \(n:(\w+)\) ON \(n\.created_at\)", idx))
    # P7-J labels (graph model v1.1) have id indexes but are not in the View inventory yet
    id_labels -= {"CodeAnchor", "Change"}
    assert branches == created_labels == id_labels == set(INVENTORY_LABELS)


def test_indexes_exist_in_a_schema_applied_graph(client, graph):
    rows = client.ro(graph, "schema/list_indexes")
    have = {r["label"] for r in rows if "created_at" in r["properties"]}
    assert have == set(INVENTORY_LABELS)


def test_plan_is_index_range_seeks_only(client, seeded):
    lines = explain_lines(client, seeded, "view/subgraph", params())
    assert not [ln for ln in lines if ln.startswith("All Node Scan")], "\n".join(lines)
    assert not [ln for ln in lines if ln.startswith("Node By Label Scan")], "\n".join(lines)
    assert len([ln for ln in lines if ln.startswith("Node By Index Scan")]) == len(INVENTORY_LABELS)


def test_time_window_reads_only_the_window(client, seeded):
    # the newest 20 of each big label: 60 rows in the window, out of 900 nodes
    ops = profile_ops(client, seeded, "view/subgraph", params(since=N - 19))
    worst = max_records(ops)
    assert worst.records <= 3 * 20 + 16, "\n".join(map(str, ops))
    assert worst.records < 900 / 4


def test_label_filter_reads_only_that_label(client, seeded):
    ops = profile_ops(client, seeded, "view/subgraph", params(labels=["ToolCall"], limit=1000))
    scans = [o for o in ops if o.name == "Node By Index Scan"]
    assert sum(o.records for o in scans) == N, "\n".join(map(str, ops))
    assert max_records(ops).records <= N
    assert [o for o in scans if o.records] and len([o for o in scans if o.records]) == 1


def test_unlisted_labels_cost_nothing(client, seeded):
    ops = profile_ops(client, seeded, "view/subgraph", params(labels=["Task"], limit=1000))
    assert sum(o.records for o in ops if o.name == "Node By Index Scan") == 1  # the single Task node
    assert max_records(ops).records <= 2


@pytest.mark.parametrize(
    "kw",
    [
        {},
        {"labels": ["ToolCall"]},
        {"labels": ["Fact", "Step"], "limit": 33},
        {"labels": ["Fact", "Nope"], "limit": 1000},
        {"since": 100, "until": 120, "limit": 1000},
        {"since": 280, "limit": 7},
        {"since": 500, "until": 600},
        {"labels": ["Agent"], "since": 150, "until": 150},
    ],
)
def test_same_nodes_as_the_old_query(client, seeded, kw):
    p = params(**kw)
    g = client.graph(seeded)
    old_ids = g.ro_query(OLD_HEAD, p).result_set[0][0]
    rows = client.ro(seeded, "view/subgraph", p)
    new_ids = [n["id"] for n in rows[0]["nodes"]] if rows else []
    assert new_ids == old_ids or sorted(new_ids) == sorted(old_ids)
    assert len(new_ids) == len(set(new_ids))
    if rows:
        ids = set(new_ids)
        assert all(e["source"] in ids and e["target"] in ids for e in rows[0]["edges"])


def test_edges_among_the_selected_nodes(client, seeded):
    rows = client.ro(seeded, "view/subgraph", params(labels=["Fact", "Step"], limit=1000))
    edges = rows[0]["edges"]
    assert len(edges) == 40 and {e["type"] for e in edges} == {"IN_STEP"}


def test_library_loads_the_query(client):
    assert isinstance(client.library, QueryLibrary)
    q = client.library.get("view/subgraph")
    assert q.mode == "ro" and len(q.statements) == 1
