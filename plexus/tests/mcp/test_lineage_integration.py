"""Lineage wired into the MCP layer: Steps, READ/WROTE, Recall records, sources, quarantine, why."""

Everything goes through MCP tools only (in-memory client, real database); assertions read the graph directly.
"""

from __future__ import annotations

import json

import pytest

from mcp import Client
from plexus.graph.tenancy import graph_name
from plexus.mcp.runtime import Runtime
from plexus.mcp.server import build_server


async def call(c: Client, name: str, **args) -> dict:
    res = await c.call_tool(name, args)
    assert not res.is_error, res.content
    return json.loads(res.content[0].text)


async def call_err(c: Client, name: str, **args) -> str:
    res = await c.call_tool(name, args)
    assert res.is_error, f"{name} should have failed"
    return res.content[0].text


def rows(client, tenant, q, **params):
    return client.graph(graph_name(tenant)).ro_query(q, params or None).result_set


async def run_scenario(c: Client) -> dict:
    """researcher cites a source and asserts a fact; planner recalls, decides on it, hands off to builder."""
    s: dict = {}
    src = await call(
        c, "add_source", agent_id="researcher", title="Acme design doc", uri="https://example.test/doc"
    )
    s["source"] = src["source_id"]
    fact = await call(
        c,
        "assert_fact",
        agent_id="researcher",
        subject="Acme API",
        predicate="database",
        value="PostgreSQL 16",
        source_id=s["source"],
    )
    s["fact"] = fact["fact_id"]
    await call(c, "start_session", agent_id="planner", agent_role="planner")
    await call(c, "register_agent", agent_id="builder", role="builder")
    await call(c, "create_tasks", agent_id="planner", tasks=[{"id": "t1", "title": "build the API"}])
    rec = await call(c, "recall", agent_id="planner", query="Acme API database", k=3)
    s["recall"] = rec
    dec = await call(
        c,
        "record_decision",
        agent_id="planner",
        task_id="t1",
        text="use PostgreSQL",
        based_on_fact_ids=[s["fact"]],
    )
    s["decision"] = dec["decision_id"]
    h = await call(
        c,
        "handoff",
        agent_id="planner",
        to_agent="builder",
        task_id="t1",
        note="build on PostgreSQL",
        fact_ids=[s["fact"]],
    )
    s["handoff"] = h["handoff_id"]
    return s


async def test_two_agent_scenario_leaves_a_full_lineage(server, client, tenant):
    async with Client(server) as c:
        s = await run_scenario(c)

        # -- Steps: one per call, a NEXT chain per agent, ToolCall.step_id set
        steps = rows(client, tenant, "MATCH (s:Step) RETURN s.agent_id, s.n ORDER BY s.agent_id, s.n")
        assert [(a, n) for a, n in steps if a == "researcher"] == [("researcher", 1), ("researcher", 2)]
        assert [(a, n) for a, n in steps if a == "planner"] == [("planner", i) for i in range(1, 6)]
        assert [(a, n) for a, n in steps if a == "builder"] == [("builder", 1)]  # register_agent only
        chain = rows(
            client,
            tenant,
            "MATCH (a:Step)-[:NEXT]->(b:Step) RETURN a.agent_id, a.n, b.agent_id, b.n ORDER BY a.agent_id",
        )
        assert all(a1 == a2 and n2 == n1 + 1 for a1, n1, a2, n2 in chain)
        assert len(chain) == (2 - 1) + (5 - 1)
        calls = rows(
            client,
            tenant,
            "MATCH (t:ToolCall) OPTIONAL MATCH (t)-[:IN_STEP]->(s:Step) "
            "RETURN t.tool, t.agent_id, t.step, s.agent_id, s.n ORDER BY t.at, t.tool",
        )
        assert len(calls) == 8
        assert all(sa == agent and n is not None for _tool, agent, _step, sa, n in calls)
        assert all(step == -1 for _t, _a, step, _sa, _n in calls)  # no explicit step was sent

        # -- WROTE / READ
        wrote = {
            (a, n, lab, i)
            for a, n, lab, i in rows(
                client,
                tenant,
                "MATCH (s:Step)-[:WROTE]->(x) RETURN s.agent_id, s.n, labels(x)[0], x.id",
            )
        }
        assert ("researcher", 2, "Fact", s["fact"]) in wrote
        assert ("planner", 2, "Task", "t1") in wrote
        assert ("planner", 4, "Decision", s["decision"]) in wrote
        assert ("planner", 5, "Handoff", s["handoff"]) in wrote
        reads = {
            (a, n, i)
            for a, n, i in rows(
                client, tenant, "MATCH (s:Step)-[:READ]->(f:Fact) RETURN s.agent_id, s.n, f.id"
            )
        }
        # recall (3), record_decision (4) and handoff (5) all read the fact; the researcher only wrote it
        assert {(a, n) for a, n, i in reads if i == s["fact"]} == {
            ("planner", 3),
            ("planner", 4),
            ("planner", 5),
        }

        # -- the Recall record and the id handed back to the agent
        rid = s["recall"]["recall_id"]
        ret = rows(
            client,
            tenant,
            "MATCH (r:Recall {id:$id})-[x:RETURNED]->(f:Fact) RETURN f.id, x.rank, x.score",
            id=rid,
        )
        assert [(f, rank) for f, rank, _sc in ret] == [(s["fact"], 1)]
        in_step = rows(
            client, tenant, "MATCH (:Recall {id:$id})-[:IN_STEP]->(st:Step) RETURN st.agent_id", id=rid
        )
        assert in_step == [["planner"]]

        # -- source link made by assert_fact
        assert rows(
            client,
            tenant,
            "MATCH (f:Fact {id:$f})-[:DERIVED_FROM]->(s:Source {id:$s}) RETURN s.title",
            f=s["fact"],
            s=s["source"],
        ) == [["Acme design doc"]]

        # -- why(decision) through the MCP tool
        why = (await call(c, "why", agent_id="auditor", node_id=s["decision"]))["why"]
        assert why["kind"] == "Decision"
        assert [f["id"] for f in why["facts"]] == [s["fact"]]
        assert why["facts"][0]["asserted_by"] == ["researcher"]
        assert why["facts"][0]["sources"] == [s["source"]]
        assert {"researcher", "planner"} <= set(why["agents"])
        assert s["source"] in why["sources"]
        assert why["steps"]  # the steps that wrote the decision and the fact

        # -- why_recalled
        wr = (await call(c, "why_recalled", agent_id="auditor", recall_id=rid))["why_recalled"]
        assert [r["fact_id"] for r in wr["results"]] == [s["fact"]]
        assert wr["results"][0]["rank"] == 1 and wr["recall"]["agent_id"] == "planner"

        # -- who_knew
        wk = (await call(c, "who_knew", agent_id="auditor", fact_id=s["fact"]))["who_knew"]
        assert wk["asserted_by"] == ["researcher"] and "planner" in wk["agents"]
        assert rid in wk["readers"][0]["recall_ids"]

        # -- time machine: planner's step 2 (create_tasks) has not read anything; step 3 (recall) has
        before = (await call(c, "knew_at", agent_id="auditor", subject_agent="planner", step_n=2))["knew_at"]
        assert before["facts"] == [] and [w["id"] for w in before["wrote"]] == ["t1"]
        after = (await call(c, "knew_at", agent_id="auditor", subject_agent="planner", step_n=3))["knew_at"]
        assert [f["fact_id"] for f in after["facts"]] == [s["fact"]]
        assert after["facts"][0]["value"] == "PostgreSQL 16"


async def test_explicit_steps_are_respected_and_shared(server, client, tenant):
    async with Client(server) as c:
        await call(c, "register_agent", agent_id="a1", step=5)
        await call(c, "ready_tasks", agent_id="a1", step=5)  # same step: same Step node
        await call(c, "ready_tasks", agent_id="a1")  # next automatic number: 6
        await call(c, "ready_tasks", agent_id="a1", step=2)  # behind: falls back to the next number (7)
        await call(c, "ready_tasks", agent_id="a1", step=9)
    got = rows(client, tenant, "MATCH (s:Step {agent_id:'a1'}) RETURN s.n ORDER BY s.n")
    assert [n for (n,) in got] == [5, 6, 7, 9]
    per_step = rows(
        client,
        tenant,
        "MATCH (t:ToolCall {agent_id:'a1'})-[:IN_STEP]->(s:Step) RETURN s.n, count(t) ORDER BY s.n",
    )
    assert per_step == [[5, 2], [6, 1], [7, 1], [9, 1]]
    flags = rows(client, tenant, "MATCH (t:ToolCall {agent_id:'a1'}) RETURN t.step ORDER BY t.at, t.step")
    assert sorted(f for (f,) in flags) == [-1, 2, 5, 5, 9]


async def test_add_source_is_idempotent_and_fact_with_unknown_source_is_a_clear_error(server):
    async with Client(server) as c:
        a = await call(c, "add_source", agent_id="x", title="Notes", text="hello world")
        b = await call(c, "add_source", agent_id="x", title="Notes", text="hello world")
        assert a["source_id"] == b["source_id"] and a["uri"].startswith("note:")
        d = await call(c, "add_source", agent_id="x", title="Notes", text="other")
        assert d["source_id"] != a["source_id"]
        err = await call_err(
            c,
            "assert_fact",
            agent_id="x",
            subject="S",
            predicate="p",
            value="v",
            source_id="no-such-source",
        )
        assert "source" in err and "no-such-source" in err


async def test_quarantine_and_release_through_tools(server, client, tenant):
    async with Client(server) as c:
        s = await run_scenario(c)
        q = (await call(c, "quarantine_source", agent_id="security", source_id=s["source"]))["quarantined"]
        assert q["fact_ids"] == [s["fact"]]
        assert q["agents"] == ["planner"] and s["decision"] in q["decision_ids"]
        assert q["readers"][0]["step_n"] is not None
        gone = await call(c, "recall", agent_id="planner", query="Acme API database", k=3)
        assert gone["count"] == 0 and gone["recall_id"]
        rel = (await call(c, "release_quarantine", agent_id="security", source_id=s["source"]))["released"]
        assert rel["fact_ids"] == [s["fact"]]
        back = await call(c, "recall", agent_id="planner", query="Acme API database", k=3)
        assert back["count"] == 1
        # the audit trail shows the facts as UPDATED by the quarantine call
        upd = rows(
            client,
            tenant,
            "MATCH (t:ToolCall {tool:'quarantine_source'})-[:UPDATED]->(f:Fact) RETURN f.id",
        )
        assert upd == [[s["fact"]]]
        err = await call_err(c, "quarantine_source", agent_id="security", source_id="nope")
        assert "nope" in err


async def test_forget_source_through_tool(server):
    async with Client(server) as c:
        s = await run_scenario(c)
        f = (await call(c, "forget_source", agent_id="admin", source_id=s["source"]))["forgotten"]
        assert f["fact_ids"] == [s["fact"]] and f["decision_ids"] == [s["decision"]]
        assert (await call(c, "recall", agent_id="planner", query="Acme API database"))["count"] == 0


async def test_reopen_task_tool(server):
    async with Client(server) as c:
        await call(c, "register_agent", agent_id="w")
        await call(c, "create_tasks", agent_id="w", tasks=[{"id": "t9", "title": "flaky"}])
        t = (await call(c, "claim_next_task", agent_id="w"))["task"]
        await call(c, "fail_task", agent_id="w", task_id="t9", expected_version=t["version"], reason="boom")
        r = (await call(c, "reopen_task", agent_id="w", task_id="t9"))["task"]
        assert r["status"] == "open"
        err = await call_err(c, "reopen_task", agent_id="w", task_id="t9")  # not failed any more
        assert "t9" in err
        err = await call_err(c, "reopen_task", agent_id="w", task_id="ghost")
        assert "ghost" in err


async def test_runtime_without_lineage_still_works(monkeypatch, client, tenant):
    import sys

    from plexus.embed import HashEmbedder

    monkeypatch.setitem(sys.modules, "plexus.lineage", None)  # `import plexus.lineage` now fails
    rt = Runtime(client=client, embedder=HashEmbedder(), stdio_tenant=tenant)
    async with Client(build_server(rt)) as c:
        names = {t.name for t in (await c.list_tools()).tools}
        assert "add_source" not in names and "recall" in names
        await call(c, "assert_fact", agent_id="solo", subject="A", predicate="p", value="v")
        r = await call(c, "recall", agent_id="solo", query="A p")
        assert r["count"] == 1 and "recall_id" not in r
    assert rows(client, tenant, "MATCH (s:Step) RETURN count(s)") == [[0]]


@pytest.mark.parametrize("tool", ["add_source", "quarantine_source", "release_quarantine", "reopen_task"])
async def test_new_tools_are_listed_with_descriptions(server, tool):
    async with Client(server) as c:
        t = next(t for t in (await c.list_tools()).tools if t.name == tool)
    assert len(t.description or "") > 80
