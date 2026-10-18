"""Flow routes: ``/api/{tenant}/flow`` (poll) and ``/api/{tenant}/stream`` (SSE) of tool calls."""

from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator, Callable

import anyio
from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import StreamingResponse
from starlette.background import BackgroundTask

from plexus.api import models as M
from plexus.api.context import FLOW_LIMIT_MAX, ApiContext, Slot, event
from plexus.common import OPEN, now_ms

STREAM_POLL_S = 0.5
STREAM_LOOKBACK_MS = 2000  # re-read this much history each poll; ids already sent are skipped
STREAM_KEEPALIVE_S = 15.0
STREAM_POLL_MIN_MS = 200  # a client cannot drive more than ~5 database reads per second


def router(ctx: ApiContext) -> APIRouter:
    r = APIRouter()
    gate = ctx.gate

    @r.get("/api/{tenant}/flow", response_model=M.FlowResponse)
    def flow(
        tenant: str,
        after: int = Query(0, ge=0, le=OPEN, description="Only tool calls with at > after (epoch ms)."),
        limit: int = Query(200, ge=1, le=FLOW_LIMIT_MAX),
    ):
        events = [event(x) for x in ctx.run(tenant, "view/flow", {"after": after, "limit": limit})]
        return M.FlowResponse(events=events, last_at=max([after, *(e.at for e in events)]))

    @r.get("/api/{tenant}/stream", response_class=StreamingResponse)
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
            ctx.run, tenant, "view/flow", {"after": OPEN, "limit": 1}
        )  # 404 if no such tenant
        last_event_id = request.headers.get("last-event-id") or ""
        start = after if after is not None else (int(last_event_id) if last_event_id.isdigit() else None)
        if start is None:
            start = now_ms()
        if start > OPEN:
            raise HTTPException(422, "Last-Event-ID is out of range")
        if not gate.try_acquire():
            raise HTTPException(429, f"too many open streams (max {gate.limit}); close one and retry")
        slot = Slot(gate)

        async def frames() -> AsyncIterator[str]:
            try:
                async for frame in sse_events(
                    request, lambda a: ctx.flow_events(tenant, a), start, poll_ms / 1000, max_events
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

    return r


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
