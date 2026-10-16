"""P9-e: audit modes ``off | light | full`` per tenant / tool class, the per-call ``audit`` argument,
read-only tenants that never create a graph, and a no-write proof (Redis command counters).

Layers: (1) the tool classification and the policy table (no database); (2) the Runtime modes over the
in-memory MCP client; (3) the no-write proof. The guard side is in ``deploy/tests/test_guard.py``.
"""

from __future__ import annotations

import json

import pytest

from mcp import Client
from plexus.embed import HashEmbedder
from plexus.graph.tenancy import graph_name
from plexus.mcp.audit_policy import AuditPolicy
from plexus.mcp.runtime import Outcome, Runtime
from plexus.mcp.server import PlexusServer, build_server
from plexus.mcp.toolkit import ToolTable, all_tool_defs

READ_TOOLS = {
    "recall",
    "fact_history",
    "best_procedure",
    "ready_tasks",
    "task_status",
    "blocked_by_failure",
    "why",
    "why_recalled",
    "who_knew",
    "knew_at",
    "as_of",
    "memory_strength",
    "facts_to_verify",
    "docs_to_update",
}


# ------------------------------------------------------------------------------------ 1. classification
def test_every_tool_has_a_kind_and_the_read_set_is_exactly_the_documented_one():
    defs = {d.name: d for d in all_tool_defs()}
    assert {n for n, d in defs.items() if d.kind == "read"} == READ_TOOLS
    assert {d.kind for d in defs.values()} == {"read", "write"}


def test_only_recall_is_an_exposure_tool():
    assert {d.name for d in all_tool_defs() if d.exposure} == {"recall"}


def test_an_unmarked_tool_is_a_write_tool():
    table = ToolTable()

    @table
    def probe(ts, m, agent_id, step=None):  # pragma: no cover (never run)
        raise AssertionError

    (d,) = list(table)
    assert d.kind == "write" and d.exposure is False


def test_exposure_requires_a_read_tool():
    with pytest.raises(TypeError):
        ToolTable()(kind="write", exposure=True)(lambda ts, m, agent_id, step=None: None)


# ------------------------------------------------------------------------------------ 1b. policy table
def test_default_mode_is_full_and_overrides_match_by_glob_first_wins():
    p = AuditPolicy.from_env({})
    assert p.tenant_mode("anything") == "full"
    p = AuditPolicy.from_env(
        {"PLEXUS_AUDIT_MODE": "light", "PLEXUS_AUDIT_MODES": "demo*=off, team_*=full ,x_*=light"}
    )
    assert p.tenant_mode("demo") == "off" and p.tenant_mode("demo_scripted") == "off"
    assert p.tenant_mode("team_abcd") == "full"
    assert p.tenant_mode("x_1") == "light"
    assert p.tenant_mode("other") == "light"  # the default
    p = AuditPolicy.from_env({"PLEXUS_AUDIT_MODES": "t*=off,team_*=full"})
    assert p.tenant_mode("team_a") == "off"  # first match wins


@pytest.mark.parametrize(
    "env",
    [
        {"PLEXUS_AUDIT_MODE": "loud"},
        {"PLEXUS_AUDIT_MODES": "demo*"},
        {"PLEXUS_AUDIT_MODES": "demo*=quiet"},
        {"PLEXUS_AUDIT_MODES": "=off"},
    ],
)
def test_a_bad_audit_setting_fails_loudly_at_startup(env):
    with pytest.raises(ValueError):
        AuditPolicy.from_env(env)


@pytest.mark.parametrize(
    "tenant_mode,kind,exposure,requested,expected",
    [
        # writes: never lowered, refused (mode off) when the tenant is off
        ("full", "write", False, None, "full"),
        ("light", "write", False, None, "full"),
        ("off", "write", False, None, "off"),
        # meta reads follow the tenant, and a per-call 'light' only lowers
        ("full", "read", False, None, "full"),
        ("full", "read", False, "light", "light"),
        ("light", "read", False, None, "light"),
        ("light", "read", False, "full", "light"),  # never upgrades beyond the tenant mode
        ("off", "read", False, "light", "off"),
        ("off", "read", False, None, "off"),
        # exposure reads (recall): full unless the tenant is off; 'light' may lower it on request
        ("full", "read", True, None, "full"),
        ("light", "read", True, None, "full"),
        ("full", "read", True, "light", "light"),
        ("light", "read", True, "light", "light"),
        ("off", "read", True, None, "off"),
        ("off", "read", True, "light", "off"),
    ],
)
def test_effective_mode_table(tenant_mode, kind, exposure, requested, expected):
    p = AuditPolicy(default=tenant_mode)
    assert p.effective("t", kind, exposure, requested) == expected


