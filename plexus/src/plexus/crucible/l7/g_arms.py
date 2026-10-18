"""Family G arms: F (graph per tenant), S-file (SQLite file per tenant), S-shared (one SQLite file, tenant_id everywhere).

Each arm creates tenants from ``g_gen.tenant_world(k)``, answers the four G4 queries (q1 fact by id, q2 decisions based on a
fact, q3 why-chain depth <= 4, q4 write one fact + one derived-from link) and the G3a product-path probes.
"""

from __future__ import annotations

import sqlite3
import time
from pathlib import Path
from typing import Any

from plexus.crucible.backends.sqlite import FTS_SCHEMA, SCHEMA
from plexus.crucible.l7 import common
from plexus.crucible.l7.g_gen import OPEN, SCOPE, T0, counts, tenant_name, tenant_world
from plexus.embed import get_embedder
from plexus.graph.client import GraphClient
from plexus.graph.schema import apply_schema
from plexus.graph.tenancy import graph_name

DEC = 5  # decimals kept of each embedding component (bulk-load parameter size)


# ================================================================================================ F: graph per tenant
class FArm:
    name = "F"

    def __init__(self, host: str, port: int):
        self.host, self.port = host, port
        self.client = GraphClient(host=host, port=port, password="", max_connections=16)
        self.client.pool.connection_kwargs["socket_timeout"] = 60.0
        self.emb = get_embedder("hash")
        self.worlds: dict[int, dict[str, Any]] = {}
        self._graphs: dict[str, Any] = {}

    def gname(self, k: int) -> str:
        return graph_name(tenant_name(k))

    def g(self, k: int) -> Any:
        n = self.gname(k)
        g = self._graphs.get(n)
        if g is None:
            g = self._graphs[n] = self.client.graph(n)
        return g

    # -- creation (G1) -----------------------------------------------------------------------------------
    def create_schema(self, k: int) -> float:
        """The product's tenant creation: ``apply_schema`` on a fresh graph. Returns seconds."""
        n = self.gname(k)
        self.client.delete_graph(n)
        t0 = time.perf_counter()
        apply_schema(self.client, n)
        return time.perf_counter() - t0

    def load(self, k: int, w: dict[str, Any] | None = None) -> dict[str, int]:
        """Bulk-load the tenant world (compatible with the product schema: UNIQUE ids, Scope/Entity/ABOUT/IN_SCOPE shape that
        ``Engram.recall`` and ``Lineage.why/impact`` read). Returns the node/edge counts read back."""
        w = w or tenant_world(k)
        self.worlds[k] = w
        g = self.g(k)

        def run(cy: str, rows: list[Any]) -> None:
            for ch in common.chunks(rows):
                g.query(cy, {"rows": ch}, common.TIMEOUT_MS)

        run(
            "UNWIND $rows AS r CREATE (:Agent {id: r.id, name: r.id, created_at: r.t})",
            [{"id": a, "t": T0} for a in w["agents"]],
        )
        run(
            "UNWIND $rows AS r CREATE (:Source {id: r.id, uri: r.uri, kind: 'doc', trust: 'normal', title: '', text: '', created_at: r.t})",
            [{"id": s["id"], "uri": s["uri"], "t": T0} for s in w["sources"]],
        )
        run(
            "UNWIND $rows AS r CREATE (:Task {id: r.id, title: r.id, status: r.status, priority: 0, lease_until: 0, claimed_by: '', version: 0, done_at: 0, created_at: r.t, seq: r.seq})",
            [{"id": t["id"], "status": t["status"], "t": T0, "seq": i} for i, t in enumerate(w["tasks"])],
        )
        run(
            "UNWIND $rows AS r MATCH (a:Task {id: r.a}) MATCH (b:Task {id: r.b}) CREATE (a)-[:DEPENDS_ON]->(b)",
            [{"a": t["id"], "b": d} for t in w["tasks"] for d in t["deps"]],
        )
        run(
            "UNWIND $rows AS r CREATE (:Scope {id: r.id, kind: 'project', name: 'global', created_at: r.t})",
            [{"id": SCOPE, "t": T0}],
        )
        run(
            "UNWIND $rows AS r CREATE (:Entity {id: r.id, name: r.name, norm_name: r.name, kind: 'thing', created_at: r.t})",
            [{"id": f"e_{t}", "name": t, "t": T0} for t in w["topics"]],
        )
        embs = self.emb.embed([f["text"] for f in w["facts"]])
        run(
            "UNWIND $rows AS r CREATE (:Fact {id: r.id, subject_id: r.subj, predicate: 'note', value: r.text, norm_value: r.norm, "
            "status: 'active', valid_from: r.at, valid_to: r.vt, recorded_at: r.at, created_at: r.at, confidence: 1.0, surprise: 0.0, "
            "embedding: vecf32(r.emb)})",
            [
                {
                    "id": f["id"],
                    "subj": f"e_{f['topic']}",
                    "text": f["text"],
                    "norm": f["text"].lower(),
                    "at": f["at"],
                    "vt": OPEN,
                    "emb": [round(x, DEC) for x in e],
                }
                for f, e in zip(w["facts"], embs, strict=True)
            ],  # fmt: skip
        )
        run(
            "UNWIND $rows AS r MATCH (f:Fact {id: r.f}) MATCH (e:Entity {id: r.e}) CREATE (f)-[:ABOUT]->(e)",
            [{"f": f["id"], "e": f"e_{f['topic']}"} for f in w["facts"]],
        )
        run(
            "UNWIND $rows AS r MATCH (f:Fact {id: r.f}) MATCH (s:Scope {id: r.s}) CREATE (f)-[:IN_SCOPE]->(s)",
            [{"f": f["id"], "s": SCOPE} for f in w["facts"]],
        )
        run(
            "UNWIND $rows AS r MATCH (f:Fact {id: r.f}) MATCH (a:Agent {id: r.a}) CREATE (f)-[:ASSERTED_BY {at: r.at}]->(a)",
            [{"f": f["id"], "a": f["agent"], "at": f["at"]} for f in w["facts"]],
        )
        src_ids = {s["id"] for s in w["sources"]}
        run(
            "UNWIND $rows AS r MATCH (f:Fact {id: r.f}) MATCH (p:Source {id: r.p}) CREATE (f)-[:DERIVED_FROM]->(p)",
            [{"f": f["id"], "p": p} for f in w["facts"] for p in f["parents"] if p in src_ids],
        )
        run(
            "UNWIND $rows AS r MATCH (f:Fact {id: r.f}) MATCH (p:Fact {id: r.p}) CREATE (f)-[:DERIVED_FROM]->(p)",
            [{"f": f["id"], "p": p} for f in w["facts"] for p in f["parents"] if p not in src_ids],
        )
        run(
            "UNWIND $rows AS r MATCH (a:Agent {id: r.a}) CREATE (s:Step {id: r.id, n: r.n, at: r.at, agent_id: r.a, created_at: r.at}) CREATE (s)-[:BY]->(a)",
            [{"id": s["id"], "n": s["n"], "at": s["at"], "a": s["agent"]} for s in w["steps"]],
        )
        run(
            "UNWIND $rows AS r MATCH (s:Step {id: r.s}) MATCH (f:Fact {id: r.f}) CREATE (s)-[:READ {via: 'use', at: r.at}]->(f)",
            [{"s": s["id"], "f": f, "at": s["at"]} for s in w["steps"] for f in s["reads"]],
        )
        run(
            "UNWIND $rows AS r MATCH (a:Agent {id: r.a}) MATCH (t:Task {id: r.t}) CREATE (d:Decision {id: r.id, text: r.text, at: r.at, created_at: r.at}) "
            "CREATE (a)-[:DECIDED]->(d) CREATE (d)-[:FOR]->(t)",
            [
                {"id": d["id"], "text": d["text"], "at": d["at"], "a": d["agent"], "t": d["task"]}
                for d in w["decisions"]
            ],
        )
        run(
            "UNWIND $rows AS r MATCH (d:Decision {id: r.d}) MATCH (f:Fact {id: r.f}) CREATE (d)-[:BASED_ON]->(f)",
            [{"d": d["id"], "f": f} for d in w["decisions"] for f in d["based_on"]],
        )
        run(
            "UNWIND $rows AS r MATCH (a:Agent {id: r.a}) MATCH (b:Agent {id: r.b}) MATCH (t:Task {id: r.t}) CREATE (h:Handoff {id: r.id, at: r.at, note: '', created_at: r.at}) "
            "CREATE (h)-[:FROM]->(a) CREATE (h)-[:TO]->(b) CREATE (h)-[:FOR]->(t)",
            [
                {"id": h["id"], "at": h["at"], "a": h["from"], "b": h["to"], "t": h["task"]}
                for h in w["handoffs"]
            ],
        )
        run(
            "UNWIND $rows AS r MATCH (h:Handoff {id: r.h}) MATCH (f:Fact {id: r.f}) CREATE (h)-[:CARRIES]->(f)",
            [{"h": h["id"], "f": f} for h in w["handoffs"] for f in h["carries"]],
        )
        got = self.read_counts(k)
        want = counts(w)
        bad = {x: (want[x], got.get(x)) for x in want if got.get(x) != want[x]}
        if bad:
            raise AssertionError(f"F tenant {k}: store differs from the ledger (ledger, store): {bad}")
        return got

    def read_counts(self, k: int) -> dict[str, int]:
        g = self.g(k)

        def n(q: str) -> int:
            return int(g.ro_query(q).result_set[0][0])

        return {
            "agents": n("MATCH (n:Agent) RETURN count(n)"), "sources": n("MATCH (n:Source) RETURN count(n)"),
            "facts": n("MATCH (n:Fact) RETURN count(n)"), "derived_edges": n("MATCH ()-[r:DERIVED_FROM]->() RETURN count(r)"),
            "steps": n("MATCH (n:Step) RETURN count(n)"), "reads": n("MATCH ()-[r:READ]->() RETURN count(r)"),
            "decisions": n("MATCH (n:Decision) RETURN count(n)"), "based_on": n("MATCH ()-[r:BASED_ON]->() RETURN count(r)"),
            "handoffs": n("MATCH (n:Handoff) RETURN count(n)"), "carries": n("MATCH ()-[r:CARRIES]->() RETURN count(r)"),
            "tasks": n("MATCH (n:Task) RETURN count(n)"), "depends_on": n("MATCH ()-[r:DEPENDS_ON]->() RETURN count(r)"),
        }  # fmt: skip

    # -- the G4 queries ------------------------------------------------------------------------------------
    def q1(self, k: int, fid: str) -> Any:
        return (
            self.g(k)
            .ro_query("MATCH (f:Fact {id: $id}) RETURN f.value", {"id": fid}, common.TIMEOUT_MS)
            .result_set
        )

    def q2(self, k: int, fid: str) -> Any:
        return (
            self.g(k)
            .ro_query(
                "MATCH (d:Decision)-[:BASED_ON]->(:Fact {id: $id}) RETURN d.id",
                {"id": fid},
                common.TIMEOUT_MS,
            )
            .result_set
        )

    def q3(self, k: int, fid: str) -> Any:
        return (
            self.g(k)
            .ro_query(
                "MATCH (f:Fact {id: $id})-[:DERIVED_FROM*1..4]->(x) RETURN DISTINCT x.id",
                {"id": fid},
                common.TIMEOUT_MS,
            )
            .result_set
        )

    def q4(self, k: int, new_id: str, parent: str) -> Any:
        return (
            self.g(k)
            .query(
                "MATCH (p:Fact {id: $p}) CREATE (f:Fact {id: $id, predicate: 'note', value: $v, subject_id: '', status: 'active', "
                "valid_from: $now, valid_to: $open, recorded_at: $now, created_at: $now, confidence: 1.0})-[:DERIVED_FROM]->(p) RETURN f.id",
                {"p": parent, "id": new_id, "v": f"written {new_id}", "now": T0, "open": OPEN},
                common.TIMEOUT_MS,
            )
            .result_set
        )

    @staticmethod
    def norm(op: str, rows: Any) -> Any:
        if op == "q1":
            return [r[0] for r in rows]
        if op in ("q2", "q3"):
            return sorted(r[0] for r in rows)
        return [r[0] for r in rows]

    # -- G3a: the product services bound to A's graph ---------------------------------------------------------
    def probe(self, a: int, b: int) -> dict[str, Any]:
        """From tenant A's binding (the product services on A's graph) try to read B's data. Returns leaked rows + controls."""
        from plexus.engram.service import Engram
        from plexus.lineage.service import Lineage, UnknownNode

        wa, wb = self.worlds[a], self.worlds[b]
        graph = self.gname(a)
        lin = Lineage(self.client, graph)
        eng = Engram(self.client, graph, self.emb)
        tag_b, secret_b = wb["tenant"], wb["secret"]
        leaked: dict[str, int] = {"canary_lookup": 0, "traversal": 0, "keyword": 0, "collision": 0}
        notes: dict[str, Any] = {}

        def blob(x: Any) -> str:
            return repr(x)

        # 1. B's canary id: why() is the product's lookup-by-id (node_info + edges)
        try:
            r = lin.why(wb["canary"])
            leaked["canary_lookup"] += 1 + (1 if secret_b in blob(r) or tag_b in blob(r) else 0)
        except UnknownNode:
            pass
        # 2. traversal from B's canary: impact() (blast radius) and why()
        try:
            r = lin.impact("fact", wb["canary"])
            leaked["traversal"] += 1
        except UnknownNode:
            pass
        # 3. keyword search for B's secret (fulltext + vector, scope of A)
        hits = eng.recall(secret_b, wa["scope"], k=8)
        leaked["keyword"] += sum(
            1 for h in hits if secret_b in blob(h) or f"tenant {tag_b}" in str(h.get("value", ""))
        )
        notes["keyword_hits_for_foreign_secret"] = len(hits)
        # 4. the colliding id f0001: why() on a fact returns the fact's props; it must be A's
        r = lin.why("f0001")
        fv = next((f["props"].get("value") for f in r["facts"] if f["id"] == "f0001"), None)
        if fv != next(f["text"] for f in wa["facts"] if f["id"] == "f0001"):
            leaked["collision"] += 1
        # controls: the same services do work on A's own data
        own = {"canary_found": False, "keyword_found": False}
        try:
            own["canary_found"] = bool(lin.why(wa["canary"])["facts"])
        except UnknownNode:
            pass
        own["keyword_found"] = any(
            h["fact_id"] == wa["canary"] for h in eng.recall(wa["secret"], wa["scope"], k=8)
        )
        return {"leaked": leaked, "leaked_total": sum(leaked.values()), "control": own, **notes}

    def close(self) -> None:
        self.client.close()


