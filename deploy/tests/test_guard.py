"""Unit tests for deploy/guard.py: no database, no Plexus imports. Run with the plexus venv:

cd plexus && uv run pytest ../deploy/tests -q -c ../deploy/tests/pytest.ini --rootdir ../deploy
"""

from __future__ import annotations

import asyncio
import json

import pytest

from deploy.guard import (
    OBSERVER_TOOLS,
    ActivityLog,
    ApiRateLimit,
    GuardConfig,
    IdleSweeper,
    PublicGuard,
    RateLimiter,
    TenantDirectory,
    TokenBucket,
    classify,
    client_ip,
    ensure_demo_audit_off,
    tenant_of,
)


class Clock:
    def __init__(self):
        self.t = 1000.0

    def __call__(self):
        return self.t


# ----------------------------------------------------------------------------------------------- pure policy
@pytest.mark.parametrize(
    "tenant,kind",
    [
        ("team_abcd", "team"),
        ("team_alice01", "team"),
        ("team_" + "a" * 24, "team"),
        ("team_abc", "deny"),  # 3 < 4
        ("team_" + "a" * 25, "deny"),
        ("team_Alice", "deny"),
        ("team_ab-cd", "deny"),
        ("team__abcd", "deny"),
        ("teams_abcd", "deny"),
        ("demo", "demo"),
        ("demo_scripted", "demo"),
        ("demo2", "deny"),  # only `demo` and `demo_*` are demo tenants
        ("acme", "deny"),
        ("default", "deny"),
        ("", "deny"),
    ],
)
def test_classify(tenant, kind):
    assert classify(tenant) == kind


def test_tenant_of_matches_the_inner_middleware():
    assert tenant_of("/mcp/t/team_abcd", []) == "team_abcd"
    assert tenant_of("/mcp/t/demo/extra", []) == "demo"  # first segment, like TenantPathMiddleware
    assert tenant_of("/mcp/t/", []) is None
    assert tenant_of("/mcp", [(b"X-Plexus-Tenant", b"team_abcd")]) == "team_abcd"
    assert tenant_of("/mcp", [(b"x-plexus-tenant", b"\xff")]) is None
    assert tenant_of("/mcp", []) is None
    # the path wins over the header (the inner middleware 400s if they differ)
    assert tenant_of("/mcp/t/demo", [(b"x-plexus-tenant", b"team_abcd")]) == "demo"


def test_client_ip_sources():
    scope = {
        "client": ("10.0.0.9", 1234),
        "headers": [(b"cf-connecting-ip", b"1.2.3.4"), (b"x-forwarded-for", b"9.9.9.9, 1.2.3.4, 172.0.0.1")],
    }
    assert client_ip(scope, GuardConfig()) == "10.0.0.9"
    assert client_ip(scope, GuardConfig(ip_header="cf-connecting-ip")) == "1.2.3.4"
    assert client_ip(scope, GuardConfig(xff_hops=2)) == "1.2.3.4"
    assert client_ip(scope, GuardConfig(xff_hops=9)) == "10.0.0.9"  # not enough entries: the peer
    assert client_ip({"headers": []}, GuardConfig()) == "unknown"


# ----------------------------------------------------------------------------------------------- rate limiting
def test_token_bucket_refills():
    clock = Clock()
    b = TokenBucket(60, clock)
    assert all(b.take() == 0.0 for _ in range(60))
    wait = b.take()
    assert 0.9 < wait <= 1.0
    clock.t += 1.0
    assert b.take() == 0.0
    assert b.take() > 0


def test_limiter_is_per_key_with_global_backstop():
    clock = Clock()
    lim = RateLimiter(3, global_per_min=5, clock=clock)
    assert [lim.check("a") for _ in range(3)] == [0.0, 0.0, 0.0]
    assert lim.check("a") > 0  # a is out
    assert lim.check("b") == 0.0 and lim.check("b") == 0.0  # b is independent, global now at 5
    assert lim.check("c") > 0  # global exhausted


def test_limiter_bounds_its_key_table():
    lim = RateLimiter(5, max_keys=3, clock=Clock())
    for i in range(10):
        lim.check(f"ip{i}")
    assert len(lim.buckets) == 3


