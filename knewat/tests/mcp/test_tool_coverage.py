"""Contract tests for the tools the first contract suite never called (C-02), and the guard that keeps it so.

Every registered tool must be exercised through MCP by at least one test in this directory.
"""

from __future__ import annotations

import ast
import json
from pathlib import Path

from knewat.graph.tenancy import graph_name
from mcp import Client

HERE = Path(__file__).parent
CALLERS = {"_call", "call", "ok", "err", "run", "call_err", "call_tool"}


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


def audit_links(client, tenant, tool: str) -> list[str]:
    got = rows(
        client,
        tenant,
        "MATCH (t:ToolCall {tool:$tool}) OPTIONAL MATCH (t)-[r:CREATED|UPDATED]->(n) "
        "RETURN collect(type(r) + ':' + labels(n)[0])",
        tool=tool,
    )
    return sorted(x for x in got[0][0] if not x.startswith("None"))


def tool_calls(client, tenant, tool: str):
    return rows(
        client,
        tenant,
        "MATCH (t:ToolCall {tool:$tool})-[:IN_STEP]->(s:Step) RETURN t.agent_id, t.wrote, s.n ORDER BY t.at",
        tool=tool,
    )


# ---------------------------------------------------------------- as_of
async def test_as_of_answers_with_the_value_valid_at_that_time(server, client, tenant):
    async with Client(server) as c:
        v1 = await ok(c, "assert_fact", agent_id="a", subject="API", predicate="version", value="v1")
        hist1 = (await ok(c, "fact_history", agent_id="a", subject="API", predicate="version"))["history"]
        t1 = hist1[0]["valid_from"]
        await ok(c, "assert_fact", agent_id="a", subject="API", predicate="version", value="v2")
        hist = (await ok(c, "fact_history", agent_id="a", subject="API", predicate="version"))["history"]
        t2 = hist[1]["valid_from"]

        then = (await ok(c, "as_of", agent_id="b", subject="API", predicate="version", t=t1))["as_of"]
        now = (await ok(c, "as_of", agent_id="b", subject="API", predicate="version", t=t2))["as_of"]
        before = await ok(c, "as_of", agent_id="b", subject="API", predicate="version", t=max(t1 - 10, 0))
        assert then["value"] == "v1" and then["fact_id"] == v1["fact_id"]
        assert now["value"] == "v2"
        assert before["as_of"] is None
    calls = tool_calls(client, tenant, "as_of")
    assert len(calls) == 3 and all(agent == "b" and n >= 1 for agent, _, n in calls)
    assert audit_links(client, tenant, "as_of") == []  # a pure read creates and updates nothing


async def test_as_of_bad_input_is_a_clear_error(server):
    async with Client(server) as c:
        text = await err(c, "as_of", agent_id="b", subject="API", predicate="version", t=-5)
        assert text.startswith("as_of:") and "t" in text
        text = await err(c, "as_of", agent_id="b", subject="API", predicate="version", t=1, scope="bogus")
        assert "invalid scope" in text


# ---------------------------------------------------------------- log_procedure_run + best_procedure
async def test_log_procedure_run_and_best_procedure(server, client, tenant):
    async with Client(server) as c:
        await ok(c, "register_agent", agent_id="w")
        await ok(c, "create_tasks", agent_id="w", tasks=[{"id": "t1", "title": "fix"}])
        for success in (True, True, False):
            r = await ok(
                c,
                "log_procedure_run",
                agent_id="w",
                procedure_name="test-then-fix",
                task_type="bugfix",
                success=success,
                task_id="t1",
                notes="n",
                steps=["run tests", "patch"],
            )
            assert r["run_id"] and r["tool_call_id"]
        await ok(
            c, "log_procedure_run", agent_id="w", procedure_name="guess", task_type="bugfix", success=False
        )
        best = await ok(c, "best_procedure", agent_id="w", task_type="bugfix")
        names = [p["name"] if "name" in p else p["procedure"] for p in best["procedures"]]
        assert names[0] == "test-then-fix" and best["count"] == 2
        assert (await ok(c, "best_procedure", agent_id="w", task_type="bugfix", min_runs=3))["count"] == 1
        assert (await ok(c, "best_procedure", agent_id="w", task_type="nothing-yet"))["count"] == 0
    assert audit_links(client, tenant, "log_procedure_run").count("CREATED:Run") == 4
    assert audit_links(client, tenant, "best_procedure") == []
    assert len(tool_calls(client, tenant, "best_procedure")) == 3


