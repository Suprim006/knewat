"""Deterministic arms for family A (blast radius) and A-dag: B1h (SQL), B1h-untuned, P-tuned, P-naive.

Every arm takes a :class:`~plexus.crucible.l6.world.QuestionA` and returns ``(answer, meta)`` where ``answer`` has the
shape of ``QuestionA.answer``. ``meta`` = ``{latency_ms, server_ms, statements, error}``; ``error`` is ``"timeout"`` when
the 5,000 ms budget of any statement is exceeded (the question then counts as wrong, its latency is the budget).
The product arm ``P`` (``impact``) lives in ``arms_product.py`` because it needs the traversal fix.
"""

from __future__ import annotations

import json
import sqlite3
import time
from pathlib import Path
from typing import Any

from plexus.crucible.l6.world import QuestionA, QuestionDag

TIMEOUT_MS = 5000


class Timeout(Exception):
    pass


def meta(t0: float, server_ms: float, statements: int, error: str = "") -> dict[str, Any]:
    return {
        "latency_ms": round((time.perf_counter() - t0) * 1000, 2), "server_ms": round(server_ms, 3),
        "statements": statements, "error": error,
    }  # fmt: skip


def shape(
    facts: int,
    agents: int,
    decisions: int,
    handoffs: int,
    probes: list[str],
    present: set[str],
    earliest: list[str],
) -> dict[str, Any]:
    return {
        "facts": facts, "agents": agents, "decisions": decisions, "handoffs": handoffs,
        "probes": [p in present for p in probes], "earliest5": earliest,
    }  # fmt: skip


# ------------------------------------------------------------------------------------------------ B1h (SQL)
CLOSURE = (
    "WITH RECURSIVE d(id) AS ("
    " SELECT src FROM fact_links WHERE dst=:s AND kind='derived_from'"
    " UNION SELECT l.src FROM fact_links l JOIN d ON l.dst=d.id WHERE l.kind='derived_from'),"
    " m AS MATERIALIZED (SELECT id FROM d) "
)
BLAST_SQL = (
    CLOSURE + "SELECT (SELECT count(*) FROM m) AS facts, "
    "(SELECT count(DISTINCT s.agent_id) FROM m {X} JOIN step_reads r ON r.fact_id=m.id JOIN steps s ON s.id=r.step_id) AS agents, "
    "(SELECT count(DISTINCT df.decision_id) FROM m {X} JOIN decision_facts df ON df.fact_id=m.id) AS decisions, "
    "(SELECT count(DISTINCT hi.handoff_id) FROM m {X} JOIN handoff_items hi ON hi.item_id=m.id AND hi.kind='fact') AS handoffs, "
    "(SELECT json_group_array(id) FROM (SELECT f.id AS id FROM m JOIN facts f ON f.id=m.id ORDER BY f.valid_from LIMIT 5)) AS earliest, "
    "(SELECT json_group_array(id) FROM m WHERE id IN (SELECT value FROM json_each(:probes))) AS present"
)  # {X} is CROSS (the join-order hint of BEAT_SQL §2.2) for the tuned arm and empty for the untuned one
DAG_SQL = (
    "WITH RECURSIVE down(id) AS (SELECT task_id FROM deps WHERE dep_id=:r UNION "
    "SELECT d.task_id FROM deps d JOIN down ON d.dep_id=down.id), m AS MATERIALIZED (SELECT id FROM down) "
    "SELECT (SELECT count(*) FROM m), (SELECT json_group_array(id) FROM (SELECT id FROM m ORDER BY id LIMIT 5)), "
    "(SELECT json_group_array(id) FROM m WHERE id IN (SELECT value FROM json_each(:probes)))"
)
DAG_UNION_ALL_SQL = (  # the trap: UNION ALL enumerates paths (BEAT_SQL §2.1), bounded by depth so that it terminates
    "WITH RECURSIVE down(id, n) AS (SELECT task_id, 1 FROM deps WHERE dep_id=:r UNION ALL "
    "SELECT d.task_id, down.n+1 FROM deps d JOIN down ON d.dep_id=down.id WHERE down.n < :cap) "
    "SELECT count(DISTINCT id), '[]', '[]' FROM down"
)


