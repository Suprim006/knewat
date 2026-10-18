"""B1h: the B1 SQLite store plus the one table a hand-written SQL answerer needs that B1 never kept: the claim history.

B1 keeps only a task's final claimer (``tasks.claimed_by``), so "which tasks were reclaimed after a lease expired, and from
whom" is not answerable from its tables, while Plexus keeps a ``CLAIMED {reclaimed_from}`` edge per claim. A competent SQL
design would keep the same fact in a table, written in the SAME ``BEGIN IMMEDIATE`` transaction as the claim, so that is all
this subclass adds. Nothing else differs from :class:`SqliteBackend` (same schema, same indexes, same transactions); the L2
context builders read a fixed table list (``contexts.B1_TABLES``), so the B1 baseline's artifacts are unchanged.
"""

from __future__ import annotations

import sqlite3
from typing import Any

from plexus.crucible.api import UnknownReference
from plexus.crucible.backends.base import check_lease, claim_result
from plexus.crucible.backends.sqlite import SqliteBackend
from plexus.crucible.util import now_ms

CLAIMS_SCHEMA = """
CREATE TABLE IF NOT EXISTS claims(
  seq INTEGER PRIMARY KEY AUTOINCREMENT, task_id TEXT NOT NULL, agent_id TEXT NOT NULL,
  reclaimed_from TEXT NOT NULL DEFAULT '', at INTEGER NOT NULL, lease_until INTEGER NOT NULL);
CREATE INDEX IF NOT EXISTS claims_task ON claims(task_id);
"""


class SqliteHistoryBackend(SqliteBackend):
    name = "B1"  # same directory layout as B1; the arm label used in results is "B1h"
    label = "SQLite (hand-written SQL)"

    def _init_schema(self, c: sqlite3.Connection) -> None:
        super()._init_schema(c)
        c.executescript(CLAIMS_SCHEMA)

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
            c.execute(
                "INSERT INTO claims(task_id, agent_id, reclaimed_from, at, lease_until) VALUES(?,?,?,?,?)",
                (row["id"], agent_id, row["claimed_by"] or "", t, t + lease_ms),
            )
            return claim_result(row, row["version"] + 1, t + lease_ms, row["claimed_by"])
