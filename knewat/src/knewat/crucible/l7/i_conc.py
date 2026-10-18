"""Family I4: conflicting concurrent writers (lost update on a counter, write skew across two tasks).

SQLite: every thread has its own connection (WAL, synchronous=NORMAL, ``busy_timeout`` = 10000 ms, explicitly set).
FalkorDB: one pooled client (512 connections), one graph, product schema. All threads start on a barrier.
"""

from __future__ import annotations

import random
import sqlite3
import threading
import time
import uuid
from collections.abc import Callable
from pathlib import Path
from typing import Any

from redis.exceptions import WatchError

from knewat.crucible.l7.i_arms import SLUG
from knewat.graph.client import GraphClient
from knewat.graph.schema import apply_schema
from knewat.graph.tenancy import graph_name

BUSY_MS = 10_000
MODE_BUDGET_S = 240.0  # a mode that has not finished by then is stopped and reported as incomplete
A_MODES = ("naive", "atomic", "cas", "pessimistic")


def _sqlite(path: str) -> sqlite3.Connection:
    c = sqlite3.connect(path, isolation_level=None, timeout=BUSY_MS / 1000)
    c.execute(f"PRAGMA busy_timeout = {BUSY_MS}")
    c.execute("PRAGMA journal_mode = WAL")
    c.execute("PRAGMA synchronous = NORMAL")
    return c


class FDb:
    """FalkorDB handle for one throwaway graph."""

    def __init__(self, host: str, port: int, tag: str):
        self.c = GraphClient(host=host, port=port, password="", max_connections=512)
        clean = "".join(ch for ch in tag.lower() if ch.isalnum())
        self.name = graph_name(f"l7i_{clean}_{uuid.uuid4().hex[:6]}")
        self.c.delete_graph(self.name)
        apply_schema(self.c, self.name)
        self.g = self.c.graph(self.name)

    def q(self, cy: str, p: dict | None = None):
        return self.g.query(cy, p, 10_000)

    def ro(self, cy: str, p: dict | None = None):
        return self.g.ro_query(cy, p, 10_000)

    def drop(self) -> None:
        self.c.delete_graph(self.name)
        self.c.close()


def _run_threads(w: int, body: Callable[[int], None], budget_s: float | None = None) -> tuple[float, bool]:
    budget_s = MODE_BUDGET_S if budget_s is None else budget_s
    start = threading.Barrier(w + 1)

    def go(i: int) -> None:
        start.wait()
        body(i)

    ths = [threading.Thread(target=go, args=(i,), daemon=True) for i in range(w)]
    for t in ths:
        t.start()
    start.wait()
    t0 = time.perf_counter()
    complete = True
    for t in ths:
        t.join(max(0.1, budget_s - (time.perf_counter() - t0)))
        if t.is_alive():
            complete = False
    return time.perf_counter() - t0, complete


# ------------------------------------------------------------------------------------------------ I4a
def i4a_sqlite(mode: str, w: int, ops: int, root: str) -> dict[str, Any]:
    path = str(Path(root) / f"i4a_{mode}_{w}_{uuid.uuid4().hex[:4]}.db")
    c = _sqlite(path)
    c.execute("CREATE TABLE c (id INTEGER PRIMARY KEY, n INTEGER, version INTEGER)")
    c.execute("INSERT INTO c VALUES (1, 0, 0)")
    c.close()
    acked = [0] * w
    errors: list[str] = []
    retries = [0] * w
    lk = threading.Lock()

    def body(i: int) -> None:
        db = _sqlite(path)
        for _ in range(ops):
            try:
                if mode == "naive":
                    n = db.execute("SELECT n FROM c WHERE id=1").fetchone()[0]
                    db.execute("UPDATE c SET n=? WHERE id=1", (n + 1,))
                elif mode == "atomic":
                    db.execute("UPDATE c SET n = n + 1 WHERE id=1")
                elif mode == "cas":
                    while True:
                        n, v = db.execute("SELECT n, version FROM c WHERE id=1").fetchone()
                        cur = db.execute(
                            "UPDATE c SET n=?, version=version+1 WHERE id=1 AND version=?", (n + 1, v)
                        )
                        if cur.rowcount == 1:
                            break
                        retries[i] += 1
                        time.sleep(random.uniform(0, 0.002))
                else:  # pessimistic
                    db.execute("BEGIN IMMEDIATE")
                    n = db.execute("SELECT n FROM c WHERE id=1").fetchone()[0]
                    db.execute("UPDATE c SET n=? WHERE id=1", (n + 1,))
                    db.execute("COMMIT")
                acked[i] += 1
            except sqlite3.Error as exc:
                if db.in_transaction:
                    db.execute("ROLLBACK")
                with lk:
                    errors.append(f"{type(exc).__name__}: {exc}")
        db.close()

    wall, complete = _run_threads(w, body)
    c = _sqlite(path)
    final = c.execute("SELECT n FROM c WHERE id=1").fetchone()[0]
    c.close()
    return _a_row("SQLite", mode, w, ops, sum(acked), final, errors, sum(retries), wall, complete)


