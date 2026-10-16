"""Crucible L7 family I: atomic multi-entity writes (SQL transactions vs FalkorDB one-statement / MULTI-EXEC / product).

    python -m plexus.crucible.l7.i run --port 6368 --scale {dev,full} --out <dir> [--parts I1,I2,I3,I4,I5] [--arms ...]
    python -m plexus.crucible.l7.i merge --out <dir> <results.json> ...      (merge parts into one doc)

Arms, items and the partial-detection rule are described in ``i_arms``. Port 6368 / container plexus-db-68 only.
"""

from __future__ import annotations

import argparse
import inspect
import json
import random
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import uuid
from pathlib import Path
from typing import Any

from plexus.crucible.l7 import common
from plexus.crucible.l7.i_arms import (
    ARMS,
    ITEMS,
    SLUG,
    Arm,
    FProduct,
    ids,
    make_arm,
    sql_statements,
    stale_flags,
    valid_tenant,
)  # fmt: skip

SCALES = {
    "dev": {
        "kills": 6,
        "i2_n": 60,
        "i3_kills": 2,
        "i4_ops": 10,
        "i4_w": (4, 10),
        "i4b_rounds": 60,
        "i5_n": 60,
    },
    "full": {
        "kills": 200,
        "i2_n": 400,
        "i3_kills": 20,
        "i4_ops": 50,
        "i4_w": (20, 200),
        "i4b_rounds": 500,
        "i5_n": 400,
    },
}
I2_ARMS = (
    "S-txn", "S-auto", "F-product", "F-multi", "F-multi-cas-first", "F-multiexec", "F-multiexec-err",
    "F-1stmt-first", "F-1stmt-last",
)  # fmt: skip


def log(msg: str) -> None:
    print(time.strftime("%H:%M:%S"), msg, flush=True)


def r3(n: int) -> float | None:
    """Rule of three: 95% upper bound of a rate after 0 events in n trials (as a fraction)."""
    return round(3 / n, 6) if n > 0 else None


def tally(states: dict[str, str]) -> dict[str, int]:
    out = {"complete": 0, "partial": 0, "absent": 0}
    for s in states.values():
        out[s] += 1
    return out


# ------------------------------------------------------------------------------------------------ the writer process
def writer(arm_name: str, host: str, port: int, tenant: str, root: str, tag: str) -> None:
    arm = make_arm(arm_name, host, port, tenant, root)
    arm.connect()
    print("ready", flush=True)
    n = 0
    while True:
        co = f"{tag}.{n}"
        task, v = arm.new_task(co)
        print(json.dumps({"t": "intent", "co": co, "task": task, "v": v}), flush=True)
        ok = arm.closeout(co, task, v, v)
        print(json.dumps({"t": "ack", "co": co, "ok": ok}), flush=True)
        n += 1


def _spawn_writer(arm: str, host: str, port: int, tenant: str, root: str, tag: str) -> subprocess.Popen:
    cmd = [
        sys.executable, "-m", "plexus.crucible.l7.i", "writer", "--arm", arm, "--host", host, "--port", str(port),
        "--tenant", tenant, "--root", root, "--tag", tag,
    ]  # fmt: skip
    return subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True)


def new_world(arm_name: str, host: str, port: int, root: str, run: str) -> Arm:
    tenant = valid_tenant(SLUG[arm_name], run)
    arm = make_arm(arm_name, host, port, tenant, root)
    arm.setup_world()
    return arm


