"""The L6 LLM pilot: 8 questions per family (A, B, D) for B1a, B0g and B0r, within a hard $20 cap.

    python -m plexus.crucible.l6.pilot run --stage measure     # 2 calls per arm on family B: measures cost per call
    python -m plexus.crucible.l6.pilot run --stage rest        # the remaining calls (gate: projected total <= $16)

Pre-registered in BASELINE.md ("L6 pre-registration", "LLM pilot budget"); ids, caps and the gate are the ones written
there. Every call is cached in ``demo_data/crucible/l6_cache``; a re-run costs nothing for cached calls.
"""

from __future__ import annotations

import argparse
import json
import random
import shutil
import statistics
import sys
import tempfile
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any

from plexus.crucible import environment
from plexus.crucible.l2.llm import BudgetExceeded
from plexus.crucible.l2.run import reply_format
from plexus.crucible.l2.scale_contexts import Bm25
from plexus.crucible.l6 import llm as L
from plexus.crucible.l6 import run as R
from plexus.crucible.l6 import score as SC
from plexus.crucible.l6 import stores as S
from plexus.crucible.l6 import world as W
from plexus.crucible.util import iso_utc, run_stamp

DEMO = R.DEMO
CACHE = R.DEMO.parent / "l6_cache"
PILOT_IDS = {
    "A": [0, 3, 5, 6, 9, 10, 12, 15],
    "B": [0, 4, 8, 9, 12, 13, 16, 20],
    "D": [0, 4, 8, 12, 16, 20, 1, 9],
}
ARMS = ("B0r", "B1a", "B0g", "P")
ARM_CAPS = {"B0r": 3.0, "B1a": 7.0, "B0g": 8.0, "P": 6.0}  # P: 2.0 until amendment 5
P_FAMILIES = ("A", "B")  # no product tool exists for D (P8 is not built): P-mcp is not asked D
TOTAL_CAP = 20.0
GATE_USD = 16.0
CONTEXT_CHARS = 32_000


class Prep:
    """One family's world, its SQLite file (B1a), its files directory (B0g) and its BM25 index over the file lines (B0r)."""

    def __init__(self, family: str, tmp: Path, scale: float = 1.0):
        self.family = family
        if family == "A":
            self.world, self.qs = W.gen_a(scale)
        elif family == "B":
            self.world, self.qs = W.gen_b(scale)
        else:
            self.world, self.qs = W.gen_d(scale)
        self.db, _ = S.build_sqlite(self.world, tmp / family, f"pilot_{family.lower()}")
        self.files = tmp / f"files_{family}"
        S.write_files(self.world, self.files)
        self.chunks = S.file_text_chunks(self.files)
        self.data_sha = self._hash()
        self._bm25: Bm25 | None = None
        self.tenant = f"l6p_{family.lower()}"

    def _hash(self) -> str:
        import hashlib

        h = hashlib.sha256()
        for p in sorted(self.files.rglob("*")):
            if p.is_file():
                h.update(p.relative_to(self.files).as_posix().encode())
                h.update(p.read_bytes())
        return h.hexdigest()

    def bm25(self) -> Bm25:
        if self._bm25 is None:
            self._bm25 = Bm25([f"{Path(f).stem} {t}" for f, t in self.chunks])
        return self._bm25

    def context(self, q: Any) -> str:
        """Best lines by BM25 over the question text, at most 32,000 characters, shown grouped by file in file order."""
        order = self.bm25().ranked(q.text())
        preface = "Excerpts of the memory files (the lines most relevant to the question by keyword):\n"
        picked: list[int] = []
        files: set[str] = set()
        used = len(preface)
        for i in order:
            f, t = self.chunks[i]
            cost = (
                len(t) + 1 + (0 if f in files else len(f) + 12)
            )  # the line, its newline and (once per file) its header
            if used + cost > CONTEXT_CHARS - 300:  # 300 chars of slack for the separators added when joining
                if CONTEXT_CHARS - 300 - used < 40:
                    break
                continue
            picked.append(i)
            files.add(f)
            used += cost
        picked.sort()
        out = ["Excerpts of the memory files (the lines most relevant to the question by keyword):\n"]
        cur = ""
        for i in picked:
            f, t = self.chunks[i]
            if f != cur:
                out.append(f"\n=== {f} ===")
                cur = f
            out.append(t)
        return "\n".join(out)

    def prompt(self, q: Any) -> str:
        notes = (L.CONVENTIONS_D + "\n") if self.family == "D" else ""
        return notes + L.question_prompt(q.id, q.text(), q.fmt())

    def template(self, q: Any) -> str:
        return getattr(q, "template", "")


def tasks_for(preps: dict[str, Prep], ids: dict[str, list[int]], arm: str) -> list[tuple[str, Any]]:
    out = []
    for fam in ("A", "B", "D"):
        if arm == "P" and fam not in P_FAMILIES:
            continue
        qs = preps[fam].qs
        for i in ids[fam]:
            out.append((fam, qs[i]))
    return out


