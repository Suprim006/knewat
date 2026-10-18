"""P9-e: audit modes ``off | light | full`` per tenant / tool class, the per-call ``audit`` argument,
read-only tenants that never create a graph, and a no-write proof (Redis command counters).

Layers: (1) the tool classification and the policy table (no database); (2) the Runtime modes over the
in-memory MCP client; (3) the no-write proof. The guard side is in ``deploy/tests/test_guard.py``.
"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest

from knewat.embed import HashEmbedder
from knewat.graph.tenancy import graph_name
from knewat.mcp.audit_policy import AuditPolicy
from knewat.mcp.runtime import Outcome, Runtime
from knewat.mcp.server import KnewatServer, build_server
from knewat.mcp.toolkit import ToolTable, all_tool_defs
from mcp import Client

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
    table = ToolTable(listed=False)

    @table
    def probe(ts, m, agent_id, step=None):  # pragma: no cover (never run)
        raise AssertionError

    (d,) = list(table)
    assert d.kind == "write" and d.exposure is False


def test_exposure_requires_a_read_tool():
    with pytest.raises(TypeError):
        ToolTable(listed=False)(kind="write", exposure=True)(lambda ts, m, agent_id, step=None: None)


# ------------------------------------------------------------------------------------ 1b. policy table
def test_default_mode_is_full_and_overrides_match_by_glob_first_wins():
    p = AuditPolicy.from_env({})
    assert p.tenant_mode("anything") == "full"
    p = AuditPolicy.from_env(
        {"KNEWAT_AUDIT_MODE": "light", "KNEWAT_AUDIT_MODES": "demo*=off, team_*=full ,x_*=light"}
    )
    assert p.tenant_mode("demo") == "off" and p.tenant_mode("demo_scripted") == "off"
    assert p.tenant_mode("team_abcd") == "full"
    assert p.tenant_mode("x_1") == "light"
    assert p.tenant_mode("other") == "light"  # the default
    p = AuditPolicy.from_env({"KNEWAT_AUDIT_MODES": "t*=off,team_*=full"})
    assert p.tenant_mode("team_a") == "off"  # first match wins


@pytest.mark.parametrize(
    "env",
    [
        {"KNEWAT_AUDIT_MODE": "loud"},
        {"KNEWAT_AUDIT_MODES": "demo*"},
        {"KNEWAT_AUDIT_MODES": "demo*=quiet"},
        {"KNEWAT_AUDIT_MODES": "=off"},
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
    env = {"KNEWAT_AUDIT_MODE": mode, "KNEWAT_AUDIT_MODES": table}
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
        first = await _ok(c, "recall", agent_id="v", query="API version", detail="full")
        for _ in range(3):
            again = await _ok(c, "recall", agent_id="v", query="API version", detail="full")
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
    table = ToolTable(listed=False)

    @table(kind="read")
    def sneaky(ts, m, agent_id: str, step: int | None = None) -> Outcome:
        """A tool that claims to be a read but starts a session (a write). Test double only."""
        return Outcome({"session_id": ts.engram(m).start_session(agent_id, "x")})

    mcp = KnewatServer("t", log_level="WARNING")
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


# ------------------------------------------------------------------------------------ guard coupling
def _load_guard():
    path = Path(__file__).resolve().parents[3] / "deploy" / "guard.py"
    spec = importlib.util.spec_from_file_location("knewat_deploy_guard", path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod  # dataclasses resolves string annotations through sys.modules
    spec.loader.exec_module(mod)
    return mod


def test_the_guard_allowlist_is_exactly_the_read_tools():
    """guard.py imports no Knewat code: its OBSERVER_TOOLS list is checked against the registry here."""
    guard = _load_guard()
    assert guard.OBSERVER_TOOLS == {d.name for d in all_tool_defs() if d.kind == "read"}


def test_the_deploy_audit_rule_makes_demo_tenants_off_and_team_tenants_unchanged():
    guard = _load_guard()
    env = {"KNEWAT_AUDIT_MODES": "team_*=light"}
    policy = AuditPolicy.from_env(guard.ensure_demo_audit_off(env))
    assert policy.tenant_mode("demo") == policy.tenant_mode("demo_scripted") == "off"
    assert policy.tenant_mode("team_abcd") == "light" and policy.tenant_mode("acme") == "full"


# ------------------------------------------------------------------------------------ 3. the no-write proof
WRITE_COMMANDS = (
    "graph.query",
    "graph.delete",
    "graph.copy",
    "graph.constraint",
    "set",
    "del",
    "unlink",
    "hset",
    "lpush",
    "rpush",
    "sadd",
    "zadd",
    "incr",
    "expire",
    "rename",
    "restore",
    "flushdb",
    "flushall",
)


def _commandstats(r) -> dict[str, int]:
    return {k.removeprefix("cmdstat_").lower(): v["calls"] for k, v in r.info("commandstats").items()}


def _server_counters(r) -> dict:
    """Everything the server counts as a write, plus the call counts of every command."""
    persistence = r.info("persistence")
    return {
        "calls": _commandstats(r),
        "dirty": persistence["rdb_changes_since_last_save"],
        "last_save": persistence["rdb_last_save_time"],
        "keys": r.dbsize(),
    }


def _delta(before: dict, after: dict) -> dict[str, int]:
    return {
        c: n - before["calls"].get(c, 0) for c, n in after["calls"].items() if n != before["calls"].get(c, 0)
    }


async def _read_burst(c: Client, ids: dict) -> int:
    """Every read tool, a few times each; returns how many calls were made."""
    calls = [
        ("recall", {"query": "API version"}),
        ("recall", {"query": "something nobody asserted", "k": 3}),
        ("recall", {"query": "API", "as_of": 1, "include_dormant": True}),
        ("fact_history", {"subject": "API", "predicate": "version"}),
        ("as_of", {"subject": "API", "predicate": "version", "t": 9_999_999_999_000}),
        ("why", {"node_id": ids["decision"]}),
        ("why", {"node_id": ids["fact"]}),
        ("why_recalled", {"recall_id": ids["recall"]}),
        ("who_knew", {"fact_id": ids["fact"]}),
        ("knew_at", {"subject_agent": "seed", "step_n": 3}),
        ("ready_tasks", {}),
        ("task_status", {"task_id": ids["task"]}),
        ("blocked_by_failure", {"task_id": ids["task"]}),
        ("best_procedure", {"task_type": "bugfix"}),
        ("memory_strength", {"fact_id": ids["fact"]}),
        ("facts_to_verify", {}),
        ("docs_to_update", {}),
    ]
    assert {t for t, _ in calls} == READ_TOOLS, "the burst must cover every read tool"
    n = 0
    for _ in range(3):
        for tool, args in calls:
            await _ok(c, tool, agent_id="visitor", **args)
            n += 1
    return n


@pytest.fixture
def raw_redis():
    import redis

    from tests.conftest import TEST_DB_HOST, TEST_DB_PORT

    r = redis.Redis(host=TEST_DB_HOST, port=TEST_DB_PORT, decode_responses=True)
    yield r
    r.close()


async def _seed_with_recall(client, tenant) -> dict:
    ids = await _seed(client, tenant)
    async with Client(build_server(_runtime(client, tenant))) as c:
        ids["recall"] = (await _ok(c, "recall", agent_id="seed", query="API version"))["recall_id"]
    return ids


async def test_no_write_proof_an_off_tenant_burst_issues_zero_write_commands(client, tenant, raw_redis):
    ids = await _seed_with_recall(client, tenant)
    graph_before = _totals(client, tenant)
    before = _server_counters(raw_redis)
    async with Client(build_server(_runtime(client, tenant, mode="off"))) as c:
        n = await _read_burst(c, ids)
    after = _server_counters(raw_redis)

    delta = _delta(before, after)
    assert n >= 50
    assert delta.get("graph.ro_query", 0) >= n, delta  # the reads really ran, as read-only queries
    assert {c: d for c, d in delta.items() if c in WRITE_COMMANDS} == {}, delta  # and not one write command
    assert after["keys"] == before["keys"]
    if after["last_save"] == before["last_save"]:  # the server's own dirty-key counter did not move
        assert after["dirty"] == before["dirty"]
    assert _totals(client, tenant) == graph_before


async def test_the_proof_can_fail_the_same_burst_in_full_mode_does_write(client, tenant, raw_redis):
    """Control: the counters above are not blind. In full mode the very same burst issues write commands."""
    ids = await _seed_with_recall(client, tenant)
    before = _server_counters(raw_redis)
    async with Client(build_server(_runtime(client, tenant, mode="full"))) as c:
        n = await _read_burst(c, ids)
    after = _server_counters(raw_redis)
    delta = _delta(before, after)
    assert delta.get("graph.query", 0) >= 2 * n  # at least a Step and a ToolCall per call
    assert after["dirty"] > before["dirty"] or after["last_save"] != before["last_save"]


async def test_light_mode_burst_issues_one_write_per_read_except_recall(client, tenant, raw_redis):
    ids = await _seed_with_recall(client, tenant)
    async with Client(build_server(_runtime(client, tenant, mode="light"))) as c:
        await _ok(c, "task_status", agent_id="warm", task_id=ids["task"])  # the schema check of a new Runtime
        before = _server_counters(raw_redis)
        n = await _read_burst(c, ids)
        delta = _delta(before, _server_counters(raw_redis))
    recalls = 3 * 3  # the recall rows of the burst stay full: Step + READ/Recall + ToolCall (3 writes)
    assert delta["graph.query"] == (n - recalls) * 1 + recalls * 3, delta
