"""Run Layer 2: play the scenario on every arm, answer the questions, score them, write the ``L2`` layer.

    python -m plexus.crucible.l2.run questions                       # regenerate demo_data/crucible/questions.yaml
    python -m plexus.crucible.l2.run run --mode pilot --port 6378     # 5 questions x B0,B1,B2 with claude -p, + P
    python -m plexus.crucible.l2.run run --mode full  --port 6378     # all questions
    python -m plexus.crucible.l2.run merge --into results.json --l2 demo_data/crucible/l2/<run>/results.json

``results.json`` has the same envelope as H's (``schema_version``, ``run``, ``environment``, ``config``, ``arms``,
``layers``, ``summary``, ``honesty``); the L2 numbers live in ``layers["L2"]`` (shape: :func:`assemble_layer`).
"""

from __future__ import annotations

import argparse
import copy
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
from plexus.crucible.l2.llm import USAGE_KEYS, BudgetExceeded, ClaudeRunner, LlmCall
from plexus.crucible.l2.plexus_answerer import PlexusAnswerer
from plexus.crucible.l2.questions import (
    FAMILIES,
    Question,
    dump_questions,
    generate,
    load_questions,
    parse_reply,
    scenario_summary,
    score,
)
from plexus.crucible.l2.scenario import Ledger, play
from plexus.crucible.util import fmt_ms, iso_utc, percentile, run_stamp

PKG = Path(__file__).resolve()
DEMO_DATA = PKG.parents[4] / "demo_data" / "crucible"
QUESTIONS_PATH = DEMO_DATA / "questions.yaml"
CACHE_DIR = DEMO_DATA / "l2_cache"
OUT_DIR = DEMO_DATA / "l2"
BASELINES = ("B0", "B1", "B2")
ARMS = ("B0", "B1", "B2", "P")
# the pilot: one question from each of five different families, across question kinds (set, ordered, value)
PILOT_IDS = ("Q05", "Q15", "Q17", "Q29", "Q43")

ANSWERERS = {
    "B0": "claude -p over the arm's files (tasks.json, MEMORY.md, decisions/handoffs jsonl, sources.json, logs)",
    "B1": "claude -p over the schema + CSV dump of the arm's SQLite tables",
    "B2": "claude -p over the top-12 retrieved memory chunks (local bge-small embeddings)",
    "P": "deterministic Cypher against the tenant graph (no LLM)",
}

L2_HONESTY = [
    "L2: exact-match accuracy over a script-derived question set (43 questions, 10 families), one scenario, one model, one run per question; no LLM judge anywhere. Ground truth is computed from the scenario script, not read back from any arm.",
    "Baselines are the same unmodified `claude -p` with no tools, shown their own artifacts at the same 32,000-character cap. At this scenario size the B0 and B1 artifacts fit in the cap without truncation, so the cap is not what limits them; B2 deliberately sees only its top-12 retrieved chunks.",
    "Result in plain words: at this scenario size (12 tasks, 9 facts, 6 decisions) the whole B0 run is about 25k characters and the whole B1 dump about 18k, so Sonnet reads everything and answers every question; Plexus TIES them on accuracy. What Plexus does measurably better here is cost and determinism (no tokens, a few milliseconds, same answer every time versus 13-16k tokens and ~5 s per question). Whether accuracy diverges when the artifacts outgrow the context cap is NOT measured by this run.",
    "Arm P answers each question with a hand-written Cypher statement per question family. That is the point of the comparison (a graph can answer these with one query) but it is also engineering effort the baselines do not get: the baselines were given no hand-written SQL or grep helpers either.",
    "The Procedures family of BASELINE §2 is not in this set: the backend protocol has no procedure tool, so the arms cannot be compared on it. Cross-session recall is reduced to episodes recorded by agents (the protocol has no sessions).",
    "The scenario is the P3 Acme script replayed on the backend protocol, plus three L2 additions (the forum-post poison fault, one extra builder decision, two project-scoped facts); see crucible/l2/scenario.py.",
    "B1 and B2 (and B0's task file) keep only a task's final claimer, not the claim history; only B0's per-agent logs and Plexus's CLAIMED edges record who held an expired lease. Recovery questions therefore test what each arm's artifacts actually contain, as configured in L1.",
]