# ================================================================================================ S-file / S-shared SQL
def _b1_rows(w: dict[str, Any]) -> dict[str, list[tuple]]:
    """Rows of the B1 tables for one tenant world (tenant_id is added by the S-shared loader)."""
    fr, fa, fl, fts = [], [], [], []
    for f in w["facts"]:
        fr.append(
            (
                f["id"],
                f"e_{f['topic']}",
                f["topic"],
                "note",
                f["text"],
                f["text"].lower(),
                "",
                w["scope"],
                "active",
                f["at"],
                OPEN,
                f["at"],
                1.0,
            )
        )
        fa.append((f["id"], f["agent"], f["at"]))
        fl += [(f["id"], p, "derived_from") for p in f["parents"]]
        fts.append((f["text"], f["id"]))
    sid = {s["id"]: i for i, s in enumerate(w["steps"], start=1)}
    return {
        "agents": [(a, "", T0) for a in w["agents"]],
        "sources": [(s["id"], s["uri"], "doc", 1.0, T0) for s in w["sources"]],
        "facts": fr, "fact_agents": fa, "fact_links": fl, "facts_fts": fts,
        "steps": [(sid[s["id"]], s["agent"], s["n"], s["at"]) for s in w["steps"]],
        "step_reads": [(sid[s["id"]], r) for s in w["steps"] for r in s["reads"]],
        "decisions": [(d["id"], d["agent"], d["task"], d["text"], d["at"], 0) for d in w["decisions"]],
        "decision_facts": [(d["id"], f) for d in w["decisions"] for f in d["based_on"]],
        "handoffs": [(h["id"], h["from"], h["to"], h["task"], "", h["at"]) for h in w["handoffs"]],
        "handoff_items": [(h["id"], "fact", f) for h in w["handoffs"] for f in h["carries"]],
        "tasks": [(t["id"], t["id"], 0, i, t["status"], T0) for i, t in enumerate(w["tasks"])],
        "deps": [(t["id"], d) for t in w["tasks"] for d in t["deps"]],
    }  # fmt: skip


