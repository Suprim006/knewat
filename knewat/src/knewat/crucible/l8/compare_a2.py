"""L8 Round A2 (P12): the post-fix P runs next to Round A's P, B1 and B0' runs, from the per-run ``metrics.json``.

``python -m plexus.crucible.l8.compare_a2`` writes ``demo_data/crucible/l8_postfix/compare_a2.{json,md}``.
Pooled rates and the separation tests come from the unchanged Round A scorer (``score.pool``); the extra rows
(history recall, contradictions, provenance, recovery, failed tasks) are summed from the same metrics files the
Round A report used. Run ``python -m plexus.crucible.l8.report --out demo_data/crucible/l8_postfix`` first (it
re-scores every run and writes the ``metrics.json`` files).
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from plexus.crucible.l8.score import pool

ROOT = Path(__file__).resolve().parents[4] / "demo_data" / "crucible"
ROUND_A = ROOT / "l8"
POSTFIX = ROOT / "l8_postfix"
SEEDS = (20261017, 20261018, 20261019, 20261020, 20261021)
COLUMNS = (("P2", POSTFIX, "P"), ("P", ROUND_A, "P"), ("B1", POSTFIX, "B1"), ("B0p", POSTFIX, "B0p"))


def load(base: Path, arm: str) -> list[dict[str, Any]]:
    out = []
    for s in SEEDS:
        p = base / "runs" / str(s) / arm / "metrics.json"
        if p.exists():
            out.append(json.loads(p.read_text(encoding="utf-8")))
    return out


def failed_tasks(base: Path, arm: str) -> list[list[dict[str, str]]]:
    """Per seed: the ``fail_task`` calls the agents made, ``{task, reason}`` (P only; the baselines have none)."""
    out = []
    for s in SEEDS:
        tdir = base / "runs" / str(s) / arm / "transcripts"
        if not tdir.exists():
            continue
        calls = []
        for f in sorted(tdir.glob("*.jsonl")):
            for line in f.read_text(encoding="utf-8").splitlines():
                if "mcp__plexus__fail_task" not in line:
                    continue
                ev = json.loads(line)
                for b in (ev.get("message") or {}).get("content") or []:
                    if isinstance(b, dict) and b.get("name") == "mcp__plexus__fail_task":
                        calls.append(
                            {"task": b["input"].get("task_id", ""), "reason": b["input"].get("reason", "")}
                        )
        out.append(calls)
    return out


def extras(ms: list[dict[str, Any]]) -> dict[str, Any]:
    hist = [v for m in ms for t in m["history_recall"].values() for v in t.values()]
    x1 = [m["contradictions"]["X1"].get("surfaced_at_write") for m in ms]
    x2 = [m["contradictions"]["X2"].get("surfaced_at_write") for m in ms]
    prov = [m["provenance"] for m in ms if isinstance((m.get("provenance") or {}).get("overall"), dict)]
    rec = [r for m in ms for r in (m.get("recovery") or []) if isinstance(r, dict)]
    return {
        "history_recall": f"{sum(bool(v) for v in hist)}/{len(hist)}",
        "x1_at_write": f"{sum(bool(v) for v in x1)}/{len(x1)}",
        "x2_at_write": f"{sum(bool(v) for v in x2)}/{len(x2)}",
        "provenance_all": (
            f"{sum(p['overall']['with_record'] for p in prov)}/{sum(p['overall']['acknowledged'] for p in prov)}"
            if prov
            else "n/a"
        ),
        "provenance_kill_turns": (
            f"{sum(p['kill_turns']['with_record'] for p in prov)}/{sum(p['kill_turns']['acknowledged'] for p in prov)}"
            if prov
            else "n/a"
        ),
        "kills_recovered": f"{sum(bool(r.get('recovered')) for r in rec)}/{len(rec)}",
        "units_repeated": f"{sum(r.get('repeated_units', 0) for r in rec)} of {sum(r.get('finished_units', 0) for r in rec)}",
        "tasks_done": [m["tasks_done"] for m in ms],
        "turns": [m["turns"] for m in ms],
        "cost_usd": round(sum(m["tokens"]["cost_usd"] for m in ms), 4),
    }


def main() -> int:
    cols: dict[str, dict[str, Any]] = {}
    for key, base, arm in COLUMNS:
        ms = load(base, arm)
        if not ms:
            continue
        pooled = pool([{**m, "arm": "P" if key in ("P2", "P") else arm} for m in ms])["arms"]
        cols[key] = {"seeds": [m["seed"] for m in ms], "pooled": next(iter(pooled.values())), **extras(ms)}
        cols[key]["fail_task_calls"] = failed_tasks(base, arm) if arm == "P" else "n/a"
    # separation tests of the post-fix P against the unchanged baselines (the Round A scorer's own test)
    both = load(POSTFIX, "P") + load(POSTFIX, "B1") + load(POSTFIX, "B0p")
    tests = pool(both)["tests"] if load(POSTFIX, "P") else {}
    doc = {"kind": "crucible-l8-roundA2-compare", "columns": cols, "tests_P2_vs_baselines": tests}
    (POSTFIX / "compare_a2.json").write_text(json.dumps(doc, indent=1, default=str) + "\n", encoding="utf-8")
    print(json.dumps({k: {kk: v[kk] for kk in v if kk != "pooled"} for k, v in cols.items()}, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
