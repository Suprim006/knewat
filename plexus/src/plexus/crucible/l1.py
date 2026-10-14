"""Layer 1: correctness under concurrency, C1-C8 (BASELINE §1). Deterministic, no LLM.

Every test is a function ``(ArmRun, seed, cfg, **params) -> RunResult`` that drives scripted workers against one
fresh tenant, counts violations exactly, and cleans up. Workers are threads sharing one backend object (each
thread has its own DB connection / file descriptors) except C2, whose victims are real OS processes killed with
SIGKILL. Concurrency is real but not deterministic; what is fixed by the seed is the workload (task priorities, DAG
shape, fact values, query times).
"""

from __future__ import annotations

import json
import random
import subprocess
import sys
import threading
import time
from collections import defaultdict
from collections.abc import Callable
from typing import Any

from plexus.crucible.api import (
    ClaimConflict,
    CrucibleError,
    InvalidTenant,
    UnknownReference,
    Unsupported,
)
from plexus.crucible.config import L1Config
from plexus.crucible.harness import (
    ArmRun,
    Env,
    RunResult,
    aggregate,
    run_workers,
    unsupported_result,
)
from plexus.crucible.util import normalize

TESTS: dict[str, dict[str, str]] = {
    "C1": {
        "title": "Claim race: N workers claim M tasks",
        "metric": "double claims / lost updates / tasks never claimed",
        "bar": "0 / 0 / 0",
    },
    "C2": {
        "title": "Kill the claimer mid-task (SIGKILL)",
        "metric": "time until the expired lease is reclaimed; orphaned tasks",
        "bar": "all reclaimed within lease + 1 heartbeat; 0 orphans",
    },
    "C3": {
        "title": "Concurrent assertions on the same entity+predicate",
        "metric": "duplicate facts; contradictions not flagged; lost endorsements",
        "bar": "0 duplicates; 100% of contradictions flagged",
    },
    "C4": {
        "title": "Dependency DAG (depth 5, fan-out 3)",
        "metric": "tasks started before their dependencies finished",
        "bar": "0",
    },
    "C5": {
        "title": "Tenant isolation probes",
        "metric": "rows leaked across tenants (+ cross-tenant writes)",
        "bar": "0",
    },
    "C6": {
        "title": "Supersede, then query 'as of T'",
        "metric": "wrong-version answers",
        "bar": "0",
    },
    "C7": {
        "title": "Paraphrase facts written concurrently by different agents",
        "metric": "duplicates stored beyond the sequential paraphrase-miss rate; false merges",
        "bar": "concurrent misses <= sequential misses (rate reported); 0 false merges",
    },
    "C8": {
        "title": "Forget by source, then probe recall",
        "metric": "derived facts still returned",
        "bar": "0",
    },
}

DENIED = (UnknownReference, ClaimConflict, InvalidTenant, ValueError, Unsupported, CrucibleError)


def _wall() -> float:
    return time.monotonic()


# ============================================================================================================
# C1: claim race
# ============================================================================================================


def c1(run: ArmRun, seed: int, cfg: L1Config, workers: int) -> RunResult:
    m = cfg.c1_tasks
    res = RunResult(seed=seed, params={"workers": workers, "tasks": m})
    b = run.open("c1")
    rng = random.Random(seed)
    b.create_tasks(
        [{"id": f"t{i:04d}", "title": f"task {i}", "priority": rng.randint(0, 3)} for i in range(m)]
    )
    names = [f"w{i:03d}" for i in range(workers)]
    for n in names:
        b.register_agent(n, "worker")
    claims: dict[str, list[tuple[str, int]]] = defaultdict(list)
    completed: dict[str, list[str]] = defaultdict(list)
    conflicts: list[str] = []
    lock = threading.Lock()

    def worker(i: int) -> None:
        name, r = names[i], random.Random(seed * 1000 + i)
        while (t := b.claim_next_task(name, 600_000)) is not None:
            with lock:
                claims[t["id"]].append((name, t["version"]))
            time.sleep(r.random() * 0.002)  # a little "work", so claims overlap with completions
            try:
                b.complete_task(name, t["id"], t["version"])
                with lock:
                    completed[t["id"]].append(name)
            except ClaimConflict as exc:
                with lock:
                    conflicts.append(str(exc))

    t0 = _wall()
    errors = run_workers(workers, worker)
    dur = _wall() - t0
    final = {t["id"]: t for t in b.list_tasks()}
    ids = [f"t{i:04d}" for i in range(m)]
    double = sum(1 for t in ids if len(claims[t]) > 1)
    lost = len(conflicts)
    for t in ids:
        f = final.get(t)
        ok_done = len(completed[t])
        if ok_done > 1 or (ok_done == 1 and (f is None or f["status"] != "done" or f["version"] != 2)):
            lost += 1  # completed twice, or a completion the store does not show
        elif ok_done == 0 and f is not None and f["status"] == "done":
            lost += 1  # done in the store, but no worker's completion was acknowledged
    never = sum(1 for t in ids if not claims[t])
    res.violations = {"double_claims": double, "lost_updates": lost, "never_claimed": never}
    res.metrics = {
        "claims": sum(len(v) for v in claims.values()),
        "duration_s": round(dur, 3),
        "ops_per_s": round(2 * m / dur, 1) if dur else 0.0,
    }
    res.set_errors(errors)
    return res.finish()