FILE_INSERTS = {
    "agents": "INSERT INTO agents(id, role, created_at) VALUES(?,?,?)",
    "sources": "INSERT INTO sources(id, uri, kind, trust, created_at) VALUES(?,?,?,?,?)",
    "facts": "INSERT INTO facts VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)",
    "fact_agents": "INSERT INTO fact_agents(fact_id, agent_id, at) VALUES(?,?,?)",
    "fact_links": "INSERT INTO fact_links(src, dst, kind) VALUES(?,?,?)",
    "facts_fts": "INSERT INTO facts_fts(text, fact_id) VALUES(?,?)",
    "steps": "INSERT INTO steps(id, agent_id, n, at) VALUES(?,?,?,?)",
    "step_reads": "INSERT INTO step_reads(step_id, fact_id) VALUES(?,?)",
    "decisions": "INSERT INTO decisions(id, agent_id, task_id, text, at, flagged) VALUES(?,?,?,?,?,?)",
    "decision_facts": "INSERT INTO decision_facts(decision_id, fact_id) VALUES(?,?)",
    "handoffs": "INSERT INTO handoffs(id, from_agent, to_agent, task_id, note, at) VALUES(?,?,?,?,?,?)",
    "handoff_items": "INSERT INTO handoff_items(handoff_id, kind, item_id) VALUES(?,?,?)",
    "tasks": "INSERT INTO tasks(id, title, priority, seq, status, created_at) VALUES(?,?,?,?,?,?)",
    "deps": "INSERT INTO deps(task_id, dep_id) VALUES(?,?)",
}
TUNED = (
    "CREATE INDEX IF NOT EXISTS step_reads_fact ON step_reads(fact_id)",
    "CREATE INDEX IF NOT EXISTS handoff_items_item ON handoff_items(item_id)",
)

