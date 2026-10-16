"""Throughput of the L4 ``P-mcp`` recall row under audit modes ``full`` / ``light`` / ``off`` (P9-e note).

Reuses the Crucible harness unchanged (``plexus.crucible.l4.recall_sweep`` on the ``P-mcp`` arm: every call goes
through ``Runtime._run``) and only changes the audit mode ``recall`` runs in, by wrapping ``Runtime._run``:

* ``full``  - today (Step + READ edges + Recall record + ToolCall: 3 write statements per recall)
* ``light`` - what ``recall(audit="light")`` does (one ToolCall: 1 write statement)
* ``off``   - what a ``demo*`` tenant does (nothing written)

Seeding (``assert_fact``) always stays ``full``. Scripted, no LLM. One FalkorDB, one machine.

    cd plexus && PLEXUS_EMBEDDER=fastembed uv run python ../deploy/bench_audit_modes.py --port 6365 --runs 3
"""

from __future__ import annotations

import argparse
import dataclasses
import json
import statistics
import sys
import tempfile
import time

from plexus.crucible.config import L4Config
from plexus.crucible.harness import Env
from plexus.crucible.l4 import recall_sweep
from plexus.mcp.runtime import Runtime

MODES = ("full", "light", "off")


def run_mode(env: Env, mode: str, cfg: L4Config) -> list[dict]:
    original = Runtime._run

    def forced(self, tenant, tool, agent_id, step, fn, started, audit_mode="full"):
        return original(self, tenant, tool, agent_id, step, fn, started, mode if tool == "recall" else audit_mode)

    Runtime._run = forced  # type: ignore[method-assign]
    try:
        return recall_sweep(env, "P-mcp", cfg)
    finally:
        Runtime._run = original  # type: ignore[method-assign]


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, required=True)
    ap.add_argument("--embedder", default="fastembed", choices=("fastembed", "hash"))
    ap.add_argument("--runs", type=int, default=3)
    ap.add_argument("--workers", type=int, nargs="+", default=[1, 10, 50])
    ap.add_argument("--json", help="write the raw points here")
    a = ap.parse_args(argv)

    cfg = dataclasses.replace(L4Config(), workers=tuple(a.workers), recall_arms=("P-mcp",))
    env = Env(root=tempfile.mkdtemp(prefix="bench-audit-"), host=a.host, port=a.port, embedder=a.embedder)
    raw: list[dict] = []
    t0 = time.perf_counter()
    for run in range(a.runs):
        for mode in MODES if run % 2 == 0 else reversed(MODES):  # alternate the order: no mode always goes first
            for p in run_mode(env, mode, cfg):
                raw.append({"mode": mode, "run": run, **p})
                print(
                    f"run {run} {mode:5} w={p['workers']:3}  {p['throughput_ops_s']:7.1f}/s  errors={p['error_count']}",
                    flush=True,
                )

    print(
        f"\nP-mcp recall, {cfg.recall_facts} facts, {a.embedder} embedder, median of {a.runs} runs "
        f"({time.perf_counter() - t0:.0f} s total)"
    )
    print("| workers | " + " | ".join(f"{m} ops/s (p50 / p99 ms)" for m in MODES) + " | light/full | off/full |")
    print("|---|" + "---|" * (len(MODES) + 2))
    for w in cfg.workers:
        cells: dict[str, tuple[float, float, float]] = {}
        for m in MODES:
            pts = [p for p in raw if p["mode"] == m and p["workers"] == w]
            cells[m] = (
                statistics.median(p["throughput_ops_s"] for p in pts),
                statistics.median(p["recall"]["p50_ms"] for p in pts),
                statistics.median(p["recall"]["p99_ms"] for p in pts),
            )
        row = " | ".join(f"{cells[m][0]:.1f} ({cells[m][1]:.0f} / {cells[m][2]:.0f})" for m in MODES)
        print(
            f"| {w} | {row} | {cells['light'][0] / cells['full'][0]:.2f}x | {cells['off'][0] / cells['full'][0]:.2f}x |"
        )
    if a.json:
        with open(a.json, "w", encoding="utf-8") as f:
            json.dump(raw, f)
    return 0 if all(p["error_count"] == 0 for p in raw) else 1


if __name__ == "__main__":
    sys.exit(main())