# ----------------------------------------------------------------------------------------------- directory / cap
def test_directory_cap_counts_known_and_pending():
    clock = Clock()
    graphs = ["plexus_t_demo", "plexus_t_team_aaaa", "rec_x", "other"]
    d = TenantDirectory(lambda: graphs, max_tenants=4, clock=clock)
    assert d.names() == {"demo", "team_aaaa"}  # non-tenant graphs are not counted
    assert d.admit("team_aaaa")  # existing: always
    assert d.admit("team_bbbb") and d.admit("team_cccc")  # two new fit (2 known + 2 pending = 4)
    assert not d.admit("team_dddd")  # over the cap
    assert d.admit("team_bbbb")  # already admitted
    clock.t += 200  # pending entries expire if the graph never appeared
    assert d.admit("team_dddd")


# ----------------------------------------------------------------------------------------------- the ASGI guard
class Recorder:
    """A stand-in MCP app: records what reached it."""

    def __init__(self):
        self.calls = []

    async def __call__(self, scope, receive, send):
        body = b""
        while True:
            m = await receive()
            body += m.get("body", b"")
            if not m.get("more_body"):
                break
        self.calls.append((scope["path"], body))
        await send({"type": "http.response.start", "status": 202, "headers": []})
        await send({"type": "http.response.body", "body": b"ok"})


def call(app, path="/mcp/t/team_abcd", method="POST", body=b"", headers=None, client="1.1.1.1", chunks=None):
    """Drive an ASGI app once; returns (status, headers, body)."""
    hdrs = [(k.encode(), v.encode()) for k, v in (headers or {}).items()]
    scope = {"type": "http", "method": method, "path": path, "headers": hdrs, "client": (client, 5)}
    parts = chunks if chunks is not None else [body]
    queue = [{"type": "http.request", "body": p, "more_body": i < len(parts) - 1} for i, p in enumerate(parts)]
    out = []

    async def receive():
        if queue:
            return queue.pop(0)
        await asyncio.sleep(0)
        return {"type": "http.disconnect"}

    async def send(m):
        out.append(m)

    asyncio.run(app(scope, receive, send))
    start = next(m for m in out if m["type"] == "http.response.start")
    data = b"".join(m.get("body", b"") for m in out if m["type"] == "http.response.body")
    return start["status"], dict(start["headers"]), data


def make_guard(cfg=None, graphs=None, **kw):
    cfg = cfg or GuardConfig()
    inner = Recorder()
    graph_list = graphs if graphs is not None else ["plexus_t_demo", "plexus_t_demo_scripted"]
    directory = TenantDirectory(lambda: graph_list, cfg.max_tenants)
    activity = ActivityLog()
    return PublicGuard(inner, cfg, directory, activity, **kw), inner, activity


def rpc(method, **params):
    return json.dumps({"jsonrpc": "2.0", "id": 7, "method": method, "params": params}).encode()


def test_team_tenant_reaches_the_mcp_app_and_is_touched():
    g, inner, activity = make_guard()
    status, _, body = call(g, body=rpc("tools/call", name="recall", arguments={}))
    assert (status, body) == (202, b"ok")
    assert inner.calls == [("/mcp/t/team_abcd", rpc("tools/call", name="recall", arguments={}))]
    assert "team_abcd" in activity.last


def test_demo_tool_calls_are_refused_with_a_clear_tool_error():
    g, inner, _ = make_guard()
    status, hdrs, body = call(g, path="/mcp/t/demo", body=rpc("tools/call", name="assert_fact", arguments={}))
    assert status == 200 and hdrs[b"content-type"] == b"application/json"
    msg = json.loads(body)
    assert msg["id"] == 7 and msg["result"]["isError"] is True
    assert "read-only" in msg["result"]["content"][0]["text"] and "team_" in msg["result"]["content"][0]["text"]
    assert inner.calls == []  # never reached Plexus


def test_refusal_is_a_valid_mcp_call_tool_result():
    """The synthesized answer must parse with the installed MCP SDK (2.x requires resultType)."""
    from mcp.types import CallToolResult

    g, _, _ = make_guard()
    _, _, body = call(g, path="/mcp/t/demo", body=rpc("tools/call", name="assert_fact", arguments={}))
    res = CallToolResult.model_validate(json.loads(body)["result"])
    assert res.is_error and "read-only" in res.content[0].text


