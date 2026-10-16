"""Assemble the L8 round-A results (results.json + report.md) from the scored runs, the audits and the probe.

python -m plexus.crucible.l8.report --out demo_data/crucible/l8 [--audit] [--probe-seed 20261017]
"""

from __future__ import annotations

import argparse
import json
import shutil
import time
from pathlib import Path
from typing import Any

from plexus.crucible import environment
from plexus.crucible.l8.run import OUT_DEFAULT, git_state
from plexus.crucible.l8.score import common_task_rate, redump_p_steps, score_all
from plexus.crucible.util import iso_utc, run_stamp

ARM_NAME = {"P": "P (Plexus)", "B1": "B1 (SQLite)", "B0p": "B0′ (Claude Code files)"}


def pct(x: float | None) -> str:
    return "n/a" if x is None else f"{100 * x:.1f}%"


def headline(pooled: dict[str, Any]) -> dict[str, Any]:
    """§12, filled in mechanically: the sentence that applies is chosen by the pre-stated separation rule."""
    a, t = pooled["arms"], pooled["tests"]
    if not all(k in a for k in ("P", "B1", "B0p")):
        return {"sentences": ["incomplete: not every round-A arm has runs"]}
    X, X2, Y = a["B1"]["stale_act"]["pooled"], a["B0p"]["stale_act"]["pooled"], a["P"]["stale_act"]["pooled"]
    A, A2, B = (a["B1"]["step_repetition"]["pooled"], a["B0p"]["step_repetition"]["pooled"],
                a["P"]["step_repetition"]["pooled"])  # fmt: skip
    pz, bz = a["P"]["tokens"]["pooled_per_correct_action"], a["B1"]["tokens"]["pooled_per_correct_action"]
    pw, bw = (
        a["P"]["tokens"]["pooled_weighted_per_correct_action"],
        a["B1"]["tokens"]["pooled_weighted_per_correct_action"],
    )
    Z = round(pz / bz, 2) if pz and bz else None
    W = round(pw / bw, 2) if pw and bw else None
    sep_b1 = t["P_vs_B1_stale_act"]["separated"]
    sep_b0 = t["P_vs_B0p_stale_act"]["separated"]
    rep_b1 = t["P_vs_B1_step_repetition"]["separated"]
    rep_b0 = t["P_vs_B0p_step_repetition"]["separated"]
    n = len(a["P"]["seeds"])
    out = []
    if sep_b1 and Y is not None and X is not None and Y < X:
        out.append(
            f"With the same agents, prompts and fault timeline, Plexus cut stale actions from {pct(X)} (B1) / {pct(X2)} "
            f"(B0′) to {pct(Y)}, and step repetition from {pct(A)} (B1) to {pct(B)}, at {Z}× the tokens per correct "
            f"action ({W}× billing-weighted); the Postgres arm with the same tool design (B3) was not run in round A, so "
            "whether the design or the graph accounts for the difference is not settled."
        )
    elif sep_b1:
        out.append(
            f"Plexus had MORE stale actions than SQLite ({pct(Y)} vs {pct(X)}, separated, n = {n} seeds each) and used {Z}× "
            f"the tokens per correct action ({W}× billing-weighted): a loss on the headline metric."
        )
    else:
        out.append(
            f"Plexus did not reduce stale actions versus SQLite ({pct(Y)} vs {pct(X)}, n = {n} seeds each; not separated by "
            f"the pre-stated rule) and used {Z}× the tokens per correct action ({W}× billing-weighted); its remaining "
            "advantages are the ones L2/L6 established (deterministic, $0 provenance answers)."
        )
    out.append(
        f"Versus unmodified Claude Code with its own memory files (B0′): stale actions {pct(Y)} (P) vs {pct(X2)} (B0′), "
        + ("separated." if sep_b0 else "not separated by the pre-stated rule (a tie).")
    )
    if not rep_b1 and not rep_b0:
        out.append(
            "Step repetition, missing completion and reasoning–action mismatch were not changed by the memory backend "
            f"(step repetition P {pct(B)}, B1 {pct(A)}, B0′ {pct(A2)}; no separation by the pre-stated rule)."
        )
    else:
        out.append(
            f"Step repetition: P {pct(B)}, B1 {pct(A)}, B0′ {pct(A2)} (P vs B1 separated: {rep_b1}; P vs B0′ separated: {rep_b0})."
        )
    if Z is not None and Z > 2:
        out.append(
            f"Cost: P used {Z}× B1's tokens per correct action (> 2×): published as a loss on cost (§6.6 criterion)."
        )
    elif Z is not None and Z <= 1.5:
        out.append(
            f"Cost: P used {Z}× B1's tokens per correct action (≤ 1.5×, within the §6.6 'worth it' criterion)."
        )
    elif Z is not None:
        out.append(
            f"Cost: P used {Z}× B1's tokens per correct action (between the 1.5× and 2× criteria of §6.6)."
        )
    return {"sentences": out, "X_B1": X, "X_B0p": X2, "Y_P": Y, "A_B1": A, "A_B0p": A2, "B_P": B, "Z": Z, "W": W,
            "separated": {"stale_P_B1": sep_b1, "stale_P_B0p": sep_b0, "rep_P_B1": rep_b1, "rep_P_B0p": rep_b0}}  # fmt: skip


