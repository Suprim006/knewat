"""Family J: per-arm adapters. Every arm performs the same logical operation per call.

* ``F-mcp``      ``PlexusBackend(mode="mcp")``: every call goes through ``Runtime._run`` (Step + READ/WROTE + ToolCall).
                 Tools the Crucible backend lacks (start_session, verify_artifact, why, impact, remember_episode into a
                 given session) run the product's own MCP work functions (``plexus.mcp.tools_*``) through the same
                 ``_call`` path, so they are audited like the rest.
* ``F-service``  ``PlexusBackend(mode="service")``: the same services, no per-call ToolCall audit.
* ``S-file``     the B1 SQLite store, one file per tenant. Additions (see ``J_SCHEMA``): ``sessions`` (start_session) and
                 ``artifact_verifications`` (verify_artifact), written inside ``BEGIN IMMEDIATE`` like every B1 write.
                 ``why`` = B1 ``why``; ``impact`` = one recursive CTE (the J-trav mix only builds the extra
                 ``step_reads(fact_id)`` index it needs).

Adapter surface: start_session, remember_episode, add_source, assert_fact -> id, recall -> [ids], create_tasks, claim ->
dict | None, complete -> [artifact ids], handoff, record_decision -> id, verify_artifact, why, impact, store_stats, drop,
close.
"""

from __future__ import annotations

import shutil
import sqlite3
from pathlib import Path
from typing import Any

from plexus.crucible.api import UnknownReference
from plexus.crucible.backends.sqlite import SqliteBackend
from plexus.crucible.util import new_id, now_ms

ARMS = ("F-mcp", "F-service", "S-file")


# ------------------------------------------------------------------------------------------------ F
class FAdapter:
    def __init__(self, tenant: str, host: str, port: int, mode: str, client: Any = None):
        from plexus.crucible.backends.plexus import PlexusBackend

        self.tenant, self.mode = tenant, mode
        self.b = PlexusBackend(tenant, host=host, port=port, embedder="hash", mode=mode, client=client)

    # ``_call`` is the backend's own plumbing for both modes (mcp -> Runtime._run; service -> same services w/o audit)
    def _tool(self, tool: str, agent: str, fn) -> dict[str, Any]:
        return self.b._call(tool, agent, fn)

    def start_session(self, agent: str, role: str = "") -> str:
        from plexus.mcp import tools_engram

        d = self._tool(
            "start_session",
            agent,
            lambda ts, m: tools_engram.start_session(
                ts, m, agent_id=agent, agent_role=role, harness="crucible", step=None
            ),
        )
        return d["session_id"]

    def remember_episode(self, agent: str, session_id: str, text: str) -> str:
        from plexus.mcp.runtime import Outcome

        def work(ts, m):
            eid = ts.engram(m).remember_episode(session_id, "note", text, None)
            return Outcome({"episode_id": eid}, created=[("Episode", eid)], updated=[("Session", session_id)])

        return self._tool("remember_episode", agent, work)["episode_id"]

    def add_source(self, uri: str) -> str:
        return self.b.add_source(uri)

    def assert_fact(self, agent, subject, predicate, value, source_id, derived_from) -> str:
        return self.b.assert_fact(
            agent, subject, predicate, value, "global", source_id=source_id, derived_from=derived_from
        )["fact_id"]

    def recall(self, agent: str, query: str) -> list[str]:
        return [h["fact_id"] for h in self.b.recall(agent, query, "global", 8)]

    def create_tasks(self, tasks) -> list[str]:
        return self.b.create_tasks(tasks)

    def claim(self, agent: str):
        return self.b.claim_next_task(agent)

    def complete(self, agent, task_id, version, artifacts) -> list[str]:
        return list(self.b.complete_task(agent, task_id, version, artifacts)["artifact_ids"])

    def handoff(self, agent, to_agent, task_id, note, artifact_ids, fact_ids) -> str:
        return self.b.handoff(agent, to_agent, task_id, note, artifact_ids, fact_ids)

    def record_decision(self, agent, task_id, text, fact_ids) -> str:
        return self.b.record_decision(agent, task_id, text, fact_ids)

    def verify_artifact(self, agent: str, artifact_id: str) -> None:
        from plexus.mcp import tools_relay

        self._tool(
            "verify_artifact",
            agent,
            lambda ts, m: tools_relay.verify_artifact(
                ts, m, agent_id=agent, artifact_id=artifact_id, step=None
            ),
        )

    def why(self, agent: str, node_id: str) -> None:
        from plexus.mcp import lineage_tools

        self._tool(
            "why",
            agent,
            lambda ts, m: lineage_tools.why(ts, m, agent_id=agent, node_id=node_id, step=None),
        )

    def impact(self, agent: str, kind: str, node_id: str) -> None:
        from plexus.mcp import tools_impact

        self._tool(
            "impact",
            agent,
            lambda ts, m: tools_impact.impact(ts, m, agent_id=agent, kind=kind, id=node_id, step=None),
        )

    # -- cell bookkeeping ------------------------------------------------------------------------------------
    def store_stats(self) -> dict[str, Any]:
        g = self.b.client.graph(self.b.graph)
        n = g.ro_query("MATCH (n) RETURN count(n)").result_set[0][0]
        e = g.ro_query("MATCH ()-[r]->() RETURN count(r)").result_set[0][0]
        out: dict[str, Any] = {"nodes": int(n), "edges": int(e)}
        try:
            mem = self.b.client.db.connection.execute_command("GRAPH.MEMORY", "USAGE", self.b.graph)
            kv = {
                (k.decode() if isinstance(k, bytes) else k): v
                for k, v in zip(mem[::2], mem[1::2], strict=False)
            }
            out["graph_memory_mb"] = float(kv.get("total_graph_sz_mb", 0))
        except Exception:
            pass
        return out

    def drop(self) -> None:
        self.b.drop()

    def close(self) -> None:
        self.b.close()


