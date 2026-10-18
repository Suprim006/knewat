"""P12 scoped tool exposure: a session publishes (and may call) only its toolset's tools; default ``full``."""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest
from starlette.testclient import TestClient

from mcp import Client
from plexus.embed import HashEmbedder
from plexus.mcp import server as server_mod
from plexus.mcp.runtime import Runtime
from plexus.mcp.server import build_http_app, build_server
from plexus.mcp.toolkit import all_tool_defs
from plexus.mcp.toolsets import (
    MODULES,
    PROFILES,
    ToolsetError,
    canonical,
    default_toolset,
    modules_of,
    tool_names,
)

from .test_http import _body, _call, _init, _open, _result, _rpc

REPORT = Path(__file__).resolve().parents[3] / "docs" / "PLEXUS_REPORT.md"
ALL = {d.name for d in all_tool_defs()}
CORE = MODULES["engram"] | MODULES["relay"] | MODULES["lineage"]


# ------------------------------------------------------------------------------------------- the module map
def test_modules_partition_every_tool_exactly_once():
    assert len(ALL) == 45
    seen: list[str] = [t for names in MODULES.values() for t in names]
    assert len(seen) == len(set(seen)) == 45  # disjoint
    assert set(seen) == ALL  # a new tool must be given a module
    assert {m: len(v) for m, v in MODULES.items()} == {
        "engram": 7, "relay": 13, "lineage": 9, "staleness": 7, "forgetting": 5, "relations": 2, "dedup": 2,
    }  # fmt: skip


def test_modules_match_the_report_module_table():
    """Module boundaries are the documented ones (PLEXUS_REPORT.md §2.2 'Main tools'), not an ad-hoc split."""
    rows = {
        "engram": "**Engram**", "relay": "**Relay**", "lineage": "**Lineage**", "staleness": "**Staleness**",
        "forgetting": "**Forgetting**", "relations": "**Relations + impact**", "dedup": "**Dedup confirm**",
    }  # fmt: skip
    lines = REPORT.read_text(encoding="utf-8").splitlines()
    for mod, label in rows.items():
        row = next(ln for ln in lines if ln.startswith(f"| {label}"))
        main_tools = row.replace("\\|", "/").rstrip("|").rsplit("|", 1)[1]  # \| inside a cell is escaped
        named = set(re.findall(r"`([a-z_]+)`", main_tools))  # `recall(hops=…)` is an argument, not a tool
        assert named & ALL == MODULES[mod], mod


def test_profiles_and_parsing():
    assert modules_of("full") == tuple(MODULES)
    assert modules_of("core") == ("engram", "relay", "lineage") == PROFILES["core"]
    assert tool_names("core") == CORE and len(CORE) == 29
    assert tool_names("full") == ALL
    assert canonical(" Relay , engram,relay") == "engram,relay"
    assert canonical("core,staleness,forgetting,relations,dedup") == "full"
    assert canonical("lineage,relay,engram") == "core"
    assert tool_names("core,staleness") == CORE | MODULES["staleness"]


@pytest.mark.parametrize("bad", ["", " ", "fulll", "core,", "engram,,relay", "coordination", "recall"])
def test_unknown_or_empty_toolset_is_refused_with_the_valid_names(bad):
    with pytest.raises(ToolsetError) as e:
        canonical(bad)
    valid = "valid: engram, relay, lineage, staleness, forgetting, relations, dedup, core, full"
    assert valid in str(e.value)


def test_process_default_flag_env_and_fail_fast(monkeypatch):
    monkeypatch.delenv("PLEXUS_TOOLSET", raising=False)
    assert default_toolset() == "full"
    monkeypatch.setenv("PLEXUS_TOOLSET", "")
    assert default_toolset() == "full"
    monkeypatch.setenv("PLEXUS_TOOLSET", "relay,engram")
    assert default_toolset() == "engram,relay"
    assert default_toolset("core") == "core"  # the flag wins over the env
    monkeypatch.setenv("PLEXUS_TOOLSET", "nope")
    with pytest.raises(ToolsetError):
        default_toolset()
    with pytest.raises(SystemExit):  # plexus-mcp --toolset nope: argparse error, no server started
        server_mod.main(["--transport", "stdio", "--toolset", "nope"])


# ---------------------------------------------------------------------------------------- stdio / in-memory
async def _names(srv) -> list[str]:
    async with Client(srv) as c:
        return [t.name for t in (await c.list_tools()).tools]


async def test_full_is_the_default_and_unchanged(runtime, monkeypatch):
    monkeypatch.delenv("PLEXUS_TOOLSET", raising=False)
    default = build_server(runtime)
    assert default.toolset == "full"
    async with Client(default) as c:
        listed = (await c.list_tools()).tools
    async with Client(build_server(runtime, "full")) as c:
        full = (await c.list_tools()).tools
    assert [t.name for t in listed] == [t.name for t in full]
    assert set(t.name for t in listed) == ALL and len(listed) == 45
    # same published schemas as the unscoped list (SDK list_tools + compact_schema), byte for byte
    unscoped = await default.list_tools()
    assert [t.model_dump() for t in listed] == [t.model_dump() for t in unscoped]


@pytest.mark.parametrize("spec", ["core", "relay", "engram,lineage", "core,staleness", "dedup"])
async def test_a_toolset_lists_only_its_tools_in_the_usual_order(runtime, spec):
    names = await _names(build_server(runtime, spec))
    assert set(names) == tool_names(spec)
    full_order = await _names(build_server(runtime, "full"))
    assert names == [n for n in full_order if n in tool_names(spec)]


