"""Layer 4: performance and scale (BASELINE §4). Scripted workers, no LLM; meant to run inside the compose network.

Three experiments, each reported per arm:

* ``claim_sweep``   W workers each run claim -> heartbeat -> complete cycles on one tenant. Latency p50/p95/p99 per
                    operation and total throughput as W grows 1 -> 200. For the Knewat arms the server-side
                    ``run_time_ms`` (summed over the call's queries, as the ToolCall stores it) is reported next to
                    the client latency.
* ``recall_sweep``  W workers run recalls over ``recall_facts`` seeded facts (embedding included, as in production).
* ``tenant_sweep``  the write ceiling: the same W workers and the same total task count spread over 1, 4, 16 tenant
                    graphs (Knewat: one FalkorDB graph per tenant; B1: one SQLite file per tenant).

Client latency is measured by Python threads in one process, so at high W it contains GIL queuing; that is why the
server time is shown next to it. Arms are driven through the same ``CoordinationBackend`` surface (L4 KNEWAT = service
layer; ``P-mcp`` additionally opens a Step and writes a ToolCall per call, as the MCP server does).
"""

from __future__ import annotations

import math
import random
import statistics
import time
from collections.abc import Callable
from typing import Any

from knewat.crucible.config import L4Config
from knewat.crucible.harness import ArmRun, Env, describe_errors, run_workers
from knewat.crucible.util import percentile

OPS = ("claim", "heartbeat", "complete")


def stats(ms: list[float]) -> dict[str, float]:
    if not ms:
        return {"n": 0}
    return {
        "n": len(ms),
        "mean_ms": round(statistics.fmean(ms), 3),
        "p50_ms": round(percentile(ms, 50), 3),
        "p95_ms": round(percentile(ms, 95), 3),
        "p99_ms": round(percentile(ms, 99), 3),
        "max_ms": round(max(ms), 3),
    }


def _op_summary(client: list[float], server: list[float]) -> dict[str, Any]:
    out = stats(client)
    if server and any(s > 0 for s in server):
        out["server_p50_ms"] = round(percentile(server, 50), 3)
        out["server_p95_ms"] = round(percentile(server, 95), 3)
        out["server_p99_ms"] = round(percentile(server, 99), 3)
        out["server_mean_ms"] = round(statistics.fmean(server), 3)
    return out


class _Recorder:
    """Per-thread latency collection (merged at the end, so no lock is needed while measuring)."""

    def __init__(self, backend: Any):
        self.b = backend
        self.client: dict[str, list[float]] = {k: [] for k in (*OPS, "recall")}
        self.server: dict[str, list[float]] = {k: [] for k in (*OPS, "recall")}
        self.errors: list[BaseException] = []
        self.empty = 0

    def timed(self, key: str, fn: Callable[[], Any]) -> Any:
        t0 = time.perf_counter()
        out = fn()
        dt = (time.perf_counter() - t0) * 1000.0
        self.client[key].append(dt)
        last = getattr(self.b, "last_server_ms", None)
        if last is not None:
            self.server[key].append(last())
        return out


def _merge(recs: list[_Recorder], key: str) -> tuple[list[float], list[float]]:
    c: list[float] = []
    s: list[float] = []
    for r in recs:
        c += r.client[key]
        s += r.server[key]
    return c, s


def _cycles(cfg: L4Config, w: int) -> int:
    target = max(cfg.min_cycles, min(cfg.max_cycles, w * cfg.ops_per_worker))
    return max(1, math.ceil(target / w))


# ------------------------------------------------------------------------------------------------------------
# claim sweep
# ------------------------------------------------------------------------------------------------------------


def claim_point(env: Env, arm: str, w: int, cfg: L4Config) -> dict[str, Any]:
    cps = _cycles(cfg, w)
    n_tasks = w * cps
    with ArmRun(env, arm) as run:
        b = run.open("l4c")
        b.create_tasks([{"id": f"t{i:05d}", "title": f"task {i}"} for i in range(n_tasks)])
        names = [f"w{i:03d}" for i in range(w)]
        for n in names:
            b.register_agent(n, "worker")
        recs = [_Recorder(b) for _ in range(w)]

        def worker(i: int) -> None:
            rec, name = recs[i], names[i]
            for _ in range(cps):
                t = rec.timed("claim", lambda: b.claim_next_task(name, cfg.lease_ms))
                if t is None:
                    rec.empty += 1
                    return
                if not rec.timed("heartbeat", lambda t=t: b.heartbeat(name, t["id"], cfg.lease_ms)):
                    rec.errors.append(RuntimeError("heartbeat refused"))
                rec.timed("complete", lambda t=t: b.complete_task(name, t["id"], t["version"]))

        t0 = time.perf_counter()
        errors = run_workers(w, worker, timeout=cfg.point_timeout_s)
        wall = time.perf_counter() - t0
        errors += [e for r in recs for e in r.errors]
        done = sum(len(r.client["complete"]) for r in recs)
        all_ops = sum(len(r.client[k]) for r in recs for k in OPS)
        final = b.list_tasks()
        point: dict[str, Any] = {
            "arm": arm,
            "workers": w,
            "cycles_per_worker": cps,
            "tasks": n_tasks,
            "wall_s": round(wall, 3),
            "ops": all_ops,
            "throughput_ops_s": round(all_ops / wall, 1) if wall else 0.0,
            "cycles_completed": done,
            "tasks_done_in_store": sum(1 for t in final if t["status"] == "done"),
            "empty_claims": sum(r.empty for r in recs),
            "errors": describe_errors(errors),
            "error_count": len(errors),
        }
        for op in OPS:
            c, s = _merge(recs, op)
            point[op] = _op_summary(c, s)
        return point


