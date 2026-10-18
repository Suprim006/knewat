"""Assemble ``results.json`` (the schema the View Results page reads) and write it with ``report.md``.

Shape (``schema_version`` 1)::

    {
      "schema_version": 1, "kind": "crucible-results",
      "run":         {id, started_at, finished_at, duration_s, quick, command, layers: [..]},
      "environment": {python, platform, cpu_count, in_docker, git_commit, embedder, falkordb: {.., graph_config}},
      "config":      {seeds: [..], l1: {..}, l4: {..}, arms: [..]},
      "arms":        {<arm>: {label, represents, description, isolation, capabilities: [..]}},
      "layers": {
        "L1": {title, tests: {C1: {title, metric, pass_bar}},
               arms: {<arm>: {tests: {C1: {runs, runs_passed, passed, unsupported, violations_total,
                                           metrics: {name: {min, median, max, sum}}, runs_detail: [..]}}}}},
        "L4": {title, claim_sweep: [..], recall_sweep: [..], tenant_sweep: [..], notes: [..]},
        "ablation": {title, stripped_relationship_types, capabilities: [..], l1_rerun: {..}, summary: {..}}
      },
      "summary": {l1_matrix: {C1: {B0: "pass"|"FAIL"|"n/a"}}, headline: [..]},
      "honesty": [..]
    }
"""

from __future__ import annotations

import json
import os
import shutil
import time
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from knewat.crucible import environment
from knewat.crucible.config import L1Config, L4Config
from knewat.crucible.l1 import TESTS
from knewat.crucible.util import iso_utc, run_stamp

SCHEMA_VERSION = 1

ARM_INFO: dict[str, dict[str, str]] = {
    "B0": {
        "represents": "How Claude Code (CLAUDE.md, auto-memory, agent-team task list) and Hermes (MEMORY.md, kanban, files) coordinate today",
        "description": "MEMORY.md + JSON task list under inter-process file locks (flock), atomic os.replace writes, append-only per-agent JSONL logs",
    },
    "B1": {
        "represents": '"Just use a relational database"',
        "description": "SQLite in WAL mode, BEGIN IMMEDIATE transactions, FTS5 recall, recursive CTEs for provenance",
    },
    "B2": {
        "represents": "Retrieval-based memory (Mem0-style)",
        "description": "Same local bge-small embeddings as Knewat, stored in SQLite + numpy brute-force cosine. Hybrid: claims, decisions and handoffs use B1's SQLite tables because a vector store cannot do atomic claims",
    },
    "P": {
        "represents": "Knewat: FalkorDB 6.0.2, one graph per tenant, deterministic Cypher",
        "description": "Engram/Relay/Lineage service layer called directly (memory, decision and handoff calls also write Steps and READ/WROTE edges)",
    },
    "P-mcp": {
        "represents": "Knewat as the MCP server runs it",
        "description": "Same as P, but every call goes through Runtime._run: a Step and a ToolCall node are written per call (no JSON transport or network hop to the MCP server)",
    },
}

HONESTY = [
    "Synthetic workloads and data only; one scenario family, a single-node database, scripted (non-LLM) workers.",
    "L1 workers are threads sharing one backend object (each with its own DB connection / file descriptors); only C2's victims are separate OS processes killed with SIGKILL. Concurrency is real but not deterministic: seeds fix the workload (priorities, DAG shape, values, query times), not the interleaving.",
    "Violations are reported as exact counts summed over all runs, never averaged.",
    "B0 and B1 are configured competently (locks / transactions). Where they match Knewat the table says so; Knewat's advantage is claimed only for what a graph does better: provenance, dependency traversal, time travel, contradictions at write time and cascading forget.",
    "L2 (provenance questions answered by an LLM for baselines) and L3 (end-to-end LLM agents) are out of scope of this run.",
    "L4 client latency is measured by Python threads in one process: at high worker counts it includes GIL queuing. Server-side run_time_ms is shown next to it for the Knewat arms.",
    "C5 probes each arm's tool API and, for Knewat, the MCP runtime's tenant binding (a header cannot rebind a connection). It does not probe the HTTP View API: that API is read-only, names the tenant in the URL and has no authentication in v1, so isolation there is by deployment. For B0/B1/B2 nothing stops a process with file access from opening another tenant's directory, and Knewat does not enforce per-graph access control inside FalkorDB either; a client with database access can query any graph.",
    "BASELINE §1 asks for one container per arm. B0/B1/B2 are embedded libraries with no server, so they run inside the crucible container; only FalkorDB (the Knewat arms) is a separate container.",
    "Numbers from `--quick` runs, or from outside Docker (Windows port forward adds ~10 ms per round trip), are not the published figures.",
]


