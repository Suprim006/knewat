"""Deterministic arms for family D (cross-sprint aggregation): hand-written SQL (B1h) and hand-written Cypher (P).

No product tool exists for these aggregates (P8 in BEAT_SQL §5 is not built), so ``P`` here is a Cypher statement over the
same graph, written with the same effort as the SQL. One statement per question (T2 and T4 need none beyond the
aggregate itself).
"""

from __future__ import annotations

import sqlite3
import time
from pathlib import Path
from typing import Any

from knewat.crucible.l6.arms_a import TIMEOUT_MS, CypherArm, Timeout, meta
from knewat.crucible.l6.world import QuestionD

# ------------------------------------------------------------------------------------------------ SQL
_RANGE = "f.scope BETWEEN :lo AND :hi"
SQL = {
    "superseded_decisions": (
        "SELECT count(DISTINCT df.decision_id) FROM decision_facts df JOIN facts f ON f.id=df.fact_id "
        f"WHERE f.status='superseded' AND {_RANGE}"
    ),
    "top_forgetter": (
        "SELECT fa.agent_id, count(*) AS c FROM facts f JOIN fact_agents fa ON fa.fact_id=f.id "
        f"WHERE f.status='forgotten' AND {_RANGE} GROUP BY fa.agent_id ORDER BY c DESC, fa.agent_id LIMIT 1"
    ),
    "shared_sources": (
        "SELECT l.dst FROM decision_facts df JOIN facts f ON f.id=df.fact_id JOIN fact_links l ON l.src=f.id "
        f"AND l.kind='derived_from' WHERE l.dst LIKE 'shared-%' AND {_RANGE} "
        "GROUP BY l.dst HAVING count(DISTINCT f.scope) > :k ORDER BY l.dst"
    ),
    "superseded_handoffs": (
        "SELECT count(DISTINCT hi.handoff_id) FROM handoff_items hi JOIN facts f ON f.id=hi.item_id "
        f"WHERE hi.kind='fact' AND f.status='superseded' AND {_RANGE}"
    ),
    "top_sprints": (
        "SELECT substr(f.scope, 7) AS tag, count(*) AS c FROM facts f "
        f"WHERE f.status='forgotten' AND {_RANGE} GROUP BY f.scope ORDER BY c DESC, tag LIMIT 3"
    ),
    "cross_agent_supersedes": (
        "SELECT count(*) FROM fact_links l JOIN facts o ON o.id=l.dst JOIN fact_agents a ON a.fact_id=l.src "
        "JOIN fact_agents b ON b.fact_id=o.id "
        "WHERE l.kind='supersedes' AND a.agent_id <> b.agent_id AND o.scope BETWEEN :lo AND :hi"
    ),
}


def _scope_bounds(q: QuestionD) -> dict[str, str]:
    return {"lo": f"scope:S{q.lo:03d}", "hi": f"scope:S{q.hi:03d}"}


class SqlD:
    def __init__(self, path: str):
        self.conn = sqlite3.connect(
            f"file:{Path(path).as_posix()}?mode=ro", uri=True, check_same_thread=False
        )
        self._deadline = 0.0
        self.conn.set_progress_handler(lambda: 1 if time.perf_counter() > self._deadline else 0, 20000)

    def close(self) -> None:
        self.conn.close()

    def answer(self, q: QuestionD) -> tuple[Any, dict[str, Any]]:
        t0 = time.perf_counter()
        self._deadline = t0 + TIMEOUT_MS / 1000
        params: dict[str, Any] = _scope_bounds(q)
        if q.template == "shared_sources":
            params["k"] = q.k
        if q.template == "cross_agent_supersedes":
            pass
        try:
            rows = self.conn.execute(SQL[q.template], params).fetchall()
        except sqlite3.OperationalError as exc:
            if "interrupted" in str(exc):
                return None, meta(t0, 0, 1, "timeout")
            raise
        t = q.template
        if t == "top_forgetter":
            return {"agent": rows[0][0], "count": rows[0][1]}, meta(t0, 0, 1)
        if t == "shared_sources":
            return [r[0] for r in rows], meta(t0, 0, 1)
        if t == "top_sprints":
            return [r[0] for r in rows], meta(t0, 0, 1)
        return int(rows[0][0]), meta(t0, 0, 1)


# ------------------------------------------------------------------------------------------------ Cypher
CYPHER = {
    "superseded_decisions": (
        "MATCH (d:Decision)-[:BASED_ON]->(f:Fact {status: 'superseded'})-[:IN_SCOPE]->(s:Scope) "
        "WHERE s.name >= $lo AND s.name <= $hi RETURN count(DISTINCT d)"
    ),
    "top_forgetter": (
        "MATCH (f:Fact {status: 'forgotten'})-[:IN_SCOPE]->(s:Scope) WHERE s.name >= $lo AND s.name <= $hi "
        "MATCH (f)-[:ASSERTED_BY]->(a:Agent) RETURN a.id AS agent, count(f) AS c ORDER BY c DESC, agent LIMIT 1"
    ),
    "shared_sources": (
        "MATCH (d:Decision)-[:BASED_ON]->(f:Fact)-[:DERIVED_FROM]->(src:Source) WHERE src.id STARTS WITH 'shared-' "
        "MATCH (f)-[:IN_SCOPE]->(s:Scope) WHERE s.name >= $lo AND s.name <= $hi "
        "WITH src.id AS id, count(DISTINCT s.name) AS n WHERE n > $k RETURN id ORDER BY id"
    ),
    "superseded_handoffs": (
        "MATCH (h:Handoff)-[:CARRIES]->(f:Fact {status: 'superseded'})-[:IN_SCOPE]->(s:Scope) "
        "WHERE s.name >= $lo AND s.name <= $hi RETURN count(DISTINCT h)"
    ),
    "top_sprints": (
        "MATCH (f:Fact {status: 'forgotten'})-[:IN_SCOPE]->(s:Scope) WHERE s.name >= $lo AND s.name <= $hi "
        "RETURN s.name AS tag, count(f) AS c ORDER BY c DESC, tag LIMIT 3"
    ),
    "cross_agent_supersedes": (
        "MATCH (n:Fact)-[:SUPERSEDES]->(o:Fact) MATCH (n)-[:ASSERTED_BY]->(a:Agent) MATCH (o)-[:ASSERTED_BY]->(b:Agent) "
        "WHERE a.id <> b.id MATCH (o)-[:IN_SCOPE]->(s:Scope) WHERE s.name >= $lo AND s.name <= $hi RETURN count(*)"
    ),
}


class CypherD(CypherArm):
    def answer(self, q: QuestionD) -> tuple[Any, dict[str, Any]]:
        self.reset()
        t0 = time.perf_counter()
        params: dict[str, Any] = {"lo": f"S{q.lo:03d}", "hi": f"S{q.hi:03d}"}
        if q.template == "shared_sources":
            params["k"] = q.k
        try:
            rows = self.ro(CYPHER[q.template], params)
        except Timeout:
            return None, meta(t0, self.server_ms, self.statements, "timeout")
        m = meta(t0, self.server_ms, self.statements)
        t = q.template
        if t == "top_forgetter":
            return {"agent": rows[0][0], "count": rows[0][1]}, m
        if t in ("shared_sources", "top_sprints"):
            return [r[0] for r in rows], m
        return int(rows[0][0]), m
