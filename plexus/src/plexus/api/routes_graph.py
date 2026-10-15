"""Graph explorer route: ``/api/{tenant}/graph``."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Query

from plexus.api import models as M
from plexus.api.context import ApiContext, activation_props, clean
from plexus.common import OPEN

# What a Fact node reports when it has no such property (written before P7); the contract's defaults.
FACT_DEFAULTS: dict[str, Any] = {
    "verify_state": "verified",
    "suspect_since": 0,
    "verify_after": OPEN,
    "surprise": 0.0,
    "pinned": False,
}
GRAPH_LIMIT_DEFAULT = 500
GRAPH_LIMIT_MAX = 2000


def router(ctx: ApiContext) -> APIRouter:
    r = APIRouter()

    @r.get("/api/{tenant}/graph", response_model=M.GraphResponse)
    def graph(
        tenant: str,
        labels: str = Query("", max_length=2000, description="Comma-separated node labels; empty = all."),
        since: int = Query(0, ge=0, le=OPEN, description="created_at >= since (epoch ms)."),
        until: int = Query(OPEN, ge=0, le=OPEN, description="created_at <= until (epoch ms)."),
        limit: int = Query(GRAPH_LIMIT_DEFAULT, ge=1, le=GRAPH_LIMIT_MAX),
    ):
        wanted = [x.strip() for x in labels.split(",") if x.strip()]
        params = {"labels": wanted, "since": since, "until": until, "limit": limit + 1}
        rows = ctx.run(tenant, "view/subgraph", params)
        row = rows[0] if rows else {"nodes": [], "edges": []}
        raw_nodes = row["nodes"] or []
        truncated = len(raw_nodes) > limit
        raw_nodes = raw_nodes[:limit]
        ids = {n["id"] for n in raw_nodes}
        act = ctx.activations(tenant, [n["id"] for n in raw_nodes if n["label"] == "Fact"])
        nodes = []
        for n in raw_nodes:
            props = clean(n["props"])
            if n["label"] == "Fact":  # facts written before P7 lack these properties: report the defaults
                for k, v in FACT_DEFAULTS.items():
                    props.setdefault(k, v)
                if n["id"] in act:
                    props.update(activation_props(act[n["id"]]))
            nodes.append(M.GraphNode(id=n["id"], label=n["label"], props=props))
        return M.GraphResponse(
            nodes=nodes,
            edges=[
                M.GraphEdge(**e) for e in (row["edges"] or []) if e["source"] in ids and e["target"] in ids
            ],
            truncated=truncated,
            limit=limit,
        )

    return r
