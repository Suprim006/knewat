"""Family E: consistent reads under concurrent writes (multi-hop snapshot).

Writers append lineage (a fact derived from existing facts of an append-target source ``A`` plus a decision based on it,
in ONE statement / transaction / locked append) and quarantine whole trees of the never-appended sources ``Q``; readers
run blast-radius reads. Invariants checked on every read (no LLM):

* **V1** every decision in the answer has all its based-on facts in the answer;
* **V2** for a ``Q`` source the answer shows all facts quarantined or none of them;
* **V3** the reported count equals the number of listed facts, and per (reader, source) it never decreases.

Arms differ only in how a reader gets its answer: one statement (``P-1stmt``, ``B1h-1stmt``), several statements without
a snapshot (``P-levelwise``, ``B1h-levelwise``, ``B0-naive``) or several statements under one (``B1h-txn``,
``B0-locked``).
"""

from __future__ import annotations

import json
import os
import random
import sqlite3
import tempfile
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from knewat.crucible.l6.world import T0, World, _fact_text
from knewat.graph.client import GraphClient
from knewat.lineage.service import Lineage

OPEN = 9_999_999_999_999
Q_SOURCES, Q_FACTS, Q_DEC = 20, 60, 6
A_SOURCES, A_FACTS = 8, 100
DEPTH_CAP = 5


# ------------------------------------------------------------------------------------------------ the store
def gen_e(scale: float = 1.0, seed: int = 20261016) -> tuple[World, dict[str, Any]]:
    """Pre-populated trees: ``Q`` sources (quarantine targets) and ``A`` sources (append targets). Depth <= 5."""
    rng = random.Random(seed + 5)
    w = World(name="E")
    w.agents = ["w1", "w2", "r1"]
    w.tasks = [{"id": "t0", "status": "open", "deps": []}]
    nq, na = max(2, int(Q_SOURCES * scale)), max(2, int(A_SOURCES * scale))
    fq, fa = max(6, int(Q_FACTS * scale)), max(8, int(A_FACTS * scale))
    depth: dict[str, int] = {}
    at = [T0]
    qs, as_ = [], []

    def tick() -> int:
        at[0] += 1
        return at[0]

    for kind, n, per in (("Q", nq, fq), ("A", na, fa)):
        for i in range(n):
            sid = f"{kind.lower()}src{i:02d}"
            w.sources.append({"id": sid, "uri": f"docs/{sid}.md"})
            (qs if kind == "Q" else as_).append(sid)
            ids: list[str] = []
            for j in range(per):
                topic, text = _fact_text(rng)
                fid = f"{sid}-f{j:03d}"
                pool = [x for x in ids if depth[x] < DEPTH_CAP]
                if not pool or j < 4:
                    parents, d = [sid], 1
                else:
                    parents = rng.sample(pool, min(rng.choice((1, 2)), len(pool)))
                    d = max(depth[p] for p in parents) + 1
                depth[fid] = d
                w.facts.append({"id": fid, "text": text, "topic": topic, "agent": "w1", "at": tick(), "status": "active",
                                "scope": "global", "tree": sid, "parents": parents})  # fmt: skip
                ids.append(fid)
            for j in range(Q_DEC if kind == "Q" else 5):
                based = rng.sample(ids, rng.randint(1, 3))
                w.decisions.append({"id": f"{sid}-d{j:02d}", "text": "d", "agent": "w1", "at": tick(), "task": "t0", "based_on": based})  # fmt: skip
    return w, {"Q": qs, "A": as_, "depth": depth}


@dataclass
class Read:
    facts: dict[str, str]  # fact id -> status
    count: int
    decisions: dict[str, list[str]]  # decision id -> its based-on fact ids


@dataclass
class Violations:
    v1: int = 0
    v2: int = 0
    v3: int = 0
    reads: int = 0
    appends: int = 0
    quarantines: int = 0
    errors: int = 0
    examples: list[str] = field(default_factory=list)

    def add(self, other: Violations) -> None:
        for k in ("v1", "v2", "v3", "reads", "appends", "quarantines", "errors"):
            setattr(self, k, getattr(self, k) + getattr(other, k))
        self.examples = (self.examples + other.examples)[:5]


