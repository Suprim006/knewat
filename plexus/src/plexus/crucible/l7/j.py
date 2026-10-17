"""Crucible L7 family J: concurrent session populations (P10 pre-registration, section J).

``python -m plexus.crucible.l7.j run --port 6369 --scale {dev,full} --out <dir> [--arms ...] [--pops ...]
[--layouts ...] [--mixes ...] [--reps N] [--seconds S]``

A *cell* is (arm, population P, tenant layout, mix, repetition). Per cell: fresh tenants (names unique to the cell),
preload (not measured), K = min(8, P) driver processes (``j_worker``) with P/K threads each, closed-loop session
replay (``j_session``), warm-up then measured seconds, then store sizes are recorded and the cell's graphs / files are
deleted. See ``j_session`` (session model, task supply rule) and ``j_arms`` (what each arm does per call).
"""

from __future__ import annotations

import argparse
import itertools
import json
import math
import os
import shutil
import statistics
import subprocess
import sys
import tempfile
import time
import traceback
import uuid
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any

from plexus.crucible.l7 import common
from plexus.crucible.l7.common import DEFAULT_HOST, SEED, DockerSampler, container_for_port, lat_summary
from plexus.crucible.l7.j_arms import ARMS, make_adapter
from plexus.crucible.l7.j_session import MIXES, RECORDED_MIX, load_sequences, preload

LAYOUTS = ("J-team", "J-one")
TEAM_SIZE = 5
ERROR_CLASSES = ("locked", "timeout", "max_pending", "pool", "connection", "unknown_ref", "other")
DOMAIN = ("ok", "no_task", "claim_conflict")
SCALES = {
    "dev": {"pops": (2, 20, 200), "reps": 1, "seconds": 10.0, "warmup": 3.0},
    "full": {"pops": (2, 20, 200, 1000), "reps": 3, "seconds": 30.0, "warmup": 5.0},
}
# dev extras: one J-trav cell per arm at P=20 and the feasibility probe at P=1000 (short)
DEV_EXTRAS = (
    "F-mcp:20:J-team:J-trav",
    "F-service:20:J-team:J-trav",
    "S-file:20:J-team:J-trav",
    "F-mcp:1000:J-one:J-real:10:5",
    "F-service:1000:J-one:J-real:10:5",
    "S-file:1000:J-one:J-real:10:5",
    "F-service:1000:J-team:J-real:10:5",
    "S-file:1000:J-team:J-real:10:5",
)


# ------------------------------------------------------------------------------------------------ cell helpers
def n_tenants(pop: int, layout: str) -> int:
    return 1 if layout == "J-one" else max(1, math.ceil(pop / TEAM_SIZE))


def tenant_of(slot: int, layout: str) -> int:
    return 0 if layout == "J-one" else slot // TEAM_SIZE


def seed_tasks_for(pop: int, layout: str, per_session: int, cap: int) -> int:
    sessions = pop if layout == "J-one" else min(pop, TEAM_SIZE)
    return max(100, min(cap, per_session * sessions))


def _agg_tool(rows: list[list[Any]]) -> dict[str, Any]:
    by_status = Counter(r[3] for r in rows)
    done = [r[2] for r in rows if r[3] in DOMAIN]
    out = {"n": len(rows), "status": dict(by_status), "lat_ms": lat_summary(done)}
    out["lat_all_ms"] = lat_summary([r[2] for r in rows])
    return out


