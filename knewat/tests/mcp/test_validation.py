"""Argument validation: unknown keys, bounds, empty values and one-line error messages (C-01, C-03..C-08)."""

from __future__ import annotations

import json

import pytest

from knewat.graph.tenancy import graph_name
from mcp import Client


async def run(c: Client, _tool: str, /, **args):
    res = await c.call_tool(_tool, args)
    return res


async def ok(c: Client, _tool: str, /, **args) -> dict:
    res = await run(c, _tool, **args)
    assert not res.is_error, res.content[0].text
    return json.loads(res.content[0].text)


async def err(c: Client, _tool: str, /, **args) -> str:
    res = await run(c, _tool, **args)
    assert res.is_error, f"{_tool} should have been rejected: {res.content[0].text[:200]}"
    return res.content[0].text


def count(client, tenant, cypher: str) -> int:
    return client.graph(graph_name(tenant)).ro_query(cypher).result_set[0][0]


# ---------------------------------------------------------------- C-01 unknown keys
@pytest.mark.parametrize("bad", ["dependsOn", "dependencies", "deps", "depends"])
async def test_unknown_task_key_is_rejected_and_names_the_expected_keys(server, client, tenant, bad):
    async with Client(server) as c:
        text = await err(
            c,
            "create_tasks",
            agent_id="p",
            tasks=[{"id": "t1", "title": "a"}, {"id": "t2", "title": "b", bad: ["t1"]}],
        )
        assert bad in text and "depends_on" in text and "title" in text and "priority" in text
        assert (await ok(c, "ready_tasks", agent_id="p"))["count"] == 0  # nothing was created


async def test_unknown_artifact_key_is_rejected(server):
    async with Client(server) as c:
        await ok(c, "register_agent", agent_id="w")
        await ok(c, "create_tasks", agent_id="w", tasks=[{"id": "t1", "title": "a"}])
        t = (await ok(c, "claim_next_task", agent_id="w"))["task"]
        text = await err(
            c,
            "complete_task",
            agent_id="w",
            task_id="t1",
            expected_version=t["version"],
            artifacts=[{"kind": "file", "uri": "x", "path": "oops"}],
        )
        assert "path" in text and "uri" in text and "summary" in text
        assert (await ok(c, "task_status", agent_id="w", task_id="t1"))["task"]["status"] == "claimed"


# ---------------------------------------------------------------- C-03 / C-05 numeric bounds
@pytest.mark.parametrize("step", [0, -3, 2**31, 2**70])
async def test_step_must_be_a_small_positive_int(server, client, tenant, step):
    async with Client(server) as c:
        text = await err(c, "assert_fact", agent_id="a", subject="S", predicate="p", value="v", step=step)
        assert "step" in text
    assert (
        count(client, tenant, "MATCH (f:Fact) RETURN count(f)") == 0
        if _graph_exists(client, tenant)
        else True
    )


def _graph_exists(client, tenant) -> bool:
    return graph_name(tenant) in client.db.list_graphs()


@pytest.mark.parametrize(
    ("tool", "args", "field"),
    [
        ("claim_next_task", {"lease_ms": 10**13}, "lease_ms"),
        ("claim_next_task", {"lease_ms": 2**70}, "lease_ms"),
        ("heartbeat", {"task_id": "t", "lease_ms": 86_400_001}, "lease_ms"),
        ("create_tasks", {"tasks": [{"title": "x", "priority": 2**70}]}, "priority"),
        ("recall", {"query": "q", "as_of": 2**70}, "as_of"),
        ("recall", {"query": "q", "as_of": -1}, "as_of"),
        ("as_of", {"subject": "s", "predicate": "p", "t": 2**70}, "t"),
        ("knew_at", {"subject_agent": "x", "step_n": 2**70}, "step_n"),
        ("knew_at", {"subject_agent": "x", "step_n": -1}, "step_n"),
        ("complete_task", {"task_id": "t", "expected_version": 2**70}, "expected_version"),
    ],
)
async def test_numeric_args_are_bounded_with_a_field_level_message(server, tool, args, field):
    async with Client(server) as c:
        text = await err(c, tool, agent_id="a", **args)
        assert field in text and "rejected the request" not in text


