"""B1 SQLite: "just use a relational database", configured the way a competent engineer would.

* one database file per tenant (``<root>/B1/<tenant>/crucible.db``), WAL, ``busy_timeout``, one connection per thread;
* every state change is a ``BEGIN IMMEDIATE`` transaction (claims, completes, assertions, forgetting);
* tables for tasks / deps / facts / fact_agents / fact_links / decisions / handoffs / steps; provenance questions
  (``why``) use a recursive CTE over ``fact_links``; "what did X know at step N" uses the ``steps`` tables;
* recall is SQLite FTS5 (BM25) over the fact text; there are no embeddings, so paraphrases are not deduplicated.

The vector arm (B2, ``vector.py``) subclasses this class and swaps recall + duplicate detection for embeddings.
"""

from __future__ import annotations

import contextlib
import os
import sqlite3
import threading
from collections.abc import Callable, Iterable, Iterator, Sequence
from pathlib import Path
from typing import Any

from plexus.crucible.api import (
    OPEN,
    UnknownReference,
    Unsupported,
    valid_tenant,
)
from plexus.crucible.backends.base import (
    MAX_RECALL_K,
    artifact_specs,
    assert_result,
    check_completable,
    check_lease,
    check_source_uri,
    claim_result,
    complete_result,
    decision_facts,
    external_deps,
    new_task_ids,
    prepare_assertion,
    query_words,
    raise_missing_deps,
    recall_hit,
    task_deps,
    task_status_view,
    unique,
)
from plexus.crucible.util import (
    classify,
    fact_text,
    new_id,
    normalize,
    now_ms,
    scope_chain,
    token_key,
)

SCHEMA = """
CREATE TABLE IF NOT EXISTS agents(id TEXT PRIMARY KEY, role TEXT NOT NULL, created_at INTEGER NOT NULL);
CREATE TABLE IF NOT EXISTS tasks(
  id TEXT PRIMARY KEY, title TEXT NOT NULL, priority INTEGER NOT NULL, seq INTEGER NOT NULL,
  status TEXT NOT NULL, claimed_by TEXT NOT NULL DEFAULT '', lease_until INTEGER NOT NULL DEFAULT 0,
  version INTEGER NOT NULL DEFAULT 0, created_at INTEGER NOT NULL, done_at INTEGER NOT NULL DEFAULT 0);
CREATE INDEX IF NOT EXISTS tasks_ready ON tasks(status, priority DESC, seq);
CREATE TABLE IF NOT EXISTS deps(task_id TEXT NOT NULL, dep_id TEXT NOT NULL, PRIMARY KEY(task_id, dep_id));
CREATE INDEX IF NOT EXISTS deps_dep ON deps(dep_id);
CREATE TABLE IF NOT EXISTS artifacts(
  id TEXT PRIMARY KEY, task_id TEXT NOT NULL, kind TEXT, uri TEXT, hash TEXT, summary TEXT,
  agent_id TEXT NOT NULL, created_at INTEGER NOT NULL);
CREATE TABLE IF NOT EXISTS sources(
  id TEXT PRIMARY KEY, uri TEXT NOT NULL UNIQUE, kind TEXT, trust REAL, created_at INTEGER NOT NULL);
CREATE TABLE IF NOT EXISTS facts(
  id TEXT PRIMARY KEY, entity TEXT NOT NULL, entity_name TEXT NOT NULL, predicate TEXT NOT NULL,
  value TEXT NOT NULL, norm_value TEXT NOT NULL, tokens TEXT NOT NULL, scope TEXT NOT NULL,
  status TEXT NOT NULL, valid_from INTEGER NOT NULL, valid_to INTEGER NOT NULL, recorded_at INTEGER NOT NULL,
  confidence REAL NOT NULL);
CREATE INDEX IF NOT EXISTS facts_ep ON facts(entity, predicate, scope, status);
CREATE TABLE IF NOT EXISTS fact_agents(
  fact_id TEXT NOT NULL, agent_id TEXT NOT NULL, at INTEGER NOT NULL, PRIMARY KEY(fact_id, agent_id));
CREATE TABLE IF NOT EXISTS fact_links(
  src TEXT NOT NULL, dst TEXT NOT NULL, kind TEXT NOT NULL, PRIMARY KEY(src, dst, kind));
CREATE INDEX IF NOT EXISTS fact_links_dst ON fact_links(dst, kind);
CREATE TABLE IF NOT EXISTS decisions(
  id TEXT PRIMARY KEY, agent_id TEXT NOT NULL, task_id TEXT NOT NULL, text TEXT NOT NULL, at INTEGER NOT NULL,
  flagged INTEGER NOT NULL DEFAULT 0);
CREATE TABLE IF NOT EXISTS decision_facts(decision_id TEXT NOT NULL, fact_id TEXT NOT NULL);
CREATE INDEX IF NOT EXISTS decision_facts_fact ON decision_facts(fact_id);
CREATE TABLE IF NOT EXISTS handoffs(
  id TEXT PRIMARY KEY, from_agent TEXT NOT NULL, to_agent TEXT NOT NULL, task_id TEXT NOT NULL,
  note TEXT NOT NULL, at INTEGER NOT NULL);
CREATE TABLE IF NOT EXISTS handoff_items(handoff_id TEXT NOT NULL, kind TEXT NOT NULL, item_id TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS episodes(
  id TEXT PRIMARY KEY, agent_id TEXT NOT NULL, step INTEGER, text TEXT NOT NULL, at INTEGER NOT NULL);
CREATE TABLE IF NOT EXISTS steps(
  id INTEGER PRIMARY KEY AUTOINCREMENT, agent_id TEXT NOT NULL, n INTEGER NOT NULL, at INTEGER NOT NULL,
  UNIQUE(agent_id, n));
CREATE TABLE IF NOT EXISTS step_reads(step_id INTEGER NOT NULL, fact_id TEXT NOT NULL);
CREATE INDEX IF NOT EXISTS step_reads_step ON step_reads(step_id);
CREATE TABLE IF NOT EXISTS step_wrote(step_id INTEGER NOT NULL, node_id TEXT NOT NULL, label TEXT NOT NULL,
  summary TEXT NOT NULL);
CREATE INDEX IF NOT EXISTS step_wrote_step ON step_wrote(step_id);
"""

