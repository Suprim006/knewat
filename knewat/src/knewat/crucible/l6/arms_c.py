"""L6-C arms: B1h (SQLite recursive CTE), P-tuned (level-wise Cypher), P-product / P-flat (``Engram.recall``).

Every arm answers a :class:`~knewat.crucible.l6.world_c.QuestionC` with ``(answer, meta)``; ``answer = {"top5": [fact ids in
rank order], "fact": top5[0] or None}`` and ``meta`` is ``arms_a.meta(...)`` (``error`` is ``"timeout"`` past the 5,000 ms
budget of any statement). The deterministic arms (B1h, P-tuned) are handed the anchor id and the predicate: the family
measures traversal and ranking, not question parsing. ``P-product`` / ``P-flat`` get the text ``"<anchor name> <predicate>"``.
"""

from __future__ import annotations

import math
import sqlite3
import time
from pathlib import Path
from typing import Any

from knewat.crucible.l6 import arms_a as A
from knewat.crucible.l6.world_c import EPS, QuestionC

# ------------------------------------------------------------------------------------------------ B1h (SQL)
C_SQL = """
WITH RECURSIVE
walk(id, cost, depth) AS (
  SELECT :anchor, 0.0, 0
  UNION ALL
  SELECT r.dst, w.cost + ln((SELECT count(*) FROM facts x WHERE x.entity_id = r.dst)), w.depth + 1
  FROM walk w JOIN relates r ON r.src = w.id
  WHERE w.depth < :depth AND r.dst <> :anchor
  UNION ALL
  SELECT r.src, w.cost + ln((SELECT count(*) FROM facts x WHERE x.entity_id = r.src)), w.depth + 1
  FROM walk w JOIN relates r ON r.dst = w.id
  WHERE w.depth < :depth AND r.src <> :anchor
),
best(id, cost, hops, rn) AS (
  SELECT id, cost, depth, row_number() OVER (PARTITION BY id ORDER BY round(cost, 9), depth)
  FROM walk WHERE depth > 0
)
SELECT f.id
FROM best b JOIN facts f ON f.entity_id = b.id AND f.predicate = :p
WHERE b.rn = 1
ORDER BY round(b.cost, 9), b.hops, b.id, f.id
LIMIT 5
"""


def sql_lines() -> int:
    return sum(1 for ln in C_SQL.splitlines() if ln.strip() and not ln.strip().startswith("--"))


def _answer(top5: list[str], **extra: Any) -> dict[str, Any]:
    return {"top5": top5, "fact": top5[0] if top5 else None, **extra}


class SqlC:
    """B1h: ONE parameterised ``WITH RECURSIVE`` statement per question over a file built by ``build_sqlite_c``.

    The fan of an entered entity is counted inside the statement (a correlated ``count(*)`` over ``facts(entity_id)``, the
    index the tuned file has), the same work the Cypher arm does when it counts ``ABOUT`` edges live; the stored
    ``entities.fan`` column is not read (this per-entity count is what a latency-tuning SQL author writes; chosen before
    the registered run)."""

    def __init__(self, path: str):
        self.conn = sqlite3.connect(
            f"file:{Path(path).as_posix()}?mode=ro", uri=True, check_same_thread=False
        )
        self._deadline = 0.0
        self.conn.set_progress_handler(self._check, 20000)

    def _check(self) -> int:
        return 1 if time.perf_counter() > self._deadline else 0

    def close(self) -> None:
        self.conn.close()

    def answer(self, q: QuestionC) -> tuple[dict[str, Any], dict[str, Any]]:
        t0 = time.perf_counter()
        self._deadline = t0 + A.TIMEOUT_MS / 1000
        try:
            rows = self.conn.execute(
                C_SQL, {"anchor": q.anchor_id, "p": q.predicate, "depth": q.depth}
            ).fetchall()
        except sqlite3.OperationalError as exc:
            if "interrupted" in str(exc):
                return _answer([]), A.meta(t0, 0, 1, "timeout")
            raise
        return _answer([r[0] for r in rows]), A.meta(t0, 0, 1)

    def explain(self, q: QuestionC) -> str:
        rows = self.conn.execute(
            "EXPLAIN QUERY PLAN " + C_SQL, {"anchor": q.anchor_id, "p": q.predicate, "depth": q.depth}
        ).fetchall()
        return "\n".join(f"{r[0]}|{r[1]}|{r[3]}" for r in rows)


# ------------------------------------------------------------------------------------------------ P-tuned (Cypher)
# `UNWIND $frontier AS fid MATCH (e:Entity {id: fid}) WITH e MATCH (e)-[:RELATES]->(n)` binds the frontier by an index seek first
# (one MATCH with the traversal would scan every RELATES edge); one pattern comprehension counts the entered entity's facts.
HOP_CYPHER = """
UNWIND $frontier AS fid
MATCH (e:Entity {id: fid})
WITH e
MATCH (e)-[:RELATES]->(n:Entity)
WITH e, n, size([(n)<-[:ABOUT]-(:Fact {status: 'active'}) | 1]) AS fan
RETURN e.id AS from_id, n.id AS to_id, fan
UNION
UNWIND $frontier AS fid
MATCH (e:Entity {id: fid})
WITH e
MATCH (e)<-[:RELATES]-(n:Entity)
WITH e, n, size([(n)<-[:ABOUT]-(:Fact {status: 'active'}) | 1]) AS fan
RETURN e.id AS from_id, n.id AS to_id, fan
"""
FACTS_CYPHER = """
UNWIND $entity_ids AS eid
MATCH (e:Entity {id: eid})
WITH e
MATCH (e)<-[:ABOUT]-(f:Fact {predicate: $p, status: 'active'})
RETURN e.id AS entity_id, f.id AS fact_id
"""