SHARED_SCHEMA = """
CREATE TABLE agents(tenant_id TEXT NOT NULL, id TEXT NOT NULL, role TEXT NOT NULL, created_at INTEGER NOT NULL, PRIMARY KEY(tenant_id, id));
CREATE TABLE sources(tenant_id TEXT NOT NULL, id TEXT NOT NULL, uri TEXT NOT NULL, kind TEXT, trust REAL, created_at INTEGER NOT NULL, PRIMARY KEY(tenant_id, id));
CREATE TABLE tasks(tenant_id TEXT NOT NULL, id TEXT NOT NULL, title TEXT NOT NULL, priority INTEGER NOT NULL, seq INTEGER NOT NULL,
  status TEXT NOT NULL, claimed_by TEXT NOT NULL DEFAULT '', lease_until INTEGER NOT NULL DEFAULT 0, version INTEGER NOT NULL DEFAULT 0,
  created_at INTEGER NOT NULL, done_at INTEGER NOT NULL DEFAULT 0, PRIMARY KEY(tenant_id, id));
CREATE INDEX tasks_ready ON tasks(tenant_id, status, priority DESC, seq);
CREATE TABLE deps(tenant_id TEXT NOT NULL, task_id TEXT NOT NULL, dep_id TEXT NOT NULL, PRIMARY KEY(tenant_id, task_id, dep_id));
CREATE INDEX deps_dep ON deps(tenant_id, dep_id);
CREATE TABLE facts(tenant_id TEXT NOT NULL, id TEXT NOT NULL, entity TEXT NOT NULL, entity_name TEXT NOT NULL, predicate TEXT NOT NULL,
  value TEXT NOT NULL, norm_value TEXT NOT NULL, tokens TEXT NOT NULL, scope TEXT NOT NULL, status TEXT NOT NULL, valid_from INTEGER NOT NULL,
  valid_to INTEGER NOT NULL, recorded_at INTEGER NOT NULL, confidence REAL NOT NULL, PRIMARY KEY(tenant_id, id));
CREATE INDEX facts_ep ON facts(tenant_id, entity, predicate, scope, status);
CREATE TABLE fact_agents(tenant_id TEXT NOT NULL, fact_id TEXT NOT NULL, agent_id TEXT NOT NULL, at INTEGER NOT NULL, PRIMARY KEY(tenant_id, fact_id, agent_id));
CREATE TABLE fact_links(tenant_id TEXT NOT NULL, src TEXT NOT NULL, dst TEXT NOT NULL, kind TEXT NOT NULL, PRIMARY KEY(tenant_id, src, dst, kind));
CREATE INDEX fact_links_dst ON fact_links(tenant_id, dst, kind);
CREATE TABLE decisions(tenant_id TEXT NOT NULL, id TEXT NOT NULL, agent_id TEXT NOT NULL, task_id TEXT NOT NULL, text TEXT NOT NULL, at INTEGER NOT NULL,
  flagged INTEGER NOT NULL DEFAULT 0, PRIMARY KEY(tenant_id, id));
CREATE TABLE decision_facts(tenant_id TEXT NOT NULL, decision_id TEXT NOT NULL, fact_id TEXT NOT NULL);
CREATE INDEX decision_facts_fact ON decision_facts(tenant_id, fact_id);
CREATE TABLE handoffs(tenant_id TEXT NOT NULL, id TEXT NOT NULL, from_agent TEXT NOT NULL, to_agent TEXT NOT NULL, task_id TEXT NOT NULL,
  note TEXT NOT NULL, at INTEGER NOT NULL, PRIMARY KEY(tenant_id, id));
CREATE TABLE handoff_items(tenant_id TEXT NOT NULL, handoff_id TEXT NOT NULL, kind TEXT NOT NULL, item_id TEXT NOT NULL);
CREATE INDEX handoff_items_item ON handoff_items(tenant_id, item_id);
CREATE TABLE steps(tenant_id TEXT NOT NULL, id INTEGER NOT NULL, agent_id TEXT NOT NULL, n INTEGER NOT NULL, at INTEGER NOT NULL, PRIMARY KEY(tenant_id, id));
CREATE TABLE step_reads(tenant_id TEXT NOT NULL, step_id INTEGER NOT NULL, fact_id TEXT NOT NULL);
CREATE INDEX step_reads_step ON step_reads(tenant_id, step_id);
CREATE INDEX step_reads_fact ON step_reads(tenant_id, fact_id);
CREATE VIRTUAL TABLE facts_fts USING fts5(text, fact_id UNINDEXED, tenant_id UNINDEXED);
"""
SHARED_TABLES = (
    "agents", "sources", "tasks", "deps", "facts", "fact_agents", "fact_links", "decisions", "decision_facts", "handoffs",
    "handoff_items", "steps", "step_reads",
)  # fmt: skip

