"""Run arm B1h (hand-written SQL) on the L2 and L2-scale question sets and score it against the committed ground truth.

    python -m knewat.crucible.l2.sql_run run                # -> demo_data/crucible/b1h/<stamp>/{results.json,report.md}
    python -m knewat.crucible.l2.sql_run run --which l2     # only the 43-question set

No LLM call, no FalkorDB: the script of each set is replayed onto a throw-away :class:`SqliteHistoryBackend` (the ledger
must equal the reference ledger the committed questions were generated from), the questions are loaded from the committed
``questions.yaml`` / ``questions_scale.yaml`` (their answers were derived from the script ledger, never typed), and every
question is answered by :class:`~knewat.crucible.l2.sql_answerer.SqlAnswerer`. The scale set asks the same 36 questions as
the paid L2-scale run (``FULL_DROPPED_IDS`` are dropped, as pre-registered in BASELINE amendment 1).
"""

from __future__ import annotations

import argparse
import json
import shutil
import statistics
import sys
import tempfile
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

from knewat.crucible.backends.sqlite_h import SqliteHistoryBackend
from knewat.crucible.l2 import run as L2R
from knewat.crucible.l2 import scale_run as SR
from knewat.crucible.l2.questions import FAMILIES, Question, load_questions, score
from knewat.crucible.l2.scale_questions import load_scale_questions
from knewat.crucible.l2.scale_scenario import play_scale
from knewat.crucible.l2.scenario import play
from knewat.crucible.l2.sql_answerer import ScaleSqlAnswerer, SqlAnswerer
from knewat.crucible.util import iso_utc, percentile, run_stamp

DEMO_DATA = L2R.DEMO_DATA
OUT_DIR = DEMO_DATA / "b1h"
ANSWERER = (
    "hand-written SQL against the tenant's SQLite store (B1 tables + a claims history table), "
    "one read-only statement per fact needed (no LLM)"
)
ARM = "B1h"


def _rows(qs: list[Question], ans: SqlAnswerer, mk: Callable[..., dict[str, Any]]) -> list[dict[str, Any]]:
    rows = []
    for q in qs:
        try:
            got, meta = ans.answer(q)
            ok, why = score(q, got)
        except Exception as exc:  # noqa: BLE001 - reported per question, never hidden
            got, meta, ok, why = None, L2R.empty_meta(), False, f"{type(exc).__name__}: {exc}"[:200]
        rows.append(
            mk(q, ok, got, why, tokens=0, cost_usd=0.0, latency_ms=meta["latency_ms"], server_ms=0.0,
               statements=meta["statements"], cached=False, context_chars=0, truncated=False)
        )  # fmt: skip
    return rows


def _finish(arm_dict: dict[str, Any]) -> dict[str, Any]:
    arm_dict["answerer"] = ANSWERER
    arm_dict["usage"].pop("server_ms", None)
    lat = [r["latency_ms"] for r in arm_dict["questions"]]
    arm_dict["usage"]["latency_ms"]["p99"] = round(percentile(lat, 99), 2) if lat else 0
    return arm_dict


def run_l2(work: Path, qpath: Path = L2R.QUESTIONS_PATH) -> dict[str, Any]:
    all_qs = load_questions(qpath)
    ref, _ = L2R.check_questions(all_qs, work / "ref")
    b = SqliteHistoryBackend("l2_b1h", work / "arm")
    try:
        led = play(b)
        if L2R.strip_ids(led) != L2R.strip_ids(ref):
            raise SystemExit("B1h did not reproduce the reference story")
        ans = SqlAnswerer(b.path)
        try:
            rows = _rows(all_qs, ans, L2R._row)
        finally:
            ans.close()
    finally:
        b.close()
    arm = _finish(L2R.arm_summary("P", rows, True, None))
    return {"arm": arm, "questions": all_qs, "n": len(all_qs)}