def aggregate(calls: list[list[Any]], seconds: float) -> dict[str, Any]:
    """Throughput, latency and error classes from the raw ``[tool, t_start_rel_s, ms, status]`` list of a cell.

    Times are relative to the start of the measured window. A call belongs to the cell if it **finished** at or after
    that start (the worker only records those; calls that started during warm-up and finished inside the window count,
    as in any closed-loop measurement) and, for throughput, before the window's end. ``late`` = calls that finished
    after the window end (within the grace period): they are in the latency statistics, not in the throughput.
    """

    def end(c: list[Any]) -> float:
        return c[1] + c[2] / 1000

    inwin = [c for c in calls if end(c) >= 0]
    completed = [c for c in inwin if c[3] in DOMAIN and end(c) <= seconds]
    errors = [c for c in inwin if c[3].startswith("err:")]
    by_tool: dict[str, list[list[Any]]] = defaultdict(list)
    for c in inwin:
        by_tool[c[0]].append(c)
    err_cls = Counter(c[3][4:] for c in errors)
    overall_done = [c[2] for c in inwin if c[3] in DOMAIN]
    return {
        "attempted": len(inwin),
        "completed": len(completed),
        "late_finishers": sum(1 for c in inwin if end(c) > seconds),
        "errors": len(errors),
        "throughput_calls_s": round(len(completed) / seconds, 2),
        "throughput_excl_refill_calls_s": round(
            sum(1 for c in completed if c[0] != "create_tasks_refill") / seconds, 2
        ),
        "error_rate": round(len(errors) / len(inwin), 5) if inwin else None,
        "errors_by_class": {k: err_cls.get(k, 0) for k in ERROR_CLASSES}
        | {k: v for k, v in err_cls.items() if k not in ERROR_CLASSES},
        "domain_outcomes": {
            "no_task": sum(1 for c in inwin if c[3] == "no_task"),
            "claim_conflict": sum(1 for c in inwin if c[3] == "claim_conflict"),
        },
        "lat_ms": lat_summary(overall_done),
        "lat_all_ms": lat_summary([c[2] for c in inwin]),
        "per_tool": {t: _agg_tool(rows) for t, rows in sorted(by_tool.items())},
        "tool_counts": dict(Counter(c[0] for c in inwin)),
    }


def mix_shares(tool_counts: dict[str, int]) -> dict[str, float]:
    tot = sum(tool_counts.values()) or 1
    return {k: round(100 * v / tot, 1) for k, v in sorted(tool_counts.items(), key=lambda kv: -kv[1])}


def _commandstats(host: str, port: int) -> dict[str, Any]:
    import redis

    r = redis.Redis(host=host, port=port, decode_responses=True)
    try:
        cs = r.info("commandstats")
        mem = r.info("memory")
    finally:
        r.close()
    g = {k: v for k, v in cs.items() if k.lower().startswith("cmdstat_graph.")}
    return {
        "usec": sum(v["usec"] for v in g.values()),
        "calls": sum(v["calls"] for v in g.values()),
        "failed": sum(v.get("failed_calls", 0) for v in g.values()),
        "by_cmd": {k: {"usec": v["usec"], "calls": v["calls"]} for k, v in g.items()},
        "used_memory_mb": round(mem["used_memory"] / 2**20, 1),
    }


def _server_share(c0: dict[str, Any], c1: dict[str, Any], seconds: float) -> dict[str, Any]:
    usec = c1["usec"] - c0["usec"]
    return {
        "graph_cmd_calls": c1["calls"] - c0["calls"],
        "graph_cmd_failed": c1["failed"] - c0["failed"],
        "graph_cmd_busy_core_s": round(usec / 1e6, 3),
        "graph_cmd_cores_busy": round(
            usec / 1e6 / seconds, 3
        ),  # server-reported time in GRAPH.* / wall (can exceed 1)
        "used_memory_mb_before": c0["used_memory_mb"],
        "used_memory_mb_after": c1["used_memory_mb"],
    }


