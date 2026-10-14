"""Arm P: every L2 question is answered by deterministic Cypher against the tenant graph (no LLM, no retrieval).

Each question's ``op`` names one function below; the function runs one or two read-only statements from
``queries/l2/*.cypher`` (a separate :class:`QueryLibrary`, loaded strictly like the product's) and shapes the rows
into the answer format. The graph holds the relationships the questions are about (BASED_ON, CARRIES, SUPERSEDES,
CONTRADICTS, DEPENDS_ON, CLAIMED, DERIVED_FROM, IN_SCOPE...), so no function reads text or guesses.
"""

from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from plexus.crucible.l2.questions import Question
from plexus.crucible.l2.scenario import decision_label
from plexus.graph.client import GraphClient
from plexus.graph.queries import QueryLibrary
from plexus.graph.tenancy import graph_name

QUERIES_ROOT = Path(__file__).resolve().parent / "queries"


def _label(predicate: str, value: str) -> str:
    return f"{predicate}={' '.join(str(value).split())}"


def _norm(s: str) -> str:
    return " ".join(s.casefold().split())


def _scope(spec: str) -> tuple[str, str]:
    kind, _, name = spec.partition(":")
    return (kind, name) if name else ("global", "global")


@dataclass
class Trace:
    """What one answer cost on the server: statements run and the server-side ``run_time_ms`` summed."""

    statements: int = 0
    server_ms: float = 0.0
    queries: list[str] = field(default_factory=list)


