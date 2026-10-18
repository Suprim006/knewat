"""Deploy-only ASGI wrapper: one process serves the View (static) and the View API (including the Cypher console).

    /healthz, /api/*, /docs   -> plexus.api.view_api (FastAPI), per-IP rate limited; POST (Cypher) has its own bucket
    everything else           -> the built plexus-view (dist/), with a single-page-app fallback to index.html

The MCP server is deliberately not mounted: this deployment only shows the seeded demo data until MCP is stable
(D-016). Nothing in ``plexus/src`` is modified; this module only composes its public pieces.
"""

from __future__ import annotations

import logging
import os
from pathlib import Path

from starlette.exceptions import HTTPException
from starlette.responses import PlainTextResponse
from starlette.staticfiles import StaticFiles

from deploy.guard import ApiRateLimit, GuardConfig
from plexus.api.view_api import create_app as create_view_api
from plexus.graph.client import GraphClient

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
    """The router: the API under ``/api``, ``/healthz``, ``/docs``; the static View for everything else."""

    def __init__(self, api, static):
        self.api = api
        self.static = static

    async def __call__(self, scope, receive, send):
        kind = scope["type"]
        if kind == "lifespan":
            return await self._lifespan(receive, send)
        if kind != "http":
            return None
        path = scope["path"]
        if path == "/healthz" or path.startswith(API_PATHS):
            return await self.api(scope, receive, send)
        return await self.static(scope, receive, send)

    @staticmethod
    async def _lifespan(receive, send):
        await receive()  # lifespan.startup
        await send({"type": "lifespan.startup.complete"})
        await receive()  # lifespan.shutdown
        await send({"type": "lifespan.shutdown.complete"})


def build_app(
    client: GraphClient | None = None,
    cfg: GuardConfig | None = None,
    static_dir: str | Path | None = None,
    results_dir: str | Path | None = None,
) -> PublicApp:
    cfg = cfg or GuardConfig.from_env()
    client = client or GraphClient()
    static_dir = Path(static_dir or os.environ.get("PLEXUS_STATIC_DIR", "/app/view"))
    results = pick_results_file(results_dir or os.environ.get("PLEXUS_RESULTS_DIR"))

    os.environ.setdefault("PLEXUS_CORS_ORIGINS", "")  # same origin: no cross-origin caller needs the API
    api = ApiRateLimit(create_view_api(client=client, results_path=results), cfg)
    static = SpaStaticFiles(directory=str(static_dir), html=True, check_dir=static_dir.is_dir())
    return PublicApp(api, static)