class SqlArm:
    """B1h over a SQLite file built by ``stores.build_sqlite``. ``tuned`` selects the CROSS JOIN hint (and the file
    must have been built with ``tuned`` indexes/ANALYZE for the full tuning)."""

    def __init__(self, path: str, *, tuned: bool = True):
        self.tuned = tuned
        self.conn = sqlite3.connect(
            f"file:{Path(path).as_posix()}?mode=ro", uri=True, check_same_thread=False
        )
        self._deadline = 0.0
        self.conn.set_progress_handler(self._check, 20000)

    def _check(self) -> int:
        return 1 if time.perf_counter() > self._deadline else 0

    def close(self) -> None:
        self.conn.close()

    def _exec(self, sql: str, params: dict[str, Any]) -> list[tuple[Any, ...]]:
        self._deadline = time.perf_counter() + TIMEOUT_MS / 1000
        try:
            return self.conn.execute(sql, params).fetchall()
        except sqlite3.OperationalError as exc:
            if "interrupted" in str(exc):
                raise Timeout from None
            raise

    def blast(self, q: QuestionA) -> tuple[dict[str, Any], dict[str, Any]]:
        t0 = time.perf_counter()
        sql = BLAST_SQL.replace("{X}", "CROSS" if self.tuned else "")
        try:
            r = self._exec(sql, {"s": q.source, "probes": json.dumps(q.probes)})[0]
        except Timeout:
            return {}, meta(t0, 0, 1, "timeout")
        ans = shape(r[0], r[1], r[2], r[3], q.probes, set(json.loads(r[5])), json.loads(r[4]))
        return ans, meta(t0, 0, 1)

    def dag(self, q: QuestionDag, *, union_all: bool = False) -> tuple[dict[str, Any], dict[str, Any]]:
        t0 = time.perf_counter()
        try:
            if union_all:
                r = self._exec(DAG_UNION_ALL_SQL, {"r": q.root, "cap": q.layers + 1})[0]
                present: set[str] = set()
                first5: list[str] = []
            else:
                r = self._exec(DAG_SQL, {"r": q.root, "probes": json.dumps(q.probes)})[0]
                present, first5 = set(json.loads(r[2])), json.loads(r[1])
        except Timeout:
            return {}, meta(t0, 0, 1, "timeout")
        return {"tasks": r[0], "probes": [p in present for p in q.probes], "first5": first5}, meta(t0, 0, 1)

    def explain(self, q: QuestionA) -> str:
        sql = "EXPLAIN QUERY PLAN " + BLAST_SQL.replace("{X}", "CROSS" if self.tuned else "")
        rows = self.conn.execute(sql, {"s": q.source, "probes": json.dumps(q.probes)}).fetchall()
        return "\n".join(f"{r[0]}|{r[1]}|{r[3]}" for r in rows)


# ------------------------------------------------------------------------------------------------ Cypher
class CypherArm:
    """Shared plumbing: a falkordb Graph handle, a 5 s timeout per statement and the summed server time."""

    def __init__(self, graph: Any):
        self.g = graph
        self.server_ms = 0.0
        self.statements = 0

    def ro(self, cypher: str, params: dict[str, Any] | None = None) -> list[list[Any]]:
        try:
            res = self.g.ro_query(cypher, params or {}, timeout=TIMEOUT_MS)
        except Exception as exc:  # noqa: BLE001 - the server message decides
            if "timed out" in str(exc).lower() or "timeout" in str(exc).lower():
                raise Timeout from None
            raise
        self.statements += 1
        self.server_ms += float(res.run_time_ms or 0.0)
        return res.result_set

    def reset(self) -> None:
        self.server_ms, self.statements = 0.0, 0