def run_scale(work: Path, k: int = SR.K_SPRINTS, qpath: Path = SR.QUESTIONS_PATH) -> dict[str, Any]:
    all_qs = load_scale_questions(qpath)
    ref, _ = SR.check_scale_questions(all_qs, work / "ref", k)
    qs = [q for q in all_qs if q.id not in SR.FULL_DROPPED_IDS]
    b = SqliteHistoryBackend("l2s_b1h", work / "arm")
    try:
        sl = play_scale(b, k)
        if SR.strip_scale(sl) != SR.strip_scale(ref):
            raise SystemExit("B1h did not reproduce the reference story")
        ans = ScaleSqlAnswerer(b.path)
        try:
            rows = _rows(qs, ans, lambda q, ok, got, why, **x: SR._row(q, ok, got, why, k, **x))
        finally:
            ans.close()
    finally:
        b.close()
    out = SR.arm_summary_scale("P", rows, True, None)
    out["usage"].pop("server_ms", None)
    return {"arm": _finish(out), "questions": qs, "n": len(qs)}


def compare(rows_b1h: list[dict[str, Any]], p_rows: list[dict[str, Any]] | None) -> dict[str, Any] | None:
    """Per-question agreement with the committed Knewat (P) rows of the same run (a paired view, no new P run)."""
    if p_rows is None:
        return None
    p = {r["id"]: r["correct"] for r in p_rows}
    ids = [r["id"] for r in rows_b1h if r["id"] in p]
    return {
        "both_correct": sum(1 for r in rows_b1h if r["id"] in p and r["correct"] and p[r["id"]]),
        "b1h_only": sum(1 for r in rows_b1h if r["id"] in p and r["correct"] and not p[r["id"]]),
        "p_only": sum(1 for r in rows_b1h if r["id"] in p and not r["correct"] and p[r["id"]]),
        "both_wrong": sum(1 for r in rows_b1h if r["id"] in p and not r["correct"] and not p[r["id"]]),
        "n": len(ids),
    }


def _committed(path: Path, layer: str) -> dict[str, Any] | None:
    return json.loads(path.read_text(encoding="utf-8"))["layers"][layer] if path.is_file() else None


def code_size() -> dict[str, Any]:
    """Author effort: non-blank, non-comment lines of the Cypher answerer + its statements vs the SQL answerer."""
    here = Path(__file__).resolve().parent

    def loc(path: Path) -> int:
        n = 0
        for ln in path.read_text(encoding="utf-8").splitlines():
            s = ln.strip()
            if s and not s.startswith(("#", "//", '"""')):
                n += 1
        return n

    cypher = sum(loc(p) for p in (here / "queries" / "l2").glob("*.cypher"))
    return {
        "cypher_answerer_lines": loc(here / "knewat_answerer.py"),
        "cypher_statement_lines": cypher,
        "sql_answerer_lines": loc(here / "sql_answerer.py"),
        "note": "non-blank non-comment lines; the SQL answerer also holds the scale variant (about a quarter of it), "
        "the Cypher one keeps that in scale_knewat.py (not counted)",
    }


