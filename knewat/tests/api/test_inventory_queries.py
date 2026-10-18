"""View inventory queries: O(labels) counts equal the full scans; keys are sampled per label (Q5, Q6, Q9)."""

from __future__ import annotations

import re
from pathlib import Path

from plexus.api import models as M
from plexus.api.view_api import INVENTORY_EDGE_TYPES, INVENTORY_LABELS
from plexus.graph.queries import QueryLibrary
from plexus.graph.tenancy import graph_name

REPO = Path(__file__).resolve().parents[3]


def _branches(name: str, kind: str) -> list[str]:
    text = "\n".join(
        ln
        for ln in QueryLibrary().get(name).path.read_text(encoding="utf-8").splitlines()
        if not ln.startswith("//")
    )
    pattern = r"\(n:(\w+)\)" if kind == "label" else r"\[r:(\w+)\]"
    return re.findall(pattern, text)


def test_static_label_and_type_lists_match_the_graph_model():
    model = (REPO / "docs" / "graph-model.md").read_text(encoding="utf-8")
    model_labels = set(re.findall(r"^\| `(\w+)` \| `", model.split("## Edges")[0], re.M))
    edge_text = model.split("## Edges")[1].split("## Indexes")[0]
    model_types = {
        t for alt in re.findall(r"\[:([A-Z_|\\]+)", edge_text) for t in alt.replace("\\", "").split("|")
    }
    assert set(INVENTORY_LABELS) == model_labels
    assert set(INVENTORY_EDGE_TYPES) == model_types
    assert sorted(_branches("view/inventory_nodes", "label")) == sorted(INVENTORY_LABELS)
    assert sorted(_branches("view/inventory_keys", "label")) == sorted(INVENTORY_LABELS)
    assert sorted(_branches("view/inventory_edges", "type")) == sorted(INVENTORY_EDGE_TYPES)
    assert list(INVENTORY_LABELS) == sorted(INVENTORY_LABELS) and list(INVENTORY_EDGE_TYPES) == sorted(
        INVENTORY_EDGE_TYPES
    )


def test_fast_counts_equal_the_full_scans(client, seeded):
    g = graph_name(seeded["tenant"])
    assert [dict(r) for r in client.ro(g, "view/inventory_nodes")] == [
        dict(r) for r in client.ro(g, "view/inventory_nodes_scan")
    ]
    assert [dict(r) for r in client.ro(g, "view/inventory_edges")] == [
        dict(r) for r in client.ro(g, "view/inventory_edges_scan")
    ]
    assert {r["label"] for r in client.ro(g, "view/labels")} >= {"Fact", "ToolCall", "Step"}
    assert {r["type"] for r in client.ro(g, "view/relationship_types")} >= {"CREATED", "WROTE"}


def test_api_inventory_matches_and_catches_labels_the_static_list_lacks(api, client, seeded):
    t = seeded["tenant"]
    before = M.InventoryResponse(**api.get(f"/api/{t}/inventory").json())
    client.graph(graph_name(t)).query(
        "CREATE (a:Zzz {id: 'z1', created_at: 1})-[:ZZ_LINK]->(b:Zzz {id: 'z2', created_at: 2})"
    )
    after = M.InventoryResponse(**api.get(f"/api/{t}/inventory").json())
    assert {x.label: x.count for x in after.labels}["Zzz"] == 2
    assert {x.type: x.count for x in after.edge_types}["ZZ_LINK"] == 1
    assert after.nodes_total == before.nodes_total + 2 and after.edges_total == before.edges_total + 1
    # everything else is unchanged
    assert {x.label: x.count for x in before.labels}.items() <= {
        x.label: x.count for x in after.labels
    }.items()


def test_keys_are_sampled_per_label(client, seeded):
    """A label whose nodes were written after thousands of others still shows its keys (Q6)."""
    g = graph_name(seeded["tenant"])
    client.graph(g).query("UNWIND range(1, 300) AS i CREATE (:Entity {id: 'bulk' + toString(i), name: 'n'})")
    rows = {r["label"]: set(r["keys"]) for r in client.ro(g, "view/inventory_keys", {"sample": 5})}
    assert {"Entity", "Fact", "ToolCall", "Step", "Task", "Agent"} <= set(rows)
    assert {"id", "tool", "agent_id"} <= rows["ToolCall"]
    assert {"predicate", "value"} <= rows["Fact"]


def test_the_dead_knew_at_query_is_gone():
    assert "view/knew_at" not in QueryLibrary().names()
    assert "lineage/knew_at" in QueryLibrary().names()
