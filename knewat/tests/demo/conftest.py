"""Fixtures for the demo tests: the scripted Acme scenario is run once per module on a throwaway tenant."""

from __future__ import annotations

import asyncio
import os
import uuid

import pytest

from plexus.demo.scenario import FaultScript
from plexus.demo.scripted import run_scripted
from plexus.embed import HashEmbedder
from plexus.graph.tenancy import graph_name

FAST_LEASE_MS = 300
STALE_PREFIX = graph_name("demot_")


_SWEPT = False


def sweep_stale_graphs(client) -> None:
    """Drop ``plexus_t_demot_*`` graphs left behind by a run that was killed before its teardown.

    Assumes the test DB is private to this run (one container per agent, see scripts/agent_db.sh); set
    ``PLEXUS_TEST_KEEP_STALE=1`` to skip when sharing one. Only this module's own prefix is touched.
    """
    if os.environ.get("PLEXUS_TEST_KEEP_STALE"):
        return
    for name in client.db.list_graphs():
        if name.startswith(STALE_PREFIX):
            client.delete_graph(name)


def drop_graphs(client, tenants: list[str]) -> None:
    """Drop every tenant graph even if one delete fails; the first failure is re-raised at the end."""
    first: Exception | None = None
    for t in tenants:
        try:
            client.delete_graph(graph_name(t))
        except Exception as exc:  # noqa: BLE001 - keep dropping the rest
            first = first or exc
    if first is not None:
        raise first


def _sweep_once(client) -> None:
    global _SWEPT
    if not _SWEPT:
        _SWEPT = True
        sweep_stale_graphs(client)


@pytest.fixture(scope="module")
def demo_tenants(client):
    """Factory for unique demo tenants; their graphs are dropped when the module is done.

    The first use in a session also sweeps ``plexus_t_demot_*`` graphs leaked by a killed earlier run.
    """
    _sweep_once(client)
    made: list[str] = []

    def make() -> str:
        t = f"demot_{uuid.uuid4().hex[:10]}"
        made.append(t)
        return t

    yield make
    drop_graphs(client, made)


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
