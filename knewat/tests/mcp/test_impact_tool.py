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
        assert (r["decisions"]["total"], r["decisions"]["ids"]) == (1, [dec])
        assert r["decisions"]["earliest_at"] == r["decisions"]["latest_at"] > 0
        assert r["facts"]["earliest_at"] <= r["facts"]["latest_at"] and len(r["facts"]["earliest"]) == 2
        assert r["decisions"]["ids_truncated"] is False  # P9-f: a cut list is never silent
        assert (r["tasks"]["total"], r["tasks"]["ids"], r["tasks"]["ids_truncated"]) == (1, ["t2"], False)
        assert "b" in r["readers"]["agents"] and r["readers"]["steps_total"] >= 1
        assert r["truncated"] is False and r["depth"] == 8

        r = (await ok(c, "impact", agent_id="a", kind="fact", id=f2))["impact"]
        assert r["facts"]["ids"] == [f2] and r["decisions"]["total"] == 0

        r = (await ok(c, "impact", agent_id="a", kind="task", id="t1"))["impact"]
        assert r["tasks"] == {
            "total": 2,
            "ids": ["t2", "t3"],
            "offset": 0,
            "next_offset": None,
            "ids_truncated": False,
        }
        r = (await ok(c, "impact", agent_id="a", kind="task", id="t1", depth=1))["impact"]
        assert r["tasks"]["ids"] == ["t2"]
        capped = (await ok(c, "impact", agent_id="a", kind="source", id=src, max_items=1))["impact"]
        assert capped["facts"]["total"] == 2 and len(capped["facts"]["ids"]) == 1


async def test_impact_lists_facts_with_their_times_earliest_first(server, client, tenant):
    async with Client(server) as c:
        src, f1, f2, dec = await _world(c)
        r = (await ok(c, "impact", agent_id="a", kind="source", id=src, order="created_at", max_items=1))[
            "impact"
        ]
        rec = r["facts"]["records"]
        assert r["facts"]["order"] == "created_at" and len(rec) == 1 and rec[0]["id"] == f1  # f1 came first
        assert rec[0]["status"] == "active" and rec[0]["created_at"] > 0 and rec[0]["valid_from"] > 0


async def test_impact_never_hides_a_cut_list(server, client, tenant):
    async with Client(server) as c:
        src, f1, f2, dec = await _world(c)
        r = await ok(c, "impact", agent_id="a", kind="source", id=src, max_items=1, probe_ids=[f1, f2, "zz"])
        facts = r["impact"]["facts"]
        assert facts["total"] == 2 and len(facts["ids"]) == 1 and facts["ids_truncated"] is True
        assert facts["next_offset"] == 1 and facts["probes"] == {f1: True, f2: True, "zz": False}
        nxt = (await ok(c, "impact", agent_id="a", kind="source", id=src, max_items=1, offset=1))["impact"]
        assert nxt["facts"]["next_offset"] is None and sorted(facts["ids"] + nxt["facts"]["ids"]) == sorted(
            [f1, f2]
        )
        t = await ok(c, "impact", agent_id="a", kind="task", id="t1", max_items=1, probe_ids=["t3", "t1"])
        tasks = t["impact"]["tasks"]
        assert tasks["ids"] == ["t2"] and tasks["ids_truncated"] is True and tasks["next_offset"] == 1
        assert tasks["probes"] == {"t3": True, "t1": False}


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
