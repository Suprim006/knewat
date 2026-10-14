"""FalkorDB clients (sync + asyncio) that only run named queries from the :class:`QueryLibrary`.

``ro`` uses ``GRAPH.RO_QUERY`` and refuses ``mode: rw`` queries; ``rw`` uses ``GRAPH.QUERY``.
Callers never pass Cypher text, only a query name and parameters.
"""

from __future__ import annotations

import asyncio
import os
import time
from collections.abc import Callable, Iterable, Sequence
from typing import Any

from falkordb import FalkorDB, Graph
from falkordb.asyncio import FalkorDB as AsyncFalkorDB
from redis import BlockingConnectionPool as SyncBlockingConnectionPool
from redis.asyncio import BlockingConnectionPool
from redis.exceptions import BusyLoadingError, ResponseError

from plexus.graph.queries import QueryLibrary, ReadOnlyViolation, RenderedQuery

_STAT_ATTRS = (
    "nodes_created",
    "nodes_deleted",
    "relationships_created",
    "relationships_deleted",
    "properties_set",
    "properties_removed",
    "labels_added",
    "labels_removed",
    "indices_created",
    "indices_deleted",
)


class Rows(list):
    """A ``list[dict]`` (one dict per row, keyed by the result header) plus execution metadata."""

    header: list[str]
    run_time_ms: float
    stats: dict[str, int]
    cached: bool

    def __init__(self, rows: Iterable[dict[str, Any]], header: list[str], run_time_ms: float, stats, cached):
        super().__init__(rows)
        self.header = header
        self.run_time_ms = run_time_ms
        self.stats = stats
        self.cached = cached


def _to_rows(result) -> Rows:
    header = [h[1] if isinstance(h, (list, tuple)) else h for h in (result.header or [])]
    rows = [dict(zip(header, row, strict=False)) for row in result.result_set]
    stats = {a: v for a in _STAT_ATTRS if (v := getattr(result, a, 0))}
    return Rows(rows, header, float(result.run_time_ms), stats, bool(result.cached_execution))


def _env_conn(host: str | None, port: int | None, password: str | None) -> tuple[str, int, str | None]:
    host = host or os.environ.get("FALKORDB_HOST") or "localhost"
    port = int(port if port is not None else os.environ.get("FALKORDB_PORT") or 6379)
    password = password if password is not None else (os.environ.get("FALKORDB_PASSWORD") or None)
    return host, port, password or None


DEFAULT_POOL = 256  # sync pool size (env PLEXUS_DB_POOL); callers beyond it wait, they do not fail
DEFAULT_POOL_TIMEOUT_S = 30.0  # how long a caller waits for a free connection (env PLEXUS_DB_POOL_TIMEOUT)
DEFAULT_LOADING_WAIT_S = 60.0  # how long to retry while Redis loads the AOF (env PLEXUS_DB_LOADING_WAIT_S)
_LOADING_POLL_S = 0.25


def _env_float(name: str, default: float) -> float:
    raw = os.environ.get(name)
    try:
        return float(raw) if raw else default
    except ValueError:
        return default


def _retry_loading(fn: Callable[[], Any], wait_s: float) -> Any:
    """Run ``fn``; while Redis answers ``-LOADING`` retry for at most ``wait_s`` seconds, then re-raise."""
    deadline = time.monotonic() + wait_s
    while True:
        try:
            return fn()
        except BusyLoadingError:
            if time.monotonic() >= deadline:
                raise
            time.sleep(_LOADING_POLL_S)


async def _aretry_loading(fn: Callable[[], Any], wait_s: float) -> Any:
    deadline = time.monotonic() + wait_s
    while True:
        try:
            return await fn()
        except BusyLoadingError:
            if time.monotonic() >= deadline:
                raise
            await asyncio.sleep(_LOADING_POLL_S)


def _check_mode(rq: RenderedQuery, read_only: bool) -> None:
    if read_only and rq.mode != "ro":
        raise ReadOnlyViolation(f"query '{rq.name}' is mode 'rw'; ro() refuses it")


def _is_tolerated(exc: Exception, tolerate: Sequence[str]) -> bool:
    msg = str(exc).lower()
    return any(t.lower() in msg for t in tolerate)


