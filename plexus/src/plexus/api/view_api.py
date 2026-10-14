"""Read-only View API. ``uv run plexus-api`` serves http://127.0.0.1:8080 (env PLEXUS_API_HOST / PLEXUS_API_PORT).

Every database access goes through :class:`ReadOnlyClient`, which only exposes ``ro()`` (``GRAPH.RO_QUERY``) and the
graph list; there is no write path in this package.
"""

from __future__ import annotations

import asyncio
import importlib
import json
import logging
import os
import threading
import time
from collections.abc import AsyncIterator, Callable
from pathlib import Path
from typing import Any

import anyio
from fastapi import FastAPI, HTTPException, Query, Request
from fastapi import Path as PathParam
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, StreamingResponse
from redis.exceptions import RedisError, ResponseError
from starlette.background import BackgroundTask

from plexus.api import models as M
from plexus.graph.client import GraphClient, Rows
from plexus.graph.queries import QueryLibrary, UnknownQuery
from plexus.graph.tenancy import TENANT_PREFIX, graph_name

log = logging.getLogger("plexus.api")

OPEN = 9_999_999_999_999
DEFAULT_ORIGINS = "http://localhost:5180,http://127.0.0.1:5180,http://localhost:5173,http://127.0.0.1:5173"
GRAPH_LIMIT_DEFAULT = 500
GRAPH_LIMIT_MAX = 2000
FLOW_LIMIT_MAX = 1000
STREAM_POLL_S = 0.5
STREAM_LOOKBACK_MS = 2000  # re-read this much history each poll; ids already sent are skipped
STREAM_KEEPALIVE_S = 15.0
STREAM_POLL_MIN_MS = 200  # a client cannot drive more than ~5 database reads per second
MAX_STREAMS = 20  # concurrent /stream connections (env PLEXUS_API_MAX_STREAMS); more get 429
FLOW_CACHE_TTL_S = 0.15  # subscribers polling within this window share one view/flow read
FLOW_CACHE_MAX = 256
MAX_ID = 128
INVENTORY_KEY_SAMPLE = 20_000


class ReadOnlyClient:
    """The only database handle the API gets: named read queries and the graph list."""

    def __init__(self, inner: GraphClient):
        self._inner = inner
        self.library: QueryLibrary = inner.library

    def ro(self, graph: str, name: str, params: dict | None = None) -> Rows:
        return self._inner.ro(graph, name, params)

    def ping(self) -> bool:
        return self._inner.ping()

    def tenants(self) -> list[str]:
        graphs = self._inner.db.list_graphs()
        return sorted(g[len(TENANT_PREFIX) :] for g in graphs if g.startswith(TENANT_PREFIX))


class StreamGate:
    """Caps concurrent SSE connections; a slot is released exactly once however the stream ends."""

    def __init__(self, limit: int):
        self.limit = limit
        self.active = 0
        self._lock = threading.Lock()

    def try_acquire(self) -> bool:
        with self._lock:
            if self.active >= self.limit:
                return False
            self.active += 1
            return True

    def release(self) -> None:
        with self._lock:
            self.active = max(self.active - 1, 0)


class _Slot:
    """One acquired stream slot; ``release`` is idempotent (generator end and response end both call it)."""

    def __init__(self, gate: StreamGate):
        self._gate = gate
        self._done = False

    def release(self) -> None:
        if not self._done:
            self._done = True
            self._gate.release()


def _cors_origins() -> list[str]:
    raw = os.environ.get("PLEXUS_CORS_ORIGINS", DEFAULT_ORIGINS)
    return [o.strip() for o in raw.split(",") if o.strip()]


def _clean(props: dict[str, Any]) -> dict[str, Any]:
    return {k: v for k, v in props.items() if v is not None}


def _event(row: dict[str, Any]) -> M.ToolCallEvent:
    step = row["step"]
    return M.ToolCallEvent(
        id=row["id"],
        tool=row["tool"],
        at=row["at"],
        agent_id=row["agent_id"],
        query_name=row["query_name"] or "",
        run_time_ms=row["run_time_ms"] or 0.0,
        wrote=bool(row["wrote"]),
        step=None if step is None or step < 0 else step,
        step_id=row["step_id"],
        step_n=row["step_n"],
        created=[M.NodeRef(**x) for x in row["created"]],
        updated=[M.NodeRef(**x) for x in row["updated"]],
    )


