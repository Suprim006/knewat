"""Shared plumbing of the View API: the read-only database handle, the stream gate and :class:`ApiContext`.

The route modules (``routes_*.py``) get one :class:`ApiContext` each and never touch the database any other way.
"""

from __future__ import annotations

import logging
import math
import threading
import time
from collections.abc import Callable
from typing import Any

from fastapi import HTTPException
from redis.exceptions import RedisError, ResponseError

from plexus.activation import Activation, Settings
from plexus.api import models as M
from plexus.graph.client import GraphClient, Rows
from plexus.graph.queries import QueryLibrary
from plexus.graph.tenancy import TENANT_PREFIX, graph_name

log = logging.getLogger("plexus.api")

FLOW_LIMIT_MAX = 1000
MAX_STREAMS = 20  # concurrent /stream connections (env PLEXUS_API_MAX_STREAMS); more get 429
FLOW_CACHE_TTL_S = 0.15  # subscribers polling within this window share one view/flow read
FLOW_CACHE_MAX = 256


class ReadOnlyClient:
    """The only database handle the API gets: named read queries and the graph list."""

    def __init__(self, inner: GraphClient):
        self._inner = inner
        self.library: QueryLibrary = inner.library

    def ro(self, graph: str, name: str, params: dict | None = None) -> Rows:
        return self._inner.ro(graph, name, params)

    def cypher(self, graph: str, text: str, params: dict | None, timeout_ms: int) -> Rows:
        """Caller-supplied Cypher, read-only (``GRAPH.RO_QUERY``). Used by the Cypher console route and nothing else."""
        return self._inner.ro_text(graph, text, params, timeout_ms)

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


class Slot:
    """One acquired stream slot; ``release`` is idempotent (generator end and response end both call it)."""

    def __init__(self, gate: StreamGate):
        self._gate = gate
        self._done = False

    def release(self) -> None:
        if not self._done:
            self._done = True
            self._gate.release()


def clean(props: dict[str, Any]) -> dict[str, Any]:
    return {k: v for k, v in props.items() if v is not None}


def activation_props(fa: Any) -> dict[str, Any]:
    """The View-facing activation fields of a ``FactActivation`` (``activation`` is omitted when it is -inf)."""
    out: dict[str, Any] = {"protected": bool(fa.protected)}
    if math.isfinite(fa.activation):
        out["activation"] = float(fa.activation)
    return out


def event(row: dict[str, Any]) -> M.ToolCallEvent:
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


def is_missing_graph(exc: ResponseError) -> bool:
    """A FalkorDB error that means the tenant's graph does not exist."""
    msg = str(exc).lower()
    return "empty key" in msg or "not exist" in msg


class ApiContext:
    """What every route needs: the read-only client, the stream gate and the guarded query helpers."""

    def __init__(self, ro: ReadOnlyClient, gate: StreamGate, results_path: str | None):
        self.ro = ro
        self.gate = gate
        self.results_path = results_path
        self._flow_cache: dict[tuple[str, int], tuple[float, list[M.ToolCallEvent]]] = {}
        self._flow_locks: dict[tuple[str, int], threading.Lock] = {}

    def graph_of(self, tenant: str) -> str:
        try:
            return graph_name(tenant)
        except ValueError:
            raise HTTPException(404, f"unknown tenant '{tenant}'") from None

    def guarded(self, tenant: str, what: str, fn: Callable[[], Any]) -> Any:
        """Run a database read, mapping the failures to HTTP errors (404 unknown tenant, 502, 503)."""
        try:
            return fn()
        except ResponseError as exc:
            if is_missing_graph(exc):
                raise HTTPException(404, f"unknown tenant '{tenant}'") from None
            log.exception("%s failed", what)
            raise HTTPException(502, "the graph database rejected the query") from None
        except (RedisError, OSError):
            log.exception("database unreachable")
            raise HTTPException(503, "graph database unavailable") from None

    def run(self, tenant: str, query: str, params: dict | None = None) -> Rows:
        g = self.graph_of(tenant)
        return self.guarded(tenant, f"query {query}", lambda: self.ro.ro(g, query, params))

    def activations(self, tenant: str, fact_ids: list[str]) -> dict[str, Any]:
        """Activation + protection of these facts (200 ids per query); ``{}`` when forgetting is off.

        A failure of this optional overlay is logged and the fields are left out: the graph itself is still served.
        """
        settings = Settings.from_env()
        if not settings.forgetting or not fact_ids:
            return {}
        try:
            return Activation(self.ro, self.graph_of(tenant), settings).compute(fact_ids)  # type: ignore[arg-type]
        except (ResponseError, RedisError, OSError):
            log.exception("activation overlay failed")
            return {}

    def run_flow(self, tenant: str, after: int) -> list[M.ToolCallEvent]:
        return [event(r) for r in self.run(tenant, "view/flow", {"after": after, "limit": FLOW_LIMIT_MAX})]

    def flow_events(self, tenant: str, after: int) -> list[M.ToolCallEvent]:
        """``run_flow`` shared between subscribers: polls of the same (tenant, after) within the TTL cost one read."""
        key = (tenant, after)
        hit = self._flow_cache.get(key)
        if hit is not None and time.monotonic() - hit[0] < FLOW_CACHE_TTL_S:
            return hit[1]
        with self._flow_locks.setdefault(key, threading.Lock()):
            hit = self._flow_cache.get(key)
            if hit is not None and time.monotonic() - hit[0] < FLOW_CACHE_TTL_S:
                return hit[1]
            events = self.run_flow(tenant, after)
            now = time.monotonic()
            self._flow_cache[key] = (now, events)
            if len(self._flow_cache) > FLOW_CACHE_MAX:  # drop expired entries (and their locks)
                for k in [k for k, (t, _) in self._flow_cache.items() if now - t >= FLOW_CACHE_TTL_S]:
                    self._flow_cache.pop(k, None)
                    self._flow_locks.pop(k, None)
            return events
