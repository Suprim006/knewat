"""Family J driver process: ``python -m plexus.crucible.l7.j_worker <config.json>``.

Builds one adapter per tenant it touches (F: one shared GraphClient per process; S: one backend per tenant file),
starts one thread per assigned session slot (closed loop: when a session ends the next one starts), waits for the
parent's go file, runs warm-up + measured seconds and writes its raw measurements to ``result_path``.
"""

from __future__ import annotations

import json
import os
import random
import sys
import threading
import time
import traceback
from pathlib import Path
from typing import Any

from plexus.crucible.l7.common import SEED, process_resources
from plexus.crucible.l7.j_arms import make_adapter
from plexus.crucible.l7.j_session import Rec, Session, TenantPool, load_sequences


def _slot_loop(
    slot: dict[str, Any],
    adapter: Any,
    pool: TenantPool,
    seqs: list[list[str]],
    trav: bool,
    t_meas: float,
    t_end: float,
    rec: Rec,
) -> None:
    rng = random.Random(SEED + slot["k"])
    n = 0
    measuring = lambda: time.time() >= t_meas  # noqa: E731
    alive = lambda: time.time() < t_end  # noqa: E731
    while alive():
        n += 1
        seq = seqs[rng.randrange(len(seqs))]
        agent = f"a{slot['slot']}x{n}"
        try:
            Session(adapter, pool, rng, agent, seq, trav, rec, measuring, alive).run()
        except Exception as exc:  # a bug in the session model itself, not a measured error
            rec.err_samples.setdefault("driver_bug", []).append(traceback.format_exc()[-400:])
            time.sleep(0.05)
            if len(rec.err_samples["driver_bug"]) > 20:
                raise exc


def _open(arm: str, tenant: str, host: str, port: int, root: str, client: Any, trav: bool) -> Any:
    """Open one tenant. Runtime.state() re-applies the (idempotent) schema on first use in every process; when 8 drivers
    start at once FalkorDB answers 'another write is in progress, retry the query' to some of them: retry (setup only)."""
    for attempt in range(200):
        try:
            return make_adapter(arm, tenant, host, port, root, client, trav_index=trav)
        except Exception as exc:
            if "another write is in progress" not in str(exc) or attempt == 199:
                raise
            time.sleep(random.uniform(0.02, 0.2))
    raise AssertionError("unreachable")


def main(cfg_path: str) -> None:
    cfg = json.loads(Path(cfg_path).read_text(encoding="utf-8"))
    arm, host, port, root = cfg["arm"], cfg["host"], cfg["port"], cfg["root"]
    client = None
    if arm.startswith("F"):
        from plexus.crucible.backends.plexus import _client

        client = _client(host, port)
    adapters: dict[str, Any] = {}
    pools: dict[str, TenantPool] = {}
    for s in cfg["slots"]:
        t = s["tenant"]
        if t not in adapters:
            adapters[t] = _open(arm, t, host, port, root, client, cfg["mix"] == "J-trav")
            pools[t] = TenantPool.from_manifest(cfg["manifests"][t])
    seqs = list(load_sequences().values())
    res0 = process_resources()
    Path(cfg["ready_path"]).write_text(json.dumps({"pid": os.getpid(), "resources": res0}), encoding="utf-8")
    while not Path(cfg["go_path"]).exists():
        time.sleep(0.02)
    go = json.loads(Path(cfg["go_path"]).read_text(encoding="utf-8"))
    t_start = go["t_start"]
    t_meas = t_start + cfg["warmup"]
    t_end = t_meas + cfg["seconds"]
    recs = [Rec() for _ in cfg["slots"]]
    threads = [
        threading.Thread(
            target=_slot_loop,
            args=(
                s,
                adapters[s["tenant"]],
                pools[s["tenant"]],
                seqs,
                cfg["mix"] == "J-trav",
                t_meas,
                t_end,
                r,
            ),
            daemon=True,
        )
        for s, r in zip(cfg["slots"], recs, strict=True)
    ]
    while time.time() < t_start:
        time.sleep(0.005)
    res_start = process_resources()
    for th in threads:
        th.start()
    deadline = t_end + cfg["grace"]
    for th in threads:
        th.join(max(0.0, deadline - time.time()))
    stuck = sum(th.is_alive() for th in threads)
    res_end = process_resources()
    calls: list[list[Any]] = []
    errs: dict[str, list[str]] = {}
    for r in recs:
        calls.extend([c[0], round(c[1] - t_meas, 4), round(c[2], 3), c[3]] for c in r.calls)
        for k, v in r.err_samples.items():
            errs.setdefault(k, []).extend(v[:3])
    out = {
        "pid": os.getpid(),
        "threads": len(threads),
        "stuck_threads": stuck,
        "sessions_completed": sum(r.sessions for r in recs),
        "skipped_complete": sum(r.skipped_complete for r in recs),
        "resources": {
            "at_ready": res0,
            "at_start": res_start,
            "at_end": res_end,
            "cpu_s_run": round(res_end["cpu_s"] - res_start["cpu_s"], 3),
        },
        "err_samples": {k: v[:5] for k, v in errs.items()},
        "calls": calls,
    }
    Path(cfg["result_path"]).write_text(json.dumps(out), encoding="utf-8")
    sys.stdout.flush()
    os._exit(0)  # skip the slow teardown of hundreds of connections / threads


def _guarded(cfg_path: str) -> None:
    try:
        main(cfg_path)
    except BaseException:
        cfg = json.loads(Path(cfg_path).read_text(encoding="utf-8"))
        Path(cfg["result_path"]).write_text(
            json.dumps({"fatal": traceback.format_exc()[-3000:]}), encoding="utf-8"
        )
        sys.stderr.write(traceback.format_exc())
        os._exit(1)


if __name__ == "__main__":
    _guarded(sys.argv[1])
