"""``crucible`` command line: ``crucible l1|l4|ablation|all [--quick] [options]``.

Examples::

    uv run crucible all --quick                       # CI-sized, against FALKORDB_HOST/PORT (default localhost:6379)
    FALKORDB_PORT=6389 uv run crucible l1 --arms B1,P --tests C1,C3 --reps 3
    docker compose -p plexus-bench --profile bench run --rm crucible all     # the published run, inside the network

Results go to ``<results dir>/<timestamp>/results.json`` + ``report.md`` (``CRUCIBLE_RESULTS_DIR`` or
``--out``; default ``plexus/src/plexus/crucible/results``). Exit code: 0 when the run completed and the Plexus arm
had no L1 violation; 1 when the Plexus arm failed an L1 test (baseline failures are findings, not errors); 2 when the
database is unreachable or the arguments are wrong.
"""

from __future__ import annotations

import argparse
import dataclasses
import os
import shutil
import sys
import tempfile
import time
from pathlib import Path
from typing import Any

from plexus.crucible import results as R
from plexus.crucible.config import L1_ARMS, L4_ARMS, L1Config, L4Config, quick_l1, quick_l4
from plexus.crucible.harness import Env
from plexus.crucible.l1 import TESTS


def _csv(value: str) -> tuple[str, ...]:
    return tuple(v.strip() for v in value.split(",") if v.strip())


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="crucible", description="Plexus Crucible: change only the backend, measure the rest."
    )
    p.add_argument(
        "layer",
        choices=("l1", "l4", "ablation", "all", "rerun"),
        help="what to run (all = l1 + l4 + ablation; rerun = re-execute the --cell cells of --base)",
    )
    p.add_argument("--quick", action="store_true", help="fewer repetitions and workers (CI sizing, < 2 min)")
    p.add_argument(
        "--arms",
        type=_csv,
        help=f"comma list; L1 default {','.join(L1_ARMS)}, L4 default {','.join(L4_ARMS)}",
    )
    p.add_argument("--tests", type=_csv, help=f"L1 tests, default all ({','.join(TESTS)})")
    p.add_argument("--reps", type=int, help="L1 repetitions per test case (default 10, quick 2)")
    p.add_argument(
        "--workers", type=lambda s: tuple(int(x) for x in s.split(",")), help="L4 worker counts, e.g. 1,10,50"
    )
    p.add_argument(
        "--out", type=Path, help="results root (default $CRUCIBLE_RESULTS_DIR or the package results/ dir)"
    )
    p.add_argument(
        "--embedder", choices=("fastembed", "hash"), help="default fastembed (or $PLEXUS_EMBEDDER)"
    )
    p.add_argument("--host", help="FalkorDB host (default $FALKORDB_HOST or 127.0.0.1)")
    p.add_argument("--port", type=int, help="FalkorDB port (default $FALKORDB_PORT or 6379)")
    p.add_argument("--base", type=Path, help="rerun: results directory (or results.json) to patch")
    p.add_argument(
        "--cell",
        action="append",
        default=[],
        help="rerun: L1:<arm>:<test> | L4:claim:<arm>:<workers> | L4:embedder",
    )
    p.add_argument(
        "--reason", default="", help="rerun: why these cells are re-executed (recorded in the results)"
    )
    p.add_argument(
        "--work-dir",
        type=Path,
        help="scratch dir for the file arms (default: a temp dir, removed afterwards)",
    )
    return p


def _config(args: argparse.Namespace) -> tuple[L1Config, L4Config]:
    l1, l4 = (quick_l1(), quick_l4()) if args.quick else (L1Config(), L4Config())
    if args.reps:
        l1 = dataclasses.replace(l1, reps=args.reps)
    if args.tests:
        bad = [t for t in args.tests if t not in TESTS]
        if bad:
            raise SystemExit(f"unknown test(s): {', '.join(bad)} (expected {', '.join(TESTS)})")
        l1 = dataclasses.replace(l1, tests=args.tests)
    if args.workers:
        l4 = dataclasses.replace(l4, workers=args.workers)
    if args.arms:
        valid = {*L1_ARMS, *L4_ARMS}
        bad = [a for a in args.arms if a not in valid]
        if bad:
            raise SystemExit(f"unknown arm(s): {', '.join(bad)} (expected {', '.join(sorted(valid))})")
        l1 = dataclasses.replace(l1, arms=tuple(a for a in args.arms if a in L1_ARMS))
        l4 = dataclasses.replace(
            l4,
            claim_arms=tuple(a for a in l4.claim_arms if a in args.arms),
            recall_arms=tuple(a for a in l4.recall_arms if a in args.arms),
            tenant_arms=tuple(a for a in l4.tenant_arms if a in args.arms),
            arms=tuple(a for a in L4_ARMS if a in args.arms),
        )
    return l1, l4