# G4 / G3a statements. File arms: no tenant predicate. Shared arm: the same statements with a tenant predicate on every table.
SQL_FILE = {
    "q1": "SELECT value FROM facts WHERE id = ?",
    "q2": "SELECT d.id FROM decisions d JOIN decision_facts x ON x.decision_id = d.id WHERE x.fact_id = ?",
    "q3": (
        "WITH RECURSIVE anc(id, depth) AS (SELECT dst, 1 FROM fact_links WHERE src = ?1 AND kind = 'derived_from' "
        "UNION SELECT l.dst, a.depth + 1 FROM anc a JOIN fact_links l ON l.src = a.id AND l.kind = 'derived_from' WHERE a.depth < 4) "
        "SELECT DISTINCT id FROM anc"
    ),
    "q4a": "INSERT INTO facts VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)",
    "q4b": "INSERT INTO fact_links(src, dst, kind) VALUES(?,?,?)",
    "kw": "SELECT f.id, f.value FROM facts_fts t JOIN facts f ON f.id = t.fact_id WHERE facts_fts MATCH ?",
    "impact": (
        "SELECT d.id FROM decisions d JOIN decision_facts x ON x.decision_id = d.id WHERE x.fact_id = ? "
        "UNION SELECT dst FROM fact_links WHERE src = ?"
    ),
}
SQL_SHARED = {
    "q1": "SELECT value FROM facts WHERE tenant_id = ?1 AND id = ?2",
    "q2": "SELECT d.id FROM decisions d JOIN decision_facts x ON x.tenant_id = d.tenant_id AND x.decision_id = d.id WHERE x.tenant_id = ?1 AND x.fact_id = ?2",
    "q3": (
        "WITH RECURSIVE anc(id, depth) AS (SELECT dst, 1 FROM fact_links WHERE tenant_id = ?1 AND src = ?2 AND kind = 'derived_from' "
        "UNION SELECT l.dst, a.depth + 1 FROM anc a JOIN fact_links l ON l.tenant_id = ?1 AND l.src = a.id AND l.kind = 'derived_from' WHERE a.depth < 4) "
        "SELECT DISTINCT id FROM anc"
    ),
    "q4a": "INSERT INTO facts VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
    "q4b": "INSERT INTO fact_links(tenant_id, src, dst, kind) VALUES(?,?,?,?)",
    "kw": (
        "SELECT f.id, f.value FROM facts_fts t JOIN facts f ON f.tenant_id = t.tenant_id AND f.id = t.fact_id "
        "WHERE facts_fts MATCH ?2 AND t.tenant_id = ?1 AND f.tenant_id = ?1"
    ),
    "impact": (
        "SELECT d.id FROM decisions d JOIN decision_facts x ON x.tenant_id = d.tenant_id AND x.decision_id = d.id WHERE x.tenant_id = ?1 AND x.fact_id = ?2 "
        "UNION SELECT dst FROM fact_links WHERE tenant_id = ?1 AND src = ?2"
    ),
}