def build(which: str = "both") -> dict[str, Any]:
    started = time.time()
    work = Path(tempfile.mkdtemp(prefix="crucible-b1h-"))
    try:
        layers: dict[str, Any] = {}
        l2 = run_l2(work / "l2") if which in ("both", "l2") else None
        sc = run_scale(work / "scale") if which in ("both", "scale") else None
        committed_l2 = _committed(L2R.OUT_DIR / "latest-full.json", "L2")
        committed_sc = _committed(SR.OUT_DIR / "latest-full.json", "L2_scale")
        if l2:
            layers["L2"] = {
                "arm": l2["arm"],
                "question_set": {"total": l2["n"], "asked": l2["n"]},
                "paired_with_P": compare(
                    l2["arm"]["questions"], committed_l2["arms"]["P"]["questions"] if committed_l2 else None
                ),
            }
        if sc:
            layers["L2_scale"] = {
                "arm": sc["arm"],
                "question_set": {"total": 40, "asked": sc["n"], "dropped": list(SR.FULL_DROPPED_IDS)},
                "paired_with_P": compare(
                    sc["arm"]["questions"], committed_sc["arms"]["P"]["questions"] if committed_sc else None
                ),
            }
        finished = time.time()
        return {
            "kind": "crucible-b1h",
            "schema": "crucible-b1h/1",
            "run": {
                "id": run_stamp() + "-b1h",
                "started_at": iso_utc(started),
                "finished_at": iso_utc(finished),
                "llm_calls": 0,
                "cost_usd": 0.0,
            },  # fmt: skip
            "arm": ARM,
            "answerer": ANSWERER,
            "code_size": code_size(),
            "layers": layers,
            "honesty": [
                "B1h is the existing B1 SQLite store with one added table (claims, written in the claim's own transaction) "
                "because B1 never kept the claim history that the Recovery questions need and Knewat keeps as CLAIMED edges. "
                "No other schema or index change.",
                "The 17 SQL operations were written by the same author as the Cypher ones, with knowledge of the question "
                "set and the scenario: that is the point of a control (same effort, same spec), but it is not a blind SQL "
                "arm. Ground truth is the committed question files (derived from the script ledger), the ledger of the B1h "
                "replay equals the reference ledger.",
                "A tie on correctness here says the L2/L2-scale gap between Knewat and the B1/B0 readers is reader-vs-query, "
                "not graph-vs-SQL. B1h is in-process SQLite (no network hop), Knewat crosses a container network: "
                "latency columns are not a like-for-like speed comparison.",
            ],
        }
    finally:
        shutil.rmtree(work, ignore_errors=True)


def render_report(doc: dict[str, Any]) -> str:
    w = [f"# Crucible B1h: hand-written SQL on L2 and L2-scale ({doc['run']['id']})\n"]
    for name, title in (("L2", "L2 (43 questions)"), ("L2_scale", "L2-scale (36 questions)")):
        layer = doc["layers"].get(name)
        if not layer:
            continue
        a = layer["arm"]
        acc = a["accuracy"]
        w.append(f"## {title}\n")
        w.append(f"B1h: **{acc['correct']}/{acc['total']} ({acc['pct']}%)**; median {a['usage']['latency_ms']['median']} ms, "
                 f"p95 {a['usage']['latency_ms']['p95']} ms per question; {a['usage']['llm_calls']} LLM calls.\n")  # fmt: skip
        w.append("| Family | correct |\n|---|---|")
        for f, v in a["by_family"].items():
            w.append(f"| {FAMILIES[f]} | {v['correct']}/{v['total']} |")
        wrong = [r for r in a["questions"] if not r["correct"]]
        w.append(
            "\nWrong: " + (", ".join(f"{r['id']} ({r['error'] or 'wrong answer'})" for r in wrong) or "none")
        )
        if layer.get("paired_with_P"):
            w.append(f"\nPaired with the committed P rows: {json.dumps(layer['paired_with_P'])}")
        w.append("")
    w.append("## Honesty\n")
    w += [f"- {h}" for h in doc["honesty"]]
    return "\n".join(w) + "\n"


def write_outputs(doc: dict[str, Any], out_root: Path = OUT_DIR) -> Path:
    d = out_root / doc["run"]["id"]
    d.mkdir(parents=True, exist_ok=True)
    (d / "results.json").write_text(json.dumps(doc, indent=2) + "\n", encoding="utf-8", newline="\n")
    (d / "report.md").write_text(render_report(doc), encoding="utf-8", newline="\n")
    shutil.copyfile(d / "results.json", out_root / "latest.json")
    return d


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="crucible-b1h")
    sub = ap.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("run", help="replay the scripts onto SQLite and answer with SQL")
    r.add_argument("--which", choices=("both", "l2", "scale"), default="both")
    r.add_argument("--out", type=Path, default=OUT_DIR)
    a = ap.parse_args(argv)
    doc = build(a.which)
    d = write_outputs(doc, a.out)
    for name, layer in doc["layers"].items():
        acc = layer["arm"]["accuracy"]
        print(f"{name}: B1h {acc['correct']}/{acc['total']}")
    print(f"results: {d / 'results.json'}")
    _ = statistics
    return 0


if __name__ == "__main__":
    sys.exit(main())
