"""Layer 3 pilot runner: the real 3-agent team (unmodified ``claude -p``) once per arm, same scheduler and faults.

    python -m plexus.crucible.l3.run run --arms B0,B1,P --model sonnet --port 6378 --budget-usd 4

The scheduler, role prompts, per-turn prompts, fault script and the ``claude -p`` driver are the P3 demo's
(``plexus.demo``). What differs per arm is only the MCP server behind the ``plexus`` name (see
:mod:`plexus.crucible.l3.baseline_mcp`) and, for B0/B1, how the *harness* reads task state (:class:`BackendWorld`;
the agents never see this). Metrics come from the agents' own stream-json transcripts and the final task states, so
they are the same code for every arm. n = 1 run per arm: a pilot, not a benchmark (BASELINE §3 wants >= 5).
"""

from __future__ import annotations

import argparse
import asyncio
import json
import shutil
import sys
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from plexus.crucible import results as H
from plexus.crucible.api import BackendSpec
from plexus.crucible.backends import open_backend
from plexus.crucible.util import iso_utc, run_stamp
from plexus.demo.engine import World
from plexus.demo.engine import run as run_engine
from plexus.demo.orchestrator import (
    REAL_BUILDER_LEASE_MS,
    ClaudeConfig,
    ClaudeDriver,
    ClaudeRunError,
    StopRun,
    plexus_mcp_command,
    write_mcp_config,
)
from plexus.demo.scenario import FaultScript, Scenario, load_scenario

DEMO_DATA = Path(__file__).resolve().parents[4] / "demo_data" / "crucible"
OUT_DIR = DEMO_DATA / "l3"
ARMS = ("B0", "B1", "P")


class _BackendRelay:
    """The slice of ``Relay`` the driver uses (``task_status``, ``ready_tasks``) over a CoordinationBackend."""

    def __init__(self, backend: Any, scenario: Scenario):
        self.b, self.sc = backend, scenario

    def task_status(self, task_id: str) -> dict[str, Any] | None:
        return self.b.task_status(task_id)

    def ready_tasks(self, limit: int = 50) -> list[dict[str, Any]]:
        now = int(time.time() * 1000)
        have = {t["id"]: t for t in self.b.list_tasks()}
        order = {t.id: i for i, t in enumerate(self.sc.all_tasks)}
        out = []
        for tid, t in have.items():
            free = t["status"] == "open" or (t["status"] == "claimed" and t["lease_until"] < now)
            deps = self.sc.task(tid).depends_on
            if free and all(have.get(d, {}).get("status") == "done" for d in deps):
                out.append({**t, "priority": self.sc.task(tid).priority})
        out.sort(key=lambda r: (-r["priority"], order[r["id"]]))
        return out[:limit]


@dataclass
class BackendWorld(World):
    """A :class:`World` whose harness-side state reads come from a baseline backend instead of a Plexus graph."""

    backend: Any = None

    def __post_init__(self) -> None:
        self.graph = ""
        self.relay = _BackendRelay(self.backend, self.scenario)  # type: ignore[assignment]

    def ready(self) -> list[dict[str, Any]]:
        return self.relay.ready_tasks(limit=50)

    def statuses(self) -> dict[str, dict[str, Any]]:
        out = {}
        for t in self.scenario.all_tasks:
            st = self.backend.task_status(t.id)
            if st is not None:
                out[t.id] = st
        return out


# ------------------------------------------------------------------------------------------------ metrics
def parse_transcript(text: str) -> list[dict[str, Any]]:
    out = []
    for line in text.splitlines():
        try:
            out.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return out


def _result_json(content: Any) -> dict[str, Any]:
    if isinstance(content, list):
        content = "".join(b.get("text", "") for b in content if isinstance(b, dict))
    try:
        val = json.loads(content) if isinstance(content, str) else {}
    except json.JSONDecodeError:
        return {}
    return val if isinstance(val, dict) else {}