async def test_one_day_lease_is_still_fine(server):
    async with Client(server) as c:
        await ok(c, "register_agent", agent_id="w")
        await ok(c, "create_tasks", agent_id="w", tasks=[{"id": "t1", "title": "a"}])
        assert (await ok(c, "claim_next_task", agent_id="w", lease_ms=86_400_000))["task"]["id"] == "t1"


# ---------------------------------------------------------------- C-04 length limits
@pytest.mark.parametrize(
    ("tool", "args"),
    [
        ("assert_fact", {"subject": "s", "predicate": "p", "value": "v" * 20_001}),
        ("assert_fact", {"subject": "s" * 513, "predicate": "p", "value": "v"}),
        ("recall", {"query": "q" * 20_001}),
        ("remember_episode", {"session_id": "s", "text": "t" * 100_001}),
        ("add_source", {"title": "t" * 2_001}),
        ("add_source", {"title": "t", "uri": "u" * 2_001}),
        ("add_source", {"title": "t", "text": "x" * 100_001}),
        ("register_agent", {"name": "n" * 513}),
        ("create_tasks", {"tasks": [{"title": "t" * 2_001}]}),
        ("create_tasks", {"tasks": [{"title": "t"}] * 201}),
        ("create_tasks", {"tasks": [{"title": "t", "depends_on": ["x"] * 201}]}),
        (
            "log_procedure_run",
            {"procedure_name": "n", "task_type": "t", "success": True, "steps": ["s"] * 201},
        ),
        ("record_decision", {"task_id": "t", "text": "x" * 100_001}),
        ("handoff", {"to_agent": "b", "task_id": "t", "note": "x" * 100_001}),
        ("handoff", {"to_agent": "b", "task_id": "t", "note": "x", "fact_ids": ["f"] * 201}),
    ],
)
async def test_oversized_arguments_are_rejected_before_any_work(server, tool, args):
    async with Client(server) as c:
        text = await err(c, tool, agent_id="a", **args)
        assert "at most" in text or "too long" in text


async def test_oversized_agent_id_is_rejected(server):
    async with Client(server) as c:
        text = await err(c, "start_session", agent_id="a" * 129)
        assert "agent_id" in text


async def test_values_at_the_limit_are_accepted(server):
    async with Client(server) as c:
        r = await ok(c, "assert_fact", agent_id="a", subject="s", predicate="p", value="v" * 20_000)
        assert r["fact_id"]


# ---------------------------------------------------------------- C-06 reads do not create Scope nodes
async def test_read_tools_do_not_create_scopes(server, client, tenant):
    async with Client(server) as c:
        await ok(c, "assert_fact", agent_id="a", subject="S", predicate="p", value="v")  # creates 'global'
        before = count(client, tenant, "MATCH (s:Scope) RETURN count(s)")
        for i in range(3):
            r = await ok(c, "recall", agent_id="a", query="S p", scope=f"project:typo{i}")
            assert r["count"] == 0
        assert (await ok(c, "fact_history", agent_id="a", subject="S", predicate="p", scope="user:zz"))[
            "count"
        ] == 0
        assert (await ok(c, "as_of", agent_id="a", subject="S", predicate="p", t=1, scope="user:zz"))[
            "as_of"
        ] is None
        # a raw id that exists nowhere
        r = await ok(c, "recall", agent_id="a", query="S p", scope="11111111-2222-3333-4444-555555555555")
        assert r["count"] == 0
        assert count(client, tenant, "MATCH (s:Scope) RETURN count(s)") == before
        assert count(client, tenant, "MATCH (r:Recall) RETURN count(r)") == 0  # nothing to explain
        # ...while a write still creates the named scope on first use
        await ok(c, "assert_fact", agent_id="a", subject="S", predicate="p", value="v", scope="project:real")
        assert count(client, tenant, "MATCH (s:Scope) RETURN count(s)") == before + 1
        assert (await ok(c, "recall", agent_id="a", query="S p", scope="project:real"))[
            "count"
        ] == 2  # global + own