def default_results_dir() -> Path:
    env = os.environ.get("CRUCIBLE_RESULTS_DIR")
    return Path(env) if env else Path(__file__).resolve().parent / "results"


def new_run_id(quick: bool) -> str:
    return run_stamp() + ("-quick" if quick else "")


def arms_section(arms: Sequence[str]) -> dict[str, Any]:
    from knewat.crucible.backends.files import FilesBackend
    from knewat.crucible.backends.knewat import KnewatBackend
    from knewat.crucible.backends.sqlite import SqliteBackend
    from knewat.crucible.backends.vector import VectorBackend

    classes = {
        "B0": FilesBackend,
        "B1": SqliteBackend,
        "B2": VectorBackend,
        "P": KnewatBackend,
        "P-mcp": KnewatBackend,
    }
    labels = {"B0": "Files", "B1": "SQLite", "B2": "Vector", "P": "Knewat", "P-mcp": "Knewat (MCP path)"}
    out: dict[str, Any] = {}
    for a in arms:
        cls = classes[a]
        out[a] = {
            "label": labels[a],
            **ARM_INFO[a],
            "isolation": cls.isolation,
            "capabilities": sorted(cls.capabilities),
        }
    return out


def l1_matrix(l1_arms: dict[str, Any], tests: Sequence[str]) -> dict[str, dict[str, str]]:
    m: dict[str, dict[str, str]] = {}
    for t in tests:
        m[t] = {}
        for arm, res in l1_arms.items():
            r = res["tests"].get(t)
            if r is None:
                continue
            m[t][arm] = "n/a" if r["unsupported"] else ("pass" if r["passed"] else "FAIL")
    return m


def headline(matrix: dict[str, dict[str, str]], l1_arms: dict[str, Any]) -> list[str]:
    """Plain statements generated from the numbers, including ties and losses (BASELINE §6 rule 3)."""
    lines: list[str] = []
    arms = sorted({a for row in matrix.values() for a in row})
    if "P" not in arms:
        return lines
    for arm in (a for a in arms if a != "P"):
        ties = [t for t, row in matrix.items() if row.get(arm) == row.get("P") == "pass"]
        losses = [t for t, row in matrix.items() if row.get(arm) == "pass" and row.get("P") == "FAIL"]
        wins = [t for t, row in matrix.items() if row.get("P") == "pass" and row.get(arm) in ("FAIL", "n/a")]
        both_fail = [t for t, row in matrix.items() if row.get(arm) == row.get("P") == "FAIL"]
        label = arm
        if ties:
            lines.append(f"{label} matches Knewat (0 violations on both) on {', '.join(ties)}.")
        if wins:
            lines.append(f"Knewat passes where {label} does not: {', '.join(wins)}.")
        if losses:
            lines.append(f"{label} passes where Knewat FAILS: {', '.join(losses)}.")
        if both_fail:
            lines.append(f"Both {label} and Knewat fail: {', '.join(both_fail)}.")
    return lines


