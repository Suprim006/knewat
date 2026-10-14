"""Streamable-HTTP tenant binding: path/header routing, session pinning (403 on mismatch), isolation."""

from __future__ import annotations

import json

import pytest
from redis.exceptions import ResponseError
from starlette.testclient import TestClient

from plexus.embed import HashEmbedder
from plexus.graph.tenancy import graph_name
from plexus.mcp.runtime import Runtime
from plexus.mcp.server import build_http_app

HDR = {"Accept": "application/json, text/event-stream", "Content-Type": "application/json"}


def _rpc(method: str, params: dict | None = None, id_: int | None = 1) -> dict:
    msg = {"jsonrpc": "2.0", "method": method, "params": params or {}}
    if id_ is not None:
        msg["id"] = id_
    return msg


def _body(resp) -> dict:
    if "text/event-stream" in resp.headers.get("content-type", ""):
        datas = [ln[5:].strip() for ln in resp.text.splitlines() if ln.startswith("data:")]
        return json.loads(datas[-1])
    return resp.json()


@pytest.fixture
def http(client):
    rt = Runtime(client=client, embedder=HashEmbedder())  # no stdio tenant: HTTP binds per connection
    with TestClient(build_http_app(rt), base_url="http://localhost") as tc:
        yield tc


def _init(http, path: str, headers: dict | None = None):
    r = http.post(
        path,
        headers={**HDR, **(headers or {})},
        json=_rpc(
            "initialize",
            {
                "protocolVersion": "2025-06-18",
                "capabilities": {},
                "clientInfo": {"name": "t", "version": "0"},
            },
        ),
    )
    return r


def _open(http, path: str, headers: dict | None = None) -> dict:
    r = _init(http, path, headers)
    assert r.status_code == 200, r.text
    sid = r.headers["mcp-session-id"]
    h = {**HDR, **(headers or {}), "mcp-session-id": sid, "mcp-protocol-version": "2025-06-18"}
    http.post(path, headers=h, json=_rpc("notifications/initialized", id_=None))
    return h


def _call(http, path, h, tool, args, id_=2):
    return http.post(path, headers=h, json=_rpc("tools/call", {"name": tool, "arguments": args}, id_))


def _result(resp) -> dict:
    res = _body(resp)["result"]
    assert not res.get("isError"), res
    return json.loads(res["content"][0]["text"])


def _count(client, tenant, tool):
    """ToolCalls of ``tool`` in the tenant's graph; 0 when the graph was never created."""
    try:
        res = client.graph(graph_name(tenant)).ro_query(
            "MATCH (t:ToolCall {tool:$t}) RETURN count(t)", {"t": tool}
        )
    except ResponseError:
        return 0
    return res.result_set[0][0]


def test_path_binding_runs_tool_in_that_tenants_graph(http, client, new_tenant):
    a, b = new_tenant(), new_tenant()
    ha = _open(http, f"/mcp/t/{a}")
    hb = _open(http, f"/mcp/t/{b}")
    _result(_call(http, f"/mcp/t/{a}", ha, "start_session", {"agent_id": "x"}))
    _result(
        _call(
            http,
            f"/mcp/t/{a}",
            ha,
            "assert_fact",
            {"agent_id": "x", "subject": "S", "predicate": "p", "value": "v"},
        )
    )
    _result(_call(http, f"/mcp/t/{b}", hb, "start_session", {"agent_id": "y"}))
    assert _count(client, a, "start_session") == 1 and _count(client, a, "assert_fact") == 1
    assert _count(client, b, "start_session") == 1 and _count(client, b, "assert_fact") == 0
    # tenant isolation: b cannot recall a's fact
    r = _result(_call(http, f"/mcp/t/{b}", hb, "recall", {"agent_id": "y", "query": "S p"}))
    assert r["count"] == 0


def test_replaying_a_session_under_another_tenant_is_rejected(http, client, new_tenant):
    a, evil = new_tenant(), new_tenant()
    ha = _open(http, f"/mcp/t/{a}")
    ok = _call(http, f"/mcp/t/{a}", ha, "start_session", {"agent_id": "x"})
    assert ok.status_code == 200
    bad = _call(http, f"/mcp/t/{evil}", ha, "start_session", {"agent_id": "x"})
    assert bad.status_code == 403
    assert "different tenant" in bad.json()["error"]
    assert _count(client, evil, "start_session") == 0  # nothing ran, graph untouched


def test_header_binding_and_header_pinning(http, client, new_tenant):
    a, evil = new_tenant(), new_tenant()
    ha = _open(http, "/mcp", {"X-Plexus-Tenant": a})
    assert _call(http, "/mcp", ha, "start_session", {"agent_id": "x"}).status_code == 200
    assert _count(client, a, "start_session") == 1
    swapped = {**ha, "X-Plexus-Tenant": evil}
    assert _call(http, "/mcp", swapped, "start_session", {"agent_id": "x"}).status_code == 403


def test_client_header_cannot_override_path(http, new_tenant):
    a, b = new_tenant(), new_tenant()
    r = _init(http, f"/mcp/t/{a}", {"X-Plexus-Tenant": b})
    assert r.status_code == 400 and "differ" in r.json()["error"]


@pytest.mark.parametrize("path", ["/mcp", "/mcp/t/", "/mcp/t/Bad%20Tenant", "/mcp/t/UPPER"])
def test_missing_or_invalid_tenant_rejected(http, path):
    r = _init(http, path)
    assert r.status_code == 400


def test_delete_session_drops_pin_and_healthz(http, new_tenant):
    a = new_tenant()
    ha = _open(http, f"/mcp/t/{a}")
    assert http.get("/healthz").json() == {"status": "ok"}
    mw = http.app
    sid = ha["mcp-session-id"]
    assert mw.pins[sid] == a
    http.delete(f"/mcp/t/{a}", headers=ha)
    assert sid not in mw.pins
