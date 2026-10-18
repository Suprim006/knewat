"""``POST /api/{tenant}/cypher``: the Cypher console. The one place the View API runs caller-supplied Cypher text.

Defence in depth, outermost first (the first two live in ``deploy/guard.py``, see D-016):
1. per-IP rate limit and a body-size cap for this route;
2. a text check here: length, no ``LOAD`` (FalkorDB's LOAD CSV reads files and URLs), and ``CALL`` only to an
   allow-list of read procedures. Comments and string literals are skipped, so a keyword hidden in either is not
   a bypass and a keyword inside a string is not a false alarm;
3. ``GRAPH.RO_QUERY``: the server itself refuses every write, whatever the text says;
4. the server's ``QUERY_MEM_CAPACITY`` and a ``TIMEOUT_MS`` timeout we pass with every query, and at most ``MAX_ROWS`` rows
   leave this process.
"""

from __future__ import annotations

import json
import logging
import re
from typing import Any

from fastapi import APIRouter, HTTPException
from fastapi.concurrency import run_in_threadpool
from redis.exceptions import RedisError, ResponseError
from redis.exceptions import TimeoutError as RedisTimeout

from plexus.api import models as M
from plexus.api.context import ApiContext, is_missing_graph

log = logging.getLogger("plexus.api.cypher")

MAX_QUERY_CHARS = 4000
MAX_PARAMS_BYTES = 8000
MAX_ROWS = 500
TIMEOUT_MS = 3000  # below the redis client's 5 s socket timeout: the server's answer must win that race
VECTOR_MIN_DIMS = 64  # a numeric list this long inside a property is shown as "<vector, N dims>"

# Procedures a console query may CALL (lower case). ``algo.`` is a prefix: the graph algorithms are read-only.
CALL_ALLOWED = frozenset(
    {
        "db.labels",
        "db.relationshiptypes",
        "db.propertykeys",
        "db.indexes",
        "db.constraints",
        "db.idx.fulltext.querynodes",
        "db.idx.fulltext.queryrelationships",
        "db.idx.vector.querynodes",
        "db.idx.vector.queryrelationships",
        "dbms.procedures",
        "dbms.functions",
    }
)
CALL_ALLOWED_PREFIXES = ("algo.",)

_LOAD = re.compile(r"\bLOAD\b", re.IGNORECASE)
_CALL = re.compile(r"\bCALL\s+([A-Za-z_][\w.]*)", re.IGNORECASE)


def code_only(text: str) -> str:
    """``text`` with comments removed and string / backtick contents blanked (quotes kept)."""
    out: list[str] = []
    i, n = 0, len(text)
    while i < n:
        c = text[i]
        if c in "'\"`":
            out.append(c)
            i += 1
            while i < n and text[i] != c:
                i += 2 if text[i] == "\\" and c != "`" else 1
            out.append(c)
            i += 1
        elif text.startswith("//", i):
            while i < n and text[i] != "\n":
                i += 1
        elif text.startswith("/*", i):
            end = text.find("*/", i + 2)
            i = n if end < 0 else end + 2
            out.append(" ")
        else:
            out.append(c)
            i += 1
    return "".join(out)


def check_text(text: str) -> None:
    """Raise ``HTTPException`` (400 / 413) if the console must not run this text."""
    if len(text) > MAX_QUERY_CHARS:
        raise HTTPException(413, f"query too long ({len(text)} characters; the limit is {MAX_QUERY_CHARS})")
    code = code_only(text)
    if _LOAD.search(code):
        raise HTTPException(400, "LOAD is not available in the console")
    for name in _CALL.findall(code):
        low = name.lower()
        if low not in CALL_ALLOWED and not low.startswith(CALL_ALLOWED_PREFIXES):
            raise HTTPException(400, f"CALL {name} is not available in the console (read procedures only)")


def jsonable(v: Any, in_props: bool = False) -> Any:
    """A FalkorDB result value as plain JSON: nodes, edges and paths become objects with a ``_type`` key."""
    if v is None or isinstance(v, (bool, int, str)):
        return v
    if isinstance(v, float):
        return v if v == v and v not in (float("inf"), float("-inf")) else str(v)
    if hasattr(v, "labels") and hasattr(v, "properties"):  # falkordb.Node
        return {
            "_type": "node",
            "id": v.id,
            "labels": list(v.labels or []),
            "properties": _props(v.properties),
        }
    if hasattr(v, "relation") and hasattr(v, "properties"):  # falkordb.Edge
        return {
            "_type": "edge",
            "id": v.id,
            "type": v.relation,
            "src": _endpoint(v.src_node),
            "dst": _endpoint(v.dest_node),
            "properties": _props(v.properties),
        }
    if hasattr(v, "nodes") and hasattr(v, "edges") and callable(v.nodes):  # falkordb.Path
        return {
            "_type": "path",
            "nodes": [jsonable(x) for x in v.nodes()],
            "edges": [jsonable(x) for x in v.edges()],
        }
    if isinstance(v, dict):
        return {str(k): jsonable(x, in_props) for k, x in v.items()}
    if isinstance(v, (list, tuple)):
        if in_props and len(v) >= VECTOR_MIN_DIMS and all(isinstance(x, (int, float)) for x in v):
            return f"<vector, {len(v)} dims>"
        return [jsonable(x, in_props) for x in v]
    return str(v)


def _endpoint(n: Any) -> Any:
    return n if isinstance(n, int) else getattr(n, "id", None)


def _props(p: dict | None) -> dict[str, Any]:
    return {str(k): jsonable(x, True) for k, x in (p or {}).items()}


def _run(ctx: ApiContext, tenant: str, req: M.CypherRequest) -> M.CypherResponse:
    graph = ctx.graph_of(tenant)
    try:
        rows = ctx.ro.cypher(graph, req.query, req.params, TIMEOUT_MS)
    except ResponseError as exc:
        msg = str(exc)
        low = msg.lower()
        if is_missing_graph(exc):
            raise HTTPException(404, f"unknown tenant '{tenant}'") from None
        if "timed out" in low:
            raise HTTPException(
                408, f"query timed out after {TIMEOUT_MS // 1000} s; narrow it or add a LIMIT"
            ) from None
        if "read-only queries" in low:
            raise HTTPException(
                400, "the console is read-only: CREATE, SET, DELETE, MERGE and REMOVE are rejected"
            ) from None
        raise HTTPException(400, msg[:500]) from None
    except RedisTimeout:  # the socket gave up before the server's own timeout reply arrived
        raise HTTPException(
            408, f"query timed out after {TIMEOUT_MS // 1000} s; narrow it or add a LIMIT"
        ) from None
    except (RedisError, OSError):
        log.exception("database unreachable")
        raise HTTPException(503, "graph database unavailable") from None
    shown = rows[:MAX_ROWS]
    return M.CypherResponse(
        tenant=tenant,
        columns=list(rows.header),
        rows=[[jsonable(r.get(c)) for c in rows.header] for r in shown],
        row_count=len(shown),
        truncated=len(rows) > MAX_ROWS,
        run_time_ms=rows.run_time_ms,
    )


def router(ctx: ApiContext) -> APIRouter:
    r = APIRouter()

    @r.post("/api/{tenant}/cypher", response_model=M.CypherResponse)
    async def cypher(tenant: str, req: M.CypherRequest):
        check_text(req.query)
        if req.params is not None and len(json.dumps(req.params)) > MAX_PARAMS_BYTES:
            raise HTTPException(413, f"params too large (the limit is {MAX_PARAMS_BYTES} bytes of JSON)")
        return await run_in_threadpool(_run, ctx, tenant, req)

    return r
