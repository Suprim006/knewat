"""Seed a small Acme-style tenant through the real MCP tools (in-process) for live smoke tests of knewat-view.

Usage (from the repo root; needs the knewat venv and a FalkorDB, no LLM, hash embeddings only):

    FALKORDB_PORT=6387 knewat/.venv/Scripts/python.exe knewat-view/scripts/seed_live.py smoke [--pause 0.4]

With ``--pause`` the calls are spread out in time, so a View open on /flow shows them arriving over SSE.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys

from mcp import Client
from knewat.embed import HashEmbedder
from knewat.graph.client import GraphClient
from knewat.mcp.runtime import Runtime
from knewat.mcp.server import build_server


async def main(tenant: str, pause: float) -> None:
    rt = Runtime(client=GraphClient(), embedder=HashEmbedder(), stdio_tenant=tenant)
    server = build_server(rt)
    out: dict[str, object] = {}

    async with Client(server) as c:

        async def call(name: str, **args):
            res = await c.call_tool(name, args)
            if res.is_error:
                raise RuntimeError(f"{name}: {res.content[0].text}")
            await asyncio.sleep(pause)
            return json.loads(res.content[0].text)

        await call("register_agent", agent_id="planner", role="planner")
        await call("register_agent", agent_id="researcher", role="researcher")
        await call("register_agent", agent_id="builder", role="builder")
        ses = await call("start_session", agent_id="researcher", agent_role="researcher")
        src = await call("add_source", agent_id="researcher", title="API brief", uri="https://example.test/brief")
        guide = await call("add_source", agent_id="researcher", title="API guide v2", uri="https://example.test/guide")
        await call(
            "remember_episode",
            agent_id="researcher",
            session_id=ses["session_id"],
            text="Read the brief: notes API with auth.",
        )
        v1 = await call(
            "assert_fact",
            agent_id="researcher",
            subject="Acme API",
            predicate="api_version",
            value="v1",
            source_id=src["source_id"],
        )
        jwt = await call(
            "assert_fact",
            agent_id="researcher",
            subject="Acme API",
            predicate="auth",
            value="JWT",
            source_id=src["source_id"],
        )
        await call("create_tasks", agent_id="planner", tasks=[{"id": "t1", "title": "build the API"}])
        rec = await call("recall", agent_id="builder", query="Acme API version", k=3)
        v2 = await call(
            "assert_fact",
            agent_id="researcher",
            subject="Acme API",
            predicate="api_version",
            value="v2",
            source_id=guide["source_id"],
            supersede=True,
        )
        key = await call(
            "assert_fact", agent_id="builder", subject="Acme API", predicate="auth", value="API key"
        )
        dec = await call(
            "record_decision",
            agent_id="planner",
            task_id="t1",
            text="use API v2 with JWT",
            based_on_fact_ids=[v2["fact_id"], jwt["fact_id"]],
        )
        await call(
            "handoff",
            agent_id="planner",
            to_agent="builder",
            task_id="t1",
            note="build on v2",
            fact_ids=[v2["fact_id"]],
        )
        out.update(
            tenant=tenant,
            decision=dec["decision_id"],
            fact_v1=v1["fact_id"],
            fact_v2=v2["fact_id"],
            fact_key=key["fact_id"],
            recall=rec.get("recall_id"),
        )
    print(json.dumps(out))


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("tenant")
    p.add_argument("--pause", type=float, default=0.0)
    a = p.parse_args()
    sys.exit(asyncio.run(main(a.tenant, a.pause)))
