"""MCP tests for activation-based forgetting (P7-K): READ provenance, recall rows, memory tools."""

from __future__ import annotations

import json

from mcp import Client
from plexus.graph.tenancy import graph_name


async def ok(c: Client, tool: str, /, **args) -> dict:
    res = await c.call_tool(tool, args)
    assert not res.is_error, res.content[0].text
    return json.loads(res.content[0].text)


async def err(c: Client, tool: str, /, **args) -> str:
    res = await c.call_tool(tool, args)
    assert res.is_error, res.content[0].text
    return res.content[0].text


def rows(client, tenant, cypher: str, **params):
    return client.graph(graph_name(tenant)).ro_query(cypher, params or None).result_set


# ---------------------------------------------------------------- slice 1: READ provenance
async def test_recall_makes_read_via_recall_and_a_decision_makes_a_use(server, client, tenant):
    async with Client(server) as c:
        f = await ok(c, "assert_fact", agent_id="a", subject="API", predicate="version", value="v1")
        await ok(c, "create_tasks", agent_id="a", tasks=[{"title": "ship", "id": "t1"}])
        r = await ok(c, "recall", agent_id="b", query="API version", step=1)
        assert f["fact_id"] in [x["fact_id"] for x in r["facts"]]
        got = rows(
            client,
            tenant,
            "MATCH (s:Step {agent_id:'b', n:1})-[r:READ]->(:Fact {id:$f}) RETURN r.via, r.at, s.at",
            f=f["fact_id"],
        )
        assert got and got[0][0] == "recall" and got[0][1] >= got[0][2]
        await ok(
            c,
            "record_decision",
            agent_id="b",
            task_id="t1",
            text="ship v1",
            based_on_fact_ids=[f["fact_id"]],
            step=2,
        )
        used = rows(
            client,
            tenant,
            "MATCH (:Step {agent_id:'b', n:2})-[r:READ]->(:Fact {id:$f}) RETURN r.via, r.at",
            f=f["fact_id"],
        )
        assert used and used[0][0] == "use" and used[0][1] > 0
