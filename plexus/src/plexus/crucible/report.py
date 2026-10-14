"""Render ``report.md`` from a results dict (pure function: results in, markdown out)."""

from __future__ import annotations

from collections import defaultdict
from typing import Any


def _table(header: list[str], rows: list[list[str]]) -> str:
    out = ["| " + " | ".join(header) + " |", "|" + "|".join("---" for _ in header) + "|"]
    out += ["| " + " | ".join(r) + " |" for r in rows]
    return "\n".join(out)


def _cell(r: dict[str, Any]) -> str:
    if r["unsupported"]:
        return "n/a (unsupported)"
    if r["passed"]:
        return f"pass ({r['runs_passed']}/{r['runs']})"
    bad = ", ".join(f"{k}={v}" for k, v in r["violations_total"].items() if v)
    return f"**FAIL** {r['runs_passed']}/{r['runs']} ({bad})"


def _lat(op: dict[str, Any]) -> str:
    if not op.get("n"):
        return "-"
    return f"{op['p50_ms']:g} / {op['p95_ms']:g} / {op['p99_ms']:g}"


def _srv(op: dict[str, Any]) -> str:
    if "server_p50_ms" not in op:
        return "-"
    return f"{op['server_p50_ms']:g} / {op['server_p95_ms']:g} / {op['server_p99_ms']:g}"


def render(res: dict[str, Any]) -> str:
    run, env, cfg = res["run"], res["environment"], res["config"]
    out: list[str] = []
    w = out.append
    w(f"# Crucible report `{run['id']}`")
    w("")
    w(
        f"- Started {run['started_at']}, finished {run['finished_at']} ({run['duration_s']} s). "
        f"Layers: {', '.join(run['layers'])}. **{'QUICK run (CI sizing): not the published figures' if run['quick'] else 'Full run'}.**"
    )
    w(f"- Command: `{run['command']}`; commit `{env.get('git_commit') or 'unknown'}`.")
    where = (
        "inside Docker (same compose network as FalkorDB)"
        if env["in_docker"]
        else "**outside Docker** (host port forward adds latency)"
    )
    w(
        f"- Ran {where}; {env['platform']}, Python {env['python']}, {env['cpu_count']} CPUs; embedder `{env['embedder']}`."
    )
    fk = env["falkordb"]
    gc = ", ".join(f"{k}={v}" for k, v in (fk.get("graph_config") or {}).items())
    w(
        f"- FalkorDB: Redis {fk.get('redis_version', '?')} at `{fk['host']}:{fk['port']}`; effective module config: {gc or 'unavailable'}."
    )
    if fk.get("falkordb_args_env"):
        w(f"- `FALKORDB_ARGS` = `{fk['falkordb_args_env']}`")
    if "seeds" in cfg:
        w(f"- Seeds: {cfg['seeds']} ({len(cfg['seeds'])} repetitions per test case).")
    w("")
    w("## Arms")
    w("")
    w(
        _table(
            ["Arm", "Name", "Represents", "How it works", "Tenant isolation"],
            [
                [a, i["label"], i["represents"], i["description"], i["isolation"]]
                for a, i in res["arms"].items()
            ],
        )
    )
    w("")
    summary = res.get("summary", {})
    if summary.get("headline"):
        w("## Headline (generated from the numbers below)")
        w("")
        for line in summary["headline"]:
            w(f"- {line}")
        w("")
    layers = res["layers"]
    if "L1" in layers:
        _l1(layers["L1"], res["arms"], w)
    if "L4" in layers:
        _l4(layers["L4"], w)
    if "ablation" in layers:
        _ablation(layers["ablation"], w)
    for rr in run.get("reruns", []):
        w("## Re-runs (cells replaced after the main run)")
        w("")
        w(f"- {rr['at']}, commit `{rr.get('git_commit') or 'unknown'}`: {rr['reason']}")
        w(
            f"- Replaced cells: {', '.join(rr['cells'])}. The original results are kept in `results.json` under `run.reruns[*].superseded`."
        )
        for sup in rr["superseded"]:
            res_ = sup["result"] or {}
            if "violations_total" in res_:
                what = (
                    f"{res_['runs_passed']}/{res_['runs']} runs passed, violations {res_['violations_total']}"
                )
            elif "error_count" in res_:
                what = f"{res_['error_count']} errors ({'; '.join(res_.get('errors', []))}), {res_['ops']} ops completed"
            else:
                what = "no earlier result"
            w(f"  - was {sup['cell']}: {what}")
        w("")
    w("## Limits and honesty notes")
    w("")
    for h in res.get("honesty", []):
        w(f"- {h}")
    w("")
    w("## Reproduce")
    w("")
    w("```bash")
    w(
        "docker compose -p plexus-bench --profile bench run --rm crucible all      # full L1 + L4 + ablation, inside the network"
    )
    w(
        "uv run crucible all --quick                                               # CI-sized, against a local FalkorDB"
    )
    w("```")
    return "\n".join(out) + "\n"