async def test_a_tool_outside_the_toolset_is_not_callable(runtime):
    async with Client(build_server(runtime, "relay")) as c:
        r = await c.call_tool("register_agent", {"agent_id": "a"})
        assert not r.is_error
        r = await c.call_tool("recall", {"agent_id": "a", "query": "x"})
        assert r.is_error
        assert r.content[0].text == (
            "recall: not in this session's toolset 'relay' (it is in module 'engram'); "
            "connect with a toolset that includes 'engram' (e.g. toolset=full)"
        )
        r = await c.call_tool("no_such_tool", {"agent_id": "a"})  # unknown names keep the SDK's error
        assert r.is_error and "Unknown tool" in r.content[0].text


async def test_l8_tools_are_all_in_core(runtime):
    """Every tool the L8 P-arm agents ever called (A2 + P12 transcripts) is in ``core``."""
    used = {"start_session", "claim_next_task", "complete_task", "recall", "assert_fact", "add_source",
            "remember_episode", "record_decision", "handoff", "create_tasks", "verify_artifact",
            "fact_history"}  # fmt: skip
    assert used <= set(await _names(build_server(runtime, "core")))


# ---------------------------------------------------------------------------------------------- HTTP
@pytest.fixture
def http(client):
    rt = Runtime(client=client, embedder=HashEmbedder())
    with TestClient(build_http_app(rt), base_url="http://localhost") as tc:
        yield tc


def _list(http, path, h) -> list[str]:
    r = http.post(path, headers=h, json=_rpc("tools/list", {}, 3))
    assert r.status_code == 200, r.text
    return [t["name"] for t in _body(r)["result"]["tools"]]


def test_http_default_is_full(http, new_tenant):
    p = f"/mcp/t/{new_tenant()}"
    assert set(_list(http, p, _open(http, p))) == ALL


@pytest.mark.parametrize("how", ["query", "header"])
def test_http_toolset_by_query_or_header(http, new_tenant, how):
    t = new_tenant()
    path = f"/mcp/t/{t}?toolset=core" if how == "query" else f"/mcp/t/{t}"
    extra = {} if how == "query" else {"X-Plexus-Toolset": "core"}
    h = _open(http, path, extra)
    assert set(_list(http, path, h)) == CORE
    _result(_call(http, path, h, "start_session", {"agent_id": "a"}))
    res = _body(_call(http, path, h, "pin_fact", {"agent_id": "a", "fact_id": "f"}))["result"]
    assert res["isError"] and "not in this session's toolset 'core'" in res["content"][0]["text"]


def test_http_toolset_is_pinned_to_the_session(http, new_tenant):
    t = new_tenant()
    h = _open(http, f"/mcp/t/{t}?toolset=relay")
    # later requests without the query keep the session's toolset ...
    assert set(_list(http, f"/mcp/t/{t}", h)) == MODULES["relay"]
    # ... and a request naming another one is refused, not silently switched
    r = http.post(f"/mcp/t/{t}?toolset=full", headers=h, json=_rpc("tools/list", {}, 4))
    assert r.status_code == 400 and "uses toolset 'relay', not 'full'" in r.json()["error"]
    # a session opened without a toolset cannot pick one later either
    h2 = _open(http, f"/mcp/t/{t}")
    r = http.post(f"/mcp/t/{t}", headers={**h2, "X-Plexus-Toolset": "core"}, json=_rpc("tools/list", {}, 5))
    assert r.status_code == 400 and "uses toolset 'default', not 'core'" in r.json()["error"]


@pytest.mark.parametrize(
    ("query", "headers", "needle"),
    [
        ("?toolset=coordination", {}, "unknown toolset 'coordination'"),
        ("?toolset=", {}, "empty toolset name"),
        ("", {"X-Plexus-Toolset": "fulll"}, "unknown toolset 'fulll'"),
        ("?toolset=core", {"X-Plexus-Toolset": "relay"}, "name different toolsets"),
    ],
)
def test_http_bad_toolset_is_a_400(http, new_tenant, query, headers, needle):
    r = _init(http, f"/mcp/t/{new_tenant()}{query}", headers)
    assert r.status_code == 400
    msg = json.loads(r.text)["error"]
    assert msg.startswith("invalid toolset: ") and needle in msg


def test_http_server_default_toolset_and_pin_cleanup(client, new_tenant):
    rt = Runtime(client=client, embedder=HashEmbedder())
    with TestClient(build_http_app(rt, toolset="engram"), base_url="http://localhost") as tc:
        t = new_tenant()
        h = _open(tc, f"/mcp/t/{t}")
        assert set(_list(tc, f"/mcp/t/{t}", h)) == MODULES["engram"]
        h_full = _open(tc, f"/mcp/t/{t}?toolset=full")  # a client may still ask for everything
        assert set(_list(tc, f"/mcp/t/{t}", h_full)) == ALL
        mw = tc.app
        sid = h_full["mcp-session-id"]
        assert mw.toolsets[sid] == "full"
        assert tc.delete(f"/mcp/t/{t}", headers=h_full).status_code in (200, 204)
        assert sid not in mw.toolsets and sid not in mw.pins
        mw.max_pins = 1
        _open(tc, f"/mcp/t/{t}?toolset=dedup")
        assert len(mw.toolsets) <= len(mw.pins) == 1  # evicted pins take their toolset with them


def test_l8_harness_toolset_is_arm_p_only(tmp_path):
    from plexus.crucible.l8.run import run_arm

    with pytest.raises(ValueError, match="arm P only"):
        run_arm("B1", 20261017, tmp_path, toolset="core")
