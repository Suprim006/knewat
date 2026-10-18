"""The real-Claude orchestrator, tested with a stand-in ``claude`` (tests/demo/fake_claude.py). No LLM, no subscription."""

from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

import pytest

from knewat.demo import orchestrator as orch
from knewat.demo.engine import Turn, World
from knewat.demo.engine import run as run_engine
from knewat.demo.scenario import FaultScript, load_scenario

from ..conftest import TEST_DB_HOST, TEST_DB_PORT
from .conftest import rows

FAKE = [sys.executable, str(Path(__file__).parent / "fake_claude.py")]


def _cfg(tmp_path, tenant, **kw) -> orch.ClaudeConfig:
    return orch.ClaudeConfig(
        workdir=tmp_path,
        mcp_config=orch.write_mcp_config(
            tmp_path / "mcp.json",
            tenant,
            "knewat-mcp",
            {"FALKORDB_HOST": TEST_DB_HOST, "FALKORDB_PORT": str(TEST_DB_PORT)},  # never the dev DB on 6379
        ),
        launcher=FAKE,
        **kw,
    )


def _world(client, tenant, **faults) -> World:
    return World(load_scenario(), FaultScript(builder_lease_ms=500, **faults), tenant, client)


def test_command_line_is_locked_down(tmp_path):
    cfg = orch.ClaudeConfig(
        workdir=tmp_path, mcp_config=tmp_path / "mcp.json", model="sonnet", max_turns=20, claude_bin="claude"
    )
    cmd = orch.build_command(cfg, "do it", "be a planner")
    assert cmd[:3] == ["claude", "-p", "do it"]
    assert "--strict-mcp-config" in cmd and cmd[cmd.index("--allowedTools") + 1] == "mcp__knewat__*"
    assert cmd[cmd.index("--tools") + 1] == ""  # no built-in tools at all
    assert cmd[cmd.index("--max-turns") + 1] == "20" and cmd[cmd.index("--model") + 1] == "sonnet"
    assert cmd[cmd.index("--output-format") + 1] == "stream-json" and "--verbose" in cmd
    assert "--bare" not in cmd and "--dangerously-skip-permissions" not in cmd


def test_env_drops_the_api_key():
    env = orch.clean_env({"ANTHROPIC_API_KEY": "sk-x", "PATH": "p"})
    assert "ANTHROPIC_API_KEY" not in env and env["PATH"] == "p"


def test_mcp_config_binds_the_run_tenant(tmp_path):
    p = orch.write_mcp_config(tmp_path / "m.json", "run_a", "C:/x/knewat-mcp.exe", {"FALKORDB_PORT": "6386"})
    srv = json.loads(p.read_text())["mcpServers"]["knewat"]
    assert srv["command"] == "C:/x/knewat-mcp.exe"
    assert srv["args"] == ["--transport", "stdio", "--tenant", "run_a"]
    assert srv["env"]["FALKORDB_PORT"] == "6386"


def test_prompts_carry_the_assignment(client, tenant_unused=None):
    w = World(load_scenario(), FaultScript(), "t_prompt", client)
    assert all(t.id in orch.init_prompt(w) for t in w.scenario.tasks)
    st = orch.TeamState()
    st.absorb("assert_fact", {"predicate": "api_version", "value": "v1"}, {"fact_id": "F1", "superseded": []})
    st.absorb(
        "assert_fact", {"predicate": "api_version", "value": "v2"}, {"fact_id": "F2", "superseded": ["F1"]}
    )
    assert "F2" in st.render() and "F1" not in st.render()
    task = w.scenario.task("t01-gather-requirements")
    p = orch.task_prompt(w, Turn("task", "researcher", task.id, task=task), st, 90000)
    assert "Task id: t01-gather-requirements" in p and "lease_ms=90000" in p
    assert "=== DOCUMENT: acme-docs/01_product_brief.md" in p and "Acme Notes is a small notes service" in p
    t3 = w.scenario.task("t03-design-endpoints")
    p = orch.task_prompt(w, Turn("task", "researcher", t3.id, task=t3, reclaim_from="builder"), st, 90000)
    assert "abandoned by 'builder'" in p


