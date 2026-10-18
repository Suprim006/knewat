"""Inventory of a tenant graph (node count per label, edge count per type) for the demo CLI and replay checks."""

from __future__ import annotations

from typing import Any

from plexus.graph.client import GraphClient
from plexus.graph.tenancy import graph_name


def inventory(client: GraphClient, tenant: str) -> dict[str, Any]:
    """``{'nodes': {label: n}, 'edges': {type: n}, 'total_nodes': n, 'total_edges': n}`` for ``tenant``."""
    graph = graph_name(tenant)
    nodes = {r["label"]: int(r["n"]) for r in client.ro(graph, "view/inventory_nodes")}
    edges = {r["type"]: int(r["n"]) for r in client.ro(graph, "view/inventory_edges")}
    return {
        "nodes": nodes,
        "edges": edges,
        "total_nodes": sum(nodes.values()),
        "total_edges": sum(edges.values()),
    }


def format_inventory(inv: dict[str, Any]) -> str:
    lines = [f"nodes: {inv['total_nodes']}   edges: {inv['total_edges']}", "", "node labels:"]
    lines += [f"  {k:<10} {v:>5}" for k, v in sorted(inv["nodes"].items())]
    lines += ["", "edge types:"]
    lines += [f"  {k:<12} {v:>5}" for k, v in sorted(inv["edges"].items())]
    return "\n".join(lines)