# ------------------------------------------------------------------------------------------------ one cell
def run_cell(
    arm: str,
    pop: int,
    layout: str,
    mix: str,
    rep: int,
    *,
    host: str,
    port: int,
    seconds: float,
    warmup: float,
    grace: float,
    work: Path,
    tag: str,
    per_session_tasks: int = 25,
    task_cap: int = 5000,
    ready_timeout: float = 600.0,
    log: Any = print,
) -> dict[str, Any]:
    t_cell = time.time()
    cell: dict[str, Any] = {
        "arm": arm, "pop": pop, "layout": layout, "mix": mix, "rep": rep,
        "seconds": seconds, "warmup": warmup, "tag": tag,
    }  # fmt: skip
    k = min(8, pop)
    n_ten = n_tenants(pop, layout)
    seed_tasks = seed_tasks_for(pop, layout, per_session_tasks, task_cap)
    cell.update(procs=k, threads_per_proc=math.ceil(pop / k), tenants=n_ten, seed_tasks_per_tenant=seed_tasks)
    tenants = [f"j{tag}t{i}" for i in range(n_ten)]
    root = work / tag
    root.mkdir(parents=True, exist_ok=True)
    is_f = arm.startswith("F")
    client = None
    if is_f:
        from plexus.crucible.backends.plexus import _client

        client = _client(host, port)
    adapters: list[Any] = []
    procs: list[subprocess.Popen] = []
    logs: list[Any] = []
    stage = "setup"
    try:
        # ---- setup: fresh tenants + preload (parallel over tenants), not measured
        def setup(i: int):
            a = make_adapter(
                arm, tenants[i], host, port, str(root / "sqlite"), client, trav_index=mix == "J-trav"
            )
            return a, preload(a, tenants[i], i + 1000 * pop, seed_tasks)

        t0 = time.time()
        with ThreadPoolExecutor(max_workers=min(8, n_ten)) as ex:
            res = list(ex.map(setup, range(n_ten)))
        adapters = [r[0] for r in res]
        manifests = {tenants[i]: res[i][1] for i in range(n_ten)}
        cell["setup_s"] = round(time.time() - t0, 2)
        # ---- spawn drivers
        stage = "spawn"
        slots_by_proc: list[list[dict[str, Any]]] = [[] for _ in range(k)]
        for s in range(pop):
            slots_by_proc[s % k].append(
                {"slot": s, "tenant": tenants[tenant_of(s, layout)], "k": rep * 100_000 + s}
            )
        rdir = root / "run"
        rdir.mkdir(exist_ok=True)
        cfgs = []
        for i in range(k):
            cfg = {
                "arm": arm, "host": host, "port": port, "root": str(root / "sqlite"), "mix": mix,
                "warmup": warmup, "seconds": seconds, "grace": grace,
                "slots": slots_by_proc[i],
                "manifests": {t: manifests[t] for t in {s["tenant"] for s in slots_by_proc[i]}},
                "ready_path": str(rdir / f"ready{i}.json"),
                "go_path": str(rdir / "go.json"),
                "result_path": str(rdir / f"result{i}.json"),
            }  # fmt: skip
            p = rdir / f"cfg{i}.json"
            p.write_text(json.dumps(cfg), encoding="utf-8")
            cfgs.append(cfg)
            lf = open(rdir / f"log{i}.txt", "w")  # noqa: SIM115
            logs.append(lf)
            procs.append(
                subprocess.Popen(
                    [sys.executable, "-m", "plexus.crucible.l7.j_worker", str(p)], stdout=lf, stderr=lf
                )
            )
        stage = "ready"
        t0 = time.time()
        while not all(Path(c["ready_path"]).exists() for c in cfgs):
            for i, pr in enumerate(procs):
                if pr.poll() is not None and not Path(cfgs[i]["ready_path"]).exists():
                    raise RuntimeError(
                        f"driver {i} exited ({pr.returncode}) before ready: " + _tail(rdir / f"log{i}.txt")
                    )
            if time.time() - t0 > ready_timeout:
                raise TimeoutError(f"drivers not ready after {ready_timeout}s")
            time.sleep(0.1)
        cell["ready_s"] = round(time.time() - t0, 2)
        # ---- go
        stage = "run"
        t_start = time.time() + 1.0
        Path(cfgs[0]["go_path"]).write_text(json.dumps({"t_start": t_start}), encoding="utf-8")
        t_meas, t_end = t_start + warmup, t_start + warmup + seconds
        c0 = c1 = None
        sampler = None
        container = container_for_port(port) if is_f else ""
        _sleep_until(t_meas)
        if is_f:
            c0 = _commandstats(host, port)
            if container:
                sampler = DockerSampler(container)
                sampler.__enter__()
        _sleep_until(t_end)
        if is_f:
            c1 = _commandstats(host, port)
        if sampler is not None:
            sampler.__exit__()
            cell["falkordb_container"] = {"name": container, **sampler.summary()}
        if c0 and c1:
            cell["falkordb_server"] = _server_share(c0, c1, seconds)
        # ---- collect
        stage = "collect"
        results = []
        for i, pr in enumerate(procs):
            rp = Path(cfgs[i]["result_path"])
            try:
                pr.wait(timeout=max(5.0, t_end + grace + 120 - time.time()))
            except subprocess.TimeoutExpired:
                pr.kill()
            if not rp.exists():
                raise RuntimeError(f"driver {i} wrote no result: " + _tail(rdir / f"log{i}.txt"))
            r = json.loads(rp.read_text(encoding="utf-8"))
            if "fatal" in r:
                raise RuntimeError(f"driver {i} failed: {r['fatal']}")
            results.append(r)
        calls = [c for r in results for c in r["calls"]]
        cell.update(aggregate(calls, seconds))
        cell["mix_share_pct"] = mix_shares(cell["tool_counts"])
        cell["sessions_completed"] = sum(r["sessions_completed"] for r in results)
        cell["skipped_complete"] = sum(r["skipped_complete"] for r in results)
        cell["stuck_threads"] = sum(r["stuck_threads"] for r in results)
        errs: dict[str, list[str]] = defaultdict(list)
        for r in results:
            for kk, v in r["err_samples"].items():
                errs[kk].extend(v)
        cell["error_samples"] = {kk: v[:5] for kk, v in errs.items()}
        cell["drivers"] = {
            "cpu_s_total": round(sum(r["resources"]["cpu_s_run"] for r in results), 2),
            "cpu_cores_avg": round(sum(r["resources"]["cpu_s_run"] for r in results) / (warmup + seconds), 2),
            "peak_working_set_mb_each": [
                r["resources"]["at_end"].get("peak_working_set_mb") for r in results
            ],
            "peak_working_set_mb_sum": round(
                sum(r["resources"]["at_end"].get("peak_working_set_mb", 0) for r in results), 1
            ),
            "handles_max": max((r["resources"]["at_end"].get("handles", 0) for r in results), default=0),
            "threads_total": sum(r["threads"] for r in results),
        }
        # ---- store sizes (before deleting)
        stage = "stats"
        sample = adapters[: min(5, len(adapters))]
        cell["store"] = {"tenants_sampled": len(sample), "per_tenant": [a.store_stats() for a in sample]}
        if not is_f:
            cell["store"]["total_bytes_all_tenants"] = sum(
                f.stat().st_size for f in (root / "sqlite").rglob("*") if f.is_file()
            )
        elif c1:
            cell["store"]["falkordb_used_memory_mb"] = c1["used_memory_mb"]
    except Exception as exc:
        cell["failed"] = {
            "stage": stage,
            "error": f"{type(exc).__name__}: {exc}"[:1500],
            "trace": traceback.format_exc()[-1500:],
        }
        log(f"  cell failed at {stage}: {exc}")
    finally:
        for pr in procs:
            if pr.poll() is None:
                pr.kill()
            try:
                pr.wait(timeout=15)  # a killed driver must release its SQLite files before they are deleted
            except subprocess.TimeoutExpired:
                pass
        for lf in logs:
            lf.close()
        t0 = time.time()
        _teardown(adapters, is_f, root, client)
        cell["teardown_s"] = round(time.time() - t0, 2)
        cell["wall_s"] = round(time.time() - t_cell, 2)
    return cell