# ------------------------------------------------------------------------------------ 2. Runtime modes
def _runtime(client, tenant, mode: str = "full", table: str = ""):
    env = {"PLEXUS_AUDIT_MODE": mode, "PLEXUS_AUDIT_MODES": table}
    return Runtime(
        client=client,
        embedder=HashEmbedder(),
        stdio_tenant=tenant,
        audit_policy=AuditPolicy.from_env(env),
    )


def _q(client, tenant, cypher: str):
    return client.graph(graph_name(tenant)).ro_query(cypher).result_set


def _count(client, tenant, label: str) -> int:
    return _q(client, tenant, f"MATCH (n:{label}) RETURN count(n)")[0][0]


def _totals(client, tenant) -> tuple[int, int]:
    return (
        _q(client, tenant, "MATCH (n) RETURN count(n)")[0][0],
        _q(client, tenant, "MATCH ()-[r]->() RETURN count(r)")[0][0],
    )


def _graphs(client) -> set[str]:
    return set(client.db.list_graphs())


async def _ok(c: Client, tool: str, /, **args) -> dict:
    res = await c.call_tool(tool, args)
    assert not res.is_error, res.content[0].text
    return json.loads(res.content[0].text)


async def _err(c: Client, tool: str, /, **args) -> str:
    res = await c.call_tool(tool, args)
    assert res.is_error, res.content[0].text
    return res.content[0].text


async def _seed(client, tenant) -> dict:
    """A fact, a task and a decision written in full mode, so there is something to read."""
    async with Client(build_server(_runtime(client, tenant))) as c:
        f = await _ok(c, "assert_fact", agent_id="seed", subject="API", predicate="version", value="v2")
        t = await _ok(c, "create_tasks", agent_id="seed", tasks=[{"title": "ship"}])
        task = t["task_ids"][0]
        d = await _ok(
            c,
            "record_decision",
            agent_id="seed",
            task_id=task,
            text="use v2",
            based_on_fact_ids=[f["fact_id"]],
        )
        return {"fact": f["fact_id"], "task": task, "decision": d["decision_id"]}


async def test_the_audit_argument_is_offered_on_read_tools_only(server):
    async with Client(server) as c:
        tools = (await c.list_tools()).tools
    kinds = {d.name: d.kind for d in all_tool_defs()}
    for t in tools:
        has = "audit" in t.input_schema["properties"]
        assert has == (kinds[t.name] == "read"), t.name
        if has:
            assert "audit" not in t.input_schema.get("required", [])


async def test_full_mode_is_unchanged(client, tenant):
    async with Client(build_server(_runtime(client, tenant))) as c:
        await _ok(c, "assert_fact", agent_id="a", subject="S", predicate="p", value="v")
        r = await _ok(c, "recall", agent_id="a", query="S p")
        assert r["recall_id"] and r["tool_call_id"] and "audit" not in r
    assert _count(client, tenant, "Recall") == 1 and _count(client, tenant, "Step") == 2


async def test_per_call_light_on_recall_writes_a_toolcall_only(client, tenant):
    async with Client(build_server(_runtime(client, tenant))) as c:
        await _ok(c, "assert_fact", agent_id="a", subject="S", predicate="p", value="v")
        before = {k: _count(client, tenant, k) for k in ("Step", "Recall", "ToolCall")}
        reads = _q(client, tenant, "MATCH ()-[r:READ]->() RETURN count(r)")
        r = await _ok(c, "recall", agent_id="a", query="S p", audit="light")
        assert r["count"] == 1 and r["audit"] == "light"
        assert r["recall_id"] is None and r["tool_call_id"]
    after = {k: _count(client, tenant, k) for k in ("Step", "Recall", "ToolCall")}
    assert after == {**before, "ToolCall": before["ToolCall"] + 1}
    q = "MATCH (t:ToolCall {tool:'recall'}) OPTIONAL MATCH (t)-[:IN_STEP]->(s) RETURN t.wrote, count(s)"
    assert _q(client, tenant, q) == [[False, 0]]
    assert _q(client, tenant, "MATCH ()-[r:READ]->() RETURN count(r)") == reads


async def test_light_tenant_keeps_recall_full_but_lightens_meta_reads(client, tenant):
    async with Client(build_server(_runtime(client, tenant, mode="light"))) as c:
        f = await _ok(c, "assert_fact", agent_id="a", subject="S", predicate="p", value="v")
        steps = _count(client, tenant, "Step")
        r = await _ok(c, "recall", agent_id="a", query="S p")
        assert r["recall_id"] and "audit" not in r  # exposure: full
        assert _count(client, tenant, "Step") == steps + 1
        h = await _ok(c, "fact_history", agent_id="a", subject="S", predicate="p")
        assert h["audit"] == "light" and h["tool_call_id"]
        assert (await _ok(c, "memory_strength", agent_id="a", fact_id=f["fact_id"]))["audit"] == "light"
        assert _count(client, tenant, "Step") == steps + 1  # no Step for the meta reads
        # a per-call 'full' never upgrades a meta read beyond the tenant mode
        h2 = await _ok(c, "fact_history", agent_id="a", subject="S", predicate="p", audit="full")
        assert h2["audit"] == "light"
        # a per-call 'light' lowers recall
        assert (await _ok(c, "recall", agent_id="a", query="S p", audit="light"))["recall_id"] is None


