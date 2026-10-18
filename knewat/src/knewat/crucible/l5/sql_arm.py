"""B1h-L5: the hand-written-SQL arm of L5b (plan §5.4, pre-registered in docs/BASELINE.md "§5.4 pre-registration").

The L5b graph (history + noise + the 90-day read schedule) is exported once into a SQLite file with a conventional
relational schema holding the same columns the Cypher reads use (:func:`export_graph`); :class:`SqlRecall` then
answers every probe with three parameterised statements:

1. ``ENTITIES_SQL``: the entities the query words name (FTS5, OR of the words) with each one's fan by ``GROUP BY``
   over active, valid, in-scope facts (what ``engram/recall_entities`` returns);
2. ``CANDIDATES_SQL``: KNN seeds (``sqlite-vec`` ``vec0``, top ``over``) unioned with the FTS5 keyword hits, the
   scope / status / validity filters, the fan-damped sibling expansion, best ``k`` by rank (what ``engram/recall``
   returns, plus a ``kw`` flag = the fact is a keyword hit, which the Cypher side gets from ``engram/recall_keywords``);
3. ``ACTIVATION_SQL``: ``A(f)``, graded salience and the protection flag per candidate, computed in SQL (a window
   function for the newest 50 events, ``power`` / ``ln``, the D-012 weights, the contract's suspect-recall rule and
   the D-013 salience weights) - what ``activation/activation`` + ``knewat.activation.service`` produce.

The two lexical rules both arms apply in Python stay in Python (every word of an entity's name in the query; the
exact-keyword bypass), and the final ``mult`` formula is the shared pure function ``knewat.activation.rank.rerank``
over the columns each arm returned. ``sqlite-vec`` has no scope pre-filter either, so the same x4 over-fetch retry
is used. No LLM. ``sql_lines()`` counts the SQL written for the arm (non-blank, non-comment lines of the three
statements), the number the pre-registration asks for.
"""

from __future__ import annotations

import math
import sqlite3
import struct
import time
from pathlib import Path
from typing import Any

from knewat.activation.rank import rerank
from knewat.activation.service import FactActivation
from knewat.activation.settings import Settings
from knewat.common import normalize
from knewat.embed import Embedder
from knewat.engram import service as engram_service
from knewat.engram.service import (
    EXPAND_BOOST,
    MAX_K,
    MAX_OVER,
    OVERFETCH,
    RECALL_ENTITIES,
    RETRY_FACTOR,
    SIBLINGS_PER_ENTITY,
    _query_words,
    _tokens,
    fact_text,
)
from knewat.graph.client import GraphClient

OPEN = 9_999_999_999_999
DIM = 384

SCHEMA = """
CREATE TABLE scopes(id TEXT PRIMARY KEY);
CREATE TABLE scope_inherits(child TEXT NOT NULL, parent TEXT NOT NULL);
CREATE TABLE entities(id TEXT PRIMARY KEY, name TEXT NOT NULL, norm_name TEXT NOT NULL);
CREATE INDEX entities_norm ON entities(norm_name);
-- FTS5 is configured like the RediSearch full-text index Knewat uses: a stemmer and '_' kept inside tokens
-- (unicode61 alone splits 'billing_cycle' into two words and does not stem, which changes the keyword hits).
CREATE VIRTUAL TABLE entities_fts USING fts5(name, content='entities', content_rowid='rowid', tokenize="porter unicode61 tokenchars '_'");
CREATE TABLE facts(id TEXT PRIMARY KEY, entity_id TEXT NOT NULL, scope_id TEXT NOT NULL, predicate TEXT NOT NULL,
  value TEXT NOT NULL, status TEXT NOT NULL, valid_from INTEGER NOT NULL, valid_to INTEGER NOT NULL,
  created_at INTEGER NOT NULL, surprise REAL NOT NULL DEFAULT 0, pinned INTEGER NOT NULL DEFAULT 0,
  verify_state TEXT NOT NULL DEFAULT 'verified', suspect_since INTEGER NOT NULL DEFAULT 0,
  verify_after INTEGER NOT NULL DEFAULT 9999999999999, embedding BLOB NOT NULL);
CREATE INDEX facts_entity ON facts(entity_id, status);
CREATE VIRTUAL TABLE facts_fts USING fts5(value, content='facts', content_rowid='rowid', tokenize="porter unicode61 tokenchars '_'");
CREATE VIRTUAL TABLE fact_vec USING vec0(fact_id TEXT PRIMARY KEY, embedding float[384] distance_metric=cosine);
CREATE TABLE fact_events(fact_id TEXT NOT NULL, kind TEXT NOT NULL, t INTEGER NOT NULL,
  agent_id TEXT NOT NULL DEFAULT '', suspect INTEGER NOT NULL DEFAULT -1);
CREATE INDEX fact_events_fact ON fact_events(fact_id, t);
CREATE TABLE fact_decisions(decision_id TEXT NOT NULL, fact_id TEXT NOT NULL, t INTEGER NOT NULL,
  flagged INTEGER NOT NULL, tasks_done INTEGER NOT NULL, artifacts_ok INTEGER NOT NULL);
CREATE INDEX fact_decisions_fact ON fact_decisions(fact_id);
CREATE TABLE fact_links(src TEXT NOT NULL, dst TEXT NOT NULL, kind TEXT NOT NULL);
CREATE INDEX fact_links_src ON fact_links(src, kind);
CREATE TABLE sources(id TEXT PRIMARY KEY, trust TEXT NOT NULL);
"""