def _teardown(adapters: list[Any], is_f: bool, root: Path, client: Any) -> None:
    def drop(a: Any) -> None:
        try:
            a.drop()
        except Exception:
            pass

    if adapters:
        with ThreadPoolExecutor(max_workers=min(8, len(adapters))) as ex:
            list(ex.map(drop, adapters))
    for a in adapters:
        try:
            a.close()
        except Exception:
            pass
    if client is not None:
        try:
            client.close()
        except Exception:
            pass
    shutil.rmtree(root, ignore_errors=True)


def _sleep_until(t: float) -> None:
    while (d := t - time.time()) > 0:
        time.sleep(min(d, 0.05))


def _tail(p: Path, n: int = 1500) -> str:
    try:
        return p.read_text(errors="replace")[-n:]
    except OSError:
        return ""


# ------------------------------------------------------------------------------------------------ the grid
def parse_extra(s: str, seconds: float, warmup: float) -> dict[str, Any]:
    p = s.split(":")
    return {
        "arm": p[0], "pop": int(p[1]), "layout": p[2], "mix": p[3],
        "seconds": float(p[4]) if len(p) > 4 else seconds,
        "warmup": float(p[5]) if len(p) > 5 else warmup,
    }  # fmt: skip


def plan(args: argparse.Namespace) -> list[dict[str, Any]]:
    cells: list[dict[str, Any]] = []
    for rep, pop, layout, mix, arm in itertools.product(
        range(args.reps), args.pops, args.layouts, args.mixes, args.arms
    ):
        cells.append({"arm": arm, "pop": pop, "layout": layout, "mix": mix, "rep": rep,
                      "seconds": args.seconds, "warmup": args.warmup})  # fmt: skip
    for e in args.extra:
        c = parse_extra(e, args.seconds, args.warmup)
        c.update(rep=0, extra=True)
        cells.append(c)
    return cells


