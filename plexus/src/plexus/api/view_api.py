"""Read-only View API. ``uv run plexus-api`` serves http://127.0.0.1:8080 (env PLEXUS_API_HOST / PLEXUS_API_PORT).

Every database access goes through :class:`ReadOnlyClient`, which only exposes ``ro()`` (``GRAPH.RO_QUERY``) and the
graph list; there is no write path in this package. The routes live in ``routes_*.py`` (one :class:`APIRouter`
factory per group, all sharing one :class:`~plexus.api.context.ApiContext`); :func:`create_app` wires them up.
"""

from __future__ import annotations

import logging
import os

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from plexus.api import routes_core, routes_flow, routes_graph, routes_lineage, routes_staleness
from plexus.api.context import MAX_STREAMS, ApiContext, ReadOnlyClient, StreamGate
from plexus.api.routes_core import INVENTORY_EDGE_TYPES, INVENTORY_LABELS
from plexus.common import OPEN
from plexus.graph.client import GraphClient

# Names tests import from here.
__all__ = [
    "INVENTORY_EDGE_TYPES",
    "INVENTORY_LABELS",
    "OPEN",
    "ReadOnlyClient",
    "StreamGate",
    "create_app",
    "main",
]

DEFAULT_ORIGINS = "http://localhost:5180,http://127.0.0.1:5180,http://localhost:5173,http://127.0.0.1:5173"


def _cors_origins() -> list[str]:
    raw = os.environ.get("PLEXUS_CORS_ORIGINS", DEFAULT_ORIGINS)
    return [o.strip() for o in raw.split(",") if o.strip()]


def create_app(
    client: GraphClient | None = None, results_path: str | None = None, max_streams: int | None = None
) -> FastAPI:
    ro_client = ReadOnlyClient(client or GraphClient())
    gate = StreamGate(
        max_streams
        if max_streams is not None
        else int(os.environ.get("PLEXUS_API_MAX_STREAMS") or MAX_STREAMS)
    )
    ctx = ApiContext(ro_client, gate, results_path)
    app = FastAPI(title="Plexus View API", version="0.1.0", description="Read-only API for plexus-view.")
    app.add_middleware(
        CORSMiddleware,
        allow_origins=_cors_origins(),
        allow_methods=["GET"],
        allow_headers=["*"],
    )
    app.state.ro = ro_client
    app.state.streams = gate
    app.state.flow_events = ctx.flow_events
    # The order is the order of the paths in the OpenAPI document.
    for routes in (routes_core, routes_graph, routes_flow, routes_lineage, routes_staleness):
        app.include_router(routes.router(ctx))
    return app


def main() -> None:
    import uvicorn

    logging.basicConfig(level=logging.INFO)
    uvicorn.run(
        create_app(),
        host=os.environ.get("PLEXUS_API_HOST", "127.0.0.1"),
        port=int(os.environ.get("PLEXUS_API_PORT", "8080")),
        log_level="info",
    )


if __name__ == "__main__":
    main()