def _crash_result(
    arm: Arm, prefix: str, intents: dict[str, dict[str, Any]], acked: dict[str, bool]
) -> dict[str, Any]:
    arm.connect()
    states, items = arm.states(prefix, intents)
    unknown = sorted(
        set(states) - set(intents)
    )  # entities of a co whose intent line was cut (should be none)
    for co in unknown:
        intents[co] = {"task": ids(co)["task"], "v": 1}
    ack_set = set(acked)
    inflight = [co for co in intents if co not in ack_set]
    missing: dict[str, int] = {}
    for co, s in states.items():
        if s == "partial":
            for it in set(ITEMS) - items[co]:
                missing[it] = missing.get(it, 0) + 1
    res: dict[str, Any] = {
        "started": len(intents),
        "acknowledged": len(ack_set),
        "acknowledged_rejected": sum(1 for v in acked.values() if not v),
        "totals": tally(states),
        "partial": sum(1 for s in states.values() if s == "partial"),
        "lost_acknowledged": sum(1 for co in ack_set if states.get(co) != "complete"),
        "partial_among_acknowledged": sum(1 for co in ack_set if states.get(co) == "partial"),
        "inflight_at_kill": len(inflight),
        "inflight_complete": sum(1 for co in inflight if states.get(co) == "complete"),
        "inflight_partial": sum(1 for co in inflight if states.get(co) == "partial"),
        "inflight_absent": sum(1 for co in inflight if states.get(co) == "absent"),
        "entities_without_intent": len(unknown),
        "partial_missing_items": dict(sorted(missing.items(), key=lambda kv: -kv[1])),
    }
    res["partial_rate_per_acknowledged"] = round(res["partial"] / max(1, res["acknowledged"]), 6)
    return res


# ------------------------------------------------------------------------------------------------ I1
def run_i1_arm(arm_name: str, kills: int, host: str, port: int, root: str, seed: int) -> dict[str, Any]:
    run = uuid.uuid4().hex[:6]
    arm = new_world(arm_name, host, port, root, run)
    rng = random.Random(seed)
    intents: dict[str, dict[str, Any]] = {}
    acked: dict[str, bool] = {}
    t0 = time.time()
    kill_delays: list[float] = []
    for k in range(kills):
        tag = f"{SLUG[arm_name]}{run}k{k}"
        p = _spawn_writer(arm_name, host, port, arm.tenant, root, tag)
        lines: list[str] = []
        ready = threading.Event()

        def pump(proc: subprocess.Popen = p, out: list[str] = lines, ev: threading.Event = ready) -> None:
            assert proc.stdout is not None
            for ln in proc.stdout:
                if ln.strip() == "ready":
                    ev.set()
                else:
                    out.append(ln)

        th = threading.Thread(target=pump, daemon=True)
        th.start()
        if not ready.wait(90):
            p.kill()
            raise RuntimeError(f"writer {tag} never became ready")
        d = rng.uniform(0.0, 0.4)
        kill_delays.append(d)
        time.sleep(d)
        p.kill()  # TerminateProcess on Windows
        p.wait()
        th.join(5)
        for ln in lines:
            try:
                m = json.loads(ln)
            except json.JSONDecodeError:
                continue  # cut by the kill: not acknowledged
            if m["t"] == "intent":
                intents[m["co"]] = {"task": m["task"], "v": m["v"]}
            elif m["t"] == "ack":
                acked[m["co"]] = bool(m["ok"])
        if (k + 1) % 20 == 0:
            log(f"I1 {arm_name}: {k + 1}/{kills} kills, {len(acked)} acknowledged, {len(intents)} started")
    run_s = time.time() - t0
    res = _crash_result(arm, SLUG[arm_name] + run, intents, acked)
    res.update({"arm": arm_name, "kills": kills, "mean_kill_delay_s": round(sum(kill_delays) / max(1, kills), 3),
                "run_s": round(run_s, 1), "tenant": arm.tenant})  # fmt: skip
    res["partial_rate_per_kill"] = round(res["partial"] / max(1, kills), 4)
    if res["partial"] == 0:
        res["rule_of_three_95_upper_per_kill"] = r3(kills)
        res["rule_of_three_95_upper_per_acknowledged"] = r3(res["acknowledged"])
    if res["lost_acknowledged"] == 0:
        res["lost_rule_of_three_95_upper_per_acknowledged"] = r3(res["acknowledged"])
    arm.close()
    arm.drop()
    return res


