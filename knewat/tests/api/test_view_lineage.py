"""View API on a graph written by the real MCP tools with Lineage wired in."""

from __future__ import annotations

import json

import pytest

from knewat.api import models as M
from knewat.embed import HashEmbedder
from knewat.mcp.runtime import Runtime
from knewat.mcp.server import build_server
from mcp import Client


@pytest.fixture
async def lineage_world(client, new_tenant):
    tenant = new_tenant()
    rt = Runtime(client=client, embedder=HashEmbedder(), stdio_tenant=tenant)
    w: dict = {"tenant": tenant}
    async with Client(build_server(rt)) as c:

        async def call(name, **args):
            r = await c.call_tool(name, args)
            assert not r.is_error, r.content
            return json.loads(r.content[0].text)

        w["source"] = (
            await call("add_source", agent_id="researcher", title="Design doc", uri="https://example.test/d")
        )["source_id"]
        w["fact"] = (
            await call(
                "assert_fact",
                agent_id="researcher",
                subject="Acme API",
                predicate="database",
                value="PostgreSQL 16",
                source_id=w["source"],
            )
        )["fact_id"]
        await call("register_agent", agent_id="planner", role="planner")
        await call("create_tasks", agent_id="planner", tasks=[{"id": "t1", "title": "build"}])
        rec = await call("recall", agent_id="planner", query="Acme API database", k=3)
        w["recall"] = rec["recall_id"]
        w["decision"] = (
            await call(
                "record_decision",
                agent_id="planner",
                task_id="t1",
                text="use PostgreSQL",
                based_on_fact_ids=[w["fact"]],
            )
        )["decision_id"]
    return w


def test_flow_carries_step_id_and_step_n(api, lineage_world):
    flow = M.FlowResponse(**api.get(f"/api/{lineage_world['tenant']}/flow").json())
    assert [e.tool for e in flow.events] == [
        "add_source",
        "assert_fact",
        "register_agent",
        "create_tasks",
        "recall",
        "record_decision",
    ]
    assert all(e.step_id and e.step_n for e in flow.events)
    by_tool = {e.tool: e for e in flow.events}
    assert [by_tool[t].step_n for t in ("add_source", "assert_fact")] == [1, 2]  # researcher
    assert [by_tool[t].step_n for t in ("register_agent", "create_tasks", "recall", "record_decision")] == [
        1,
        2,
        3,
        4,
    ]
    assert {r.label for r in by_tool["add_source"].created} == {"Source"}
    assert {r.label for r in by_tool["recall"].created} == {"Recall"}


def test_step_endpoint_returns_what_each_agent_knew(api, lineage_world):
    t, w = lineage_world["tenant"], lineage_world
    s2 = M.StepResponse(**api.get(f"/api/{t}/step/2").json())
    agents = {a.agent_id: a for a in s2.agents}
    assert set(agents) == {"researcher", "planner"}
    assert [(x.id, x.label) for x in agents["researcher"].wrote] == [(w["fact"], "Fact")]
    assert agents["researcher"].read == []
    assert [(x.id, x.label) for x in agents["planner"].wrote] == [("t1", "Task")]
    assert agents["planner"].read == []  # step 2 = create_tasks, the recall comes at step 3

    s3 = M.StepResponse(**api.get(f"/api/{t}/step/3").json())
    planner = next(a for a in s3.agents if a.agent_id == "planner")
    assert planner.step_n == 3
    assert [(f.id, f.value, f.entity, f.read_at_step) for f in planner.read] == [
        (w["fact"], "PostgreSQL 16", "Acme API", 3)
    ]
    researcher = next(a for a in s3.agents if a.agent_id == "researcher")
    assert researcher.step_n == 2  # latest step <= 3

    s0 = M.StepResponse(**api.get(f"/api/{t}/step/0").json())
    assert s0.agents == []


def test_why_endpoint_for_decision_and_fact(api, lineage_world):
    t, w = lineage_world["tenant"], lineage_world
    r = api.get(f"/api/{t}/why/{w['decision']}")
    assert r.status_code == 200
    body = M.WhyResponse(**r.json())
    res = body.result
    assert body.id == w["decision"] and res.kind == "Decision" and not res.truncated
    assert [f.id for f in res.facts] == [w["fact"]]
    assert res.facts[0].asserted_by == ["researcher"] and res.facts[0].sources == [w["source"]]
    assert {"researcher", "planner"} <= set(res.agents)
    assert any(e.rel == "BASED_ON" and e.from_ == w["decision"] and e.to == w["fact"] for e in res.edges)
    assert res.paths and all(hop.rel for p in res.paths for hop in p)
    assert "from" in r.json()["result"]["edges"][0]  # wire format uses the stored-direction key `from`

    fact = M.WhyResponse(**api.get(f"/api/{t}/why/{w['fact']}").json())
    assert fact.result.kind == "Fact" and fact.result.facts[0].sources == [w["source"]]

    assert api.get(f"/api/{t}/why/not-a-node").status_code == 404
    assert api.get(f"/api/{t}/why/{w['source']}").status_code == 404  # only decisions and facts
    assert api.get("/api/no_such_tenant_zz/why/x").status_code == 404


def test_recall_endpoint(api, lineage_world):
    t, w = lineage_world["tenant"], lineage_world
    r = api.get(f"/api/{t}/recall/{w['recall']}")
    assert r.status_code == 200
    body = M.RecallResponse(**r.json())
    res = body.result
    assert res.recall.agent_id == "planner" and res.recall.query == "Acme API database"
    assert [(h.rank, h.fact_id) for h in res.results] == [(1, w["fact"])]
    assert res.results[0].asserted_by == ["researcher"]
    assert any(e.rel == "RETURNED" for e in res.edges)
    assert api.get(f"/api/{t}/recall/nope").status_code == 404


def test_lineage_endpoints_do_not_write(api, client, lineage_world):
    from knewat.graph.tenancy import graph_name

    t = lineage_world["tenant"]
    q = "MATCH (n) RETURN count(n)"
    before = client.graph(graph_name(t)).ro_query(q).result_set
    for path in ("step/3", f"why/{lineage_world['decision']}", f"recall/{lineage_world['recall']}"):
        assert api.get(f"/api/{t}/{path}").status_code == 200
    assert client.graph(graph_name(t)).ro_query(q).result_set == before