def create_app(
    client: GraphClient | None = None, results_path: str | None = None, max_streams: int | None = None
) -> FastAPI:
    ro_client = ReadOnlyClient(client or GraphClient())
    gate = StreamGate(
        max_streams
        if max_streams is not None
        else int(os.environ.get("PLEXUS_API_MAX_STREAMS") or MAX_STREAMS)
    )
    app = FastAPI(title="Plexus View API", version="0.1.0", description="Read-only API for plexus-view.")
    app.add_middleware(
        CORSMiddleware,
        allow_origins=_cors_origins(),
        allow_methods=["GET"],
        allow_headers=["*"],
    )
    app.state.ro = ro_client
    app.state.streams = gate

    def graph_of(tenant: str) -> str:
        try:
            return graph_name(tenant)
        except ValueError:
            raise HTTPException(404, f"unknown tenant '{tenant}'") from None

    def run(tenant: str, query: str, params: dict | None = None) -> Rows:
        g = graph_of(tenant)
        try:
            return ro_client.ro(g, query, params)
        except ResponseError as exc:
            if "empty key" in str(exc).lower() or "not exist" in str(exc).lower():
                raise HTTPException(404, f"unknown tenant '{tenant}'") from None
            log.exception("query %s failed", query)
            raise HTTPException(502, "the graph database rejected the query") from None
        except (RedisError, OSError):
            log.exception("database unreachable")
            raise HTTPException(503, "graph database unavailable") from None

    def run_flow(tenant: str, after: int) -> list[M.ToolCallEvent]:
        return [_event(r) for r in run(tenant, "view/flow", {"after": after, "limit": FLOW_LIMIT_MAX})]

    flow_cache: dict[tuple[str, int], tuple[float, list[M.ToolCallEvent]]] = {}
    flow_locks: dict[tuple[str, int], threading.Lock] = {}

    def flow_events(tenant: str, after: int) -> list[M.ToolCallEvent]:
        """``run_flow`` shared between subscribers: polls of the same (tenant, after) within the TTL cost one read."""
        key = (tenant, after)
        hit = flow_cache.get(key)
        if hit is not None and time.monotonic() - hit[0] < FLOW_CACHE_TTL_S:
            return hit[1]
        with flow_locks.setdefault(key, threading.Lock()):
            hit = flow_cache.get(key)
            if hit is not None and time.monotonic() - hit[0] < FLOW_CACHE_TTL_S:
                return hit[1]
            events = run_flow(tenant, after)
            now = time.monotonic()
            flow_cache[key] = (now, events)
            if len(flow_cache) > FLOW_CACHE_MAX:  # drop expired entries (and their locks)
                for k in [k for k, (t, _) in flow_cache.items() if now - t >= FLOW_CACHE_TTL_S]:
                    flow_cache.pop(k, None)
                    flow_locks.pop(k, None)
            return events

    app.state.flow_events = flow_events

    @app.get("/healthz", include_in_schema=False)
    def healthz(deep: int = 0) -> JSONResponse:
        """Liveness (static). ``?deep=1`` also pings the database, so a compose healthcheck notices it is down."""
        if deep:
            try:
                ro_client.ping()
            except (RedisError, OSError):
                return JSONResponse({"status": "unavailable"}, status_code=503)
        return JSONResponse({"status": "ok"})

    # ------------------------------------------------------------------ files
    @app.get("/api/queries/{name:path}", response_model=M.QueryText)
    def query_text(name: str):
        try:
            q = ro_client.library.get(name)
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

    @app.get("/api/results")
    def results():
        path = results_path or os.environ.get("PLEXUS_RESULTS_PATH")
        if not path or not Path(path).is_file():
            raise HTTPException(404, "no Crucible results available")
        try:
            return JSONResponse(json.loads(Path(path).read_text(encoding="utf-8")))
        except ValueError:
            raise HTTPException(500, "results file is not valid JSON") from None

    # ------------------------------------------------------------------ tenants and inventory
    @app.get("/api/tenants", response_model=M.TenantsResponse)
    def tenants():
        try:
            names = ro_client.tenants()
        except (RedisError, OSError):
            raise HTTPException(503, "graph database unavailable") from None
        return M.TenantsResponse(tenants=[M.TenantInfo(tenant=t, graph=TENANT_PREFIX + t) for t in names])

    @app.get("/api/{tenant}/inventory", response_model=M.InventoryResponse)
    def inventory(tenant: str):
        nodes = run(tenant, "view/inventory_nodes")
        edges = run(tenant, "view/inventory_edges")
        sample = {"sample": INVENTORY_KEY_SAMPLE}
        keys = {r["label"]: sorted(r["keys"]) for r in run(tenant, "view/inventory_keys", sample)}
        idx = run(tenant, "view/indexes")
        return M.InventoryResponse(
            tenant=tenant,
            nodes_total=sum(r["n"] for r in nodes),
            edges_total=sum(r["n"] for r in edges),
            labels=[
                M.LabelInventory(label=r["label"], count=r["n"], keys=keys.get(r["label"], [])) for r in nodes
            ],
            edge_types=[M.EdgeInventory(type=r["type"], count=r["n"]) for r in edges],
            indexes=[
                M.IndexInfo(
                    label=r["label"],
                    properties=list(r["properties"]),
                    types={k: list(v) for k, v in (r["types"] or {}).items()},
                    entity_type=r["entitytype"],
                    status=r["status"],
                )
                for r in idx
            ],
        )

    # ------------------------------------------------------------------ graph explorer
    @app.get("/api/{tenant}/graph", response_model=M.GraphResponse)
    def graph(
        tenant: str,
        labels: str = Query("", max_length=2000, description="Comma-separated node labels; empty = all."),
        since: int = Query(0, ge=0, le=OPEN, description="created_at >= since (epoch ms)."),
        until: int = Query(OPEN, ge=0, le=OPEN, description="created_at <= until (epoch ms)."),
        limit: int = Query(GRAPH_LIMIT_DEFAULT, ge=1, le=GRAPH_LIMIT_MAX),
    ):
        wanted = [x.strip() for x in labels.split(",") if x.strip()]
        params = {"labels": wanted, "since": since, "until": until, "limit": limit + 1}
        rows = run(tenant, "view/subgraph", params)
        row = rows[0] if rows else {"nodes": [], "edges": []}
        raw_nodes = row["nodes"] or []
        truncated = len(raw_nodes) > limit
        raw_nodes = raw_nodes[:limit]
        ids = {n["id"] for n in raw_nodes}
        return M.GraphResponse(
            nodes=[M.GraphNode(id=n["id"], label=n["label"], props=_clean(n["props"])) for n in raw_nodes],
            edges=[
                M.GraphEdge(**e) for e in (row["edges"] or []) if e["source"] in ids and e["target"] in ids
            ],
            truncated=truncated,
            limit=limit,
        )

    # ------------------------------------------------------------------ flow and SSE
    @app.get("/api/{tenant}/flow", response_model=M.FlowResponse)
    def flow(
        tenant: str,
        after: int = Query(0, ge=0, le=OPEN, description="Only tool calls with at > after (epoch ms)."),
        limit: int = Query(200, ge=1, le=FLOW_LIMIT_MAX),
    ):
        events = [_event(r) for r in run(tenant, "view/flow", {"after": after, "limit": limit})]
        return M.FlowResponse(events=events, last_at=max([after, *(e.at for e in events)]))

    @app.get("/api/{tenant}/stream", response_class=StreamingResponse)
    async def stream(
        request: Request,
        tenant: str,
        after: int | None = Query(
            None, ge=0, le=OPEN, description="Start after this `at`; default: now (live only)."
        ),
        max_events: int | None = Query(
            None, ge=1, le=100_000, description="Close after this many events (tests/tools)."
        ),
        poll_ms: int = Query(
            int(STREAM_POLL_S * 1000),
            ge=STREAM_POLL_MIN_MS,
            le=10_000,
            description="Database poll interval; at least 200.",
        ),
    ):
        await anyio.to_thread.run_sync(
            run, tenant, "view/flow", {"after": OPEN, "limit": 1}
        )  # 404 if no such tenant
        last_event_id = request.headers.get("last-event-id") or ""
        start = after if after is not None else (int(last_event_id) if last_event_id.isdigit() else None)
        if start is None:
            start = int(time.time() * 1000)
        if start > OPEN:
            raise HTTPException(422, "Last-Event-ID is out of range")
        if not gate.try_acquire():
            raise HTTPException(429, f"too many open streams (max {gate.limit}); close one and retry")
        slot = _Slot(gate)

        async def frames() -> AsyncIterator[str]:
            try:
                async for frame in sse_events(
                    request, lambda a: flow_events(tenant, a), start, poll_ms / 1000, max_events
                ):
                    yield frame
            finally:
                slot.release()

        return StreamingResponse(
            frames(),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
            background=BackgroundTask(slot.release),
        )

    # ------------------------------------------------------------------ lineage-backed
    def lineage_module():
        try:
            return importlib.import_module("plexus.lineage")
        except ImportError:
            raise HTTPException(501, "Lineage is not installed in this deployment") from None

    def lineage(tenant: str):
        """A ``Lineage`` bound to the tenant graph over the read-only client (it cannot write)."""
        cls = getattr(lineage_module(), "Lineage", None)
        if cls is None:
            raise HTTPException(501, "this Lineage build has no Lineage class")
        return cls(ro_client, graph_of(tenant))

    def explain(tenant: str, method: str, arg: Any, model: Any, ident: str):
        lin = lineage(tenant)
        if not hasattr(lin, method):
            raise HTTPException(501, f"this Lineage build has no {method}()")
        try:
            result = getattr(lin, method)(arg)
        except (LookupError, ValueError) as exc:
            raise HTTPException(404, str(exc)) from None
        except ResponseError as exc:
            if "empty key" in str(exc).lower() or "not exist" in str(exc).lower():
                raise HTTPException(404, f"unknown tenant '{tenant}'") from None
            log.exception("%s failed", method)
            raise HTTPException(502, "the graph database rejected the query") from None
        except (RedisError, OSError):
            log.exception("database unreachable")
            raise HTTPException(503, "graph database unavailable") from None
        return model(id=ident, result=json.loads(json.dumps(result, default=str)))

    @app.get("/api/{tenant}/step/{n}", response_model=M.StepResponse)
    def step(tenant: str, n: int = PathParam(ge=0, le=OPEN)):
        """What each agent knew and wrote at its latest step <= n: ``Lineage.knew_at`` per agent."""
        lin = lineage(tenant)
        agents: list[M.StepAgent] = []
        for row in run(tenant, "view/step_agents", {"n": n}):
            try:
                k = lin.knew_at(row["agent_id"], n)
            except (RedisError, OSError):
                log.exception("database unreachable")
                raise HTTPException(503, "graph database unavailable") from None
            if k["step_n"] is None:
                continue
            agents.append(
                M.StepAgent(
                    agent_id=k["agent_id"],
                    step_n=k["step_n"],
                    step_at=k["at"],
                    read=[
                        M.StepFact(
                            id=f["fact_id"],
                            entity=f["entity"],
                            predicate=f["predicate"],
                            value=f["value"],
                            status=f["status"],
                            valid_from=f["valid_from"],
                            valid_to=f["valid_to"],
                            read_at_step=f["read_at_step"],
                        )
                        for f in k["facts"]
                    ],
                    wrote=[
                        M.StepWrote(id=w["id"], label=w["label"], summary=w["summary"], step_n=w["step_n"])
                        for w in k["wrote"]
                    ],
                )
            )
        return M.StepResponse(n=n, agents=agents)

    @app.get("/api/{tenant}/why/{node_id}", response_model=M.WhyResponse)
    def why(tenant: str, node_id: str = PathParam(min_length=1, max_length=MAX_ID)):
        """``Lineage.why`` for a decision or fact id."""
        return explain(tenant, "why", node_id, M.WhyResponse, node_id)

    @app.get("/api/{tenant}/recall/{recall_id}", response_model=M.RecallResponse)
    def recall_record(tenant: str, recall_id: str = PathParam(min_length=1, max_length=MAX_ID)):
        """``Lineage.why_recalled`` for a recall id (the recall tool returns it as ``recall_id``)."""
        return explain(tenant, "why_recalled", recall_id, M.RecallResponse, recall_id)

    return app