# ------------------------------------------------------------------------------------------------ preparation
def strip_ids(led: Ledger) -> dict[str, Any]:
    d = led.to_json()
    d.pop("arm")
    for key in ("facts", "decisions", "sources", "artifacts"):
        for row in d[key]:
            row.pop("id", None)
    return d


class Prepared:
    """One arm after the scenario has been played on it."""

    def __init__(self, arm: str, tenant: str, backend: Any, ledger: Ledger, path: Path | None):
        self.arm, self.tenant, self.backend, self.ledger, self.path = arm, tenant, backend, ledger, path


def prepare_arm(arm: str, root: Path, host: str, port: int, embedder: str, tenant: str) -> Prepared:
    b = open_backend(
        BackendSpec(arm=arm, tenant=tenant, root=str(root), host=host, port=port, embedder=embedder)
    )
    led = play(b)
    path = getattr(b, "dir", None)
    return Prepared(arm, tenant, b, led, Path(path) if path else None)


def reply_format(reply: str, failed: bool) -> str:
    """``json_only`` (the whole reply is the answer object), ``prose_then_json`` or ``unparseable``."""
    if failed:
        return "call_failed"
    if parse_reply(reply, strict=True)[1] == "":
        return "json_only"
    return "prose_then_json" if parse_reply(reply)[1] == "" else "unparseable"


def check_questions(committed: list[Question], tmp: Path) -> tuple[Ledger, list[Question]]:
    led, fresh = generate(tmp)
    if [q.to_json() for q in committed] != [q.to_json() for q in fresh]:
        raise SystemExit(
            "questions.yaml differs from what the scenario generates: run `... l2.run questions`"
        )
    return led, fresh


# ------------------------------------------------------------------------------------------------ answering
def _row(q: Question, ok: bool, got: Any, why: str, **extra: Any) -> dict[str, Any]:
    return {
        "id": q.id,
        "family": q.family,
        "correct": ok,
        "expected": q.answer,
        "got": got,
        "error": why,
        **extra,
    }


def empty_meta() -> dict[str, Any]:
    """The per-question meta of an answerer that raised."""
    return {"latency_ms": 0.0, "server_ms": 0.0, "statements": 0, "queries": []}


def ask_with_retry(runner: ClaudeRunner, arm: str, q: Question, context: str) -> LlmCall:
    """One ``claude -p`` call (cache first); a process-level failure that was not a cache hit is retried once, live."""
    call = runner.ask(arm, q, context)
    if call.error and not call.cached:
        call = runner.ask(arm, q, context, use_cache=False)
    return call


def grade_call(q: Question, call: LlmCall) -> tuple[bool, str, Any]:
    """``(correct, error text, parsed answer)`` for one baseline call."""
    if call.error:
        return False, f"call failed: {call.error}", None
    if call.parse_error:
        return False, call.parse_error, None
    ok, why = score(q, call.answer)
    return ok, why, call.answer


def answer_plexus(
    p: Prepared, qs: list[Question], client: Any, log: Callable[[str], None]
) -> list[dict[str, Any]]:
    ans = PlexusAnswerer(client, p.tenant)
    rows = []
    for q in qs:
        try:
            got, meta = ans.answer(q)
            ok, why = score(q, got)
        except Exception as exc:  # noqa: BLE001 - reported per question, never hidden
            got, meta, ok, why = None, empty_meta(), False, f"{type(exc).__name__}: {exc}"[:200]
        rows.append(
            _row(q, ok, got, why, tokens=0, cost_usd=0.0, latency_ms=meta["latency_ms"], server_ms=meta["server_ms"],
                 statements=meta["statements"], cached=False, context_chars=0, truncated=False)
        )  # fmt: skip
    log(f"  P: {sum(r['correct'] for r in rows)}/{len(rows)} correct, deterministic Cypher")
    return rows