async def test_read_on_a_fresh_tenant_with_no_scopes_returns_empty(server, client, tenant):
    async with Client(server) as c:
        r = await ok(c, "recall", agent_id="a", query="anything")
        assert r["count"] == 0
        assert count(client, tenant, "MATCH (s:Scope) RETURN count(s)") == 0


async def test_scope_name_is_capped(server):
    async with Client(server) as c:
        text = await err(
            c,
            "assert_fact",
            agent_id="a",
            subject="s",
            predicate="p",
            value="v",
            scope="project:" + "x" * 600,
        )
        assert "scope" in text


# ---------------------------------------------------------------- C-07 empty / garbage values
@pytest.mark.parametrize(
    ("tool", "args"),
    [
        ("create_tasks", {"tasks": [{"title": ""}]}),
        ("create_tasks", {"tasks": [{"id": "", "title": "x"}]}),
        ("remember_episode", {"session_id": "s", "text": ""}),
        ("remember_episode", {"session_id": "s", "text": "x", "role": "wizard"}),
        ("log_procedure_run", {"procedure_name": "", "task_type": "t", "success": True}),
        ("add_source", {"title": ""}),
        ("assert_fact", {"subject": "", "predicate": "p", "value": "v"}),
        ("assert_fact", {"subject": "s", "predicate": "", "value": "v"}),
        ("record_decision", {"task_id": "t", "text": ""}),
        ("handoff", {"to_agent": "b", "task_id": "t", "note": ""}),
    ],
)
async def test_empty_or_unknown_enum_values_are_rejected(server, tool, args):
    async with Client(server) as c:
        await err(c, tool, agent_id="a", **args)


async def test_role_accepts_the_documented_values(server):
    async with Client(server) as c:
        s = await ok(c, "start_session", agent_id="a")
        for role in ("user", "assistant", "tool", "note"):
            await ok(c, "remember_episode", agent_id="a", session_id=s["session_id"], text="x", role=role)


async def test_unknown_task_ids_are_errors_consistently(server):
    async with Client(server) as c:
        await ok(c, "register_agent", agent_id="a")
        assert "ghost" in await err(c, "task_status", agent_id="a", task_id="ghost")
        assert "ghost" in await err(c, "blocked_by_failure", agent_id="a", task_id="ghost")
        text = await err(
            c,
            "log_procedure_run",
            agent_id="a",
            procedure_name="p",
            task_type="t",
            success=True,
            task_id="ghost",
        )
        assert "ghost" in text
        await ok(c, "create_tasks", agent_id="a", tasks=[{"id": "real", "title": "x"}])
        r = await ok(
            c,
            "log_procedure_run",
            agent_id="a",
            procedure_name="p",
            task_type="t",
            success=True,
            task_id="real",
        )
        assert r["run_id"]


# ---------------------------------------------------------------- C-08 error text and docs
async def test_validation_errors_are_one_short_line_without_pydantic_noise(server):
    async with Client(server) as c:
        text = await err(c, "recall", agent_id="a", query="q", k=0)
        assert text.startswith("recall:") and "k" in text
        for noise in ("pydantic", "errors.pydantic.dev", "Arguments", "validation error for", "input_value"):
            assert noise not in text
        assert "\n" not in text and len(text) < 300

        text = await err(c, "create_tasks", agent_id="a", tasks="not a list")
        assert "tasks" in text and "pydantic" not in text

        text = await err(c, "assert_fact", agent_id="a", subject="s", predicate="p")  # value missing
        assert "value" in text and "required" in text.lower()


async def test_validation_error_does_not_echo_huge_input(server):
    async with Client(server) as c:
        text = await err(c, "assert_fact", agent_id="a", subject="s", predicate="p", value="v" * 50_000)
        assert len(text) < 400


async def test_as_of_scope_documents_the_same_specs_as_recall(server):
    async with Client(server) as c:
        tools = {t.name: t for t in (await c.list_tools()).tools}
    d = tools["as_of"].input_schema["properties"]["scope"]["description"]
    assert "project:<name>" in d and "global" in d
