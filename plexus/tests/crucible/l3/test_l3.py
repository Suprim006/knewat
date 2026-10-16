"""Layer 3 plumbing without an LLM: the baseline MCP server plays the whole Acme scenario with the P3 scripted agents."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

import pytest

from mcp import Client
from plexus.crucible.l3.baseline_mcp import build_baseline_server
from plexus.crucible.l3.run import BackendWorld, transcript_metrics
from plexus.demo.engine import run as run_engine
from plexus.demo.scenario import FaultScript, load_scenario
from plexus.demo.scripted import ScriptedDriver

TOOLS = {
    "start_session", "remember_episode", "add_source", "assert_fact", "recall", "create_tasks", "claim_next_task",
    "heartbeat", "complete_task", "handoff", "record_decision", "verify_artifact",
}  # fmt: skip


def play_team(backend, **faults):
    sc = load_scenario()
    w = BackendWorld(sc, FaultScript(builder_lease_ms=800, **faults), "l3t", None, backend=backend)

    async def go():
        async with Client(build_baseline_server(backend)) as mcp:
            await run_engine(w, ScriptedDriver(mcp))

    asyncio.run(go())
    return w


def test_server_exposes_the_plexus_tool_names_and_arguments():
    from plexus.mcp.runtime import Runtime  # noqa: F401  (the real surface lives in plexus.mcp.tools)

    async def names(backend):
        async with Client(build_baseline_server(backend)) as mcp:
            return {t.name: t for t in (await mcp.list_tools()).tools}

    class Dummy:
        pass

    tools = asyncio.run(names(Dummy()))
    assert set(tools) == TOOLS
    snap = json.loads(
        open(Path(__file__).resolve().parents[2] / "mcp/snapshots/tools.json", encoding="utf-8").read()
    )
    real = snap  # {tool name: {description, inputSchema}}
    for name in TOOLS:
        mine = set(tools[name].input_schema["properties"])
        theirs = set(real[name]["inputSchema"]["properties"]) - {
            "audit"
        }  # P9-e: Plexus-only audit level on reads
        if name == "recall":  # P7-K: optional Plexus-only arguments (forgetting, hops); baselines have none
            theirs -= {"include_dormant", "forgetting", "hops"}  # P9-b: hops (typed relations)
        assert mine == theirs, (name, mine ^ theirs)


@pytest.mark.parametrize("arm", ["B0", "B1"])
def test_scripted_team_completes_on_a_baseline(arm, opened):
    b = opened(arm)
    w = play_team(b)
    assert {t["id"]: t["status"] for t in b.list_tasks()} == {t.id: "done" for t in w.scenario.all_tasks}
    assert [e["event"] for e in w.events if e["event"] in ("kill_builder", "reclaim", "publish_v2")] == [
        "kill_builder", "reclaim", "publish_v2",
    ]  # fmt: skip
    reclaim = next(e for e in w.events if e["event"] == "reclaim")
    assert reclaim["agent"] == "researcher" and reclaim["reclaimed_from"] == "builder"
    cur = [f for f in b.facts("Acme Notes API", "api_version") if f["status"] == "active"]
    assert [f["value"] for f in cur] == ["v2"]
    assert w.statuses()["t03-design-endpoints"]["status"] == "done"


def test_transcript_metrics_counts_the_agents_own_calls():
    def tu(i, name, inp):
        return json.dumps(
            {
                "type": "assistant",
                "message": {
                    "content": [{"type": "tool_use", "id": i, "name": f"mcp__plexus__{name}", "input": inp}]
                },
            }
        )

    def tr(i, content, err=False):
        return json.dumps(
            {
                "type": "user",
                "message": {
                    "content": [
                        {
                            "type": "tool_result",
                            "tool_use_id": i,
                            "is_error": err,
                            "content": [{"type": "text", "text": json.dumps(content)}],
                        }
                    ]
                },
            }
        )

    t1 = "\n".join([
        tu("a", "assert_fact", {}), tr("a", {"fact_id": "f", "superseded": ["x"], "contradicts": []}),
        tu("b", "record_decision", {"task_id": "t", "based_on_fact_ids": ["f"]}), tr("b", {}, err=True),
    ])  # fmt: skip
    t2 = "\n".join(
        [
            tu("c", "complete_task", {"task_id": "t10", "artifacts": [{"summary": "docs for API v1"}]}),
            tu("d", "handoff", {"task_id": "t10", "fact_ids": []}),
        ]
    )
    m = transcript_metrics({"01-researcher-ingest-v2.jsonl": t1, "02-researcher-t10.jsonl": t2})
    assert m["tool_calls"] == 4 and m["tool_errors"] == 1 and m["supersessions_surfaced"] == 1
    assert (
        m["decisions"] == 1
        and m["decisions_with_evidence"] == 1
        and m["handoffs"] == 1
        and m["handoffs_with_facts"] == 0
    )
    assert m["stale_artifacts"] == 1 and m["stale_artifact_tasks"] == ["t10"]