def answer_baseline(
    p: Prepared,
    qs: list[Question],
    runner: ClaudeRunner,
    embedder: Any,
    log: Callable[[str], None],
    ctx_dir: Path | None,
) -> tuple[list[dict[str, Any]], bool]:
    """Returns (rows, completed). ``completed`` is False when the budget cap stopped the arm early."""
    assert p.path is not None
    if p.arm == "B0":
        fixed = C.b0_context(p.path)
    elif p.arm == "B1":
        fixed = C.b1_context(p.path / "crucible.db")
    else:
        fixed = None
    index = C.B2Index(p.path / "crucible.db", embedder) if p.arm == "B2" else None
    if fixed is not None and ctx_dir is not None:
        ctx_dir.mkdir(parents=True, exist_ok=True)
        (ctx_dir / f"{p.arm}.context.txt").write_text(fixed.text, encoding="utf-8", newline="\n")
    rows: list[dict[str, Any]] = []
    for q in qs:
        ctx = fixed if fixed is not None else index.context(q.text)  # type: ignore[union-attr]
        try:
            call = ask_with_retry(runner, p.arm, q, ctx.text)
        except BudgetExceeded as exc:
            log(f"  {p.arm}: stopped at {q.id}: {exc}")
            return rows, False
        ok, why, got = grade_call(q, call)
        rows.append(
            _row(
                q, ok, got, why,
                tokens=call.total_tokens, usage={k: call.usage.get(k, 0) for k in USAGE_KEYS},
                cost_usd=round(call.cost_usd, 6), latency_ms=call.latency_ms, cached=call.cached,
                context_chars=ctx.chars, artifact_chars=ctx.artifact_chars, truncated=ctx.truncated, context_sha256=ctx.sha256[:16],
                model=call.model, num_turns=call.num_turns, reply=call.reply[:600],
                reply_format=reply_format(call.reply, bool(call.error)),
                retrieved=[c for c in ctx.parts] if p.arm == "B2" else None,
            )
        )  # fmt: skip
        log(
            f"  {p.arm} {q.id} {'ok ' if ok else 'BAD'} {call.total_tokens:>6} tok  ${call.cost_usd:.4f}  {call.latency_ms / 1000:.1f}s{'  (cached)' if call.cached else ''}"
        )
    return rows, True


# ------------------------------------------------------------------------------------------------ results
def _pct(c: int, n: int) -> float:
    return round(100.0 * c / n, 1) if n else 0.0


def arm_summary(
    arm: str, rows: list[dict[str, Any]], completed: bool, ctx: dict[str, Any] | None
) -> dict[str, Any]:
    n = len(rows)
    by_family: dict[str, dict[str, Any]] = {}
    for fam in FAMILIES:
        fr = [r for r in rows if r["family"] == fam]
        if fr:
            c = sum(r["correct"] for r in fr)
            by_family[fam] = {"correct": c, "total": len(fr), "pct": _pct(c, len(fr))}
    correct = sum(r["correct"] for r in rows)
    lat = [r["latency_ms"] for r in rows]
    usage = {k: sum(r.get("usage", {}).get(k, 0) for r in rows) for k in USAGE_KEYS}
    live = [r for r in rows if not r["cached"] and arm != "P"]
    out: dict[str, Any] = {
        "answerer": ANSWERERS[arm],
        "completed": completed,
        "accuracy": {"correct": correct, "total": n, "pct": _pct(correct, n)},
        "by_family": by_family,
        "errors": sum(1 for r in rows if r["error"].startswith("call failed")),
        "unparseable": sum(1 for r in rows if r.get("reply_format") == "unparseable"),
        "reply_format": {
            k: sum(1 for r in rows if r.get("reply_format") == k)
            for k in ("json_only", "prose_then_json", "unparseable", "call_failed")
        }
        if arm != "P"
        else None,
        "accuracy_whole_reply_json": {
            "correct": sum(r["correct"] and r.get("reply_format", "json_only") == "json_only" for r in rows),
            "total": n,
            "pct": _pct(
                sum(r["correct"] and r.get("reply_format", "json_only") == "json_only" for r in rows), n
            ),
        },
        "usage": {
            "llm_calls": 0 if arm == "P" else n,
            "calls_run_live": len(live),
            "calls_from_cache": 0 if arm == "P" else n - len(live),
            **usage,
            "total_tokens": sum(usage.values()),
            "tokens_per_question": round(sum(usage.values()) / n, 1) if n else 0,
            "cost_usd": round(sum(r["cost_usd"] for r in rows), 4),
            "cost_per_question_usd": round(sum(r["cost_usd"] for r in rows) / n, 4) if n else 0,
            "latency_ms": {
                "median": round(statistics.median(lat), 1) if lat else 0,
                "p95": round(percentile(lat, 95), 1),
                "total": round(sum(lat), 1),
            },
        },
        "questions": rows,
    }
    if arm == "P":
        out["usage"]["server_ms"] = {
            "median": round(statistics.median([r["server_ms"] for r in rows]), 3) if rows else 0,
            "total": round(sum(r["server_ms"] for r in rows), 3),
        }
        out["usage"]["statements"] = sum(r["statements"] for r in rows)
    if ctx:
        out["context"] = ctx
    return out