def check(res: Read, is_q: bool, prev: int | None, src: str, out: Violations) -> None:
    out.reads += 1
    for did, based in res.decisions.items():
        if not set(based) <= set(res.facts):
            out.v1 += 1
            if len(out.examples) < 5:
                out.examples.append(f"V1 {src} {did}")
            break
    if is_q and len(set(res.facts.values())) > 1:
        out.v2 += 1
        if len(out.examples) < 5:
            out.examples.append(f"V2 {src} {sorted(set(res.facts.values()))}")
    if res.count != len(res.facts) or (prev is not None and res.count < prev):
        out.v3 += 1
        if len(out.examples) < 5:
            out.examples.append(f"V3 {src} count={res.count} listed={len(res.facts)} prev={prev}")


# ------------------------------------------------------------------------------------------------ arms
class EArm:
    name = ""
    graph_name = ""

    def append(self, src: str, fid: str, did: str, parents: list[str], at: int) -> None: ...
    def quarantine(self, src: str) -> None: ...
    def read(self, src: str) -> Read: ...
    def close(self) -> None: ...


class KnewatE(EArm):
    """P-1stmt / P-levelwise over a FalkorDB graph already loaded with the world."""

    ONE = (
        "MATCH (s:Source {id: $s}) MATCH (s)<-[:DERIVED_FROM*1..6]-(f:Fact) WITH DISTINCT f "
        "OPTIONAL MATCH (d:Decision)-[:BASED_ON]->(f) "
        "WITH collect(DISTINCT {id: f.id, st: f.status}) AS fs, collect(DISTINCT d) AS ds "
        "RETURN fs, size(fs), [d IN ds | {id: d.id, based: [(d)-[:BASED_ON]->(x) | x.id]}]"
    )
    APPEND = (
        "MATCH (p:Fact) WHERE p.id IN $parents WITH collect(p) AS ps "
        "CREATE (f:Fact {id: $id, predicate: 'note', value: $text, status: 'active', valid_from: $at, valid_to: 9999999999999, created_at: $at}) "
        "FOREACH (x IN ps | CREATE (f)-[:DERIVED_FROM]->(x)) "
        "CREATE (d:Decision {id: $did, text: 'd', at: $at, created_at: $at}) CREATE (d)-[:BASED_ON]->(f) "
        "FOREACH (x IN ps | CREATE (d)-[:BASED_ON]->(x))"
    )

    def __init__(self, client: GraphClient, graph: str, *, levelwise: bool):
        self.client, self.g, self.levelwise = client, client.graph(graph), levelwise
        self.name = "P-levelwise" if levelwise else "P-1stmt"
        self.graph_name = graph
        self.lineage = Lineage(client, graph)

    def append(self, src: str, fid: str, did: str, parents: list[str], at: int) -> None:
        self.g.query(self.APPEND, {"id": fid, "did": did, "text": f"n {fid}", "at": at, "parents": parents})

    def quarantine(self, src: str) -> None:
        self.lineage.quarantine(src)

    def read(self, src: str) -> Read:
        if not self.levelwise:
            r = self.g.ro_query(self.ONE, {"s": src}).result_set
            if not r:
                return Read({}, 0, {})
            fs, n, ds = r[0]
            return Read({x["id"]: x["st"] for x in fs}, n, {d["id"]: list(d["based"]) for d in ds})
        # level by level, one statement each (what a client that mirrors the product's level-wise expansion does)
        n = self.g.ro_query(
            "MATCH (:Source {id: $s})<-[:DERIVED_FROM*1..6]-(f:Fact) RETURN count(DISTINCT f)", {"s": src}
        ).result_set[0][0]
        facts: dict[str, str] = {}
        rows = self.g.ro_query(
            "MATCH (:Source {id: $s})<-[:DERIVED_FROM]-(f:Fact) RETURN f.id, f.status", {"s": src}
        ).result_set
        frontier = []
        for i, st in rows:
            facts[i] = st
            frontier.append(i)
        while frontier:
            rows = self.g.ro_query(
                "MATCH (p:Fact) WHERE p.id IN $fr MATCH (p)<-[:DERIVED_FROM]-(x:Fact) RETURN DISTINCT x.id, x.status",
                {"fr": frontier},
            ).result_set
            frontier = []
            for i, st in rows:
                if i not in facts:
                    facts[i] = st
                    frontier.append(i)
        dids = [
            r[0]
            for r in self.g.ro_query(
                "MATCH (f:Fact) WHERE f.id IN $ids MATCH (d:Decision)-[:BASED_ON]->(f) RETURN DISTINCT d.id",
                {"ids": list(facts)},
            ).result_set
        ]
        based: dict[str, list[str]] = {d: [] for d in dids}
        for d, x in self.g.ro_query(
            "MATCH (d:Decision) WHERE d.id IN $ds MATCH (d)-[:BASED_ON]->(x:Fact) RETURN d.id, x.id",
            {"ds": dids},
        ).result_set:
            based[d].append(x)
        return Read(facts, n, based)


