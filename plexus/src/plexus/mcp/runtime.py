"""MCP runtime: tenant binding, per-tenant services, tool-call wrapper (timing + ToolCall audit + error mapping).

A tool is a plain function ``fn(ts: TenantState, m: MeteredClient) -> Outcome`` run in a worker thread by
:meth:`Runtime.call`. The wrapper measures the *database-reported* (server-side) execution time of every query
the tool ran, records one ``ToolCall`` node afterwards, and turns failures into clear tool errors without ever
exposing Cypher text.

The pieces live in small modules and are re-exported here, so ``from plexus.mcp.runtime import ...`` keeps working:
:mod:`~plexus.mcp.metering` (``MeteredClient``, ``Outcome``), :mod:`~plexus.mcp.tenant` (``TenantState``, scope
resolution) and :mod:`~plexus.mcp.lineage_hook` (``Step`` / ``WROTE`` / ``READ`` attachment). This module keeps what
is process-wide: the database client, the tenant cache and the call wrapper.
"""

from __future__ import annotations

import contextlib
import logging
import os
import threading
import time
from collections.abc import Callable, Mapping
from typing import Any

import anyio
from mcp.server.mcpserver.exceptions import ToolError
from redis.exceptions import RedisError, ResponseError

from plexus.audit import record_tool_call
from plexus.embed import Embedder
from plexus.engram.errors import UnknownReference
from plexus.graph.client import GraphClient
from plexus.graph.queries import QueryError
from plexus.graph.schema import apply_schema
from plexus.graph.tenancy import graph_name
from plexus.mcp import lineage_hook
from plexus.mcp.embedding import CheckedEmbedder, make_embedder
from plexus.mcp.lineage_hook import HOOK_NODE_KEYS, LINK_CHUNK, WROTE_LABELS
from plexus.mcp.metering import AUXILIARY_PREFIX, MeteredClient, Outcome
from plexus.mcp.tenant import TenantState, lineage_class
from plexus.relay import RelayError

__all__ = [
    "AUXILIARY_PREFIX",
    "HOOK_NODE_KEYS",
    "LINK_CHUNK",
    "SCHEMA_RECHECK_S",
    "TENANT_HEADER",
    "WROTE_LABELS",
    "MeteredClient",
    "Outcome",
    "Runtime",
    "TenantState",
    "lineage_class",
]

log = logging.getLogger("plexus.mcp")  # stderr only: stdout is the stdio protocol channel

TENANT_HEADER = "x-plexus-tenant"
SCHEMA_RECHECK_S = 5.0  # how often a tenant's indexes are re-verified (env PLEXUS_SCHEMA_RECHECK_S)