def table(pooled: dict[str, Any], runs: list[dict[str, Any]], audits: dict[str, Any]) -> str:
    a = pooled["arms"]
    arms = [x for x in ("P", "B1", "B0p") if x in a]
    w = ["| Metric | " + " | ".join(ARM_NAME[x] for x in arms) + " |", "|---|" + "---|" * len(arms)]

    def row(name: str, fn: Any) -> None:
        w.append(f"| {name} | " + " | ".join(str(fn(a[x], x)) for x in arms) + " |")

    def seeds(v: dict[str, Any], f: Any = pct) -> str:
        vals = ", ".join(f(x) if isinstance(x, (int, float)) else str(x) for x in v["values"])
        return f"{vals}"

    row("runs (seeds)", lambda m, x: len(m["seeds"]))
    row("tasks done / 16 (per seed)", lambda m, x: seeds(m["tasks_done"], str))
    row("turns (per seed)", lambda m, x: seeds(m["turns"], str))
    row(
        "**stale-act rate, pooled** [Wilson 95%]",
        lambda m, x: (
            f"**{pct(m['stale_act']['pooled'])}** ({m['stale_act']['stale']}/{m['stale_act']['n']}) {m['stale_act']['wilson95']}"
        ),
    )
    row("stale-act rate per seed", lambda m, x: seeds(m["stale_act"]["seed_rates"]))
    row("stale-act, dependent-only (pooled)", lambda m, x: pct(m["stale_act"]["dependent_pooled"]))
    row("stale-act, artifact files only (pooled)", lambda m, x: pct(m["stale_act"]["artifact_files_pooled"]))
    row(
        "stale facts live in store at end (per seed)",
        lambda m, x: seeds(m["stale_act"]["stale_facts_live_at_end"], str),
    )
    row(
        "time-to-notice L1 median turns (per seed)",
        lambda m, x: seeds(m["time_to_notice"]["level1_median"], str),
    )
    row(
        "time-to-notice L2 median turns (per seed)",
        lambda m, x: seeds(m["time_to_notice"]["level2_median"], str),
    )
    row(
        "notice censored L1 / L2 (of cases)",
        lambda m, x: (
            f"{m['time_to_notice']['level1_censored']} / {m['time_to_notice']['level2_censored']} (of {m['time_to_notice']['cases']})"
        ),
    )
    row(
        "**step repetition (R1+R2+R3), pooled**",
        lambda m, x: f"**{pct(m['step_repetition']['pooled'])}** ({m['step_repetition']['events']})",
    )
    row("step repetition per seed", lambda m, x: seeds(m["step_repetition"]["seed_rates"]))
    row("missing completion C1+C2+C3 (per seed, of 16)", lambda m, x: seeds(m["missing_completion"], str))
    row(
        "mismatch M1 / M2 / M3 (sum)",
        lambda m, x: f"{m['mismatch']['M1']} / {m['mismatch']['M2']} / {m['mismatch']['M3']}",
    )
    row(
        "tokens per correct action, pooled (raw)",
        lambda m, x: (
            f"{m['tokens']['pooled_per_correct_action']:,}"
            if m["tokens"]["pooled_per_correct_action"]
            else "n/a"
        ),
    )
    row(
        "tokens per correct action, pooled (billing-weighted)",
        lambda m, x: (
            f"{m['tokens']['pooled_weighted_per_correct_action']:,}"
            if m["tokens"]["pooled_weighted_per_correct_action"]
            else "n/a"
        ),
    )
    row("cost USD (all seeds)", lambda m, x: f"${m['tokens']['cost_usd']:.2f}")
    if audits:
        row(
            "audit Q1/Q2/Q3 correct (per seed)",
            lambda m, x: ", ".join(audits.get(x, {}).get(str(s), "-") for s in m["seeds"]),
        )
    return "\n".join(w)


