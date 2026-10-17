"""Plexus MCP server: ``plexus-mcp --transport stdio --tenant acme`` or ``--transport http --port 8765``."""

from __future__ import annotations

import argparse
import logging
import os
import sys
import threading
from typing import Any

from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.exceptions import ToolError
from mcp.server.transport_security import TransportSecuritySettings
from mcp_types import ListToolsResult
from pydantic import ValidationError

from plexus.mcp.http import TenantPathMiddleware
from plexus.mcp.lineage_tools import register_lineage
from plexus.mcp.memory_tools import register_memory
from plexus.mcp.runtime import Runtime
from plexus.mcp.staleness_tools import register_staleness
from plexus.mcp.tools import register_engram_relay
from plexus.mcp.tools_dedup import register_dedup
from plexus.mcp.tools_impact import register_impact
from plexus.mcp.tools_relations import register_relations
from plexus.mcp.toolsets import FULL, TOOLSET_HEADER, ToolsetError, default_toolset, module_of, tool_names

INSTRUCTIONS = (
    "Plexus is a shared graph memory and coordination layer for a team of agents. "
    "Call start_session first. Use recall before acting and assert_fact to store durable knowledge; use "
    "create_tasks / claim_next_task / complete_task to coordinate, handoff to pass work on, and record_decision "
    "(with the fact ids it relies on) so decisions can be explained later. Every tool takes your agent_id."
)


MAX_ERRORS_SHOWN = 4


def validation_message(tool: str, exc: ValidationError) -> str:
    """One short line for an LLM: ``recall: k: Input should be greater than or equal to 1; query: Field required``.

    No pydantic model names, no documentation URLs and never the rejected value (it can be 100 kB).
    """
    parts: list[str] = []
    for err in exc.errors(include_url=False, include_context=False, include_input=False):
        field = ".".join(str(p) for p in err["loc"])
        msg = str(err["msg"]).removeprefix("Value error, ").strip()
        parts.append(f"{field}: {msg}" if field else msg)
    shown = "; ".join(parts[:MAX_ERRORS_SHOWN])
    more = len(parts) - MAX_ERRORS_SHOWN
    return f"{tool}: {shown}" + (f" (+{more} more)" if more > 0 else "")


_GUARD_KEYS = frozenset({"title", "maxLength", "minLength", "maxItems"})
_BOUND_KEYS = frozenset({"maximum", "minimum", "exclusiveMaximum", "exclusiveMinimum"})
_NULL = {"type": "null"}
GUARD_BOUND = (
    10_000  # |bound| at or above this is a resource guard (20 000 chars, 2**31-1, OPEN), not meaning
)


def compact_schema(s: Any) -> Any:
    """The published form of a tool's input schema (P12 token fix): what a model needs to call the tool, without
    the boilerplate pydantic emits for every field. Dropped: ``title``; ``maxLength`` / ``minLength`` /
    ``maxItems``; numeric bounds of 10 000 or more and ``minimum: 0``; ``default: null``. ``anyOf [X, null]``
    becomes ``X`` (the field is optional either way: it is not in ``required``). Kept: every description,
    type, enum, ``required``, ``$defs`` / ``$ref``, small bounds (``k`` 1..50, ``hops`` 0..2) and non-null
    defaults. The server still validates every argument against the full pydantic model, so a dropped bound
    is still enforced (an over-long value gets the usual one-line error)."""
    if isinstance(s, list):
        return [compact_schema(x) for x in s]
    if not isinstance(s, dict):
        return s
    out: dict[str, Any] = {}
    for k, v in s.items():
        if k in _GUARD_KEYS:
            continue
        if (
            k in _BOUND_KEYS
            and isinstance(v, int | float)
            and (abs(v) >= GUARD_BOUND or (k == "minimum" and v == 0))
        ):
            continue
        if k in ("properties", "$defs") and isinstance(v, dict):
            out[k] = {
                name: compact_schema(sub) for name, sub in v.items()
            }  # keys are names, not schema keywords
        else:
            out[k] = compact_schema(v)
    alts = out.get("anyOf")
    if isinstance(alts, list) and len(alts) == 2 and _NULL in alts:
        other = next(x for x in alts if x != _NULL)
        del out["anyOf"]
        out = {**other, **out}
    if "default" in out and out["default"] is None:
        del out["default"]
    return out


def schema_mode() -> str:
    """``PLEXUS_MCP_SCHEMA=full`` publishes pydantic's verbose schemas (the pre-P12 tool list); default compact."""
    return "full" if os.environ.get("PLEXUS_MCP_SCHEMA", "").strip().lower() == "full" else "compact"