def _needs_db(layer: str, l1: L1Config, l4: L4Config) -> bool:
    if layer in ("ablation", "rerun", "all"):
        return True
    return any(a.startswith("P") for a in (l1.arms if layer == "l1" else l4.arms))


DB_WAIT_S = float(os.environ.get("CRUCIBLE_DB_WAIT_S", "120"))


def wait_for_db(host: str, port: int, timeout_s: float) -> str:
    """Block until the server answers PING *and* has finished loading its dataset (``loading:0``).

    PING succeeds (and a compose healthcheck that only pings goes green) while Redis is still replaying a large AOF,
    but every command then fails with ``BusyLoadingError``. Waits at most ``timeout_s`` while the server reports
    loading; any other failure returns at once. Returns "" when ready, else the reason.
    """
    import redis

    deadline = time.monotonic() + timeout_s
    last = ""
    while True:
        try:
            r = redis.Redis(host=host, port=port, socket_timeout=5, decode_responses=True)
            r.ping()
            if int(r.info("persistence").get("loading", 0)) == 0:
                return ""
            last = "still loading the dataset"
        except redis.exceptions.BusyLoadingError:
            last = "still loading the dataset"
        except Exception as exc:  # noqa: BLE001
            if "loading" not in str(exc).lower():
                return str(exc)
            last = "still loading the dataset"
        if time.monotonic() >= deadline:
            return f"{last} after {timeout_s:.0f}s"
        time.sleep(1.0)


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    l1_cfg, l4_cfg = _config(args)
    work = args.work_dir or Path(tempfile.mkdtemp(prefix="crucible-"))
    work.mkdir(parents=True, exist_ok=True)
    env = Env.from_environ(root=str(work), embedder=args.embedder)
    if args.host:
        env.host = args.host
    if args.port:
        env.port = args.port
    if _needs_db(args.layer, l1_cfg, l4_cfg):
        err = wait_for_db(env.host, env.port, DB_WAIT_S)
        if err:
            print(f"crucible: FalkorDB is not usable at {env.host}:{env.port} ({err})", file=sys.stderr)
            return 2
    if args.layer == "rerun":
        if not args.base or not args.cell or not args.reason:
            print("crucible rerun needs --base, at least one --cell and a --reason", file=sys.stderr)
            return 2
        from plexus.crucible.rerun import rerun

        try:
            d, _ = rerun(args.base, args.cell, args.reason, env, log=lambda m: print(m, flush=True))
        finally:
            if args.work_dir is None:
                shutil.rmtree(work, ignore_errors=True)
        print(f"patched: {d / 'results.json'}", flush=True)
        print(f"report:  {d / 'report.md'}", flush=True)
        return 0
    started = time.time()
    run_id = R.new_run_id(args.quick)
    command = "crucible " + " ".join(argv if argv is not None else sys.argv[1:])
    print(
        f"crucible {args.layer}{' --quick' if args.quick else ''}: run {run_id}, FalkorDB {env.host}:{env.port}, embedder {env.embedder}",
        flush=True,
    )
    l1: dict[str, Any] | None = None
    l4: dict[str, Any] | None = None
    ab: dict[str, Any] | None = None
    try:
        if args.layer in ("l1", "all"):
            from plexus.crucible.l1 import run_l1

            print("== L1: correctness under concurrency ==", flush=True)
            l1 = run_l1(env, l1_cfg, log=lambda m: print(m, flush=True))
        if args.layer in ("l4", "all"):
            from plexus.crucible.l4 import run_l4

            print("== L4: performance and scale ==", flush=True)
            l4 = run_l4(env, l4_cfg, log=lambda m: print(m, flush=True))
        if args.layer in ("ablation", "all"):
            from plexus.crucible.ablation import run_ablation

            print("== Ablation ==", flush=True)
            ab = run_ablation(env, l1_cfg, log=lambda m: print(m, flush=True))
    finally:
        if args.work_dir is None:
            shutil.rmtree(work, ignore_errors=True)
    res = R.assemble(
        run_id=run_id,
        started=started,
        quick=args.quick,
        command=command,
        l1_cfg=l1_cfg if l1 is not None else None,
        l4_cfg=l4_cfg if l4 is not None else None,
        l1=l1,
        l4=l4,
        ablation=ab,
        host=env.host,
        port=env.port,
        embedder=env.embedder,
    )
    out_root = args.out or R.default_results_dir()
    d = R.write(res, out_root, run_id)
    print(f"results: {d / 'results.json'}\nreport:  {d / 'report.md'}", flush=True)
    plexus_failed = False
    if l1 is not None and "P" in l1:
        plexus_failed = any(not r["passed"] for r in l1["P"].values())
        if plexus_failed:
            print("crucible: the Plexus arm FAILED an L1 test (see report)", file=sys.stderr)
    return 1 if plexus_failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