def call_one(runner: L.PilotRunner, prep: Prep, arm: str, q: Any) -> L.Call:
    return runner.ask(
        arm, prep.family, q.id, prep.prompt(q), data_sha=prep.data_sha,
        context=prep.context(q) if arm == "B0r" else "", db=prep.db if arm == "B1a" else "", files_dir=prep.files if arm == "B0g" else None, tenant=prep.tenant if arm == "P" else "",
    )  # fmt: skip


def row(prep: Prep, q: Any, call: L.Call) -> dict[str, Any]:
    if call.error and not call.error.startswith(("max_turns", "budget")):
        strict, comp = False, {}
    elif call.parse_error or call.answer is None:
        strict, comp = False, {}
    else:
        strict, comp = SC.score(prep.family, q.answer, call.answer, prep.template(q))
    return {
        "id": q.id, "strict": strict, "components": comp, "error": call.error, "parse_error": call.parse_error,
        "tokens": call.total_tokens, "usage": call.usage, "cost_usd": round(call.cost_usd, 6), "latency_ms": call.latency_ms,
        "num_turns": call.num_turns, "tool_calls": len(call.tools_used), "tools": sorted(set(call.tools_used)), "cached": call.cached,
        "context_chars": call.context_chars, "reply_format": reply_format(call.reply, bool(call.error)) if call.reply else "no_reply",
        "expected": q.answer if not strict else None, "got": json.dumps(call.answer, default=str)[:300] if not strict else None,
        "reply": call.reply[:500], "model": call.model,
    }  # fmt: skip


def summarise(rows: list[dict[str, Any]], completed: bool) -> dict[str, Any]:
    n = len(rows)
    return {
        "n": n, "strict_correct": sum(r["strict"] for r in rows), "completed": completed,
        "strict_whole_reply_json": sum(r["strict"] and r["reply_format"] == "json_only" for r in rows),
        "errors": sum(bool(r["error"]) for r in rows),
        "tokens_per_question": round(sum(r["tokens"] for r in rows) / n, 1) if n else 0,
        "cost_usd": round(sum(r["cost_usd"] for r in rows), 4), "cost_per_question_usd": round(sum(r["cost_usd"] for r in rows) / n, 4) if n else 0,
        "tool_calls_per_question": round(sum(r["tool_calls"] for r in rows) / n, 2) if n else 0,
        "latency_s_median": round(statistics.median([r["latency_ms"] for r in rows]) / 1000, 1) if rows else 0,
        "components_correct": {k: sum(int(r["components"].get(k, False)) for r in rows) for k in {c for r in rows for c in r["components"]}},
        "questions": rows,
    }  # fmt: skip


def run_pilot(
    stage: str,
    out: Path,
    scale: float,
    launcher: list[str] | None,
    log: Any = print,
    cache: Path | None = None,
    graphs: bool = True,
    host: str = "127.0.0.1",
    port: int = 6361,
) -> dict[str, Any]:
    started = time.time()
    tmp = Path(tempfile.mkdtemp(prefix="crucible-l6-pilot-"))
    preps = {f: Prep(f, tmp, scale) for f in ("A", "B", "D")}
    for f, p in preps.items():
        log(
            f"pilot: family {f}: {len(p.qs)} questions, {len(p.chunks)} file lines, data sha {p.data_sha[:12]}"
        )
    runner = L.PilotRunner(
        cache or CACHE, total_cap=TOTAL_CAP, arm_caps=ARM_CAPS, launcher=launcher, db_host=host, db_port=port
    )
    client = None
    if graphs:  # the P arm reads the real graph: one tenant per family, dropped at the end
        from plexus.graph.client import GraphClient
        from plexus.graph.tenancy import graph_name

        client = GraphClient(host=host, port=port)
        for f in P_FAMILIES:
            S.load_plexus(preps[f].world, client, preps[f].tenant)
            log(f"pilot: loaded graph for family {f} (tenant {preps[f].tenant})")

    def cleanup() -> None:
        shutil.rmtree(tmp, ignore_errors=True)
        if client is not None:
            for f in P_FAMILIES:
                client.delete_graph(graph_name(preps[f].tenant))

    ids = {f: list(v) for f, v in PILOT_IDS.items()}
    if scale < 1:  # toy run: keep the ids that exist
        ids = {f: [i for i in v if i < len(preps[f].qs)][:8] for f, v in ids.items()}
    measured: dict[str, list[float]] = {a: [] for a in ARMS}
    measure_ids = [ids["B"][0], ids["B"][4]]
    rows: dict[tuple[str, str], list[dict[str, Any]]] = {}
    completed: dict[str, bool] = dict.fromkeys(ARMS, True)
    lock = threading.Lock()

    def do(arm: str, items: list[tuple[str, Any]]) -> None:
        for fam, q in items:
            try:
                call = call_one(runner, preps[fam], arm, q)
            except BudgetExceeded as exc:
                log(f"  {arm}: stopped at {q.id}: {exc}")
                with lock:
                    completed[arm] = False
                return
            r = row(preps[fam], q, call)
            with lock:
                rows.setdefault((fam, arm), []).append(r)
                if (fam, q.id) and fam == "B" and q in [preps["B"].qs[i] for i in measure_ids]:
                    measured[arm].append(call.cost_usd)
            log(
                f"  {arm} {q.id} {'ok ' if r['strict'] else 'BAD'} {r['tokens']:>7} tok ${r['cost_usd']:.3f} {r['latency_ms'] / 1000:.0f}s tools={r['tool_calls']}{' (cached)' if r['cached'] else ''}{' ' + r['error'][:40] if r['error'] else ''}"
            )

    if stage in ("measure", "all"):
        with ThreadPoolExecutor(4) as ex:
            list(ex.map(lambda a: do(a, [("B", preps["B"].qs[i]) for i in measure_ids]), ARMS))
        mean = {a: statistics.mean(v) if v else 0.0 for a, v in measured.items()}
        calls_per_arm = {a: sum(len(ids[f]) for f in ids if a != "P" or f in P_FAMILIES) for a in ARMS}
        projected = sum(m * calls_per_arm[a] for a, m in mean.items())
        log(
            f"measured mean cost per call {mean}; projected total for {calls_per_arm} calls per arm: ${projected:.2f} (gate ${GATE_USD})"
        )
        if stage == "measure" or projected > GATE_USD:
            log("stopping after the measurement stage" + (" (gate exceeded)" if projected > GATE_USD else ""))
            cleanup()
            return _doc(
                rows, ids, preps, runner, started, completed, out, stage, projected, mean, partial=True
            )
    if stage in ("rest", "all"):
        with ThreadPoolExecutor(4) as ex:
            list(ex.map(lambda a: do(a, tasks_for(preps, ids, a)), ARMS))
    doc = _doc(
        rows, ids, preps, runner, started, completed, out, stage, None, None, partial=stage == "measure"
    )
    cleanup()
    return doc


