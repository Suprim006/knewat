"""Family I arms: the composite close-out write, one class per arm (see docs/research/P10_GRAPH_VS_SQL.md, I).

A *close-out* writes 14 checkable *items* over 6 entity kinds, all tagged with the close-out id ``co`` (in the
text/id of every entity, so it works for the product path that mints its own ids too):

====================  ==================================================  =====================================
item                  graph                                               SQL
====================  ==================================================  =====================================
fact                  Fact value ``fact <co>``                            facts row
fact_derived          (Fact)-[:DERIVED_FROM]->(Source)                    fact_derived row
fact_asserted         (Fact)-[:ASSERTED_BY]->(Agent)                      fact_asserted row
step_node             Step ``step_<co>`` (product: any Step WROTE it)     steps row
step_wrote            (Step)-[:WROTE]->(Fact)                             step_wrote row
decision              Decision text ``decision <co>``                     decisions row
decision_based_on     (Decision)-[:BASED_ON]->(Fact)                      decision_based_on row
decision_decided_for  (Agent)-[:DECIDED]->(D)-[:FOR]->(Task)              decisions.agent_id and task_id set
artifact              Artifact id ``a_<co>``                              artifacts row
artifact_links        PRODUCED_BY agent and FOR task                      artifacts.agent_id and task_id set
handoff               Handoff note ``handoff <co>``                       handoffs row
handoff_links         FROM, TO and FOR edges                              handoffs.from/to/task set
handoff_carries       (Handoff)-[:CARRIES]->(Fact)                        handoff_carries row
task_done             Task status done, version = expected + 1, done_at  same
====================  ==================================================  =====================================

A close-out is **complete** with all 14, **absent** with 0 and **partial** otherwise. Partial detection is the same
function for every arm; only the item queries differ.
"""

from __future__ import annotations

import random
import re
import sqlite3
import threading
from pathlib import Path
from typing import Any

from redis.exceptions import ResponseError

from plexus.graph.client import GraphClient
from plexus.graph.schema import apply_schema
from plexus.graph.tenancy import graph_name

QDIR = Path(__file__).resolve().parent / "i_queries"
AGENT, TO, SRC = "a1", "a2", "s0"
ITEMS = (
    "fact", "fact_derived", "fact_asserted", "step_node", "step_wrote", "decision", "decision_based_on",
    "decision_decided_for", "artifact", "artifact_links", "handoff", "handoff_links", "handoff_carries",
    "task_done",
)  # fmt: skip
ARMS = ("S-txn", "S-auto", "F-product", "F-multi", "F-multiexec", "F-1stmt")
SLUG = {
    "S-txn": "stxn", "S-auto": "sauto", "F-product": "fprod", "F-multi": "fmulti", "F-multiexec": "fmexec",
    "F-1stmt": "f1first", "F-1stmt-first": "f1first", "F-1stmt-last": "f1last", "F-multiexec-err": "fmexecerr",
    "F-multi-cas-first": "fmulticas",
}  # fmt: skip


def query_text(name: str) -> str:
    """The statement file ``i_queries/<name>`` without comment lines."""
    lines = (QDIR / name).read_text(encoding="utf-8").splitlines()
    return "\n".join(ln for ln in lines if ln.strip() and not ln.strip().startswith(("//", "--")))


def sql_statements() -> list[str]:
    parts = (QDIR / "s_closeout.sql").read_text(encoding="utf-8").split("\n;;\n")
    return [
        "\n".join(ln for ln in p.splitlines() if ln.strip() and not ln.strip().startswith("--"))
        for p in parts
    ]


def ids(co: str) -> dict[str, str]:
    return {
        "step": f"step_{co}", "fact": f"fact_{co}", "dec": f"dec_{co}", "art": f"a_{co}", "ho": f"ho_{co}",
        "task": f"t_{co}", "value": f"fact {co}", "text": f"decision {co}", "note": f"handoff {co}",
        "summary": f"artifact {co}",
    }  # fmt: skip


