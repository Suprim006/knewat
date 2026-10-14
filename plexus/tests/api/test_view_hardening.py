"""View API hardening: integer bounds are 422 (never 502), /stream is capped and shares its polling work,
and /healthz?deep=1 reaches the database (C-09, C-10, C-11, P5C-07)."""

from __future__ import annotations

import contextlib
import socket
import threading
import time

import httpx
import pytest
import uvicorn
from fastapi.testclient import TestClient

from plexus.api.view_api import OPEN, create_app

HUGE = 99999999999999999999
INT64 = 9223372036854775808


# ---------------------------------------------------------------- C-09 / P5C-07: bounds are 422
@pytest.mark.parametrize(
    ("path", "params"),
    [
        ("graph", {"until": HUGE}),
        ("graph", {"since": INT64}),
        ("graph", {"since": OPEN + 1}),
        ("flow", {"after": INT64}),
        ("flow", {"after": HUGE}),
        ("stream", {"after": HUGE}),
        ("stream", {"after": OPEN + 1}),
        ("step/9223372036854775808", {}),
        ("step/99999999999999999999999", {}),
        ("step/-1", {}),
    ],
)
def test_huge_integers_are_a_422_not_a_502(api, seeded, path, params):
    r = api.get(f"/api/{seeded['tenant']}/{path}", params=params)
    assert r.status_code == 422, (path, r.status_code, r.text[:200])


def test_values_at_the_bound_are_still_served(api, seeded):
    t = seeded["tenant"]
    assert api.get(f"/api/{t}/graph", params={"since": 0, "until": OPEN}).status_code == 200
    assert api.get(f"/api/{t}/flow", params={"after": OPEN}).json()["events"] == []
    assert api.get(f"/api/{t}/step/{OPEN}").status_code == 200


def test_oversized_path_ids_are_a_422(api, seeded):
    t = seeded["tenant"]
    assert api.get(f"/api/{t}/why/{'x' * 500}").status_code == 422
    assert api.get(f"/api/{t}/recall/{'x' * 500}").status_code == 422
    assert api.get(f"/api/{t}/graph", params={"labels": "A," * 3000}).status_code == 422


def test_stream_poll_interval_has_a_floor(api, seeded):
    t = seeded["tenant"]
    assert api.get(f"/api/{t}/stream", params={"poll_ms": 20, "max_events": 1}).status_code == 422
    assert api.get(f"/api/{t}/stream", params={"poll_ms": 199, "max_events": 1}).status_code == 422
    ok = api.get(f"/api/{t}/stream", params={"poll_ms": 200, "max_events": 1, "after": 0})
    assert ok.status_code == 200


# ---------------------------------------------------------------- C-11: deep health
def test_healthz_deep_pings_the_database(client, monkeypatch):
    with TestClient(create_app(client=client)) as tc:
        assert tc.get("/healthz").json() == {"status": "ok"}
        assert tc.get("/healthz", params={"deep": 1}).json() == {"status": "ok"}

        def down():
            raise OSError("db down")

        monkeypatch.setattr(client, "ping", down)
        assert tc.get("/healthz").status_code == 200  # liveness stays static
        r = tc.get("/healthz", params={"deep": 1})
        assert r.status_code == 503 and r.json() == {"status": "unavailable"}


# ---------------------------------------------------------------- C-10: stream cap and shared polling
@contextlib.contextmanager
def live(app):
    """Serve ``app`` with a real uvicorn on a free port (ASGITransport buffers the body)."""
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]
    server = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=port, log_level="warning"))
    th = threading.Thread(target=server.run, daemon=True)
    th.start()
    deadline = time.monotonic() + 10
    while not server.started and time.monotonic() < deadline:
        time.sleep(0.02)
    assert server.started
    try:
        yield f"http://127.0.0.1:{port}"
    finally:
        server.should_exit = True
        th.join(10)


def test_stream_connections_are_capped_and_slots_are_released(client, seeded):
    t = seeded["tenant"]
    app = create_app(client=client, max_streams=2)
    with live(app) as base, httpx.Client(base_url=base, timeout=10) as hc:
        url = f"/api/{t}/stream"
        with hc.stream("GET", url) as a, hc.stream("GET", url) as b:
            assert a.status_code == 200 and b.status_code == 200
            third = hc.get(url, params={"max_events": 1})
            assert third.status_code == 429 and "stream" in third.json()["detail"]
            assert hc.get(f"/api/{t}/flow").status_code == 200  # other endpoints are unaffected
        # both clients hung up: the slots come back (disconnect is noticed on the next poll)
        deadline = time.monotonic() + 10
        status = 429
        while status == 429 and time.monotonic() < deadline:
            time.sleep(0.3)
            with hc.stream("GET", url, params={"max_events": 1, "after": 0}) as again:
                status = again.status_code
        assert status == 200


def test_finished_streams_release_their_slot(client, seeded):
    t = seeded["tenant"]
    app = create_app(client=client, max_streams=1)
    with TestClient(app) as tc:
        for _ in range(3):  # each one closes itself after max_events
            r = tc.get(f"/api/{t}/stream", params={"after": 0, "max_events": 1})
            assert r.status_code == 200
    assert app.state.streams.active == 0


def test_subscribers_share_one_flow_query_per_poll(client, seeded, monkeypatch):
    t = seeded["tenant"]
    app = create_app(client=client)
    real = app.state.ro.ro
    calls = []

    def counting(graph, name, params=None):
        calls.append(name)
        return real(graph, name, params)

    monkeypatch.setattr(app.state.ro, "ro", counting)
    results = []
    threads = [
        threading.Thread(target=lambda: results.append(app.state.flow_events(t, 0))) for _ in range(12)
    ]
    for th in threads:
        th.start()
    for th in threads:
        th.join()
    assert calls.count("view/flow") == 1  # twelve subscribers, one database read
    assert len(results) == 12 and all(len(r) == len(results[0]) > 0 for r in results)
    time.sleep(0.4)  # the cache entry expires: the next poll reads fresh data
    app.state.flow_events(t, 0)
    assert calls.count("view/flow") == 2
