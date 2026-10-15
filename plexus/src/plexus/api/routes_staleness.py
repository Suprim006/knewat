"""Staleness and forgetting routes (P7): ``/verify-queue``, ``/docs-to-update`` and ``/memory-strength/{fact_id}``."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query
from fastapi import Path as PathParam

from plexus.activation import Activation, Settings
from plexus.api import models as M
from plexus.api.context import ApiContext, activation_props
from plexus.api.routes_lineage import MAX_ID
from plexus.common import OPEN
from plexus.staleness import Staleness

VERIFY_LIMIT_MAX = 200  # = plexus.staleness.service.MAX_LIST


def router(ctx: ApiContext) -> APIRouter:
    r = APIRouter()

    @r.get("/api/{tenant}/verify-queue", response_model=M.VerifyQueueResponse)
    def verify_queue(
        tenant: str,
        scope_id: str = Query(
            "", max_length=MAX_ID, description="Limit to this scope and the scopes it inherits."
        ),
        limit: int = Query(50, ge=1, le=VERIFY_LIMIT_MAX),
    ):
        """``Staleness.facts_to_verify`` plus each fact's activation: what an agent should re-check next."""
        stale = Staleness(ctx.ro, ctx.graph_of(tenant))  # type: ignore[arg-type]
        rows = ctx.guarded(tenant, "facts_to_verify", lambda: stale.facts_to_verify(scope_id, limit))
        act = ctx.activations(tenant, [x["fact_id"] for x in rows])
        out = []
        for x in rows:
            extra = activation_props(act[x["fact_id"]]) if x["fact_id"] in act else {}
            out.append(M.VerifyRow(**{**x, **extra}))
        return M.VerifyQueueResponse(rows=out)

    @r.get("/api/{tenant}/docs-to-update", response_model=M.DocsToUpdateResponse)
    def docs_to_update(
        tenant: str,
        since: int = Query(0, ge=0, le=OPEN, description="Only changes with at >= since (epoch ms)."),
        limit: int = Query(50, ge=1, le=VERIFY_LIMIT_MAX),
    ):
        """``Staleness.docs_to_update``: docs that describe code which changed after the doc was last edited."""
        stale = Staleness(ctx.ro, ctx.graph_of(tenant))  # type: ignore[arg-type]
        rows = ctx.guarded(tenant, "docs_to_update", lambda: stale.docs_to_update(since, limit))
        return M.DocsToUpdateResponse(docs=[M.DocRow(**x) for x in rows])

    @r.get("/api/{tenant}/memory-strength/{fact_id}", response_model=M.MemoryStrengthResponse)
    def memory_strength(tenant: str, fact_id: str = PathParam(min_length=1, max_length=MAX_ID)):
        """``Activation.strength``: activation, protection and a one-line explanation. Never counts as a use."""
        settings = Settings.from_env()
        act = Activation(ctx.ro, ctx.graph_of(tenant), settings)  # type: ignore[arg-type]
        s = ctx.guarded(tenant, "memory_strength", lambda: act.strength(fact_id))
        if s is None:
            raise HTTPException(404, f"unknown fact id: {fact_id}")
        return M.MemoryStrengthResponse(**s, forgetting=settings.forgetting)

    return r
