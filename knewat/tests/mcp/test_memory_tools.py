"""MCP tests for activation-based forgetting (P7-K): READ provenance, recall rows, memory tools."""

from __future__ import annotations

import json

import pytest

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


# ---------------------------------------------------------------- slice 2: surprise
async def test_assert_fact_output_carries_surprise(server, client, tenant):
    async with Client(server) as c:
        a = await ok(c, "assert_fact", agent_id="a", subject="API", predicate="version", value="v1")
        assert a["surprise"] == 0.5
        b = await ok(c, "assert_fact", agent_id="b", subject="API", predicate="version", value="v2")
        assert b["contradicts"] == [a["fact_id"]] and b["surprise"] == 0.9
        dup = await ok(c, "assert_fact", agent_id="c", subject="API", predicate="version", value="v2")
        assert dup["duplicate_of"] == b["fact_id"] and dup["surprise"] is None


# ---------------------------------------------------------------- slice 5: the memory tools
DAY = 86_400_000


async def _seed(c, client, tenant):
    """Two facts; the first is made 300 days old and faint, the second is fresh."""
    a = await ok(
        c, "assert_fact", agent_id="a", subject="Old Thing", predicate="note", value="forgotten detail"
    )
    b = await ok(c, "assert_fact", agent_id="a", subject="New Thing", predicate="note", value="fresh detail")
    client.graph(graph_name(tenant)).query(
        "MATCH (f:Fact {id:$f})-[a:ASSERTED_BY]->(:Agent) "
        "SET f.created_at = f.created_at - $d, f.valid_from = f.valid_from - $d, a.at = a.at - $d, "
        "f.surprise = 0.0",
        {"f": a["fact_id"], "d": 300 * DAY},
    )
    return a["fact_id"], b["fact_id"]


async def test_pin_and_unpin_fact(server, client, tenant):
    async with Client(server) as c:
        old, _ = await _seed(c, client, tenant)
        p = await ok(c, "pin_fact", agent_id="a", fact_id=old)
        assert p["pinned"] is True and p["tool_call_id"]
        assert rows(client, tenant, "MATCH (f:Fact {id:$f}) RETURN f.pinned", f=old) == [[True]]
        s = (await ok(c, "memory_strength", agent_id="a", fact_id=old))["strength"]
        assert s["protected"] and s["protect_reasons"] == ["pinned"]
        u = await ok(c, "unpin_fact", agent_id="a", fact_id=old)
        assert u["pinned"] is False
        assert rows(client, tenant, "MATCH (f:Fact {id:$f}) RETURN f.pinned", f=old) == [[False]]
        assert "no-such-fact" in await err(c, "pin_fact", agent_id="a", fact_id="no-such-fact")
        assert "no-such-fact" in await err(c, "unpin_fact", agent_id="a", fact_id="no-such-fact")
    links = rows(client, tenant, "MATCH (t:ToolCall {tool:'pin_fact'})-[:UPDATED]->(f:Fact) RETURN f.id")
    assert links == [[old]]


async def test_memory_strength_explains_and_does_not_count_as_a_use(server, client, tenant):
    async with Client(server) as c:
        old, new = await _seed(c, client, tenant)
        s1 = (await ok(c, "memory_strength", agent_id="b", fact_id=old, step=1))["strength"]
        s2 = (await ok(c, "memory_strength", agent_id="b", fact_id=old, step=2))["strength"]
        assert s1["activation"] == pytest.approx(s2["activation"], abs=1e-6), "inspecting is not using"
        for key in ("activation", "a0", "multiplier", "floor", "protected", "protect_reasons", "explanation"):
            assert key in s1
        assert 0.9 <= s1["multiplier"] < 0.95 and "never used" in s1["explanation"]
        fresh = (await ok(c, "memory_strength", agent_id="b", fact_id=new))["strength"]
        assert fresh["multiplier"] > s1["multiplier"]
        assert "ghost" in await err(c, "memory_strength", agent_id="b", fact_id="ghost")
    assert rows(client, tenant, "MATCH (:Step)-[r:READ]->(:Fact) RETURN count(r)") == [[0]]