async def sse_events(
    request: Request,
    fetch: Callable[[int], list[M.ToolCallEvent]],
    start: int,
    poll_s: float,
    max_events: int | None,
) -> AsyncIterator[str]:
    """Poll ``fetch(after)`` and yield SSE frames for tool calls not sent yet.

    Each poll re-reads ``STREAM_LOOKBACK_MS`` of history and skips ids already sent, so a call that lands late
    with a slightly older ``at`` (concurrent writers) is still delivered exactly once.
    """
    last_at = start
    seen: dict[str, int] = {}  # id -> at, pruned outside the look-back window
    sent = 0
    idle = 0.0
    yield "retry: 1000\n\n"
    while True:
        if await request.is_disconnected():
            return
        try:
            events = await anyio.to_thread.run_sync(fetch, max(last_at - STREAM_LOOKBACK_MS, 0))
        except HTTPException as exc:
            yield f"event: error\ndata: {json.dumps({'detail': exc.detail})}\n\n"
            return
        fresh = [e for e in events if e.id not in seen and e.at > start]
        for e in fresh:
            seen[e.id] = e.at
            last_at = max(last_at, e.at)
            yield f"id: {e.at}\nevent: toolcall\ndata: {e.model_dump_json()}\n\n"
            sent += 1
            if max_events is not None and sent >= max_events:
                return
        floor = last_at - STREAM_LOOKBACK_MS - 1000
        seen = {i: a for i, a in seen.items() if a >= floor}
        if fresh:
            idle = 0.0
        else:
            idle += poll_s
            if idle >= STREAM_KEEPALIVE_S:
                idle = 0.0
                yield ": keep-alive\n\n"
        await asyncio.sleep(poll_s)


def main() -> None:
    import uvicorn

    logging.basicConfig(level=logging.INFO)
    uvicorn.run(
        create_app(),
        host=os.environ.get("PLEXUS_API_HOST", "127.0.0.1"),
        port=int(os.environ.get("PLEXUS_API_PORT", "8080")),
        log_level="info",
    )


if __name__ == "__main__":
    main()
