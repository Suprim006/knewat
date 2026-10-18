"""P9-int: the graph route marks a fact with ``maybe_duplicate_of`` while a DUPLICATES_MAYBE link is open."""

from __future__ import annotations

from plexus.api import models as M
from plexus.graph.tenancy import graph_name


def test_graph_nodes_carry_maybe_duplicate_of_and_the_edge_is_listed(api, seeded, client):
    t, new, old = seeded["tenant"], seeded["f2"], seeded["f1"]
    plain = M.GraphResponse(**api.get(f"/api/{t}/graph").json())
    assert all("maybe_duplicate_of" not in n.props for n in plain.nodes)
    client.graph(graph_name(t)).query(
        "MATCH (a:Fact {id: $a}), (b:Fact {id: $b}) CREATE (a)-[:DUPLICATES_MAYBE {score: 0.9}]->(b)",
        {"a": new, "b": old},
    )
    g = M.GraphResponse(**api.get(f"/api/{t}/graph").json())
    by_id = {n.id: n for n in g.nodes}
    assert by_id[new].props["maybe_duplicate_of"] == old
    assert "maybe_duplicate_of" not in by_id[old].props
    assert any(e.type == "DUPLICATES_MAYBE" and e.source == new and e.target == old for e in g.edges)
    inv = M.InventoryResponse(**api.get(f"/api/{t}/inventory").json())
    assert {e.type: e.count for e in inv.edge_types}["DUPLICATES_MAYBE"] == 1
