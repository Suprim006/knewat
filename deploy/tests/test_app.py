"""deploy/app.py: routing between the API and the static View, and that no MCP route exists. No database."""

from __future__ import annotations

import asyncio

from deploy.app import PublicApp, SpaStaticFiles, pick_results_file


async def _api(scope, receive, send):
    await send({"type": "http.response.start", "status": 200, "headers": []})
    await send({"type": "http.response.body", "body": b"api:" + scope["path"].encode()})


def get(app, path, method="GET"):
    out = []
    msgs = [{"type": "http.request", "body": b"", "more_body": False}]

    async def receive():  # the request, then silence: Starlette's FileResponse listens for a disconnect meanwhile
        if msgs:
            return msgs.pop(0)
        await asyncio.sleep(3600)

    async def send(m):
        out.append(m)

    asyncio.run(
        app({"type": "http", "method": method, "path": path, "headers": [], "query_string": b""}, receive, send)
    )
    start = next(m for m in out if m["type"] == "http.response.start")
    return start["status"], b"".join(m.get("body", b"") for m in out if m["type"] == "http.response.body")


def make(tmp_path):
    (tmp_path / "assets").mkdir()
    (tmp_path / "index.html").write_text('<div id="root"></div>')
    (tmp_path / "assets" / "a.js").write_text("x")
    return PublicApp(_api, SpaStaticFiles(directory=str(tmp_path), html=True))


def test_api_paths_go_to_the_api_and_the_rest_to_the_view(tmp_path):
    app = make(tmp_path)
    assert get(app, "/healthz") == (200, b"api:/healthz")
    assert get(app, "/api/demo/cypher", "POST") == (200, b"api:/api/demo/cypher")
    assert get(app, "/docs") == (200, b"api:/docs")
    assert get(app, "/")[0] == 200
    assert get(app, "/cypher") == (200, b'<div id="root"></div>')  # client-side route: SPA fallback
    assert get(app, "/assets/a.js") == (200, b"x")
    assert get(app, "/missing.js")[0] == 404


def test_there_is_no_mcp_route(tmp_path):
    app = make(tmp_path)
    for path in ("/mcp", "/mcp/t/demo", "/mcp/t/team_abcd"):
        status, body = get(app, path, "POST")
        assert status in (404, 405) and not body.startswith(b"api:")


def test_lifespan_starts_and_stops(tmp_path):
    app = make(tmp_path)
    sent, msgs = [], [{"type": "lifespan.startup"}, {"type": "lifespan.shutdown"}]

    async def receive():
        return msgs.pop(0)

    async def send(m):
        sent.append(m["type"])

    asyncio.run(app({"type": "lifespan"}, receive, send))
    assert sent == ["lifespan.startup.complete", "lifespan.shutdown.complete"]


def test_results_file_prefers_latest_all(tmp_path):
    assert pick_results_file(None) is None and pick_results_file(tmp_path) is None
    (tmp_path / "latest.json").write_text("{}")
    assert pick_results_file(tmp_path).endswith("latest.json")
    (tmp_path / "latest-all.json").write_text("{}")
    assert pick_results_file(tmp_path).endswith("latest-all.json")