FTS_SCHEMA = "CREATE VIRTUAL TABLE IF NOT EXISTS facts_fts USING fts5(text, fact_id UNINDEXED)"


class SqliteBackend:
    name = "B1"
    label = "SQLite"
    capabilities = frozenset({"why", "knew_at", "as_of", "contradictions", "forget_cascade", "dependencies"})
    isolation = "one SQLite database file per tenant; the tenant name is validated before it becomes a path"

    def __init__(self, tenant: str, root: str | os.PathLike[str]):
        self.tenant = valid_tenant(tenant)
        self.dir = Path(root) / self.name / self.tenant
        self.dir.mkdir(parents=True, exist_ok=True)
        self.path = str(self.dir / "crucible.db")
        self._tls = threading.local()
        self._conns: list[sqlite3.Connection] = []
        self._conns_lock = threading.Lock()
        with self._conn() as c:
            c.execute("PRAGMA journal_mode=WAL")
            c.executescript(SCHEMA)
            self._init_schema(c)

    # -- connection plumbing ------------------------------------------------------------------------------
    def _init_schema(self, c: sqlite3.Connection) -> None:
        c.execute(FTS_SCHEMA)

    @contextlib.contextmanager
    def _conn(self) -> Iterator[sqlite3.Connection]:
        c = getattr(self._tls, "conn", None)
        if c is None:
            c = sqlite3.connect(self.path, timeout=120, isolation_level=None, check_same_thread=False)
            c.row_factory = sqlite3.Row
            c.execute("PRAGMA busy_timeout=120000")
            c.execute("PRAGMA synchronous=NORMAL")
            self._tls.conn = c
            with self._conns_lock:
                self._conns.append(c)
        yield c

    @contextlib.contextmanager
    def _tx(self) -> Iterator[sqlite3.Connection]:
        """``BEGIN IMMEDIATE`` ... ``COMMIT`` (``ROLLBACK`` on error)."""
        with self._conn() as c:
            c.execute("BEGIN IMMEDIATE")
            try:
                yield c
            except BaseException:
                c.execute("ROLLBACK")
                raise
            else:
                c.execute("COMMIT")

    def close(self) -> None:
        with self._conns_lock:
            conns, self._conns = self._conns, []
        for c in conns:
            with contextlib.suppress(sqlite3.Error):
                c.close()
        self._tls = threading.local()

    # -- agents --------------------------------------------------------------------------------------------
    def register_agent(self, agent_id: str, role: str = "") -> None:
        with self._tx() as c:
            c.execute(
                "INSERT INTO agents(id, role, created_at) VALUES(?,?,?) "
                "ON CONFLICT(id) DO UPDATE SET role=CASE WHEN excluded.role!='' THEN excluded.role ELSE role END",
                (agent_id, role, now_ms()),
            )

    def _ensure_agent(self, c: sqlite3.Connection, agent_id: str) -> None:
        c.execute(
            "INSERT OR IGNORE INTO agents(id, role, created_at) VALUES(?,?,?)", (agent_id, "", now_ms())
        )

    # -- steps (lineage bookkeeping) ------------------------------------------------------------------------
    def _step(self, c: sqlite3.Connection, agent_id: str, at: int) -> int:
        row = c.execute(
            "SELECT COALESCE(MAX(n),0)+1 AS n FROM steps WHERE agent_id=?", (agent_id,)
        ).fetchone()
        cur = c.execute("INSERT INTO steps(agent_id, n, at) VALUES(?,?,?)", (agent_id, row["n"], at))
        return int(cur.lastrowid or 0)

    @staticmethod
    def _reads(c: sqlite3.Connection, step_id: int, fact_ids: Iterable[str]) -> None:
        c.executemany(
            "INSERT INTO step_reads(step_id, fact_id) VALUES(?,?)",
            [(step_id, f) for f in dict.fromkeys(fact_ids)],
        )

    @staticmethod
    def _wrote(c: sqlite3.Connection, step_id: int, node_id: str, label: str, summary: str) -> None:
        c.execute(
            "INSERT INTO step_wrote(step_id, node_id, label, summary) VALUES(?,?,?,?)",
            (step_id, node_id, label, summary),
        )

    # -- memory ----------------------------------------------------------------------------------------------
    def remember_episode(self, agent_id: str, text: str, step: int | None = None) -> str:
        eid, at = new_id(), now_ms()
        with self._tx() as c:
            self._ensure_agent(c, agent_id)
            c.execute(
                "INSERT INTO episodes(id, agent_id, step, text, at) VALUES(?,?,?,?,?)",
                (eid, agent_id, step, text, at),
            )
            self._step(c, agent_id, at)
            self._index_episode(c, eid, text)
        return eid

    def _index_episode(self, c: sqlite3.Connection, eid: str, text: str) -> None:  # B2 embeds episodes
        return None

    def add_source(self, uri: str, kind: str = "doc", trust: float = 1.0) -> str:
        check_source_uri(uri)
        with self._tx() as c:
            row = c.execute("SELECT id FROM sources WHERE uri=?", (uri,)).fetchone()
            if row:
                return row["id"]
            sid = new_id()
            c.execute(
                "INSERT INTO sources(id, uri, kind, trust, created_at) VALUES(?,?,?,?,?)",
                (sid, uri, kind, trust, now_ms()),
            )
            return sid

    # hooks for the vector arm ---------------------------------------------------------------------------
    def _prepare_fact(self, entity_name: str, predicate: str, value: str) -> Any:
        return None

    def _dup_predicate(self, prepared: Any, value: str) -> Callable[[dict[str, Any]], bool] | None:
        return None

    def _index_fact(self, c: sqlite3.Connection, fact_id: str, text: str, prepared: Any) -> None:
        c.execute("INSERT INTO facts_fts(text, fact_id) VALUES(?,?)", (text, fact_id))

    def _forget_index(self, c: sqlite3.Connection, fact_ids: Sequence[str]) -> None:
        return None  # status filtering happens in the query; the index entry can stay

    def assert_fact(
        self,
        agent_id: str,
        subject: str,
        predicate: str,
        value: str,
        scope: str = "global",
        source_id: str | None = None,
        derived_from: Sequence[str] = (),
        confidence: float = 1.0,
        supersede: bool = False,
        now: int | None = None,
    ) -> dict[str, Any]:
        asn = prepare_assertion(subject, predicate, value, scope, source_id, derived_from, now, now_ms)
        entity, pred, norm_value, t, origins = asn.entity, asn.predicate, asn.norm_value, asn.t, asn.origins
        prepared = self._prepare_fact(
            " ".join(subject.split()), pred, value
        )  # embeddings happen outside the txn
        is_dup = self._dup_predicate(prepared, value)
        with self._tx() as c:
            self._check_origins(c, source_id, derived_from)
            self._ensure_agent(c, agent_id)
            cur = self._current(c, entity, pred, scope)
            dup, closing, clashing, ts = classify(cur, agent_id, norm_value, supersede, t, is_dup)
            step = self._step(c, agent_id, t)
            if dup is not None:
                c.execute(
                    "INSERT OR IGNORE INTO fact_agents(fact_id, agent_id, at) VALUES(?,?,?)",
                    (dup["id"], agent_id, t),
                )
                for o in origins:
                    c.execute(
                        "INSERT OR IGNORE INTO fact_links(src, dst, kind) VALUES(?,?,'derived_from')",
                        (dup["id"], o),
                    )
                for f in closing:
                    c.execute("UPDATE facts SET valid_to=?, status='superseded' WHERE id=?", (ts, f["id"]))
                    c.execute(
                        "INSERT OR IGNORE INTO fact_links(src, dst, kind) VALUES(?,?,'supersedes')",
                        (dup["id"], f["id"]),
                    )
                self._reads(c, step, [dup["id"], *(f["id"] for f in closing)])
                return assert_result(dup["id"], dup["id"], closing, [])
            fid = new_id()
            name_row = c.execute("SELECT entity_name FROM facts WHERE entity=? LIMIT 1", (entity,)).fetchone()
            ename = name_row["entity_name"] if name_row else " ".join(subject.split())
            c.execute(
                "INSERT INTO facts(id, entity, entity_name, predicate, value, norm_value, tokens, scope, status, "
                "valid_from, valid_to, recorded_at, confidence) VALUES(?,?,?,?,?,?,?,?,'active',?,?,?,?)",
                (
                    fid,
                    entity,
                    ename,
                    pred,
                    " ".join(value.split()),
                    norm_value,
                    token_key(value),
                    scope,
                    ts,
                    OPEN,
                    t,
                    confidence,
                ),
            )
            c.execute("INSERT INTO fact_agents(fact_id, agent_id, at) VALUES(?,?,?)", (fid, agent_id, t))
            for o in origins:
                c.execute("INSERT INTO fact_links(src, dst, kind) VALUES(?,?,'derived_from')", (fid, o))
            for f in closing:
                c.execute("UPDATE facts SET valid_to=?, status='superseded' WHERE id=?", (ts, f["id"]))
                c.execute("INSERT INTO fact_links(src, dst, kind) VALUES(?,?,'supersedes')", (fid, f["id"]))
            for f in clashing:
                c.execute("INSERT INTO fact_links(src, dst, kind) VALUES(?,?,'contradicts')", (fid, f["id"]))
            self._index_fact(c, fid, fact_text(ename, pred, value), prepared)
            self._wrote(c, step, fid, "Fact", " ".join(value.split()))
            self._reads(c, step, [*(f["id"] for f in closing), *(f["id"] for f in clashing)])
            return assert_result(fid, None, closing, clashing)

    @staticmethod
    def _check_origins(c: sqlite3.Connection, source_id: str | None, derived_from: Sequence[str]) -> None:
        if source_id and not c.execute("SELECT 1 FROM sources WHERE id=?", (source_id,)).fetchone():
            raise UnknownReference(f"unknown source id: {source_id}")
        for o in derived_from:
            if not c.execute(
                "SELECT 1 FROM facts WHERE id=? UNION SELECT 1 FROM sources WHERE id=?", (o, o)
            ).fetchone():
                raise UnknownReference(f"unknown origin id: {o}")

    @staticmethod
    def _current(c: sqlite3.Connection, entity: str, predicate: str, scope: str) -> list[dict[str, Any]]:
        rows = c.execute(
            "SELECT f.id, f.norm_value, f.valid_from, f.tokens, f.value, "
            "(SELECT group_concat(agent_id, char(31)) FROM fact_agents a WHERE a.fact_id=f.id) AS agents "
            "FROM facts f WHERE f.entity=? AND f.predicate=? AND f.scope=? AND f.status='active' AND f.valid_to=? "
            "ORDER BY f.valid_from, f.id",
            (entity, predicate, scope, OPEN),
        ).fetchall()
        return [
            {
                "id": r["id"],
                "norm_value": r["norm_value"],
                "valid_from": r["valid_from"],
                "tokens": r["tokens"],
                "value": r["value"],
                "asserted_by": (r["agents"] or "").split("\x1f") if r["agents"] else [],
            }
            for r in rows
        ]

    # -- recall ------------------------------------------------------------------------------------------------
    def _visible_clause(self, scope: str, as_of: int | None) -> tuple[str, list[Any], int]:
        chain = scope_chain(scope)
        t = as_of if as_of is not None else now_ms()
        statuses = ("active",) if as_of is None else ("active", "superseded")
        clause = (
            f"f.scope IN ({','.join('?' * len(chain))}) AND f.status IN ({','.join('?' * len(statuses))}) "
            "AND f.valid_from <= ? AND ? < f.valid_to"
        )
        return clause, [*chain, *statuses, t, t], t

    def recall(
        self, agent_id: str, query: str, scope: str = "global", k: int = 8, as_of: int | None = None
    ) -> list[dict[str, Any]]:
        if k <= 0:
            return []
        k = min(k, MAX_RECALL_K)
        clause, args, t = self._visible_clause(scope, as_of)
        qwords = query_words(query)
        hits: list[dict[str, Any]] = []
        if qwords:
            match = " OR ".join('"' + w.replace('"', "") + '"' for w in qwords)
            with self._conn() as c:
                rows = c.execute(
                    "SELECT f.id, f.entity_name, f.predicate, f.value, f.status, bm25(facts_fts) AS score "
                    f"FROM facts_fts JOIN facts f ON f.id = facts_fts.fact_id WHERE facts_fts MATCH ? AND {clause} "
                    "ORDER BY score ASC, f.id ASC LIMIT ?",
                    [match, *args, k],
                ).fetchall()
            hits = [self._hit(r) for r in rows]
        self._log_recall(agent_id, hits)
        return hits

    @staticmethod
    def _hit(r: sqlite3.Row) -> dict[str, Any]:
        return recall_hit(
            r["id"],
            fact_text(r["entity_name"], r["predicate"], r["value"]),
            r["entity_name"],
            r["predicate"],
            r["value"],
            r["status"],
            float(r["score"]),
        )

    def _log_recall(self, agent_id: str, hits: Sequence[dict[str, Any]]) -> None:
        """Record the recall as a step with READ edges (what lets ``knew_at`` answer later)."""
        at = now_ms()
        with self._tx() as c:
            self._ensure_agent(c, agent_id)
            self._reads(c, self._step(c, agent_id, at), [h["fact_id"] for h in hits])

    # -- forgetting -------------------------------------------------------------------------------------------
    def forget_source(self, source_id: str) -> dict[str, Any]:
        t = now_ms()
        with self._tx() as c:
            if not c.execute("SELECT 1 FROM sources WHERE id=?", (source_id,)).fetchone():
                raise UnknownReference(f"no source with id '{source_id}'")
            rows = c.execute(
                "WITH RECURSIVE reach(id, depth) AS ("
                "  SELECT src, 1 FROM fact_links WHERE dst=? AND kind='derived_from' "
                "  UNION SELECT l.src, r.depth+1 FROM fact_links l JOIN reach r ON l.dst=r.id "
                "  WHERE l.kind='derived_from' AND r.depth < 5) "
                "SELECT DISTINCT f.id FROM reach JOIN facts f ON f.id=reach.id WHERE f.status != 'forgotten'",
                (source_id,),
            ).fetchall()
            ids = sorted(r["id"] for r in rows)
            for fid in ids:
                c.execute(
                    "UPDATE facts SET status='forgotten', valid_to=MIN(valid_to, ?) WHERE id=?", (t, fid)
                )
                c.execute(
                    "UPDATE decisions SET flagged=1 WHERE id IN (SELECT decision_id FROM decision_facts WHERE fact_id=?)",
                    (fid,),
                )
            self._forget_index(c, ids)
            return {"source_id": source_id, "fact_ids": ids}

    # -- fact reads -----------------------------------------------------------------------------------------------
    def facts(self, subject: str, predicate: str, scope: str = "global") -> list[dict[str, Any]]:
        entity, pred = normalize(subject), normalize(predicate)
        with self._conn() as c:
            rows = c.execute(
                "SELECT id, value, status, valid_from, valid_to FROM facts WHERE entity=? AND predicate=? AND scope=? "
                "ORDER BY valid_from, id",
                (entity, pred, scope),
            ).fetchall()
            out = []
            for r in rows:
                out.append(
                    {
                        "fact_id": r["id"],
                        "value": r["value"],
                        "status": r["status"],
                        "valid_from": r["valid_from"],
                        "valid_to": r["valid_to"],
                        "asserted_by": self._col(
                            c,
                            "SELECT agent_id FROM fact_agents WHERE fact_id=? ORDER BY at, agent_id",
                            r["id"],
                        ),
                        "supersedes": self._col(
                            c,
                            "SELECT dst FROM fact_links WHERE src=? AND kind='supersedes' ORDER BY dst",
                            r["id"],
                        ),
                        "contradicts": self._col(
                            c,
                            "SELECT dst FROM fact_links WHERE src=? AND kind='contradicts' ORDER BY dst",
                            r["id"],
                        ),
                    }
                )
        return out

    @staticmethod
    def _col(c: sqlite3.Connection, sql: str, *args: Any) -> list[str]:
        return [r[0] for r in c.execute(sql, args).fetchall()]

    def as_of(self, subject: str, predicate: str, t: int, scope: str = "global") -> dict[str, Any] | None:
        chain = scope_chain(scope)
        entity, pred = normalize(subject), normalize(predicate)
        with self._conn() as c:
            rows = c.execute(
                "SELECT id, value, status, valid_from, valid_to, scope FROM facts "
                f"WHERE entity=? AND predicate=? AND scope IN ({','.join('?' * len(chain))}) "
                "AND status IN ('active','superseded') AND valid_from <= ? AND ? < valid_to "
                "ORDER BY CASE scope WHEN ? THEN 0 ELSE 1 END, valid_from DESC, id LIMIT 20",
                [entity, pred, *chain, t, t, scope],
            ).fetchall()
        if not rows:
            return None

        def one(r: sqlite3.Row) -> dict[str, Any]:
            return {
                "fact_id": r["id"],
                "value": r["value"],
                "status": r["status"],
                "valid_from": r["valid_from"],
                "valid_to": r["valid_to"],
            }

        best = one(rows[0])
        best["also_valid"] = [one(r) for r in rows[1:]]
        return best

    # -- coordination -------------------------------------------------------------------------------------------
    def create_tasks(self, tasks: Sequence[dict[str, Any]]) -> list[str]:
        if not tasks:
            return []
        ids = new_task_ids(tasks, new_id)
        t0 = now_ms()
        with self._tx() as c:
            existing = {
                r["id"]
                for r in c.execute(f"SELECT id FROM tasks WHERE id IN ({','.join('?' * len(ids))})", ids)
            }
            if existing:
                raise ValueError(f"task id(s) already exist: {', '.join(sorted(existing))}")
            ext = external_deps(tasks, ids)
            if ext:
                have = {
                    r["id"]
                    for r in c.execute(f"SELECT id FROM tasks WHERE id IN ({','.join('?' * len(ext))})", ext)
                }
                raise_missing_deps([d for d in ext if d not in have])
            base = c.execute("SELECT COALESCE(MAX(seq),-1)+1 AS s FROM tasks").fetchone()["s"]
            for i, (tid, t) in enumerate(zip(ids, tasks, strict=True)):
                c.execute(
                    "INSERT INTO tasks(id, title, priority, seq, status, created_at) VALUES(?,?,?,?, 'open', ?)",
                    (tid, str(t["title"]), int(t.get("priority", 0)), base + i, t0),
                )
                for d in task_deps(t):
                    c.execute("INSERT INTO deps(task_id, dep_id) VALUES(?,?)", (tid, d))
        return ids

    def claim_next_task(
        self, agent_id: str, lease_ms: int = 60_000, now: int | None = None
    ) -> dict[str, Any] | None:
        check_lease(lease_ms)
        t = now if now is not None else now_ms()
        with self._tx() as c:
            if not c.execute("SELECT 1 FROM agents WHERE id=?", (agent_id,)).fetchone():
                raise UnknownReference(f"unknown agent id(s): {agent_id}")
            row = c.execute(
                "SELECT id, title, priority, version, claimed_by FROM tasks t "
                "WHERE (t.status='open' OR (t.status='claimed' AND t.lease_until < ?)) "
                "AND NOT EXISTS (SELECT 1 FROM deps d JOIN tasks p ON p.id = d.dep_id "
                "                WHERE d.task_id = t.id AND p.status != 'done') "
                "ORDER BY t.priority DESC, t.seq ASC, t.id ASC LIMIT 1",
                (t,),
            ).fetchone()
            if row is None:
                return None
            c.execute(
                "UPDATE tasks SET status='claimed', claimed_by=?, lease_until=?, version=version+1 WHERE id=?",
                (agent_id, t + lease_ms, row["id"]),
            )
            return claim_result(row, row["version"] + 1, t + lease_ms, row["claimed_by"])

    def heartbeat(self, agent_id: str, task_id: str, lease_ms: int = 60_000, now: int | None = None) -> bool:
        check_lease(lease_ms)
        t = now if now is not None else now_ms()
        with self._tx() as c:
            cur = c.execute(
                "UPDATE tasks SET lease_until = MAX(lease_until, ?) WHERE id=? AND claimed_by=? AND status='claimed'",
                (t + lease_ms, task_id, agent_id),
            )
            return cur.rowcount == 1

    def complete_task(
        self, agent_id: str, task_id: str, expected_version: int, artifacts: Sequence[dict[str, Any]] = ()
    ) -> dict[str, Any]:
        arts = artifact_specs(artifacts, new_id)
        t = now_ms()
        with self._tx() as c:
            row = c.execute("SELECT status, claimed_by, version FROM tasks WHERE id=?", (task_id,)).fetchone()
            check_completable(task_id, agent_id, expected_version, row)
            c.execute("UPDATE tasks SET status='done', done_at=?, version=version+1 WHERE id=?", (t, task_id))
            for a in arts:
                c.execute(
                    "INSERT INTO artifacts(id, task_id, kind, uri, hash, summary, agent_id, created_at) VALUES(?,?,?,?,?,?,?,?)",
                    (a["id"], task_id, a["kind"], a["uri"], a["hash"], a["summary"], agent_id, t),
                )
            return complete_result(task_id, expected_version, arts)

    def handoff(
        self,
        agent_id: str,
        to_agent: str,
        task_id: str,
        note: str,
        artifact_ids: Iterable[str] = (),
        fact_ids: Iterable[str] = (),
    ) -> str:
        arts, facts = unique(artifact_ids), unique(fact_ids)
        hid, t = new_id(), now_ms()
        with self._tx() as c:
            self._require(c, "agents", [agent_id, to_agent])
            self._require(c, "tasks", [task_id])
            self._require(c, "artifacts", arts)
            self._require(c, "facts", facts)
            c.execute(
                "INSERT INTO handoffs(id, from_agent, to_agent, task_id, note, at) VALUES(?,?,?,?,?,?)",
                (hid, agent_id, to_agent, task_id, note, t),
            )
            c.executemany(
                "INSERT INTO handoff_items(handoff_id, kind, item_id) VALUES(?,?,?)",
                [(hid, "artifact", a) for a in arts] + [(hid, "fact", f) for f in facts],
            )
            step = self._step(c, agent_id, t)
            self._wrote(c, step, hid, "Handoff", note)
            self._reads(c, step, facts)
        return hid

    def record_decision(
        self, agent_id: str, task_id: str, text: str, based_on_fact_ids: Iterable[str] = ()
    ) -> str:
        facts = decision_facts(based_on_fact_ids)
        did, t = new_id(), now_ms()
        with self._tx() as c:
            self._require(c, "agents", [agent_id])
            self._require(c, "tasks", [task_id])
            self._require(c, "facts", facts)
            c.execute(
                "INSERT INTO decisions(id, agent_id, task_id, text, at) VALUES(?,?,?,?,?)",
                (did, agent_id, task_id, text, t),
            )
            c.executemany(
                "INSERT INTO decision_facts(decision_id, fact_id) VALUES(?,?)", [(did, f) for f in facts]
            )
            step = self._step(c, agent_id, t)
            self._wrote(c, step, did, "Decision", text)
            self._reads(c, step, facts)
        return did

    @staticmethod
    def _require(c: sqlite3.Connection, table: str, ids: Sequence[str]) -> None:
        if not ids:
            return
        have = {
            r["id"]
            for r in c.execute(f"SELECT id FROM {table} WHERE id IN ({','.join('?' * len(ids))})", list(ids))
        }
        missing = [i for i in dict.fromkeys(ids) if i not in have]
        if missing:
            raise UnknownReference(f"unknown {table.rstrip('s')} id(s): {', '.join(missing)}")

    def task_status(self, task_id: str) -> dict[str, Any] | None:
        with self._conn() as c:
            r = c.execute("SELECT * FROM tasks WHERE id=?", (task_id,)).fetchone()
            if r is None:
                return None
            deps = c.execute(
                "SELECT p.id, p.status FROM deps d JOIN tasks p ON p.id=d.dep_id WHERE d.task_id=? ORDER BY p.id",
                (task_id,),
            ).fetchall()
        return task_status_view(r, deps)

    def list_tasks(self) -> list[dict[str, Any]]:
        with self._conn() as c:
            rows = c.execute(
                "SELECT id, status, claimed_by, version, lease_until FROM tasks ORDER BY seq, id"
            ).fetchall()
        return [dict(r) for r in rows]

    # -- lineage ---------------------------------------------------------------------------------------------------
    def why(self, node_id: str) -> dict[str, Any]:
        with self._conn() as c:
            dec = c.execute("SELECT * FROM decisions WHERE id=?", (node_id,)).fetchone()
            if dec is not None:
                kind = "Decision"
                fact_ids = self._col(
                    c, "SELECT fact_id FROM decision_facts WHERE decision_id=? ORDER BY fact_id", node_id
                )
            elif c.execute("SELECT 1 FROM facts WHERE id=?", (node_id,)).fetchone():
                kind, fact_ids = "Fact", [node_id]
            else:
                raise UnknownReference(f"no decision or fact with id '{node_id}'")
            facts = []
            for fid in fact_ids:
                f = c.execute("SELECT * FROM facts WHERE id=?", (fid,)).fetchone()
                sources = self._col(
                    c,
                    "WITH RECURSIVE up(id, depth) AS (SELECT dst, 1 FROM fact_links WHERE src=? AND kind='derived_from' "
                    "UNION SELECT l.dst, u.depth+1 FROM fact_links l JOIN up u ON l.src=u.id "
                    "WHERE l.kind='derived_from' AND u.depth < 3) "
                    "SELECT DISTINCT s.id FROM up JOIN sources s ON s.id=up.id ORDER BY s.id",
                    fid,
                )
                facts.append(
                    {
                        "id": fid,
                        "value": f["value"],
                        "status": f["status"],
                        "asserted_by": self._col(
                            c, "SELECT agent_id FROM fact_agents WHERE fact_id=? ORDER BY at, agent_id", fid
                        ),
                        "sources": sources,
                        "supersedes": self._col(
                            c, "SELECT dst FROM fact_links WHERE src=? AND kind='supersedes'", fid
                        ),
                        "superseded_by": self._col(
                            c, "SELECT src FROM fact_links WHERE dst=? AND kind='supersedes'", fid
                        ),
                        "contradicts": self._col(
                            c, "SELECT dst FROM fact_links WHERE src=? AND kind='contradicts'", fid
                        ),
                    }
                )
        agents = sorted({a for f in facts for a in f["asserted_by"]})
        return {
            "root": node_id,
            "kind": kind,
            "facts": facts,
            "agents": agents,
            "sources": sorted({s for f in facts for s in f["sources"]}),
        }

    def knew_at(self, agent_id: str, step_n: int) -> dict[str, Any]:
        out: dict[str, Any] = {"agent_id": agent_id, "step_n": None, "at": None, "facts": [], "wrote": []}
        with self._conn() as c:
            cut = c.execute(
                "SELECT id, n, at FROM steps WHERE agent_id=? AND n <= ? ORDER BY n DESC LIMIT 1",
                (agent_id, step_n),
            ).fetchone()
            if cut is None:
                return out
            out["step_n"], out["at"] = cut["n"], cut["at"]
            rows = c.execute(
                "SELECT f.id, f.entity_name, f.predicate, f.value, f.status, f.valid_from, f.valid_to, MIN(s.n) AS first_n "
                "FROM steps s JOIN step_reads r ON r.step_id=s.id JOIN facts f ON f.id=r.fact_id "
                "WHERE s.agent_id=? AND s.n <= ? AND f.valid_from <= ? AND ? < f.valid_to "
                "GROUP BY f.id ORDER BY first_n, f.id",
                (agent_id, cut["n"], cut["at"], cut["at"]),
            ).fetchall()
            out["facts"] = [
                {
                    "fact_id": r["id"],
                    "entity": r["entity_name"],
                    "predicate": r["predicate"],
                    "value": r["value"],
                    "status": r["status"],
                    "valid_from": r["valid_from"],
                    "valid_to": r["valid_to"],
                    "read_at_step": r["first_n"],
                }
                for r in rows
            ]
            wrote = c.execute(
                "SELECT w.node_id, w.label, w.summary, s.n FROM steps s JOIN step_wrote w ON w.step_id=s.id "
                "WHERE s.agent_id=? AND s.n <= ? ORDER BY s.n, w.node_id",
                (agent_id, cut["n"]),
            ).fetchall()
            out["wrote"] = [
                {"id": w["node_id"], "label": w["label"], "summary": w["summary"], "step_n": w["n"]}
                for w in wrote
            ]
        return out


def unsupported(what: str) -> Unsupported:
    return Unsupported(f"{what}: this arm keeps no provenance; Layer 2 answers it by LLM over its artifacts")