def i4a_falkor(mode: str, w: int, ops: int, host: str, port: int) -> dict[str, Any]:
    f = FDb(host, port, f"a{mode[:3]}{w}")
    f.q("CREATE (:Counter {id: 'c', n: 0, version: 0})")
    acked = [0] * w
    retries = [0] * w
    errors: list[str] = []
    lk = threading.Lock()
    conn = f.c.db.connection

    def body(i: int) -> None:
        for _ in range(ops):
            try:
                if mode == "naive":
                    n = f.ro("MATCH (c:Counter {id: 'c'}) RETURN c.n").result_set[0][0]
                    f.q("MATCH (c:Counter {id: 'c'}) SET c.n = $n", {"n": n + 1})
                elif mode == "atomic":
                    f.q("MATCH (c:Counter {id: 'c'}) SET c.n = c.n + 1")
                elif mode == "cas":
                    while True:
                        n, v = f.ro("MATCH (c:Counter {id: 'c'}) RETURN c.n, c.version").result_set[0]
                        r = f.q(
                            "MATCH (c:Counter {id: 'c'}) WHERE c.version = $v SET c.n = $n, c.version = c.version + 1 RETURN c.n",
                            {"n": n + 1, "v": v},
                        )
                        if r.result_set:
                            break
                        retries[i] += 1
                        time.sleep(random.uniform(0, 0.002))
                else:  # pessimistic: WATCH the graph key, read, MULTI/EXEC the write, retry when EXEC aborts
                    while True:
                        with conn.pipeline(transaction=True) as p:
                            try:
                                p.watch(f.name)
                                rd = p.execute_command(
                                    "GRAPH.RO_QUERY", f.name, "MATCH (c:Counter {id: 'c'}) RETURN c.n"
                                )
                                n = int(rd[1][0][0])
                                p.multi()
                                p.execute_command(
                                    "GRAPH.QUERY",
                                    f.name,
                                    f"CYPHER n={n + 1} MATCH (c:Counter {{id: 'c'}}) SET c.n = $n",
                                )
                                p.execute()
                                break
                            except WatchError:
                                retries[i] += 1
                                time.sleep(random.uniform(0, 0.002))
                acked[i] += 1
            except Exception as exc:  # noqa: BLE001
                with lk:
                    errors.append(f"{type(exc).__name__}: {str(exc)[:80]}")

    wall, complete = _run_threads(w, body)
    final = f.ro("MATCH (c:Counter {id: 'c'}) RETURN c.n").result_set[0][0]
    f.drop()
    return _a_row("FalkorDB", mode, w, ops, sum(acked), final, errors, sum(retries), wall, complete)


def _a_row(
    backend: str,
    mode: str,
    w: int,
    ops: int,
    acked: int,
    final: int,
    errors: list[str],
    retries: int,
    wall: float,
    complete: bool,
) -> dict[str, Any]:
    kinds: dict[str, int] = {}
    for e in errors:
        kinds[e[:70]] = kinds.get(e[:70], 0) + 1
    return {
        "backend": backend, "mode": mode, "W": w, "ops": ops, "attempted": w * ops, "acked": acked, "final": final,
        "lost_acked": acked - final, "lost_vs_attempted": w * ops - final, "errors": len(errors),
        "error_kinds": kinds, "retries": retries, "wall_s": round(wall, 2), "completed_in_budget": complete,
        "busy_timeout_ms": BUSY_MS if backend == "SQLite" else None,
    }  # fmt: skip


# ------------------------------------------------------------------------------------------------ I4b
def _pair_ids(r: int) -> tuple[str, str]:
    return f"p{r}a", f"p{r}b"


