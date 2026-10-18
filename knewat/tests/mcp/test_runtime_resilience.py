"""Runtime resilience: a replaced tenant graph heals (P5C-01), same-agent parallel calls keep Step numbers and
times consistent (P5C-04), a degraded lineage/audit write is reported (P5C-05), and DB failures map to clear
tool errors (C-02)."""

from __future__ import annotations

import asyncio
import json

import pytest
from redis.exceptions import ConnectionError as RedisConnectionError

from knewat.embed import HashEmbedder
from knewat.graph.tenancy import graph_name
from knewat.lineage import Lineage
from knewat.mcp.runtime import Runtime
from knewat.mcp.server import build_server
from knewat.relay import Relay
from mcp import Client


async def ok(c: Client, tool: str, /, **args) -> dict:
    res = await c.call_tool(tool, args)
    assert not res.is_error, res.content[0].text
    return json.loads(res.content[0].text)


async def err(c: Client, tool: str, /, **args) -> str:
    res = await c.call_tool(tool, args)
    assert res.is_error, res.content[0].text
    return res.content[0].text


def q(client, tenant, cypher: str, **params):
    return client.graph(graph_name(tenant)).ro_query(cypher, params or None).result_set


@pytest.fixture
def lazy_runtime(client, tenant) -> Runtime:
    """A runtime that trusts its cached tenant state for an hour (only the on-error path can heal it)."""
    return Runtime(client=client, embedder=HashEmbedder(), stdio_tenant=tenant, schema_recheck_s=3600)


# ---------------------------------------------------------------- P5C-01: the tenant graph is replaced
async def test_tenant_heals_after_its_graph_is_deleted(lazy_runtime, client, tenant):
    async with Client(build_server(lazy_runtime)) as c:
        f = await ok(c, "assert_fact", agent_id="a", subject="S", predicate="p", value="v1")
        assert (await ok(c, "recall", agent_id="a", query="S p"))["count"] == 1
        client.delete_graph(graph_name(tenant))  # a demo reset / restore under the running server

        r = await ok(c, "recall", agent_id="a", query="S p")  # read-first tool on a missing graph
        assert r["count"] == 0
        f2 = await ok(c, "assert_fact", agent_id="a", subject="S", predicate="p", value="v2")
        assert f2["fact_id"] != f["fact_id"] and f2["superseded"] == []
        assert (await ok(c, "recall", agent_id="a", query="S p"))["count"] == 1

        # the schema was re-applied: indexes exist again, and the cached scope id belongs to the new graph
        assert q(client, tenant, "CALL db.indexes() YIELD label RETURN count(label)")[0][0] > 0
        assert q(client, tenant, "MATCH (s:Scope {name:'global'}) RETURN s.id")[0][0] == f2["scope_id"]


async def test_stale_scope_id_after_graph_replacement_is_not_reused(lazy_runtime, client, tenant):
    async with Client(build_server(lazy_runtime)) as c:
        await ok(c, "assert_fact", agent_id="a", subject="S", predicate="p", value="v1")
        client.delete_graph(graph_name(tenant))
        r = await ok(c, "assert_fact", agent_id="a", subject="S", predicate="p", value="v2")  # write first
        assert r["fact_id"]
        assert q(client, tenant, "MATCH (f:Fact) RETURN count(f)") == [[1]]


async def test_write_first_tool_after_delete_gets_the_schema_back(client, tenant):
    rt = Runtime(client=client, embedder=HashEmbedder(), stdio_tenant=tenant, schema_recheck_s=0)
    async with Client(build_server(rt)) as c:
        await ok(c, "start_session", agent_id="a")
        client.delete_graph(graph_name(tenant))
        await ok(
            c, "start_session", agent_id="a"
        )  # would recreate the graph WITHOUT indexes if state is trusted
        assert q(client, tenant, "CALL db.indexes() YIELD label RETURN count(label)")[0][0] > 0


# ---------------------------------------------------------------- P5C-04: parallel calls of one agent
async def test_parallel_calls_of_one_agent_get_contiguous_steps_in_time_order(server, client, tenant):
    async with Client(server) as c:
        await asyncio.gather(*(ok(c, "ready_tasks", agent_id="par") for _ in range(30)))
    steps = q(client, tenant, "MATCH (s:Step {agent_id:'par'}) RETURN s.n, s.at ORDER BY s.n")
    assert [n for n, _ in steps] == list(range(1, 31))
    ats = [a for _, a in steps]
    assert ats == sorted(ats), "Step.at must not go backwards as n grows"
    # every ToolCall was recorded in its own step, no earlier than the step started
    calls = q(
        client, tenant, "MATCH (t:ToolCall {agent_id:'par'})-[:IN_STEP]->(s:Step) RETURN s.n, t.at, s.at"
    )
    assert len(calls) == 30 and all(t_at >= s_at for _, t_at, s_at in calls)