# ------------------------------------------------------------------------------------------------ S
J_SCHEMA = """
CREATE TABLE IF NOT EXISTS sessions(
  id TEXT PRIMARY KEY, agent_id TEXT NOT NULL, role TEXT NOT NULL, harness TEXT NOT NULL, started_at INTEGER NOT NULL);
CREATE TABLE IF NOT EXISTS artifact_verifications(
  artifact_id TEXT NOT NULL, agent_id TEXT NOT NULL, independent INTEGER NOT NULL, at INTEGER NOT NULL,
  PRIMARY KEY(artifact_id, agent_id));
"""
TRAV_INDEX = "CREATE INDEX IF NOT EXISTS step_reads_fact ON step_reads(fact_id)"

IMPACT_SQL = """
WITH RECURSIVE reach(id, depth) AS (
  {base}
  UNION SELECT l.src, r.depth + 1 FROM fact_links l JOIN reach r ON l.dst = r.id
  WHERE l.kind = 'derived_from' AND r.depth < 8)
SELECT
  (SELECT count(DISTINCT id) FROM reach) AS facts,
  (SELECT count(DISTINCT s.agent_id) FROM step_reads sr JOIN steps s ON s.id = sr.step_id
     WHERE sr.fact_id IN (SELECT id FROM reach)) AS agents,
  (SELECT count(DISTINCT df.decision_id) FROM decision_facts df WHERE df.fact_id IN (SELECT id FROM reach)) AS decisions,
  (SELECT count(DISTINCT d.task_id) FROM decision_facts df JOIN decisions d ON d.id = df.decision_id
     WHERE df.fact_id IN (SELECT id FROM reach)) AS tasks,
  (SELECT count(DISTINCT hi.handoff_id) FROM handoff_items hi
     WHERE hi.kind = 'fact' AND hi.item_id IN (SELECT id FROM reach)) AS handoffs
"""
BASE_FACT = "SELECT ?, 0"
BASE_SOURCE = "SELECT src, 1 FROM fact_links WHERE dst = ? AND kind = 'derived_from'"


class JSqlite(SqliteBackend):
    """B1 plus the two J tables (and, for J-trav, the index the impact CTE needs)."""

    trav_index = False

    def _init_schema(self, c: sqlite3.Connection) -> None:
        super()._init_schema(c)
        c.executescript(J_SCHEMA)
        if self.trav_index:
            c.execute(TRAV_INDEX)


