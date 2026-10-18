"""Layer 3 plumbing without an LLM: the baseline MCP server plays the whole Acme scenario with the P3 scripted agents."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

import pytest

from knewat.crucible.l3.baseline_mcp import build_baseline_server
from knewat.crucible.l3.run import BackendWorld, headline_l3, transcript_metrics
from knewat.demo.engine import run as run_engine
from knewat.demo.scenario import FaultScript, load_scenario
from knewat.demo.scripted import ScriptedDriver
from mcp import Client

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


def test_server_exposes_the_knewat_tool_names_and_arguments():
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
        }  # P9-e: Knewat-only audit level on reads
        if name == "recall":  # P7-K: optional Knewat-only arguments (forgetting, hops); baselines have none
            theirs -= {"include_dormant", "forgetting", "hops", "detail"}  # P9-b: hops; P12: detail
        if name == "assert_fact":  # P13: multi-source provenance is Knewat-only; baselines take one source_id
            theirs -= {"source_ids"}
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
                    "content": [{"type": "tool_use", "id": i, "name": f"mcp__knewat__{name}", "input": inp}]
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


def test_headline_l3_states_ties_and_cost():
    def arm(cost):
        return {
            "tasks_done": 12, "tasks_total": 12, "recovery": {"task_finished_after_reclaim": True},
            "decisions_with_evidence": 3, "handoffs_with_facts": 2, "stale_artifacts": 0,
            "contradictions_surfaced": 1, "cost_usd": cost,
        }  # fmt: skip

    lines = headline_l3({"arms": {"P": arm(0.5), "B0": arm(0.25)}})
    assert lines[0].endswith("tasks done P 12/12, B0 12/12.")
    assert "2 of 2 arms (P, B0)" in lines[1]
    assert "no separation between arms" in lines[2]
    assert "P $0.50, B0 $0.25" in lines[3]
    assert headline_l3({"arms": {}}) == []