def test_demo_handshake_and_listing_still_work():
    g, inner, _ = make_guard()
    for m in ("initialize", "tools/list", "ping", "notifications/initialized"):
        assert call(g, path="/mcp/t/demo_scripted", body=rpc(m))[0] == 202
    assert call(g, path="/mcp/t/demo", method="GET")[0] == 202  # SSE stream
    assert len(inner.calls) == 5


def test_demo_refusal_also_applies_via_header_and_batch_is_rejected():
    g, inner, _ = make_guard()
    status, _, body = call(g, path="/mcp", headers={"X-Plexus-Tenant": "demo"}, body=rpc("tools/call", name="x"))
    assert status == 200 and json.loads(body)["result"]["isError"] is True
    status, _, _ = call(g, path="/mcp/t/demo", body=b"[" + rpc("tools/call", name="x") + b"]")
    assert status == 400
    assert inner.calls == []


def test_other_tenants_are_forbidden():
    g, inner, _ = make_guard()
    for t in ("acme", "default", "team_x", "demo2", "TEAM_ABCD"):
        status, _, body = call(g, path=f"/mcp/t/{t}", body=rpc("initialize"))
        assert status == 403, t
        assert "team_[a-z0-9]{4,24}" in json.loads(body)["error"]
    assert inner.calls == []


def test_missing_tenant_falls_through_to_the_plexus_error():
    g, inner, _ = make_guard()
    assert call(g, path="/mcp", body=rpc("initialize"))[0] == 202  # inner middleware answers 400 itself
    assert len(inner.calls) == 1


def test_graph_cap_blocks_new_tenants_only():
    cfg = GuardConfig(max_tenants=3)
    g, inner, _ = make_guard(cfg, graphs=["plexus_t_demo", "plexus_t_demo_scripted", "plexus_t_team_aaaa"])
    assert call(g, path="/mcp/t/team_aaaa", body=rpc("initialize"))[0] == 202  # existing tenant still works
    status, _, body = call(g, path="/mcp/t/team_bbbb", body=rpc("initialize"))
    assert status == 503 and "maximum of 3" in json.loads(body)["error"]
    assert call(g, path="/mcp/t/demo", body=rpc("initialize"))[0] == 202  # demo is unaffected by the cap


def test_rate_limit_returns_429_with_retry_after():
    g, inner, _ = make_guard(GuardConfig(rate_per_min=5, global_rate_per_min=1000))
    codes = [call(g, body=rpc("ping"), client="2.2.2.2")[0] for _ in range(7)]
    assert codes == [202] * 5 + [429] * 2
    status, hdrs, _ = call(g, body=rpc("ping"), client="2.2.2.2")
    assert status == 429 and int(hdrs[b"retry-after"]) >= 1
    assert call(g, body=rpc("ping"), client="3.3.3.3")[0] == 202  # another IP is unaffected


def test_body_cap_on_content_length_and_streamed():
    g, inner, _ = make_guard(GuardConfig(max_body_bytes=100))
    status, _, _ = call(g, body=b"x" * 101, headers={"content-length": "101"})
    assert status == 413
    status, _, _ = call(g, chunks=[b"x" * 60, b"y" * 60])  # no Content-Length (chunked)
    assert status == 413
    assert call(g, body=b"x" * 100, headers={"content-length": "100"})[0] == 202
    assert call(g, body=b"", headers={"content-length": "abc"})[0] == 400
    assert len(inner.calls) == 1


def test_api_rate_limit():
    inner = Recorder()
    a = ApiRateLimit(inner, GuardConfig(api_rate_per_min=3))
    codes = [call(a, path="/api/tenants", method="GET", client="9.9.9.9")[0] for _ in range(5)]
    assert codes == [202] * 3 + [429] * 2