class SAdapter:
    def __init__(self, tenant: str, root: str, trav_index: bool = False):
        self.tenant = tenant
        cls = type("JSqliteT", (JSqlite,), {"trav_index": trav_index})
        self.b = cls(tenant, root)

    def start_session(self, agent: str, role: str = "") -> str:
        sid, t = new_id(), now_ms()
        with self.b._tx() as c:
            self.b._ensure_agent(c, agent)
            if role:
                c.execute("UPDATE agents SET role=? WHERE id=?", (role, agent))
            c.execute(
                "INSERT INTO sessions(id, agent_id, role, harness, started_at) VALUES(?,?,?,?,?)",
                (sid, agent, role, "crucible", t),
            )
        return sid

    def remember_episode(self, agent: str, session_id: str, text: str) -> str:
        return self.b.remember_episode(agent, text)  # B1 episodes have no session column: see notes-j.md

    def add_source(self, uri: str) -> str:
        return self.b.add_source(uri)

    def assert_fact(self, agent, subject, predicate, value, source_id, derived_from) -> str:
        return self.b.assert_fact(
            agent, subject, predicate, value, "global", source_id=source_id, derived_from=derived_from
        )["fact_id"]

    def recall(self, agent: str, query: str) -> list[str]:
        return [h["fact_id"] for h in self.b.recall(agent, query, "global", 8)]

    def create_tasks(self, tasks) -> list[str]:
        return self.b.create_tasks(tasks)

    def claim(self, agent: str):
        return self.b.claim_next_task(agent)

    def complete(self, agent, task_id, version, artifacts) -> list[str]:
        return list(self.b.complete_task(agent, task_id, version, artifacts)["artifact_ids"])

    def handoff(self, agent, to_agent, task_id, note, artifact_ids, fact_ids) -> str:
        return self.b.handoff(agent, to_agent, task_id, note, artifact_ids, fact_ids)

    def record_decision(self, agent, task_id, text, fact_ids) -> str:
        return self.b.record_decision(agent, task_id, text, fact_ids)

    def verify_artifact(self, agent: str, artifact_id: str) -> None:
        t = now_ms()
        with self.b._tx() as c:
            row = c.execute("SELECT agent_id FROM artifacts WHERE id=?", (artifact_id,)).fetchone()
            if row is None:
                raise UnknownReference(f"unknown artifact id: {artifact_id}")
            c.execute(
                "INSERT INTO artifact_verifications(artifact_id, agent_id, independent, at) VALUES(?,?,?,?) "
                "ON CONFLICT(artifact_id, agent_id) DO UPDATE SET at=excluded.at",
                (artifact_id, agent, int(row["agent_id"] != agent), t),
            )

    def why(self, agent: str, node_id: str) -> None:
        self.b.why(node_id)

    def impact(self, agent: str, kind: str, node_id: str) -> None:
        base = BASE_SOURCE if kind == "source" else BASE_FACT
        with self.b._conn() as c:
            c.execute(IMPACT_SQL.format(base=base), (node_id,)).fetchone()

    # -- cell bookkeeping ------------------------------------------------------------------------------------
    def store_stats(self) -> dict[str, Any]:
        d = Path(self.b.dir)
        size = sum(f.stat().st_size for f in d.iterdir() if f.is_file())
        with self.b._conn() as c:
            rows = {
                t: c.execute(f"SELECT count(*) FROM {t}").fetchone()[0]
                for t in ("facts", "tasks", "episodes", "steps")
            }
        return {"file_bytes": size, **{f"rows_{k}": v for k, v in rows.items()}}

    def drop(self) -> None:
        self.b.close()
        shutil.rmtree(Path(self.b.dir), ignore_errors=True)

    def close(self) -> None:
        self.b.close()


def make_adapter(
    arm: str, tenant: str, host: str, port: int, root: str, client: Any = None, trav_index: bool = False
):
    if arm == "F-mcp":
        return FAdapter(tenant, host, port, "mcp", client)
    if arm == "F-service":
        return FAdapter(tenant, host, port, "service", client)
    if arm == "S-file":
        return SAdapter(tenant, root, trav_index)
    raise ValueError(f"unknown arm {arm}")