async def test_sweep_dry_run_then_real_then_restore(server, client, tenant):
    async with Client(server) as c:
        old, _new = await _seed(c, client, tenant)
        dry = (await ok(c, "memory_sweep", agent_id="a"))["sweep"]
        assert dry["dry_run"] is True and [x["fact_id"] for x in dry["candidates"]] == [old]
        assert dry["would_move"] == 1 and dry["moved"] == []
        assert rows(client, tenant, "MATCH (f:Fact {id:$f}) RETURN f.status", f=old) == [["active"]]
        real = (await ok(c, "memory_sweep", agent_id="a", dry_run=False))["sweep"]
        assert real["moved"] == [old]
        got = rows(client, tenant, "MATCH (f:Fact {id:$f}) RETURN f.status, f.prior_status", f=old)
        assert got == [["dormant", "active"]]
        # dormant facts are hidden from recall unless asked for
        r = await ok(c, "recall", agent_id="a", query="Old Thing forgotten detail", k=10)
        assert old not in [x["fact_id"] for x in r["facts"]]
        r = await ok(
            c, "recall", agent_id="a", query="Old Thing forgotten detail", k=10, include_dormant=True
        )
        assert old in [x["fact_id"] for x in r["facts"]]
        back = await ok(c, "restore_fact", agent_id="a", fact_id=old)
        assert back["restored"] is True and back["status"] == "active"
        got = rows(client, tenant, "MATCH (f:Fact {id:$f}) RETURN f.status, f.prior_status", f=old)
        assert got == [["active", None]]
        again = await ok(c, "restore_fact", agent_id="a", fact_id=old)
        assert again["restored"] is False
        assert "ghost" in await err(c, "restore_fact", agent_id="a", fact_id="ghost")
    # the real sweep and the restore are audited as updates of exactly that fact
    for tool in ("memory_sweep", "restore_fact"):
        got = rows(client, tenant, "MATCH (t:ToolCall {tool:$t})-[:UPDATED]->(f:Fact) RETURN f.id", t=tool)
        assert got == [[old]], tool
    assert rows(client, tenant, "MATCH (f:Fact) RETURN count(f)") == [[2]], "nothing was deleted"


async def test_sweep_of_an_unknown_scope_and_bad_arguments(server, client, tenant):
    async with Client(server) as c:
        r = await ok(c, "memory_sweep", agent_id="a", scope="project:nope")
        assert r["sweep"] is None
        assert "limit" in await err(c, "memory_sweep", agent_id="a", limit=0)
        assert "limit" in await err(c, "memory_sweep", agent_id="a", limit=201)
        assert "threshold" in await err(c, "memory_sweep", agent_id="a", threshold=1e9)
        assert "dry_run" in await err(c, "memory_sweep", agent_id="a", dry_run="maybe")
    assert rows(client, tenant, "MATCH (s:Scope) RETURN count(s)") == [[0]], "a sweep never creates a scope"


async def test_memory_tools_open_a_step_for_the_agent(server, client, tenant):
    async with Client(server) as c:
        old, _ = await _seed(c, client, tenant)
        await ok(c, "pin_fact", agent_id="z", fact_id=old, step=7)
        await ok(c, "memory_strength", agent_id="z", fact_id=old, step=7)
    got = rows(
        client,
        tenant,
        "MATCH (t:ToolCall)-[:IN_STEP]->(s:Step {agent_id:'z'}) RETURN t.tool, s.n ORDER BY t.tool",
    )
    assert got == [["memory_strength", 7], ["pin_fact", 7]]


async def test_recall_arguments_forgetting_and_include_dormant(server, client, tenant):
    async with Client(server) as c:
        await _seed(c, client, tenant)
        on = await ok(c, "recall", agent_id="a", query="detail", k=5, detail="full")
        assert all(isinstance(x["activation"], float) and x["protected"] is False for x in on["facts"])
        off = await ok(c, "recall", agent_id="a", query="detail", k=5, forgetting=False, detail="full")
        assert all(x["activation"] is None and x["protected"] is None for x in off["facts"])
        for key in ("verify_state", "suspect_since", "suspect_reason", "surprise"):
            assert key in on["facts"][0]
        assert "forgetting" in await err(c, "recall", agent_id="a", query="x", forgetting="sometimes")
