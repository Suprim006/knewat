"""FalkorDB clients (sync + asyncio) that only run named queries from the :class:`QueryLibrary`.

``ro`` uses ``GRAPH.RO_QUERY`` and refuses ``mode: rw`` queries; ``rw`` uses ``GRAPH.QUERY``.
Callers never pass Cypher text, only a query name and parameters.
"""

from __future__ import annotations

import os
from collections.abc import Iterable, Sequence
from typing import Any

from falkordb import FalkorDB, Graph
from falkordb.asyncio import FalkorDB as AsyncFalkorDB
from redis.asyncio import BlockingConnectionPool
from redis.exceptions import ResponseError

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


def _check_mode(rq: RenderedQuery, read_only: bool) -> None:
    if read_only and rq.mode != "ro":
        raise ReadOnlyViolation(f"query '{rq.name}' is mode 'rw'; ro() refuses it")


def _is_tolerated(exc: Exception, tolerate: Sequence[str]) -> bool:
    msg = str(exc).lower()
    return any(t.lower() in msg for t in tolerate)


class GraphClient:
    """Sync client. Connection: args, else ``FALKORDB_HOST/PORT/PASSWORD`` env, else localhost:6379."""

    def __init__(
        self,
        host: str | None = None,
        port: int | None = None,
        password: str | None = None,
        library: QueryLibrary | None = None,
    ):
        self.host, self.port, password = _env_conn(host, port, password)
        self.db = FalkorDB(host=self.host, port=self.port, password=password)
        self.library = library or QueryLibrary()

    def graph(self, name: str) -> Graph:
        return self.db.select_graph(name)

    def _run(self, graph: str, rq: RenderedQuery, statement: str, read_only: bool, timeout_ms) -> Rows:
        g = self.graph(graph)
        call = g.ro_query if read_only else g.query
        return _to_rows(call(statement, rq.params or None, timeout_ms))

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

    def ping(self) -> bool:
        return bool(self.db.connection.ping())


class AsyncGraphClient:
    """asyncio client backed by a ``BlockingConnectionPool`` (callers wait for a free connection)."""

    def __init__(
        self,
        host: str | None = None,
        port: int | None = None,
        password: str | None = None,
        library: QueryLibrary | None = None,
        max_connections: int = 32,
    ):
        self.host, self.port, password = _env_conn(host, port, password)
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
        result = await self.graph(graph).query(rq.cypher, rq.params or None, timeout_ms)
        return _to_rows(result)

    async def ro(
        self, graph: str, query_name: str, params: dict | None = None, timeout_ms: int | None = None
    ) -> Rows:
        rq = self.library.render(query_name, params)
        _check_mode(rq, read_only=True)
        result = await self.graph(graph).ro_query(rq.cypher, rq.params or None, timeout_ms)
        return _to_rows(result)

    async def delete_graph(self, name: str) -> None:
        try:
            await self.graph(name).delete()
        except ResponseError as exc:
            if "empty key" not in str(exc).lower() and "not exist" not in str(exc).lower():
                raise

    async def aclose(self) -> None:
        await self.pool.disconnect()