async def test_procedure_tools_reject_bad_input(server):
    async with Client(server) as c:
        text = await err(c, "best_procedure", agent_id="w", task_type="bugfix", limit=0)
        assert text.startswith("best_procedure:") and "limit" in text
        text = await err(c, "best_procedure", agent_id="w", task_type="")
        assert "task_type" in text
        text = await err(
            c, "log_procedure_run", agent_id="w", procedure_name="p", task_type="t", success="maybe"
        )
        assert "success" in text
        text = await err(
            c,
            "log_procedure_run",
            agent_id="w",
            procedure_name="p",
            task_type="t",
            success=True,
            task_id="nope",
        )
        assert "nope" in text


# ---------------------------------------------------------------- verify_artifact
async def test_verify_artifact_records_independent_checks(server, client, tenant):
    async with Client(server) as c:
        for a in ("builder", "reviewer"):
            await ok(c, "register_agent", agent_id=a)
        await ok(c, "create_tasks", agent_id="builder", tasks=[{"id": "t1", "title": "build"}])
        t = (await ok(c, "claim_next_task", agent_id="builder"))["task"]
        done = await ok(
            c,
            "complete_task",
            agent_id="builder",
            task_id="t1",
            expected_version=t["version"],
            artifacts=[{"kind": "file", "uri": "out.md", "hash": "abc"}],
        )
        art = done["artifact_ids"][0]
        own = await ok(c, "verify_artifact", agent_id="builder", artifact_id=art)
        other = await ok(c, "verify_artifact", agent_id="reviewer", artifact_id=art)
        assert own["independent"] is False and other["independent"] is True
        assert other["tool_call_id"]
    assert audit_links(client, tenant, "verify_artifact") == ["UPDATED:Artifact", "UPDATED:Artifact"]
    assert len(tool_calls(client, tenant, "verify_artifact")) == 2


async def test_verify_artifact_unknown_id_is_a_clear_error(server, client, tenant):
    async with Client(server) as c:
        await ok(c, "register_agent", agent_id="reviewer")
        text = await err(c, "verify_artifact", agent_id="reviewer", artifact_id="no-such-artifact")
        assert "no-such-artifact" in text and "MATCH" not in text
        assert "artifact_id" in await err(c, "verify_artifact", agent_id="reviewer", artifact_id="")
    assert audit_links(client, tenant, "verify_artifact") == []  # a rejected call leaves nothing behind


# ---------------------------------------------------------------- the guard
def _called_tools() -> set[str]:
    """Every string literal passed as the tool name to a call helper in a test of this directory."""
    seen: set[str] = set()
    for path in HERE.glob("test_*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            fn = node.func
            name = fn.id if isinstance(fn, ast.Name) else fn.attr if isinstance(fn, ast.Attribute) else ""
            if name not in CALLERS:
                continue
            for arg in node.args[:2]:
                if isinstance(arg, ast.Constant) and isinstance(arg.value, str):
                    seen.add(arg.value)
    return seen


async def test_every_registered_tool_is_called_through_mcp_by_some_test(server):
    async with Client(server) as c:
        registered = {t.name for t in (await c.list_tools()).tools}
    missing = registered - _called_tools()
    assert not missing, f"tools with no MCP contract test: {sorted(missing)}"
    assert len(registered) >= 29