def tenant_predicate_sites() -> dict[str, int]:
    """Tenant-handling code size, countable honestly: S-shared statements that need a tenant predicate (occurrences of
    ``tenant_id`` in the statement texts above) vs S-file / F (zero: the binding picks the file / graph)."""
    return {
        "S-shared_statements": len(SQL_SHARED),
        "S-shared_tenant_id_occurrences": sum(s.count("tenant_id") for s in SQL_SHARED.values()),
        "S-file_tenant_predicates": sum(s.count("tenant_id") for s in SQL_FILE.values()),
    }


def _fts_query(secret: str) -> str:
    return f'"{secret}"'


def _norm(op: str, rows: Any) -> Any:
    if op == "q1":
        return [r[0] for r in rows]
    if op in ("q2", "q3"):
        return sorted(r[0] for r in rows)
    return [r[0] for r in rows]


class SqliteBase:
    def _connect(self, path: str) -> sqlite3.Connection:
        c = sqlite3.connect(path, isolation_level=None, check_same_thread=False)
        c.execute("PRAGMA busy_timeout = 10000")
        c.execute("PRAGMA synchronous = NORMAL")
        return c


class SFileArm(SqliteBase):
    """One SQLite file per tenant (B1 SCHEMA + FTS), WAL, synchronous=NORMAL."""

    name = "S-file"

    def __init__(self, root: Path):
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        self.worlds: dict[int, dict[str, Any]] = {}
        self.conns: dict[int, sqlite3.Connection] = {}
        self.arms: dict[int, Any] = {}
        self.cached = True  # S-file-cached (True) or S-file-open (False): the G4 access mode

    def path(self, k: int) -> str:
        return str(self.root / f"{tenant_name(k)}.db")

    def create_schema(self, k: int) -> float:
        t0 = time.perf_counter()
        c = self._connect(self.path(k))
        c.execute("PRAGMA journal_mode = WAL")
        c.executescript(SCHEMA)
        c.execute(FTS_SCHEMA)
        c.close()
        return time.perf_counter() - t0

    def load(self, k: int, w: dict[str, Any] | None = None) -> dict[str, int]:
        w = w or tenant_world(k)
        self.worlds[k] = w
        c = self._connect(self.path(k))
        rows = _b1_rows(w)
        c.execute("BEGIN")
        for t, sql in FILE_INSERTS.items():
            c.executemany(sql, rows[t])
        c.execute("COMMIT")
        for s in TUNED:
            c.execute(s)
        got = self.read_counts(c)
        c.close()
        want = counts(w)
        bad = {x: (want[x], got.get(x)) for x in want if got.get(x) != want[x]}
        if bad:
            raise AssertionError(f"S-file tenant {k}: store differs from the ledger (ledger, store): {bad}")
        return got

    @staticmethod
    def read_counts(c: sqlite3.Connection) -> dict[str, int]:
        def n(sql: str) -> int:
            return int(c.execute(sql).fetchone()[0])

        return {
            "agents": n("SELECT count(*) FROM agents"), "sources": n("SELECT count(*) FROM sources"),
            "facts": n("SELECT count(*) FROM facts"), "derived_edges": n("SELECT count(*) FROM fact_links WHERE kind='derived_from'"),
            "steps": n("SELECT count(*) FROM steps"), "reads": n("SELECT count(*) FROM step_reads"),
            "decisions": n("SELECT count(*) FROM decisions"), "based_on": n("SELECT count(*) FROM decision_facts"),
            "handoffs": n("SELECT count(*) FROM handoffs"), "carries": n("SELECT count(*) FROM handoff_items"),
            "tasks": n("SELECT count(*) FROM tasks"), "depends_on": n("SELECT count(*) FROM deps"),
        }  # fmt: skip

    # -- connections -------------------------------------------------------------------------------------
    def open_all(self, n: int) -> None:
        for k in range(n):
            if k not in self.conns:
                self.conns[k] = self._connect(self.path(k))

    def _use(self, k: int) -> tuple[sqlite3.Connection, bool]:
        if self.cached:
            c = self.conns.get(k)
            if c is None:
                c = self.conns[k] = self._connect(self.path(k))
            return c, False
        return self._connect(self.path(k)), True

    def _run(self, k: int, fn: Any) -> Any:
        c, temp = self._use(k)
        try:
            arm = common.sqlite_deadline(c)
            arm()
            return fn(c, arm)
        finally:
            if temp:
                c.close()

    def q1(self, k: int, fid: str) -> Any:
        return self._run(k, lambda c, arm: c.execute(SQL_FILE["q1"], (fid,)).fetchall())

    def q2(self, k: int, fid: str) -> Any:
        return self._run(k, lambda c, arm: c.execute(SQL_FILE["q2"], (fid,)).fetchall())

    def q3(self, k: int, fid: str) -> Any:
        return self._run(k, lambda c, arm: c.execute(SQL_FILE["q3"], (fid,)).fetchall())

    def q4(self, k: int, new_id: str, parent: str) -> Any:
        def go(c: sqlite3.Connection, arm: Any) -> list[tuple]:
            c.execute("BEGIN IMMEDIATE")
            try:
                c.execute(
                    SQL_FILE["q4a"],
                    (new_id, "", "", "note", f"written {new_id}", "", "", SCOPE, "active", T0, OPEN, T0, 1.0),
                )
                c.execute(SQL_FILE["q4b"], (new_id, parent, "derived_from"))
                c.execute("COMMIT")
            except BaseException:
                if c.in_transaction:
                    c.execute("ROLLBACK")
                raise
            return [(new_id,)]

        return self._run(k, go)

    norm = staticmethod(_norm)

    # -- G3a ---------------------------------------------------------------------------------------------
    def probe(self, a: int, b: int) -> dict[str, Any]:
        wa, wb = self.worlds[a], self.worlds[b]
        c = self._connect(self.path(a))  # A's binding: A's file only
        leaked = {"canary_lookup": 0, "traversal": 0, "keyword": 0, "collision": 0}
        leaked["canary_lookup"] = len(c.execute(SQL_FILE["q1"], (wb["canary"],)).fetchall())
        leaked["traversal"] = len(c.execute(SQL_FILE["q3"], (wb["canary"],)).fetchall()) + len(
            c.execute(SQL_FILE["impact"], (wb["canary"], wb["canary"])).fetchall()
        )
        leaked["keyword"] = len(c.execute(SQL_FILE["kw"], (_fts_query(wb["secret"]),)).fetchall())
        got = c.execute(SQL_FILE["q1"], ("f0001",)).fetchall()
        if [r[0] for r in got] != [next(f["text"] for f in wa["facts"] if f["id"] == "f0001")]:
            leaked["collision"] = 1
        own = {
            "canary_found": bool(c.execute(SQL_FILE["q1"], (wa["canary"],)).fetchall()),
            "keyword_found": bool(c.execute(SQL_FILE["kw"], (_fts_query(wa["secret"]),)).fetchall()),
        }
        c.close()
        return {"leaked": leaked, "leaked_total": sum(leaked.values()), "control": own}

    def file_size(self, k: int, checkpoint: bool = True) -> int:
        c = self._connect(self.path(k))
        if checkpoint:
            c.execute("PRAGMA wal_checkpoint(TRUNCATE)")
        c.close()
        p = Path(self.path(k))
        return p.stat().st_size

    def close(self) -> None:
        for c in self.conns.values():
            c.close()
        self.conns.clear()


