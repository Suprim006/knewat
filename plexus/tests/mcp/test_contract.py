"""MCP contract tests over the in-memory client (stdio-style binding: one tenant per Runtime)."""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from mcp import Client
from plexus.graph.tenancy import graph_name

SNAPSHOT = Path(__file__).parent / "snapshots" / "tools.json"

STALENESS_TOOLS = {
    "anchor_fact",
    "describe_code",
    "mark_changed",
    "verify_fact",
    "facts_to_verify",
    "docs_to_update",
    "set_review_date",
}

ENGRAM_RELAY_TOOLS = {
    "start_session",
    "remember_episode",
    "assert_fact",
    "recall",
    "fact_history",
    "log_procedure_run",
    "best_procedure",
    "register_agent",
    "create_tasks",
    "claim_next_task",
    "heartbeat",
    "complete_task",
    "fail_task",
    "handoff",
    "verify_artifact",
    "record_decision",
    "reopen_task",
    "ready_tasks",
    "task_status",
    "blocked_by_failure",
}


async def _call(c: Client, name: str, **args):
    res = await c.call_tool(name, args)
    return res


def _data(res) -> dict:
    assert not res.is_error, res.content
    return json.loads(res.content[0].text)


async def test_tool_list_and_schema_snapshot(server):
    async with Client(server) as c:
        tools = (await c.list_tools()).tools
    got = {
        t.name: {"description": t.description, "inputSchema": t.input_schema}
        for t in sorted(tools, key=lambda t: t.name)
    }
    names = set(got)
    assert ENGRAM_RELAY_TOOLS <= names
    lineage_tools = {
        "why",
        "why_recalled",
        "who_knew",
        "knew_at",
        "as_of",
        "add_source",
        "forget_source",
        "quarantine_source",
        "release_quarantine",
    }
    assert STALENESS_TOOLS <= names
    memory_tools = {"pin_fact", "unpin_fact", "memory_strength", "memory_sweep", "restore_fact"}  # P7-K
    extra = names - ENGRAM_RELAY_TOOLS - STALENESS_TOOLS
    assert extra == lineage_tools | memory_tools, "unexpected or missing tools"
    for name, spec in got.items():
        props = spec["inputSchema"]["properties"]
        assert "agent_id" in props, name
        assert "step" in props, name
        assert "tenant" not in props and "graph" not in props, f"{name} must not take a tenant"
        assert "agent_id" in spec["inputSchema"]["required"], name
        assert len(spec["description"] or "") > 40, f"{name} needs an LLM-facing description"
    if os.environ.get("UPDATE_SNAPSHOT") or not SNAPSHOT.exists():
        SNAPSHOT.parent.mkdir(exist_ok=True)
        SNAPSHOT.write_text(json.dumps(got, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    assert got == json.loads(SNAPSHOT.read_text(encoding="utf-8")), (
        "schema drift: rerun with UPDATE_SNAPSHOT=1"
    )


def _tool_calls(client, tenant):
    res = client.graph(graph_name(tenant)).ro_query(
        "MATCH (t:ToolCall) OPTIONAL MATCH (t)-[r:CREATED|UPDATED]->(n) "
        "RETURN t.tool AS tool, t.agent_id AS agent, t.wrote AS wrote, t.run_time_ms AS ms, "
        "t.query_name AS q, collect(type(r) + ':' + labels(n)[0]) AS links ORDER BY t.at, t.tool"
    )
    return [
        dict(zip(["tool", "agent", "wrote", "ms", "q", "links"], row, strict=True)) for row in res.result_set
    ]


async def test_engram_flow_and_toolcall_audit(server, client, tenant):
    async with Client(server) as c:
        s = _data(await _call(c, "start_session", agent_id="smoke", agent_role="tester"))
        e = _data(
            await _call(
                c, "remember_episode", agent_id="smoke", session_id=s["session_id"], text="hello", step=1
            )
        )
        f = _data(
            await _call(
                c, "assert_fact", agent_id="smoke", subject="API", predicate="version", value="v1", step=2
            )
        )
        assert f["superseded"] == [] and f["duplicate_of"] is None
        f2 = _data(
            await _call(c, "assert_fact", agent_id="smoke", subject="API", predicate="version", value="v2")
        )
        assert f2["superseded"] == [f["fact_id"]]
        r = _data(await _call(c, "recall", agent_id="smoke", query="API version", k=3))
        assert r["count"] >= 1
        assert r["facts"][0]["value"] in {"v1", "v2"}
        assert any(x["fact_id"] == f2["fact_id"] and x["status"] == "active" for x in r["facts"])
        h = _data(await _call(c, "fact_history", agent_id="smoke", subject="API", predicate="version"))
        assert [x["value"] for x in h["history"]] == ["v1", "v2"]
        assert e["episode_id"]

    calls = _tool_calls(client, tenant)
    tools = [x["tool"] for x in calls]
    assert tools.count("start_session") == 1 and tools.count("assert_fact") == 2
    assert sorted(tools) == sorted(
        ["start_session", "remember_episode", "assert_fact", "assert_fact", "recall", "fact_history"]
    )
    by = {x["tool"]: x for x in calls}
    assert by["start_session"]["links"].count("CREATED:Session") == 1
    assert "CREATED:Episode" in by["remember_episode"]["links"]
    # recall changes no memory, but its Recall record is a node the call created
    assert by["recall"]["wrote"] is True and by["recall"]["links"] == ["CREATED:Recall"]
    # P7-K: the last read of a forgetting-on recall is the activation lookup, so that is the query name now
    assert by["recall"]["q"] in ("engram/recall", "activation/activation") and by["recall"]["ms"] > 0
    second = [x for x in calls if x["tool"] == "assert_fact"]
    assert any("UPDATED:Fact" in x["links"] for x in second)  # the superseded fact
    assert all(x["agent"] == "smoke" for x in calls)


async def test_relay_flow(server, client, tenant):
    async with Client(server) as c:
        await _call(c, "register_agent", agent_id="planner", role="planner")
        await _call(c, "register_agent", agent_id="builder", role="builder")
        t = _data(
            await _call(
                c,
                "create_tasks",
                agent_id="planner",
                tasks=[
                    {"id": "t1", "title": "design"},
                    {"id": "t2", "title": "build", "depends_on": ["t1"]},
                ],
            )
        )
        assert t["task_ids"] == ["t1", "t2"]
        claim = _data(await _call(c, "claim_next_task", agent_id="builder", lease_ms=60000))
        assert claim["task"]["id"] == "t1"
        hb = _data(await _call(c, "heartbeat", agent_id="builder", task_id="t1"))
        assert hb["alive"] is True
        none_yet = _data(await _call(c, "claim_next_task", agent_id="planner"))
        assert none_yet["task"] is None  # t2 is blocked by t1
        done = _data(
            await _call(
                c,
                "complete_task",
                agent_id="builder",
                task_id="t1",
                expected_version=claim["task"]["version"],
                artifacts=[{"kind": "file", "uri": "design.md", "summary": "the design"}],
            )
        )
        assert done["status"] == "done" and len(done["artifact_ids"]) == 1
        ho = _data(
            await _call(
                c,
                "handoff",
                agent_id="builder",
                to_agent="planner",
                task_id="t1",
                note="design done",
                artifact_ids=done["artifact_ids"],
            )
        )
        assert ho["handoff_id"]
        fact = _data(
            await _call(
                c, "assert_fact", agent_id="builder", subject="design", predicate="status", value="ok"
            )
        )
        d = _data(
            await _call(
                c,
                "record_decision",
                agent_id="builder",
                task_id="t1",
                text="ship it",
                based_on_fact_ids=[fact["fact_id"]],
            )
        )
        assert d["decision_id"]
        st = _data(await _call(c, "task_status", agent_id="planner", task_id="t2"))
        assert st["task"]["status"] == "open" and st["task"]["blocked_by"] == []
        assert _data(await _call(c, "ready_tasks", agent_id="planner"))["count"] == 1
        assert _data(await _call(c, "blocked_by_failure", agent_id="planner", task_id="t1"))["blocked"] == [
            "t2"
        ]

    by = {}
    for x in _tool_calls(client, tenant):
        by.setdefault(x["tool"], x)
    assert sorted(by["create_tasks"]["links"]) == ["CREATED:Task", "CREATED:Task"]
    assert "UPDATED:Task" in by["claim_next_task"]["links"]
    assert (
        "CREATED:Artifact" in by["complete_task"]["links"] and "UPDATED:Task" in by["complete_task"]["links"]
    )
    assert by["handoff"]["links"] == ["CREATED:Handoff"]
    assert by["record_decision"]["links"] == ["CREATED:Decision"]


async def test_errors_are_clear_and_leak_no_cypher(server, client, tenant):
    async with Client(server) as c:
        r = await _call(c, "remember_episode", agent_id="a", session_id="nope", text="x")
        assert r.is_error and "session 'nope' does not exist" in r.content[0].text
        r = await _call(c, "claim_next_task", agent_id="ghost")
        assert r.is_error and "unknown agent" in r.content[0].text
        r = await _call(c, "assert_fact", agent_id="a", subject="s", predicate="p", value="v", scope="bogus")
        assert r.is_error and "invalid scope" in r.content[0].text
        r = await _call(
            c, "create_tasks", agent_id="a", tasks=[{"id": "x", "title": "x", "depends_on": ["x"]}]
        )
        assert r.is_error and "depends on itself" in r.content[0].text
        r = await _call(c, "create_tasks", agent_id="a", tasks="not a list")
        assert r.is_error  # schema validation
        r = await _call(c, "recall", agent_id="a", query="q", scope="project:")  # malformed scope
        assert r.is_error
        for res in [r]:
            for word in ("MATCH", "RETURN", "CREATE ("):
                assert word not in res.content[0].text
    # failed calls are not audited as writes; the server survived
    assert all(x["tool"] != "claim_next_task" or x["wrote"] is False for x in _tool_calls(client, tenant))


async def test_tenant_is_not_an_argument_and_schema_applied_once(runtime, server, client, tenant):
    async with Client(server) as c:
        r = await _call(c, "start_session", agent_id="a", tenant="evil")  # unknown argument: never read
        assert not r.is_error
        await _call(c, "start_session", agent_id="a")
        await _call(c, "start_session", agent_id="a")
    assert list(runtime._tenants) == [tenant]
    assert "evil" not in runtime._tenants
    # a stdio runtime ignores any header and serves its one tenant
    assert runtime.tenant_of({"x-plexus-tenant": "other"}) == tenant


async def test_scope_specs_project_inherits_global(server, client, tenant):
    async with Client(server) as c:
        await _call(c, "assert_fact", agent_id="a", subject="Acme", predicate="stack", value="python")
        await _call(
            c,
            "assert_fact",
            agent_id="a",
            subject="Acme",
            predicate="owner",
            value="team-x",
            scope="project:acme",
        )
        proj = _data(await _call(c, "recall", agent_id="a", query="Acme owner", scope="project:acme", k=5))
        glob = _data(await _call(c, "recall", agent_id="a", query="Acme owner", scope="global", k=5))
    pv = {f["predicate"] for f in proj["facts"]}
    gv = {f["predicate"] for f in glob["facts"]}
    assert {"stack", "owner"} <= pv  # project sees global + its own
    assert "owner" not in gv  # global does not see project facts


@pytest.mark.parametrize("bad", ["Upper", "has space", "x" * 49, ""])
def test_invalid_tenant_rejected(client, bad):
    from plexus.mcp.runtime import Runtime

    rt = Runtime(client=client, stdio_tenant=bad or None)
    with pytest.raises(Exception, match=r"invalid tenant|no tenant"):
        rt.tenant_of({})