class SqliteE(EArm):
    """B1h-1stmt (one recursive CTE), B1h-txn (several SELECTs in one read transaction), B1h-levelwise (autocommit)."""

    CTE = (
        "WITH RECURSIVE d(id) AS (SELECT src FROM fact_links WHERE dst=:s AND kind='derived_from' "
        "UNION SELECT l.src FROM fact_links l JOIN d ON l.dst=d.id WHERE l.kind='derived_from') "
    )

    def __init__(self, path: str, mode: str):
        self.path, self.mode = path, mode
        self.name = {"1stmt": "B1h-1stmt", "txn": "B1h-txn", "levelwise": "B1h-levelwise"}[mode]
        self._tls = threading.local()

    def _c(self) -> sqlite3.Connection:
        c = getattr(self._tls, "c", None)
        if c is None:
            c = sqlite3.connect(self.path, timeout=60, isolation_level=None, check_same_thread=False)
            c.execute("PRAGMA busy_timeout=60000")
            self._tls.c = c
        return c

    def append(self, src: str, fid: str, did: str, parents: list[str], at: int) -> None:
        c = self._c()
        c.execute("BEGIN IMMEDIATE")
        try:
            c.execute(
                "INSERT INTO facts VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (fid, "x", "x", "note", f"n {fid}", "", "", "global", "active", at, OPEN, at, 1.0),
            )
            c.executemany(
                "INSERT INTO fact_links(src,dst,kind) VALUES(?,?,'derived_from')", [(fid, p) for p in parents]
            )
            c.execute(
                "INSERT INTO decisions(id,agent_id,task_id,text,at,flagged) VALUES(?,?,?,?,?,0)",
                (did, "w1", "t0", "d", at),
            )
            c.executemany(
                "INSERT INTO decision_facts(decision_id,fact_id) VALUES(?,?)",
                [(did, x) for x in [fid, *parents]],
            )
            c.execute("COMMIT")
        except BaseException:
            c.execute("ROLLBACK")
            raise

    def quarantine(self, src: str) -> None:
        c = self._c()
        c.execute("BEGIN IMMEDIATE")
        try:
            c.execute(
                self.CTE + "UPDATE facts SET status='quarantined' WHERE id IN (SELECT id FROM d)", {"s": src}
            )
            c.execute("COMMIT")
        except BaseException:
            c.execute("ROLLBACK")
            raise

    def read(self, src: str) -> Read:
        c = self._c()
        p = {"s": src}
        if self.mode == "1stmt":
            rows = c.execute(
                self.CTE + "SELECT f.id, f.status, (SELECT count(*) FROM d) AS n, "
                "(SELECT group_concat(df.decision_id || ':' || df.fact_id, ',') FROM decision_facts df WHERE df.fact_id IN (SELECT id FROM d) "
                "OR df.decision_id IN (SELECT decision_id FROM decision_facts WHERE fact_id IN (SELECT id FROM d))) AS pairs "
                "FROM d JOIN facts f ON f.id=d.id",
                p,
            ).fetchall()
            if not rows:
                return Read({}, 0, {})
            based: dict[str, list[str]] = {}
            for pair in (rows[0][3] or "").split(","):
                if pair:
                    did, _, fid = pair.partition(":")
                    based.setdefault(did, []).append(fid)
            return Read({r[0]: r[1] for r in rows}, rows[0][2], based)
        if self.mode == "txn":
            c.execute("BEGIN")
        try:
            n = c.execute(self.CTE + "SELECT count(*) FROM d", p).fetchone()[0]
            facts = {
                r[0]: r[1]
                for r in c.execute(self.CTE + "SELECT f.id, f.status FROM d JOIN facts f ON f.id=d.id", p)
            }
            dids = [
                r[0]
                for r in c.execute(
                    self.CTE
                    + "SELECT DISTINCT df.decision_id FROM d JOIN decision_facts df ON df.fact_id=d.id",
                    p,
                )
            ]
            based = {x: [] for x in dids}
            for did in dids:
                based[did] = [
                    r[0] for r in c.execute("SELECT fact_id FROM decision_facts WHERE decision_id=?", (did,))
                ]
        finally:
            if self.mode == "txn":
                c.execute("COMMIT")
        return Read(facts, n, based)

    def close(self) -> None:
        pass