class PlexusServer(MCPServer):
    """MCPServer that reports argument-validation failures as one short line instead of a pydantic dump,
    publishes compact tool schemas (see :func:`compact_schema`) and scopes the published tools to the
    session's toolset (see :mod:`plexus.mcp.toolsets`; default ``full`` = every tool)."""

    def __init__(self, *args: Any, toolset: str = FULL, **kwargs: Any):
        super().__init__(*args, **kwargs)
        self.toolset = toolset  # process default (canonical): stdio, and HTTP sessions that pick none

    def session_toolset(self, headers: Any) -> str:
        """The toolset of the request: the session's (``x-plexus-toolset``, set and pinned by
        :class:`~plexus.mcp.http.TenantPathMiddleware`), else the process default."""
        raw = (headers or {}).get(TOOLSET_HEADER) if headers is not None else None
        return raw if raw else self.toolset

    async def list_tools(self):
        tools = await super().list_tools()
        if schema_mode() == "full":
            return tools
        # outputSchema is pydantic's generic {"type": "object", "additionalProperties": true} for every tool
        return [t.model_copy(update={"input_schema": compact_schema(t.input_schema), "output_schema": None})
                for t in tools]  # fmt: skip

    async def _handle_list_tools(self, ctx, params):  # the SDK's tools/list handler (bound at __init__)
        tools = await self.list_tools()
        ts = self.session_toolset(getattr(ctx.request, "headers", None))
        if ts != FULL:
            names = tool_names(ts)
            tools = [t for t in tools if t.name in names]
        return ListToolsResult(tools=tools)

    async def call_tool(self, name, arguments, context=None):
        ts = self.session_toolset(context.headers if context is not None else None)
        if ts != FULL and name not in tool_names(ts) and (mod := module_of(name)) is not None:
            raise ToolError(
                f"{name}: not in this session's toolset '{ts}' (it is in module '{mod}'); "
                f"connect with a toolset that includes '{mod}' (e.g. toolset=full)"
            )
        try:
            return await super().call_tool(name, arguments, context)
        except ToolError as exc:
            if isinstance(exc.__cause__, ValidationError):
                raise ToolError(validation_message(name, exc.__cause__)) from exc.__cause__
            raise


def build_server(rt: Runtime, toolset: str | None = None) -> PlexusServer:
    """An MCPServer with every available tool registered (Lineage tools only if ``plexus.lineage`` exists).

    ``toolset`` (default: env ``PLEXUS_TOOLSET``, else ``full``) is the process default of the published tool
    list; every tool is still registered, a session sees only its toolset's."""
    mcp = PlexusServer(
        "plexus", instructions=INSTRUCTIONS, log_level="WARNING", toolset=default_toolset(toolset)
    )
    register_engram_relay(mcp, rt)
    register_lineage(mcp, rt)
    register_staleness(mcp, rt)
    register_memory(mcp, rt)
    register_impact(mcp, rt)
    register_dedup(mcp, rt)
    register_relations(mcp, rt)
    return mcp


DEFAULT_ALLOWED_HOSTS = "127.0.0.1:*,localhost:*,[::1]:*,127.0.0.1,localhost,plexus-mcp:*,plexus-mcp"


def build_http_app(rt: Runtime, allowed_hosts: list[str] | None = None, toolset: str | None = None):
    """ASGI app: tenant-binding middleware around the SDK's streamable-HTTP app (``/mcp``, ``/mcp/t/<tenant>``).

    DNS-rebinding protection stays on: only Host headers in ``allowed_hosts`` (env ``PLEXUS_MCP_ALLOWED_HOSTS``,
    comma-separated, ``host:*`` allows any port) are accepted.
    """
    hosts = allowed_hosts or [
        h.strip()
        for h in os.environ.get("PLEXUS_MCP_ALLOWED_HOSTS", DEFAULT_ALLOWED_HOSTS).split(",")
        if h.strip()
    ]
    security = TransportSecuritySettings(
        enable_dns_rebinding_protection=True,
        allowed_hosts=hosts,
        allowed_origins=[f"http://{h}" for h in hosts],
    )
    mcp = build_server(rt, toolset)
    return TenantPathMiddleware(
        mcp.streamable_http_app(streamable_http_path="/mcp", transport_security=security),
        health=lambda: rt.client.ping(),
    )


def _prewarm(rt: Runtime) -> None:
    """Load the embedding model in the background so the first tool call is not slow."""
    threading.Thread(target=lambda: rt.embedder.embed(["warm up"]), daemon=True, name="embed-warmup").start()


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(prog="plexus-mcp", description=__doc__)
    ap.add_argument("--transport", choices=["stdio", "http"], default="stdio")
    ap.add_argument(
        "--tenant", help="stdio: the tenant this process serves (default: env PLEXUS_TENANT or 'default')"
    )
    ap.add_argument("--host", default=os.environ.get("PLEXUS_MCP_HOST", "127.0.0.1"))
    ap.add_argument("--port", type=int, default=int(os.environ.get("PLEXUS_MCP_PORT", "8765")))
    ap.add_argument(
        "--toolset",
        default=None,
        help="tools to publish: 'full' (default), 'core' (engram,relay,lineage) or a comma-separated list of "
        "modules: engram, relay, lineage, staleness, forgetting, relations, dedup (default: env PLEXUS_TOOLSET); "
        "HTTP clients can pick per session with ?toolset= or X-Plexus-Toolset",
    )
    a = ap.parse_args(argv)
    try:
        toolset = default_toolset(a.toolset)
    except ToolsetError as exc:
        ap.error(str(exc))
    logging.basicConfig(
        stream=sys.stderr, level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s"
    )

    if a.transport == "stdio":
        tenant = a.tenant or os.environ.get("PLEXUS_TENANT") or "default"
        rt = Runtime(stdio_tenant=tenant)
        rt.tenant_of(None)  # fail fast on an invalid tenant name
        _prewarm(rt)
        build_server(rt, toolset).run("stdio")
    else:
        import uvicorn

        rt = Runtime()
        _prewarm(rt)
        uvicorn.run(build_http_app(rt, toolset=toolset), host=a.host, port=a.port, log_level="info")


if __name__ == "__main__":
    main()