def estimate_s(cells: list[dict[str, Any]], setup_s: float = 20.0, teardown_s: float = 10.0) -> float:
    return sum(c["seconds"] + c["warmup"] + 3.0 + setup_s + teardown_s for c in cells)


def _median(xs: list[float]) -> float | None:
    xs = [x for x in xs if x is not None]
    return round(statistics.median(xs), 2) if xs else None


def build_report(doc: dict[str, Any]) -> str:
    cells = doc["cells"]
    groups: dict[tuple, list[dict[str, Any]]] = defaultdict(list)
    for c in cells:
        groups[(c["pop"], c["layout"], c["mix"], c["arm"], c.get("extra", False))].append(c)
    lines = [
        f"# L7 family J: concurrent session populations ({doc['run']['id']})",
        "",
        f"scale `{doc['params']['scale']}`; measured {doc['params']['seconds']} s after {doc['params']['warmup']} s warm-up; "
        f"reps {doc['params']['reps']}; seed {SEED}; embedder `hash` (F); FTS5 (S). "
        "Median of repetitions, [min..max] in brackets. Throughput = completed tool calls/s (ok + no_task + claim_conflict).",
        "",
        "## Cells",
        "",
        "| P | layout | mix | arm | reps ok/run | tput calls/s (excl. refill) | p50 ms | p99 ms | errors | err classes | FalkorDB cpu% mean/max | "
        "FalkorDB mem MiB | GRAPH.* cores busy | driver cpu cores | driver peak WS MB |",
        "|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|",
    ]
    for key in sorted(groups, key=lambda k: (k[4], k[0], k[1], k[2], ARMS.index(k[3]))):
        gs = groups[key]
        ok = [g for g in gs if "failed" not in g]
        pop, layout, mix, arm, extra = key
        if not ok:
            f = gs[0]["failed"]
            lines.append(
                f"| {pop} | {layout} | {mix} | {arm} | 0/{len(gs)} | FAILED at {f['stage']}: {f['error'][:120]} |"
                + " |" * 10
            )
            continue
        tp = [g["throughput_calls_s"] for g in ok]
        errs: Counter = Counter()
        for g in ok:
            errs.update({k: v for k, v in g["errors_by_class"].items() if v})
        cont = [g.get("falkordb_container", {}) for g in ok]
        srv = [g.get("falkordb_server", {}) for g in ok]
        cpu = [c.get("cpu_pct_mean") for c in cont if c.get("cpu_pct_mean") is not None]
        cpumax = [c.get("cpu_pct_max") for c in cont if c.get("cpu_pct_max") is not None]
        mem = [c.get("mem_mib_max") for c in cont if c.get("mem_mib_max") is not None]
        busy = [s.get("graph_cmd_cores_busy") for s in srv if s]
        lines.append(
            f"| {pop} | {layout} | {mix} | {arm} | {len(ok)}/{len(gs)} | {_med_rng(tp)} | "
            f"{_med_rng([g['lat_ms']['p50'] for g in ok])} | {_med_rng([g['lat_ms']['p99'] for g in ok])} | "
            f"{sum(g['errors'] for g in ok)}/{sum(g['attempted'] for g in ok)} | "
            f"{', '.join(f'{k}={v}' for k, v in errs.items()) or '-'} | "
            f"{_med(cpu)}/{_med(cpumax)} | {_med(mem)} | {_med(busy)} | "
            f"{_med([g['drivers']['cpu_cores_avg'] for g in ok])} | {_med([g['drivers']['peak_working_set_mb_sum'] for g in ok])} |"
        )
    lines += ["", "## Per-tool latency, p50/p99 ms (median over repetitions)", ""]
    tools = sorted({t for c in cells if "per_tool" in c for t in c["per_tool"]})
    seen_ctx = sorted({(k[0], k[1], k[2], k[4]) for k in groups}, key=lambda k: (k[3], k[0], k[1], k[2]))
    for pop, layout, mix, extra in seen_ctx:
        lines += [
            f"### P={pop} {layout} {mix}{' (extra)' if extra else ''}",
            "",
            "| tool | " + " | ".join(ARMS) + " |",
            "|---|" + "---|" * len(ARMS),
        ]
        for t in tools:
            row = []
            any_ = False
            for arm in ARMS:
                ok = [
                    g
                    for g in groups.get((pop, layout, mix, arm, extra), [])
                    if "failed" not in g and t in g.get("per_tool", {})
                ]
                if not ok:
                    row.append("-")
                    continue
                any_ = True
                row.append(
                    f"{_med([g['per_tool'][t]['lat_ms']['p50'] for g in ok])}/{_med([g['per_tool'][t]['lat_ms']['p99'] for g in ok])} "
                    f"(n={sum(g['per_tool'][t]['n'] for g in ok)})"
                )
            if any_:
                lines.append(f"| {t} | " + " | ".join(row) + " |")
        lines.append("")
    lines += ["## Realized mix (share of attempted calls, first repetition)", ""]
    for key in sorted(groups, key=lambda k: (k[4], k[0], k[1], k[2], ARMS.index(k[3]))):
        ok = [g for g in groups[key] if "failed" not in g]
        if ok:
            lines.append(f"* P={key[0]} {key[1]} {key[2]} {key[3]}: {ok[0]['mix_share_pct']}")
    lines += ["", "## Recorded mix (pre-registration)", "", f"{RECORDED_MIX}", "", "## Failures", ""]
    failed = [c for c in cells if "failed" in c]
    lines += [
        f"* {c['arm']} P={c['pop']} {c['layout']} {c['mix']} rep {c['rep']}: {c['failed']['stage']}: {c['failed']['error']}"
        for c in failed
    ] or ["none"]
    s_shared = "S-shared (optional, J-team): not run."
    lines += ["", s_shared, ""]
    return "\n".join(lines)


