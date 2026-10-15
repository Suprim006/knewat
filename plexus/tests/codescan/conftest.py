# ruff: noqa: E501
"""Fixtures for the client-side tests: a real Plexus MCP server on a loopback port, and temp git repositories."""

from __future__ import annotations

import socket
import subprocess
import threading
import time
import uuid
from pathlib import Path

import pytest

from plexus.embed import HashEmbedder
from plexus.graph.tenancy import graph_name
from plexus.mcp.runtime import Runtime
from plexus.mcp.server import build_http_app


@pytest.fixture
def new_tenant(client):
    """Factory for unique tenant ids; every graph it handed out is dropped in teardown."""
    made: list[str] = []

    def make() -> str:
        t = f"cs_{uuid.uuid4().hex[:12]}"
        made.append(t)
        return t

    yield make
    for t in made:
        client.delete_graph(graph_name(t))


class Live:
    def __init__(self, url: str, tenant: str, client):
        self.url, self.tenant, self.client = url, tenant, client
        self.graph = graph_name(tenant)

    def rows(self, cypher: str, **params):
        return self.client.graph(self.graph).ro_query(cypher, params or None).result_set


@pytest.fixture
def live(client, new_tenant):
    """The real HTTP app (uvicorn in a thread) bound to a throw-away tenant; yields ``Live``."""
    import uvicorn

    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]
    app = build_http_app(Runtime(client=client, embedder=HashEmbedder()))
    server = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=port, log_level="warning"))
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    deadline = time.monotonic() + 15
    while not server.started:
        if time.monotonic() > deadline:
            raise RuntimeError("test server did not start")
        time.sleep(0.02)
    try:
        yield Live(f"http://127.0.0.1:{port}", new_tenant(), client)
    finally:
        server.should_exit = True
        thread.join(timeout=10)


def git(repo: Path, *args: str) -> str:
    out = subprocess.run(["git", "-C", str(repo), *args], capture_output=True, text=True, check=True)  # noqa: S603,S607
    return out.stdout.strip()


@pytest.fixture
def repo(tmp_path) -> Path:
    r = tmp_path / "repo"
    r.mkdir()
    git(r, "init", "-q")
    git(r, "config", "user.email", "t@example.com")
    git(r, "config", "user.name", "T")
    git(r, "config", "core.autocrlf", "false")
    return r


def commit_all(repo: Path, message: str) -> str:
    git(repo, "add", "-A")
    git(repo, "commit", "-q", "-m", message)
    return git(repo, "rev-parse", "HEAD")
