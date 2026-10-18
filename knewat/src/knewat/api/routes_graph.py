"""Graph explorer route: ``/api/{tenant}/graph``."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Query

from knewat.api import models as M
from knewat.api.context import ApiContext, activation_props, clean
from knewat.common import OPEN

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


def _maybe_duplicates(ctx: ApiContext, tenant: str, fact_ids: list[str]) -> dict[str, str]:
    """``{fact id: id of the older fact it may duplicate}`` (P9-c ``DUPLICATES_MAYBE``, nearest first).

    One read for all the facts of the subgraph (index seek per id, see the query).
    """
    if not fact_ids:
        return {}
    rows = ctx.run(tenant, "view/maybe_duplicates", {"ids": fact_ids})
    out: dict[str, str] = {}
    for r in rows:
        out.setdefault(r["id"], r["other"])
    return out


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
        fact_ids = [n["id"] for n in raw_nodes if n["label"] == "Fact"]
        act = ctx.activations(tenant, fact_ids)
        maybe = _maybe_duplicates(ctx, tenant, fact_ids)
        nodes = []
        for n in raw_nodes:
            props = clean(n["props"])
            if n["label"] == "Fact":  # facts written before P7 lack these properties: report the defaults
                for k, v in FACT_DEFAULTS.items():
                    props.setdefault(k, v)
                if n["id"] in act:
                    props.update(activation_props(act[n["id"]]))
                if n["id"] in maybe:
                    props["maybe_duplicate_of"] = maybe[n["id"]]
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