# ------------------------------------------------------------------------------------------------ I2
def run_i2_arm(arm_name: str, n: int, host: str, port: int, root: str, seed: int) -> dict[str, Any]:
    run = uuid.uuid4().hex[:6]
    arm = new_world(arm_name, host, port, root, run)
    arm.connect()
    flags = stale_flags(seed, n)
    intents: dict[str, dict[str, Any]] = {}
    result_ok: dict[str, bool] = {}
    errors = 0
    lat: list[float] = []
    for i in range(n):
        co = f"{SLUG[arm_name]}{run}.{i}"
        task, v = arm.new_task(co)
        intents[co] = {"task": task, "v": v}
        expected = v - 1 if flags[i] else v
        t0 = time.perf_counter()
        try:
            result_ok[co] = arm.closeout(co, task, v, expected)
        except Exception as exc:  # noqa: BLE001
            errors += 1
            result_ok[co] = False
            log(f"I2 {arm_name}: closeout error {type(exc).__name__}: {str(exc)[:100]}")
        lat.append((time.perf_counter() - t0) * 1000)
    states, items = arm.states(SLUG[arm_name] + run, intents)
    stale = [co for co, f in zip(intents, flags, strict=True) if f]
    fresh = [co for co, f in zip(intents, flags, strict=True) if not f]
    res = {
        "arm": arm_name,
        "closeouts": n,
        "stale": len(stale),
        "stale_partial": sum(1 for co in stale if states[co] == "partial"),
        "stale_absent": sum(1 for co in stale if states[co] == "absent"),
        "stale_complete": sum(1 for co in stale if states[co] == "complete"),
        "stale_task_mutated": sum(1 for co in stale if "task_done" in items[co]),
        "stale_leftover_items_total": sum(len(items[co]) for co in stale),
        "fresh": len(fresh),
        "fresh_complete": sum(1 for co in fresh if states[co] == "complete"),
        "fresh_partial": sum(1 for co in fresh if states[co] == "partial"),
        "fresh_absent": sum(1 for co in fresh if states[co] == "absent"),
        "client_reported_rejected": sum(1 for co in stale if not result_ok[co]),
        "client_reported_ok_on_fresh": sum(1 for co in fresh if result_ok[co]),
        "errors": errors,
        "latency_ms": common.lat_summary(lat),
        "tenant": arm.tenant,
    }
    res["partial_total"] = res["stale_partial"] + res["fresh_partial"]
    if res["stale_partial"] == 0 and res["stale"]:
        res["stale_partial_rule_of_three_95_upper"] = r3(res["stale"])
    if arm_name in ("F-product", "F-multi"):
        res["note"] = "no compensation: as the client convention / product is"
    if isinstance(arm, FProduct):
        res["queries_per_closeout_last"] = arm.queries
    arm.close()
    arm.drop()
    return res


# ------------------------------------------------------------------------------------------------ I3
def _docker(*args: str, timeout: int = 120) -> subprocess.CompletedProcess:
    return subprocess.run(["docker", *args], capture_output=True, text=True, timeout=timeout)


def wait_ready(host: str, port: int, timeout_s: float = 240.0) -> float:
    """Block until PING answers PONG (not LOADING). Returns seconds waited; raises if the server never comes back."""
    import redis

    t0 = time.time()
    while time.time() - t0 < timeout_s:
        try:
            r = redis.Redis(host=host, port=port, socket_timeout=3)
            if r.ping():
                r.close()
                return time.time() - t0
        except (redis.exceptions.RedisError, OSError):
            pass
        time.sleep(0.25)
    raise RuntimeError(f"server on {host}:{port} not ready after {timeout_s}s")


def bug_reports(container: str) -> int:
    """Number of Redis crash reports ("REDIS BUG REPORT START") in the container's log so far."""
    r = _docker("logs", container)
    return (r.stdout + r.stderr).count("REDIS BUG REPORT START")


def recover(host: str, port: int, container: str, graph: str, max_bounces: int = 4) -> dict[str, Any]:
    """After ``docker start``: wait for PONG, then run one query on ``graph``; a hung or crashed server is killed and restarted.

    A Redis that segfaulted keeps its container "Up" but answers nothing (observed in the dev run), so a health
    query with a socket timeout is the only reliable readiness check. Returns timing and the number of extra bounces.
    """
    import redis

    t0 = time.time()
    bounces = 0
    while True:
        try:
            wait_ready(host, port, 120.0)
            r = redis.Redis(host=host, port=port, socket_timeout=15)
            r.execute_command("GRAPH.RO_QUERY", graph, "RETURN 1")
            r.close()
            return {"ready_after_s": round(time.time() - t0, 2), "extra_bounces": bounces, "up": True}
        except (redis.exceptions.RedisError, OSError, RuntimeError):
            bounces += 1
            if bounces > max_bounces:
                return {"ready_after_s": round(time.time() - t0, 2), "extra_bounces": bounces, "up": False}
            _docker("kill", "-s", "KILL", container)
            time.sleep(1)
            _docker("start", container)