# -- statement 1: the entities a query names, with their fan (engram/recall_entities) ---------------------------------
ENTITIES_SQL = """
WITH RECURSIVE sids(id, lvl) AS (
  SELECT :scope, 0
  UNION SELECT si.parent, lvl + 1 FROM scope_inherits si JOIN sids ON si.child = sids.id WHERE lvl < 3),
hits AS (
  SELECT e.id, e.name, bm25(entities_fts) AS score
  FROM entities_fts JOIN entities e ON e.rowid = entities_fts.rowid
  WHERE entities_fts MATCH :q ORDER BY score, e.id LIMIT :lim)
SELECT h.id AS entity_id, h.name, -h.score AS score, count(f.id) AS fan
FROM hits h LEFT JOIN facts f ON f.entity_id = h.id
  AND f.status IN (:s0, :s1, :s2) AND f.valid_from <= :t AND :t < f.valid_to
  AND f.scope_id IN (SELECT id FROM sids)
GROUP BY h.id ORDER BY h.score, h.id
"""

# -- statement 2: vector + keyword seeds, filters, fan-damped sibling expansion (engram/recall + recall_keywords) ------
CANDIDATES_SQL = """
WITH RECURSIVE sids(id, lvl) AS (
  SELECT :scope, 0
  UNION SELECT si.parent, lvl + 1 FROM scope_inherits si JOIN sids ON si.child = sids.id WHERE lvl < 3),
vh AS (SELECT fact_id AS id, distance AS s FROM fact_vec WHERE embedding MATCH :q AND k = :over),
kh AS (
  SELECT f.id, vec_distance_cosine(f.embedding, :q) AS s
  FROM facts_fts JOIN facts f ON f.rowid = facts_fts.rowid
  WHERE facts_fts MATCH :kw AND :kw <> '' AND f.status IN (:s0, :s1, :s2) AND f.valid_from <= :t AND :t < f.valid_to
    AND f.scope_id IN (SELECT id FROM sids)
  ORDER BY bm25(facts_fts) LIMIT :fetch_k),
seeds AS (
  SELECT f.id, f.entity_id, min(h.s) AS score
  FROM (SELECT id, s FROM vh UNION ALL SELECT id, s FROM kh) h JOIN facts f ON f.id = h.id
  WHERE f.status IN (:s0, :s1, :s2) AND f.valid_from <= :t AND :t < f.valid_to AND f.scope_id IN (SELECT id FROM sids)
  GROUP BY f.id ORDER BY score, f.id LIMIT :k),
fan AS (SELECT entity_id, count(*) AS n FROM facts WHERE status = 'active' GROUP BY entity_id),
seedd AS (
  SELECT s.id, s.entity_id, s.score,
    CASE WHEN NOT :damp THEN 1.0 WHEN coalesce(fan.n, 0) < 1 THEN 1.0 WHEN ln(fan.n) >= :smax THEN 0.0
         ELSE 1.0 - ln(fan.n) / :smax END AS damp
  FROM seeds s LEFT JOIN fan ON fan.entity_id = s.entity_id),
sib AS (
  SELECT s.id AS seed, g.id, vec_distance_cosine(g.embedding, :q) AS d, s.damp,
    row_number() OVER (PARTITION BY s.id ORDER BY vec_distance_cosine(g.embedding, :q), g.id) AS rn
  FROM seedd s JOIN facts g ON g.entity_id = s.entity_id AND g.id <> s.id
    AND g.status IN (:s0, :s1, :s2) AND g.valid_from <= :t AND :t < g.valid_to AND g.scope_id IN (SELECT id FROM sids)),
cands AS (
  SELECT id, score AS rank, score AS dist, 1 AS seed, NULL AS via FROM seedd
  UNION ALL SELECT id, max(0.0, d - :boost * damp), d, 0, seed FROM sib WHERE rn <= :sibs),
best AS (
  SELECT id, min(rank) AS rank, min(dist) AS dist, max(seed) AS isseed, min(via) AS via
  FROM cands GROUP BY id ORDER BY rank, id LIMIT :k)
SELECT f.id AS fact_id, f.entity_id, e.name AS entity_name, f.predicate, f.value, f.status, f.valid_from, f.valid_to,
  f.scope_id, b.dist AS score, b.rank, CASE WHEN b.isseed = 1 THEN NULL ELSE b.via END AS via,
  (SELECT count(*) FROM vh) AS raw, f.surprise, f.verify_state, f.suspect_since, f.verify_after,
  EXISTS (SELECT 1 FROM kh WHERE kh.id = f.id) AS kw
FROM best b JOIN facts f ON f.id = b.id JOIN entities e ON e.id = f.entity_id
ORDER BY b.rank, f.id
"""