def context_summary(rows: list[dict[str, Any]]) -> dict[str, Any]:
    chars = [r["context_chars"] for r in rows]
    return {
        "chars_median": int(statistics.median(chars)) if chars else 0,
        "chars_max": max(chars, default=0),
        "artifact_chars": max((r.get("artifact_chars", 0) for r in rows), default=0),
        "questions_truncated": sum(1 for r in rows if r["truncated"]),
    }


def assemble_layer(
    *, mode: str, model: str, qs: list[Question], all_qs: list[Question], led: Ledger, arms: dict[str, Any],
    budget_usd: float | None, notes: list[str], qpath: Path = QUESTIONS_PATH,
) -> dict[str, Any]:  # fmt: skip
    fams = {f: {"title": t, "n": sum(q.family == f for q in qs)} for f, t in FAMILIES.items()}
    qhash = hashlib.sha256(qpath.read_bytes()).hexdigest() if qpath.exists() else ""
    return {
        "title": "Provenance and time questions (exact match)",
        "mode": mode,
        "model": model,
        "model_ids": sorted({r["model"] for a in arms.values() for r in a["questions"] if r.get("model")}),
        "context_budget_chars": C.CONTEXT_CHARS,
        "b2_top_k": C.B2_TOP_K,
        "budget_usd": budget_usd,
        "question_set": {
            "path": "plexus/demo_data/crucible/questions.yaml",
            "sha256": qhash,
            "total": len(all_qs),
            "asked": len(qs),
            "ids": [q.id for q in qs],
        },
        "scenario": scenario_summary(led),
        "families": {k: v for k, v in fams.items() if v["n"]},
        "arms": arms,
        "summary": {
            "accuracy_pct": {a: v["accuracy"]["pct"] for a, v in arms.items()},
            "tokens_per_question": {a: v["usage"]["tokens_per_question"] for a, v in arms.items()},
            "cost_usd": {a: v["usage"]["cost_usd"] for a, v in arms.items()},
            "latency_ms_median": {a: v["usage"]["latency_ms"]["median"] for a, v in arms.items()},
        },
        "notes": notes,
    }


def headline_l2(layer: dict[str, Any]) -> list[str]:
    arms = layer["arms"]
    out = []
    for a, v in arms.items():
        acc = v["accuracy"]
        usage = v["usage"]
        who = "Plexus (deterministic Cypher)" if a == "P" else f"{a} + claude -p ({layer['model']})"
        extra = (
            ""
            if a == "P"
            else f", {usage['tokens_per_question']:.0f} tokens and ${usage['cost_per_question_usd']:.3f} per question"
        )
        out.append(f"L2: {who} answered {acc['correct']}/{acc['total']} ({acc['pct']}%) exactly{extra}.")
    if "P" in arms:
        for a, v in arms.items():
            if a == "P":
                continue
            diff = arms["P"]["accuracy"]["pct"] - v["accuracy"]["pct"]
            lost = [
                f
                for f, x in v["by_family"].items()
                if x["pct"] > arms["P"]["by_family"].get(f, {"pct": 0})["pct"]
            ]
            word = "ties" if diff == 0 else ("beats" if diff > 0 else "trails")
            out.append(
                f"L2: Plexus {word} {a} by {abs(diff):.1f} points"
                + (f"; {a} is ahead on {', '.join(lost)}" if lost else "")
                + "."
            )
    return out


def results_doc(
    layer: dict[str, Any], run_id: str, started: float, command: str, host: str, port: int, embedder: str
) -> dict[str, Any]:
    finished = time.time()
    arms = [a for a in ("B0", "B1", "B2", "P") if a in layer["arms"]]
    return {
        "schema_version": H.SCHEMA_VERSION,
        "kind": "crucible-results",
        "run": {
            "id": run_id,
            "started_at": iso_utc(started),
            "finished_at": iso_utc(finished),
            "duration_s": round(finished - started, 1),
            "quick": layer["mode"] == "pilot",
            "command": command,
            "layers": ["L2"],
        },
        "environment": environment.collect(host, port, embedder),
        "config": {
            "arms": arms,
            "l2": {
                k: layer[k]
                for k in ("mode", "model", "context_budget_chars", "b2_top_k", "budget_usd", "question_set")
            },
        },
        "arms": H.arms_section(arms),
        "layers": {"L2": layer},
        "summary": {"l2_accuracy_pct": layer["summary"]["accuracy_pct"], "headline": headline_l2(layer)},
        "honesty": [*L2_HONESTY],
    }