def run_i3_arm(
    arm_name: str, kills: int, host: str, port: int, root: str, seed: int, writers: int = 4
) -> dict[str, Any]:
    container = common.container_for_port(port)
    assert container == "plexus-db-68", "I3 may only kill plexus-db-68"
    run = uuid.uuid4().hex[:6]
    arm = new_world(arm_name, host, port, root, run)
    rng = random.Random(seed)
    intents: dict[str, dict[str, Any]] = {}
    acked: dict[str, bool] = {}
    lock = threading.Lock()
    restarts: list[dict[str, Any]] = []
    prefix = SLUG[arm_name] + run
    failed = 0
    bugs_start = bugs_seen = bug_reports(container)
    for k in range(kills):
        stop = threading.Event()
        ready = threading.Barrier(writers + 1)
        errs: list[str] = []

        def work(
            w: int,
            k: int = k,
            stop: threading.Event = stop,
            ready: threading.Barrier = ready,
            errs: list = errs,
        ) -> None:
            a = None
            try:
                a = make_arm(arm_name, host, port, arm.tenant, root)
                a.connect()
            except Exception as exc:  # noqa: BLE001
                errs.append(f"connect: {type(exc).__name__}")
            try:
                ready.wait(120)
            except threading.BrokenBarrierError:
                return
            if a is None:
                return
            n = 0
            while not stop.is_set():
                co = f"{prefix}k{k}w{w}.{n}"
                n += 1
                try:
                    task, v = a.new_task(co)
                    with lock:
                        intents[co] = {"task": task, "v": v}
                    ok = a.closeout(co, task, v, v)
                    with lock:
                        acked[co] = ok
                except Exception as exc:  # noqa: BLE001  (connection lost: the reply was not received)
                    errs.append(type(exc).__name__)
                    return

        ths = [threading.Thread(target=work, args=(w,), daemon=True) for w in range(writers)]
        for t in ths:
            t.start()
        ready.wait(120)
        time.sleep(rng.uniform(0.4, 1.6))
        t_kill = time.time()
        kr = _docker("kill", "-s", "KILL", container)
        stop.set()
        for t in ths:
            t.join(90)
        t_start = time.time()
        sr = _docker("start", container)
        rec = recover(host, port, container, arm.gname)
        wait_s, up = rec["ready_after_s"], rec["up"]
        bugs_now = bug_reports(container)
        st = _docker("inspect", "-f", "{{.State.Running}} {{.State.ExitCode}}", container).stdout.strip()
        restarts.append({
            "k": k, "kill_rc": kr.returncode, "start_rc": sr.returncode, "ready_after_s": round(wait_s, 2),
            "up": up, "state": st, "writer_errors": sorted(set(errs)), "kill_to_start_s": round(t_start - t_kill, 2),
            "extra_bounces": rec["extra_bounces"], "new_bug_reports": bugs_now - bugs_seen,
        })  # fmt: skip
        bugs_seen = bugs_now
        if not up:
            failed += 1
            log(f"I3 {arm_name}: SERVER DID NOT COME BACK after kill {k} ({st}); stopping this arm")
            break
        log(f"I3 {arm_name}: kill {k + 1}/{kills}: {len(acked)} acked, restart ready in {wait_s:.1f}s")
    res = None
    for _attempt in range(
        3
    ):  # the server may crash again right after the last restart; recover and retry the read
        try:
            res = _crash_result(arm, prefix, intents, acked)
            break
        except Exception as exc:  # noqa: BLE001
            log(f"I3 {arm_name}: verification read failed ({type(exc).__name__}); recovering the server")
            _docker("kill", "-s", "KILL", container)
            time.sleep(1)
            _docker("start", container)
            recover(host, port, container, arm.gname)
    assert res is not None, "could not read the store back after 3 recoveries"
    res["server_bug_reports_arm_total"] = bug_reports(container) - bugs_start
    res.update({
        "arm": arm_name, "kills_requested": kills, "kills_done": len(restarts), "writers": writers,
        "server_failed_to_restart": failed,
        "server_bug_reports": sum(r["new_bug_reports"] for r in restarts),
        "server_extra_bounces": sum(r["extra_bounces"] for r in restarts),
        "restart_ready_s": common.lat_summary([r["ready_after_s"] for r in restarts if r["up"]]),
        "restarts": restarts, "tenant": arm.tenant,
    })  # fmt: skip
    if res["partial"] == 0:
        res["rule_of_three_95_upper_per_kill"] = r3(len(restarts))
    if res["lost_acknowledged"] == 0:
        res["lost_rule_of_three_95_upper_per_acknowledged"] = r3(res["acknowledged"])
    arm.close()
    arm.drop()
    return res


