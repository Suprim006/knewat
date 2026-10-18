"""View API fixtures: a tenant seeded through the real MCP tools, and a TestClient on the API."""

from __future__ import annotations

import json
import os
import uuid

import pytest
from fastapi.testclient import TestClient

from mcp import Client
from plexus.api.view_api import create_app
from plexus.embed import HashEmbedder
from plexus.graph.tenancy import graph_name
from plexus.mcp.runtime import Runtime
from plexus.mcp.server import build_server

STALE_PREFIX = graph_name("apit_")


_SWEPT = False


def sweep_stale_graphs(client) -> None:
    """Drop ``plexus_t_apit_*`` graphs left behind by a run that was killed before its teardown.

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


async def seed(client, tenant: str) -> dict:
    """Run a small realistic session through the MCP tools (so ToolCalls, edges and facts exist)."""
    rt = Runtime(client=client, embedder=HashEmbedder(), stdio_tenant=tenant)
    out: dict = {}
    async with Client(build_server(rt)) as c:

        async def call(name, **args):
            r = await c.call_tool(name, args)
            assert not r.is_error, r.content
            return json.loads(r.content[0].text)

        s = await call("start_session", agent_id="planner", agent_role="planner")
        await call("remember_episode", agent_id="planner", session_id=s["session_id"], text="kickoff", step=1)
        f1 = await call(
            "assert_fact", agent_id="planner", subject="API", predicate="version", value="v1", step=2
        )
        f2 = await call(
            "assert_fact", agent_id="planner", subject="API", predicate="version", value="v2", step=3
        )
        await call("recall", agent_id="planner", query="API version")
        await call("register_agent", agent_id="builder", role="builder")
        await call("create_tasks", agent_id="planner", tasks=[{"id": "t1", "title": "build"}])
        claim = await call("claim_next_task", agent_id="builder")
        d = await call(
            "record_decision",
            agent_id="builder",
            task_id="t1",
            text="use v2",
            based_on_fact_ids=[f2["fact_id"]],
        )
        out.update(
            session=s["session_id"],
            f1=f1["fact_id"],
            f2=f2["fact_id"],
            claim=claim["task"],
            decision=d["decision_id"],
        )
    return out


@pytest.fixture
def new_tenant(client):
    """Factory for unique tenant ids; every graph it handed out is dropped in teardown.

    The first use in a session also sweeps ``plexus_t_apit_*`` graphs leaked by a killed earlier run.
    """
    _sweep_once(client)
    made: list[str] = []

    def make() -> str:
        t = f"apit_{uuid.uuid4().hex[:12]}"
        made.append(t)
        return t

    yield make
    drop_graphs(client, made)


@pytest.fixture
async def seeded(client, new_tenant):
    tenant = new_tenant()
    info = await seed(client, tenant)
    info["tenant"] = tenant
    return info


@pytest.fixture
def api(client):
    with TestClient(create_app(client=client)) as tc:
        yield tc