# ------------------------------------------------------------------------------------------------------------
# recall sweep
# ------------------------------------------------------------------------------------------------------------

_TOPICS = ["billing", "search", "mobile", "auth", "deploy", "cache", "queue", "metrics", "storage", "email"]
_VERBS = ["retries", "caches", "validates", "archives", "throttles", "indexes", "encrypts", "batches"]


def _fact(i: int) -> tuple[str, str, str]:
    topic, verb = _TOPICS[i % len(_TOPICS)], _VERBS[(i // len(_TOPICS)) % len(_VERBS)]
    return (
        f"{topic} service {i}",
        f"{verb} policy",
        f"the {topic} service {verb} requests for tenant group {i} within {5 + i % 50} seconds",
    )


def recall_sweep(env: Env, arm: str, cfg: L4Config) -> list[dict[str, Any]]:
    points: list[dict[str, Any]] = []
    rng = random.Random(cfg.seed)
    with ArmRun(env, arm) as run:
        b = run.open("l4r")
        b.register_agent("seed")
        t0 = time.perf_counter()

        def seed_facts(i: int) -> None:
            for k in range(i, cfg.recall_facts, 8):
                s, p, v = _fact(k)
                b.assert_fact("seed", s, p, v)

        seed_errors = run_workers(min(8, cfg.recall_facts), seed_facts, timeout=cfg.point_timeout_s * 2)
        seed_s = time.perf_counter() - t0
        for w in cfg.workers:
            total = max(
                100 if cfg.max_recalls >= 100 else cfg.max_recalls // 2,
                min(cfg.max_recalls, w * cfg.recall_per_worker),
            )
            rpw = max(1, math.ceil(total / w))
            names = [f"r{i:03d}" for i in range(w)]
            for n in names:
                b.register_agent(n, "worker")
            queries = [[_fact(rng.randrange(cfg.recall_facts)) for _ in range(rpw)] for _ in range(w)]
            recs = [_Recorder(b) for _ in range(w)]

            def worker(i: int, recs=recs, names=names, queries=queries) -> None:
                rec = recs[i]
                for s, p, v in queries[i]:
                    hits = rec.timed(
                        "recall", lambda s=s, p=p, v=v, i=i: b.recall(names[i], f"{s} {p} {v}", k=8)
                    )
                    if not hits:
                        rec.empty += 1

            t1 = time.perf_counter()
            errors = run_workers(w, worker, timeout=cfg.point_timeout_s)
            wall = time.perf_counter() - t1
            c, s = _merge(recs, "recall")
            points.append(
                {
                    "arm": arm,
                    "workers": w,
                    "facts": cfg.recall_facts,
                    "recalls": len(c),
                    "wall_s": round(wall, 3),
                    "throughput_ops_s": round(len(c) / wall, 1) if wall else 0.0,
                    "empty_recalls": sum(r.empty for r in recs),
                    "recall": _op_summary(c, s),
                    "errors": describe_errors(errors),
                    "error_count": len(errors),
                    "seed_s": round(seed_s, 2),
                    "seed_errors": describe_errors(seed_errors),
                }
            )
    return points


# ------------------------------------------------------------------------------------------------------------
# one graph vs N tenant graphs
# ------------------------------------------------------------------------------------------------------------


def tenant_point(env: Env, arm: str, tenants: int, cfg: L4Config) -> dict[str, Any]:
    w = cfg.tenant_workers
    cps = max(1, cfg.tenant_ops_per_worker)
    n_tasks = w * cps
    with ArmRun(env, arm) as run:
        backends = [run.open(f"l4t{i}") for i in range(tenants)]
        per = [[] for _ in range(tenants)]
        for i in range(n_tasks):
            per[i % tenants].append({"id": f"t{i:05d}", "title": f"task {i}"})
        for b, tasks in zip(backends, per, strict=True):
            b.create_tasks(tasks)
        names = [f"w{i:03d}" for i in range(w)]
        for i, n in enumerate(names):
            backends[i % tenants].register_agent(n, "worker")
        recs = [_Recorder(backends[i % tenants]) for i in range(w)]

        def worker(i: int) -> None:
            b, rec, name = backends[i % tenants], recs[i], names[i]
            for _ in range(cps):
                t = rec.timed("claim", lambda: b.claim_next_task(name, cfg.lease_ms))
                if t is None:
                    rec.empty += 1
                    return
                rec.timed("complete", lambda t=t: b.complete_task(name, t["id"], t["version"]))

        t0 = time.perf_counter()
        errors = run_workers(w, worker, timeout=cfg.point_timeout_s)
        wall = time.perf_counter() - t0
        errors += [e for r in recs for e in r.errors]
        ops = sum(len(r.client[k]) for r in recs for k in ("claim", "complete"))
        c, s = _merge(recs, "claim")
        return {
            "arm": arm,
            "tenants": tenants,
            "workers": w,
            "tasks": n_tasks,
            "wall_s": round(wall, 3),
            "ops": ops,
            "throughput_ops_s": round(ops / wall, 1) if wall else 0.0,
            "empty_claims": sum(r.empty for r in recs),
            "claim": _op_summary(c, s),
            "errors": describe_errors(errors),
            "error_count": len(errors),
        }


# ------------------------------------------------------------------------------------------------------------
# embedder probe: how much of recall latency is the (shared, lock-serialised) embedding model?
# ------------------------------------------------------------------------------------------------------------


def embedder_probe(env: Env, cfg: L4Config) -> list[dict[str, Any]]:
    """Embed query-sized texts from W threads with no database involved. This is the ceiling for every arm whose
    recall embeds the query (B2, P, P-mcp): the model instance is shared and its calls are serialised."""
    from knewat.embed import get_embedder

    emb = get_embedder(env.embedder)
    emb.embed(["warm up"])
    out = []
    for w in sorted({1, 10, max(cfg.workers)}):
        calls = max(4, min(16, 400 // w))
        lat: list[list[float]] = [[] for _ in range(w)]

        def worker(i: int, lat=lat, calls=calls) -> None:
            for k in range(calls):
                s, p, v = _fact(i * calls + k)
                t0 = time.perf_counter()
                emb.embed([f"{s} {p} {v}"])
                lat[i].append((time.perf_counter() - t0) * 1000.0)

        t0 = time.perf_counter()
        run_workers(w, worker, timeout=cfg.point_timeout_s)
        wall = time.perf_counter() - t0
        flat = [x for ls in lat for x in ls]
        out.append(
            {
                "workers": w,
                "calls": len(flat),
                "wall_s": round(wall, 3),
                "throughput_ops_s": round(len(flat) / wall, 1),
                **stats(flat),
            }
        )
    return out


# ------------------------------------------------------------------------------------------------------------
# driver
# ------------------------------------------------------------------------------------------------------------


def run_l4(env: Env, cfg: L4Config, log: Callable[[str], None] = print) -> dict[str, Any]:
    out: dict[str, Any] = {"claim_sweep": [], "recall_sweep": [], "tenant_sweep": []}
    for arm in cfg.claim_arms:
        for w in cfg.workers:
            p = claim_point(env, arm, w, cfg)
            out["claim_sweep"].append(p)
            log(
                f"  L4 claim  {arm:>5} W={w:<3} {p['throughput_ops_s']:>8} ops/s  claim p50={p['claim'].get('p50_ms')} "
                f"p99={p['claim'].get('p99_ms')} ms  errors={p['error_count']}"
            )
    for arm in cfg.recall_arms:
        pts = recall_sweep(env, arm, cfg)
        out["recall_sweep"] += pts
        for p in pts:
            log(
                f"  L4 recall {arm:>5} W={p['workers']:<3} {p['throughput_ops_s']:>8} ops/s  recall p50={p['recall'].get('p50_ms')} "
                f"p99={p['recall'].get('p99_ms')} ms  errors={p['error_count']}"
            )
    for arm in cfg.tenant_arms:
        for t in cfg.tenant_counts:
            p = tenant_point(env, arm, t, cfg)
            out["tenant_sweep"].append(p)
            log(
                f"  L4 tenants {arm:>4} T={t:<3} {p['throughput_ops_s']:>8} ops/s  claim p99={p['claim'].get('p99_ms')} ms"
            )
    out["embedder_probe"] = embedder_probe(env, cfg)
    for p in out["embedder_probe"]:
        log(f"  L4 embedder-only W={p['workers']:<3} {p['throughput_ops_s']:>8} ops/s  p50={p['p50_ms']} ms")
    return out