# ------------------------------------------------------------------------------------------------ I5
def _glue_lines(cls: type, method: str = "closeout") -> int:
    return common.code_lines(inspect.getsource(getattr(cls, method)))


def run_i5(n: int, host: str, port: int, root: str, i1: dict | None, i2: dict | None) -> dict[str, Any]:
    from plexus.crucible.l7.i_arms import QDIR, FOneStatement, SqliteArm

    stmt_f = common.code_lines((QDIR / "f_1stmt_first.cypher").read_text(encoding="utf-8"))
    sql_txt = "\n".join(
        s for s in (QDIR / "s_closeout.sql").read_text(encoding="utf-8").splitlines() if s.strip() != ";;"
    )
    out: dict[str, Any] = {
        "lines_statement_text": {"F-1stmt": stmt_f, "S-txn": common.code_lines(sql_txt)},
        "lines_python_glue_closeout_method": {
            "F-1stmt": _glue_lines(FOneStatement),
            "S-txn": _glue_lines(SqliteArm),
        },
        "statements_per_closeout": {"F-1stmt": 1, "S-txn": len(sql_statements()) + 2},
        "n_per_writer": n,
    }
    for arm_name in ("F-1stmt", "S-txn"):
        run = uuid.uuid4().hex[:6]
        world = new_world(arm_name, host, port, root, run)
        cell: dict[str, Any] = {}
        for writers in (1, 8):
            lat: list[float] = []
            errors: list[str] = []
            rts: list[int] = []
            lk = threading.Lock()

            def work(
                w: int,
                writers: int = writers,
                arm_name: str = arm_name,
                run: str = run,
                world: Arm = world,
                lat: list = lat,
                errors: list = errors,
                rts: list = rts,
                lk: threading.Lock = lk,
            ) -> None:
                a = make_arm(arm_name, host, port, world.tenant, root)
                a.connect()
                mine: list[float] = []
                for i in range(n):
                    co = f"{SLUG[arm_name]}{run}w{writers}x{w}.{i}"
                    task, v = a.new_task(co)
                    t0 = time.perf_counter()
                    try:
                        a.closeout(co, task, v, v)
                    except Exception as exc:  # noqa: BLE001
                        with lk:
                            errors.append(f"{type(exc).__name__}: {str(exc)[:60]}")
                        continue
                    mine.append((time.perf_counter() - t0) * 1000)
                    rts.append(a.round_trips)
                a.close()
                with lk:
                    lat.extend(mine)

            t0 = time.perf_counter()
            ths = [threading.Thread(target=work, args=(w,)) for w in range(writers)]
            for t in ths:
                t.start()
            for t in ths:
                t.join()
            wall = time.perf_counter() - t0
            cell[f"writers_{writers}"] = {
                "latency_ms": common.lat_summary(lat),
                "errors": len(errors),
                "error_kinds": sorted(set(errors))[:5],
                "closeouts_per_s": round(len(lat) / wall, 1),
                "round_trips_per_closeout": rts[0] if rts else None,
            }
        out[arm_name] = cell
        world.drop()
    out["embedded_vs_server"] = (
        "S-txn: embedded (in-process SQLite, no network); F-1stmt: server (Docker port-forward)"
    )
    for name, src in (("i1", i1), ("i2", i2)):
        if src:
            out[f"{name}_outcomes"] = {
                a: src.get(a) for a in ("S-txn", "F-1stmt", "F-1stmt-first", "F-1stmt-last") if a in src
            }
    return out