# ============================================================================================================
# C2: kill the claimer
# ============================================================================================================


def c2(run: ArmRun, seed: int, cfg: L1Config) -> RunResult:
    res = RunResult(
        seed=seed,
        params={
            "tasks": cfg.c2_tasks,
            "victims": cfg.c2_victims,
            "survivors": cfg.c2_survivors,
            "lease_ms": cfg.c2_lease_ms,
            "heartbeat_ms": cfg.c2_heartbeat_ms,
        },
    )
    b = run.open("c2")
    spec = run.spec("c2", b.tenant)  # type: ignore[attr-defined]
    b.create_tasks([{"id": f"t{i:03d}", "title": f"task {i}"} for i in range(cfg.c2_tasks)])
    victims = [f"victim{i}" for i in range(cfg.c2_victims)]
    procs: dict[str, subprocess.Popen[str]] = {}
    held: dict[str, str] = {}
    errors: list[BaseException] = []
    try:
        for v in victims:  # one at a time: each victim takes the next ready task
            p = subprocess.Popen(
                [
                    sys.executable,
                    "-m",
                    "plexus.crucible.victim",
                    json.dumps(spec.to_json()),
                    v,
                    str(cfg.c2_lease_ms),
                    str(cfg.c2_heartbeat_ms),
                ],
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
                text=True,
            )
            procs[v] = p
            line = _readline(p, 90.0)
            if not line.startswith("CLAIMED"):
                raise RuntimeError(f"victim {v} did not claim a task: {line!r}")
            held[v] = line.split()[1]
        time.sleep(cfg.c2_heartbeat_ms * 1.5 / 1000)  # let each victim heartbeat at least once
        survivors = [f"survivor{i}" for i in range(cfg.c2_survivors)]
        for s in survivors:
            b.register_agent(s, "worker")
        claims: list[tuple[str, str, str, float]] = []  # (task, agent, reclaimed_from, t_claim)
        completions: dict[str, int] = defaultdict(int)
        lock = threading.Lock()
        stop = threading.Event()
        victim_tasks = set(held.values())

        def survivor(i: int) -> None:
            name = survivors[i]
            while not stop.is_set():
                t = b.claim_next_task(name, cfg.c2_lease_ms)
                if t is None:
                    time.sleep(cfg.c2_poll_ms / 1000)
                    continue
                with lock:
                    claims.append((t["id"], name, t["reclaimed_from"], _wall()))
                time.sleep(0.003)
                try:
                    b.complete_task(name, t["id"], t["version"])
                    with lock:
                        completions[t["id"]] += 1
                except ClaimConflict:
                    pass

        t_kill = _wall()
        for p in procs.values():
            p.kill()  # SIGKILL / TerminateProcess: no cleanup runs
        for p in procs.values():
            p.wait(timeout=30)
        threads = [threading.Thread(target=survivor, args=(i,), daemon=True) for i in range(len(survivors))]
        for t in threads:
            t.start()
        deadline = t_kill + (cfg.c2_lease_ms / 1000) * 3 + 20
        total = cfg.c2_tasks
        while _wall() < deadline:
            with lock:
                if len(completions) >= total:
                    break
            time.sleep(0.05)
        stop.set()
        for t in threads:
            t.join(timeout=30)
        final = {t["id"]: t for t in b.list_tasks()}
        delays: list[float] = []
        wrong_reclaimer = late = 0
        bar_ms = cfg.c2_lease_ms + cfg.c2_heartbeat_ms
        for v, tid in held.items():
            mine = [c for c in claims if c[0] == tid]
            if not mine:
                continue
            _, _, reclaimed_from, t_claim = mine[0]
            delay = (t_claim - t_kill) * 1000
            delays.append(delay)
            if reclaimed_from != v:
                wrong_reclaimer += 1
            if delay > bar_ms:
                late += 1
        orphans = sum(1 for tid in held.values() if final.get(tid, {}).get("status") != "done")
        other_stuck = sum(1 for tid, f in final.items() if tid not in victim_tasks and f["status"] != "done")
        double_done = sum(1 for n in completions.values() if n > 1)
        res.violations = {
            "orphaned_tasks": orphans + other_stuck,
            "reclaimed_late": late,
            "wrong_reclaimer": wrong_reclaimer,
            "double_completions": double_done,
        }
        res.metrics = {
            "reclaim_delay_ms_max": round(max(delays), 1) if delays else -1,
            "reclaim_delay_ms_min": round(min(delays), 1) if delays else -1,
            "reclaim_bar_ms": bar_ms,
            "reclaimed": len(delays),
        }
    except BaseException as exc:  # noqa: BLE001
        errors.append(exc)
    finally:
        for p in procs.values():
            if p.poll() is None:
                p.kill()
    res.set_errors(errors)
    return res.finish()