def merge_into(base: dict[str, Any], l2_doc: dict[str, Any]) -> dict[str, Any]:
    """Return ``base`` (an H results.json) with the L2 layer, arm info, summary lines and honesty notes added."""
    out = copy.deepcopy(base)
    out.setdefault("layers", {})["L2"] = l2_doc["layers"]["L2"]
    run_layers = out.setdefault("run", {}).setdefault("layers", [])
    if "L2" not in run_layers:
        run_layers.append("L2")
    out.setdefault("config", {})["l2"] = l2_doc["config"]["l2"]
    for arm, info in l2_doc["arms"].items():
        out.setdefault("arms", {}).setdefault(arm, info)
    cfg_arms = out["config"].setdefault("arms", [])
    for arm in l2_doc["config"]["arms"]:
        if arm not in cfg_arms:
            cfg_arms.append(arm)
    summ = out.setdefault("summary", {})
    summ["l2_accuracy_pct"] = l2_doc["summary"]["l2_accuracy_pct"]
    summ["headline"] = [*summ.get("headline", []), *l2_doc["summary"]["headline"]]
    hon = out.setdefault("honesty", [])
    hon[:] = [h for h in hon if not h.startswith("L2 (provenance questions answered by an LLM")]
    hon += [h for h in l2_doc["honesty"] if h not in hon]
    return out


# ------------------------------------------------------------------------------------------------ report


def render_report(doc: dict[str, Any]) -> str:
    layer = doc["layers"]["L2"]
    arms = layer["arms"]
    w: list[str] = []
    w.append(f"# Crucible L2: provenance and time questions ({layer['mode']})\n")
    w.append(f"Run {doc['run']['id']} · model `{layer['model']}` ({', '.join(layer['model_ids']) or 'n/a'}) · "
             f"context cap {layer['context_budget_chars']:,} chars · {layer['question_set']['asked']} of "
             f"{layer['question_set']['total']} questions\n")  # fmt: skip
    w.append("## Accuracy (exact match)\n")
    order = list(arms)
    w.append("| Family | n | " + " | ".join(order) + " |")
    w.append("|---|---|" + "---|" * len(order))
    for fam, info in layer["families"].items():
        cells = []
        for a in order:
            f = arms[a]["by_family"].get(fam)
            cells.append(f"{f['correct']}/{f['total']}" if f else "-")
        w.append(f"| {info['title']} | {info['n']} | " + " | ".join(cells) + " |")
    totals = [
        f"**{arms[a]['accuracy']['correct']}/{arms[a]['accuracy']['total']} ({arms[a]['accuracy']['pct']}%)**"
        for a in order
    ]
    w.append(f"| **All** | {layer['question_set']['asked']} | " + " | ".join(totals) + " |\n")
    strict = [
        f"{arms[a]['accuracy_whole_reply_json']['correct']}/{arms[a]['accuracy_whole_reply_json']['total']}"
        for a in order
    ]
    w.append(
        "Whole-reply-JSON-only variant (stricter): "
        + ", ".join(f"{a} {x}" for a, x in zip(order, strict, strict=True))
        + "\n"
    )
    w.append("## Cost\n")
    w.append(
        "| Arm | tokens / question | cost / question | total cost | median latency | context chars (median) | truncated |"
    )
    w.append("|---|---|---|---|---|---|---|")
    for a in order:
        u = arms[a]["usage"]
        c = arms[a].get("context", {})
        w.append(f"| {a} | {u['tokens_per_question']:.0f} | ${u['cost_per_question_usd']:.4f} | ${u['cost_usd']:.3f} | "
                 f"{fmt_ms(u['latency_ms']['median'])} | {c.get('chars_median', '-')} | {c.get('questions_truncated', '-')} |")  # fmt: skip
    w.append("\n## Wrong answers\n")
    any_wrong = False
    for a in order:
        for r in arms[a]["questions"]:
            if not r["correct"]:
                any_wrong = True
                w.append(
                    f"- **{a} {r['id']}** ({r['family']}): expected `{json.dumps(r['expected'])}`, got `{json.dumps(r['got'])}`{' (' + r['error'] + ')' if r['error'] else ''}"
                )
    if not any_wrong:
        w.append("none")
    w.append("\n## Headline\n")
    w += [f"- {h}" for h in doc["summary"]["headline"]]
    w.append("\n## Notes\n")
    w += [f"- {n}" for n in layer["notes"]]
    w.append("\n## Honesty\n")
    w += [f"- {h}" for h in doc["honesty"]]
    return "\n".join(w) + "\n"