def transcript_metrics(transcripts: dict[str, str]) -> dict[str, Any]:
    """Arm-independent counts from the agents' own tool calls (file names are ``NN-agent-turn.jsonl``)."""
    calls = errors = 0
    decisions: list[dict[str, Any]] = []
    handoffs: list[dict[str, Any]] = []
    artifacts: list[dict[str, Any]] = []
    contradictions = supersessions = 0
    v2_turn = None
    for fname in sorted(transcripts):
        turn = int(fname.split("-", 1)[0])
        pending: dict[str, tuple[str, dict[str, Any]]] = {}
        if "ingest-v2" in fname:
            v2_turn = turn
        for ev in parse_transcript(transcripts[fname]):
            for block in (
                (ev.get("message") or {}).get("content", []) if isinstance(ev.get("message"), dict) else []
            ):
                if not isinstance(block, dict):
                    continue
                if block.get("type") == "tool_use":
                    name = str(block.get("name", "")).removeprefix("mcp__plexus__")
                    inp = block.get("input") or {}
                    pending[block["id"]] = (name, inp)
                    calls += 1
                    if name == "record_decision":
                        decisions.append(
                            {
                                "turn": turn,
                                "task": inp.get("task_id"),
                                "based_on": len(inp.get("based_on_fact_ids") or []),
                            }
                        )
                    elif name == "handoff":
                        handoffs.append(
                            {
                                "turn": turn,
                                "task": inp.get("task_id"),
                                "facts": len(inp.get("fact_ids") or []),
                            }
                        )
                    elif name == "complete_task":
                        for a in inp.get("artifacts") or []:
                            artifacts.append(
                                {
                                    "turn": turn,
                                    "task": inp.get("task_id"),
                                    "summary": str(a.get("summary", "")),
                                }
                            )
                elif block.get("type") == "tool_result":
                    name, _ = pending.pop(block.get("tool_use_id"), ("", {}))
                    if block.get("is_error"):
                        errors += 1
                    elif name == "assert_fact":
                        data = _result_json(block.get("content"))
                        contradictions += bool(data.get("contradicts"))
                        supersessions += bool(data.get("superseded"))
    stale = [
        a
        for a in artifacts
        if v2_turn and a["turn"] > v2_turn and "v1" in a["summary"] and "v2" not in a["summary"]
    ]
    return {
        "tool_calls": calls,
        "tool_errors": errors,
        "decisions": len(decisions),
        "decisions_with_evidence": sum(d["based_on"] > 0 for d in decisions),
        "handoffs": len(handoffs),
        "handoffs_with_facts": sum(h["facts"] > 0 for h in handoffs),
        "artifacts": len(artifacts),
        "stale_artifacts": len(stale),
        "stale_artifact_tasks": [a["task"] for a in stale],
        "contradictions_surfaced": contradictions,
        "supersessions_surfaced": supersessions,
    }