def test_full_run_with_a_killed_builder_and_a_published_v2(client, demo_tenants, tmp_path, monkeypatch):
    monkeypatch.setenv("FAKE_HANG_BUILDER", "1")
    tenant = demo_tenants()
    w = _world(client, tenant, kill_builder_at=5, publish_v2_at=8)
    driver = orch.ClaudeDriver(_cfg(tmp_path, tenant))
    asyncio.run(run_engine(w, driver))
    assert w.faults.fired.keys() == {"kill_builder", "publish_v2"}
    assert w.faults.fired["kill_builder"] >= 5
    names = [e["event"] for e in w.events]
    assert names.index("kill_builder") < names.index("lease_wait") < names.index("reclaim")
    assert rows(client, tenant, "MATCH (t:Task) WHERE t.status <> 'done' RETURN count(t)")[0][0] == 0
    assert (
        rows(client, tenant, "MATCH (t:Task) RETURN count(t)")[0][0] == 12
    )  # the planner added t12 after v2
    claims = rows(
        client,
        tenant,
        "MATCH (a:Agent)-[c:CLAIMED]->(:Task {id:'t03-design-endpoints'}) RETURN a.id, c.reclaimed_from ORDER BY c.at",
    )
    assert claims == [["builder", ""], ["researcher", "builder"]]
    summary = driver.summary(w)
    assert summary["permission_denials"] == [] and summary["claude_processes"] == len(driver.reports)
    assert any(r["killed"] for r in summary["per_turn"]) and summary["total_cost_usd"] > 0
    assert (tmp_path / "transcripts").glob("*.jsonl")


def test_permission_denial_aborts_the_run(client, demo_tenants, tmp_path, monkeypatch):
    monkeypatch.setenv("FAKE_DENY", "1")
    tenant = demo_tenants()
    w = _world(client, tenant)
    driver = orch.ClaudeDriver(_cfg(tmp_path, tenant))
    with pytest.raises(orch.ClaudeRunError, match="permission_denials"):
        asyncio.run(run_engine(w, driver))


def test_stop_after_turns_is_a_pilot_not_an_error(client, demo_tenants, tmp_path):
    tenant = demo_tenants()
    w = _world(client, tenant, kill_builder_at=None, publish_v2_at=None)
    driver = orch.ClaudeDriver(_cfg(tmp_path, tenant, stop_after_turns=3))
    with pytest.raises(orch.StopRun):
        asyncio.run(run_engine(w, driver))
    assert [r.name for r in driver.reports] == ["init", "t01-gather-requirements", "t02-choose-api-version"]
    assert [t["status"] for t in w.statuses().values()].count("done") == 2


def test_transcripts_are_sanitised(tmp_path):
    init = {
        "type": "system",
        "subtype": "init",
        "cwd": str(tmp_path),
        "slash_commands": ["private-plugin:thing"],
        "plugins": ["x"],
        "tools": ["mcp__knewat__recall"],
        "mcp_servers": [{"name": "knewat", "status": "connected"}],
        "model": "claude-x",
    }
    other = {"type": "user", "note": f"path {tmp_path} and {Path.home()}"}
    text = json.dumps(init) + "\n" + json.dumps(other) + "\n"
    out = orch.sanitize_transcript(text, tmp_path)
    first, second = (json.loads(x) for x in out.splitlines())
    assert set(first) == {"type", "subtype", "tools", "mcp_servers", "model"}
    assert "<workdir>" in second["note"] and "<home>" in second["note"] and str(tmp_path) not in out


def test_each_prompt_carries_the_shared_step_counter(client):
    w = World(load_scenario(), FaultScript(), "t_hint", client)
    w.step = 16
    assert "step=17 on your first call" in orch.init_prompt(w)
    sp = orch.special_prompt(w, Turn("special", "researcher", "ingest-v2"), orch.TeamState())
    assert "step=17" in sp and "06_api_style_guide_v2" in sp and "do NOT call claim_next_task" in sp


def test_recorded_transcripts_contain_no_local_paths(tmp_path):
    cfg = orch.ClaudeConfig(workdir=tmp_path, mcp_config=tmp_path / "m.json")
    d = orch.ClaudeDriver(cfg)
    line = json.dumps(
        {"type": "system", "subtype": "init", "cwd": str(tmp_path), "plugins": [{"path": str(Path.home())}]}
    )
    d.reports.append(orch.TurnReport(1, "planner", "init", "init", transcript=line + "\n"))
    out = d.transcripts()["01-planner-init.jsonl"]
    assert str(tmp_path) not in out and str(Path.home()) not in out and "plugins" not in out