def _doc(
    rows, ids, preps, runner, started, completed, out, stage, projected, mean, partial
) -> dict[str, Any]:  # type: ignore[no-untyped-def]
    fams: dict[str, Any] = {}
    for fam in ("A", "B", "D"):
        arms = {}
        for arm in ARMS:
            rs = sorted({r["id"]: r for r in rows.get((fam, arm), [])}.values(), key=lambda r: r["id"])
            if rs:
                arms[arm] = summarise(rs, completed[arm])
        fams[fam] = {
            "pilot_ids": [preps[fam].qs[i].id for i in ids[fam]],
            "n_questions": len(ids[fam]),
            "arms": arms,
        }
    all_rows = [r for v in rows.values() for r in v]
    doc = {
        "schema": "crucible-l6/1", "kind": "pilot",
        "run": {"id": run_stamp() + "-pilot", "started_at": iso_utc(started), "finished_at": iso_utc(), "stage": stage, "llm_calls": len(all_rows), "calls_run_live": runner.live_calls, "cost_usd": round(sum(r["cost_usd"] for r in all_rows), 4), "cost_live_usd": round(runner.spent - runner.spent_before, 4), "cost_cumulative_usd": round(runner.spent, 4)},  # noqa: E501
        "git": R.git_state(), "environment": environment.collect("127.0.0.1", 0, "none") | {"claude": "claude -p, model sonnet"},
        "prompt_version": L.PROMPT_VERSION, "model": runner.model,
        "budget": {"total_cap_usd": TOTAL_CAP, "arm_caps_usd": ARM_CAPS, "per_call_cap_usd": L.PER_CALL_CAP_USD, "gate_usd": GATE_USD, "projected_usd": projected, "measured_mean_cost": mean, "arm_spent_cumulative_usd": {k: round(v, 4) for k, v in runner.arm_spent.items()}},  # noqa: E501
        "partial": partial, "families": fams,
        "scoring": "reply may start with prose and must END with one {\"answer\": ...} object; strict = every component exact; whole-reply-JSON variant reported",
        "cache": "demo_data/crucible/l6_cache",
    }  # fmt: skip
    d = out / doc["run"]["id"]
    d.mkdir(parents=True, exist_ok=True)
    (d / "results.json").write_text(
        json.dumps(doc, indent=1, default=str) + "\n", encoding="utf-8", newline="\n"
    )
    shutil.copyfile(d / "results.json", out / f"latest-pilot{'-measure' if partial else ''}.json")
    return doc


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="crucible-l6-pilot")
    sub = ap.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("run")
    r.add_argument("--stage", choices=("measure", "rest", "all"), required=True)
    r.add_argument("--out", type=Path, default=DEMO)
    r.add_argument("--scale", type=float, default=1.0)
    a = ap.parse_args(argv)
    rng = random.Random(0)
    _ = rng
    doc = run_pilot(a.stage, a.out, a.scale, None, lambda s: print(s, flush=True))
    print(json.dumps({k: doc[k] for k in ("run", "budget")}, indent=1, default=str))
    return 0


if __name__ == "__main__":
    sys.exit(main())
