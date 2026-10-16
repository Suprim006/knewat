"""Plexus MCP server: ``plexus-mcp --transport stdio --tenant acme`` or ``--transport http --port 8765``."""

from __future__ import annotations

import argparse
import logging
import os
import sys
import threading

from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.exceptions import ToolError
from mcp.server.transport_security import TransportSecuritySettings
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


class PlexusServer(MCPServer):
    """MCPServer that reports argument-validation failures as one short line instead of a pydantic dump."""

    async def call_tool(self, name, arguments, context=None):
        try:
            return await super().call_tool(name, arguments, context)
        except ToolError as exc:
            if isinstance(exc.__cause__, ValidationError):
                raise ToolError(validation_message(name, exc.__cause__)) from exc.__cause__
            raise


def build_server(rt: Runtime) -> MCPServer:
    """An MCPServer with every available tool registered (Lineage tools only if ``plexus.lineage`` exists)."""
    mcp = PlexusServer("plexus", instructions=INSTRUCTIONS, log_level="WARNING")
    register_engram_relay(mcp, rt)
    register_lineage(mcp, rt)
    register_staleness(mcp, rt)
    register_memory(mcp, rt)
    register_impact(mcp, rt)
    register_dedup(mcp, rt)
    register_relations(mcp, rt)
    return mcp


DEFAULT_ALLOWED_HOSTS = "127.0.0.1:*,localhost:*,[::1]:*,127.0.0.1,localhost,plexus-mcp:*,plexus-mcp"


def build_http_app(rt: Runtime, allowed_hosts: list[str] | None = None):
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
    mcp = build_server(rt)
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
    a = ap.parse_args(argv)
    logging.basicConfig(
        stream=sys.stderr, level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s"
    )

    if a.transport == "stdio":
        tenant = a.tenant or os.environ.get("PLEXUS_TENANT") or "default"
        rt = Runtime(stdio_tenant=tenant)
        rt.tenant_of(None)  # fail fast on an invalid tenant name
        _prewarm(rt)
        build_server(rt).run("stdio")
    else:
        import uvicorn

        rt = Runtime()
        _prewarm(rt)
        uvicorn.run(build_http_app(rt), host=a.host, port=a.port, log_level="info")


if __name__ == "__main__":
    main()
