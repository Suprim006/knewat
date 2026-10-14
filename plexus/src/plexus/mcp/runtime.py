"""MCP runtime: tenant binding, per-tenant services, tool-call wrapper (timing + ToolCall audit + error mapping).

A tool is a plain function ``fn(ts: TenantState, m: MeteredClient) -> Outcome`` run in a worker thread by
:meth:`Runtime.call`. The wrapper measures the *database-reported* (server-side) execution time of every query
the tool ran, records one ``ToolCall`` node afterwards, and turns failures into clear tool errors without ever
exposing Cypher text.
"""

from __future__ import annotations

import importlib
import logging
import re
import threading
import time
from collections.abc import Callable, Iterable, Mapping, Sequence
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
WROTE_LABELS = frozenset(
    {"Decision", "Handoff", "Task"}
)  # nodes a Step can WROTE besides Facts (see link_step)
LINK_CHUNK = 200  # ids per link_step call (lineage.MAX_LINK_IDS)
_UUID = re.compile(r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}")


def lineage_class() -> Any:
    """``plexus.lineage.Lineage`` if it is importable and can record steps, else ``None``."""
    try:
        cls = getattr(importlib.import_module("plexus.lineage"), "Lineage", None)
    except ImportError:
        return None
    return cls if cls is not None and hasattr(cls, "record_step") else None


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
    step_id: str | None = None  # ignored: the runtime sets it from Lineage.record_step
    # Lineage attachment (ignored when plexus.lineage is not installed):
    read_ids: Sequence[str] = ()  # Facts the call looked at -> (Step)-[:READ]->(Fact)
    assert_result: dict[str, Any] | None = None  # Engram.assert_fact result -> Lineage.link_assert_result
    after: Callable[[Any, str | None], dict[str, Any] | None] | None = None
    """``after(lineage, step_id)`` runs once the Step exists; the dict it returns is merged into the result."""


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

    def lineage(self, m: MeteredClient) -> Any:
        """A ``Lineage`` for this tenant, or ``None`` when ``plexus.lineage`` is not installed."""
        cls = lineage_class()
        return None if cls is None else cls(m, self.graph)

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
        started = time.time_ns() // 1_000_000
        out = fn(ts, m)
        # The Step is opened only after the tool succeeded (a rejected call leaves no Step and registers no
        # agent), but stamped with the time the call started: "what the agent knew at this step" is then the
        # state it acted on, not the state after its own write.
        step_id = self._open_step(ts, agent_id, step, started)
        data = dict(out.data)
        data.update(self._attach(ts, step_id, out))
        try:
            data["tool_call_id"] = record_tool_call(
                self.client,
                ts.graph,
                tool,
                agent_id,
                step_id,
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

    # -- Lineage hook -------------------------------------------------------------------------------------
    def _open_step(self, ts: TenantState, agent_id: str, step: int | None, at: int) -> str | None:
        """The agent's Step for this call (get-or-create by (agent, n)); ``None`` without Lineage.

        An explicit ``step`` is respected (the same ``n`` always maps to the same Step). Without one the next
        number is used (previous + 1), so every call is attributable. A ``step`` behind the agent's latest one
        cannot be recorded (the NEXT chain is append-only): the call then takes the next number instead.
        """
        lin = ts.lineage(MeteredClient(self.client))
        if lin is None:
            return None
        try:
            try:
                return lin.record_step(agent_id, step, at)
            except ValueError:  # StepOrderError
                if step is None:
                    raise
                log.warning("step %s is behind %s's latest step; using the next number", step, agent_id)
                return lin.record_step(agent_id, None, at)
        except Exception:
            log.exception("lineage: could not record a Step for %s", agent_id)
            return None

    def _attach(self, ts: TenantState, step_id: str | None, out: Outcome) -> dict[str, Any]:
        """Attach WROTE / READ edges and run the tool's ``after`` hook. Never fails the call."""
        extra: dict[str, Any] = {}
        if step_id is None:
            return extra
        lin = ts.lineage(MeteredClient(self.client))
        if lin is None:
            return extra
        wrote = _ids(i for label, i in (*out.created, *out.updated) if label in WROTE_LABELS)
        read = _ids(out.read_ids)
        try:
            if out.assert_result is not None:
                lin.link_assert_result(step_id, out.assert_result)
            for i in range(0, max(len(wrote), len(read)), LINK_CHUNK):
                lin.link_step(step_id, wrote_ids=wrote[i : i + LINK_CHUNK], read_ids=read[i : i + LINK_CHUNK])
        except Exception:
            log.exception("lineage: could not link step %s", step_id)
        if out.after is not None:
            try:
                extra = out.after(lin, step_id) or {}
            except Exception:
                log.exception("lineage: after-hook failed for step %s", step_id)
        return extra


def _ids(values: Iterable[str]) -> list[str]:
    return list(dict.fromkeys(v for v in values if v))


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
