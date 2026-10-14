"""Pure helpers that turn the edge list of ``lineage/why_edges`` into the structure ``Lineage.why`` returns.

No database access here: everything is a function of ``(rows, node info)`` so it can be unit-tested.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from typing import Any

MAX_WHY_ELEMENTS = 200  # nodes + edges returned by why / why_recalled
MAX_WHY_PATHS = 50
MAX_PATH_HOPS = 5

# Nodes a path never walks out of (keeps paths readable, no hopping through hubs such as an Agent).
_TERMINAL = frozenset({"Agent", "Entity", "Scope", "Source", "Task"})
_FACT_OUTER_RELS = frozenset({"ASSERTED_BY", "DERIVED_FROM"})


def clean(props: Mapping[str, Any]) -> dict[str, Any]:
    """Drop null properties (a missing property comes back as null)."""
    return {k: v for k, v in props.items() if v is not None}


def bound_edges(
    rows: Iterable[Mapping[str, Any]], root: str, max_elements: int
) -> tuple[list[dict[str, str]], dict[str, str], bool]:
    """Keep edges in ``prio`` order while ``len(nodes) + len(edges) <= max_elements``.

    Returns ``(edges, {node id: label} without the root, truncated)``.
    """
    ordered = sorted(rows, key=lambda r: (r["prio"], r["sl"], r["rel"], r["s"], r["t"]))
    labels: dict[str, str] = {}
    edges: list[dict[str, str]] = []
    truncated = False
    budget = max_elements - 1  # the root node always counts
    seen: set[tuple[str, str, str]] = set()
    for r in ordered:
        key = (r["s"], r["rel"], r["t"])
        if key in seen:
            continue
        seen.add(key)
        new_nodes = [
            (i, lab) for i, lab in ((r["s"], r["sl"]), (r["t"], r["tl"])) if i not in labels and i != root
        ]
        cost = 1 + len(new_nodes)
        if cost > budget:
            truncated = True
            continue
        budget -= cost
        edges.append({"from": r["s"], "rel": r["rel"], "to": r["t"]})
        labels.update(dict(new_nodes))
    return edges, labels, truncated


def summarise(
    root: str, kind: str, nodes: list[dict[str, Any]], edges: list[dict[str, str]]
) -> dict[str, Any]:
    """Build the readable ``why`` answer (per-fact evidence, agents, sources, paths) from nodes and edges."""
    by_id = {n["id"]: n for n in nodes}
    label = {i: n["label"] for i, n in by_id.items()}
    out_edges: dict[str, list[tuple[str, str]]] = {}
    in_edges: dict[str, list[tuple[str, str]]] = {}
    for e in edges:
        out_edges.setdefault(e["from"], []).append((e["rel"], e["to"]))
        in_edges.setdefault(e["to"], []).append((e["rel"], e["from"]))

    def outs(i: str, rel: str) -> list[str]:
        return sorted({t for r, t in out_edges.get(i, ()) if r == rel})

    def ins(i: str, rel: str) -> list[str]:
        return sorted({f for r, f in in_edges.get(i, ()) if r == rel})

    def reach(start: str, want: str) -> list[str]:
        """Nodes labelled ``want`` reachable from ``start`` over DERIVED_FROM edges."""
        seen, stack, found = {start}, [start], []
        while stack:
            cur = stack.pop()
            for nxt in outs(cur, "DERIVED_FROM"):
                if nxt not in seen:
                    seen.add(nxt)
                    stack.append(nxt)
                    if label.get(nxt) == want:
                        found.append(nxt)
        return sorted(found)

    base = outs(root, "BASED_ON") if kind == "Decision" else [root]
    facts = [
        {
            "id": f,
            "props": by_id[f]["props"] if f in by_id else {},
            "asserted_by": outs(f, "ASSERTED_BY"),
            "sources": reach(f, "Source"),
            "episodes": reach(f, "Episode"),
            "derived_from_facts": reach(f, "Fact"),
            "supersedes": outs(f, "SUPERSEDES"),
            "superseded_by": ins(f, "SUPERSEDES"),
            "contradicts": outs(f, "CONTRADICTS"),
            "contradicted_by": ins(f, "CONTRADICTS"),
            "written_by_steps": ins(f, "WROTE"),
        }
        for f in base
    ]

    def of(lab: str) -> list[str]:
        return sorted(i for i, lb in label.items() if lb == lab)

    return {
        "root": root,
        "kind": kind,
        "facts": facts,
        "agents": of("Agent"),
        "sources": of("Source"),
        "episodes": of("Episode"),
        "steps": of("Step"),
        "paths": paths_from(root, set(base), label, edges),
        "nodes": nodes,
        "edges": edges,
    }


def paths_from(
    root: str, base: set[str], label: Mapping[str, str], edges: list[dict[str, str]]
) -> list[list[dict[str, Any]]]:
    """Maximal simple paths from ``root`` over the edge list (either direction), at most 5 hops, 50 paths.

    A hop is ``{from, rel, to, reverse}``; ``reverse`` is true when the stored edge points ``to -> from``.
    """
    adj: dict[str, list[tuple[str, str, bool]]] = {}
    for e in edges:
        adj.setdefault(e["from"], []).append((e["rel"], e["to"], False))
        adj.setdefault(e["to"], []).append((e["rel"], e["from"], True))

    def may_leave(here: str, rel: str, reverse: bool) -> bool:
        lab = label.get(here)
        if lab in _TERMINAL:
            return False
        if lab == "Step":
            return rel == "BY" and not reverse
        if lab == "Session":
            return rel == "HAD" and reverse
        if lab == "Episode":
            return rel == "HAS_EPISODE" and reverse
        if lab == "Fact" and here not in base:
            return rel in _FACT_OUTER_RELS and not reverse
        return True

    paths: list[list[dict[str, Any]]] = []

    def walk(here: str, path: list[dict[str, Any]], seen: set[str]) -> None:
        if len(paths) >= MAX_WHY_PATHS:
            return
        options = (
            [a for a in sorted(adj.get(here, ())) if a[1] not in seen and may_leave(here, a[0], a[2])]
            if len(path) < MAX_PATH_HOPS
            else []
        )
        if not options:
            if path:
                paths.append(path)
            return
        for rel, to, rev in options:
            walk(to, [*path, {"from": here, "rel": rel, "to": to, "reverse": rev}], seen | {to})

    walk(root, [], {root})
    return paths