def classify(items: set[str]) -> str:
    n = len(items & set(ITEMS))
    return "complete" if n == len(ITEMS) else "absent" if n == 0 else "partial"


def stale_flags(seed: int, n: int, pct: float = 0.25) -> list[bool]:
    rng = random.Random(seed)
    return [rng.random() < pct for _ in range(n)]


def _is_guard_error(exc: Exception) -> bool:
    return "zero" in str(exc).lower()


# ------------------------------------------------------------------------------------------------ base
class Arm:
    name = ""
    kind = "F"
    product = False

    def __init__(self, host: str, port: int, tenant: str = "", root: str = ""):
        self.host, self.port, self.tenant, self.root = host, port, tenant, root
        self.round_trips = 0  # database round trips of the last close-out (statements for SQLite)

    # world creation (once) ; connection (once per process) ; one claimed task per close-out ; the close-out
    def setup_world(self) -> None: ...
    def connect(self) -> None: ...
    def new_task(self, co: str) -> tuple[str, int]: ...
    def closeout(self, co: str, task: str, v: int, expected: int) -> bool: ...
    def verify(self, prefix: str, intents: dict[str, dict[str, Any]]) -> dict[str, set[str]]: ...
    def close(self) -> None: ...
    def drop(self) -> None: ...

    def states(
        self, prefix: str, intents: dict[str, dict[str, Any]]
    ) -> tuple[dict[str, str], dict[str, set[str]]]:
        items = self.verify(prefix, intents)
        return {co: classify(it) for co, it in items.items()}, items


def _params(co: str, v: int, now: int, *, agent: str = AGENT) -> dict[str, Any]:
    d = ids(co)
    d.update({"co": co, "v": v, "now": now, "agent": agent, "to": TO, "src": SRC})
    return d


