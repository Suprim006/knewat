"""Fixtures for the demo tests: the scripted Acme scenario is run once per module on a throwaway tenant."""

from __future__ import annotations

import asyncio
import uuid

import pytest

from plexus.demo.scenario import FaultScript
from plexus.demo.scripted import run_scripted
from plexus.embed import HashEmbedder
from plexus.graph.tenancy import graph_name

FAST_LEASE_MS = 300


@pytest.fixture(scope="module")
def demo_tenants(client):
    """Factory for unique demo tenants; their graphs are dropped when the module is done."""
    made: list[str] = []

    def make() -> str:
        t = f"demot_{uuid.uuid4().hex[:10]}"
        made.append(t)
        return t

    yield make
    for t in made:
        client.delete_graph(graph_name(t))


@pytest.fixture(scope="module")
def scripted_run(client, demo_tenants):
    """(tenant, world) after one full scripted run with a short builder lease."""
    tenant = demo_tenants()
    world = asyncio.run(
        run_scripted(
            tenant, client, embedder=HashEmbedder(), faults=FaultScript(builder_lease_ms=FAST_LEASE_MS)
        )
    )
    return tenant, world


def rows(client, tenant: str, cypher: str, params: dict | None = None) -> list[list]:
    """Ad-hoc read of a demo tenant graph (tests only)."""
    return client.graph(graph_name(tenant)).ro_query(cypher, params).result_set