class SSharedArm(SqliteBase):
    """One SQLite file, ``tenant_id`` leading every primary key and index, every statement filtered by tenant."""

    name = "S-shared"

    def __init__(self, root: Path):
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        self.p = str(self.root / "shared.db")
        self.conn = self._connect(self.p)
        self.conn.execute("PRAGMA journal_mode = WAL")
        self.conn.executescript(SHARED_SCHEMA)
        self.worlds: dict[int, dict[str, Any]] = {}

    def create_schema(self, k: int) -> float:
        return 0.0  # there is no per-tenant DDL

    def load(self, k: int, w: dict[str, Any] | None = None) -> dict[str, int]:
        w = w or tenant_world(k)
        self.worlds[k] = w
        ten = w["tenant"]
        rows = _b1_rows(w)
        c = self.conn
        c.execute("BEGIN")
        for t, sql in FILE_INSERTS.items():
            if t == "facts_fts":
                c.executemany(
                    "INSERT INTO facts_fts(text, fact_id, tenant_id) VALUES(?,?,?)",
                    [(*r, ten) for r in rows[t]],
                )
                continue
            tbl = t
            cols = sql.split("(", 1)[1].split(")", 1)[0] if "(" in sql.split("VALUES")[0] else None
            ph = ",".join("?" * (len(rows[t][0]) + 1)) if rows[t] else "?"
            if cols:
                c.executemany(
                    f"INSERT INTO {tbl}(tenant_id, {cols}) VALUES({ph})", [(ten, *r) for r in rows[t]]
                )
            else:
                c.executemany(f"INSERT INTO {tbl} VALUES({ph})", [(ten, *r) for r in rows[t]])
        c.execute("COMMIT")
        got = self.read_counts(ten)
        want = counts(w)
        bad = {x: (want[x], got.get(x)) for x in want if got.get(x) != want[x]}
        if bad:
            raise AssertionError(f"S-shared tenant {k}: store differs from the ledger (ledger, store): {bad}")
        return got

    def read_counts(self, ten: str) -> dict[str, int]:
        c = self.conn

        def n(sql: str) -> int:
            return int(c.execute(sql, (ten,)).fetchone()[0])

        return {
            "agents": n("SELECT count(*) FROM agents WHERE tenant_id=?"), "sources": n("SELECT count(*) FROM sources WHERE tenant_id=?"),
            "facts": n("SELECT count(*) FROM facts WHERE tenant_id=?"),
            "derived_edges": n("SELECT count(*) FROM fact_links WHERE tenant_id=? AND kind='derived_from'"),
            "steps": n("SELECT count(*) FROM steps WHERE tenant_id=?"), "reads": n("SELECT count(*) FROM step_reads WHERE tenant_id=?"),
            "decisions": n("SELECT count(*) FROM decisions WHERE tenant_id=?"), "based_on": n("SELECT count(*) FROM decision_facts WHERE tenant_id=?"),
            "handoffs": n("SELECT count(*) FROM handoffs WHERE tenant_id=?"), "carries": n("SELECT count(*) FROM handoff_items WHERE tenant_id=?"),
            "tasks": n("SELECT count(*) FROM tasks WHERE tenant_id=?"), "depends_on": n("SELECT count(*) FROM deps WHERE tenant_id=?"),
        }  # fmt: skip

    def _ten(self, k: int) -> str:
        return tenant_name(k)

    def q1(self, k: int, fid: str) -> Any:
        return self.conn.execute(SQL_SHARED["q1"], (self._ten(k), fid)).fetchall()

    def q2(self, k: int, fid: str) -> Any:
        return self.conn.execute(SQL_SHARED["q2"], (self._ten(k), fid)).fetchall()

    def q3(self, k: int, fid: str) -> Any:
        return self.conn.execute(SQL_SHARED["q3"], (self._ten(k), fid)).fetchall()

    def q4(self, k: int, new_id: str, parent: str) -> Any:
        c = self.conn
        t = self._ten(k)
        c.execute("BEGIN IMMEDIATE")
        try:
            c.execute(
                SQL_SHARED["q4a"],
                (t, new_id, "", "", "note", f"written {new_id}", "", "", SCOPE, "active", T0, OPEN, T0, 1.0),
            )
            c.execute(SQL_SHARED["q4b"], (t, new_id, parent, "derived_from"))
            c.execute("COMMIT")
        except BaseException:
            if c.in_transaction:
                c.execute("ROLLBACK")
            raise
        return [(new_id,)]

    norm = staticmethod(_norm)

    def probe(self, a: int, b: int) -> dict[str, Any]:
        wa, wb = self.worlds[a], self.worlds[b]
        c, ta = self.conn, self._ten(a)  # A's binding: the shared file + A's tenant id on every statement
        leaked = {"canary_lookup": 0, "traversal": 0, "keyword": 0, "collision": 0}
        leaked["canary_lookup"] = len(c.execute(SQL_SHARED["q1"], (ta, wb["canary"])).fetchall())
        leaked["traversal"] = len(c.execute(SQL_SHARED["q3"], (ta, wb["canary"])).fetchall()) + len(
            c.execute(SQL_SHARED["impact"], (ta, wb["canary"])).fetchall()
        )
        leaked["keyword"] = len(c.execute(SQL_SHARED["kw"], (ta, _fts_query(wb["secret"]))).fetchall())
        got = c.execute(SQL_SHARED["q1"], (ta, "f0001")).fetchall()
        if [r[0] for r in got] != [next(f["text"] for f in wa["facts"] if f["id"] == "f0001")]:
            leaked["collision"] = 1
        own = {
            "canary_found": bool(c.execute(SQL_SHARED["q1"], (ta, wa["canary"])).fetchall()),
            "keyword_found": bool(c.execute(SQL_SHARED["kw"], (ta, _fts_query(wa["secret"]))).fetchall()),
        }
        return {"leaked": leaked, "leaked_total": sum(leaked.values()), "control": own}

    def file_size(self, checkpoint: bool = True) -> int:
        if checkpoint:
            self.conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
        return Path(self.p).stat().st_size

    def close(self) -> None:
        self.conn.close()