def i4b_run(
    backend: str, mode: str, rounds: int, think_ms: float, host: str, port: int, root: str
) -> dict[str, Any]:
    think = think_ms / 1000
    errors: list[str] = []
    lk = threading.Lock()
    barrier = threading.Barrier(2)
    f: FDb | None = None
    path = ""
    if backend == "FalkorDB":
        f = FDb(host, port, f"b{mode[:4]}")
        f.q(
            "UNWIND range(0, $n - 1) AS i CREATE (:Task {id: 'p' + toString(i) + 'a', status: 'open'}), (:Task {id: 'p' + toString(i) + 'b', status: 'open'})",
            {"n": rounds},
        )
        conn = f.c.db.connection
    else:
        path = str(Path(root) / f"i4b_{mode}_{uuid.uuid4().hex[:4]}.db")
        c = _sqlite(path)
        c.execute("CREATE TABLE tasks (id TEXT PRIMARY KEY, status TEXT, claimed_by TEXT)")
        c.executemany(
            "INSERT INTO tasks VALUES (?, 'open', NULL)", [(x,) for r in range(rounds) for x in _pair_ids(r)]
        )
        c.close()

    def claim_falkor(me: int, r: int) -> None:
        assert f is not None
        a, b = _pair_ids(r)
        mine, other = (a, b) if me == 0 else (b, a)
        agent = f"agent{me}"
        if mode == "one statement":
            f.q(
                "MATCH (a:Task {id: $a}), (b:Task {id: $b}) WHERE a.status = 'open' AND b.status = 'open' "
                "WITH a, b MATCH (m:Task {id: $mine}) SET m.status = 'claimed', m.claimed_by = $agent",
                {"a": a, "b": b, "mine": mine, "agent": agent},
            )
        elif mode == "multi-statement no txn":
            n = f.ro(
                "MATCH (t:Task) WHERE t.id IN [$a, $b] AND t.status = 'claimed' RETURN count(t)",
                {"a": a, "b": b},
            ).result_set[0][0]
            if think:
                time.sleep(think)
            if n == 0:
                f.q(
                    "MATCH (m:Task {id: $mine}) SET m.status = 'claimed', m.claimed_by = $agent",
                    {"mine": mine, "agent": agent},
                )
        else:  # WATCH + MULTI/EXEC, retried
            while True:
                with conn.pipeline(transaction=True) as p:
                    try:
                        p.watch(f.name)
                        rd = p.execute_command(
                            "GRAPH.RO_QUERY",
                            f.name,
                            f"CYPHER a='{a}' b='{b}' MATCH (t:Task) WHERE t.id IN [$a, $b] AND t.status = 'claimed' RETURN count(t)",
                        )
                        n = int(rd[1][0][0])
                        if think:
                            time.sleep(think)
                        p.multi()
                        if n == 0:
                            p.execute_command(
                                "GRAPH.QUERY",
                                f.name,
                                f"CYPHER mine='{mine}' agent='{agent}' MATCH (m:Task {{id: $mine}}) SET m.status = 'claimed', m.claimed_by = $agent",
                            )
                        p.execute()
                        break
                    except WatchError:
                        time.sleep(random.uniform(0, 0.002))

    def claim_sqlite(db: sqlite3.Connection, me: int, r: int) -> None:
        a, b = _pair_ids(r)
        mine = a if me == 0 else b
        agent = f"agent{me}"
        if mode == "one statement":
            db.execute(
                "UPDATE tasks SET status='claimed', claimed_by=? WHERE id=? AND NOT EXISTS "
                "(SELECT 1 FROM tasks WHERE id IN (?, ?) AND status='claimed')",
                (agent, mine, a, b),
            )
            return
        begin = {"BEGIN IMMEDIATE": "BEGIN IMMEDIATE", "BEGIN DEFERRED": "BEGIN DEFERRED"}.get(mode)
        if begin:
            db.execute(begin)
        try:
            n = db.execute(
                "SELECT count(*) FROM tasks WHERE id IN (?, ?) AND status='claimed'", (a, b)
            ).fetchone()[0]
            if think:
                time.sleep(think)
            if n == 0:
                db.execute("UPDATE tasks SET status='claimed', claimed_by=? WHERE id=?", (agent, mine))
            if begin:
                db.execute("COMMIT")
        except BaseException:
            if db.in_transaction:
                db.execute("ROLLBACK")
            raise

    def body(me: int) -> None:
        db = _sqlite(path) if backend == "SQLite" else None
        for r in range(rounds):
            try:
                barrier.wait(60)
            except threading.BrokenBarrierError:
                return
            try:
                if db is None:
                    claim_falkor(me, r)
                else:
                    claim_sqlite(db, me, r)
            except Exception as exc:  # noqa: BLE001
                with lk:
                    errors.append(f"{type(exc).__name__}: {str(exc)[:70]}")
        if db is not None:
            db.close()

    _run_threads_plain(body, 2)
    both = none = 0
    if f is not None:
        rows = f.ro(
            "MATCH (t:Task) WHERE t.status = 'claimed' RETURN substring(t.id, 0, size(t.id) - 1) AS p, count(t) AS n"
        ).result_set
        per = {r[0]: r[1] for r in rows}
        both = sum(1 for v in per.values() if v >= 2)
        none = rounds - len(per)
        f.drop()
    else:
        c = _sqlite(path)
        per = {
            r[0]: r[1]
            for r in c.execute(
                "SELECT substr(id, 1, length(id) - 1), count(*) FROM tasks WHERE status='claimed' GROUP BY 1"
            )
        }
        both = sum(1 for v in per.values() if v >= 2)
        none = rounds - len(per)
        c.close()
    kinds: dict[str, int] = {}
    for e in errors:
        kinds[e] = kinds.get(e, 0) + 1
    return {
        "backend": backend, "mode": mode, "think_ms": think_ms, "rounds": rounds, "violations": both, "both": both,
        "none": none, "errors": len(errors), "error_kinds": dict(sorted(kinds.items(), key=lambda kv: -kv[1])[:4]),
    }  # fmt: skip