class GraphClient:
    """Sync client. Connection: args, else ``FALKORDB_HOST/PORT/PASSWORD`` env, else localhost:6379.

    Backed by a ``BlockingConnectionPool`` of ``max_connections`` (env ``PLEXUS_DB_POOL``, default 256):
    a caller that finds every connection busy waits up to ``pool_timeout`` seconds instead of failing.
    While Redis is still loading its dataset (``-LOADING``) connect and queries are retried for up to
    ``loading_wait_s``.
    """

    def __init__(
        self,
        host: str | None = None,
        port: int | None = None,
        password: str | None = None,
        library: QueryLibrary | None = None,
        max_connections: int | None = None,
        pool_timeout: float | None = None,
        loading_wait_s: float | None = None,
    ):
        self.host, self.port, password = _env_conn(host, port, password)
        if max_connections is None:
            max_connections = int(_env_float("PLEXUS_DB_POOL", DEFAULT_POOL))
        if pool_timeout is None:
            pool_timeout = _env_float("PLEXUS_DB_POOL_TIMEOUT", DEFAULT_POOL_TIMEOUT_S)
        self.loading_wait_s = (
            _env_float("PLEXUS_DB_LOADING_WAIT_S", DEFAULT_LOADING_WAIT_S)
            if loading_wait_s is None
            else loading_wait_s
        )
        self.pool = SyncBlockingConnectionPool(
            host=self.host,
            port=self.port,
            password=password,
            max_connections=max_connections,
            timeout=pool_timeout,
            decode_responses=True,
            protocol=2,  # what FalkorDB(...) itself uses; RESP3 changes reply shapes (e.g. MODULE LIST)
        )
        try:
            self.db = _retry_loading(lambda: FalkorDB(connection_pool=self.pool), self.loading_wait_s)
        except BaseException:
            self.pool.disconnect()
            raise
        self.library = library or QueryLibrary()

    def graph(self, name: str) -> Graph:
        return self.db.select_graph(name)

    def _run(self, graph: str, rq: RenderedQuery, statement: str, read_only: bool, timeout_ms) -> Rows:
        g = self.graph(graph)
        call = g.ro_query if read_only else g.query
        return _to_rows(
            _retry_loading(lambda: call(statement, rq.params or None, timeout_ms), self.loading_wait_s)
        )

    def rw(
        self, graph: str, query_name: str, params: dict | None = None, timeout_ms: int | None = None
    ) -> Rows:
        rq = self.library.render(query_name, params)
        return self._run(graph, rq, rq.cypher, False, timeout_ms)

    def ro(
        self, graph: str, query_name: str, params: dict | None = None, timeout_ms: int | None = None
    ) -> Rows:
        rq = self.library.render(query_name, params)
        _check_mode(rq, read_only=True)
        return self._run(graph, rq, rq.cypher, True, timeout_ms)

    def rw_script(
        self,
        graph: str,
        query_name: str,
        params: dict | None = None,
        timeout_ms: int | None = None,
        tolerate: Sequence[str] = (),
    ) -> list[Rows | None]:
        """Run every statement of a (possibly multi-statement) query in order.

        A ``ResponseError`` whose message contains one of ``tolerate`` (case-insensitive) yields ``None`` for
        that statement; any other error propagates. Statements are not atomic together.
        """
        rq = self.library.render(query_name, params)
        out: list[Rows | None] = []
        for stmt in rq.statements:
            try:
                out.append(self._run(graph, rq, stmt, rq.mode == "ro", timeout_ms))
            except ResponseError as exc:
                if not _is_tolerated(exc, tolerate):
                    raise
                out.append(None)
        return out

    def delete_graph(self, name: str) -> None:
        """Drop a graph; a graph that does not exist is not an error."""
        try:
            self.graph(name).delete()
        except ResponseError as exc:
            if "empty key" not in str(exc).lower() and "not exist" not in str(exc).lower():
                raise

    def close(self) -> None:
        self.db.connection.close()
        self.pool.disconnect()

    def ping(self) -> bool:
        return bool(_retry_loading(self.db.connection.ping, self.loading_wait_s))


class AsyncGraphClient:
    """asyncio client backed by a ``BlockingConnectionPool`` (callers wait for a free connection)."""

    def __init__(
        self,
        host: str | None = None,
        port: int | None = None,
        password: str | None = None,
        library: QueryLibrary | None = None,
        max_connections: int = 32,
        loading_wait_s: float | None = None,
    ):
        self.host, self.port, password = _env_conn(host, port, password)
        self.loading_wait_s = (
            _env_float("PLEXUS_DB_LOADING_WAIT_S", DEFAULT_LOADING_WAIT_S)
            if loading_wait_s is None
            else loading_wait_s
        )
        self.pool = BlockingConnectionPool(
            host=self.host,
            port=self.port,
            password=password,
            max_connections=max_connections,
            decode_responses=True,
        )
        self.db = AsyncFalkorDB(connection_pool=self.pool)
        self.library = library or QueryLibrary()

    def graph(self, name: str):
        return self.db.select_graph(name)

    async def rw(
        self, graph: str, query_name: str, params: dict | None = None, timeout_ms: int | None = None
    ) -> Rows:
        rq = self.library.render(query_name, params)
        g = self.graph(graph)
        result = await _aretry_loading(
            lambda: g.query(rq.cypher, rq.params or None, timeout_ms), self.loading_wait_s
        )
        return _to_rows(result)

    async def ro(
        self, graph: str, query_name: str, params: dict | None = None, timeout_ms: int | None = None
    ) -> Rows:
        rq = self.library.render(query_name, params)
        _check_mode(rq, read_only=True)
        g = self.graph(graph)
        result = await _aretry_loading(
            lambda: g.ro_query(rq.cypher, rq.params or None, timeout_ms), self.loading_wait_s
        )
        return _to_rows(result)

    async def delete_graph(self, name: str) -> None:
        try:
            await self.graph(name).delete()
        except ResponseError as exc:
            if "empty key" not in str(exc).lower() and "not exist" not in str(exc).lower():
                raise

    async def aclose(self) -> None:
        await self.pool.disconnect()