def test_cypher_posts_have_their_own_smaller_bucket_and_the_gets_are_unaffected():
    inner = Recorder()
    a = ApiRateLimit(inner, GuardConfig(api_rate_per_min=100, cypher_rate_per_min=2))
    q = b'{"query": "RETURN 1"}'
    codes = [call(a, path="/api/demo/cypher", body=q, client="9.9.9.9")[0] for _ in range(4)]
    assert codes == [202, 202, 429, 429]
    assert call(a, path="/api/demo/cypher", body=q, client="9.9.9.9")[1][b"retry-after"]
    assert call(a, path="/api/tenants", method="GET", client="9.9.9.9")[0] == 202
    assert call(a, path="/api/demo/cypher", body=q, client="8.8.8.8")[0] == 202  # another client


def test_cypher_body_cap_on_content_length_and_streamed():
    inner = Recorder()
    a = ApiRateLimit(inner, GuardConfig(cypher_max_body_bytes=100))
    assert call(a, path="/api/demo/cypher", body=b"x" * 101, headers={"content-length": "101"})[0] == 413
    assert call(a, path="/api/demo/cypher", chunks=[b"x" * 60, b"x" * 60])[0] == 413  # no Content-Length
    assert call(a, path="/api/demo/cypher", body=b"x" * 100)[0] == 202
    assert inner.calls == [("/api/demo/cypher", b"x" * 100)]


# ----------------------------------------------------------------------------------------------- idle sweep
def test_idle_sweep_deletes_only_idle_team_graphs():
    clock = Clock()
    graphs = ["plexus_t_demo", "plexus_t_demo_scripted", "plexus_t_team_old1", "plexus_t_team_new1", "plexus_t_acme"]
    deleted = []

    def delete(name):
        deleted.append(name)
        graphs.remove(name)

    act = ActivityLog(clock=clock)
    sw = IdleSweeper(act, lambda: list(graphs), delete, idle_s=24 * 3600, clock=clock)
    act.touch("team_old1")
    clock.t += 23 * 3600
    act.touch("team_new1")
    assert sw.sweep_once() == []  # nothing is older than 24 h yet; the unseen `acme` stays (never swept)
    clock.t += 2 * 3600  # team_old1 idle 25 h, team_new1 idle 2 h
    assert sw.sweep_once() == ["team_old1"]
    assert deleted == ["plexus_t_team_old1"]
    assert "team_old1" not in act.last
    clock.t += 30 * 3600
    assert sw.sweep_once() == ["team_new1"]
    assert sorted(graphs) == ["plexus_t_acme", "plexus_t_demo", "plexus_t_demo_scripted"]


def test_sweep_starts_the_idle_clock_for_graphs_it_never_saw_active():
    clock = Clock()
    graphs = ["plexus_t_team_zzzz"]
    deleted = []
    act = ActivityLog(clock=clock)
    sw = IdleSweeper(act, lambda: list(graphs), deleted.append, idle_s=100, clock=clock)
    assert sw.sweep_once() == []  # first sight: grace period, not deletion
    clock.t += 101
    assert sw.sweep_once() == ["team_zzzz"]


# ----------------------------------------------------------------------------------------------- P9-e: readable demo
def tool_call(name, **arguments):
    return rpc("tools/call", name=name, arguments=arguments)


def test_demo_read_tools_are_forwarded_and_each_tool_is_on_the_allowlist():
    g, inner, activity = make_guard(cfg=GuardConfig(demo_rate_per_min=100, rate_per_min=1000))
    for name in sorted(OBSERVER_TOOLS):
        status, _, body = call(g, path="/mcp/t/demo", body=tool_call(name, agent_id="visitor"))
        assert (status, body) == (202, b"ok"), name
    assert len(inner.calls) == len(OBSERVER_TOOLS)
    assert "demo" not in activity.last  # demo tenants are never touched for the idle sweep


def test_demo_forwarding_works_through_the_header_route_too():
    g, inner, _ = make_guard()
    status, _, _ = call(g, path="/mcp", headers={"X-Plexus-Tenant": "demo_scripted"}, body=tool_call("recall"))
    assert status == 202 and len(inner.calls) == 1


@pytest.mark.parametrize(
    "name",
    [
        "assert_fact",
        "start_session",
        "create_tasks",
        "forget_source",
        "memory_sweep",
        "pin_fact",
        "Recall",
        "recall ",
        "",
    ],
)
def test_demo_write_tools_and_unknown_names_are_refused_with_a_clear_tool_error(name):
    g, inner, _ = make_guard()
    status, _, body = call(g, path="/mcp/t/demo", body=tool_call(name, agent_id="x"))
    msg = json.loads(body)
    assert status == 200 and msg["result"]["isError"] is True
    text = msg["result"]["content"][0]["text"]
    assert "read-only" in text and "reads are allowed" in text and "team_" in text
    assert inner.calls == []