class Runtime:
    """Process-wide state shared by all connections: DB client, embedder, per-tenant states."""

    def __init__(
        self,
        client: GraphClient | None = None,
        embedder: Embedder | None = None,
        stdio_tenant: str | None = None,
        schema_recheck_s: float | None = None,
    ):
        self.client = client or GraphClient()
        self.schema_recheck_s = (
            schema_recheck_s
            if schema_recheck_s is not None
            else float(os.environ.get("PLEXUS_SCHEMA_RECHECK_S") or SCHEMA_RECHECK_S)
        )
        self._agent_locks: dict[tuple[str, str], list] = {}  # (tenant, agent) -> [lock, users]
        self._embedder = (
            embedder
            if embedder is None or isinstance(embedder, CheckedEmbedder)
            else CheckedEmbedder(embedder)
        )
        self.stdio_tenant = stdio_tenant  # set => stdio: one process, one tenant, headers ignored
        self._tenants: dict[str, TenantState] = {}
        self._lock = threading.Lock()

    @property
    def embedder(self) -> Embedder:
        if self._embedder is None:
            self._embedder = make_embedder()
        return self._embedder

    # -- tenant binding and cache --------------------------------------------------------------------------
    def tenant_of(self, headers: Mapping[str, str] | None) -> str:
        """The tenant bound to this connection. Never taken from tool arguments."""
        tenant = self.stdio_tenant or (headers or {}).get(TENANT_HEADER)
        if not tenant:
            raise ToolError("no tenant is bound to this connection (use /mcp/t/<tenant> or --tenant)")
        try:
            graph_name(tenant)
        except ValueError as exc:
            raise ToolError(str(exc)) from None
        return tenant

    def state(self, tenant: str) -> TenantState:
        """TenantState for ``tenant``; the first use applies the schema (idempotent) under a lock.

        The state is not trusted forever: every ``schema_recheck_s`` seconds the graph's indexes are looked at
        again, and if the graph was deleted or replaced under a running server (a demo reset, a restore) the
        schema is re-applied and the cached scope ids are dropped, so the tenant heals itself.
        """
        ts = self._tenants.get(tenant)
        if ts is not None and time.monotonic() - ts.verified_at < self.schema_recheck_s:
            return ts
        with self._lock:
            ts = self._tenants.get(tenant)
            now = time.monotonic()
            if ts is not None and now - ts.verified_at < self.schema_recheck_s:
                return ts
            if ts is not None and self._schema_intact(ts.graph):
                ts.verified_at = now
                return ts
            if ts is not None:
                log.warning("tenant %s: graph or schema is gone; re-applying the schema", tenant)
            graph = graph_name(tenant)
            apply_schema(self.client, graph)
            ts = TenantState(tenant, graph, self.client, self.embedder)
            self._tenants[tenant] = ts
            return ts

    def _schema_intact(self, graph: str) -> bool:
        try:
            return bool(self.client.ro(graph, "view/indexes"))
        except ResponseError:  # "empty key": the graph no longer exists
            return False

    def invalidate(self, tenant: str) -> None:
        """Forget a tenant's cached state; the next :meth:`state` re-applies the schema."""
        with self._lock:
            self._tenants.pop(tenant, None)

    @contextlib.asynccontextmanager
    async def _agent_lock(self, tenant: str, agent_id: str):
        """Serialise the calls of ONE agent (parallel tool calls are normal for Claude Code).

        Step numbers and their ``at`` stamps are then assigned in call-start order and recorded in the same
        order, so ``n`` and ``at`` always agree and an explicit ``step`` is never remapped by a race.
        Different agents never wait for each other.
        """
        key = (tenant, agent_id)
        entry = self._agent_locks.get(key)
        if entry is None:
            entry = self._agent_locks[key] = [anyio.Lock(), 0]
        entry[1] += 1
        try:
            async with entry[0]:
                yield
        finally:
            entry[1] -= 1
            if entry[1] == 0:
                self._agent_locks.pop(key, None)

    # -- the tool wrapper ----------------------------------------------------------------------------------
    async def call(
        self,
        headers: Mapping[str, str] | None,
        tool: str,
        agent_id: str,
        step: int | None,
        fn: Callable[[TenantState, MeteredClient], Outcome],
    ) -> dict[str, Any]:
        """Run ``fn`` for the bound tenant, record a ToolCall, return its data (+ ``tool_call_id``)."""
        if not agent_id or not agent_id.strip():
            raise ToolError("agent_id is required")
        tenant = self.tenant_of(headers)
        try:
            async with self._agent_lock(tenant, agent_id):
                started = time.time_ns() // 1_000_000  # taken inside the lock: n and at agree
                return await anyio.to_thread.run_sync(self._run, tenant, tool, agent_id, step, fn, started)
        except ToolError:
            raise
        except Exception as exc:
            raise _to_tool_error(tool, exc) from None

    def _run(self, tenant, tool, agent_id, step, fn, started: int) -> dict[str, Any]:
        ts, m, out = self._execute(tenant, fn)
        # The Step is opened only after the tool succeeded (a rejected call leaves no Step and registers no
        # agent), but stamped with the time the call started: "what the agent knew at this step" is then the
        # state it acted on, not the state after its own write.
        degraded: list[str] = []
        step_id = self._open_step(ts, agent_id, step, started, degraded)
        data = dict(out.data)
        extra = self._attach(ts, step_id, out, degraded)
        data.update(extra)
        # nodes the Lineage hook created (e.g. the Recall record) are CREATED by this ToolCall too
        created = [
            *out.created,
            *((label, extra[key]) for key, label in HOOK_NODE_KEYS.items() if key in extra),
        ]
        try:
            data["tool_call_id"] = record_tool_call(
                self.client,
                ts.graph,
                tool,
                agent_id,
                step_id,
                m.query_name or tool,
                m.run_time_ms,
                created,
                out.updated,
                step=step,
                wrote=bool(m.writes) or len(created) > len(out.created),
            )
        except Exception:  # the tool's own write already happened; never fail the call over the audit row
            log.exception("audit: could not record ToolCall for %s", tool)
            data["audit_degraded"] = True
        if degraded:
            data["lineage_degraded"] = (
                True  # the write succeeded but its Step / WROTE / READ edges are incomplete
            )
        return data

    def _execute(
        self, tenant: str, fn: Callable[[TenantState, MeteredClient], Outcome]
    ) -> tuple[TenantState, MeteredClient, Outcome]:
        """Run the tool function, once more on a fresh tenant state if the cached one was stale."""
        ts = self.state(tenant)
        for attempt in (0, 1):
            m = MeteredClient(self.client)
            try:
                return ts, m, fn(ts, m)
            except Exception as exc:
                if attempt == 0 and _is_stale_graph(exc):
                    # the graph was replaced under us: nothing was written (the failure is the first read or an
                    # all-or-nothing write), so rebuild the tenant state and run the tool once more
                    log.warning(
                        "tenant %s: stale cached state (%s); retrying once", tenant, type(exc).__name__
                    )
                    self.invalidate(tenant)
                    ts = self.state(tenant)
                    continue
                raise
        raise AssertionError("unreachable")  # pragma: no cover (the second attempt returns or raises)

    # -- Lineage hook (see plexus.mcp.lineage_hook) --------------------------------------------------------
    def _open_step(
        self, ts: TenantState, agent_id: str, step: int | None, at: int, degraded: list[str]
    ) -> str | None:
        """The agent's Step for this call (get-or-create by (agent, n)); ``None`` without Lineage."""
        return lineage_hook.open_step(self.client, ts, agent_id, step, at, degraded)

    def _attach(
        self, ts: TenantState, step_id: str | None, out: Outcome, degraded: list[str]
    ) -> dict[str, Any]:
        """Attach WROTE / READ edges and run the tool's ``after`` hook. Never fails the call."""
        return lineage_hook.attach(self.client, ts, step_id, out, degraded)


def _is_stale_graph(exc: Exception) -> bool:
    """True for the two failures a deleted / replaced tenant graph produces under a cached TenantState."""
    if isinstance(exc, ResponseError):
        return "empty key" in str(exc).lower()
    return isinstance(exc, UnknownReference) and exc.kind == "scope"


def _to_tool_error(tool: str, exc: Exception) -> ToolError:
    """Clear message for caller mistakes; a generic one (details in the server log) for everything else."""
    if isinstance(exc, RelayError | LookupError | ValueError):
        # LookupError/ValueError are raised by the service layer with caller-facing text. KeyError reprs its arg.
        msg = exc.args[0] if isinstance(exc, KeyError) and exc.args else str(exc)
        return ToolError(f"{tool}: {msg}")
    log.exception("tool %s failed", tool)
    if isinstance(exc, RedisError | QueryError):
        return ToolError(f"{tool}: the graph database rejected the request (details are in the server log)")
    return ToolError(f"{tool}: internal error (details are in the server log)")