def _med(xs: list[float]) -> str:
    m = _median(xs)
    return "-" if m is None else f"{m:g}"


def _med_rng(xs: list[float]) -> str:
    xs = [x for x in xs if x is not None]
    if not xs:
        return "-"
    return f"{statistics.median(xs):g}" + (f" [{min(xs):g}..{max(xs):g}]" if len(xs) > 1 else "")


def make_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(prog="python -m plexus.crucible.l7.j")
    sub = ap.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("run", help="run the family J grid")
    r.add_argument("--host", default=DEFAULT_HOST)
    r.add_argument("--port", type=int, required=True)
    r.add_argument("--scale", choices=sorted(SCALES), default="dev")
    r.add_argument("--out", type=Path, default=None)
    r.add_argument("--arms", nargs="+", choices=ARMS, default=list(ARMS))
    r.add_argument("--pops", nargs="+", type=int, default=None)
    r.add_argument("--layouts", nargs="+", choices=LAYOUTS, default=list(LAYOUTS))
    r.add_argument("--mixes", nargs="+", choices=MIXES, default=None)
    r.add_argument("--reps", type=int, default=None)
    r.add_argument("--seconds", type=float, default=None, help="measured seconds per cell")
    r.add_argument("--warmup", type=float, default=None)
    r.add_argument(
        "--grace", type=float, default=30.0, help="how long to wait for in-flight calls after the window"
    )
    r.add_argument("--seed-tasks-per-session", type=int, default=25)
    r.add_argument("--seed-tasks-cap", type=int, default=5000)
    r.add_argument(
        "--extra", nargs="*", default=None, help="arm:pop:layout:mix[:seconds[:warmup]] extra cells"
    )
    r.add_argument("--workdir", type=Path, default=None, help="scratch dir for SQLite files / driver configs")
    r.add_argument("--extra-only", action="store_true", help="run only the --extra cells (skip the grid)")
    r.add_argument("--plan-only", action="store_true", help="print the cell list and the duration estimate")
    r.add_argument(
        "--flushall", action="store_true", help="FLUSHALL the FalkorDB at the end (only your own container!)"
    )
    return ap