# -- statement 3: A(f), salience and protection per fact (activation/activation + knewat.activation.service) ----------
# `ids` is a VALUES list built per call (one placeholder per fact id).
ACTIVATION_SQL = """
WITH RECURSIVE ids(id) AS (VALUES {ids}),
reads AS (
  SELECT e.fact_id, e.kind, e.t, e.agent_id, row_number() OVER (PARTITION BY e.fact_id ORDER BY e.t DESC) AS rn,
    (e.kind = 'recall' AND (e.suspect = 1 OR (f.verify_state = 'suspect' AND e.t > f.suspect_since)
                            OR f.verify_after <= e.t)) AS doubted
  FROM fact_events e JOIN ids ON ids.id = e.fact_id JOIN facts f ON f.id = e.fact_id
  WHERE e.kind IN ('use', 'recall') AND e.t <= :now),
ev AS (
  SELECT f.id AS fact_id, f.created_at AS t, 1.0 AS w FROM facts f JOIN ids ON ids.id = f.id
  UNION ALL SELECT fact_id, t, CASE kind WHEN 'recall' THEN 0.3 ELSE 1.0 END FROM reads WHERE rn <= 50 AND NOT doubted
  UNION ALL SELECT e.fact_id, e.t, CASE e.kind WHEN 'verified' THEN 2.0 ELSE 1.0 END
    FROM fact_events e JOIN ids ON ids.id = e.fact_id JOIN facts f ON f.id = e.fact_id
    WHERE e.kind IN ('reassert', 'verified', 'handoff') AND e.t <= :now AND NOT (e.kind = 'reassert' AND e.t <= f.created_at)
  UNION ALL SELECT d.fact_id, d.t, 1.0 FROM fact_decisions d JOIN ids ON ids.id = d.fact_id WHERE d.t <= :now),
newest AS (SELECT fact_id, t, w, row_number() OVER (PARTITION BY fact_id ORDER BY t DESC) AS rn FROM ev),
base AS (SELECT fact_id, sum(w * power(max(:now - t, 60000) / 1000.0, -0.5)) AS s FROM newest WHERE rn <= 50 GROUP BY fact_id),
trusted(fact_id, id, lvl) AS (
  SELECT id, id, 0 FROM ids
  UNION ALL SELECT tr.fact_id, l.dst, tr.lvl + 1 FROM trusted tr JOIN fact_links l ON l.src = tr.id AND l.kind = 'derived_from' WHERE tr.lvl < 3),
inp AS (
  SELECT f.id AS fact_id, f.pinned, f.surprise, f.created_at,
    (SELECT count(*) FROM fact_decisions d WHERE d.fact_id = f.id AND NOT d.flagged) AS dec_any,
    (SELECT count(*) FROM fact_decisions d WHERE d.fact_id = f.id AND NOT d.flagged AND d.t <= :now) AS decisions,
    (SELECT coalesce(sum(d.artifacts_ok), 0) FROM fact_decisions d WHERE d.fact_id = f.id AND NOT d.flagged AND d.t <= :now) AS artifacts_ok,
    (SELECT coalesce(sum(d.tasks_done), 0) FROM fact_decisions d WHERE d.fact_id = f.id AND NOT d.flagged AND d.t <= :now) AS tasks_done,
    (SELECT count(*) FROM fact_events e WHERE e.fact_id = f.id AND e.kind = 'verified' AND e.t <= :now) AS verified,
    (SELECT count(*) FROM fact_events e WHERE e.fact_id = f.id AND e.kind = 'handoff') AS hand_any,
    (SELECT count(*) FROM fact_events e WHERE e.fact_id = f.id AND e.kind = 'handoff' AND e.t <= :now) AS handoffs,
    (SELECT max(0, count(DISTINCT r.agent_id) - 1) FROM reads r WHERE r.fact_id = f.id AND r.kind = 'use' AND r.agent_id <> '' AND r.rn <= 50) AS use_agents,
    EXISTS (SELECT 1 FROM trusted tr JOIN sources s ON s.id = tr.id WHERE tr.fact_id = f.id AND tr.lvl > 0 AND s.trust = 'high') AS trusted,
    EXISTS (SELECT 1 FROM fact_links l WHERE l.src = f.id AND l.kind IN ('supersedes', 'contradicts')) AS linked
  FROM facts f JOIN ids ON ids.id = f.id),
sal AS (
  SELECT i.*, CASE WHEN decisions + verified + artifacts_ok + tasks_done + use_agents + handoffs + trusted + pinned = 0 THEN 0.0
    ELSE 1.0 - exp(-(1.0 * decisions + 1.5 * verified + 1.0 * artifacts_ok + 0.5 * tasks_done + 0.5 * use_agents
                     + 0.5 * handoffs + 1.0 * trusted + 3.0 * pinned)) END AS salience
  FROM inp i)
SELECT s.fact_id, s.salience,
  ln(coalesce(b.s, 0.0) + CASE WHEN s.surprise <= 0 THEN 0 ELSE 1 + floor(4 * min(s.surprise, 1.0) + 0.5) END
     * power(max(:now - s.created_at, 60000) / 1000.0, -0.5)) AS activation,
  (s.pinned OR s.dec_any > 0 OR s.hand_any > 0 OR s.linked OR s.trusted) AS protected
FROM sal s LEFT JOIN base b ON b.fact_id = s.fact_id
"""