def write_outputs(doc: dict[str, Any], out_root: Path, run_id: str) -> Path:
    d = out_root / run_id
    d.mkdir(parents=True, exist_ok=True)
    (d / "results.json").write_text(json.dumps(doc, indent=2) + "\n", encoding="utf-8", newline="\n")
    (d / "report.md").write_text(render_report(doc), encoding="utf-8", newline="\n")
    mode = doc["layers"]["L2"]["mode"]
    shutil.copyfile(d / "results.json", out_root / f"latest-{mode}.json")
    return d


# ------------------------------------------------------------------------------------------------ the run
def run_l2(
    *, mode: str, arms: tuple[str, ...], model: str, budget_usd: float | None, host: str, port: int,
    embedder: str, out_root: Path, cache_dir: Path, log: Callable[[str], None], command: str = "",
    launcher: list[str] | None = None, question_ids: tuple[str, ...] | None = None,
    qpath: Path = QUESTIONS_PATH, run_id: str | None = None, keep_graph: bool = False,
) -> tuple[dict[str, Any], Path]:  # fmt: skip
    started = time.time()
    run_id = run_id or run_stamp() + f"-{mode}"
    work = Path(tempfile.mkdtemp(prefix="crucible-l2-"))
    all_qs = load_questions(qpath)
    ref_led, _ = check_questions(all_qs, work / "ref")
    ids = question_ids or (PILOT_IDS if mode == "pilot" else tuple(q.id for q in all_qs))
    qs = [q for q in all_qs if q.id in ids]
    log(f"L2 {mode}: {len(qs)} questions, arms {','.join(arms)}, model {model}, budget {budget_usd}")
    runner = ClaudeRunner(model, cache_dir=cache_dir, budget_usd=budget_usd, launcher=launcher)
    emb = None
    if "B2" in arms:
        from plexus.embed import get_embedder

        emb = get_embedder(embedder)
    prepared: dict[str, Prepared] = {}
    results: dict[str, Any] = {}
    notes: list[str] = []
    client = None
    try:
        for arm in arms:
            tenant = f"l2_{run_id.replace('-', '_').lower()}"[:48]
            p = prepare_arm(arm, work / "arms", host, port, embedder, tenant)
            prepared[arm] = p
            same = strip_ids(p.ledger) == strip_ids(ref_led)
            if not same:
                raise SystemExit(f"arm {arm} did not reproduce the reference story")
            log(
                f"{arm}: scenario played ({len(p.ledger.facts)} facts, {len(p.ledger.decisions)} decisions); ledger matches the reference"
            )
            if arm == "P":
                from plexus.graph.client import GraphClient

                client = GraphClient(host=host, port=port)
                rows = answer_plexus(p, qs, client, log)
                results[arm] = arm_summary(arm, rows, True, None)
            else:
                rows, done = answer_baseline(p, qs, runner, emb, log, out_root / run_id)
                results[arm] = arm_summary(arm, rows, done, context_summary(rows))
                if not done:
                    notes.append(
                        f"{arm} stopped early at the ${budget_usd} budget cap after {len(rows)} questions."
                    )
        total_cost = sum(v["usage"]["cost_usd"] for v in results.values())
        live = sum(v["usage"]["calls_run_live"] for v in results.values())
        cached = sum(v["usage"]["calls_from_cache"] for v in results.values())
        notes.append(
            f"LLM cost of the answers reported here: ${total_cost:.4f} over {live + cached} claude -p calls "
            f"({live} run in this invocation for ${runner.spent_usd:.4f}; {cached} re-used from the on-disk cache "
            "demo_data/crucible/l2_cache, where each entry is the original call: tokens, cost and latency in the rows are "
            "those original measurements, so 'cached: true' on a row means re-scored, not free of cost)."
        )
        notes.append(
            "Each baseline question is one `claude -p` process (max-turns 3, no tools, context on stdin, ANTHROPIC_API_KEY removed); permission_denials and tool use are checked per call and fail the question."
        )
        notes.append(
            "Scoring rule for the baselines: the model may reason in prose first, but the reply must END with exactly one "
            '{"answer": ...} JSON object (no text after it); that object is compared by exact match. '
            "`accuracy_whole_reply_json` is the stricter variant where only replies that are nothing but the JSON object "
            "count. The first full run used the whole-reply rule and scored B0 36/43, B1 38/43, B2 39/43 (Plexus 43/43): 13 baseline replies had a sentence of reasoning before a correct JSON object and were counted as unparseable. The rule was changed to the one above after seeing that (a methodology fix made with the results in view, so treat it as such), and every number was recomputed from the cached replies without any new LLM call. Both variants are reported."
        )
        if mode == "pilot":
            notes.append(
                "PILOT: 5 questions (one from each of 5 families); not a result. The full set is run only if this costs under the budget gate."
            )
        layer = assemble_layer(
            mode=mode,
            model=model,
            qs=qs,
            all_qs=all_qs,
            led=ref_led,
            arms=results,
            budget_usd=budget_usd,
            notes=notes,
            qpath=qpath,
        )
        doc = results_doc(
            layer, run_id, started, command or f"l2.run run --mode {mode}", host, port, embedder
        )
        d = write_outputs(doc, out_root, run_id)
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
    ap = argparse.ArgumentParser(prog="crucible-l2")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("questions", help="regenerate questions.yaml from the scenario script")
    r = sub.add_parser("run", help="play the scenario on every arm, answer and score")
    r.add_argument("--mode", choices=("pilot", "full"), default="pilot")
    r.add_argument("--arms", default=",".join(ARMS))
    r.add_argument("--model", default="sonnet")
    r.add_argument(
        "--budget-usd", type=float, default=None, help="stop spending when non-cached calls reach this"
    )
    r.add_argument("--host", default="127.0.0.1")
    r.add_argument("--port", type=int, default=6378)
    r.add_argument("--embedder", choices=("fastembed", "hash"), default="fastembed")
    r.add_argument("--out", type=Path, default=OUT_DIR)
    r.add_argument("--cache", type=Path, default=CACHE_DIR)
    r.add_argument("--ids", default="", help="comma list of question ids (overrides the mode's set)")
    r.add_argument("--keep-graph", action="store_true")
    m = sub.add_parser("merge", help="add an L2 results.json to an existing H results.json")
    m.add_argument("--into", type=Path, required=True)
    m.add_argument("--l2", type=Path, required=True)
    m.add_argument("--write", type=Path, help="output path (default: overwrite --into)")
    a = ap.parse_args(argv)
    if a.cmd == "questions":
        led, qs = generate(tempfile.mkdtemp(prefix="crucible-l2-q-"))
        dump_questions(qs, led, QUESTIONS_PATH)
        print(f"wrote {len(qs)} questions to {QUESTIONS_PATH}")
        return 0
    if a.cmd == "merge":
        base = json.loads(a.into.read_text(encoding="utf-8"))
        doc = json.loads(a.l2.read_text(encoding="utf-8"))
        (a.write or a.into).write_text(
            json.dumps(merge_into(base, doc), indent=2) + "\n", encoding="utf-8", newline="\n"
        )
        return 0
    arms = tuple(x for x in a.arms.split(",") if x)
    bad = [x for x in arms if x not in ARMS]
    if bad:
        raise SystemExit(f"unknown arm(s) {bad}; expected {ARMS}")
    doc, d = run_l2(
        mode=a.mode, arms=arms, model=a.model, budget_usd=a.budget_usd, host=a.host, port=a.port,
        embedder=a.embedder, out_root=a.out, cache_dir=a.cache, log=lambda s: print(s, flush=True),
        command="python -m plexus.crucible.l2.run " + " ".join(argv if argv is not None else sys.argv[1:]),
        question_ids=tuple(x for x in a.ids.split(",") if x) or None, keep_graph=a.keep_graph,
    )  # fmt: skip
    for h in doc["summary"]["headline"]:
        print(h)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
