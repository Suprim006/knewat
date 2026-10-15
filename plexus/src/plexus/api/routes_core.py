"""Static and inventory routes: ``/healthz``, ``/api/queries``, ``/api/results``, ``/api/tenants``, inventory."""

from __future__ import annotations

import json
import os
from pathlib import Path

from fastapi import APIRouter, HTTPException
from fastapi.responses import JSONResponse
from redis.exceptions import RedisError

from plexus.api import models as M
from plexus.api.context import ApiContext
from plexus.common import now_ms
from plexus.graph.queries import UnknownQuery
from plexus.graph.tenancy import TENANT_PREFIX

INVENTORY_KEY_SAMPLE = 200  # nodes sampled PER LABEL for the property-key inventory
# The graph model's node labels and edge types (docs/graph-model.md). view/inventory_nodes|edges|keys count each of
# them in O(1); a test keeps these lists, the queries and the model in sync, and the inventory endpoint falls back
# to the full scans if the graph holds a label or type that is not listed.
INVENTORY_LABELS = (
    "Agent Artifact Change CodeAnchor Decision Entity Episode Fact Handoff Procedure Recall Run Scope Session Source Step "
    "Task ToolCall"
).split()
INVENTORY_EDGE_TYPES = sorted(
    (
        "ABOUT ANCHORED_TO ASSERTED_BY BASED_ON BY CARRIES CLAIMED CONTRADICTS CREATED DECIDED DEPENDS_ON DERIVED_FROM "
        "DESCRIBES DUPLICATES FOR FROM HAD HAS_EPISODE IN_SCOPE IN_STEP INHERITS NEXT PRODUCED_BY READ RETURNED "
        "SUPERSEDES SUSPECTED TO TOUCHED UPDATED USED_IN VERIFIED_BY WROTE"
    ).split()
)


def router(ctx: ApiContext) -> APIRouter:
    r = APIRouter()
    run = ctx.run

    @r.get("/healthz", include_in_schema=False)
    def healthz(deep: int = 0) -> JSONResponse:
        """Liveness (static). ``?deep=1`` also pings the database, so a compose healthcheck notices it is down."""
        if deep:
            try:
                ctx.ro.ping()
            except (RedisError, OSError):
                return JSONResponse({"status": "unavailable"}, status_code=503)
        return JSONResponse({"status": "ok"})

    # ------------------------------------------------------------------ files
    @r.get("/api/queries/{name:path}", response_model=M.QueryText)
    def query_text(name: str):
        try:
            q = ctx.ro.library.get(name)
        except UnknownQuery:
            raise HTTPException(404, f"unknown query '{name}'") from None
        return M.QueryText(
            name=q.name,
            mode=q.mode,
            purpose=q.purpose,
            params=dict(q.params),
            returns=q.returns,
            text=Path(q.path).read_text(encoding="utf-8"),
        )

    @r.get("/api/results")
    def results():
        path = ctx.results_path or os.environ.get("PLEXUS_RESULTS_PATH")
        if not path or not Path(path).is_file():
            raise HTTPException(404, "no Crucible results available")
        try:
            return JSONResponse(json.loads(Path(path).read_text(encoding="utf-8")))
        except ValueError:
            raise HTTPException(500, "results file is not valid JSON") from None

    # ------------------------------------------------------------------ tenants and inventory
    @r.get("/api/tenants", response_model=M.TenantsResponse)
    def tenants():
        try:
            names = ctx.ro.tenants()
        except (RedisError, OSError):
            raise HTTPException(503, "graph database unavailable") from None
        return M.TenantsResponse(tenants=[M.TenantInfo(tenant=t, graph=TENANT_PREFIX + t) for t in names])

    @r.get("/api/{tenant}/inventory", response_model=M.InventoryResponse)
    def inventory(tenant: str):
        nodes = run(tenant, "view/inventory_nodes")
        if {x["label"] for x in run(tenant, "view/labels")} - set(INVENTORY_LABELS):
            nodes = run(tenant, "view/inventory_nodes_scan")  # an unlisted label exists: count everything
        edges = run(tenant, "view/inventory_edges")
        if {x["type"] for x in run(tenant, "view/relationship_types")} - set(INVENTORY_EDGE_TYPES):
            edges = run(tenant, "view/inventory_edges_scan")
        sample = {"sample": INVENTORY_KEY_SAMPLE}
        keys = {x["label"]: sorted(x["keys"]) for x in run(tenant, "view/inventory_keys", sample)}
        idx = run(tenant, "view/indexes")
        mem = run(tenant, "view/inventory_memory", {"now": now_ms()})[0]
        return M.InventoryResponse(
            tenant=tenant,
            nodes_total=sum(x["n"] for x in nodes),
            edges_total=sum(x["n"] for x in edges),
            labels=[
                M.LabelInventory(label=x["label"], count=x["n"], keys=keys.get(x["label"], [])) for x in nodes
            ],
            edge_types=[M.EdgeInventory(type=x["type"], count=x["n"]) for x in edges],
            indexes=[
                M.IndexInfo(
                    label=x["label"],
                    properties=list(x["properties"]),
                    types={k: list(v) for k, v in (x["types"] or {}).items()},
                    entity_type=x["entitytype"],
                    status=x["status"],
                )
                for x in idx
            ],
            suspect_facts=mem["suspect_facts"],
            dormant_facts=mem["dormant_facts"],
            pinned_facts=mem["pinned_facts"],
            changes=mem["changes"],
            code_anchors=mem["code_anchors"],
        )

    return r