class NaiveArm(CypherArm):
    """P-naive: the natural variable-length patterns, one statement per component, ``*1..12`` / ``*1..L+1``."""

    def blast(self, q: QuestionA) -> tuple[dict[str, Any], dict[str, Any]]:
        self.reset()
        t0 = time.perf_counter()
        p = {"s": q.source}
        pat = "MATCH (:Source {id: $s})<-[:DERIVED_FROM*1..12]-(f:Fact) "
        try:
            facts = self.ro(pat + "RETURN count(DISTINCT f)", p)[0][0]
            agents = self.ro(pat + "MATCH (st:Step)-[:READ]->(f) RETURN count(DISTINCT st.agent_id)", p)[0][0]
            decisions = self.ro(pat + "MATCH (d:Decision)-[:BASED_ON]->(f) RETURN count(DISTINCT d)", p)[0][0]
            handoffs = self.ro(pat + "MATCH (h:Handoff)-[:CARRIES]->(f) RETURN count(DISTINCT h)", p)[0][0]
            present = {
                r[0]
                for r in self.ro(
                    pat + "WHERE f.id IN $probes RETURN DISTINCT f.id", {**p, "probes": q.probes}
                )
            }
            earliest = [
                r[0]
                for r in self.ro(
                    pat + "RETURN DISTINCT f.id AS id, f.valid_from AS at ORDER BY at LIMIT 5", p
                )
            ]
        except Timeout:
            return {}, meta(t0, self.server_ms, self.statements, "timeout")
        return shape(facts, agents, decisions, handoffs, q.probes, present, earliest), meta(
            t0, self.server_ms, self.statements
        )

    def dag(self, q: QuestionDag) -> tuple[dict[str, Any], dict[str, Any]]:
        self.reset()
        t0 = time.perf_counter()
        n = q.layers + 1
        pat = f"MATCH (t:Task)-[:DEPENDS_ON*1..{n}]->(:Task {{id: $r}}) "  # n is an int computed here, never user input
        try:
            ids = [r[0] for r in self.ro(pat + "RETURN DISTINCT t.id AS id ORDER BY id", {"r": q.root})]
        except Timeout:
            return {}, meta(t0, self.server_ms, self.statements, "timeout")
        s = set(ids)
        return {"tasks": len(ids), "probes": [p in s for p in q.probes], "first5": ids[:5]}, meta(
            t0, self.server_ms, self.statements
        )


class AnchoredArm(NaiveArm):
    """P-anchored (added by amendment 1 of the pre-registration): the two-MATCH form BEAT_SQL §2.2 found fast on trees,
    ``MATCH (s:Source {id}) MATCH (s)<-[:DERIVED_FROM*1..12]-(f:Fact) WITH DISTINCT f ...``: anchored on the source, but
    still a variable-length pattern, so it enumerates paths on diamonds."""

    def blast(self, q: QuestionA) -> tuple[dict[str, Any], dict[str, Any]]:
        self.reset()
        t0 = time.perf_counter()
        p = {"s": q.source}
        pat = "MATCH (s:Source {id: $s}) MATCH (s)<-[:DERIVED_FROM*1..12]-(f:Fact) WITH DISTINCT f "
        try:
            facts = self.ro(pat + "RETURN count(f)", p)[0][0]
            agents = self.ro(pat + "MATCH (st:Step)-[:READ]->(f) RETURN count(DISTINCT st.agent_id)", p)[0][0]
            decisions = self.ro(pat + "MATCH (d:Decision)-[:BASED_ON]->(f) RETURN count(DISTINCT d)", p)[0][0]
            handoffs = self.ro(pat + "MATCH (h:Handoff)-[:CARRIES]->(f) RETURN count(DISTINCT h)", p)[0][0]
            present = {
                r[0] for r in self.ro(pat + "WHERE f.id IN $probes RETURN f.id", {**p, "probes": q.probes})
            }
            earliest = [
                r[0] for r in self.ro(pat + "RETURN f.id AS id, f.valid_from AS at ORDER BY at LIMIT 5", p)
            ]
        except Timeout:
            return {}, meta(t0, self.server_ms, self.statements, "timeout")
        return shape(facts, agents, decisions, handoffs, q.probes, present, earliest), meta(
            t0, self.server_ms, self.statements
        )


