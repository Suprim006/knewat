"""Deterministic arms for family B (why-chain depth): B1h (path CTE), P-naive, P-tuned and the product ``why`` (P / P-pre).

Question: decision -> its one fact -> ... -> the fact derived directly from source R. Answer ``{"chain": [...], "agent": id}``.
"""

from __future__ import annotations

import sqlite3
import time
from pathlib import Path
from typing import Any

from knewat.crucible.l6.arms_a import TIMEOUT_MS, CypherArm, Timeout, meta
from knewat.crucible.l6.world import QuestionB

PATH_SQL = (
    "WITH RECURSIVE p(id, path, depth) AS ("
    " SELECT df.fact_id, df.fact_id, 0 FROM decision_facts df WHERE df.decision_id=:d"
    " UNION ALL SELECT l.dst, p.path || ',' || l.dst, p.depth + 1 FROM p JOIN fact_links l ON l.src = p.id"
    " AND l.kind = 'derived_from' WHERE p.depth < :cap) "
    "SELECT path FROM p WHERE id = :root"
)


class SqlB:
    def __init__(self, path: str):
        self.conn = sqlite3.connect(
            f"file:{Path(path).as_posix()}?mode=ro", uri=True, check_same_thread=False
        )
        self._deadline = 0.0
        self.conn.set_progress_handler(lambda: 1 if time.perf_counter() > self._deadline else 0, 20000)

    def close(self) -> None:
        self.conn.close()

    def answer(self, q: QuestionB) -> tuple[dict[str, Any], dict[str, Any]]:
        t0 = time.perf_counter()
        self._deadline = t0 + TIMEOUT_MS / 1000
        try:
            rows = self.conn.execute(PATH_SQL, {"d": q.decision, "root": q.root, "cap": 20}).fetchall()
            if len(rows) != 1:
                return {}, meta(t0, 0, 1, f"{len(rows)} paths")
            chain = rows[0][0].split(",")[:-1]
            agent = self.conn.execute(
                "SELECT agent_id FROM fact_agents WHERE fact_id=?", (chain[-1],)
            ).fetchone()[0]
        except sqlite3.OperationalError as exc:
            if "interrupted" in str(exc):
                return {}, meta(t0, 0, 1, "timeout")
            raise
        return {"chain": chain, "agent": agent}, meta(t0, 0, 2)


class NaiveB(CypherArm):
    """P-naive: one natural pattern, ``(d)-[:BASED_ON]->(f)-[:DERIVED_FROM*1..12]->(s {id})`` returning the node ids."""

    def answer(self, q: QuestionB) -> tuple[dict[str, Any], dict[str, Any]]:
        self.reset()
        t0 = time.perf_counter()
        try:
            rows = self.ro(
                "MATCH p = (d:Decision {id: $d})-[:BASED_ON]->(f:Fact)-[:DERIVED_FROM*1..12]->(s:Source {id: $r}) "
                "RETURN [n IN nodes(p) | n.id] AS ids",
                {"d": q.decision, "r": q.root},
            )
            if len(rows) != 1:
                return {}, meta(t0, self.server_ms, self.statements, f"{len(rows)} paths")
            chain = rows[0][0][1:-1]
            agent = self.ro("MATCH (:Fact {id: $f})-[:ASSERTED_BY]->(a:Agent) RETURN a.id", {"f": chain[-1]})[
                0
            ][0]
        except Timeout:
            return {}, meta(t0, self.server_ms, self.statements, "timeout")
        return {"chain": chain, "agent": agent}, meta(t0, self.server_ms, self.statements)


class TunedB(CypherArm):
    """P-tuned: forward level-wise expansion with parent pointers (``id IN $frontier`` seeks the id index)."""

    def answer(self, q: QuestionB) -> tuple[dict[str, Any], dict[str, Any]]:
        self.reset()
        t0 = time.perf_counter()
        try:
            f0 = self.ro("MATCH (d:Decision {id: $d})-[:BASED_ON]->(f:Fact) RETURN f.id", {"d": q.decision})[
                0
            ][0]
            parent: dict[str, str] = {}
            frontier = [f0]
            seen = {f0}
            found = False
            for _ in range(40):
                if not frontier or found:
                    break
                rows = self.ro(
                    "MATCH (p:Fact) WHERE p.id IN $frontier MATCH (p)-[:DERIVED_FROM]->(x) RETURN p.id AS p, x.id AS x",
                    {"frontier": frontier},
                )
                nxt = []
                for p, x in rows:
                    if x not in seen:
                        seen.add(x)
                        parent[x] = p
                        nxt.append(x)
                found = q.root in seen
                frontier = nxt
            if not found:
                return {}, meta(t0, self.server_ms, self.statements, "root not reached")
            chain = []
            cur = parent[q.root]
            while True:
                chain.append(cur)
                if cur == f0:
                    break
                cur = parent[cur]
            chain.reverse()
            agent = self.ro("MATCH (:Fact {id: $f})-[:ASSERTED_BY]->(a:Agent) RETURN a.id", {"f": chain[-1]})[
                0
            ][0]
        except Timeout:
            return {}, meta(t0, self.server_ms, self.statements, "timeout")
        return {"chain": chain, "agent": agent}, meta(t0, self.server_ms, self.statements)


def chain_from_why(why: dict[str, Any], decision: str, root: str) -> dict[str, Any]:
    """Rebuild the chain from the product ``why`` result (its ``edges``): DERIVED_FROM adjacency from the decision's
    fact to ``root``; the agent comes from the ASSERTED_BY edge of the last fact. Missing pieces give an empty answer."""
    edges = why.get("edges", [])
    based = [e["to"] for e in edges if e["rel"] == "BASED_ON" and e["from"] == decision]
    adj: dict[str, list[str]] = {}
    for e in edges:
        if e["rel"] == "DERIVED_FROM":
            adj.setdefault(e["from"], []).append(e["to"])
    if not based:
        return {}

    def dfs(node: str, path: list[str]) -> list[str] | None:
        for nxt in adj.get(node, []):
            if nxt == root:
                return path
            r = dfs(nxt, [*path, nxt])
            if r:
                return r
        return None

    chain = dfs(based[0], [based[0]])
    if not chain:
        return {}
    agent = next((e["to"] for e in edges if e["rel"] == "ASSERTED_BY" and e["from"] == chain[-1]), "")
    return {"chain": chain, "agent": agent}


class ProductWhyB:
    """P / P-pre: the product ``Lineage.why`` called as the MCP tool calls it; the chain is rebuilt from its edges."""

    def __init__(self, lineage: Any, **kwargs: Any):
        self.lineage = lineage
        self.kwargs = kwargs

    def answer(self, q: QuestionB) -> tuple[dict[str, Any], dict[str, Any]]:
        t0 = time.perf_counter()
        try:
            why = self.lineage.why(q.decision, **self.kwargs)
        except Exception as exc:  # noqa: BLE001
            return {}, meta(t0, 0, 1, f"{type(exc).__name__}: {exc}"[:120])
        ans = chain_from_why(why, q.decision, q.root)
        return ans, meta(t0, 0, 1, "" if ans else "root not in the why result")