async def test_parallel_explicit_steps_are_never_remapped(server, client, tenant):
    async with Client(server) as c:
        await asyncio.gather(*(ok(c, "ready_tasks", agent_id="par", step=k) for k in range(1, 21)))
    got = q(client, tenant, "MATCH (t:ToolCall {agent_id:'par'})-[:IN_STEP]->(s:Step) RETURN t.step, s.n")
    assert len(got) == 20 and all(requested == n for requested, n in got)
    assert sorted(n for (n,) in q(client, tenant, "MATCH (s:Step) RETURN s.n")) == list(range(1, 21))


async def test_different_agents_do_not_wait_for_each_other(server):
    async with Client(server) as c:
        await asyncio.gather(
            *(ok(c, "ready_tasks", agent_id=f"agent-{i % 4}") for i in range(24)),
        )


# ---------------------------------------------------------------- P5C-05: degraded bookkeeping is reported
async def test_failed_step_link_is_retried_once_and_then_reported(monkeypatch, server, client, tenant):
    real = Lineage.link_step
    calls = {"n": 0}

    def flaky_once(self, *a, **kw):
        calls["n"] += 1
        if calls["n"] == 1:
            raise RedisConnectionError("transient")
        return real(self, *a, **kw)

    async with Client(server) as c:
        # the WROTE edge of a new fact is written by the assert statement itself (no link_step call); a new
        # value for the same subject + predicate supersedes (READs) the old fact: that READ is linked after
        await ok(c, "assert_fact", agent_id="a", subject="S", predicate="p", value="v")
        monkeypatch.setattr(Lineage, "link_step", flaky_once)
        r = await ok(c, "assert_fact", agent_id="a", subject="S", predicate="p", value="w")
        assert (
            "lineage_degraded" not in r and r["tool_call_id"] and calls["n"] == 2
        )  # failed once, retried once
        assert q(client, tenant, "MATCH (:Step)-[w:WROTE]->(:Fact) RETURN count(w)") == [[2]]

        def always_fail(self, *a, **kw):
            raise RedisConnectionError("down")

        monkeypatch.setattr(Lineage, "link_step", always_fail)
        r = await ok(c, "assert_fact", agent_id="a", subject="S", predicate="p", value="x")
        assert r["lineage_degraded"] is True and r["fact_id"] and r["tool_call_id"]
        # ... but the new fact still has its WROTE edge: that is the point of folding it into the write
        assert q(
            client, tenant, "MATCH (:Step)-[w:WROTE]->(:Fact {id: $i}) RETURN count(w)", i=r["fact_id"]
        ) == [[1]]


async def test_failed_step_is_reported(monkeypatch, server):
    def boom(self, *a, **kw):
        raise RedisConnectionError("down")

    monkeypatch.setattr(Lineage, "record_step", boom)
    async with Client(server) as c:
        r = await ok(c, "assert_fact", agent_id="a", subject="S", predicate="p", value="v")
        assert r["lineage_degraded"] is True and r["fact_id"]


async def test_failed_audit_row_is_reported(monkeypatch, server):
    def boom(*a, **kw):
        raise RedisConnectionError("down")

    monkeypatch.setattr("knewat.mcp.runtime.record_tool_call", boom)
    async with Client(server) as c:
        r = await ok(c, "assert_fact", agent_id="a", subject="S", predicate="p", value="v")
        assert r["audit_degraded"] is True and "tool_call_id" not in r and r["fact_id"]


async def test_healthy_calls_carry_no_degraded_flags(server):
    async with Client(server) as c:
        r = await ok(c, "assert_fact", agent_id="a", subject="S", predicate="p", value="v")
    assert "lineage_degraded" not in r and "audit_degraded" not in r


# ---------------------------------------------------------------- C-02: DB failures become clear tool errors
async def test_database_errors_are_generic_and_leak_nothing(monkeypatch, server):
    def redis_down(self, *a, **kw):
        raise RedisConnectionError("MATCH (n) secret query text")

    monkeypatch.setattr(Relay, "ready_tasks", redis_down)
    async with Client(server) as c:
        text = await err(c, "ready_tasks", agent_id="a")
    assert "graph database rejected the request" in text and "MATCH" not in text and "secret" not in text


async def test_unexpected_errors_are_internal_and_leak_nothing(monkeypatch, server):
    def bug(self, *a, **kw):
        raise RuntimeError("secret internal detail")

    monkeypatch.setattr(Relay, "ready_tasks", bug)
    async with Client(server) as c:
        text = await err(c, "ready_tasks", agent_id="a")
    assert "internal error" in text and "secret" not in text