def sql_lines() -> int:
    """Non-blank, non-comment lines of the three statements (the pre-registered "lines of SQL written")."""
    return sum(
        1
        for stmt in (ENTITIES_SQL, CANDIDATES_SQL, ACTIVATION_SQL)
        for ln in stmt.splitlines()
        if ln.strip() and not ln.strip().startswith("--")
    )


def _blob(vec: list[float]) -> bytes:
    return struct.pack(f"{len(vec)}f", *vec)


def _fts_or(words: list[str]) -> str:
    return " OR ".join('"' + w.replace('"', '""') + '"' for w in words)


def connect(path: str | Path) -> sqlite3.Connection:
    import sqlite_vec  # benchmark-only dependency (dev group)

    c = sqlite3.connect(str(path), check_same_thread=False)
    c.enable_load_extension(True)
    sqlite_vec.load(c)
    c.enable_load_extension(False)
    c.row_factory = sqlite3.Row
    return c


# -- export ------------------------------------------------------------------------------------------------------------
def export_graph(client: GraphClient, graph: str, path: str | Path) -> dict[str, int]:
    """Copy the L5b tenant graph into a fresh SQLite file at ``path``; returns the row counts written."""
    p = Path(path)
    if p.exists():
        p.unlink()
    g = client.graph(graph)

    def q(cypher: str) -> list[list[Any]]:
        return g.ro_query(cypher).result_set

    c = connect(p)
    c.executescript(SCHEMA)
    c.execute("BEGIN")
    c.executemany("INSERT INTO scopes VALUES(?)", q("MATCH (s:Scope) RETURN s.id"))
    c.executemany(
        "INSERT INTO scope_inherits VALUES(?,?)",
        q("MATCH (a:Scope)-[:INHERITS]->(b:Scope) RETURN a.id, b.id"),
    )
    c.executemany(
        "INSERT INTO entities VALUES(?,?,?)",
        q("MATCH (e:Entity) RETURN e.id, e.name, coalesce(e.norm_name, '')"),
    )
    facts = q(
        "MATCH (f:Fact)-[:ABOUT]->(e:Entity) MATCH (f)-[:IN_SCOPE]->(s:Scope) "
        "RETURN f.id, e.id, s.id, f.predicate, f.value, f.status, f.valid_from, f.valid_to, f.created_at, "
        "coalesce(f.surprise, 0.0), coalesce(f.pinned, false), coalesce(f.verify_state, 'verified'), "
        "coalesce(f.suspect_since, 0), coalesce(f.verify_after, 9999999999999), f.embedding"
    )
    c.executemany(
        "INSERT INTO facts VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        [(*r[:10], int(bool(r[10])), r[11], r[12], r[13], _blob([float(x) for x in r[14]])) for r in facts],
    )
    c.executemany(
        "INSERT INTO fact_vec(fact_id, embedding) VALUES(?,?)",
        [(r[0], _blob([float(x) for x in r[14]])) for r in facts],
    )
    c.executemany(
        "INSERT INTO fact_events VALUES(?,?,?,?,?)",
        q(
            "MATCH (s:Step)-[r:READ]->(f:Fact) RETURN f.id, CASE WHEN r.via = 'use' THEN 'use' ELSE 'recall' END, "
            "coalesce(r.at, s.at), coalesce(s.agent_id, ''), CASE WHEN r.suspect IS NULL THEN -1 WHEN r.suspect THEN 1 ELSE 0 END"
        ),
    )
    c.executemany(
        "INSERT INTO fact_events(fact_id, kind, t) VALUES(?,'reassert',?)",
        q("MATCH (f:Fact)-[a:ASSERTED_BY]->(:Agent) RETURN f.id, a.at"),
    )
    c.executemany(
        "INSERT INTO fact_events(fact_id, kind, t) VALUES(?,'verified',?)",
        q("MATCH (f:Fact)-[v:VERIFIED_BY]->(:Agent) RETURN f.id, v.at"),
    )
    c.executemany(
        "INSERT INTO fact_events(fact_id, kind, t) VALUES(?,'handoff',?)",
        q("MATCH (h:Handoff)-[:CARRIES]->(f:Fact) RETURN f.id, h.created_at"),
    )
    done = dict(q("MATCH (d:Decision)-[:FOR]->(t:Task {status: 'done'}) RETURN d.id, count(t)"))
    arts = dict(
        q(
            "MATCH (d:Decision)-[:FOR]->(:Task {status: 'done'})<-[:FOR]-(x:Artifact)-[:VERIFIED_BY {independent: true}]->(:Agent) "
            "RETURN d.id, count(DISTINCT x)"  # mirrors activation/activation after audit C1
        )
    )
    c.executemany(
        "INSERT INTO fact_decisions VALUES(?,?,?,?,?,?)",
        [
            (d, f, t, int(bool(fl)), int(done.get(d, 0)), int(arts.get(d, 0)))
            for d, f, t, fl in q(
                "MATCH (d:Decision)-[:BASED_ON]->(f:Fact) RETURN d.id, f.id, d.created_at, coalesce(d.flagged, false)"
            )
        ],
    )
    links = [(a, b, "supersedes") for a, b in q("MATCH (f:Fact)-[:SUPERSEDES]->(o:Fact) RETURN f.id, o.id")]
    links += [(a, b, "contradicts") for a, b in q("MATCH (f:Fact)-[:CONTRADICTS]-(o:Fact) RETURN f.id, o.id")]
    links += [(a, b, "derived_from") for a, b in q("MATCH (f:Fact)-[:DERIVED_FROM]->(x) RETURN f.id, x.id")]
    c.executemany("INSERT INTO fact_links VALUES(?,?,?)", links)
    c.executemany(
        "INSERT INTO sources VALUES(?,?)", q("MATCH (s:Source) RETURN s.id, coalesce(toString(s.trust), '')")
    )
    c.execute("INSERT INTO entities_fts(entities_fts) VALUES('rebuild')")
    c.execute("INSERT INTO facts_fts(facts_fts) VALUES('rebuild')")
    c.execute("COMMIT")
    c.execute("ANALYZE")
    counts = {
        t: int(c.execute(f"SELECT count(*) FROM {t}").fetchone()[0])
        for t in ("scopes", "entities", "facts", "fact_events", "fact_decisions", "fact_links", "sources")
    }
    c.close()
    return counts