class TunedArm(CypherArm):
    """P-tuned: level-wise expansion over DISTINCT nodes, anchored on ids (the `staleness/mark_changed` / `dependents_of`
    shape); the facts found are then joined to steps, decisions and handoffs in id-batches. No product code."""

    LEVEL1 = (
        "MATCH (:Source {id: $s})<-[:DERIVED_FROM]-(x:Fact) RETURN DISTINCT x.id AS id, x.valid_from AS at"
    )
    # `WHERE p.id IN $list` plans as a Node By Index Scan (0.2 ms); the `UNWIND $list AS x MATCH (:Fact {id: x})` form plans as
    # Unwind -> Conditional Traverse from every Fact -> Filter (an O(N) scan per row: 756 ms for 5 ids on 51k facts, measured).
    LEVEL = "MATCH (p:Fact) WHERE p.id IN $frontier MATCH (p)<-[:DERIVED_FROM]-(x:Fact) RETURN DISTINCT x.id AS id, x.valid_from AS at"
    AGENTS = "MATCH (f:Fact) WHERE f.id IN $ids MATCH (f)<-[:READ]-(st:Step) RETURN DISTINCT st.agent_id AS a"
    DECISIONS = (
        "MATCH (f:Fact) WHERE f.id IN $ids MATCH (d:Decision)-[:BASED_ON]->(f) RETURN DISTINCT d.id AS d"
    )
    HANDOFFS = "MATCH (f:Fact) WHERE f.id IN $ids MATCH (h:Handoff)-[:CARRIES]->(f) RETURN DISTINCT h.id AS h"
    TASKS = (
        "MATCH (p:Task) WHERE p.id IN $frontier MATCH (p)<-[:DEPENDS_ON]-(x:Task) RETURN DISTINCT x.id AS id"
    )
    CHUNK = 2000

    def _closure(
        self, first: str, params: dict[str, Any], level: str, max_levels: int = 40
    ) -> dict[str, int]:
        seen: dict[str, int] = {}
        rows = self.ro(first, params)
        frontier = []
        for i, at in rows:
            seen[i] = at
            frontier.append(i)
        for _ in range(max_levels):
            if not frontier:
                break
            nxt = []
            for k in range(0, len(frontier), self.CHUNK):
                for i, at in self.ro(level, {"frontier": frontier[k : k + self.CHUNK]}):
                    if i not in seen:
                        seen[i] = at
                        nxt.append(i)
            frontier = nxt
        return seen

    def _batched(self, cypher: str, ids: list[str]) -> set[str]:
        out: set[str] = set()
        for k in range(0, len(ids), self.CHUNK):
            out |= {r[0] for r in self.ro(cypher, {"ids": ids[k : k + self.CHUNK]})}
        return out

    def blast(self, q: QuestionA) -> tuple[dict[str, Any], dict[str, Any]]:
        self.reset()
        t0 = time.perf_counter()
        try:
            seen = self._closure(self.LEVEL1, {"s": q.source}, self.LEVEL)
            ids = list(seen)
            agents = self._batched(self.AGENTS, ids)
            decisions = self._batched(self.DECISIONS, ids)
            handoffs = self._batched(self.HANDOFFS, ids)
        except Timeout:
            return {}, meta(t0, self.server_ms, self.statements, "timeout")
        earliest = sorted(seen, key=lambda i: seen[i])[:5]
        ans = shape(len(seen), len(agents), len(decisions), len(handoffs), q.probes, set(ids), earliest)
        return ans, meta(t0, self.server_ms, self.statements)

    def dag(self, q: QuestionDag) -> tuple[dict[str, Any], dict[str, Any]]:
        self.reset()
        t0 = time.perf_counter()
        seen: set[str] = set()
        frontier = [q.root]
        try:
            for _ in range(q.layers + 3):
                if not frontier:
                    break
                rows = self.ro(self.TASKS, {"frontier": frontier})
                frontier = sorted({r[0] for r in rows} - seen)
                seen.update(frontier)
        except Timeout:
            return {}, meta(t0, self.server_ms, self.statements, "timeout")
        ids = sorted(seen)
        return {"tasks": len(ids), "probes": [p in seen for p in q.probes], "first5": ids[:5]}, meta(
            t0, self.server_ms, self.statements
        )