def _readline(p: subprocess.Popen[str], timeout: float) -> str:
    out: list[str] = []

    def reader() -> None:
        assert p.stdout is not None
        out.append(p.stdout.readline().strip())

    t = threading.Thread(target=reader, daemon=True)
    t.start()
    t.join(timeout)
    return out[0] if out else ""


# ============================================================================================================
# C3: concurrent assertions
# ============================================================================================================

CONFLICT_VALUES = [
    "MySQL 8",
    "MongoDB 7",
    "Redis 7",
    "Cassandra 4",
    "DynamoDB 2",
    "CockroachDB 23",
    "SQLite 3",
    "Oracle 19",
    "MariaDB 11",
    "Neo4j 5",
    "ClickHouse 24",
    "TiDB 7",
]


def c3(run: ArmRun, seed: int, cfg: L1Config) -> RunResult:
    n_same, n_conf = cfg.c3_same_value_agents, min(cfg.c3_conflicting_agents, len(CONFLICT_VALUES))
    res = RunResult(seed=seed, params={"same_value_agents": n_same, "conflicting_agents": n_conf})
    b = run.open("c3")
    rng = random.Random(seed)
    same_agents = [f"s{i:02d}" for i in range(n_same)]
    conf_agents = [f"c{i:02d}" for i in range(n_conf)]
    for a in [*same_agents, *conf_agents]:
        b.register_agent(a)
    spellings = ["PostgreSQL 16", "postgresql 16", "PostgreSQL  16", "POSTGRESQL 16"]
    jobs: list[tuple[str, str]] = [(a, rng.choice(spellings)) for a in same_agents]
    jobs += [(a, CONFLICT_VALUES[i]) for i, a in enumerate(conf_agents)]
    rng.shuffle(jobs)
    subject, predicate = "Orders service", "primary database"

    def worker(i: int) -> None:
        agent, value = jobs[i]
        b.assert_fact(agent, subject, predicate, value)

    errors = run_workers(len(jobs), worker)
    hist = b.facts(subject, predicate)
    active = [f for f in hist if f["status"] == "active"]
    by_value: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for f in active:
        by_value[normalize(f["value"])].append(f)
    duplicates = sum(len(v) - 1 for v in by_value.values())
    expected_active = 1 + n_conf
    ids = [f["fact_id"] for f in active]
    flagged = {frozenset((f["fact_id"], c)) for f in active for c in f["contradicts"] if c in ids}
    pairs = [
        frozenset((a["fact_id"], c["fact_id"]))
        for i, a in enumerate(active)
        for c in active[i + 1 :]
        if normalize(a["value"]) != normalize(c["value"])
    ]
    missed = sum(1 for p in pairs if p not in flagged)
    pg = next((f for f in active if normalize(f["value"]) == "postgresql 16"), None)
    lost_endorsements = len(set(same_agents) - set(pg["asserted_by"])) if pg else n_same
    res.violations = {
        "duplicate_facts": duplicates,
        "contradictions_missed": missed,
        "lost_endorsements": lost_endorsements,
        "wrong_active_count": abs(len(active) - expected_active),
    }
    res.metrics = {
        "active_facts": len(active),
        "expected_active": expected_active,
        "contradiction_pairs": len(pairs),
        "contradictions_flagged": len(pairs) - missed,
    }
    res.set_errors(errors)
    return res.finish()


# ============================================================================================================
# C4: dependency DAG
# ============================================================================================================


