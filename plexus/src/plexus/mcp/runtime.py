"""MCP runtime: tenant binding, per-tenant services, tool-call wrapper (timing + ToolCall audit + error mapping).

A tool is a plain function ``fn(ts: TenantState, m: MeteredClient) -> Outcome`` run in a worker thread by
:meth:`Runtime.call`. The wrapper measures the *database-reported* (server-side) execution time of every query
the tool ran, records one ``ToolCall`` node afterwards, and turns failures into clear tool errors without ever
exposing Cypher text.
"""

from __future__ import annotations

import logging
import re
import threading
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any

import anyio
from mcp.server.mcpserver.exceptions import ToolError
from redis.exceptions import RedisError

from plexus.audit import record_tool_call
from plexus.audit.recorder import Ref
from plexus.embed import Embedder
from plexus.engram import Engram
from plexus.graph.client import GraphClient, Rows
from plexus.graph.queries import QueryError
from plexus.graph.schema import apply_schema
from plexus.graph.tenancy import graph_name
from plexus.mcp.embedding import CheckedEmbedder, make_embedder
from plexus.relay import Relay, RelayError

log = logging.getLogger("plexus.mcp")  # stderr only: stdout is the stdio protocol channel

TENANT_HEADER = "x-plexus-tenant"
_UUID = re.compile(r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}")


class MeteredClient:
    """Per-call proxy over :class:`GraphClient` that sums the server-side ``run_time_ms`` of every query."""

    def __init__(self, inner: GraphClient):
        self._inner = inner
        self.run_time_ms = 0.0
        self.queries: list[str] = []
        self.writes: list[str] = []

    def _note(self, name: str, rows: Rows | None, write: bool) -> None:
        self.queries.append(name)
        if write:
            self.writes.append(name)
        if rows is not None:
            self.run_time_ms += rows.run_time_ms

    def ro(self, graph: str, name: str, params: dict | None = None, timeout_ms: int | None = None) -> Rows:
        rows = self._inner.ro(graph, name, params, timeout_ms)
        self._note(name, rows, False)
        return rows

    def rw(self, graph: str, name: str, params: dict | None = None, timeout_ms: int | None = None) -> Rows:
        rows = self._inner.rw(graph, name, params, timeout_ms)
        self._note(name, rows, True)
        return rows

    def __getattr__(self, item: str) -> Any:
        return getattr(self._inner, item)

    @property
    def query_name(self) -> str:
        """The write query if there was one (the last), else the last read query."""
        if self.writes:
            return self.writes[-1]
        return self.queries[-1] if self.queries else ""


@dataclass
class Outcome:
    """What a tool function returns: the JSON-able result plus the nodes it touched (for the audit edges)."""

    data: dict[str, Any]
    created: Sequence[Ref] = ()
    updated: Sequence[Ref] = ()
    step_id: str | None = None


@dataclass
class TenantState:
    """Services for one tenant graph (schema applied once)."""

    tenant: str
    graph: str
    client: GraphClient
    embedder: Embedder
    _scopes: dict[str, str] = field(default_factory=dict)
    _lock: threading.Lock = field(default_factory=threading.Lock)

    def engram(self, m: MeteredClient) -> Engram:
        return Engram(m, self.graph, self.embedder)  # type: ignore[arg-type]

    def relay(self, m: MeteredClient) -> Relay:
        return Relay(m, self.graph)  # type: ignore[arg-type]

    def scope_id(self, spec: str, m: MeteredClient) -> str:
        """Resolve a scope spec to a Scope id: ``global`` | ``project:<name>`` | ``user:<name>`` | a scope id.

        Named scopes are created on first use (idempotent MERGE); ``project:`` and ``user:`` scopes inherit
        ``global``. A raw id is passed through (the service layer rejects an unknown one).
        """
        spec = (spec or "global").strip()
        if _UUID.fullmatch(spec):
            return spec
        with self._lock:
            hit = self._scopes.get(spec)
        if hit:
            return hit
        kind, _, name = spec.partition(":")
        eng = self.engram(m)
        if spec == "global":
            sid = eng.create_scope("global", "global")
        elif kind in ("project", "user") and name.strip():
            parent = self.scope_id("global", m)
            sid = eng.create_scope(kind, name.strip(), inherits=[parent])
        else:
            raise ToolError(
                f"invalid scope '{spec}': use 'global', 'project:<name>', 'user:<name>' or a scope id"
            )
        with self._lock:
            self._scopes[spec] = sid
        return sid


class Runtime:
    """Process-wide state shared by all connections: DB client, embedder, per-tenant states."""

    def __init__(
        self,
        client: GraphClient | None = None,
        embedder: Embedder | None = None,
        stdio_tenant: str | None = None,
    ):
        self.client = client or GraphClient()
        self._embedder = (
            embedder
            if embedder is None or isinstance(embedder, CheckedEmbedder)
            else CheckedEmbedder(embedder)
        )
        self.stdio_tenant = stdio_tenant  # set => stdio: one process, one tenant, headers ignored
        self._tenants: dict[str, TenantState] = {}
        self._lock = threading.Lock()
        self.lineage: Any = None  # set by the lineage hook when plexus.lineage exists

    @property
    def embedder(self) -> Embedder:
        if self._embedder is None:
            self._embedder = make_embedder()
        return self._embedder

    # -- tenant binding ----------------------------------------------------------------------------------
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
        """TenantState for ``tenant``; the first use applies the schema (idempotent) under a lock."""
        ts = self._tenants.get(tenant)
        if ts is not None:
            return ts
        with self._lock:
            ts = self._tenants.get(tenant)
            if ts is None:
                graph = graph_name(tenant)
                apply_schema(self.client, graph)
                ts = TenantState(tenant, graph, self.client, self.embedder)
                self._tenants[tenant] = ts
            return ts

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
            return await anyio.to_thread.run_sync(self._run, tenant, tool, agent_id, step, fn)
        except ToolError:
            raise
        except Exception as exc:
            raise _to_tool_error(tool, exc) from None

    def _run(self, tenant, tool, agent_id, step, fn) -> dict[str, Any]:
        ts = self.state(tenant)
        m = MeteredClient(self.client)
        out = fn(ts, m)
        data = dict(out.data)
        try:
            data["tool_call_id"] = record_tool_call(
                self.client,
                ts.graph,
                tool,
                agent_id,
                out.step_id,
                m.query_name or tool,
                m.run_time_ms,
                out.created,
                out.updated,
                step=step,
                wrote=bool(m.writes),
            )
        except Exception:  # the tool's own write already happened; never fail the call over the audit row
            log.exception("audit: could not record ToolCall for %s", tool)
        return data


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