@pytest.mark.parametrize("params", [{}, {"name": None}, {"name": ["recall"]}, {"name": {"a": 1}}, {"name": 5}])
def test_demo_tools_call_with_a_malformed_name_is_refused_not_crashed(params):
    g, inner, _ = make_guard()
    status, _, body = call(g, path="/mcp/t/demo", body=rpc("tools/call", **params))
    assert status == 200 and json.loads(body)["result"]["isError"] is True
    assert inner.calls == []


def test_a_demo_tenant_without_a_graph_is_refused_so_a_request_cannot_create_one():
    listed: list[str] = ["plexus_t_demo"]
    g, inner, _ = make_guard(graphs=listed)
    status, _, body = call(g, path="/mcp/t/demo_new", body=tool_call("recall", agent_id="v", query="x"))
    msg = json.loads(body)
    assert status == 200 and msg["result"]["isError"] is True
    assert "does not exist" in msg["result"]["content"][0]["text"]
    assert inner.calls == [] and listed == ["plexus_t_demo"]  # nothing forwarded, nothing created
    # the handshake still works for any demo name (it touches no graph)
    assert call(g, path="/mcp/t/demo_new", body=rpc("initialize"))[0] == 202


def test_demo_reads_have_their_own_smaller_rate_limit_and_team_tenants_are_unaffected():
    clock = Clock()
    cfg = GuardConfig(rate_per_min=1000, global_rate_per_min=10_000, demo_rate_per_min=3, demo_global_rate_per_min=100)
    g, inner, _ = make_guard(
        cfg, limiter=RateLimiter(1000, 10_000, clock=clock), demo_limiter=RateLimiter(3, 100, clock=clock)
    )
    codes = [call(g, path="/mcp/t/demo", body=tool_call("recall"))[0] for _ in range(5)]
    assert codes == [202, 202, 202, 429, 429]
    status, hdrs, _ = call(g, path="/mcp/t/demo", body=tool_call("recall"))
    assert status == 429 and int(hdrs[b"retry-after"]) >= 1
    # a refused write and the handshake do not spend the demo-read budget; a team tenant has its own path
    assert call(g, path="/mcp/t/demo", body=tool_call("assert_fact"))[0] == 200
    assert call(g, path="/mcp/t/demo", body=rpc("tools/list"))[0] == 202
    assert call(g, body=tool_call("recall"))[0] == 202
    assert len(inner.calls) == 3 + 1 + 1


def test_team_tenants_are_unchanged_by_the_allowlist():
    g, inner, _ = make_guard()
    for name in ("assert_fact", "recall", "anything"):
        assert call(g, body=tool_call(name))[0] == 202
    assert len(inner.calls) == 3


def test_demo_batches_and_oversized_bodies_are_still_refused():
    g, inner, _ = make_guard(cfg=GuardConfig(max_body_bytes=1024))
    assert call(g, path="/mcp/t/demo", body=b"[" + tool_call("recall") + b"]")[0] == 400
    assert call(g, path="/mcp/t/demo", body=b"x" * 2048)[0] == 413
    assert inner.calls == []


def test_demo_audit_off_is_forced_into_the_runtime_environment():
    env: dict[str, str] = {}
    assert ensure_demo_audit_off(env)["PLEXUS_AUDIT_MODES"] == "demo*=off"
    env = {"PLEXUS_AUDIT_MODES": "team_*=light"}
    assert ensure_demo_audit_off(env)["PLEXUS_AUDIT_MODES"] == "demo*=off,team_*=light"
    # an operator's own demo rule can not weaken it: ours is first and the first match wins
    env = {"PLEXUS_AUDIT_MODES": "demo*=full,team_*=light"}
    assert ensure_demo_audit_off(env)["PLEXUS_AUDIT_MODES"] == "demo*=off,demo*=full,team_*=light"
    assert ensure_demo_audit_off(env)["PLEXUS_AUDIT_MODES"].count("demo*=off") == 1  # idempotent