class FilesE(EArm):
    """B0-naive / B0-locked: facts.jsonl, decisions.jsonl (append-only, written under a lock) and status.json (atomic replace)."""

    def __init__(self, root: Path, world: World, locked_reads: bool):
        self.root = root
        root.mkdir(parents=True, exist_ok=True)
        self.name = "B0-locked" if locked_reads else "B0-naive"
        self.locked_reads = locked_reads
        self.mutex = (
            threading.Lock()
        )  # stands for the lock file that B0's writers (and, if locked, readers) take
        (root / "facts.jsonl").write_text(
            "".join(json.dumps({"id": f["id"], "parents": f["parents"]}) + "\n" for f in world.facts),
            encoding="utf-8",
        )
        (root / "decisions.jsonl").write_text(
            "".join(json.dumps({"id": d["id"], "based_on": d["based_on"]}) + "\n" for d in world.decisions),
            encoding="utf-8",
        )
        (root / "status.json").write_text("{}", encoding="utf-8")
        self.children: dict[str, list[str]] = {}

    def _append(self, name: str, rec: dict[str, Any]) -> None:
        fd = os.open(self.root / name, os.O_WRONLY | os.O_APPEND)
        try:
            os.write(fd, (json.dumps(rec) + "\n").encode())
        finally:
            os.close(fd)

    def append(self, src: str, fid: str, did: str, parents: list[str], at: int) -> None:
        with self.mutex:
            self._append("facts.jsonl", {"id": fid, "parents": parents})
            self._append("decisions.jsonl", {"id": did, "based_on": [fid, *parents]})

    def quarantine(self, src: str) -> None:
        with self.mutex:
            facts = self._facts()
            ids = self._closure(facts, src)
            status = json.loads((self.root / "status.json").read_text(encoding="utf-8"))
            status.update(dict.fromkeys(ids, "quarantined"))
            tmp = self.root / f"status.{threading.get_ident()}.tmp"
            tmp.write_text(json.dumps(status), encoding="utf-8")
            os.replace(tmp, self.root / "status.json")

    def _facts(self) -> list[dict[str, Any]]:
        return [
            json.loads(x) for x in (self.root / "facts.jsonl").read_text(encoding="utf-8").splitlines() if x
        ]

    @staticmethod
    def _closure(facts: list[dict[str, Any]], src: str) -> list[str]:
        ch: dict[str, list[str]] = {}
        for f in facts:
            for p in f["parents"]:
                ch.setdefault(p, []).append(f["id"])
        seen: dict[str, None] = {}
        stack = [src]
        while stack:
            for x in ch.get(stack.pop(), []):
                if x not in seen:
                    seen[x] = None
                    stack.append(x)
        return list(seen)

    def _read(self, src: str) -> Read:
        facts = self._facts()  # natural order: facts, then decisions, then status
        decisions = [
            json.loads(x)
            for x in (self.root / "decisions.jsonl").read_text(encoding="utf-8").splitlines()
            if x
        ]
        status = json.loads((self.root / "status.json").read_text(encoding="utf-8"))
        ids = self._closure(facts, src)
        s = set(ids)
        based = {d["id"]: d["based_on"] for d in decisions if s.intersection(d["based_on"])}
        return Read({i: status.get(i, "active") for i in ids}, len(ids), based)

    def read(self, src: str) -> Read:
        if self.locked_reads:
            with self.mutex:
                return self._read(src)
        return self._read(src)


