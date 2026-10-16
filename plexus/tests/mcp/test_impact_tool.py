"""MCP contract for ``impact`` (P4): read-only blast radius of a source, a fact or a task."""

from __future__ import annotations

import pytest

from mcp import Client

from .test_tool_coverage import err, ok, rows


async def _world(c):
    src = (await ok(c, "add_source", agent_id="a", title="Bad blog", uri="https://x.example/bad"))[
        "source_id"
    ]
    f1 = (
        await ok(
            c, "assert_fact", agent_id="a", subject="Cache", predicate="engine", value="Redis", source_id=src
        )
    )["fact_id"]
    f2 = (
        await ok(
            c, "assert_fact", agent_id="a", subject="Cache", predicate="ttl", value="60 s", source_id=src
        )
    )["fact_id"]
    await ok(
        c,
        "create_tasks",
        agent_id="a",
        tasks=[
            {"id": "t1", "title": "design"},
            {"id": "t2", "title": "build", "depends_on": ["t1"]},
            {"id": "t3", "title": "ship", "depends_on": ["t2"]},
        ],
    )
    dec = (
        await ok(c, "record_decision", agent_id="a", task_id="t2", text="use redis", based_on_fact_ids=[f1])
    )["decision_id"]
    await ok(c, "recall", agent_id="b", query="cache engine redis")  # agent b READs the facts
    return src, f1, f2, dec


async def test_impact_source_fact_and_task(server, client, tenant):
    async with Client(server) as c:
        src, f1, f2, dec = await _world(c)
        r = (await ok(c, "impact", agent_id="a", kind="source", id=src))["impact"]
        assert r["facts"]["ids"] == sorted([f1, f2]) and r["facts"]["by_status"] == {"active": 2}
        assert r["decisions"] == {"total": 1, "ids": [dec]}
        assert r["tasks"] == {"total": 1, "ids": ["t2"]}
        assert "b" in r["readers"]["agents"] and r["readers"]["steps_total"] >= 1
        assert r["truncated"] is False and r["depth"] == 8

        r = (await ok(c, "impact", agent_id="a", kind="fact", id=f2))["impact"]
        assert r["facts"]["ids"] == [f2] and r["decisions"]["total"] == 0

        r = (await ok(c, "impact", agent_id="a", kind="task", id="t1"))["impact"]
        assert r["tasks"] == {"total": 2, "ids": ["t2", "t3"]}
        r = (await ok(c, "impact", agent_id="a", kind="task", id="t1", depth=1))["impact"]
        assert r["tasks"]["ids"] == ["t2"]
        capped = (await ok(c, "impact", agent_id="a", kind="source", id=src, max_items=1))["impact"]
        assert capped["facts"]["total"] == 2 and len(capped["facts"]["ids"]) == 1


async def test_impact_writes_no_memory_and_no_read_edges(server, client, tenant):
    async with Client(server) as c:
        src, f1, f2, dec = await _world(c)
        before = rows(client, tenant, "MATCH (:Step)-[r:READ]->(:Fact) RETURN count(r)")
        status = rows(client, tenant, "MATCH (f:Fact) RETURN f.id, f.status ORDER BY f.id")
        total = rows(client, tenant, "MATCH (n) WHERE NOT n:ToolCall AND NOT n:Step RETURN count(n)")
        for kind, i in (("source", src), ("fact", f1), ("task", "t1")):
            await ok(c, "impact", agent_id="a", kind=kind, id=i)
        assert rows(client, tenant, "MATCH (:Step)-[r:READ]->(:Fact) RETURN count(r)") == before
        assert rows(client, tenant, "MATCH (f:Fact) RETURN f.id, f.status ORDER BY f.id") == status
        assert rows(client, tenant, "MATCH (n) WHERE NOT n:ToolCall AND NOT n:Step RETURN count(n)") == total


@pytest.mark.parametrize("kind", ["source", "fact", "task"])
async def test_impact_unknown_id_is_a_clear_error(server, kind):
    async with Client(server) as c:
        text = await err(c, "impact", agent_id="a", kind=kind, id="nope")
        assert "nope" in text


async def test_impact_argument_bounds(server, client, tenant):
    async with Client(server) as c:
        src, *_ = await _world(c)
        assert "depth" in await err(c, "impact", agent_id="a", kind="source", id=src, depth=13)
        assert "depth" in await err(c, "impact", agent_id="a", kind="task", id="t1", depth=0)
        assert "kind" in await err(c, "impact", agent_id="a", kind="decision", id=src)