def _run_threads_plain(body: Callable[[int], None], n: int) -> None:
    ths = [threading.Thread(target=body, args=(i,), daemon=True) for i in range(n)]
    for t in ths:
        t.start()
    for t in ths:
        t.join(MODE_BUDGET_S * 2)


def rerun_a_cell(
    backend: str, mode: str, w: int, ops: int, budget_s: float, host: str, port: int, root: str
) -> dict[str, Any]:
    """Re-run ONE I4a cell with a longer budget (a cell that hit ``MODE_BUDGET_S`` is incomplete, its numbers are artefacts)."""
    global MODE_BUDGET_S
    old, MODE_BUDGET_S = MODE_BUDGET_S, budget_s
    try:
        r = i4a_sqlite(mode, w, ops, root) if backend == "SQLite" else i4a_falkor(mode, w, ops, host, port)
    finally:
        MODE_BUDGET_S = old
    r["rerun_budget_s"] = budget_s
    return r


def run_i4(host: str, port: int, root: str, sc: dict[str, Any], log: Callable[[str], None]) -> dict[str, Any]:
    out: dict[str, Any] = {"a": [], "b": [], "busy_timeout_ms": BUSY_MS, "mode_budget_s": MODE_BUDGET_S}
    for w in sc["i4_w"]:
        for backend in ("SQLite", "FalkorDB"):
            for mode in A_MODES:
                log(f"I4a {backend} {mode} W={w}")
                try:
                    r = (
                        i4a_sqlite(mode, w, sc["i4_ops"], root)
                        if backend == "SQLite"
                        else i4a_falkor(mode, w, sc["i4_ops"], host, port)
                    )
                except Exception as exc:  # noqa: BLE001
                    r = {
                        "backend": backend,
                        "mode": mode,
                        "W": w,
                        "ops": sc["i4_ops"],
                        "attempted": w * sc["i4_ops"],
                        "acked": 0,
                        "final": -1,
                        "lost_acked": -1,
                        "errors": 1,
                        "retries": 0,
                        "crash": f"{type(exc).__name__}: {exc}",
                    }
                out["a"].append(r)
    rounds = sc["i4b_rounds"]
    plan = [
        ("SQLite", "one statement", (0,)), ("FalkorDB", "one statement", (0,)),
        ("SQLite", "multi-statement no txn", (0, 2)), ("FalkorDB", "multi-statement no txn", (0, 2)),
        ("SQLite", "BEGIN IMMEDIATE", (0, 2)), ("SQLite", "BEGIN DEFERRED", (0, 2)),
        ("FalkorDB", "WATCH+MULTI/EXEC", (0, 2)),
    ]  # fmt: skip
    for backend, mode, thinks in plan:
        for think in thinks:
            log(f"I4b {backend} {mode} think={think}ms")
            out["b"].append(i4b_run(backend, mode, rounds, think, host, port, root))
    _ = SLUG
    return out