def assemble(
    *,
    run_id: str,
    started: float,
    quick: bool,
    command: str,
    l1_cfg: L1Config | None,
    l4_cfg: L4Config | None,
    l1: dict[str, Any] | None,
    l4: dict[str, Any] | None,
    ablation: dict[str, Any] | None,
    host: str,
    port: int,
    embedder: str,
) -> dict[str, Any]:
    finished = time.time()
    layers: dict[str, Any] = {}
    arms_used: list[str] = []
    summary: dict[str, Any] = {}
    if l1 is not None and l1_cfg is not None:
        l1_arms = {arm: {"tests": tests} for arm, tests in l1.items()}
        layers["L1"] = {
            "title": "Correctness under concurrency (C1-C8)",
            "tests": {t: TESTS[t] for t in l1_cfg.tests},
            "arms": l1_arms,
        }
        arms_used += list(l1)
        matrix = l1_matrix(l1_arms, l1_cfg.tests)
        summary["l1_matrix"] = matrix
        summary["headline"] = headline(matrix, l1_arms)
        summary["l1_violations_total"] = {
            arm: sum(sum(r["violations_total"].values()) for r in tests.values()) for arm, tests in l1.items()
        }
    if l4 is not None and l4_cfg is not None:
        layers["L4"] = {
            "title": "Performance and scale",
            **l4,
            "notes": [
                "Workers are Python threads in one process; run inside the compose network (docker compose --profile bench run crucible).",
                "claim = claim_next_task, heartbeat, complete are timed separately; each cycle is claim -> heartbeat -> complete.",
                "B2's claims are B1's SQLite claims (hybrid), so only its recall is measured separately.",
                "P-mcp adds a Step and a ToolCall write to every call, as the MCP server does.",
                "B0/B1/B2 are embedded libraries running inside the crucible container (they have no server); the Knewat arms talk to the FalkorDB container over the compose network. B1/B2 use SQLite's built-in busy handler, which has no fairness queue, so tail latency under write contention is large; cross-process writers cannot be queued in-process.",
                "recall includes embedding the query with the local bge-small model (one model instance per process, calls serialised by its lock) for B2, P and P-mcp.",
            ],
        }
        arms_used += [a for a in l4_cfg.arms if a not in arms_used]
    if ablation is not None:
        layers["ablation"] = {"title": "Ablation (D-001): relationships removed", **ablation}
        if "P" not in arms_used:
            arms_used.append("P")
    cfg: dict[str, Any] = {"arms": arms_used}
    if l1_cfg is not None:
        cfg["seeds"] = l1_cfg.seeds
        cfg["l1"] = l1_cfg.to_json()
    if l4_cfg is not None:
        cfg["l4"] = l4_cfg.to_json()
    ordered = [a for a in ("B0", "B1", "B2", "P", "P-mcp") if a in arms_used]
    return {
        "schema_version": SCHEMA_VERSION,
        "kind": "crucible-results",
        "run": {
            "id": run_id,
            "started_at": iso_utc(started),
            "finished_at": iso_utc(finished),
            "duration_s": round(finished - started, 1),
            "quick": quick,
            "command": command,
            "layers": [k for k in ("L1", "L4", "ablation") if k in layers],
        },
        "environment": environment.collect(host, port, embedder),
        "config": cfg,
        "arms": arms_section(ordered),
        "layers": layers,
        "summary": summary,
        "honesty": HONESTY,
    }


def write(results: dict[str, Any], out_root: Path, run_id: str) -> Path:
    """Write ``<out_root>/<run_id>/results.json`` + ``report.md``; refresh ``<out_root>/latest.json``."""
    from knewat.crucible.report import render

    d = out_root / run_id
    d.mkdir(parents=True, exist_ok=True)
    (d / "results.json").write_text(
        json.dumps(results, indent=2, sort_keys=False) + "\n", encoding="utf-8", newline="\n"
    )
    (d / "report.md").write_text(render(results), encoding="utf-8", newline="\n")
    shutil.copyfile(d / "results.json", out_root / "latest.json")
    return d
