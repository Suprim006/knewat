"""Arm P at scale: the same deterministic Cypher answerer, with sprint scoping where a question asks about a whole class.

``plexus_answerer.PlexusAnswerer`` is reused unchanged. Questions whose arguments already name a unique thing (a task id
``s07-t03-...``, a fact label, a decision name, a subject, a source uri) run exactly the same operation with exactly the
same statements. Questions that ask about ALL decisions / handoffs / claims / conflicts / episodes need to be restricted
to the sprint named in the question; those operations are overridden below (``_sop_*``), listed in the BASELINE
section. The restriction is a filter over the rows of the existing statements by the sprint tag carried in task ids,
source uris and episode texts, except ``visible_facts`` which needs one extra read-only statement
(``queries/l2scale/facts_visible_subject.cypher``) that adds the subject to ``l2/facts_visible``.
"""

from __future__ import annotations

import time
from typing import Any

from plexus.crucible.l2.plexus_answerer import PlexusAnswerer, Trace, _label, _norm, _scope
from plexus.crucible.l2.questions import Question
from plexus.crucible.l2.scenario import decision_label


class ScalePlexusAnswerer(PlexusAnswerer):
    SCOPED_OPS = (
        "handoffs_to", "handoffs_with_superseded_facts", "decisions_on_superseded", "decisions_on_forgotten",
        "active_conflicts", "active_conflict_agents", "reclaimed_tasks", "completed_by", "visible_facts",
        "episode_count",
    )  # fmt: skip

    def __init__(self, client: Any, tenant: str):
        super().__init__(client, tenant)
        self._ops = {n[4:]: fn for n, fn in vars(PlexusAnswerer).items() if n.startswith("_op_")}  # the unchanged ops
        self._sops = {n[5:]: fn for n, fn in vars(type(self)).items() if n.startswith("_sop_")}
        assert set(self._sops) == set(self.SCOPED_OPS)

    def answer(self, q: Question) -> tuple[Any, dict[str, Any]]:
        args = dict(q.args)
        sprint = args.pop("sprint")
        self.trace = Trace()
        t0 = time.perf_counter()
        if q.op in self._sops:
            out = self._sops[q.op](self, sprint, **args)
        else:
            fn = self._ops.get(q.op)
            if fn is None:
                raise KeyError(f"no Cypher answerer for op '{q.op}'")
            out = fn(self, **args)
        meta = {
            "latency_ms": round((time.perf_counter() - t0) * 1000, 2),
            "server_ms": round(self.trace.server_ms, 3),
            "statements": self.trace.statements,
            "queries": list(self.trace.queries),
        }
        return out, meta

    # -- helpers ---------------------------------------------------------------------------------------------
    @staticmethod
    def _in_sprint_task(sprint: str, task_id: str | None) -> bool:
        return bool(task_id) and task_id.startswith(f"{sprint}-")

    @staticmethod
    def _in_sprint_uri(sprint: str, uri: str) -> bool:
        return f"/{sprint}/" in uri

    # -- scoped operations -------------------------------------------------------------------------------------
    def _sop_handoffs_to(self, sprint: str, agent: str) -> list[str]:
        return [
            r["task_id"]
            for r in self.run("handoffs")
            if r["to_agent"] == agent and self._in_sprint_task(sprint, r["task_id"])
        ]

    def _sop_handoffs_with_superseded_facts(self, sprint: str) -> list[str]:
        return [t for t in (r["task_id"] for r in self.run("handoffs_with_fact_status", status="superseded")) if self._in_sprint_task(sprint, t)]

    def _decisions_with_status(self, sprint: str, status: str) -> list[str]:
        rows = [r for r in self.run("decisions") if self._in_sprint_task(sprint, r["task_id"]) and r["status"] == status]
        return list(dict.fromkeys(decision_label(r["text"]) for r in rows))

    def _sop_decisions_on_superseded(self, sprint: str) -> list[str]:
        return self._decisions_with_status(sprint, "superseded")

    def _sop_decisions_on_forgotten(self, sprint: str) -> list[str]:
        return self._decisions_with_status(sprint, "forgotten")

    def _conflicts(self, sprint: str) -> list[dict[str, Any]]:
        return [
            r for r in self.run("active_conflicts") if any(self._in_sprint_uri(sprint, s) for s in r["sources"])
        ]

    def _sop_active_conflicts(self, sprint: str) -> list[str]:
        return [_label(r["predicate"], r["value"]) for r in self._conflicts(sprint)]

    def _sop_active_conflict_agents(self, sprint: str) -> list[str]:
        return [f"{_label(r['predicate'], r['value'])}@{a}" for r in self._conflicts(sprint) for a in r["asserted_by"]]

    def _sop_reclaimed_tasks(self, sprint: str) -> list[str]:
        return list(
            dict.fromkeys(
                r["task_id"] for r in self.run("claims") if r["reclaimed_from"] and self._in_sprint_task(sprint, r["task_id"])
            )
        )

    def _sop_completed_by(self, sprint: str, agent: str) -> list[str]:
        return [
            r["task_id"]
            for r in self.run("claims")
            if r["task_status"] == "done" and r["task_claimed_by"] == agent and r["agent"] == agent
            and self._in_sprint_task(sprint, r["task_id"])
        ]  # fmt: skip

    def _sop_visible_facts(self, sprint: str, scope: str, subject: str) -> list[str]:
        kind, name = _scope(scope)
        rows = self.run("l2scale_facts_visible_subject", kind=kind, name=name, norm_subject=_norm(subject))
        return [_label(r["predicate"], r["value"]) for r in rows]

    def _sop_episode_count(self, sprint: str, agent: str) -> int:
        tag = f"{sprint.upper()}:"
        return sum(r["agent"] == agent and r["text"].startswith(tag) for r in self.run("episodes"))

    def run(self, query: str, /, **params: Any) -> list[dict[str, Any]]:
        if not query.startswith("l2scale_"):
            return super().run(query, **params)
        name = "l2scale/" + query[len("l2scale_") :]
        rq = self.lib.render(name, params)
        assert rq.mode == "ro"
        rows = self.client._run(self.graph, rq, rq.cypher, True, None)
        self.trace.statements += 1
        self.trace.server_ms += float(rows.run_time_ms or 0.0)
        self.trace.queries.append(name)
        return list(rows)