# -- the arm -----------------------------------------------------------------------------------------------------------
class SqlRecall:
    """``recall`` over the exported SQLite file with the harness-facing surface of ``Engram`` (``recall``,
    ``_resolve_entities``); ``statements`` / ``sql_ms`` accumulate per call (reset by the caller)."""

    def __init__(self, path: str | Path, embedder: Embedder):
        self.conn = connect(path)
        self.embedder = embedder
        self.statements = 0
        self.sql_ms = 0.0

    def close(self) -> None:
        self.conn.close()

    def reset(self) -> None:
        self.statements, self.sql_ms = 0, 0.0

    def _run(self, sql: str, params: dict[str, Any] | list[Any]) -> list[sqlite3.Row]:
        t0 = time.perf_counter()
        rows = self.conn.execute(sql, params).fetchall()
        self.sql_ms += (time.perf_counter() - t0) * 1000
        self.statements += 1
        return rows

    @staticmethod
    def _st(statuses: list[str]) -> dict[str, str]:
        s = list(statuses) + ["", "", ""]
        return {"s0": s[0], "s1": s[1], "s2": s[2]}

    def _resolve_entities(
        self, query: str, scope_id: str, t: int, statuses: list[str]
    ) -> dict[str, dict[str, Any]]:
        words = _query_words(query)
        if not words:
            return {}
        have = set(_tokens(query))
        base = {"scope": scope_id, "lim": RECALL_ENTITIES, "t": t, **self._st(statuses)}
        out: dict[str, dict[str, Any]] = {}
        for r in self._run(ENTITIES_SQL, {**base, "q": _fts_or(words)}):
            name_words = _tokens(r["name"] or "")
            if name_words and all(w in have for w in name_words):
                out[r["entity_id"]] = {"name": r["name"], "fan": int(r["fan"]), "score": float(r["score"])}
        if not out:  # the exact-name fallback of Engram._resolve_entities
            exact = self._run(
                "SELECT id, name FROM entities WHERE norm_name = :n ORDER BY id LIMIT 1",
                {"n": normalize(query)},
            )
            if exact:
                fans = self._run(
                    ENTITIES_SQL, {**base, "q": _fts_or(_tokens(exact[0]["name"]) or [exact[0]["name"]])}
                )
                fan = next((int(f["fan"]) for f in fans if f["entity_id"] == exact[0]["id"]), 0)
                out[exact[0]["id"]] = {"name": exact[0]["name"], "fan": fan, "score": float("inf")}
        return out

    def _candidates(
        self,
        qv: list[float],
        query: str,
        scope_id: str,
        k: int,
        t: int,
        statuses: list[str],
        damp: bool,
        smax: float,
    ) -> list[dict[str, Any]]:
        words = _query_words(query)
        over = max(k * OVERFETCH, 1)
        params = {
            "scope": scope_id, "q": _blob(qv), "k": k, "fetch_k": k, "t": t, "kw": _fts_or(words),
            "boost": EXPAND_BOOST, "sibs": SIBLINGS_PER_ENTITY, "damp": int(damp), "smax": float(smax), **self._st(statuses),
        }  # fmt: skip
        while True:
            over = min(over, MAX_OVER)
            rows = [dict(r) for r in self._run(CANDIDATES_SQL, {**params, "over": over})]
            if len(rows) >= k or over >= MAX_OVER or (rows and rows[0]["raw"] < over):
                return rows
            over *= RETRY_FACTOR

    def _activation(self, fact_ids: list[str], now: int) -> dict[str, FactActivation]:
        if not fact_ids:
            return {}
        sql = ACTIVATION_SQL.replace("{ids}", ",".join(f"(:i{n})" for n in range(len(fact_ids))))
        out: dict[str, FactActivation] = {}
        params = {"now": now, **{f"i{n}": fid for n, fid in enumerate(fact_ids)}}
        for r in self._run(sql, params):
            a = float("-inf") if r["activation"] is None else float(r["activation"])
            out[r["fact_id"]] = FactActivation(
                fact_id=r["fact_id"], status="", created_at=0, surprise=0.0, pinned=False, verify_state="",
                suspect_since=0, verify_after=0, events=[], activation=a, protected=bool(r["protected"]),
                salience=float(r["salience"]),
            )  # fmt: skip
        return out

    def activation_all(self, now: int) -> dict[str, FactActivation]:
        """Every fact's A(f) / salience / protected (the fidelity check against ``Activation.compute``)."""
        ids = [r[0] for r in self.conn.execute("SELECT id FROM facts ORDER BY id").fetchall()]
        out: dict[str, FactActivation] = {}
        for i in range(0, len(ids), 200):
            out.update(self._activation(ids[i : i + 200], now))
        return out

    def recall(
        self,
        query: str,
        scope_id: str,
        k: int = 8,
        budget_chars: int = 2000,
        *,
        forgetting: bool | None = None,
        separation: bool | None = None,
        settings: Settings | None = None,
        now: int | None = None,
    ) -> list[dict[str, Any]]:
        """The same contract as ``Engram.recall`` (active facts, no ``as_of``, no hops), over SQLite."""
        settings = settings or Settings.from_env()
        fg = settings.forgetting if forgetting is None else forgetting
        sp = settings.separation if separation is None else separation
        k = min(k, MAX_K)
        t = now if now is not None else engram_service._now_ms()
        statuses = ["active"]
        entities = self._resolve_entities(query, scope_id, t, statuses) if sp else {}
        rerank_on = fg or bool(entities)
        fetch_k = min(2 * k, 2 * MAX_K) if rerank_on else k
        qv = self.embedder.embed([query])[0]
        rows = self._candidates(qv, query, scope_id, fetch_k, t, statuses, sp, settings.s_max)
        acts: dict[str, FactActivation] = {}
        if rerank_on:
            if fg:
                acts = self._activation([r["fact_id"] for r in rows], t)
            top = rerank(
                rows, acts, settings=settings, k=k, kw_ids={r["fact_id"] for r in rows if r["kw"]},
                words=_query_words(query), entities={eid: e["fan"] for eid, e in entities.items()},
                forgetting=fg, separation=sp,
            )  # fmt: skip
            rows = [x.row for x in top]
        out: list[dict[str, Any]] = []
        used = 0
        for r in rows:
            text = fact_text(r["entity_name"], r["predicate"], r["value"])
            if used + len(text) > budget_chars and out:
                break
            used += len(text)
            fa = acts.get(r["fact_id"])
            out.append(
                {
                    "fact_id": r["fact_id"],
                    "text": text,
                    "score": r["score"],
                    "entity": r["entity_name"],
                    "predicate": r["predicate"],
                    "value": r["value"],
                    "via": r["via"],
                    "activation": None if fa is None else fa.activation,
                    "protected": None if fa is None else fa.protected,
                }  # fmt: skip
            )
        return out