def robustness(out: Path) -> dict[str, Any]:
    """Post-hoc variants (amendments 2-3), pooled per arm. Never the headline."""
    ms: dict[str, list[dict[str, Any]]] = {}
    for mj in sorted((out / "runs").glob("*/*/metrics.json")):
        m = json.loads(mj.read_text(encoding="utf-8"))
        ms.setdefault(m["arm"], []).append(m)
    res: dict[str, Any] = {}
    for arm, lst in ms.items():
        r: dict[str, Any] = {}
        for var in ("excl_x2_brief_write", "excl_deleted_only", "excl_both"):
            k = sum(m["stale_act"]["post_hoc"][var]["stale"] for m in lst)
            n = sum(m["stale_act"]["post_hoc"][var]["n"] for m in lst)
            r[var] = {
                "stale": k,
                "n": n,
                "rate": round(k / n, 4) if n else None,
                "seed_rates": [
                    m["stale_act"]["post_hoc"][var]["rate"] for m in sorted(lst, key=lambda x: x["seed"])
                ],
            }
        res[arm] = r
    # common tasks: per seed, tasks in which every arm has at least one scored action
    by_seed: dict[int, dict[str, dict[str, Any]]] = {}
    for arm, lst in ms.items():
        for m in lst:
            by_seed.setdefault(m["seed"], {})[arm] = m
    common: dict[str, list[dict[str, Any]]] = {}
    for seed, arms in by_seed.items():
        if len(arms) < 3:
            continue
        tasks = set.intersection(*({a["task"] for a in m["actions"]} for m in arms.values()))
        for arm, m in arms.items():
            common.setdefault(arm, []).append({"seed": seed, **common_task_rate([m], tasks)})
    for arm, rows in common.items():
        k, n = sum(x["stale"] for x in rows), sum(x["n"] for x in rows)
        res[arm]["common_tasks"] = {
            "stale": k,
            "n": n,
            "rate": round(k / n, 4) if n else None,
            "seed_rates": [x["rate"] for x in sorted(rows, key=lambda x: x["seed"])],
        }
    return res


def robust_table(rb: dict[str, Any]) -> str:
    arms = [x for x in ("P", "B1", "B0p") if x in rb]
    w = ["", "Post-hoc robustness variants of the stale-act rate (amendments 2-3; descriptive, not the headline):", "",
         "| Variant | " + " | ".join(ARM_NAME[x] for x in arms) + " |", "|---|" + "---|" * len(arms)]  # fmt: skip
    for var, label in (("excl_x2_brief_write", "excluding the X2 brief-mandated store write"),
                       ("excl_deleted_only", "excluding actions whose only stale tokens are of deleted functions"),
                       ("excl_both", "excluding both"),
                       ("common_tasks", "only tasks every arm of the seed reached")):  # fmt: skip
        cells = []
        for a in arms:
            v = rb[a].get(var)
            cells.append(f"{pct(v['rate'])} ({v['stale']}/{v['n']})" if v else "n/a")
        w.append(f"| {label} | " + " | ".join(cells) + " |")
    return "\n".join(w)


def render(doc: dict[str, Any]) -> str:
    p = doc["pooled"]
    w = ["# Crucible L8 round A: long-horizon memory under live change (P, B1, B0′ × seeds)\n",
         f"Run `{doc['run']['id']}`, code `{doc['git']['short']}` (dirty: {doc['git']['dirty']}), model alias `sonnet`, "
         f"prompts `{doc['config']['prompt_version']}`. Spend: ${doc['run']['cost_usd']:.2f} (notional, subscription).\n",
         "## Headline\n", *[f"- {s}" for s in doc["headline"]["sentences"]], "",
         "## Metrics (MAST rows measure three narrow signatures, not the taxonomy categories)\n", doc["table"], "",
         "## Separation tests (exact permutation on seed-level rates; separated = p ≤ 0.05 and ranges do not overlap)\n"]  # fmt: skip
    for k, v in p["tests"].items():
        w.append(
            f"- {k}: p = {v['perm_p']}, ranges overlap = {v['ranges_overlap']}, **separated = {v['separated']}**"
        )
    w.append("\n## Honesty\n")
    w += [f"- {h}" for h in doc["honesty"]]
    return "\n".join(w) + "\n"


HONESTY = [
    "Round A only (P, B1, B0′); B0 and B3 (Postgres with the same tool design) were not run, so the design-vs-graph question of §5.5 is open.",
    "n = 5 seeds per arm (if fewer, the table says so); claude -p has no seed, the seeds fix the fault schedule only.",
    "Synthetic sentinels, synthetic repo, one scenario family, one model (Sonnet via the owner's subscription; costs are notional), one machine.",
    "MAST rows are three deterministic signatures per mode, not Cemri et al.'s annotated categories.",
    "Implementation choices the plan left open are listed in amendment 1 of docs/research/L8_LONG_HORIZON_OUTCOMES.md.",
]


