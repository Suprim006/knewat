"""View API: every endpoint returns the documented shapes; nothing can write; SSE delivers new events."""

from __future__ import annotations

import asyncio
import json
import re
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from plexus.api import models as M
from plexus.api.view_api import create_app

API_SRC = Path(__file__).parents[2] / "src" / "plexus" / "api"


def test_tenants_lists_plexus_graphs(api, seeded):
    body = M.TenantsResponse(**api.get("/api/tenants").json())
    assert seeded["tenant"] in {t.tenant for t in body.tenants}
    t = next(t for t in body.tenants if t.tenant == seeded["tenant"])
    assert t.graph == f"plexus_t_{seeded['tenant']}"
    assert all(not x.tenant.startswith("test_") for x in body.tenants)  # only plexus_t_* graphs


def test_inventory(api, seeded):
    inv = M.InventoryResponse(**api.get(f"/api/{seeded['tenant']}/inventory").json())
    labels = {x.label: x for x in inv.labels}
    assert {"Agent", "Session", "Episode", "Fact", "Entity", "Task", "Decision", "ToolCall", "Scope"} <= set(
        labels
    )
    assert labels["Fact"].count == 2 and labels["ToolCall"].count == 9
    assert {"predicate", "value", "status"} <= set(labels["Fact"].keys)
    edge_types = {e.type for e in inv.edge_types}
    assert {"ABOUT", "IN_SCOPE", "SUPERSEDES", "CREATED", "UPDATED", "CLAIMED", "BASED_ON"} <= edge_types
    assert inv.nodes_total == sum(x.count for x in inv.labels)
    assert inv.edges_total == sum(e.count for e in inv.edge_types)
    kinds = {k for i in inv.indexes for ks in i.types.values() for k in ks}
    assert {"RANGE", "FULLTEXT", "VECTOR"} <= kinds
    assert all(i.status for i in inv.indexes)


def test_graph_shape_filters_and_no_embeddings(api, seeded):
    t = seeded["tenant"]
    g = M.GraphResponse(**api.get(f"/api/{t}/graph").json())
    assert not g.truncated and g.limit == 500
    ids = {n.id for n in g.nodes}
    assert seeded["f2"] in ids and seeded["decision"] in ids
    assert all(e.source in ids and e.target in ids for e in g.edges)
    assert {"SUPERSEDES", "BASED_ON"} <= {e.type for e in g.edges}
    assert any(
        e.source == seeded["f2"] and e.target == seeded["f1"] and e.type == "SUPERSEDES" for e in g.edges
    )
    assert "embedding" not in json.dumps(api.get(f"/api/{t}/graph").json())
    fact = next(n for n in g.nodes if n.id == seeded["f1"])
    assert (
        fact.label == "Fact" and fact.props["predicate"] == "version" and fact.props["status"] == "superseded"
    )
    assert all(v is not None for n in g.nodes for v in n.props.values())

    only = M.GraphResponse(**api.get(f"/api/{t}/graph", params={"labels": "Fact,Decision"}).json())
    assert {n.label for n in only.nodes} == {"Fact", "Decision"}

    small = M.GraphResponse(**api.get(f"/api/{t}/graph", params={"limit": 3}).json())
    assert len(small.nodes) == 3 and small.truncated
    assert all(e.source in {n.id for n in small.nodes} for e in small.edges)

    none = M.GraphResponse(**api.get(f"/api/{t}/graph", params={"since": 9_000_000_000_000}).json())
    assert none.nodes == [] and none.edges == []


def test_flow_orders_toolcalls_with_created_updated(api, seeded):
    t = seeded["tenant"]
    flow = M.FlowResponse(**api.get(f"/api/{t}/flow").json())
    tools = [e.tool for e in flow.events]
    assert tools == [
        "start_session",
        "remember_episode",
        "assert_fact",
        "assert_fact",
        "recall",
        "register_agent",
        "create_tasks",
        "claim_next_task",
        "record_decision",
    ]
    ats = [e.at for e in flow.events]
    assert ats == sorted(ats) and flow.last_at == ats[-1]
    second = flow.events[3]
    assert [r.label for r in second.created] == ["Fact"]
    assert second.updated[0].id == seeded["f1"] and second.updated[0].label == "Fact"
    assert flow.events[1].step == 1 and flow.events[0].step is None
    assert flow.events[4].wrote is True and [r.label for r in flow.events[4].created] == ["Recall"]
    assert all(e.run_time_ms > 0 for e in flow.events)
    assert flow.events[8].created[0].id == seeded["decision"]

    later = M.FlowResponse(**api.get(f"/api/{t}/flow", params={"after": ats[6]}).json())
    assert [e.tool for e in later.events] == ["claim_next_task", "record_decision"]
    capped = M.FlowResponse(**api.get(f"/api/{t}/flow", params={"limit": 2}).json())
    assert [e.tool for e in capped.events] == ["start_session", "remember_episode"]
    empty = M.FlowResponse(**api.get(f"/api/{t}/flow", params={"after": flow.last_at}).json())
    assert empty.events == [] and empty.last_at == flow.last_at


def _sse_events(text: str) -> list[dict]:
    out = []
    for block in text.split("\n\n"):
        if "event: toolcall" in block:
            data = re.search(r"^data: (.*)$", block, re.M).group(1)
            out.append(json.loads(data))
    return out


def test_sse_replays_from_after_and_closes_at_max_events(api, seeded):
    t = seeded["tenant"]
    r = api.get(f"/api/{t}/stream", params={"after": 0, "max_events": 3, "poll_ms": 200})
    assert r.status_code == 200 and r.headers["content-type"].startswith("text/event-stream")
    evs = _sse_events(r.text)
    assert [e["tool"] for e in evs] == ["start_session", "remember_episode", "assert_fact"]
    assert f"id: {evs[0]['at']}" in r.text
    M.ToolCallEvent(**evs[0])