# ------------------------------------------------------------------------------------------------ the run
def run_arm(
    arm: EArm,
    meta: dict[str, Any],
    *,
    seed: int,
    seconds: float,
    appenders: int = 4,
    readers: int = 8,
    quarantine_every: float = 0.25,
) -> Violations:
    rng0 = random.Random(seed)
    stop = threading.Event()
    lock = threading.Lock()
    registry: dict[str, list[str]] = {s: [] for s in meta["A"]}
    for fid, d in meta["depth"].items():
        src = fid.split("-f")[0]
        if src in registry and d < DEPTH_CAP:
            registry[src].append(fid)
    counter = [0]
    tot = Violations()
    todo_q = list(meta["Q"])
    rng0.shuffle(todo_q)

    def appender(k: int) -> None:
        rng = random.Random(seed * 100 + k)
        v = Violations()
        while not stop.is_set():
            src = rng.choice(meta["A"])
            with lock:
                pool = list(registry[src])
                counter[0] += 1
                n = counter[0]
            parents = rng.sample(pool, rng.choice((1, 2, 3)) if len(pool) >= 3 else 1)
            fid, did = f"{src}-n{n:06d}", f"{src}-dn{n:06d}"
            try:
                arm.append(src, fid, did, parents, T0 + 10_000_000 + n)
                v.appends += 1
                with lock:
                    if max(meta["depth"][p] for p in parents) + 1 < DEPTH_CAP:
                        registry[src].append(fid)
                    meta["depth"][fid] = max(meta["depth"][p] for p in parents) + 1
            except Exception:  # noqa: BLE001
                v.errors += 1
        with lock:
            tot.add(v)

    def quarantiner() -> None:
        v = Violations()
        i = 0
        while not stop.is_set() and i < len(todo_q):
            time.sleep(quarantine_every)
            try:
                arm.quarantine(todo_q[i])
                v.quarantines += 1
            except Exception:  # noqa: BLE001
                v.errors += 1
            i += 1
        with lock:
            tot.add(v)

    def reader(k: int) -> None:
        rng = random.Random(seed * 1000 + k)
        v = Violations()
        last: dict[str, int] = {}
        while not stop.is_set():
            src = rng.choice(meta["A"] + meta["Q"])
            try:
                res = arm.read(src)
            except Exception:  # noqa: BLE001
                v.errors += 1
                continue
            is_q = src in meta["Q"]
            check(res, is_q, None if is_q else last.get(src), src, v)
            last[src] = res.count
        with lock:
            tot.add(v)

    threads = [threading.Thread(target=appender, args=(k,)) for k in range(appenders)]
    threads += [threading.Thread(target=quarantiner)]
    threads += [threading.Thread(target=reader, args=(k,)) for k in range(readers)]
    for t in threads:
        t.start()
    time.sleep(seconds)
    stop.set()
    for t in threads:
        t.join()
    return tot


def run_all(
    *,
    runs: int,
    seconds: float,
    scale: float,
    client: GraphClient | None,
    arm_names: set[str] | None = None,
    log: Any = print,
) -> dict[str, Any]:
    """10 seeded runs per arm; every (arm, run) starts from a fresh copy of the same store."""
    results: dict[str, dict[str, Any]] = {}
    for run in range(runs):
        seed = 20261016 + run
        world, meta0 = gen_e(scale)
        # arms mutate their store, so each (arm, run) gets a store of its own
        order = ["P-1stmt", "P-levelwise", "B1h-1stmt", "B1h-txn", "B1h-levelwise", "B0-naive", "B0-locked"]
        for nm in order:
            if arm_names and nm not in arm_names:
                continue
            if nm.startswith("P-") and client is None:
                continue
            tmp = Path(tempfile.mkdtemp(prefix="l6e-"))
            meta = {"Q": list(meta0["Q"]), "A": list(meta0["A"]), "depth": dict(meta0["depth"])}
            arm = _make_arm(nm, world, tmp, client, run)
            try:
                v = run_arm(arm, meta, seed=seed, seconds=seconds)
            finally:
                arm.close()
                if nm.startswith("P-") and client is not None:
                    client.delete_graph(arm.graph_name)
            r = results.setdefault(nm, {"per_run": [], "total": Violations()})
            r["per_run"].append(
                {k: getattr(v, k) for k in ("v1", "v2", "v3", "reads", "appends", "quarantines", "errors")}
                | {"seed": seed, "examples": v.examples}
            )
            r["total"].add(v)
            log(
                f"E run {run} {nm}: reads={v.reads} V1={v.v1} V2={v.v2} V3={v.v3} appends={v.appends} quarantines={v.quarantines} errors={v.errors}"
            )
    return {
        nm: {
            "runs": len(r["per_run"]),
            "totals": {
                k: getattr(r["total"], k)
                for k in ("v1", "v2", "v3", "reads", "appends", "quarantines", "errors")
            },
            "runs_with_violation": sum(1 for x in r["per_run"] if x["v1"] + x["v2"] + x["v3"] > 0),
            "per_run": r["per_run"],
        }
        for nm, r in results.items()
    }


def _make_arm(nm: str, world: World, tmp: Path, client: GraphClient | None, run: int) -> EArm:
    from knewat.crucible.l6 import stores as S

    if nm.startswith("P-"):
        assert client is not None
        name, _ = S.load_knewat(world, client, f"l6_e_{run}_{nm.lower().replace('-', '_')}")
        return KnewatE(client, name, levelwise=nm == "P-levelwise")
    if nm.startswith("B1h-"):
        mode = nm.split("-", 1)[1]
        path, _ = S.build_sqlite(world, tmp, f"e_{run}_{mode}")
        return SqliteE(path, mode)
    return FilesE(tmp / "f", world, nm == "B0-locked")