def c4(run: ArmRun, seed: int, cfg: L1Config) -> RunResult:
    layers = cfg.c4_layers
    res = RunResult(seed=seed, params={"layers": list(layers), "workers": cfg.c4_workers})
    b = run.open("c4")
    rng = random.Random(seed)
    ids: list[list[str]] = [[f"L{d}-{i:03d}" for i in range(n)] for d, n in enumerate(layers)]
    tasks: list[dict[str, Any]] = []
    deps_of: dict[str, list[str]] = {}
    for d, layer in enumerate(ids):
        for i, tid in enumerate(layer):
            deps: list[str] = []
            if d > 0:
                deps.append(ids[d - 1][i // 3])  # fan-out 3
                if len(ids[d - 1]) > 1 and rng.random() < 0.25:  # some diamonds: a second parent
                    other = rng.choice(ids[d - 1])
                    if other not in deps:
                        deps.append(other)
            deps_of[tid] = deps
            tasks.append({"id": tid, "title": tid, "priority": rng.randint(0, 2), "depends_on": deps})
    b.create_tasks(tasks)
    total = len(tasks)
    names = [f"w{i:02d}" for i in range(cfg.c4_workers)]
    for n in names:
        b.register_agent(n)
    t_claimed: dict[str, float] = {}
    t_complete_start: dict[str, float] = {}
    post_claim_bad: list[str] = []
    done = [0]
    lock = threading.Lock()
    deadline = _wall() + 120

    def worker(i: int) -> None:
        name, r = names[i], random.Random(seed * 100 + i)
        while _wall() < deadline:
            with lock:
                if done[0] >= total:
                    return
            t = b.claim_next_task(name, 600_000)
            if t is None:
                time.sleep(0.003)
                continue
            now = _wall()
            st = b.task_status(
                t["id"]
            )  # post-claim check: done is monotone, so "not done" now is a violation
            with lock:
                t_claimed[t["id"]] = now
                if st and any(d["status"] != "done" for d in st["dependencies"]):
                    post_claim_bad.append(t["id"])
            time.sleep(r.random() * 0.003)
            with lock:
                t_complete_start[t["id"]] = _wall()
            b.complete_task(name, t["id"], t["version"])
            with lock:
                done[0] += 1

    errors = run_workers(cfg.c4_workers, worker)
    early = set(post_claim_bad)
    for tid, deps in deps_of.items():
        for d in deps:
            if tid in t_claimed and d in t_complete_start and t_claimed[tid] < t_complete_start[d]:
                early.add(tid)  # claimed before its dependency had even begun to complete
    final = {t["id"]: t for t in b.list_tasks()}
    not_done = sum(1 for t in final.values() if t["status"] != "done")
    res.violations = {"started_before_deps_done": len(early), "tasks_not_completed": not_done}
    res.metrics = {"tasks": total, "edges": sum(len(v) for v in deps_of.values())}
    res.set_errors(errors)
    return res.finish()


# ============================================================================================================
# C5: tenant isolation
# ============================================================================================================

INJECTIONS = [
    "x'}) MATCH (n) DETACH DELETE n //",
    "'; DROP TABLE facts; --",
    '" OR 1=1 --',
    "a') MATCH (s) RETURN s //",
    "} MATCH (t:Task) SET t.status = 'done' //",
    "../../etc/passwd",
    "${jndi:ldap://x}",
    'SECRET-B* OR "SECRET" NEAR SECRET',
]


def _snapshot(b: Any, subjects: list[str], predicate: str) -> list[Any]:
    snap: list[Any] = []
    for s in subjects:
        snap.append([(f["fact_id"], f["value"], f["status"]) for f in b.facts(s, predicate)])
    snap.append([(t["id"], t["status"], t["version"], t["claimed_by"]) for t in b.list_tasks()])
    return snap


def c5(run: ArmRun, seed: int, cfg: L1Config) -> RunResult:
    res = RunResult(seed=seed, params={"workers": cfg.c5_workers, "injections": len(INJECTIONS)})
    a = run.open("c5a")
    bt = run.open("c5b")
    marker = f"SECRET-B-{seed}"
    subjects = [f"Secret-Project-B-{i}" for i in range(4)]
    bt.register_agent("bob")
    src_b = bt.add_source("doc://b-confidential")
    b_fact_ids = [
        bt.assert_fact("bob", s, "codename", f"{marker}-{i}", source_id=src_b)["fact_id"]
        for i, s in enumerate(subjects)
    ]
    bt.create_tasks([{"id": f"b-task-{i}", "title": f"{marker} task {i}"} for i in range(3)])
    t = bt.claim_next_task("bob", 600_000)
    done = bt.complete_task(
        "bob", t["id"], t["version"], [{"id": "b-art-1", "kind": "file", "uri": f"{marker}.md"}]
    )
    b_dec = bt.record_decision("bob", "b-task-1", f"{marker} decision", b_fact_ids[:2])
    b_ids = [*b_fact_ids, "b-task-0", "b-task-1", "b-task-2", "b-art-1", b_dec, src_b, *done["artifact_ids"]]
    before = _snapshot(bt, subjects, "codename")

    a.register_agent("alice")
    a.create_tasks([{"id": f"a-task-{i}", "title": f"a task {i}"} for i in range(5)])
    a_fact = a.assert_fact("alice", "A public project", "codename", "daffodil")["fact_id"]

    def leaked(obj: Any) -> int:
        text = json.dumps(obj, default=str)
        return int(marker in text) + sum(1 for i in [*b_ids, bt.tenant] if i in text)  # type: ignore[attr-defined]

    probes: list[tuple[str, Callable[[], Any]]] = []
    for s in subjects:
        probes += [
            (f"recall:{s}", lambda s=s: a.recall("alice", f"{s} codename {marker}", k=20)),
            (f"recall-project:{s}", lambda s=s: a.recall("alice", s, scope="project:b", k=20)),
            (f"facts:{s}", lambda s=s: a.facts(s, "codename")),
            (f"as_of:{s}", lambda s=s: a.as_of(s, "codename", 4_000_000_000_000)),
            (f"recall-asof:{s}", lambda s=s: a.recall("alice", s, k=20, as_of=4_000_000_000_000)),
        ]
    probes += [("recall:marker", lambda: a.recall("alice", marker, k=50))]
    for tid in ("b-task-0", "b-task-1", "b-task-2"):
        probes += [
            (f"task_status:{tid}", lambda tid=tid: a.task_status(tid)),
            (f"complete:{tid}", lambda tid=tid: a.complete_task("alice", tid, 1)),
            (f"heartbeat:{tid}", lambda tid=tid: a.heartbeat("alice", tid, 60_000)),
            (f"decision:{tid}", lambda tid=tid: a.record_decision("alice", tid, "hijack", b_fact_ids[:1])),
            (f"handoff:{tid}", lambda tid=tid: a.handoff("alice", "bob", tid, "n", fact_ids=b_fact_ids[:1])),
        ]
    probes += [
        ("handoff:b-art", lambda: a.handoff("alice", "alice", "a-task-0", "n", artifact_ids=["b-art-1"])),
        ("why:b-decision", lambda: a.why(b_dec)),
        ("why:b-fact", lambda: a.why(b_fact_ids[0])),
        ("forget:b-source", lambda: a.forget_source(src_b)),
        ("assert-with-b-source", lambda: a.assert_fact("alice", "x", "y", "z", source_id=src_b)),
        ("derive-from-b-fact", lambda: a.assert_fact("alice", "x", "y2", "z2", derived_from=[b_fact_ids[0]])),
        ("claim", lambda: a.claim_next_task("alice", 600_000)),
        ("list_tasks", lambda: a.list_tasks()),
        ("knew_at:bob", lambda: a.knew_at("bob", 100)),
    ]
    for guess in (
        f"plexus_t_{bt.tenant}",  # type: ignore[attr-defined]
        f"../{bt.tenant}",  # type: ignore[attr-defined]
        f"{bt.tenant}/../x",  # type: ignore[attr-defined]
        bt.tenant.upper(),  # type: ignore[attr-defined]
        f"{bt.tenant} ",  # type: ignore[attr-defined]
        "a'); MATCH (n) DETACH DELETE n //",
        "..\\..\\" + bt.tenant,  # type: ignore[attr-defined]
    ):
        probes.append((f"open-tenant:{guess[:30]}", lambda g=guess: _guess_tenant(run, g, marker, b_ids)))
    if hasattr(a, "rt"):  # Plexus: the tenant is bound to the connection, a header must not rebind it
        probes.append(
            (
                "header-spoof",
                lambda: a.rt.tenant_of({"x-plexus-tenant": bt.tenant}),  # type: ignore[attr-defined]
            )
        )
    for inj in INJECTIONS:
        probes += [
            (f"inj-assert:{inj[:12]}", lambda inj=inj: a.assert_fact("alice", inj, inj, inj)),
            (f"inj-recall:{inj[:12]}", lambda inj=inj: a.recall("alice", inj, k=20)),
            (f"inj-facts:{inj[:12]}", lambda inj=inj: a.facts(inj, inj)),
            (f"inj-agent:{inj[:12]}", lambda inj=inj: a.register_agent(inj)),
            (f"inj-task:{inj[:12]}", lambda inj=inj: a.task_status(inj)),
            (
                f"inj-tasks:{inj[:12]}",
                lambda inj=inj: a.create_tasks([{"id": f"inj-{abs(hash(inj))}", "title": inj}]),
            ),
            (f"inj-scope:{inj[:12]}", lambda inj=inj: a.recall("alice", "q", scope=f"project:{inj}")),
        ]
    n_leaked = 0
    unexpected: list[BaseException] = []
    lock = threading.Lock()
    queue = list(enumerate(probes))
    probe_log: list[tuple[str, int]] = []

    def worker(_: int) -> None:
        nonlocal n_leaked
        while True:
            with lock:
                if not queue:
                    return
                _, (name, fn) = queue.pop()
            try:
                out = fn()
            except DENIED:
                continue
            except Exception as exc:  # noqa: BLE001
                with lock:
                    unexpected.append(RuntimeError(f"{name}: {type(exc).__name__}: {exc}"))
                continue
            k = leaked(out)
            if k:
                with lock:
                    n_leaked += k
                    probe_log.append((name, k))

    errors = run_workers(cfg.c5_workers, worker)
    after = _snapshot(bt, subjects, "codename")
    cross_writes = int(before != after)
    a_ok = a.facts("A public project", "codename")
    own_intact = int(not a_ok or a_ok[0]["fact_id"] != a_fact)
    res.violations = {
        "rows_leaked": n_leaked,
        "cross_tenant_writes": cross_writes,
        "own_data_damaged": own_intact,
    }
    res.metrics = {"probes": len(probes), "tenant_isolation": 1}
    res.details = {"leaking_probes": probe_log[:10]}
    res.set_errors([*errors, *unexpected])
    return res.finish()


def _guess_tenant(run: ArmRun, guess: str, marker: str, b_ids: list[str]) -> Any:
    """Try to address B's store by a guessed tenant name; whatever it returns must hold none of B's data."""
    g = run.open("guess", tenant=guess)  # InvalidTenant for anything that is not a plain tenant name
    return {
        "recall": g.recall("alice", f"Secret-Project-B {marker}", k=20),
        "tasks": g.list_tasks(),
        "facts": g.facts("Secret-Project-B-0", "codename"),
    }


# ============================================================================================================
# C6: as-of queries
# ============================================================================================================


def c6(run: ArmRun, seed: int, cfg: L1Config) -> RunResult:
    res = RunResult(
        seed=seed,
        params={"subjects": cfg.c6_subjects, "versions": cfg.c6_versions, "queries": cfg.c6_queries},
    )
    b = run.open("c6")
    rng = random.Random(seed)
    b.register_agent("writer")
    base = 1_700_000_000_000 + rng.randint(0, 10**6)
    truth: dict[str, list[tuple[int, str]]] = {}
    for s in range(cfg.c6_subjects):
        t, vers = base + rng.randint(0, 500), []
        for k in range(cfg.c6_versions):
            vers.append((t, f"build {k + 1}.{s}.{rng.randint(10, 99)}"))
            t += 1000 + rng.randint(0, 400)
        truth[f"Service-{s}"] = vers

    def write(i: int) -> None:
        for s in range(i, cfg.c6_subjects, cfg.c6_workers):
            subject = f"Service-{s}"
            for t, v in truth[subject]:
                b.assert_fact("writer", subject, "release", v, now=t)

    errors = run_workers(cfg.c6_workers, write)
    wrong = asked = 0
    bad: list[Any] = []

    def expected(subject: str, t: int) -> str | None:
        cur = None
        for vt, v in truth[subject]:
            if vt <= t:
                cur = v
        return cur

    for subject, vers in truth.items():
        times = [vt for vt, _ in vers]
        qs = [rng.randint(times[0] - 700, times[-1] + 2500) for _ in range(cfg.c6_queries - 2)]
        qs += [times[0], times[-1]]  # exact boundaries
        for q in qs:
            got = b.as_of(subject, "release", q)
            exp = expected(subject, q)
            asked += 1
            if (got["value"] if got else None) != exp:
                wrong += 1
                if len(bad) < 3:
                    bad.append({"subject": subject, "t": q, "expected": exp, "got": got and got["value"]})
    res.violations = {"wrong_version_answers": wrong}
    res.metrics = {"queries": asked}
    res.details = {"examples": bad}
    res.set_errors(errors)
    return res.finish()


# ============================================================================================================
# C7: paraphrases
# ============================================================================================================

# (subject, predicate, value A, value B): the same statement in different words. 'kind' says how different.
PARAPHRASES: list[tuple[str, str, str, str, str]] = [
    ("Payments service", "owner", "The platform team owns it.", "The platform team owns it", "punctuation"),
    (
        "Search index",
        "refresh interval",
        "Refreshed every 30 seconds",
        "refreshed every 30 seconds.",
        "punctuation",
    ),
    ("Auth gateway", "log level", "Set to debug in staging", "Set to debug in staging!", "punctuation"),
    ("Billing job", "schedule", "Runs nightly at 02:00 UTC", "Runs every night at 02:00 UTC", "light"),
    (
        "Notes API",
        "rate limit",
        "100 requests per minute per key",
        "Each key is limited to 100 requests per minute",
        "light",
    ),
    (
        "Cache layer",
        "eviction policy",
        "Least recently used entries are evicted first",
        "Evicts the least recently used entries first",
        "light",
    ),
    ("Mobile app", "minimum os", "Requires iOS 16 or newer", "Needs iOS 16 or later", "light"),
    (
        "Data lake",
        "retention",
        "Raw events are kept for 90 days",
        "Events are retained in raw form for 90 days",
        "light",
    ),
    (
        "Deploy pipeline",
        "approval",
        "Production deploys need two reviewers",
        "Two reviewers must approve every production deploy",
        "heavy",
    ),
    (
        "Incident process",
        "paging",
        "The on-call engineer is paged first",
        "First to be paged is whoever is on call",
        "heavy",
    ),
    (
        "Onboarding doc",
        "location",
        "Stored in the team handbook wiki",
        "You can find it in the wiki handbook of the team",
        "heavy",
    ),
    (
        "Metrics stack",
        "dashboard tool",
        "Grafana shows all service metrics",
        "All service metrics are visualised in Grafana",
        "heavy",
    ),
]
# Different statements that look alike: merging these would lose information.
CONTROLS: list[tuple[str, str, str, str]] = [
    ("Gateway service", "language", "Written in Go", "Written in Rust"),
    ("Orders queue", "retry limit", "Retries 3 times before failing", "Retries 5 times before failing"),
    ("Reports job", "runs on", "Runs on Mondays", "Runs on Fridays"),
    ("Customer db", "region", "Hosted in eu-west", "Hosted in us-east"),
]


def _run_pairs(b: Any, pairs: list[tuple[str, str, str, str]], concurrent: bool, seed: int) -> list[int]:
    """Assert both values of every pair (by two different agents); returns active-fact counts per pair."""
    rng = random.Random(seed)
    jobs: list[tuple[str, str, str, str]] = []
    for i, (subject, predicate, va, vb) in enumerate(pairs):
        agents = [f"pa{i:02d}", f"pb{i:02d}"]
        rng.shuffle(agents)
        jobs += [(agents[0], subject, predicate, va), (agents[1], subject, predicate, vb)]
    for ag, *_ in jobs:
        b.register_agent(ag)
    order = list(range(len(jobs)))
    if concurrent:
        rng.shuffle(order)

        def w(i: int) -> None:
            ag, s, p, v = jobs[order[i]]
            b.assert_fact(ag, s, p, v)

        errors = run_workers(len(jobs), w)
        if errors:
            raise errors[0]
    else:
        for j in order:
            ag, s, p, v = jobs[j]
            b.assert_fact(ag, s, p, v)
    return [sum(1 for f in b.facts(s, p) if f["status"] == "active") for s, p, _, _ in pairs]


def c7(run: ArmRun, seed: int, cfg: L1Config) -> RunResult:
    corpus = PARAPHRASES[: cfg.c7_pairs]
    res = RunResult(seed=seed, params={"paraphrase_pairs": len(corpus), "control_pairs": len(CONTROLS)})
    pairs = [(s, p, a, b_) for s, p, a, b_, _ in corpus] + list(CONTROLS)
    seq = _run_pairs(run.open("c7s"), pairs, concurrent=False, seed=seed)
    conc = _run_pairs(run.open("c7c"), pairs, concurrent=True, seed=seed)
    n = len(corpus)
    miss_seq, miss_conc = sum(1 for c in seq[:n] if c > 1), sum(1 for c in conc[:n] if c > 1)
    false_seq = sum(1 for c in seq[n:] if c < 2)
    false_conc = sum(1 for c in conc[n:] if c < 2)
    res.violations = {
        "extra_duplicates_under_concurrency": max(0, miss_conc - miss_seq),
        "false_merges": false_seq + false_conc,
    }
    by_kind: dict[str, list[int]] = defaultdict(lambda: [0, 0])
    for (_, _, _, _, kind), c in zip(corpus, seq[:n], strict=True):
        by_kind[kind][0] += 1
        by_kind[kind][1] += int(c > 1)
    res.metrics = {
        "pairs": n,
        "misses_sequential": miss_seq,
        "misses_concurrent": miss_conc,
        "miss_rate_sequential": round(miss_seq / n, 3),
        "miss_rate_concurrent": round(miss_conc / n, 3),
    }
    res.details = {"misses_by_kind": {k: {"pairs": v[0], "missed": v[1]} for k, v in by_kind.items()}}
    return res.finish()


# ============================================================================================================
# C8: forget by source
# ============================================================================================================


def c8(run: ArmRun, seed: int, cfg: L1Config) -> RunResult:
    res = RunResult(
        seed=seed,
        params={
            "sources": cfg.c8_sources,
            "facts_per_source": cfg.c8_facts_per_source,
            "forgotten_sources": cfg.c8_forgotten_sources,
        },
    )
    b = run.open("c8")
    rng = random.Random(seed)
    b.register_agent("curator")
    sources = [b.add_source(f"doc://handbook-{i}") for i in range(cfg.c8_sources)]
    forget_idx = set(rng.sample(range(cfg.c8_sources), cfg.c8_forgotten_sources))
    facts: dict[str, dict[str, Any]] = {}  # fact_id -> {query, derived_from_source}
    topics = ["vacation", "expenses", "security", "onboarding", "travel", "equipment", "holidays", "benefits"]
    for si, sid in enumerate(sources):
        for k in range(cfg.c8_facts_per_source):
            topic = topics[k % len(topics)]
            subj, pred, val = (
                f"Handbook {si} {topic} rule {k}",
                f"{topic} guideline {si}-{k}",
                f"item {si}.{k} says {topic} approval is required",
            )
            fid = b.assert_fact("curator", subj, pred, val, source_id=sid)["fact_id"]
            facts[fid] = {"query": f"{subj} {pred} {val}", "root": si, "subject": subj, "predicate": pred}
        # second-order facts derived from the first fact of this source (not linked to the source directly)
        first = next(f for f, v in facts.items() if v["root"] == si)
        for k in range(2):
            subj, pred, val = (
                f"Summary {si}",
                f"digest point {k}",
                f"digest {si}.{k} summarises handbook {si}",
            )
            fid = b.assert_fact("curator", subj, pred, val, derived_from=[first])["fact_id"]
            facts[fid] = {"query": f"{subj} {pred} {val}", "root": si, "subject": subj, "predicate": pred}
    expected_gone = {f for f, v in facts.items() if v["root"] in forget_idx}
    expected_kept = set(facts) - expected_gone
    for f in list(facts)[:3]:  # sanity: before forgetting, probes find their facts
        hits = b.recall("curator", facts[f]["query"], k=10)
        assert any(h["fact_id"] == f for h in hits), "recall cannot find a fact before forgetting"

    def forget(i: int) -> None:
        for si in sorted(forget_idx)[i::2]:
            b.forget_source(sources[si])

    errors = run_workers(max(1, min(2, len(forget_idx))), forget)
    returned: set[str] = set()
    over_forgotten = 0
    lock = threading.Lock()
    ids = list(facts)

    def probe(i: int) -> None:
        nonlocal over_forgotten
        for fid in ids[i::4]:
            got = {h["fact_id"] for h in b.recall("curator", facts[fid]["query"], k=10)}
            with lock:
                returned.update(got & expected_gone)
                if fid in expected_kept and fid not in got:
                    over_forgotten += 1

    errors += run_workers(4, probe)
    not_marked = 0
    for fid in expected_gone:  # the fact itself must read as forgotten, not just fall out of the top-k
        v = facts[fid]
        mine = [f for f in b.facts(v["subject"], v["predicate"]) if f["fact_id"] == fid]
        if not mine or mine[0]["status"] == "active":
            not_marked += 1
    res.violations = {"derived_facts_still_returned": len(returned), "not_marked_forgotten": not_marked}
    res.metrics = {
        "facts": len(facts),
        "forgotten_expected": len(expected_gone),
        "kept_but_not_found": over_forgotten,
    }
    res.set_errors(errors)
    return res.finish()


# ============================================================================================================
# driver
# ============================================================================================================


def _cases(test: str, cfg: L1Config) -> list[dict[str, Any]]:
    if test == "C1":
        return [{"workers": w} for w in cfg.c1_workers]
    return [{}]


def run_test(
    env: Env, arm: str, test: str, cfg: L1Config, log: Callable[[str], None] = print
) -> dict[str, Any]:
    fn = {"C1": c1, "C2": c2, "C3": c3, "C4": c4, "C5": c5, "C6": c6, "C7": c7, "C8": c8}[test]
    runs: list[RunResult] = []
    for params in _cases(test, cfg):
        for seed in cfg.seeds:
            t0 = _wall()
            run = ArmRun(env, arm)
            try:
                r = fn(run, seed, cfg, **params)
            except Unsupported as exc:
                r = unsupported_result(seed, dict(params), exc)
            except Exception as exc:  # noqa: BLE001 - a crashed run is a failed run, recorded, never hidden
                r = RunResult(seed=seed, params=dict(params))
                r.set_errors([exc])
                r.violations["crashed"] = 1
                r.finish()
            finally:
                run.cleanup()
            r.duration_s = _wall() - t0
            runs.append(r)
            flag = "ok" if r.passed else "FAIL"
            log(
                f"  {arm:>3} {test} {params or ''} seed={seed}: {flag} {r.violations if not r.passed else ''} ({r.duration_s:.1f}s)"
            )
    out = aggregate(runs)
    out["runs_detail"] = [r.to_json() for r in runs]
    return out


def run_l1(env: Env, cfg: L1Config, log: Callable[[str], None] = print) -> dict[str, Any]:
    """Run the selected tests on the selected arms. Returns ``{arm: {test: result}}``."""
    results: dict[str, dict[str, Any]] = {}
    for arm in cfg.arms:
        results[arm] = {}
        for test in cfg.tests:
            results[arm][test] = run_test(env, arm, test, cfg, log)
    return results
