"""Run L2 at scale: K sprints of history (>= 10x the 32k-character budget), 40 questions, arms P / B0 / B1 / B2.

    python -m plexus.crucible.l2.scale_run questions                       # regenerate demo_data/crucible/questions_scale.yaml
    python -m plexus.crucible.l2.scale_run run --mode pilot --port 6366    # 5 questions x B0,B1,B2 with claude -p, + P
    python -m plexus.crucible.l2.scale_run run --mode full  --port 6366    # all 40 (cached answers are free)

Same scoring rule, reply parser, model, runner and results envelope as ``run.py``; the numbers live in
``layers["L2_scale"]`` (shape: :func:`assemble_scale_layer`, documented in the README). Pre-registered in
``docs/BASELINE.md`` ("L2-scale (pre-registered)") before the first paid call.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import statistics
import sys
import tempfile
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

from plexus.crucible import environment
from plexus.crucible import results as H
from plexus.crucible.api import BackendSpec
from plexus.crucible.backends import open_backend
from plexus.crucible.l2 import contexts as C
from plexus.crucible.l2 import scale_contexts as SC
from plexus.crucible.l2.llm import USAGE_KEYS, BudgetExceeded, ClaudeRunner
from plexus.crucible.l2.questions import CONVENTIONS, FAMILIES, Question, parse_reply, score
from plexus.crucible.l2.run import ANSWERERS, DEMO_DATA, _pct, arm_summary, context_summary, reply_format
from plexus.crucible.l2.scale_plexus import ScalePlexusAnswerer
from plexus.crucible.l2.scale_questions import (
    CONVENTIONS_SCALE_EXTRA,
    SEED,
    build_scale_questions,
    dump_scale_questions,
    generate_scale,
    load_scale_questions,
    scale_summary,
)
from plexus.crucible.l2.scale_scenario import ScaleLedger, play_scale
from plexus.crucible.util import percentile

K_SPRINTS = 20
QUESTIONS_PATH = DEMO_DATA / "questions_scale.yaml"
CACHE_DIR = DEMO_DATA / "l2_scale_cache"
OUT_DIR = DEMO_DATA / "l2_scale"
BASELINES = ("B0", "B1", "B2")
ARMS = ("B0", "B1", "B2", "P")
PROMPT_VERSION = "l2-scale-v1"
# pre-registered pilot: five families, all three strata (early / middle / late), fixed before any paid call
PILOT_IDS = ("Q03", "Q14", "Q21", "Q25", "Q37")
_lines = CONVENTIONS.split("\n")
CONVENTIONS_SCALE = "\n".join([*_lines[:-1], CONVENTIONS_SCALE_EXTRA, _lines[-1]])

ANSWERERS_SCALE = {
    "B0": "claude -p over BM25-ranked chunks of the arm's files (tasks, MEMORY.md, decisions/handoffs jsonl, sources, logs), 32k chars",
    "B1": "claude -p over the full schema + BM25-ranked rows (with one-hop joined text) of the arm's SQLite tables as CSV, 32k chars",
    "B2": "claude -p over the top-12 retrieved memory chunks (local bge-small embeddings), cap 32k chars",
    "P": "deterministic Cypher against the tenant graph (no LLM), sprint-scoped where a question asks about a whole class",
}
PLEXUS_CHANGES = [
    "Operations whose arguments already name a unique thing (task id, fact label, decision name, subject, source uri) run the unchanged l2 operation with the unchanged statements: decision_facts, decision_fact_agents, decision_sources, handoff_artifacts, handoff_route, handoff_facts, as_of_values, as_of_facts, value_history, decisions_on_fact, superseder, fact_agent, fact_source, fact_scope, blocked_by_failure, direct_dependencies, ready_after, reclaimer, previous_claimer, current_value, scope_leak, episode_agent, remaining_from_source, forgotten_facts.",
    "Ten operations ask about a whole class (all handoffs to X, all decisions on superseded facts, ...) and are restricted to the sprint named in the question by a Python filter over the rows of the same statements (task ids start with the sprint tag, source uris contain it, episode texts start with it): handoffs_to, handoffs_with_superseded_facts, decisions_on_superseded, decisions_on_forgotten, active_conflicts, active_conflict_agents, reclaimed_tasks, completed_by, episode_count.",
    "One operation needs one new read-only statement: visible_facts runs queries/l2scale/facts_visible_subject.cypher (l2/facts_visible plus a subject restriction), because the global scope now holds the facts of all 20 sprints.",
    "No other query was changed; the original plexus_answerer.py and queries/l2/*.cypher are untouched.",
]
HONESTY = [
    "L2-scale: exact-match accuracy over 40 script-derived questions (10 families x 4) about 20 independent sprints of one team history; one scenario family, one model (sonnet), one run per question; no LLM judge. Ground truth is computed from the per-sprint scenario ledgers, not read back from any arm. Pre-registered in docs/BASELINE.md before the first paid call.",
    "The history is 20 repetitions of the same synthetic story with varied ids and values. Real histories are messier; sprints here do not interact, which favours retrieval (a question names its sprint and a sprint's records share its tag).",
    "Every question names exactly one sprint, so competent keyword retrieval can find a sprint's records. Questions that aggregate across sprints (the strongest case for a graph) are NOT in this set.",
    "Baselines are the same unmodified `claude -p --model sonnet` with no tools at the same 32,000-character cap, shown BM25-ranked chunks/rows (B0, B1) or vector top-12 (B2) selected with the question text. The selectors were written once, before any paid call, and not tuned afterwards.",
    "Arm P answers with hand-written Cypher per question family (the same operations as the 43-question L2 run, with the sprint scoping listed in the results); that engineering effort is part of what P costs and the baselines get no equivalent helper.",
    'Reply rule for the baselines is the final L2 rule: prose may precede the reply, which must END with one {"answer": ...} object; the whole-reply-JSON variant is reported next to it.',
    "B1 and B2 (and B0's task file) keep only a task's final claimer, not the claim history; only B0's per-agent logs and Plexus's CLAIMED edges record who held an expired lease. Recovery questions therefore test what each arm's artifacts actually contain, as configured in L1.",
]


# ------------------------------------------------------------------------------------------------ strata
def stratum_of(n: int, k: int) -> str:
    third = k // 3
    return "early" if n <= third else ("late" if n > k - third else "middle")


def strip_scale(sl: ScaleLedger) -> list[dict[str, Any]]:
    out = []
    for led in sl.ledgers:
        d = led.to_json()
        d.pop("arm")
        for key in ("facts", "decisions", "sources", "artifacts"):
            for row in d[key]:
                row.pop("id", None)
        out.append(d)
    return out


class ScalePrepared:
    def __init__(self, arm: str, tenant: str, backend: Any, ledger: ScaleLedger, path: Path | None):
        self.arm, self.tenant, self.backend, self.ledger, self.path = arm, tenant, backend, ledger, path


def prepare_scale_arm(
    arm: str, root: Path, host: str, port: int, embedder: str, tenant: str, k: int
) -> ScalePrepared:
    b = open_backend(
        BackendSpec(arm=arm, tenant=tenant, root=str(root), host=host, port=port, embedder=embedder)
    )
    sl = play_scale(b, k)
    path = getattr(b, "dir", None)
    return ScalePrepared(arm, tenant, b, sl, Path(path) if path else None)


def check_scale_questions(committed: list[Question], tmp: Path, k: int) -> tuple[ScaleLedger, list[Question]]:
    sl, fresh = generate_scale(tmp, k)
    if [q.to_json() for q in committed] != [q.to_json() for q in fresh]:
        raise SystemExit(
            "questions_scale.yaml differs from what the scenario generates: run `... scale_run questions`"
        )
    return sl, fresh


# ------------------------------------------------------------------------------------------------ evidence diagnostic
def evidence_in_context(q: Question, context_text: str) -> dict[str, int] | None:
    """How many expected answer items have ALL their words somewhere in the context (a diagnostic, never a score)."""
    if q.kind not in ("set", "ordered", "value"):
        return None
    items = q.answer if isinstance(q.answer, list) else [q.answer]
    have = set(SC.tokens(context_text))
    found = 0
    for it in items:
        need = set(SC.tokens(str(it).split("@")[0] if q.item == "fact_by" else str(it)))
        found += bool(need) and need <= have
    return {"found": found, "total": len(items)}


# ------------------------------------------------------------------------------------------------ answering
def _row(q: Question, ok: bool, got: Any, why: str, k: int, **extra: Any) -> dict[str, Any]:
    n = int(q.args["sprint"][1:])
    return {
        "id": q.id, "family": q.family, "sprint": q.args["sprint"].upper(), "stratum": stratum_of(n, k),
        "correct": ok, "expected": q.answer, "got": got, "error": why, **extra,
    }  # fmt: skip


def answer_plexus_scale(
    p: ScalePrepared, qs: list[Question], client: Any, k: int, log: Callable[[str], None]
) -> list[dict[str, Any]]:
    ans = ScalePlexusAnswerer(client, p.tenant)
    rows = []
    for q in qs:
        try:
            got, meta = ans.answer(q)
            ok, why = score(q, got)
        except Exception as exc:  # noqa: BLE001 - reported per question, never hidden
            got, meta, ok, why = (
                None, {"latency_ms": 0.0, "server_ms": 0.0, "statements": 0, "queries": []}, False,
                f"{type(exc).__name__}: {exc}"[:200],
            )  # fmt: skip
        rows.append(
            _row(q, ok, got, why, k, tokens=0, cost_usd=0.0, latency_ms=meta["latency_ms"], server_ms=meta["server_ms"],
                 statements=meta["statements"], cached=False, context_chars=0, truncated=False)
        )  # fmt: skip
    log(f"  P: {sum(r['correct'] for r in rows)}/{len(rows)} correct, deterministic Cypher")
    return rows


def context_for(arm: str, p: ScalePrepared, index: C.B2Index | None, q: Question) -> C.Context:
    assert p.path is not None
    if arm == "B0":
        return SC.b0_scale_context(p.path, q.text)
    if arm == "B1":
        return SC.b1_scale_context(p.path / "crucible.db", q.text)
    assert index is not None
    return index.context(q.text)


def answer_baseline_scale(
    p: ScalePrepared, qs: list[Question], runner: ClaudeRunner, embedder: Any, k: int, log: Callable[[str], None],
    ctx_dir: Path | None,
) -> tuple[list[dict[str, Any]], bool]:  # fmt: skip
    index = C.B2Index(p.path / "crucible.db", embedder) if p.arm == "B2" else None  # type: ignore[operator]
    rows: list[dict[str, Any]] = []
    for q in qs:
        ctx = context_for(p.arm, p, index, q)
        if ctx_dir is not None:
            d = ctx_dir / "contexts" / p.arm
            d.mkdir(parents=True, exist_ok=True)
            (d / f"{q.id}.txt").write_text(ctx.text, encoding="utf-8", newline="\n")
        try:
            call = runner.ask(p.arm, q, ctx.text)
            if call.error and not call.cached:
                call = runner.ask(p.arm, q, ctx.text, use_cache=False)  # one retry for process-level failures
        except BudgetExceeded as exc:
            log(f"  {p.arm}: stopped at {q.id}: {exc}")
            return rows, False
        if call.error:
            ok, why, got = False, f"call failed: {call.error}", None
        elif call.parse_error:
            ok, why, got = False, call.parse_error, None
        else:
            got = call.answer
            ok, why = score(q, got)
        share = SC.sprint_share(ctx, q.args["sprint"])
        rows.append(
            _row(
                q, ok, got, why, k,
                tokens=call.total_tokens, usage={u: call.usage.get(u, 0) for u in USAGE_KEYS},
                cost_usd=round(call.cost_usd, 6), latency_ms=call.latency_ms, cached=call.cached,
                context_chars=ctx.chars, artifact_chars=ctx.artifact_chars, truncated=True,
                context_sha256=ctx.sha256[:16], model=call.model, num_turns=call.num_turns, reply=call.reply[:600],
                reply_format=reply_format(call.reply, bool(call.error)), shown_units=len(ctx.parts),
                shown_lines=share["lines"], shown_lines_with_sprint=share["lines_with_sprint"],
                evidence_in_context=evidence_in_context(q, ctx.text),
            )
        )  # fmt: skip
        log(
            f"  {p.arm} {q.id} {'ok ' if ok else 'BAD'} {call.total_tokens:>6} tok  ${call.cost_usd:.4f}  {call.latency_ms / 1000:.1f}s{'  (cached)' if call.cached else ''}"
        )
    return rows, True


# ------------------------------------------------------------------------------------------------ results
def wilson95(c: int, n: int) -> list[float]:
    """Wilson 95% interval for a proportion, in percent (one run per question: this is the sampling width, not noise of the model)."""
    if n == 0:
        return [0.0, 0.0]
    z = 1.96
    p = c / n
    den = 1 + z * z / n
    mid = (p + z * z / (2 * n)) / den
    half = z * ((p * (1 - p) / n + z * z / (4 * n * n)) ** 0.5) / den
    return [round(100 * max(0.0, mid - half), 1), round(100 * min(1.0, mid + half), 1)]


def by_stratum(rows: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    out = {}
    for s in ("early", "middle", "late"):
        sr = [r for r in rows if r["stratum"] == s]
        if sr:
            c = sum(r["correct"] for r in sr)
            out[s] = {"correct": c, "total": len(sr), "pct": _pct(c, len(sr))}
    return out


def arm_summary_scale(
    arm: str, rows: list[dict[str, Any]], completed: bool, ctx: dict[str, Any] | None
) -> dict[str, Any]:
    out = arm_summary(arm, rows, completed, ctx)
    out["answerer"] = ANSWERERS_SCALE[arm]
    out["accuracy"]["wilson95_pct"] = wilson95(out["accuracy"]["correct"], out["accuracy"]["total"])
    out["by_stratum"] = by_stratum(rows)
    if arm != "P":
        wrong = [r for r in rows if not r["correct"]]
        ev = [r.get("evidence_in_context") for r in wrong if r.get("evidence_in_context")]
        out["failure_analysis"] = {
            "wrong": len(wrong),
            "call_failed": sum(r.get("reply_format") == "call_failed" for r in wrong),
            "unparseable": sum(r.get("reply_format") == "unparseable" for r in wrong),
            "wrong_with_all_evidence_in_context": sum(e["found"] == e["total"] for e in ev),
            "wrong_with_partial_or_no_evidence_in_context": sum(e["found"] < e["total"] for e in ev),
            "median_share_of_shown_lines_from_the_asked_sprint": round(
                statistics.median([r["shown_lines_with_sprint"] / max(r["shown_lines"], 1) for r in rows]), 3
            )
            if rows
            else 0,
        }
    return out


def assemble_scale_layer(
    *, mode: str, model: str, qs: list[Question], all_qs: list[Question], sl: ScaleLedger, arms: dict[str, Any],
    budget_usd: float | None, notes: list[str], artifact_chars: dict[str, int], qpath: Path = QUESTIONS_PATH,
) -> dict[str, Any]:  # fmt: skip
    k = len(sl.sprints)
    fams = {f: {"title": t, "n": sum(q.family == f for q in qs)} for f, t in FAMILIES.items()}
    cap = C.CONTEXT_CHARS
    return {
        "title": "Provenance and time questions at scale (history >= 10x the context budget)",
        "mode": mode,
        "model": model,
        "model_ids": sorted({r["model"] for a in arms.values() for r in a["questions"] if r.get("model")}),
        "context_budget_chars": cap,
        "b2_top_k": C.B2_TOP_K,
        "budget_usd": budget_usd,
        "history": {
            "sprints": k,
            "scenario": sl.summary(),
            "artifact_chars": artifact_chars,
            "artifact_chars_over_budget": {a: round(v / cap, 2) for a, v in artifact_chars.items()},
            "strata": {
                s: [n for n in range(1, k + 1) if stratum_of(n, k) == s] for s in ("early", "middle", "late")
            },
        },
        "retrieval": {
            "B0": "BM25 over chunks of the arm's files (task, source entry, MEMORY.md bullet, jsonl line)",
            "B1": "full schema always; BM25 over rows (own text + one-hop joined text), best rows that fit",
            "B2": "vector top-12 chunks (local bge-small), unchanged from L2",
            "bm25": {"k1": SC.K1, "b": SC.B, "query": "the question text"},
        },
        "question_set": {
            "path": "plexus/demo_data/crucible/questions_scale.yaml",
            "sha256": hashlib.sha256(qpath.read_bytes()).hexdigest() if qpath.exists() else "",
            "total": len(all_qs),
            "asked": len(qs),
            "ids": [q.id for q in qs],
            "sprints": {q.id: q.args["sprint"].upper() for q in qs},
            "seed": SEED,
        },
        "families": {kk: v for kk, v in fams.items() if v["n"]},
        "arms": arms,
        "summary": {
            "accuracy_pct": {a: v["accuracy"]["pct"] for a, v in arms.items()},
            "tokens_per_question": {a: v["usage"]["tokens_per_question"] for a, v in arms.items()},
            "cost_usd": {a: v["usage"]["cost_usd"] for a, v in arms.items()},
            "latency_ms_median": {a: v["usage"]["latency_ms"]["median"] for a, v in arms.items()},
        },
        "plexus_changes": PLEXUS_CHANGES,
        "notes": notes,
    }


def headline_scale(layer: dict[str, Any]) -> list[str]:
    arms = layer["arms"]
    out = []
    for a, v in arms.items():
        acc, usage = v["accuracy"], v["usage"]
        who = "Plexus (deterministic Cypher)" if a == "P" else f"{a} + claude -p ({layer['model']})"
        extra = (
            ""
            if a == "P"
            else f", {usage['tokens_per_question']:.0f} tokens and ${usage['cost_per_question_usd']:.3f} per question"
        )
        out.append(
            f"L2-scale: {who} answered {acc['correct']}/{acc['total']} ({acc['pct']}%) exactly{extra}."
        )
    if "P" in arms:
        for a, v in arms.items():
            if a == "P":
                continue
            diff = arms["P"]["accuracy"]["pct"] - v["accuracy"]["pct"]
            word = "ties" if diff == 0 else ("beats" if diff > 0 else "trails")
            out.append(f"L2-scale: Plexus {word} {a} by {abs(diff):.1f} points.")
    return out


def scale_results_doc(
    layer: dict[str, Any], run_id: str, started: float, command: str, host: str, port: int, embedder: str
) -> dict[str, Any]:  # fmt: skip
    finished = time.time()
    arms = [a for a in ARMS if a in layer["arms"]]
    return {
        "schema_version": H.SCHEMA_VERSION,
        "kind": "crucible-results",
        "run": {
            "id": run_id,
            "started_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(started)),
            "finished_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(finished)),
            "duration_s": round(finished - started, 1),
            "quick": layer["mode"] == "pilot",
            "command": command,
            "layers": ["L2_scale"],
        },
        "environment": environment.collect(host, port, embedder),
        "config": {
            "arms": arms,
            "l2_scale": {
                kk: layer[kk]
                for kk in (
                    "mode",
                    "model",
                    "context_budget_chars",
                    "b2_top_k",
                    "budget_usd",
                    "question_set",
                    "retrieval",
                )
            },
        },
        "arms": H.arms_section(arms),
        "layers": {"L2_scale": layer},
        "summary": {
            "l2_scale_accuracy_pct": layer["summary"]["accuracy_pct"],
            "headline": headline_scale(layer),
        },
        "honesty": [*HONESTY],
    }


# ------------------------------------------------------------------------------------------------ report
def _fmt_ms(ms: float) -> str:
    return f"{ms:.1f} ms" if ms < 1000 else f"{ms / 1000:.2f} s"


def render_scale_report(doc: dict[str, Any]) -> str:
    layer = doc["layers"]["L2_scale"]
    arms = layer["arms"]
    order = list(arms)
    w: list[str] = []
    h = layer["history"]
    w.append(f"# Crucible L2 at scale ({layer['mode']})\n")
    w.append(
        f"Run {doc['run']['id']} · model `{layer['model']}` ({', '.join(layer['model_ids']) or 'n/a'}) · context cap "
        f"{layer['context_budget_chars']:,} chars · {layer['question_set']['asked']} of {layer['question_set']['total']} questions · "
        f"{h['sprints']} sprints\n"
    )
    w.append("## History vs the context budget\n")
    w.append("| Artifact | chars | x cap |")
    w.append("|---|---|---|")
    for a, v in h["artifact_chars"].items():
        w.append(f"| {a} | {v:,} | {h['artifact_chars_over_budget'][a]} |")
    w.append("\n## Accuracy (exact match)\n")
    w.append("| Family | n | " + " | ".join(order) + " |")
    w.append("|---|---|" + "---|" * len(order))
    for fam, info in layer["families"].items():
        cells = []
        for a in order:
            f = arms[a]["by_family"].get(fam)
            cells.append(f"{f['correct']}/{f['total']}" if f else "-")
        w.append(f"| {info['title']} | {info['n']} | " + " | ".join(cells) + " |")
    ci = [
        f"{a} {arms[a]['accuracy']['wilson95_pct'][0]}-{arms[a]['accuracy']['wilson95_pct'][1]}%"
        for a in order
    ]
    totals = [
        f"**{arms[a]['accuracy']['correct']}/{arms[a]['accuracy']['total']} ({arms[a]['accuracy']['pct']}%)**"
        for a in order
    ]
    w.append(f"| **All** | {layer['question_set']['asked']} | " + " | ".join(totals) + " |\n")
    w.append("Wilson 95% intervals on the totals: " + ", ".join(ci) + ".\n")
    w.append("By position of the asked sprint in the history:\n")
    w.append("| Stratum | sprints | " + " | ".join(order) + " |")
    w.append("|---|---|" + "---|" * len(order))
    for s, sprints in h["strata"].items():
        cells = []
        for a in order:
            x = arms[a]["by_stratum"].get(s)
            cells.append(f"{x['correct']}/{x['total']}" if x else "-")
        w.append(f"| {s} | S{sprints[0]:02d}-S{sprints[-1]:02d} | " + " | ".join(cells) + " |")
    strict = [
        f"{arms[a]['accuracy_whole_reply_json']['correct']}/{arms[a]['accuracy_whole_reply_json']['total']}"
        for a in order
    ]
    w.append(
        "\nWhole-reply-JSON-only variant (stricter): "
        + ", ".join(f"{a} {x}" for a, x in zip(order, strict, strict=True))
        + "\n"
    )
    w.append("## Cost\n")
    w.append(
        "| Arm | tokens / question | cost / question | total cost | median latency | context chars (median) |"
    )
    w.append("|---|---|---|---|---|---|")
    for a in order:
        u = arms[a]["usage"]
        c = arms[a].get("context", {})
        w.append(
            f"| {a} | {u['tokens_per_question']:.0f} | ${u['cost_per_question_usd']:.4f} | ${u['cost_usd']:.3f} | "
            f"{_fmt_ms(u['latency_ms']['median'])} | {c.get('chars_median', '-')} |"
        )
    w.append("\n## Failure analysis\n")
    for a in order:
        fa = arms[a].get("failure_analysis")
        if fa:
            w.append(
                f"- **{a}**: {fa['wrong']} wrong; {fa['unparseable']} unparseable replies, {fa['call_failed']} failed calls; "
                f"of the wrong answers with a checkable answer, {fa['wrong_with_all_evidence_in_context']} had every expected item's words "
                f"somewhere in the context and {fa['wrong_with_partial_or_no_evidence_in_context']} did not; median share of shown "
                f"lines that mention the asked sprint: {fa['median_share_of_shown_lines_from_the_asked_sprint']}."
            )
    w.append("\n## Wrong answers\n")
    any_wrong = False
    for a in order:
        for r in arms[a]["questions"]:
            if not r["correct"]:
                any_wrong = True
                ev = r.get("evidence_in_context")
                w.append(
                    f"- **{a} {r['id']}** ({r['family']}, {r['sprint']}, {r['stratum']}): expected `{json.dumps(r['expected'])}`, "
                    f"got `{json.dumps(r['got'])}`{' (' + r['error'] + ')' if r['error'] else ''}"
                    + (f"; evidence in context {ev['found']}/{ev['total']}" if ev else "")
                )
    if not any_wrong:
        w.append("none")
    w.append("\n## Headline\n")
    w += [f"- {x}" for x in doc["summary"]["headline"]]
    w.append("\n## Plexus changes relative to the 43-question L2 answerer\n")
    w += [f"- {x}" for x in layer["plexus_changes"]]
    w.append("\n## Notes\n")
    w += [f"- {n}" for n in layer["notes"]]
    w.append("\n## Honesty\n")
    w += [f"- {x}" for x in doc["honesty"]]
    return "\n".join(w) + "\n"


def write_scale_outputs(doc: dict[str, Any], out_root: Path, run_id: str) -> Path:
    d = out_root / run_id
    d.mkdir(parents=True, exist_ok=True)
    (d / "results.json").write_text(json.dumps(doc, indent=2) + "\n", encoding="utf-8", newline="\n")
    (d / "report.md").write_text(render_scale_report(doc), encoding="utf-8", newline="\n")
    mode = doc["layers"]["L2_scale"]["mode"]
    shutil.copyfile(d / "results.json", out_root / f"latest-{mode}.json")
    return d


# ------------------------------------------------------------------------------------------------ the run
def run_scale(
    *, mode: str, arms: tuple[str, ...], model: str, budget_usd: float | None, host: str, port: int, embedder: str,
    out_root: Path, cache_dir: Path, log: Callable[[str], None], k: int = K_SPRINTS, command: str = "",
    launcher: list[str] | None = None, question_ids: tuple[str, ...] | None = None, qpath: Path = QUESTIONS_PATH,
    run_id: str | None = None, keep_graph: bool = False,
) -> tuple[dict[str, Any], Path]:  # fmt: skip
    started = time.time()
    run_id = run_id or time.strftime("%Y%m%dT%H%M%SZ", time.gmtime()) + f"-{mode}"
    work = Path(tempfile.mkdtemp(prefix="crucible-l2s-"))
    all_qs = load_scale_questions(qpath)
    ref, _ = check_scale_questions(all_qs, work / "ref", k)
    ids = question_ids or (PILOT_IDS if mode == "pilot" else tuple(q.id for q in all_qs))
    qs = [q for q in all_qs if q.id in ids]
    log(
        f"L2-scale {mode}: {len(qs)} questions, {k} sprints, arms {','.join(arms)}, model {model}, budget {budget_usd}"
    )
    runner = ClaudeRunner(
        model, cache_dir=cache_dir, budget_usd=budget_usd, launcher=launcher, conventions=CONVENTIONS_SCALE,
        prompt_version=PROMPT_VERSION,
    )  # fmt: skip
    emb = None
    if "B2" in arms:
        from plexus.embed import get_embedder

        emb = get_embedder(embedder)
    prepared: dict[str, ScalePrepared] = {}
    results: dict[str, Any] = {}
    artifact_chars: dict[str, int] = {}
    notes: list[str] = []
    client = None
    try:
        for arm in arms:
            tenant = f"l2s_{run_id.replace('-', '_').lower()}"[:48]
            p = prepare_scale_arm(arm, work / "arms", host, port, embedder, tenant, k)
            prepared[arm] = p
            if strip_scale(p.ledger) != strip_scale(ref):
                raise SystemExit(f"arm {arm} did not reproduce the reference story")
            s = p.ledger.summary()
            log(
                f"{arm}: {k} sprints played ({s['facts']} facts, {s['decisions']} decisions); ledgers match the reference"
            )
            if arm == "P":
                from plexus.graph.client import GraphClient

                client = GraphClient(host=host, port=port)
                rows = answer_plexus_scale(p, qs, client, k, log)
                results[arm] = arm_summary_scale(arm, rows, True, None)
            else:
                assert p.path is not None
                if arm == "B0":
                    artifact_chars[arm] = C.b0_context(p.path, 10**9).artifact_chars
                elif arm == "B1":
                    artifact_chars[arm] = C.b1_context(p.path / "crucible.db", 10**9).artifact_chars
                else:
                    artifact_chars[arm] = C.B2Index(p.path / "crucible.db", emb).context("x").artifact_chars
                rows, done = answer_baseline_scale(p, qs, runner, emb, k, log, out_root / run_id)
                results[arm] = arm_summary_scale(arm, rows, done, context_summary(rows))
                if not done:
                    notes.append(
                        f"{arm} stopped early at the ${budget_usd} budget cap after {len(rows)} questions."
                    )
        total_cost = sum(v["usage"]["cost_usd"] for v in results.values())
        live = sum(v["usage"]["calls_run_live"] for v in results.values())
        cached = sum(v["usage"]["calls_from_cache"] for v in results.values())
        notes.append(
            f"LLM cost of the answers reported here: ${total_cost:.4f} over {live + cached} claude -p calls ({live} run in this "
            f"invocation for ${runner.spent_usd:.4f}; {cached} re-used from the on-disk cache demo_data/crucible/l2_scale_cache, where each entry "
            "is the original call: tokens, cost and latency in the rows are those original measurements, so 'cached: true' means re-scored, not free of cost)."
        )
        notes.append(
            "Each baseline question is one `claude -p` process (max-turns 3, no tools, context on stdin, ANTHROPIC_API_KEY removed); "
            "permission_denials and tool use are checked per call and fail the question."
        )
        notes.append(
            "Scoring rule for the baselines (decided before the first paid call, = the final L2 rule): the model may reason in prose first, but the "
            'reply must END with exactly one {"answer": ...} JSON object (no text after it); that object is compared by exact match. '
            "`accuracy_whole_reply_json` counts only replies that are nothing but the JSON object."
        )
        if mode == "pilot":
            notes.append(
                "PILOT: 5 questions (five families, all three strata); not a result. It only gates the cost of the full run."
            )
        layer = assemble_scale_layer(
            mode=mode, model=model, qs=qs, all_qs=all_qs, sl=ref, arms=results, budget_usd=budget_usd, notes=notes,
            artifact_chars=artifact_chars, qpath=qpath,
        )  # fmt: skip
        doc = scale_results_doc(
            layer, run_id, started, command or f"l2.scale_run run --mode {mode}", host, port, embedder
        )
        d = write_scale_outputs(doc, out_root, run_id)
        log(f"results: {d / 'results.json'}")
        return doc, d
    finally:
        for p in prepared.values():
            if p.arm == "P" and not keep_graph:
                drop = getattr(p.backend, "drop", None)
                if drop:
                    drop()
            p.backend.close()
        if client is not None:
            client.close()
        shutil.rmtree(work, ignore_errors=True)


# ------------------------------------------------------------------------------------------------ CLI
def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="crucible-l2-scale")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("questions", help="regenerate questions_scale.yaml from the scenario script")
    r = sub.add_parser("run", help="play K sprints on every arm, answer and score")
    r.add_argument("--mode", choices=("pilot", "full"), default="pilot")
    r.add_argument("--arms", default=",".join(ARMS))
    r.add_argument("--model", default="sonnet")
    r.add_argument(
        "--budget-usd", type=float, default=None, help="stop spending when non-cached calls reach this"
    )
    r.add_argument("--host", default="127.0.0.1")
    r.add_argument("--port", type=int, default=6366)
    r.add_argument("--embedder", choices=("fastembed", "hash"), default="fastembed")
    r.add_argument("--out", type=Path, default=OUT_DIR)
    r.add_argument("--cache", type=Path, default=CACHE_DIR)
    r.add_argument("--ids", default="", help="comma list of question ids (overrides the mode's set)")
    r.add_argument("--keep-graph", action="store_true")
    a = ap.parse_args(argv)
    if a.cmd == "questions":
        sl, qs = generate_scale(tempfile.mkdtemp(prefix="crucible-l2s-q-"), K_SPRINTS)
        dump_scale_questions(qs, sl, QUESTIONS_PATH)
        print(f"wrote {len(qs)} questions to {QUESTIONS_PATH}")
        return 0
    arms = tuple(x for x in a.arms.split(",") if x)
    bad = [x for x in arms if x not in ARMS]
    if bad:
        raise SystemExit(f"unknown arm(s) {bad}; expected {ARMS}")
    doc, _d = run_scale(
        mode=a.mode, arms=arms, model=a.model, budget_usd=a.budget_usd, host=a.host, port=a.port,
        embedder=a.embedder, out_root=a.out, cache_dir=a.cache, log=lambda s: print(s, flush=True),
        command="python -m plexus.crucible.l2.scale_run " + " ".join(argv if argv is not None else sys.argv[1:]),
        question_ids=tuple(x for x in a.ids.split(",") if x) or None, keep_graph=a.keep_graph,
    )  # fmt: skip
    for hline in doc["summary"]["headline"]:
        print(hline)
    return 0


_ = (
    ANSWERERS,
    BASELINES,
    build_scale_questions,
    parse_reply,
    percentile,
    scale_summary,
)  # re-exported for tests

if __name__ == "__main__":
    raise SystemExit(main())