async def test_sse_yields_events_that_land_while_connected(client, seeded):
    """Open the stream, THEN write a new tool call: the stream must push it."""
    import httpx

    from plexus.audit import record_tool_call
    from plexus.graph.tenancy import graph_name

    t = seeded["tenant"]
    app = create_app(client=client)
    start = await asyncio.to_thread(
        lambda: app.state.ro.ro(graph_name(t), "view/flow", {"after": 0, "limit": 1000})
    )
    last = max(r["at"] for r in start)

    async def writer():
        await asyncio.sleep(0.4)
        await asyncio.to_thread(
            record_tool_call, client, graph_name(t), "recall", "late-agent", None, "engram/recall", 1.0
        )

    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as hc:
        w = asyncio.create_task(writer())
        async with hc.stream(
            "GET", f"/api/{t}/stream", params={"after": last, "max_events": 1, "poll_ms": 200}
        ) as resp:
            body = ""
            async for chunk in resp.aiter_text():
                body += chunk
        await w
    evs = _sse_events(body)
    assert len(evs) == 1 and evs[0]["agent_id"] == "late-agent" and evs[0]["tool"] == "recall"


def test_unknown_and_invalid_tenant_404(api):
    for path in ("inventory", "graph", "flow", "stream"):
        assert api.get(f"/api/does_not_exist_zz/{path}", params={"max_events": 1}).status_code == 404
        assert api.get(f"/api/Bad Tenant/{path}").status_code == 404


def test_query_text_endpoint(api):
    r = api.get("/api/queries/engram/recall")
    assert r.status_code == 200
    q = M.QueryText(**r.json())
    assert q.name == "engram/recall" and q.mode == "ro" and "db.idx.vector.queryNodes" in q.text
    assert q.text.startswith("// name: engram/recall")
    assert api.get("/api/queries/view/flow").json()["mode"] == "ro"
    assert api.get("/api/queries/nope/missing").status_code == 404
    assert api.get("/api/queries/..%2f..%2fpyproject").status_code == 404
    assert api.get("/api/queries/../../pyproject.toml").status_code in (404, 422)


def test_results_file(client, tmp_path, monkeypatch):
    monkeypatch.delenv("PLEXUS_RESULTS_PATH", raising=False)
    with TestClient(create_app(client=client)) as tc:
        assert tc.get("/api/results").status_code == 404
    p = tmp_path / "results.json"
    p.write_text('{"l1": {"pass": true}}')
    monkeypatch.setenv("PLEXUS_RESULTS_PATH", str(p))
    with TestClient(create_app(client=client)) as tc:
        assert tc.get("/api/results").json() == {"l1": {"pass": True}}
    with TestClient(create_app(client=client, results_path=str(tmp_path / "gone.json"))) as tc:
        assert tc.get("/api/results").status_code == 404


def test_cors_origins_configurable(client, monkeypatch):
    def acao(tc, origin):
        return tc.get("/api/tenants", headers={"Origin": origin}).headers.get("access-control-allow-origin")

    with TestClient(create_app(client=client)) as tc:
        assert acao(tc, "http://localhost:5180") == "http://localhost:5180"
        assert acao(tc, "http://127.0.0.1:5180") == "http://127.0.0.1:5180"
        assert acao(tc, "http://evil.example") is None
    monkeypatch.setenv("PLEXUS_CORS_ORIGINS", "http://view.example:9000")
    with TestClient(create_app(client=client)) as tc:
        assert acao(tc, "http://view.example:9000") == "http://view.example:9000"
        assert acao(tc, "http://localhost:5180") is None


def test_no_write_path_in_api_package(api):
    """The API can only read: no rw()/query() calls, no write-capable handle, no write verbs on any route."""
    for py in API_SRC.glob("*.py"):
        text = py.read_text(encoding="utf-8")
        assert not re.search(r"\.rw\(|rw_script|\.query\(|GRAPH\.QUERY|delete_graph", text), py.name
    assert not hasattr(api.app.state.ro, "rw") and not hasattr(api.app.state.ro, "rw_script")
    for route in api.app.routes:
        assert getattr(route, "methods", None) in (None, {"GET"}, {"GET", "HEAD"}), route.path
    assert api.post("/api/tenants").status_code == 405
    assert api.delete("/api/queries/engram/recall").status_code == 405


def test_read_only_client_refuses_write_queries(client):
    from plexus.api.view_api import ReadOnlyClient
    from plexus.graph.queries import ReadOnlyViolation

    ro = ReadOnlyClient(client)
    with pytest.raises(ReadOnlyViolation):
        ro.ro("any_graph", "schema/indexes", {})


def test_openapi_has_all_endpoints(api):
    paths = set(api.get("/openapi.json").json()["paths"])
    expected = {
        "/api/tenants",
        "/api/{tenant}/inventory",
        "/api/{tenant}/graph",
        "/api/{tenant}/flow",
        "/api/{tenant}/stream",
        "/api/{tenant}/step/{n}",
        "/api/{tenant}/why/{node_id}",
        "/api/{tenant}/recall/{recall_id}",
        "/api/queries/{name}",
        "/api/results",
    }
    assert expected <= paths


def test_exported_schema_is_current():
    from plexus.api.export_schema import DEFAULT_PATH, build_schema

    assert json.loads(DEFAULT_PATH.read_text(encoding="utf-8")) == build_schema(), (
        "docs/view-api.schema.json is stale: run `uv run python -m plexus.api.export_schema`"
    )