async def test_light_never_touches_write_tools(client, tenant):
    async with Client(build_server(_runtime(client, tenant, mode="light"))) as c:
        r = await _ok(c, "assert_fact", agent_id="a", subject="S", predicate="p", value="v")
        assert "audit" not in r
    assert _count(client, tenant, "Step") == 1


async def test_off_tenant_reads_write_nothing_and_writes_are_refused(client, tenant):
    ids = await _seed(client, tenant)
    before = _totals(client, tenant)
    async with Client(build_server(_runtime(client, tenant, mode="off"))) as c:
        r = await _ok(c, "recall", agent_id="visitor", query="API version")
        assert r["count"] == 1 and r["audit"] == "off"
        assert r["tool_call_id"] is None and r["recall_id"] is None
        assert (await _ok(c, "task_status", agent_id="visitor", task_id=ids["task"]))["audit"] == "off"
        assert (await _ok(c, "why", agent_id="visitor", node_id=ids["decision"]))["audit"] == "off"
        msg = await _err(c, "assert_fact", agent_id="visitor", subject="x", predicate="y", value="z")
        assert "read-only" in msg and "assert_fact" in msg
        assert "read-only" in await _err(c, "create_tasks", agent_id="visitor", tasks=[{"title": "t"}])
        assert "read-only" in await _err(c, "start_session", agent_id="visitor")
    assert _totals(client, tenant) == before  # not a node, not an edge


async def test_off_recall_does_not_move_the_ranking(client, tenant):
    await _seed(client, tenant)
    async with Client(build_server(_runtime(client, tenant, mode="off"))) as c:
        first = await _ok(c, "recall", agent_id="v", query="API version")
        for _ in range(3):
            again = await _ok(c, "recall", agent_id="v", query="API version")
        assert [f["activation"] for f in first["facts"]] == [f["activation"] for f in again["facts"]]
        assert [f["score"] for f in first["facts"]] == [f["score"] for f in again["facts"]]


async def test_off_tenant_never_creates_a_graph(client, new_tenant):
    ghost = new_tenant()
    before = _graphs(client)
    calls = [
        ("recall", {"query": "API version"}),
        ("fact_history", {"subject": "API", "predicate": "version"}),
        ("ready_tasks", {}),
        ("as_of", {"subject": "API", "predicate": "version", "t": 1}),
    ]
    async with Client(build_server(_runtime(client, ghost, mode="off"))) as c:
        for tool, args in calls:
            msg = await _err(c, tool, agent_id="visitor", **args)
            assert "read-only" in msg and "not created" in msg, (tool, msg)
        msg = await _err(c, "assert_fact", agent_id="v", subject="s", predicate="p", value="v")
        assert "read-only" in msg
    assert _graphs(client) == before and graph_name(ghost) not in _graphs(client)


async def test_off_tenant_does_not_recreate_a_deleted_graph(client, tenant):
    await _seed(client, tenant)
    rt = _runtime(client, tenant, mode="off")
    async with Client(build_server(rt)) as c:
        assert (await _ok(c, "recall", agent_id="v", query="API version"))["count"] == 1
        client.delete_graph(graph_name(tenant))
        rt.schema_recheck_s = 0
        assert "not created" in await _err(c, "recall", agent_id="v", query="API version")
    assert graph_name(tenant) not in _graphs(client)


# ---- a mislabelled read tool
def _mislabelled(rt):
    table = ToolTable()

    @table(kind="read")
    def sneaky(ts, m, agent_id: str, step: int | None = None) -> Outcome:
        """A tool that claims to be a read but starts a session (a write). Test double only."""
        return Outcome({"session_id": ts.engram(m).start_session(agent_id, "x")})

    mcp = PlexusServer("t", log_level="WARNING")
    table.register(mcp, rt)
    return mcp


async def test_a_mislabelled_read_tool_fails_closed_on_an_off_tenant(client, tenant):
    await _seed(client, tenant)
    before = _totals(client, tenant)
    async with Client(_mislabelled(_runtime(client, tenant, mode="off"))) as c:
        await _err(c, "sneaky", agent_id="v")
    assert _totals(client, tenant) == before


async def test_a_mislabelled_read_tool_is_audited_in_full_on_a_light_tenant(client, tenant):
    async with Client(_mislabelled(_runtime(client, tenant, mode="light"))) as c:
        r = await _ok(c, "sneaky", agent_id="v")
        assert r["tool_call_id"] and "audit" not in r  # demoted to full: no 'light' claim in the result
    assert _q(client, tenant, "MATCH (t:ToolCall {tool:'sneaky'}) RETURN t.wrote") == [[True]]
    assert _count(client, tenant, "Step") == 1
