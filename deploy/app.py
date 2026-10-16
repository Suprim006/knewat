"""Deploy-only ASGI wrapper: one process serves the View (static), the read-only View API and the public MCP endpoint.

    /healthz, /api/*, /docs   -> plexus.api.view_api (FastAPI, read-only), per-IP rate limited
    /mcp, /mcp/t/<tenant>     -> PublicGuard -> TenantPathMiddleware -> MCP streamable-HTTP app
    everything else           -> the built plexus-view (dist/), with a single-page-app fallback to index.html

Nothing in ``plexus/src`` is modified; this module only composes its public pieces. The MCP DNS-rebinding Host
allow-list is switched off on purpose: it protects loopback services from a browser on the same machine, while
this service is public and reachable under whatever hostname the platform assigns (Render, a custom domain).
"""

from __future__ import annotations

import logging
import os
from pathlib import Path

from mcp.server.transport_security import TransportSecuritySettings
from starlette.exceptions import HTTPException
from starlette.responses import PlainTextResponse
from starlette.staticfiles import StaticFiles

from deploy.guard import (
    ActivityLog,
    ApiRateLimit,
    GuardConfig,
    IdleSweeper,
    PublicGuard,
    TenantDirectory,
    ensure_demo_audit_off,
)
from plexus.api.view_api import create_app as create_view_api
from plexus.graph.client import GraphClient
from plexus.mcp.http import TenantPathMiddleware
from plexus.mcp.runtime import Runtime
from plexus.mcp.server import build_server

log = logging.getLogger("plexus.deploy")

API_PATHS = ("/api/", "/docs", "/openapi.json")


class SpaStaticFiles(StaticFiles):
    """StaticFiles with a client-side-routing fallback: an unknown path without a file extension serves index.html."""

    async def get_response(self, path, scope):
        try:
            response = await super().get_response(path, scope)
        except HTTPException as exc:  # not inside a Starlette app here, so nothing else turns this into a response
            if exc.status_code != 404 or "." in Path(path).name:
                return PlainTextResponse(exc.detail, status_code=exc.status_code)
            response = await super().get_response("index.html", scope)
        if path.startswith("assets/"):  # content-hashed by Vite
            response.headers["cache-control"] = "public, max-age=31536000, immutable"
        elif response.status_code == 200:
            response.headers["cache-control"] = "no-cache"
        return response


def pick_results_file(results_dir: str | Path | None) -> str | None:
    """``latest-all.json`` (P5 combined run) if present, else ``latest.json``."""
    if not results_dir:
        return None
    for name in ("latest-all.json", "latest.json"):
        p = Path(results_dir) / name
        if p.is_file():
            return str(p)
    return None


class PublicApp:
    """The router. Also drives the lifespan of the mounted ASGI apps (the MCP session manager needs it)."""

    def __init__(
        self, api, mcp_guard, static, mcp_lifespan, activity: ActivityLog, directory: TenantDirectory, runtime=None
    ):
        self.runtime = runtime
        self.api = api
        self.mcp = mcp_guard
        self.static = static
        self.mcp_lifespan = mcp_lifespan  # async context manager factory (the MCP Starlette app's lifespan)
        self.activity = activity
        self.directory = directory

    async def __call__(self, scope, receive, send):
        kind = scope["type"]
        if kind == "lifespan":
            return await self._lifespan(receive, send)
        if kind != "http":
            return None
        path = scope["path"]
        if path == "/healthz" or path.startswith(API_PATHS):
            return await self.api(scope, receive, send)
        if path == "/mcp" or path.startswith("/mcp/"):
            return await self.mcp(scope, receive, send)
        return await self.static(scope, receive, send)

    async def _lifespan(self, receive, send):
        await receive()  # lifespan.startup
        try:
            async with self.mcp_lifespan():
                await send({"type": "lifespan.startup.complete"})
                await receive()  # lifespan.shutdown
        except Exception as exc:
            log.exception("startup failed")
            await send({"type": "lifespan.startup.failed", "message": str(exc)})
            return
        await send({"type": "lifespan.shutdown.complete"})


def build_app(
    client: GraphClient | None = None,
    cfg: GuardConfig | None = None,
    static_dir: str | Path | None = None,
    results_dir: str | Path | None = None,
) -> tuple[PublicApp, IdleSweeper]:
    cfg = cfg or GuardConfig.from_env()
    client = client or GraphClient()
    static_dir = Path(static_dir or os.environ.get("PLEXUS_STATIC_DIR", "/app/view"))
    results = pick_results_file(results_dir or os.environ.get("PLEXUS_RESULTS_DIR"))

    os.environ.setdefault("PLEXUS_CORS_ORIGINS", "")  # same origin: no cross-origin caller needs the API
    api = ApiRateLimit(create_view_api(client=client, results_path=results), cfg)

    ensure_demo_audit_off()  # demo* tenants are served in audit mode `off`: read-only, nothing written
    rt = Runtime(client=client)
    mcp_inner = build_server(rt).streamable_http_app(
        streamable_http_path="/mcp",
        transport_security=TransportSecuritySettings(enable_dns_rebinding_protection=False),
        max_request_body_size=cfg.max_body_bytes,
        session_idle_timeout=600.0,
        max_sessions=200,
    )
    mcp = TenantPathMiddleware(mcp_inner, health=client.ping)

    def list_graphs() -> list[str]:
        return list(client.db.list_graphs())

    directory = TenantDirectory(list_graphs, cfg.max_tenants)
    activity = ActivityLog()
    guard = PublicGuard(mcp, cfg, directory, activity)
    static = SpaStaticFiles(directory=str(static_dir), html=True, check_dir=static_dir.is_dir())
    app = PublicApp(
        api, guard, static, lambda: mcp_inner.router.lifespan_context(mcp_inner), activity, directory, runtime=rt
    )
    sweeper = IdleSweeper(activity, list_graphs, client.delete_graph, idle_s=cfg.idle_hours * 3600)
    return app, sweeper