def main(argv: list[str] | None = None) -> int:
    args = make_parser().parse_args(argv)
    sc = SCALES[args.scale]
    args.pops = args.pops or list(sc["pops"])
    args.reps = args.reps if args.reps is not None else sc["reps"]
    args.seconds = args.seconds if args.seconds is not None else sc["seconds"]
    args.warmup = args.warmup if args.warmup is not None else sc["warmup"]
    args.mixes = args.mixes or (["J-real"] if args.scale == "dev" else list(MIXES))
    if args.extra is None:
        args.extra = list(DEV_EXTRAS) if args.scale == "dev" else []
    cells = plan(args)
    if args.extra_only:
        cells = [c for c in cells if c.get("extra")]
    if args.plan_only:
        for c in cells:
            print(c)
        print(
            f"{len(cells)} cells, ~{estimate_s(cells) / 60:.0f} min (assuming 20 s setup + 10 s teardown per cell)"
        )
        return 0
    started = time.time()
    out = args.out or common.DEMO
    work = Path(args.workdir or tempfile.mkdtemp(prefix="j-"))
    work.mkdir(parents=True, exist_ok=True)
    doc = common.envelope(
        "j", args.host, args.port, started, "python -m plexus.crucible.l7.j " + " ".join(sys.argv[1:])
    )
    doc["params"] = {
        "scale": args.scale, "arms": args.arms, "pops": args.pops, "layouts": args.layouts, "mixes": args.mixes,
        "reps": args.reps, "seconds": args.seconds, "warmup": args.warmup, "grace": args.grace,
        "seed_tasks_per_session": args.seed_tasks_per_session, "seed_tasks_cap": args.seed_tasks_cap,
        "extra": args.extra, "recorded_mix": RECORDED_MIX, "sequences": {k: len(v) for k, v in load_sequences().items()},
        "falkordb_pool": os.environ.get("CRUCIBLE_POOL", "512"),
    }  # fmt: skip
    doc["cells"] = []
    run_tag = uuid.uuid4().hex[:5]
    for i, c in enumerate(cells):
        print(
            f"[{i + 1}/{len(cells)}] {c['arm']} P={c['pop']} {c['layout']} {c['mix']} rep {c['rep']} ({c['seconds']}s)",
            flush=True,
        )
        cell = run_cell(
            c["arm"], c["pop"], c["layout"], c["mix"], c["rep"],
            host=args.host, port=args.port, seconds=c["seconds"], warmup=c["warmup"], grace=args.grace,
            work=work, tag=f"{run_tag}c{i}", per_session_tasks=args.seed_tasks_per_session, task_cap=args.seed_tasks_cap,
        )  # fmt: skip
        if c.get("extra"):
            cell["extra"] = True
        doc["cells"].append(cell)
        if "failed" not in cell:
            print(
                f"    {cell['throughput_calls_s']} calls/s p50 {cell['lat_ms']['p50']} p99 {cell['lat_ms']['p99']} ms "
                f"errors {cell['errors']}/{cell['attempted']} { ({k: v for k, v in cell['errors_by_class'].items() if v}) }",
                flush=True,
            )
        # partial results survive a crash of the harness
        (work / "partial.json").write_text(json.dumps(doc, default=str), encoding="utf-8")
    d = common.write(doc, out, build_report(doc))
    print(f"wrote {d}")
    shutil.rmtree(work, ignore_errors=True)
    if args.flushall:
        import redis

        r = redis.Redis(host=args.host, port=args.port)
        r.flushall()
        r.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