# ------------------------------------------------------------------------------------------------ report
def fmt(x: Any) -> str:
    return "-" if x is None else str(x)


def report_md(doc: dict[str, Any]) -> str:
    L = [
        f"# Crucible L7 family I: atomic multi-entity writes ({doc.get('scale')}, run {doc['run']['id']})",
        "",
    ]
    p = doc.get("parts", {})
    if "I1" in p:
        L += ["## I1 writer crash (hard kill 0-400 ms after ready)", "",
              "| arm | kills | started | acked | partial | lost acked | in flight at kill (complete/partial/absent) | partial per ack | r3 95% upper per kill |",
              "|---|---|---|---|---|---|---|---|---|"]  # fmt: skip
        for a, r in p["I1"]["arms"].items():
            L.append(
                f"| {a} | {r['kills']} | {r['started']} | {r['acknowledged']} | {r['partial']} | {r['lost_acknowledged']} | "
                f"{r['inflight_at_kill']} ({r['inflight_complete']}/{r['inflight_partial']}/{r['inflight_absent']}) | "
                f"{r['partial_rate_per_acknowledged']} | {fmt(r.get('rule_of_three_95_upper_per_kill'))} |"
            )
        L.append("")
    if "I2" in p:
        L += ["## I2 logical abort (25% stale versions)", "",
              "| arm | closeouts | stale | stale partial | stale absent | task mutated | leftover items | fresh complete | fresh partial | errors |",
              "|---|---|---|---|---|---|---|---|---|---|"]  # fmt: skip
        for a, r in p["I2"]["arms"].items():
            L.append(
                f"| {a} | {r['closeouts']} | {r['stale']} | {r['stale_partial']} | {r['stale_absent']} | {r['stale_task_mutated']} | "
                f"{r['stale_leftover_items_total']} | {r['fresh_complete']}/{r['fresh']} | {r['fresh_partial']} | {r['errors']} |"
            )
        L.append("")
    if "I3" in p:
        L += ["## I3 database-server crash (`docker kill -s KILL`, 4 writers)", "",
              "| arm | kills | started | acked | partial | lost acked | in flight (complete/partial/absent) | restart ready s p50 | failed restarts |",
              "|---|---|---|---|---|---|---|---|---|"]  # fmt: skip
        for a, r in p["I3"]["arms"].items():
            L.append(
                f"| {a} | {r['kills_done']} | {r['started']} | {r['acknowledged']} | {r['partial']} | {r['lost_acknowledged']} | "
                f"{r['inflight_at_kill']} ({r['inflight_complete']}/{r['inflight_partial']}/{r['inflight_absent']}) | "
                f"{r['restart_ready_s']['p50']} | {r['server_failed_to_restart']} |"
            )
        if "aof_repro" in p["I3"]:
            L += ["", "AOF replay reproduction: " + json.dumps(p["I3"]["aof_repro"].get("summary", {}))]
        L.append("")
    if "I4" in p:
        L += ["## I4a lost update (one counter)", "",
              "| backend | mode | W | ops/writer | attempted | acked | final | lost (acked-final) | errors | retries |",
              "|---|---|---|---|---|---|---|---|---|---|"]  # fmt: skip
        for r in p["I4"]["a"]:
            L.append(
                f"| {r['backend']} | {r['mode']} | {r['W']} | {r['ops']} | {r['attempted']} | {r['acked']} | {r['final']} | "
                f"{r['lost_acked']} | {r['errors']} | {r['retries']} |"
            )
        L += ["", "## I4b write skew", "",
              "| backend | mode | think ms | rounds | violations | errors | claimed-both | claimed-none |",
              "|---|---|---|---|---|---|---|---|"]  # fmt: skip
        for r in p["I4"]["b"]:
            L.append(
                f"| {r['backend']} | {r['mode']} | {r['think_ms']} | {r['rounds']} | {r['violations']} | {r['errors']} | {r['both']} | {r['none']} |"
            )
        L.append("")
    if "I5" in p:
        r = p["I5"]
        L += ["## I5 single-statement sufficiency", "",
              f"* statement lines: {r['lines_statement_text']}; python glue (closeout method): {r['lines_python_glue_closeout_method']}",
              f"* statements per close-out: {r['statements_per_closeout']}", "",
              "| arm | writers | p50 ms | p99 ms | closeouts/s | round trips | errors |", "|---|---|---|---|---|---|---|"]  # fmt: skip
        for a in ("F-1stmt", "S-txn"):
            for w in (1, 8):
                c = r[a][f"writers_{w}"]
                L.append(
                    f"| {a} | {w} | {c['latency_ms']['p50']} | {c['latency_ms']['p99']} | {c['closeouts_per_s']} | {c['round_trips_per_closeout']} | {c['errors']} |"
                )
        L.append(f"\n{r['embedded_vs_server']}")
    return "\n".join(L) + "\n"