def _l1(layer: dict[str, Any], arms: dict[str, Any], w) -> None:
    arm_ids = list(layer["arms"])
    w("## L1: correctness under concurrency")
    w("")
    w(
        "Violation counts are summed over every run (no averaging). `pass (n/n)` = all n runs had 0 violations."
    )
    w("")
    rows = []
    for t, spec in layer["tests"].items():
        cells = []
        for a in arm_ids:
            r = layer["arms"][a]["tests"].get(t)
            cells.append(_cell(r) if r else "-")
        rows.append([f"**{t}** {spec['title']}", spec["bar"], *cells])
    w(_table(["Test", "Pass bar", *arm_ids], rows))
    w("")
    for t, spec in layer["tests"].items():
        w(f"### {t}: {spec['title']}")
        w("")
        w(f"Metric: {spec['metric']}. Bar: {spec['bar']}.")
        w("")
        det = _l1_detail(t, arm_ids, layer)
        if det:
            w(det)
            w("")
    unsupp = sorted(
        {(a, t) for a in arm_ids for t, r in layer["arms"][a]["tests"].items() if r["unsupported"]}
    )
    if unsupp:
        w("Unsupported (answered by an LLM in L2): " + ", ".join(f"{a}/{t}" for a, t in unsupp))
        w("")


def _runs(layer: dict[str, Any], arm: str, test: str) -> list[dict[str, Any]]:
    return layer["arms"][arm]["tests"][test].get("runs_detail", [])


