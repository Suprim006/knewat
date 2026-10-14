"""Plexus MCP server: ``plexus-mcp --transport stdio --tenant acme`` or ``--transport http --port 8765``."""

from __future__ import annotations

import argparse
import logging
import os
import sys
import threading

from mcp.server.mcpserver import MCPServer
from mcp.server.transport_security import TransportSecuritySettings

from plexus.mcp.http import TenantPathMiddleware
from plexus.mcp.lineage_tools import register_lineage
from plexus.mcp.runtime import Runtime
from plexus.mcp.tools import register_engram_relay

INSTRUCTIONS = (
    "Plexus is a shared graph memory and coordination layer for a team of agents. "
    "Call start_session first. Use recall before acting and assert_fact to store durable knowledge; use "
    "create_tasks / claim_next_task / complete_task to coordinate, handoff to pass work on, and record_decision "
    "(with the fact ids it relies on) so decisions can be explained later. Every tool takes your agent_id."
)


def build_server(rt: Runtime) -> MCPServer:
    """An MCPServer with every available tool registered (Lineage tools only if ``plexus.lineage`` exists)."""
    mcp = MCPServer("plexus", instructions=INSTRUCTIONS, log_level="WARNING")
    register_engram_relay(mcp, rt)
    register_lineage(mcp, rt)
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
        mcp.streamable_http_app(streamable_http_path="/mcp", transport_security=security)
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