# ------------------------------------------------------------------------------------------------ CLI
def _dump(doc: dict[str, Any], a: argparse.Namespace, final: bool = False) -> Path | None:
    out = Path(a.out)
    if final:
        return common.write(doc, out, report_md(doc))
    out.mkdir(parents=True, exist_ok=True)  # progress copy so a crash does not lose finished arms
    (out / f"partial-{doc['run']['id']}.json").write_text(
        json.dumps(doc, indent=1, default=str), encoding="utf-8"
    )
    return None


def cmd_run(a: argparse.Namespace) -> int:
    sc = SCALES[a.scale]
    parts = [x.strip().upper() for x in a.parts.split(",")]
    doc = common.envelope("i", a.host, a.port, time.time(), " ".join(sys.argv))
    doc.update({"scale": a.scale, "parts": {}, "db_port": a.port, "i4_busy_timeout_ms": 10000})
    root = tempfile.mkdtemp(prefix="l7i-")
    container = common.container_for_port(a.port)
    doc["server_bug_reports_at_start"] = bug_reports(container)
    arms = a.arms.split(",") if a.arms else list(ARMS)
    try:
        if "I1" in parts:
            doc["parts"]["I1"] = {"kills_per_arm": sc["kills"], "arms": {}}
            for i, arm in enumerate(arms):
                log(f"I1 start {arm}")
                doc["parts"]["I1"]["arms"][arm] = run_i1_arm(
                    arm, sc["kills"], a.host, a.port, root, common.SEED + 100 + i
                )
                _dump(doc, a)
        if "I2" in parts:
            doc["parts"]["I2"] = {"closeouts_per_arm": sc["i2_n"], "stale_fraction": 0.25, "arms": {}}
            for arm in I2_ARMS:
                log(f"I2 start {arm}")
                doc["parts"]["I2"]["arms"][arm] = run_i2_arm(
                    arm, sc["i2_n"], a.host, a.port, root, common.SEED + 200
                )
                _dump(doc, a)
        if "I3" in parts:
            doc["parts"]["I3"] = {"kills_per_arm": sc["i3_kills"], "arms": {}}
            for i, arm in enumerate(("F-1stmt", "F-multi")):
                log(f"I3 start {arm}")
                doc["parts"]["I3"]["arms"][arm] = run_i3_arm(
                    arm, sc["i3_kills"], a.host, a.port, root, common.SEED + 300 + i
                )
                _dump(doc, a)
        if "I3A" in parts:
            from plexus.crucible.l7 import i_aof

            if a.aof_result:
                aof = json.loads(Path(a.aof_result).read_text(encoding="utf-8"))
            else:
                aof = i_aof.run_repro(Path(a.aof_data), repeats=3)
            doc["parts"].setdefault("I3", {"arms": {}})["aof_repro"] = aof
        if "I4" in parts:
            from plexus.crucible.l7 import i_conc

            doc["parts"]["I4"] = i_conc.run_i4(a.host, a.port, root, sc, log)
        if "I4C" in parts:
            from plexus.crucible.l7 import i_conc

            rows = [
                i_conc.rerun_a_cell(
                    "FalkorDB", "pessimistic", 200, sc["i4_ops"], 1500.0, a.host, a.port, root
                )
            ]
            doc["parts"]["I4"] = {"a": rows, "b": [], "rerun": True}
        if "I5" in parts:
            doc["parts"]["I5"] = run_i5(
                sc["i5_n"], a.host, a.port, root,
                doc["parts"].get("I1", {}).get("arms"), doc["parts"].get("I2", {}).get("arms"),
            )  # fmt: skip
    finally:
        shutil.rmtree(root, ignore_errors=True)
        doc["server_bug_reports_at_end"] = bug_reports(container)
    log(f"wrote {_dump(doc, a, final=True)}")
    return 0


