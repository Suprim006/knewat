"""Arm B1h: every L2 question answered by hand-written SQL against the SQLite store (no LLM, no retrieval).

This is the control the BEAT_SQL analysis asked for: the same 17 question operations as the Cypher answerer
(``knewat_answerer.KnewatAnswerer``), written by the same author with the same effort, but in SQL over the B1 tables
(plus the ``claims`` history table of :class:`~knewat.crucible.backends.sqlite_h.SqliteHistoryBackend`). One read-only
statement per fact the question needs, parameterised, shaped into the same answer format and scored by the same
``score``. The L2 baselines B0/B1/B2 are LLM readers of a dump; this arm is a *query* and so is comparable to P.

Where the SQL differs from the Cypher on purpose: the transitive closure is a ``WITH RECURSIVE ... UNION`` (set
semantics, linear on a DAG), the decision name (first four words, punctuation dropped) is computed in Python over the
rows exactly as the Cypher arm does, and scope visibility is ``scope IN (own, 'global')`` instead of an ``INHERITS``
walk.
"""

from __future__ import annotations

import sqlite3
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

from knewat.crucible.l2.questions import Question
from knewat.crucible.l2.scenario import decision_label
from knewat.crucible.util import normalize, scope_chain

_SEP = "\x1f"


def _label(predicate: str, value: str) -> str:
    return f"{predicate}={' '.join(str(value).split())}"


def _scope(spec: str) -> str:
    kind, _, name = spec.partition(":")
    return spec if name else "global"


def _split(s: str | None) -> list[str]:
    return s.split(_SEP) if s else []


_AGENTS = "(SELECT group_concat(a.agent_id, char(31)) FROM (SELECT agent_id FROM fact_agents WHERE fact_id=f.id ORDER BY at, agent_id) a)"
_SOURCES = (
    "(SELECT group_concat(u.uri, char(31)) FROM (SELECT s.uri FROM fact_links l JOIN sources s ON s.id=l.dst "
    "WHERE l.src=f.id AND l.kind='derived_from' ORDER BY s.uri) u)"
)