def _l1_detail(t: str, arm_ids: list[str], layer: dict[str, Any]) -> str:
    if t == "C1":
        workers = sorted({r["params"]["workers"] for a in arm_ids for r in _runs(layer, a, t)})
        rows = []
        for a in arm_ids:
            cells = []
            for n in workers:
                rs = [r for r in _runs(layer, a, t) if r["params"]["workers"] == n]
                v = defaultdict(int)
                for r in rs:
                    for k, x in r["violations"].items():
                        v[k] += x
                ops = sorted(r["metrics"].get("ops_per_s", 0) for r in rs)
                med = ops[len(ops) // 2] if ops else 0
                cells.append(f"{v['double_claims']}/{v['lost_updates']}/{v['never_claimed']} @ {med:g} ops/s")
            rows.append([a, *cells])
        return "Double claims / lost updates / never claimed (all runs), median ops/s:\n\n" + _table(
            ["Arm", *[f"{n} workers" for n in workers]], rows
        )
    if t == "C2":
        rows = []
        for a in arm_ids:
            rs = _runs(layer, a, t)
            if not rs:
                continue
            mx = max((r["metrics"].get("reclaim_delay_ms_max", -1) for r in rs), default=-1)
            bar = rs[0]["metrics"].get("reclaim_bar_ms", "")
            orph = sum(r["violations"].get("orphaned_tasks", 0) for r in rs)
            rows.append([a, f"{mx:g}", f"{bar:g}" if bar != "" else "", str(orph)])
        return _table(
            [
                "Arm",
                "Slowest reclaim after kill (ms)",
                "Bar: lease + 1 heartbeat (ms)",
                "Orphaned tasks (all runs)",
            ],
            rows,
        )
    if t == "C7":
        rows = []
        kinds: dict[str, dict[str, list[int]]] = {}
        for a in arm_ids:
            rs = _runs(layer, a, t)
            if not rs:
                continue
            seq = sum(r["metrics"].get("misses_sequential", 0) for r in rs)
            conc = sum(r["metrics"].get("misses_concurrent", 0) for r in rs)
            pairs = sum(r["metrics"].get("pairs", 0) for r in rs)
            fm = sum(r["violations"].get("false_merges", 0) for r in rs)
            rows.append(
                [
                    a,
                    f"{seq}/{pairs} ({seq / pairs:.0%})" if pairs else "-",
                    f"{conc}/{pairs} ({conc / pairs:.0%})" if pairs else "-",
                    str(fm),
                ]
            )
            k = kinds.setdefault(a, {})
            for r in rs:
                for kind, v in r["details"].get("misses_by_kind", {}).items():
                    cur = k.setdefault(kind, [0, 0])
                    cur[0] += v["pairs"]
                    cur[1] += v["missed"]
        text = (
            "Paraphrase pairs stored as two facts instead of one (miss), sequential vs concurrent writers:\n\n"
            + _table(
                ["Arm", "Misses, sequential", "Misses, concurrent", "False merges of distinct facts"], rows
            )
        )
        krows = [
            [
                a,
                *[
                    f"{kinds[a].get(k, [0, 0])[1]}/{kinds[a].get(k, [0, 0])[0]}"
                    for k in ("punctuation", "light", "heavy")
                ],
            ]
            for a in kinds
        ]
        return (
            text
            + "\n\nMisses by paraphrase kind (missed/pairs, sequential):\n\n"
            + _table(["Arm", "punctuation / case", "light rewording", "heavy rewording"], krows)
        )
    rows = []
    for a in arm_ids:
        r = layer["arms"][a]["tests"].get(t)
        if not r:
            continue
        v = ", ".join(f"{k}={x}" for k, x in r["violations_total"].items()) or "-"
        rows.append([a, v])
    return _table(["Arm", "Violations (all runs)"], rows)


def _l4(layer: dict[str, Any], w) -> None:
    w("## L4: performance and scale")
    w("")
    for n in layer.get("notes", []):
        w(f"- {n}")
    w("")
    claim = layer["claim_sweep"]
    arms = list(dict.fromkeys(p["arm"] for p in claim))
    workers = sorted({p["workers"] for p in claim})

    def find(pts: list[dict[str, Any]], arm: str, n: int) -> dict[str, Any] | None:
        return next((p for p in pts if p["arm"] == arm and p["workers"] == n), None)

    w("### Throughput (claim + heartbeat + complete operations per second)")
    w("")
    w(
        _table(
            ["Arm", *[f"{n} workers" for n in workers]],
            [[a, *[_get(find(claim, a, n), "throughput_ops_s") for n in workers]] for a in arms],
        )
    )
    w("")
    for op in ("claim", "heartbeat", "complete"):
        w(f"### {op}: client latency p50 / p95 / p99 (ms)")
        w("")
        w(
            _table(
                ["Arm", *[f"{n} workers" for n in workers]],
                [[a, *[_lat((find(claim, a, n) or {}).get(op, {})) for n in workers]] for a in arms],
            )
        )
        w("")
        srv = [
            a for a in arms if any("server_p50_ms" in (find(claim, a, n) or {}).get(op, {}) for n in workers)
        ]
        if srv:
            w(f"{op}: server-side `run_time_ms` p50 / p95 / p99 (ms), summed over the call's queries:")
            w("")
            w(
                _table(
                    ["Arm", *[f"{n} workers" for n in workers]],
                    [[a, *[_srv((find(claim, a, n) or {}).get(op, {})) for n in workers]] for a in srv],
                )
            )
            w("")
    errs = sum(p["error_count"] for p in claim)
    w(f"Errors across all claim points: {errs}.")
    w("")
    recall = layer["recall_sweep"]
    if recall:
        rarms = list(dict.fromkeys(p["arm"] for p in recall))
        rworkers = sorted({p["workers"] for p in recall})
        w("### recall: client latency p50 / p95 / p99 (ms) and throughput")
        w("")
        w(
            f"{recall[0]['facts']} facts seeded; each recall embeds the query (arms with embeddings) and, for the Plexus/SQLite arms, records the recall."
        )
        w("")
        w(
            _table(
                ["Arm", *[f"{n} workers" for n in rworkers]],
                [
                    [
                        a,
                        *[
                            _lat((find(recall, a, n) or {}).get("recall", {}))
                            + " @ "
                            + _get(find(recall, a, n), "throughput_ops_s")
                            for n in rworkers
                        ],
                    ]
                    for a in rarms
                ],
            )
        )
        w("")
        rsrv = [
            a
            for a in rarms
            if any("server_p50_ms" in (find(recall, a, n) or {}).get("recall", {}) for n in rworkers)
        ]
        if rsrv:
            w("recall: server-side `run_time_ms` p50 / p95 / p99 (ms):")
            w("")
            w(
                _table(
                    ["Arm", *[f"{n} workers" for n in rworkers]],
                    [
                        [a, *[_srv((find(recall, a, n) or {}).get("recall", {})) for n in rworkers]]
                        for a in rsrv
                    ],
                )
            )
            w("")
    probe = layer.get("embedder_probe")
    if probe:
        w("### Embedder alone (no database): the ceiling for recall")
        w("")
        w(
            "Recall embeds the query with one shared bge-small instance whose calls are serialised. With W closed-loop "
            "workers, latency ~ W / throughput (Little's law), so once that instance saturates, p50 grows linearly with W "
            "whatever the store behind it does. Compare with the server-side `run_time_ms` above (about 10 ms)."
        )
        w("")
        w(
            _table(
                ["Workers", "Embeds/s", "p50 / p95 / p99 (ms)"],
                [[str(p["workers"]), f"{p['throughput_ops_s']:g}", _lat(p)] for p in probe],
            )
        )
        w("")
    tenants = layer["tenant_sweep"]
    if tenants:
        tarms = list(dict.fromkeys(p["arm"] for p in tenants))
        counts = sorted({p["tenants"] for p in tenants})
        w(
            f"### One graph vs N tenant graphs (write ceiling), {tenants[0]['workers']} workers, claim + complete"
        )
        w("")
        rows = []
        for a in tarms:
            cells = []
            for n in counts:
                p = next((p for p in tenants if p["arm"] == a and p["tenants"] == n), None)
                cells.append(
                    "-"
                    if p is None
                    else f"{p['throughput_ops_s']:g} ops/s, claim p99 {p['claim'].get('p99_ms', '-')} ms"
                )
            rows.append([a, *cells])
        w(_table(["Arm", *[f"{n} tenant{'s' if n > 1 else ''}" for n in counts]], rows))
        w("")


def _get(p: dict[str, Any] | None, key: str) -> str:
    return "-" if p is None else f"{p[key]:g}"


def _ablation(ab: dict[str, Any], w) -> None:
    w("## Ablation (D-001): cut the edges, see what breaks")
    w("")
    s = ab["summary"]
    w(
        f"Deleted relationship types: {', '.join(ab['stripped_relationship_types'])} "
        f"(edges removed: {ab['edges_deleted']}). "
        f"{s['broken_by_ablation']}/{s['capabilities_needing_edges']} capabilities that need those edges break; "
        f"{s['controls_unaffected']}/{s['controls']} control capabilities (no stripped edge involved) are unaffected."
    )
    w("")
    rows = []
    for c in ab["capabilities"]:
        rows.append(
            [
                c["capability"],
                c["needs"],
                "pass" if c["intact"]["passed"] else "FAIL",
                "pass" if c["ablated"]["passed"] else "**FAIL**",
                c["ablated"]["detail"],
            ]
        )
    w(_table(["Capability", "Needs edge", "Intact", "Ablated", "Ablated detail"], rows))
    w("")
    w(
        "L1 re-run with the edges stripped as soon as they are written (`P-abl`) next to the intact Plexus arm:"
    )
    w("")
    rr = []
    for arm, tests in ab["l1_rerun"].items():
        for t, r in tests.items():
            rr.append([arm, t, _cell(r)])
    w(_table(["Arm", "Test", "Result"], rr))
    w("")