class PlexusAnswerer:
    def __init__(self, client: GraphClient, tenant: str):
        self.client = client
        self.graph = graph_name(tenant)
        self.lib = QueryLibrary(QUERIES_ROOT)
        self.trace = Trace()
        self._ops: dict[str, Callable[..., Any]] = {
            name[4:]: fn for name, fn in vars(type(self)).items() if name.startswith("_op_")
        }

    # -- plumbing -------------------------------------------------------------------------------------------
    def run(self, query: str, /, **params: Any) -> list[dict[str, Any]]:
        rq = self.lib.render(f"l2/{query}", params)
        assert rq.mode == "ro"
        rows = self.client._run(self.graph, rq, rq.cypher, True, None)
        self.trace.statements += 1
        self.trace.server_ms += float(rows.run_time_ms or 0.0)
        self.trace.queries.append(f"l2/{query}")
        return list(rows)

    def answer(self, q: Question) -> tuple[Any, dict[str, Any]]:
        """Returns ``(answer, {latency_ms, server_ms, statements, queries})``."""
        fn = self._ops.get(q.op)
        if fn is None:
            raise KeyError(f"no Cypher answerer for op '{q.op}'")
        self.trace = Trace()
        t0 = time.perf_counter()
        out = fn(self, **q.args)
        meta = {
            "latency_ms": round((time.perf_counter() - t0) * 1000, 2),
            "server_ms": round(self.trace.server_ms, 3),
            "statements": self.trace.statements,
            "queries": list(self.trace.queries),
        }
        return out, meta

    @property
    def ops(self) -> list[str]:
        return sorted(self._ops)

    # -- decision provenance ---------------------------------------------------------------------------------------
    def _decision_rows(self, decision: str) -> list[dict[str, Any]]:
        rows = [r for r in self.run("decisions") if decision_label(r["text"]) == decision]
        return [r for r in rows if r["predicate"] is not None]

    def _op_decision_facts(self, decision: str) -> list[str]:
        return [_label(r["predicate"], r["value"]) for r in self._decision_rows(decision)]

    def _op_decision_fact_agents(self, decision: str) -> list[str]:
        return [
            f"{_label(r['predicate'], r['value'])}@{a}"
            for r in self._decision_rows(decision)
            for a in r["asserted_by"]
        ]

    def _op_decision_sources(self, decision: str) -> list[str]:
        return list(dict.fromkeys(s for r in self._decision_rows(decision) for s in r["sources"]))

    # -- handoffs ----------------------------------------------------------------------------------------------------
    def _handoff(self, task: str) -> dict[str, Any]:
        return next(r for r in self.run("handoffs") if r["task_id"] == task)

    def _op_handoff_artifacts(self, task: str) -> list[str]:
        return list(self._handoff(task)["artifacts"])

    def _op_handoff_route(self, task: str) -> list[str]:
        h = self._handoff(task)
        return [f"{h['from_agent']}->{h['to_agent']}"]

    def _op_handoff_facts(self, task: str) -> list[str]:
        return [_label(f["predicate"], f["value"]) for f in self._handoff(task)["facts"]]

    def _op_handoffs_to(self, agent: str) -> list[str]:
        return [r["task_id"] for r in self.run("handoffs") if r["to_agent"] == agent]

    def _op_handoffs_with_superseded_facts(self) -> list[str]:
        return [r["task_id"] for r in self.run("handoffs_with_fact_status", status="superseded")]

    # -- time travel -----------------------------------------------------------------------------------------------------
    def _op_as_of_values(self, subject: str, predicate: str, t: int) -> list[str]:
        return [r["value"] for r in self.run("fact_as_of", norm_subject=_norm(subject), predicate=predicate, t=t)]

    def _op_as_of_facts(self, subject: str, predicate: str, t: int) -> list[str]:
        rows = self.run("fact_as_of", norm_subject=_norm(subject), predicate=predicate, t=t)
        return [_label(r["predicate"], r["value"]) for r in rows]

    def _op_value_history(self, subject: str, predicate: str) -> list[str]:
        return [r["value"] for r in self.run("fact_versions", norm_subject=_norm(subject), predicate=predicate)]

    # -- facts -----------------------------------------------------------------------------------------------------------------
    def _fact(self, label: str) -> dict[str, Any]:
        for r in self.run("facts_all"):
            if _label(r["predicate"], r["value"]) == label:
                return r
        raise KeyError(label)

    def _op_decisions_on_superseded(self) -> list[str]:
        return [decision_label(r["text"]) for r in self.run("decisions_on_status", status="superseded")]

    def _op_decisions_on_forgotten(self) -> list[str]:
        return [decision_label(r["text"]) for r in self.run("decisions_on_status", status="forgotten")]

    def _op_decisions_on_fact(self, fact: str) -> list[str]:
        predicate, _, value = fact.partition("=")
        return [decision_label(r["text"]) for r in self.run("decisions_on_fact", predicate=predicate, value=value)]

    def _op_superseder(self, fact: str) -> list[str]:
        out = []
        for r in self.run("facts_all"):
            if any(_label(o["predicate"], o["value"]) == fact for o in r["supersedes"]):
                out += [f"{_label(r['predicate'], r['value'])}@{a}" for a in r["asserted_by"]]
        return out

    def _op_fact_agent(self, fact: str) -> str:
        return self._fact(fact)["asserted_by"][0]

    def _op_fact_source(self, fact: str) -> str:
        return self._fact(fact)["sources"][0]

    def _op_fact_scope(self, fact: str) -> str:
        r = self._fact(fact)
        return r["scope_name"] if r["scope_kind"] == "global" else f"{r['scope_kind']}:{r['scope_name']}"

    # -- dependencies --------------------------------------------------------------------------------------------------------------
    def _op_blocked_by_failure(self, task: str) -> list[str]:
        return [r["id"] for r in self.run("tasks_downstream", task_id=task)]

    def _op_direct_dependencies(self, task: str) -> list[str]:
        return [r["id"] for r in self.run("task_dependencies", task_id=task)]

    def _op_ready_after(self, done: list[str]) -> list[str]:
        return [r["id"] for r in self.run("tasks_ready_after", done=list(done))]

    # -- contradictions -----------------------------------------------------------------------------------------------------------------
    def _op_active_conflicts(self) -> list[str]:
        return [_label(r["predicate"], r["value"]) for r in self.run("active_conflicts")]

    def _op_active_conflict_agents(self) -> list[str]:
        return [
            f"{_label(r['predicate'], r['value'])}@{a}" for r in self.run("active_conflicts") for a in r["asserted_by"]
        ]

    # -- recovery ----------------------------------------------------------------------------------------------------------------------------
    def _op_reclaimed_tasks(self) -> list[str]:
        return list(dict.fromkeys(r["task_id"] for r in self.run("claims") if r["reclaimed_from"]))

    def _op_reclaimer(self, task: str) -> str:
        return next(r["agent"] for r in self.run("claims") if r["task_id"] == task and r["reclaimed_from"])

    def _op_previous_claimer(self, task: str) -> str:
        return next(r["reclaimed_from"] for r in self.run("claims") if r["task_id"] == task and r["reclaimed_from"])

    def _op_completed_by(self, agent: str) -> list[str]:
        return [
            r["task_id"]
            for r in self.run("claims")
            if r["task_status"] == "done" and r["task_claimed_by"] == agent and r["agent"] == agent
        ]

    # -- memory currency and scope ------------------------------------------------------------------------------------------------------------
    def _op_current_value(self, subject: str, predicate: str) -> str:
        return self.run("fact_current", norm_subject=_norm(subject), predicate=predicate)[0]["value"]

    def _op_visible_facts(self, scope: str) -> list[str]:
        kind, name = _scope(scope)
        return [_label(r["predicate"], r["value"]) for r in self.run("facts_visible", kind=kind, name=name)]

    def _op_scope_leak(self, scope: str, other: str) -> str:
        kind, name = _scope(scope)
        okind, oname = _scope(other)
        rows = self.run("facts_visible", kind=kind, name=name)
        return "yes" if any(r["scope_kind"] == okind and r["scope_name"] == oname for r in rows) else "no"

    # -- episodes ---------------------------------------------------------------------------------------------------------------------------------
    def _op_episode_agent(self, contains: str) -> str:
        return next(r["agent"] for r in self.run("episodes") if contains.casefold() in r["text"].casefold())

    def _op_episode_count(self, agent: str) -> int:
        return sum(r["agent"] == agent for r in self.run("episodes"))

    # -- forgetting -------------------------------------------------------------------------------------------------------------------------------------
    def _op_remaining_from_source(self, source: str) -> list[str]:
        rows = self.run("facts_from_source", uri=source)
        return [_label(r["predicate"], r["value"]) for r in rows if r["status"] == "active"]

    def _op_forgotten_facts(self, source: str) -> list[str]:
        rows = self.run("facts_from_source", uri=source)
        return [_label(r["predicate"], r["value"]) for r in rows if r["status"] == "forgotten"]