def activation_fidelity(sql: SqlRecall, acts_graph: dict[str, FactActivation], now: int) -> dict[str, Any]:
    """Compare SQL ``A(f)`` / salience / protected with the graph side for every fact; returns counts and the worst gap."""
    sql_acts = sql.activation_all(now)
    worst = 0.0
    bad: list[dict[str, Any]] = []
    for fid, g in acts_graph.items():
        s = sql_acts.get(fid)
        if s is None:
            bad.append({"fact_id": fid, "why": "missing in SQL"})
            continue
        da = (
            abs(s.activation - g.activation)
            if math.isfinite(g.activation) and math.isfinite(s.activation)
            else (0.0 if s.activation == g.activation else float("inf"))
        )
        ds = abs(s.salience - g.salience)
        worst = max(worst, da, ds)
        if da > 1e-6 or ds > 1e-6 or s.protected != g.protected:
            bad.append(
                {
                    "fact_id": fid,
                    "a_sql": s.activation,
                    "a_graph": g.activation,
                    "sal_sql": s.salience,
                    "sal_graph": g.salience,
                    "prot_sql": s.protected,
                    "prot_graph": g.protected,
                }
            )  # noqa: E501
    return {"facts": len(acts_graph), "disagreements": len(bad), "worst_abs_gap": worst, "examples": bad[:10]}