class SqlAnswerer:
    def __init__(self, db_path: str | Path):
        self.conn = sqlite3.connect(f"file:{Path(db_path).as_posix()}?mode=ro", uri=True)
        self.conn.row_factory = sqlite3.Row
        self.statements = 0
        self.queries: list[str] = []
        self._ops: dict[str, Callable[..., Any]] = {
            n[4:]: fn for n, fn in vars(SqlAnswerer).items() if n.startswith("_op_")
        }

    def close(self) -> None:
        self.conn.close()

    # -- plumbing ---------------------------------------------------------------------------------------------
    def sql(self, text: str, *params: Any) -> list[sqlite3.Row]:
        self.statements += 1
        self.queries.append(" ".join(text.split())[:80])
        return self.conn.execute(text, params).fetchall()

    def answer(self, q: Question) -> tuple[Any, dict[str, Any]]:
        fn = self._ops.get(q.op)
        if fn is None:
            raise KeyError(f"no SQL answerer for op '{q.op}'")
        self.statements, self.queries = 0, []
        t0 = time.perf_counter()
        out = self._dispatch(q, fn)
        meta = {
            "latency_ms": round((time.perf_counter() - t0) * 1000, 2),
            "server_ms": 0.0,
            "statements": self.statements,
            "queries": list(self.queries),
        }
        return out, meta

    def _dispatch(self, q: Question, fn: Callable[..., Any]) -> Any:
        return fn(self, **q.args)

    @property
    def ops(self) -> list[str]:
        return sorted(self._ops)

    # -- shared reads -------------------------------------------------------------------------------------------
    def _decision_rows(self, decision: str) -> list[sqlite3.Row]:
        rows = self.sql(
            f"SELECT d.text, f.predicate, f.value, f.status, {_AGENTS} AS agents, {_SOURCES} AS sources "
            "FROM decisions d JOIN decision_facts df ON df.decision_id=d.id JOIN facts f ON f.id=df.fact_id "
            "ORDER BY d.at, d.id, f.predicate, f.value"
        )
        return [r for r in rows if decision_label(r["text"]) == decision]

    def _handoff(self, task: str) -> sqlite3.Row:
        rows = self.sql(
            "SELECT h.id, h.from_agent, h.to_agent, h.task_id FROM handoffs h WHERE h.task_id=?", task
        )
        return rows[0]

    def _handoff_facts(self, hid: str) -> list[sqlite3.Row]:
        return self.sql(
            "SELECT f.predicate, f.value FROM handoff_items i JOIN facts f ON f.id=i.item_id "
            "WHERE i.handoff_id=? AND i.kind='fact' ORDER BY f.predicate, f.value",
            hid,
        )

    def _fact(self, label: str) -> sqlite3.Row:
        predicate, _, value = label.partition("=")
        return self.sql(
            f"SELECT f.predicate, f.value, f.status, f.scope, {_AGENTS} AS agents, {_SOURCES} AS sources "
            "FROM facts f WHERE f.predicate=? AND f.value=?",
            predicate,
            value,
        )[0]

    # -- decision provenance ---------------------------------------------------------------------------------------
    def _op_decision_facts(self, decision: str) -> list[str]:
        return [_label(r["predicate"], r["value"]) for r in self._decision_rows(decision)]

    def _op_decision_fact_agents(self, decision: str) -> list[str]:
        return [
            f"{_label(r['predicate'], r['value'])}@{a}"
            for r in self._decision_rows(decision)
            for a in _split(r["agents"])
        ]

    def _op_decision_sources(self, decision: str) -> list[str]:
        return list(dict.fromkeys(s for r in self._decision_rows(decision) for s in _split(r["sources"])))

    # -- handoffs ----------------------------------------------------------------------------------------------------
    def _op_handoff_artifacts(self, task: str) -> list[str]:
        h = self._handoff(task)
        return [
            r["uri"]
            for r in self.sql(
                "SELECT a.uri FROM handoff_items i JOIN artifacts a ON a.id=i.item_id "
                "WHERE i.handoff_id=? AND i.kind='artifact' ORDER BY a.uri",
                h["id"],
            )
        ]

    def _op_handoff_route(self, task: str) -> list[str]:
        h = self._handoff(task)
        return [f"{h['from_agent']}->{h['to_agent']}"]

    def _op_handoff_facts(self, task: str) -> list[str]:
        return [_label(f["predicate"], f["value"]) for f in self._handoff_facts(self._handoff(task)["id"])]

    def _op_handoffs_to(self, agent: str) -> list[str]:
        return [
            r["task_id"] for r in self.sql("SELECT task_id FROM handoffs WHERE to_agent=? ORDER BY at", agent)
        ]

    def _op_handoffs_with_superseded_facts(self) -> list[str]:
        return [
            r["task_id"]
            for r in self.sql(
                "SELECT DISTINCT h.task_id FROM handoffs h JOIN handoff_items i ON i.handoff_id=h.id AND i.kind='fact' "
                "JOIN facts f ON f.id=i.item_id WHERE f.status='superseded' ORDER BY h.task_id"
            )
        ]

    # -- time travel -----------------------------------------------------------------------------------------------------
    def _as_of(self, subject: str, predicate: str, t: int) -> list[sqlite3.Row]:
        return self.sql(
            "SELECT predicate, value FROM facts WHERE entity=? AND predicate=? AND scope='global' "
            "AND status IN ('active','superseded') AND valid_from <= ? AND ? < valid_to ORDER BY valid_from, value",
            normalize(subject),
            predicate,
            t,
            t,
        )

    def _op_as_of_values(self, subject: str, predicate: str, t: int) -> list[str]:
        return [r["value"] for r in self._as_of(subject, predicate, t)]

    def _op_as_of_facts(self, subject: str, predicate: str, t: int) -> list[str]:
        return [_label(r["predicate"], r["value"]) for r in self._as_of(subject, predicate, t)]

    def _op_value_history(self, subject: str, predicate: str) -> list[str]:
        return [
            r["value"]
            for r in self.sql(
                "SELECT value FROM facts WHERE entity=? AND predicate=? AND scope='global' "
                "AND status IN ('active','superseded') ORDER BY valid_from, value",
                normalize(subject),
                predicate,
            )
        ]

    # -- facts -------------------------------------------------------------------------------------------------------------------
    def _decisions_on_status(self, status: str) -> list[str]:
        rows = self.sql(
            "SELECT DISTINCT d.text FROM decisions d JOIN decision_facts df ON df.decision_id=d.id "
            "JOIN facts f ON f.id=df.fact_id WHERE f.status=? ORDER BY d.text",
            status,
        )
        return [decision_label(r["text"]) for r in rows]

    def _op_decisions_on_superseded(self) -> list[str]:
        return self._decisions_on_status("superseded")

    def _op_decisions_on_forgotten(self) -> list[str]:
        return self._decisions_on_status("forgotten")

    def _op_decisions_on_fact(self, fact: str) -> list[str]:
        predicate, _, value = fact.partition("=")
        rows = self.sql(
            "SELECT DISTINCT d.text FROM decisions d JOIN decision_facts df ON df.decision_id=d.id "
            "JOIN facts f ON f.id=df.fact_id WHERE f.predicate=? AND f.value=? ORDER BY d.text",
            predicate,
            value,
        )
        return [decision_label(r["text"]) for r in rows]

    def _op_superseder(self, fact: str) -> list[str]:
        predicate, _, value = fact.partition("=")
        rows = self.sql(
            "SELECT n.predicate, n.value, (SELECT group_concat(a.agent_id, char(31)) FROM fact_agents a WHERE a.fact_id=n.id) AS agents "
            "FROM facts o JOIN fact_links l ON l.dst=o.id AND l.kind='supersedes' JOIN facts n ON n.id=l.src "
            "WHERE o.predicate=? AND o.value=?",
            predicate,
            value,
        )
        return [f"{_label(r['predicate'], r['value'])}@{a}" for r in rows for a in _split(r["agents"])]

    def _op_fact_agent(self, fact: str) -> str:
        return _split(self._fact(fact)["agents"])[0]

    def _op_fact_source(self, fact: str) -> str:
        return _split(self._fact(fact)["sources"])[0]

    def _op_fact_scope(self, fact: str) -> str:
        return str(self._fact(fact)["scope"])

    # -- dependencies --------------------------------------------------------------------------------------------------------------
    def _op_blocked_by_failure(self, task: str) -> list[str]:
        rows = self.sql(
            "WITH RECURSIVE down(id) AS (SELECT task_id FROM deps WHERE dep_id=? "
            "UNION SELECT d.task_id FROM deps d JOIN down ON d.dep_id=down.id) "
            "SELECT id FROM down ORDER BY id",
            task,
        )
        return [r["id"] for r in rows]

    def _op_direct_dependencies(self, task: str) -> list[str]:
        return [
            r["dep_id"] for r in self.sql("SELECT dep_id FROM deps WHERE task_id=? ORDER BY dep_id", task)
        ]

    def _op_ready_after(self, done: list[str]) -> list[str]:
        ph = ",".join("?" * len(done))
        rows = self.sql(
            f"SELECT t.id FROM tasks t WHERE t.id NOT IN ({ph}) "
            "AND EXISTS (SELECT 1 FROM deps d WHERE d.task_id=t.id) "
            f"AND NOT EXISTS (SELECT 1 FROM deps d WHERE d.task_id=t.id AND d.dep_id NOT IN ({ph})) ORDER BY t.id",
            *done,
            *done,
        )
        return [r["id"] for r in rows]

    # -- contradictions --------------------------------------------------------------------------------------------------------------------
    def _conflicts(self) -> list[sqlite3.Row]:
        return self.sql(
            f"SELECT DISTINCT f.predicate, f.value, {_AGENTS} AS agents, {_SOURCES} AS sources FROM facts f "
            "JOIN fact_links l ON (l.src=f.id OR l.dst=f.id) AND l.kind='contradicts' "
            "JOIN facts g ON g.id = CASE WHEN l.src=f.id THEN l.dst ELSE l.src END "
            "WHERE f.status='active' AND g.status='active' ORDER BY f.predicate, f.value"
        )

    def _op_active_conflicts(self) -> list[str]:
        return [_label(r["predicate"], r["value"]) for r in self._conflicts()]

    def _op_active_conflict_agents(self) -> list[str]:
        return [
            f"{_label(r['predicate'], r['value'])}@{a}"
            for r in self._conflicts()
            for a in _split(r["agents"])
        ]

    # -- recovery ----------------------------------------------------------------------------------------------------------------------------
    def _op_reclaimed_tasks(self) -> list[str]:
        rows = self.sql("SELECT DISTINCT task_id FROM claims WHERE reclaimed_from != '' ORDER BY task_id")
        return [r["task_id"] for r in rows]

    def _op_reclaimer(self, task: str) -> str:
        return self.sql(
            "SELECT agent_id FROM claims WHERE task_id=? AND reclaimed_from != '' ORDER BY seq LIMIT 1", task
        )[0]["agent_id"]

    def _op_previous_claimer(self, task: str) -> str:
        return self.sql(
            "SELECT reclaimed_from FROM claims WHERE task_id=? AND reclaimed_from != '' ORDER BY seq LIMIT 1",
            task,
        )[0]["reclaimed_from"]

    def _op_completed_by(self, agent: str) -> list[str]:
        rows = self.sql(
            "SELECT DISTINCT t.id FROM tasks t JOIN claims c ON c.task_id=t.id "
            "WHERE t.status='done' AND t.claimed_by=? AND c.agent_id=? ORDER BY t.id",
            agent,
            agent,
        )
        return [r["id"] for r in rows]

    # -- memory currency and scope -----------------------------------------------------------------------------------------------------------------
    def _op_current_value(self, subject: str, predicate: str) -> str:
        return self.sql(
            "SELECT value FROM facts WHERE entity=? AND predicate=? AND scope='global' AND status='active' "
            "ORDER BY valid_from, value",
            normalize(subject),
            predicate,
        )[0]["value"]

    def _visible(self, scope: str, subject: str | None = None) -> list[sqlite3.Row]:
        chain = scope_chain(_scope(scope))
        ph = ",".join("?" * len(chain))
        extra, args = ("AND f.entity=? ", [normalize(subject)]) if subject else ("", [])
        return self.sql(
            f"SELECT f.predicate, f.value, f.scope FROM facts f WHERE f.scope IN ({ph}) AND f.status='active' {extra}"
            "ORDER BY f.valid_from, f.value",
            *chain,
            *args,
        )

    def _op_visible_facts(self, scope: str) -> list[str]:
        return [_label(r["predicate"], r["value"]) for r in self._visible(scope)]

    def _op_scope_leak(self, scope: str, other: str) -> str:
        return "yes" if any(r["scope"] == _scope(other) for r in self._visible(scope)) else "no"

    # -- episodes ------------------------------------------------------------------------------------------------------------------------------------
    def _op_episode_agent(self, contains: str) -> str:
        rows = self.sql("SELECT agent_id, text FROM episodes ORDER BY at, id")
        return next(r["agent_id"] for r in rows if contains.casefold() in r["text"].casefold())

    def _op_episode_count(self, agent: str) -> int:
        return int(self.sql("SELECT COUNT(*) AS n FROM episodes WHERE agent_id=?", agent)[0]["n"])

    # -- forgetting -----------------------------------------------------------------------------------------------------------------------------------------
    def _from_source(self, uri: str) -> list[sqlite3.Row]:
        return self.sql(
            "WITH RECURSIVE up(id) AS (SELECT l.src FROM fact_links l JOIN sources s ON s.id=l.dst "
            "WHERE s.uri=? AND l.kind='derived_from' "
            "UNION SELECT l.src FROM fact_links l JOIN up ON l.dst=up.id WHERE l.kind='derived_from') "
            "SELECT f.predicate, f.value, f.status FROM up JOIN facts f ON f.id=up.id ORDER BY f.predicate, f.value",
            uri,
        )

    def _op_remaining_from_source(self, source: str) -> list[str]:
        return [
            _label(r["predicate"], r["value"]) for r in self._from_source(source) if r["status"] == "active"
        ]

    def _op_forgotten_facts(self, source: str) -> list[str]:
        return [
            _label(r["predicate"], r["value"])
            for r in self._from_source(source)
            if r["status"] == "forgotten"
        ]