def cmd_merge(a: argparse.Namespace) -> int:
    docs = [json.loads(Path(p).read_text(encoding="utf-8")) for p in a.inputs]
    doc = docs[0]
    originals = [d["parts"] for d in docs]
    doc["parts"] = {}
    doc["merged_from"] = []
    for d, parts in zip(docs, originals, strict=True):
        d["parts"] = parts
        for k, v in parts.items():
            if k == "I4" and v.get("rerun") and k in doc["parts"]:
                key = lambda r: (r["backend"], r["mode"], r["W"])  # noqa: E731
                new = {key(r): r for r in v["a"]}
                doc["parts"][k]["a"] = [
                    {**new[key(r)], "replaces_incomplete_cell": True} if key(r) in new else r
                    for r in doc["parts"][k]["a"]
                ]
            elif k in doc["parts"] and "arms" in v:
                doc["parts"][k]["arms"].update(v["arms"])
                if "aof_repro" in v:
                    doc["parts"][k]["aof_repro"] = v["aof_repro"]
            elif k in doc["parts"]:
                doc["parts"][k].update(v)
            else:
                doc["parts"][k] = v
        doc["merged_from"].append({"run_id": d["run"]["id"], "command": d["run"]["command"], "parts": sorted(d["parts"]),
                                   "started_at": d["run"]["started_at"], "finished_at": d["run"]["finished_at"]})  # fmt: skip
    if a.aof_result:
        doc["parts"].setdefault("I3", {"arms": {}})["aof_repro"] = json.loads(
            Path(a.aof_result).read_text(encoding="utf-8")
        )
    doc["run"]["id"] = doc["run"]["id"] + "-merged"
    log(f"merged -> {common.write(doc, Path(a.out), report_md(doc))}")
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="crucible-l7-i")
    sub = ap.add_subparsers(dest="cmd", required=True)
    w = sub.add_parser("writer")
    w.add_argument("--arm", required=True)
    w.add_argument("--host", default=common.DEFAULT_HOST)
    w.add_argument("--port", type=int, required=True)
    w.add_argument("--tenant", default="")
    w.add_argument("--root", default="")
    w.add_argument("--tag", required=True)
    r = sub.add_parser("run")
    r.add_argument("--host", default=common.DEFAULT_HOST)
    r.add_argument("--port", type=int, default=6368)
    r.add_argument("--scale", choices=sorted(SCALES), default="dev")
    r.add_argument("--out", default=str(common.DEMO))
    r.add_argument("--parts", default="I1,I2,I3,I3A,I4,I5")
    r.add_argument("--arms", default="")
    r.add_argument(
        "--aof-result",
        default="",
        help="JSON written by `python -m plexus.crucible.l7.i_aof` (skips the repro)",
    )
    r.add_argument("--aof-data", default="C:/Change_folder_after_HDD/wt-p10/.p10/aof-crash-evidence/data")
    m = sub.add_parser("merge")
    m.add_argument("--out", required=True)
    m.add_argument("--aof-result", default="")
    m.add_argument("inputs", nargs="+")
    a = ap.parse_args(argv)
    if a.cmd == "writer":
        writer(a.arm, a.host, a.port, a.tenant, a.root, a.tag)
        return 0
    if a.cmd == "merge":
        return cmd_merge(a)
    if a.port != 6368:
        print("family I uses port 6368 only", file=sys.stderr)
        return 2
    return cmd_run(a)


if __name__ == "__main__":
    sys.exit(main())