def cypher_lines() -> int:
    return sum(
        1
        for s in (HOP_CYPHER, FACTS_CYPHER)
        for ln in s.splitlines()
        if ln.strip() and not ln.strip().startswith("//")
    )


class TunedC(A.CypherArm):
    """P-tuned: one statement per hop over the distinct frontier (min cost per entity kept here), one for the facts.

    ``best[e] = (cost, hops)``; the frontier of the next hop is the set of entities whose best cost improved at this hop, so
    an entity reached more cheaply by a longer walk (within the depth bound) is expanded again."""

    CHUNK = 2000

    def answer(self, q: QuestionC) -> tuple[dict[str, Any], dict[str, Any]]:
        self.reset()
        t0 = time.perf_counter()
        best: dict[str, tuple[float, int]] = {q.anchor_id: (0.0, 0)}
        frontier = [q.anchor_id]
        try:
            for hop in range(1, q.depth + 1):
                if not frontier:
                    break
                cand: dict[str, float] = {}
                for k in range(0, len(frontier), self.CHUNK):
                    for from_id, to_id, fan in self.ro(
                        HOP_CYPHER, {"frontier": frontier[k : k + self.CHUNK]}
                    ):
                        if to_id == q.anchor_id or fan < 1:
                            continue
                        c = best[from_id][0] + math.log(fan)
                        if to_id not in cand or c < cand[to_id]:
                            cand[to_id] = c
                frontier = []
                for e, c in sorted(cand.items()):
                    if e not in best or c < best[e][0] - EPS:
                        best[e] = (c, hop)
                        frontier.append(e)
            ids = sorted(e for e in best if e != q.anchor_id)
            found: list[tuple[float, int, str, str]] = []
            for k in range(0, len(ids), self.CHUNK):
                for eid, fid in self.ro(
                    FACTS_CYPHER, {"entity_ids": ids[k : k + self.CHUNK], "p": q.predicate}
                ):
                    found.append((best[eid][0], best[eid][1], eid, fid))
        except A.Timeout:
            return _answer([]), A.meta(t0, self.server_ms, self.statements, "timeout")
        found.sort(key=lambda t: (round(t[0], 9), t[1], t[2], t[3]))
        return _answer([t[3] for t in found[:5]]), A.meta(t0, self.server_ms, self.statements)

    def profile_hop(self, frontier: list[str]) -> Any:
        return self.g.profile(HOP_CYPHER, {"frontier": frontier})


# ------------------------------------------------------------------------------------------------ P-product / P-flat
class RecordingClient:
    """A GraphClient look-alike that counts statements and sums the server's ``run_time_ms`` of ``ro`` / ``rw``."""

    def __init__(self, client: Any):
        self._c = client
        self.statements = 0
        self.server_ms = 0.0

    def __getattr__(self, name: str) -> Any:
        return getattr(self._c, name)

    def _rec(self, rows: Any) -> Any:
        self.statements += 1
        self.server_ms += float(getattr(rows, "run_time_ms", 0.0) or 0.0)
        return rows

    def ro(self, *a: Any, **k: Any) -> Any:
        return self._rec(self._c.ro(*a, **k))

    def rw(self, *a: Any, **k: Any) -> Any:
        return self._rec(self._c.rw(*a, **k))


class ProductC:
    """``Engram.recall("<anchor name> <predicate>", scope, k=5, hops=min(depth, 2))`` as shipped.

    ``engram.client`` must be a :class:`RecordingClient`. ``hops=0`` is ``P-flat``. ``top5`` is the first five rows of the
    result (hop facts are ranked behind every direct hit, so with five direct hits they never reach it); ``all`` lists every
    returned fact id so that a hit anywhere in the result can be reported too. ``not_answerable`` marks depth > MAX_HOPS."""

    def __init__(self, engram: Any, scope_id: str, hops: int | None):
        self.engram, self.scope_id, self.hops = engram, scope_id, hops

    def answer(self, q: QuestionC) -> tuple[dict[str, Any], dict[str, Any]]:
        from knewat.engram.relations import MAX_HOPS

        rec = self.engram.client
        rec.statements, rec.server_ms = 0, 0.0
        hops = min(q.depth, MAX_HOPS) if self.hops is None else self.hops
        t0 = time.perf_counter()
        try:
            rows = self.engram.recall(q.text, self.scope_id, k=5, hops=hops)
        except Exception as exc:  # noqa: BLE001 - recorded, the question counts as wrong
            m = A.meta(t0, rec.server_ms, rec.statements, f"{type(exc).__name__}: {exc}"[:120])
            return _answer([], all=[]), m
        ids = [r["fact_id"] for r in rows]
        m = A.meta(t0, rec.server_ms, rec.statements)
        m["not_answerable"] = bool(self.hops is None and q.depth > MAX_HOPS)
        return _answer(ids[:5], all=ids), m


# ------------------------------------------------------------------------------------------------ scoring
def score(q: QuestionC, answer: dict[str, Any]) -> dict[str, bool]:
    top5 = answer.get("top5", [])
    return {
        "strict": bool(top5) and top5[0] == q.answer_fact_id,
        "hit5": q.answer_fact_id in top5,
        "top5_equal": top5 == q.expected_top5,
        "hit_any": q.answer_fact_id in answer.get("all", top5),
    }