# ------------------------------------------------------------------------------------------------ SQLite arms
class SqliteArm(Arm):
    kind = "S"
    txn = True

    def __init__(self, host: str, port: int, tenant: str = "", root: str = ""):
        super().__init__(host, port, tenant, root)
        self.path = Path(root) / f"{tenant}.db"
        self.conn: sqlite3.Connection | None = None
        self.stmts = sql_statements()

    def _open(self) -> sqlite3.Connection:
        c = sqlite3.connect(str(self.path), isolation_level=None, timeout=10.0)
        c.execute("PRAGMA busy_timeout = 10000")
        c.execute("PRAGMA journal_mode = WAL")
        c.execute("PRAGMA synchronous = NORMAL")
        return c

    def setup_world(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        c = self._open()
        c.executescript((QDIR / "s_schema.sql").read_text(encoding="utf-8"))
        c.execute("INSERT INTO agents VALUES (?)", (AGENT,))
        c.execute("INSERT INTO agents VALUES (?)", (TO,))
        c.execute("INSERT INTO sources VALUES (?)", (SRC,))
        c.close()

    def connect(self) -> None:
        self.conn = self._open()

    def new_task(self, co: str) -> tuple[str, int]:
        assert self.conn is not None
        tid = ids(co)["task"]
        self.conn.execute(
            "INSERT INTO tasks (id, status, claimed_by, version) VALUES (?, 'claimed', ?, 1)", (tid, AGENT)
        )
        return tid, 1

    def closeout(self, co: str, task: str, v: int, expected: int) -> bool:
        from plexus.crucible.util import now_ms

        c = self.conn
        assert c is not None
        p = _params(co, expected, now_ms())
        p["task"] = task
        self.round_trips = 0
        if self.txn:
            c.execute("BEGIN IMMEDIATE")
            self.round_trips += 1
        try:
            for i, s in enumerate(self.stmts):
                cur = c.execute(s, p)
                self.round_trips += 1
                if i == 7 and cur.rowcount == 0:  # the version guard
                    if self.txn:
                        c.execute("ROLLBACK")
                        self.round_trips += 1
                    return False
            if self.txn:
                c.execute("COMMIT")
                self.round_trips += 1
            return True
        except BaseException:
            if c.in_transaction:
                c.execute("ROLLBACK")
            raise

    def verify(self, prefix: str, intents: dict[str, dict[str, Any]]) -> dict[str, set[str]]:
        c = sqlite3.connect(f"file:{self.path.as_posix()}?mode=ro", uri=True)
        like = prefix.replace("%", "") + "%"
        out: dict[str, set[str]] = {}

        def add(item: str, sql: str, strip: int) -> None:
            for (x,) in c.execute(sql, (like,)):
                out.setdefault(x[strip:], set()).add(item)

        add("fact", "SELECT value FROM facts WHERE value LIKE 'fact ' || ?", 5)
        add(
            "fact_derived",
            "SELECT f.value FROM facts f JOIN fact_derived d ON d.fact_id=f.id JOIN sources s ON s.id=d.source_id WHERE f.value LIKE 'fact ' || ?",
            5,
        )
        add(
            "fact_asserted",
            "SELECT f.value FROM facts f JOIN fact_asserted d ON d.fact_id=f.id JOIN agents s ON s.id=d.agent_id WHERE f.value LIKE 'fact ' || ?",
            5,
        )
        add("step_node", "SELECT id FROM steps WHERE id LIKE 'step_' || ?", 5)
        add(
            "step_wrote",
            "SELECT f.value FROM facts f JOIN step_wrote w ON w.node_id=f.id JOIN steps s ON s.id=w.step_id WHERE f.value LIKE 'fact ' || ?",
            5,
        )
        add("decision", "SELECT text FROM decisions WHERE text LIKE 'decision ' || ?", 9)
        add(
            "decision_based_on",
            "SELECT d.text FROM decisions d JOIN decision_based_on b ON b.decision_id=d.id JOIN facts f ON f.id=b.fact_id WHERE d.text LIKE 'decision ' || ?",
            9,
        )
        add(
            "decision_decided_for",
            "SELECT d.text FROM decisions d JOIN agents a ON a.id=d.agent_id JOIN tasks t ON t.id=d.task_id WHERE d.text LIKE 'decision ' || ?",
            9,
        )
        add("artifact", "SELECT id FROM artifacts WHERE id LIKE 'a_' || ?", 2)
        add(
            "artifact_links",
            "SELECT x.id FROM artifacts x JOIN agents a ON a.id=x.agent_id JOIN tasks t ON t.id=x.task_id WHERE x.id LIKE 'a_' || ?",
            2,
        )
        add("handoff", "SELECT note FROM handoffs WHERE note LIKE 'handoff ' || ?", 8)
        add(
            "handoff_links",
            "SELECT h.note FROM handoffs h JOIN agents a ON a.id=h.from_agent JOIN agents b ON b.id=h.to_agent JOIN tasks t ON t.id=h.task_id WHERE h.note LIKE 'handoff ' || ?",
            8,
        )
        add(
            "handoff_carries",
            "SELECT h.note FROM handoffs h JOIN handoff_carries k ON k.handoff_id=h.id JOIN facts f ON f.id=k.fact_id WHERE h.note LIKE 'handoff ' || ?",
            8,
        )
        tasks = {r[0]: r[1:] for r in c.execute("SELECT id, status, version, done_at FROM tasks")}
        c.close()
        return _finish_items(out, intents, tasks)

    def close(self) -> None:
        if self.conn is not None:
            self.conn.close()
            self.conn = None

    def drop(self) -> None:
        for suf in ("", "-wal", "-shm"):
            Path(str(self.path) + suf).unlink(missing_ok=True)


class SqliteAuto(SqliteArm):
    txn = False


def _finish_items(
    out: dict[str, set[str]], intents: dict[str, dict[str, Any]], tasks: dict[str, tuple[Any, ...]]
) -> dict[str, set[str]]:
    """Add ``task_done`` (status done, version expected+1, done_at set) and make sure every intent has an entry."""
    for co, it in intents.items():
        out.setdefault(co, set())
        t = tasks.get(it["task"])
        if t is not None and t[0] == "done" and t[1] == it["v"] + 1 and t[2] is not None:
            out[co].add("task_done")
    return out


# ------------------------------------------------------------------------------------------------ FalkorDB arms
class FalkorArm(Arm):
    kind = "F"

    def __init__(self, host: str, port: int, tenant: str = "", root: str = ""):
        super().__init__(host, port, tenant, root)
        self.gname = graph_name(tenant)
        self.c: GraphClient | None = None
        self.g: Any = None
        self.q: dict[str, str] = {}

    def _client(self) -> GraphClient:
        c = GraphClient(host=self.host, port=self.port, password="")
        c.pool.connection_kwargs["socket_timeout"] = (
            60.0  # a server that crashed and hangs must not hang the harness
        )
        return c

    def _load_queries(self) -> None:
        for n in (
            "step",
            "fact",
            "decision",
            "task",
            "artifact",
            "handoff",
            "task_err",
            "1stmt_first",
            "1stmt_last",
        ):
            self.q[n] = query_text(f"f_{n}.cypher")

    def setup_world(self) -> None:
        c = self._client()
        c.delete_graph(self.gname)
        apply_schema(c, self.gname)
        g = c.graph(self.gname)
        g.query(
            "CREATE (:Agent {id: $a, name: $a}), (:Agent {id: $b, name: $b}), (:Source {id: $s, uri: 'docs/closeout.md'})",
            {"a": AGENT, "b": TO, "s": SRC},
        )
        c.close()

    def connect(self) -> None:
        self.c = self._client()
        self.g = self.c.graph(self.gname)
        self._load_queries()

    def new_task(self, co: str) -> tuple[str, int]:
        tid = ids(co)["task"]
        self.g.query(
            "CREATE (:Task {id: $t, title: $t, status: 'claimed', claimed_by: $a, version: 1, priority: 0})",
            {"t": tid, "a": AGENT},
        )
        return tid, 1

    def _run(self, name: str, p: dict[str, Any]) -> Any:
        self.round_trips += 1
        return self.g.query(self.q[name], p, 10_000)

    def verify(self, prefix: str, intents: dict[str, dict[str, Any]]) -> dict[str, set[str]]:
        assert self.c is not None
        g = self.c.graph(self.gname)
        out: dict[str, set[str]] = {}

        def add(item: str, cy: str, strip: int) -> None:
            r = g.ro_query(cy, {"p": prefix}, 10_000)
            for (x,) in r.result_set:
                out.setdefault(x[strip:], set()).add(item)

        add("fact", "MATCH (f:Fact) WHERE f.value STARTS WITH 'fact ' + $p RETURN f.value", 5)
        add(
            "fact_derived",
            "MATCH (f:Fact)-[:DERIVED_FROM]->(:Source) WHERE f.value STARTS WITH 'fact ' + $p RETURN f.value",
            5,
        )
        add(
            "fact_asserted",
            "MATCH (f:Fact)-[:ASSERTED_BY]->(:Agent) WHERE f.value STARTS WITH 'fact ' + $p RETURN f.value",
            5,
        )
        if self.product:
            add(
                "step_node",
                "MATCH (:Step)-[:WROTE]->(f:Fact) WHERE f.value STARTS WITH 'fact ' + $p RETURN f.value",
                5,
            )
        else:
            add("step_node", "MATCH (s:Step) WHERE s.id STARTS WITH 'step_' + $p RETURN s.id", 5)
        add(
            "step_wrote",
            "MATCH (:Step)-[:WROTE]->(f:Fact) WHERE f.value STARTS WITH 'fact ' + $p RETURN f.value",
            5,
        )
        add("decision", "MATCH (d:Decision) WHERE d.text STARTS WITH 'decision ' + $p RETURN d.text", 9)
        add(
            "decision_based_on",
            "MATCH (d:Decision)-[:BASED_ON]->(:Fact) WHERE d.text STARTS WITH 'decision ' + $p RETURN d.text",
            9,
        )
        add(
            "decision_decided_for",
            "MATCH (:Agent)-[:DECIDED]->(d:Decision)-[:FOR]->(:Task) WHERE d.text STARTS WITH 'decision ' + $p RETURN d.text",
            9,
        )
        add("artifact", "MATCH (x:Artifact) WHERE x.id STARTS WITH 'a_' + $p RETURN x.id", 2)
        add(
            "artifact_links",
            "MATCH (x:Artifact)-[:PRODUCED_BY]->(:Agent) MATCH (x)-[:FOR]->(:Task) WHERE x.id STARTS WITH 'a_' + $p RETURN x.id",
            2,
        )
        add("handoff", "MATCH (h:Handoff) WHERE h.note STARTS WITH 'handoff ' + $p RETURN h.note", 8)
        add(
            "handoff_links",
            "MATCH (h:Handoff)-[:FROM]->(:Agent) MATCH (h)-[:TO]->(:Agent) MATCH (h)-[:FOR]->(:Task) WHERE h.note STARTS WITH 'handoff ' + $p RETURN h.note",
            8,
        )
        add(
            "handoff_carries",
            "MATCH (h:Handoff)-[:CARRIES]->(:Fact) WHERE h.note STARTS WITH 'handoff ' + $p RETURN h.note",
            8,
        )
        tids = [it["task"] for it in intents.values()]
        tasks: dict[str, tuple[Any, ...]] = {}
        for i in range(0, len(tids), 5000):
            r = g.ro_query(
                "MATCH (t:Task) WHERE t.id IN $ids RETURN t.id, t.status, t.version, t.done_at",
                {"ids": tids[i : i + 5000]},
                10_000,
            )
            tasks.update({row[0]: tuple(row[1:]) for row in r.result_set})
        return _finish_items(out, intents, tasks)

    def close(self) -> None:
        if self.c is not None:
            self.c.close()
            self.c = None

    def drop(self) -> None:
        c = self._client()
        c.delete_graph(self.gname)
        c.close()


class FMulti(FalkorArm):
    """Six separate GRAPH.QUERY statements, one round trip each, in the product's order (no compensation)."""

    cas_first = False
    order = ("step", "fact", "decision", "task", "artifact", "handoff")

    def closeout(self, co: str, task: str, v: int, expected: int) -> bool:
        from plexus.crucible.util import now_ms

        p = _params(co, expected, now_ms())
        p["task"] = task
        self.round_trips = 0
        order = ("task", "step", "fact", "decision", "artifact", "handoff") if self.cas_first else self.order
        for name in order:
            r = self._run(name, p)
            if name == "task" and not r.result_set:
                return False  # guard miss: stop (nothing is undone)
        return True


class FMultiCasFirst(FMulti):
    cas_first = True


class FMultiExec(FalkorArm):
    """The six statements queued as GRAPH.QUERY inside MULTI/EXEC (one flight)."""

    err_variant = False

    def closeout(self, co: str, task: str, v: int, expected: int) -> bool:
        from plexus.crucible.util import now_ms

        assert self.c is not None
        p = _params(co, expected, now_ms())
        p["task"] = task
        hdr = self.g._build_params_header(p)
        pipe = self.c.db.connection.pipeline(transaction=True)
        for name in (
            "step",
            "fact",
            "decision",
            "task_err" if self.err_variant else "task",
            "artifact",
            "handoff",
        ):
            pipe.execute_command("GRAPH.QUERY", self.gname, hdr + self.q[name])
        self.round_trips = 1
        res = pipe.execute(raise_on_error=False)
        guard = res[3]
        if isinstance(guard, Exception):
            if not _is_guard_error(guard):
                raise guard
            return False
        for r in res:
            if isinstance(r, Exception):
                raise r
        return bool(guard[1])  # rows of the task statement


class FMultiExecErr(FMultiExec):
    err_variant = True


class FOneStatement(FalkorArm):
    which = "1stmt_first"

    def closeout(self, co: str, task: str, v: int, expected: int) -> bool:
        from plexus.crucible.util import now_ms

        p = _params(co, expected, now_ms())
        p["task"] = task
        self.round_trips = 0
        try:
            r = self._run(self.which, p)
        except ResponseError as exc:
            if _is_guard_error(exc):
                return False
            raise
        return bool(r.result_set)


class FOneLast(FOneStatement):
    which = "1stmt_last"


class FProduct(FalkorArm):
    """The product path: assert_fact, record_decision, complete_task, handoff through ``Runtime._run`` (mode 'mcp')."""

    product = True

    def __init__(self, host: str, port: int, tenant: str = "", root: str = ""):
        super().__init__(host, port, tenant, root)
        self.b: Any = None
        self.queries = 0

    def _backend(self) -> Any:
        from plexus.crucible.backends.plexus import PlexusBackend

        return PlexusBackend(self.tenant, host=self.host, port=self.port, embedder="hash", mode="mcp")

    def setup_world(self) -> None:
        c = self._client()
        c.delete_graph(self.gname)
        c.close()
        b = self._backend()
        b.register_agent(AGENT, "worker")
        b.register_agent(TO, "worker")
        self.src = b.add_source("docs/closeout.md")
        # record the product-minted source id as the shared Source (the harness passes it to the writer)
        b.close()

    def source_id(self) -> str:
        c = self._client()
        rows = c.graph(self.gname).ro_query("MATCH (s:Source) RETURN s.id").result_set
        c.close()
        return rows[0][0]

    def connect(self) -> None:
        super().connect()
        self.b = self._backend()
        self.src = self.source_id()
        orig = self.b.client._run
        arm = self

        def counting(*a: Any, **k: Any) -> Any:
            arm.queries += 1
            return orig(*a, **k)

        self.b.client._run = counting

    def new_task(self, co: str) -> tuple[str, int]:
        tid = ids(co)["task"]
        self.b.create_tasks([{"id": tid, "title": tid}])
        t = self.b.claim_next_task(AGENT, lease_ms=3_600_000)
        assert t is not None
        return t["id"], int(t["version"])

    def closeout(self, co: str, task: str, v: int, expected: int) -> bool:
        from plexus.crucible.api import ClaimConflict

        d = ids(co)
        b = self.b
        self.queries = 0
        self.round_trips = 4  # tool calls
        fid = b.assert_fact(AGENT, f"subject {co}", "note", d["value"], source_id=self.src)["fact_id"]
        b.record_decision(AGENT, task, d["text"], [fid])
        try:
            b.complete_task(
                AGENT,
                task,
                expected,
                [{"id": d["art"], "kind": "report", "uri": "mem://x", "summary": d["summary"]}],
            )
        except ClaimConflict:
            return False
        b.handoff(AGENT, TO, task, d["note"], [], [fid])
        return True

    def close(self) -> None:
        if self.b is not None:
            self.b.close()
            self.b = None
        super().close()


def make_arm(name: str, host: str, port: int, tenant: str, root: str) -> Arm:
    cls = {
        "S-txn": SqliteArm, "S-auto": SqliteAuto, "F-product": FProduct, "F-multi": FMulti,
        "F-multiexec": FMultiExec, "F-1stmt": FOneStatement, "F-1stmt-first": FOneStatement,
        "F-1stmt-last": FOneLast, "F-multiexec-err": FMultiExecErr, "F-multi-cas-first": FMultiCasFirst,
    }[name]  # fmt: skip
    return cls(host, port, tenant, root)


def valid_tenant(slug: str, run: str) -> str:
    t = re.sub(r"[^a-z0-9_]", "", f"l7i_{slug}_{run}".lower())[:48]
    return t


_lock = threading.Lock()