def assemble(
    out: Path, *, audit: bool, probe_seed: int | None, host: str, port: int, started: float, command: str
) -> Path:
    for rj in sorted((out / "runs").glob("*/P/run.json")):
        if "wrote_steps" not in json.loads((rj.parent / "store_dump.json").read_text(encoding="utf-8")):
            redump_p_steps(rj.parent, host, port)  # amendment 3: provenance is matched on the Step number
    scored = score_all(out)
    robust = robustness(out)
    runs = []
    for rj in sorted((out / "runs").glob("*/*/run.json")):
        r = json.loads(rj.read_text(encoding="utf-8"))
        runs.append({k: r[k] for k in ("seed", "arm", "status", "error", "tenant", "wall_s", "kills_fired", "commits_not_landed",
                                       "hook_failed_commits", "git")} | {"cost_usd": r["claude"]["total_cost_usd"],
                                                                          "processes": r["claude"]["claude_processes"]})  # fmt: skip
    audits: dict[str, dict[str, str]] = {}
    audit_rows = []
    probe = None
    if audit:
        from plexus.crucible.l8.audit import audit_run

        for rj in sorted((out / "runs").glob("*/*/run.json")):
            rd = rj.parent
            res = audit_run(rd, out / "seeds" / rd.parent.name, host, port)
            audits.setdefault(rd.name, {})[rd.parent.name] = "/".join(
                "✓" if res[q]["correct"] else "✗" for q in ("Q1", "Q2", "Q3")
            )
            audit_rows.append({"seed": int(rd.parent.name), "arm": rd.name, "score": res["score"],
                               "Q1": {k: res["Q1"][k] for k in ("count_ok", "probes_ok", "earliest_ok", "correct", "probes_right", "truth_count")},
                               "Q2": {k: res["Q2"][k] for k in ("truth", "answer", "correct")},
                               "Q3": {k: res["Q3"][k] for k in ("truth", "answer", "correct")},
                               "reader_cost": round(sum(c["cost"] for c in res["reader_calls"]), 4)})  # fmt: skip
    if probe_seed:
        from plexus.crucible.l8.audit import run_probe

        rp = json.loads((out / "runs" / str(probe_seed) / "P" / "run.json").read_text(encoding="utf-8"))
        rb = json.loads((out / "runs" / str(probe_seed) / "B1" / "run.json").read_text(encoding="utf-8"))
        sent = json.loads((out / "seeds" / str(probe_seed) / "sentinels.json").read_text(encoding="utf-8"))
        probe = run_probe(rp, rb, sent, host, port)
    cost = sum(r["cost_usd"] for r in runs) + sum(x["reader_cost"] for x in audit_rows)
    if probe:
        cost += sum(x["cost"] for x in probe["rows"])
    doc = {
        "schema": "crucible-l8/1", "kind": "roundA",
        "run": {"id": run_stamp() + "-roundA", "started_at": iso_utc(started), "finished_at": iso_utc(), "command": command,
                "cost_usd": round(cost, 4)},
        "git": git_state(), "environment": environment.collect(host, port, "hash"),
        "config": {"prompt_version": "l8-v1", "arms": ["P", "B1", "B0p"], "model": "sonnet", "max_turns": 25,
                   "seeds": sorted({r["seed"] for r in runs})},
        "runs": runs, "pooled": {k: v for k, v in scored.items() if k != "runs"}, "robustness_post_hoc": robust,
        "audit": audit_rows, "probe": probe,
    }  # fmt: skip
    doc["headline"] = headline(doc["pooled"])
    doc["table"] = table(doc["pooled"], runs, audits) + "\n" + robust_table(robust)
    doc["honesty"] = HONESTY
    d = out / doc["run"]["id"]
    d.mkdir(parents=True, exist_ok=True)
    (d / "results.json").write_text(
        json.dumps(doc, indent=1, default=str) + "\n", encoding="utf-8", newline="\n"
    )
    (d / "report.md").write_text(render(doc), encoding="utf-8", newline="\n")
    shutil.copyfile(d / "results.json", out / "latest-roundA.json")
    return d


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="crucible-l8-report")
    ap.add_argument("--out", type=Path, default=OUT_DEFAULT)
    ap.add_argument("--audit", action="store_true")
    ap.add_argument("--probe-seed", type=int, default=None)
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=6365)
    a = ap.parse_args(argv)
    d = assemble(a.out, audit=a.audit, probe_seed=a.probe_seed, host=a.host, port=a.port, started=time.time(),
                 command="python -m plexus.crucible.l8.report " + " ".join(argv or []))  # fmt: skip
    print((d / "report.md").read_text(encoding="utf-8"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
