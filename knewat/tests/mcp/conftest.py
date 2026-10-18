"""MCP fixtures: a Runtime on a throwaway tenant (graph ``knewat_t_<tenant>`` dropped in teardown)."""

from __future__ import annotations

import uuid

import pytest

from knewat.embed import HashEmbedder
from knewat.graph.tenancy import graph_name
from knewat.mcp.runtime import Runtime
from knewat.mcp.server import build_server


@pytest.fixture
def new_tenant(client):
    """Factory for unique tenant ids; every graph it handed out is dropped in teardown."""
    made: list[str] = []

    def make() -> str:
        t = f"mcpt_{uuid.uuid4().hex[:12]}"
        made.append(t)
        return t

    yield make
    for t in made:
        client.delete_graph(graph_name(t))


@pytest.fixture
def tenant(new_tenant) -> str:
    return new_tenant()


@pytest.fixture
def runtime(client, tenant) -> Runtime:
    return Runtime(client=client, embedder=HashEmbedder(), stdio_tenant=tenant)


@pytest.fixture
def server(runtime):
    return build_server(runtime)