class ScaleSqlAnswerer(SqlAnswerer):
    """The L2-scale variant: the history holds K sprints, and class-wide questions are restricted to the named sprint.

    Same restriction rules as ``ScaleKnewatAnswerer``: task ids start with the sprint tag, source uris contain
    ``/<sprint>/``, episode texts start with ``S07:``. Here the restriction is part of the SQL (``LIKE``), not a Python
    filter over the rows.
    """

    SCOPED_OPS = (
        "handoffs_to", "handoffs_with_superseded_facts", "decisions_on_superseded", "decisions_on_forgotten",
        "active_conflicts", "active_conflict_agents", "reclaimed_tasks", "completed_by", "visible_facts",
        "episode_count",
    )  # fmt: skip

    def __init__(self, db_path: str | Path):
        super().__init__(db_path)
        self._sops: dict[str, Callable[..., Any]] = {
            n[5:]: fn for n, fn in vars(ScaleSqlAnswerer).items() if n.startswith("_sop_")
        }
        assert set(self._sops) == set(self.SCOPED_OPS)

    def _dispatch(self, q: Question, fn: Callable[..., Any]) -> Any:
        args = dict(q.args)
        sprint = args.pop("sprint")
        if q.op in self._sops:
            return self._sops[q.op](self, sprint, **args)
        return fn(self, **args)

    @staticmethod
    def _pre(sprint: str) -> str:
        return f"{sprint}-%"

    def _sop_handoffs_to(self, sprint: str, agent: str) -> list[str]:
        return [
            r["task_id"]
            for r in self.sql(
                "SELECT task_id FROM handoffs WHERE to_agent=? AND task_id LIKE ? ORDER BY at",
                agent,
                self._pre(sprint),
            )
        ]

    def _sop_handoffs_with_superseded_facts(self, sprint: str) -> list[str]:
        return [
            r["task_id"]
            for r in self.sql(
                "SELECT DISTINCT h.task_id FROM handoffs h JOIN handoff_items i ON i.handoff_id=h.id AND i.kind='fact' "
                "JOIN facts f ON f.id=i.item_id WHERE f.status='superseded' AND h.task_id LIKE ? ORDER BY h.task_id",
                self._pre(sprint),
            )
        ]

    def _decisions_with_status(self, sprint: str, status: str) -> list[str]:
        rows = self.sql(
            "SELECT DISTINCT d.text FROM decisions d JOIN decision_facts df ON df.decision_id=d.id "
            "JOIN facts f ON f.id=df.fact_id WHERE f.status=? AND d.task_id LIKE ? ORDER BY d.text",
            status,
            self._pre(sprint),
        )
        return list(dict.fromkeys(decision_label(r["text"]) for r in rows))

    def _sop_decisions_on_superseded(self, sprint: str) -> list[str]:
        return self._decisions_with_status(sprint, "superseded")

    def _sop_decisions_on_forgotten(self, sprint: str) -> list[str]:
        return self._decisions_with_status(sprint, "forgotten")

    def _sprint_conflicts(self, sprint: str) -> list[sqlite3.Row]:
        return [r for r in self._conflicts() if any(f"/{sprint}/" in s for s in _split(r["sources"]))]

    def _sop_active_conflicts(self, sprint: str) -> list[str]:
        return [_label(r["predicate"], r["value"]) for r in self._sprint_conflicts(sprint)]

    def _sop_active_conflict_agents(self, sprint: str) -> list[str]:
        return [
            f"{_label(r['predicate'], r['value'])}@{a}"
            for r in self._sprint_conflicts(sprint)
            for a in _split(r["agents"])
        ]

    def _sop_reclaimed_tasks(self, sprint: str) -> list[str]:
        rows = self.sql(
            "SELECT DISTINCT task_id FROM claims WHERE reclaimed_from != '' AND task_id LIKE ? ORDER BY task_id",
            self._pre(sprint),
        )
        return [r["task_id"] for r in rows]

    def _sop_completed_by(self, sprint: str, agent: str) -> list[str]:
        rows = self.sql(
            "SELECT DISTINCT t.id FROM tasks t JOIN claims c ON c.task_id=t.id "
            "WHERE t.status='done' AND t.claimed_by=? AND c.agent_id=? AND t.id LIKE ? ORDER BY t.id",
            agent,
            agent,
            self._pre(sprint),
        )
        return [r["id"] for r in rows]

    def _sop_visible_facts(self, sprint: str, scope: str, subject: str) -> list[str]:
        return [_label(r["predicate"], r["value"]) for r in self._visible(scope, subject)]

    def _sop_episode_count(self, sprint: str, agent: str) -> int:
        tag = f"{sprint.upper()}:"
        return int(
            self.sql(
                "SELECT COUNT(*) AS n FROM episodes WHERE agent_id=? AND substr(text,1,?)=?",
                agent,
                len(tag),
                tag,
            )[0]["n"]
        )