def arm_metrics(
    arm: str,
    w: World,
    driver: ClaudeDriver,
    status: str,
    error: str,
    wall_s: float,
    final: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    summ = driver.summary(w)
    tasks = w.scenario.all_tasks
    done = [t.id for t in tasks if final.get(t.id, {}).get("status") == "done"]
    kill = next((e for e in w.events if e["event"] == "kill_builder"), None)
    reclaim = next((e for e in w.events if e["event"] == "reclaim"), None)
    recovered = bool(kill and reclaim and final.get(kill["task"], {}).get("status") == "done")
    m: dict[str, Any] = {
        "status": status,
        "error": error,
        "completed": status == "completed" and len(done) == len(tasks),
        "tasks_done": len(done),
        "tasks_total": len(tasks),
        "tasks_not_done": [t.id for t in tasks if t.id not in done],
        "faults_fired": dict(w.faults.fired),
        "recovery": {
            "builder_killed": bool(kill),
            "reclaimed_by": reclaim["agent"] if reclaim else None,
            "task_finished_after_reclaim": recovered,
            "seconds_from_kill_to_reclaim": round(reclaim["t"] - kill["t"], 1) if kill and reclaim else None,
        },
        "claude_processes": summ["claude_processes"],
        "claude_turns": summ["claude_turns"],
        "tokens": summ["tokens"],
        "total_tokens": sum(summ["tokens"].values()),
        "cost_usd": summ["total_cost_usd"],
        "wall_s": round(wall_s, 1),
        "permission_denials": len(summ["permission_denials"]),
        "per_turn": summ["per_turn"],
    }
    m.update(transcript_metrics(driver.transcripts()))
    return m


# ------------------------------------------------------------------------------------------------ one arm
def run_arm(
    arm: str, *, model: str, work: Path, host: str, port: int, embedder: str, max_turns: int, log: Any,
    stop_after_turns: int | None = None, launcher: list[str] | None = None, lease_ms: int = REAL_BUILDER_LEASE_MS,
    turn_timeout_s: int = 900,
) -> tuple[dict[str, Any], dict[str, str]]:  # fmt: skip
    tenant = f"l3_{arm.lower()}_{time.strftime('%H%M%S')}"
    workdir = work / arm
    workdir.mkdir(parents=True, exist_ok=True)
    cfgfile = workdir / "mcp.json"
    client = None
    if arm == "P":
        from plexus.graph.client import GraphClient
        from plexus.graph.schema import apply_schema
        from plexus.graph.tenancy import graph_name

        client = GraphClient(host=host, port=port)
        apply_schema(client, graph_name(tenant))
        write_mcp_config(
            cfgfile, tenant, plexus_mcp_command(),
            env={"FALKORDB_HOST": host, "FALKORDB_PORT": str(port), "PLEXUS_EMBEDDER": embedder},
        )  # fmt: skip
        backend = None
    else:
        root = str(work / "arms")
        backend = open_backend(BackendSpec(arm=arm, tenant=tenant, root=root, embedder=embedder))
        cfgfile.write_text(
            json.dumps(
                {
                    "mcpServers": {
                        "plexus": {
                            "command": sys.executable,
                            "args": [
                                "-m",
                                "plexus.crucible.l3.baseline_mcp",
                                "--arm",
                                arm,
                                "--root",
                                root,
                                "--tenant",
                                tenant,
                                "--embedder",
                                embedder,
                            ],
                            "env": {},
                        }
                    }
                },
                indent=2,
            ),
            encoding="utf-8",
        )
    cfg = ClaudeConfig(
        workdir=workdir, mcp_config=cfgfile, model=model, max_turns=max_turns, launcher=launcher,
        stop_after_turns=stop_after_turns, turn_timeout_s=turn_timeout_s,
    )  # fmt: skip
    faults = FaultScript(builder_lease_ms=lease_ms)
    sc = load_scenario()
    if arm == "P":
        w = World(sc, faults, tenant, client)
    else:
        w = BackendWorld(sc, faults, tenant, None, backend=backend)
    driver = ClaudeDriver(cfg, on_event=log)
    status, error = "completed", ""
    t0 = time.time()
    try:
        asyncio.run(run_engine(w, driver))
    except StopRun:
        status = "stopped (--stop-after-turns)"
    except (ClaudeRunError, Exception) as exc:  # noqa: BLE001 - recorded, not hidden
        status, error = "aborted", f"{type(exc).__name__}: {exc}"[:300]
    final = w.statuses()
    metrics = arm_metrics(arm, w, driver, status, error, time.time() - t0, final)
    metrics["events"] = [{k: v for k, v in e.items() if k != "t"} for e in w.events]
    transcripts = driver.transcripts()
    if backend is not None:
        backend.close()
    if client is not None:
        from plexus.graph.tenancy import graph_name

        client.delete_graph(graph_name(tenant))
        client.close()
    return metrics, transcripts


# ------------------------------------------------------------------------------------------------ results
L3_HONESTY = [
    "L3 pilot: ONE run per arm (BASELINE §3 asks for >= 5 with fixed seeds); LLM runs are noisy, so nothing here is a ranking.",
    "B0/B1 agents talk to a purpose-built stdio MCP server with the same tool names and argument names as the Plexus tools the scenario uses (crucible/l3/baseline_mcp.py); they have no lineage tools and `verify_artifact` is only acknowledged. P uses the real plexus-mcp.",
    "The scheduler, prompts, faults (builder killed at step 15, style guide v2 at step 20) and model are the P3 demo's and identical across arms. The poison fault is off.",
    "Metrics come from the agents' stream-json transcripts and the final task states; 'stale artifacts' is a text heuristic (an artifact summary written after v2 was published that names v1 and not v2).",
]


def headline_l3(layer: dict[str, Any]) -> list[str]:
    """Plain statements from the numbers, ties and losses included (BASELINE §6 rule 3)."""
    arms = layer["arms"]
    if not arms:
        return []
    out = []
    done = {a: f"{m['tasks_done']}/{m['tasks_total']}" for a, m in arms.items()}
    out.append("L3 pilot (n=1 per arm): tasks done " + ", ".join(f"{a} {d}" for a, d in done.items()) + ".")
    rec = [a for a, m in arms.items() if m["recovery"]["task_finished_after_reclaim"]]
    out.append(
        f"L3: the killed builder's task was reclaimed and finished in {len(rec)} of {len(arms)} arms ({', '.join(rec) or 'none'})."
    )
    keys = ("decisions_with_evidence", "handoffs_with_facts", "stale_artifacts", "contradictions_surfaced")
    if len({tuple(m[k] for k in keys) for m in arms.values()}) == 1:
        out.append(
            "L3: no separation between arms on evidence-carrying decisions, fact-carrying handoffs, stale artifacts or surfaced contradictions (identical counts)."
        )
    cost = {a: m["cost_usd"] for a, m in arms.items()}
    out.append(
        "L3: cost per full run "
        + ", ".join(f"{a} ${c:.2f}" for a, c in cost.items())
        + "; with n=1 this is noise-level, not a ranking."
    )
    return out


def render_l3_report(layer: dict[str, Any]) -> str:
    arms = layer["arms"]
    w = [
        "# Crucible L3 pilot: real 3-agent team, one run per arm\n",
        f"Model `{layer['model']}`, n=1 per arm.\n",
    ]
    w.append("| Metric | " + " | ".join(arms) + " |\n|---|" + "---|" * len(arms))
    rows = [
        ("status", lambda a: a["status"]),
        ("tasks done", lambda a: f"{a['tasks_done']}/{a['tasks_total']}"),
        (
            "builder killed -> reclaimed by",
            lambda a: (
                f"{a['recovery']['reclaimed_by']}, finished={a['recovery']['task_finished_after_reclaim']}"
            ),
        ),
        ("decisions (with evidence)", lambda a: f"{a['decisions']} ({a['decisions_with_evidence']})"),
        ("handoffs (carrying facts)", lambda a: f"{a['handoffs']} ({a['handoffs_with_facts']})"),
        ("stale artifacts", lambda a: a["stale_artifacts"]),
        ("contradictions surfaced at write time", lambda a: a["contradictions_surfaced"]),
        ("tool calls / errors", lambda a: f"{a['tool_calls']} / {a['tool_errors']}"),
        ("claude processes", lambda a: a["claude_processes"]),
        ("tokens", lambda a: f"{a['total_tokens']:,}"),
        ("cost (USD)", lambda a: f"{a['cost_usd']:.3f}"),
        ("wall time (s)", lambda a: a["wall_s"]),
    ]
    for name, fn in rows:
        w.append(f"| {name} | " + " | ".join(str(fn(a)) for a in arms.values()) + " |")
    w.append("\n## Headline\n\n" + "\n".join(f"- {h}" for h in layer.get("headline", [])))
    w.append("\n## Honesty\n\n" + "\n".join(f"- {h}" for h in L3_HONESTY))
    return "\n".join(w) + "\n"


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="crucible-l3")
    sub = ap.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("run")
    r.add_argument("--arms", default=",".join(ARMS))
    r.add_argument("--model", default="sonnet")
    r.add_argument("--max-turns", type=int, default=25)
    r.add_argument("--host", default="127.0.0.1")
    r.add_argument("--port", type=int, default=6378)
    r.add_argument("--embedder", default="hash", choices=("fastembed", "hash"))
    r.add_argument("--out", type=Path, default=OUT_DIR)
    r.add_argument("--stop-after-turns", type=int, default=None)
    r.add_argument(
        "--budget-usd", type=float, default=None, help="stop before starting an arm once this is spent"
    )
    a = ap.parse_args(argv)
    started = time.time()
    run_id = run_stamp() + "-pilot"
    work = Path(tempfile.mkdtemp(prefix="crucible-l3-"))
    arms: dict[str, Any] = {}
    spent = 0.0
    out = a.out / run_id
    (out / "transcripts").mkdir(parents=True, exist_ok=True)
    try:
        for arm in [x for x in a.arms.split(",") if x]:
            if a.budget_usd is not None and spent >= a.budget_usd:
                print(f"L3: budget ${a.budget_usd} reached; skipping {arm}", flush=True)
                continue
            print(f"== L3 arm {arm} ==", flush=True)
            m, tr = run_arm(
                arm, model=a.model, work=work, host=a.host, port=a.port, embedder=a.embedder, max_turns=a.max_turns,
                log=lambda s: print(s, flush=True), stop_after_turns=a.stop_after_turns,
            )  # fmt: skip
            arms[arm] = m
            spent += m["cost_usd"]
            for name, text in tr.items():
                (out / "transcripts" / f"{arm}-{name}").write_text(text, encoding="utf-8", newline="\n")
            print(
                f"{arm}: {m['status']} {m['tasks_done']}/{m['tasks_total']} tasks, ${m['cost_usd']}, {m['wall_s']}s",
                flush=True,
            )
    finally:
        shutil.rmtree(work, ignore_errors=True)
    layer = {
        "title": "End-to-end team outcomes (pilot, n=1)",
        "model": a.model,
        "arms": arms,
        "honesty": L3_HONESTY,
    }
    layer["headline"] = headline_l3(layer)
    doc = {
        "schema_version": H.SCHEMA_VERSION, "kind": "crucible-results",
        "run": {"id": run_id, "started_at": iso_utc(started),
                "finished_at": iso_utc(), "duration_s": round(time.time() - started, 1),
                "quick": True, "command": "python -m plexus.crucible.l3.run " + " ".join(argv if argv is not None else sys.argv[1:]),
                "layers": ["L3"]},
        "config": {"arms": list(arms), "l3": {"model": a.model, "max_turns": a.max_turns, "runs_per_arm": 1}},
        "arms": H.arms_section([x for x in arms if x in ("B0", "B1", "B2", "P")]),
        "layers": {"L3": layer},
        "summary": {"headline": layer["headline"]},
        "honesty": L3_HONESTY,
    }  # fmt: skip
    (out / "results.json").write_text(json.dumps(doc, indent=2) + "\n", encoding="utf-8", newline="\n")
    (out / "report.md").write_text(render_l3_report(layer), encoding="utf-8", newline="\n")
    shutil.copyfile(out / "results.json", a.out / "latest.json")
    print(f"results: {out / 'results.json'}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
