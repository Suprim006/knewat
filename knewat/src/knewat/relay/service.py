"""Relay service layer: thin Python wrappers around the named Cypher queries in ``queries/relay/``.

Every state change is ONE parameterised statement (FalkorDB serialises writes per graph, so one statement is
atomic and isolated). Python only validates input shape (cycle check, bounds) and turns an empty result into a
precise error.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable, Sequence
from typing import Any

from plexus.common import check_between, new_id, now_ms, unique
from plexus.graph.client import GraphClient
from plexus.relay.errors import ClaimConflict, DuplicateArtifact, DuplicateTask, InvalidDag, UnknownReference

MAX_TASKS_PER_CALL = 500
MAX_EDGES_PER_CALL = 5000
MAX_ARTIFACTS_PER_CALL = 100
MAX_REFS_PER_CALL = 100
MAX_BLOCKED_DEPTH = 50  # blocked_by_failure: BFS levels
MAX_BLOCKED_NODES = 5000  # blocked_by_failure: distinct tasks returned
MAX_LEASE_MS = 24 * 3600 * 1000  # longest lease a claim / heartbeat may ask for (24 h)


def _check_lease(lease_ms: int) -> None:
    """Reject a lease outside 1 ms..24 h: now + lease_ms must not overflow int64 or lock a task for good."""
    if not 0 < lease_ms <= MAX_LEASE_MS:
        raise ValueError(f"lease_ms must be between 1 and {MAX_LEASE_MS} (24 h)")


def _check_acyclic(deps: dict[str, list[str]]) -> None:
    """Kahn's algorithm over the in-batch edges; edges to ids outside the batch cannot form a cycle."""
    indeg = {t: 0 for t in deps}
    children: dict[str, list[str]] = {t: [] for t in deps}
    for t, ds in deps.items():
        for d in ds:
            if d in deps:
                indeg[t] += 1
                children[d].append(t)
    queue = [t for t, n in indeg.items() if n == 0]
    seen = 0
    while queue:
        cur = queue.pop()
        seen += 1
        for ch in children[cur]:
            indeg[ch] -= 1
            if indeg[ch] == 0:
                queue.append(ch)
    if seen != len(deps):
        stuck = sorted(t for t, n in indeg.items() if n > 0)
        raise InvalidDag(f"dependency cycle among task(s): {', '.join(stuck)}")


class Relay:
    """Coordination operations on one tenant graph."""

    def __init__(self, client: GraphClient, graph: str, clock: Callable[[], int] = now_ms):
        self.client = client
        self.graph = graph
        self._clock = clock

    # -- agents -----------------------------------------------------------------------------------------
    def register_agent(self, agent_id: str, name: str, role: str, harness: str) -> dict[str, Any]:
        rows = self.client.rw(
            self.graph,
            "relay/register_agent",
            {"id": agent_id, "name": name, "role": role, "harness": harness, "now": self._clock()},
        )
        return dict(rows[0])

    # -- task DAG ---------------------------------------------------------------------------------------
    def create_tasks(self, tasks: Sequence[dict[str, Any]], *, step_id: str | None = None) -> list[str]:
        """Create tasks (+ DEPENDS_ON edges) atomically. Each item: ``{id?, title, priority?, depends_on?}``.

        ``depends_on`` may name tasks in the same batch or tasks that already exist. Returns the task ids in
        input order. Raises :class:`InvalidDag` (cycle, duplicate id in batch, > 500 tasks),
        :class:`DuplicateTask` or :class:`UnknownReference` (dependency not found); nothing is written then.
        """
        if not tasks:
            return []
        if len(tasks) > MAX_TASKS_PER_CALL:
            raise InvalidDag(f"at most {MAX_TASKS_PER_CALL} tasks per call, got {len(tasks)}")
        rows: list[dict[str, Any]] = []
        deps: dict[str, list[str]] = {}
        for item in tasks:
            tid = str(item.get("id") or new_id())
            if tid in deps:
                raise InvalidDag(f"duplicate task id in batch: {tid}")
            depends = list(dict.fromkeys(str(d) for d in item.get("depends_on") or ()))
            if tid in depends:
                raise InvalidDag(f"task {tid} depends on itself")
            deps[tid] = depends
            rows.append(
                {
                    "id": tid,
                    "title": str(item["title"]),
                    "priority": int(item.get("priority", 0)),
                    "seq": len(rows),
                }
            )
        _check_acyclic(deps)
        ids = list(deps)
        index = {t: i for i, t in enumerate(ids)}
        edges = [
            {"i": index[t], "j": index.get(d, -1), "dep": "" if d in index else d}
            for t, ds in deps.items()
            for d in ds
        ]
        if len(edges) > MAX_EDGES_PER_CALL:
            raise InvalidDag(f"at most {MAX_EDGES_PER_CALL} dependency edges per call, got {len(edges)}")
        ext = sorted({e["dep"] for e in edges if e["j"] < 0})
        res = self.client.rw(
            self.graph,
            "relay/create_tasks",
            {
                "tasks": rows,
                "edges": edges,
                "ids": ids,
                "ext_dep_ids": ext,
                "step_id": step_id or "",
                "now": self._clock(),
            },
        )
        if res.stats.get("nodes_created", 0) != len(rows):
            self._explain_rejected_create(ids, ext)
        return ids

    # -- claims -----------------------------------------------------------------------------------------
    def claim_next_task(
        self, agent_id: str, lease_ms: int, now: int | None = None, *, step_id: str | None = None
    ) -> dict[str, Any] | None:
        """Atomically claim the highest-priority ready task, or return None if nothing is claimable.

        Ready = open (or lease expired) with every dependency done. The returned dict carries ``version``
        (pass it to complete_task/fail_task) and ``reclaimed_from``
        ('' unless an expired lease was taken over).
        Raises :class:`UnknownReference` if the agent is not registered.
        """
        _check_lease(lease_ms)
        now = self._clock() if now is None else now
        rows = self.client.rw(
            self.graph,
            "relay/claim_next_task",
            {"agent": agent_id, "lease_ms": lease_ms, "step_id": step_id or "", "now": now},
        )
        if rows:
            return dict(rows[0])
        if not self.client.ro(self.graph, "relay/agent_exists", {"id": agent_id}):
            raise UnknownReference("agent", [agent_id])
        return None

    def heartbeat(self, agent_id: str, task_id: str, lease_ms: int, now: int | None = None) -> bool:
        """Extend the lease to ``max(current, now + lease_ms)``; it is never shortened.

        False if the caller is not the current claimer.
        """
        _check_lease(lease_ms)
        now = self._clock() if now is None else now
        rows = self.client.rw(
            self.graph,
            "relay/heartbeat",
            {"agent": agent_id, "task": task_id, "lease_ms": lease_ms, "now": now},
        )
        return bool(rows)

    # -- completion -------------------------------------------------------------------------------------
    def complete_task(
        self,
        agent_id: str,
        task_id: str,
        expected_version: int,
        artifacts: Sequence[dict[str, Any]] = (),
        now: int | None = None,
        *,
        step_id: str | None = None,
    ) -> dict[str, Any]:
        """Mark the task done if ``agent_id`` still holds it at ``expected_version``; record its artifacts.

        Artifacts: ``{id?, kind, uri, hash?, summary?}``. Returns ``{id, status, version, artifact_ids}``.
        Raises :class:`ClaimConflict` (stale version, wrong owner, not claimed), :class:`UnknownReference`
        (no such task) or :class:`DuplicateArtifact`; nothing is written then.
        """
        return self._finish(
            "relay/complete_task", agent_id, task_id, expected_version, artifacts, now, {}, step_id
        )

    def fail_task(
        self,
        agent_id: str,
        task_id: str,
        expected_version: int,
        artifacts: Sequence[dict[str, Any]] = (),
        reason: str = "",
        now: int | None = None,
        *,
        step_id: str | None = None,
    ) -> dict[str, Any]:
        """Like :meth:`complete_task` but marks the task failed (downstream tasks stay blocked)."""
        return self._finish(
            "relay/fail_task",
            agent_id,
            task_id,
            expected_version,
            artifacts,
            now,
            {"reason": reason},
            step_id,
        )

    def reopen_task(
        self, agent_id: str, task_id: str, now: int | None = None, *, step_id: str | None = None
    ) -> dict[str, Any]:
        """Retry a failed task: CAS ``failed`` -> ``open`` (version+1, lease and ``done_at`` cleared).

        Returns ``{id, status, version}``. Raises :class:`UnknownReference` (task or agent) or
        :class:`ClaimConflict` (the task is not failed); nothing is written then. Dependents stay blocked
        until the reopened task is done again; a stale holder of the old claim cannot complete it.
        """
        now = self._clock() if now is None else now
        rows = self.client.rw(
            self.graph,
            "relay/reopen_task",
            {"agent": agent_id, "task": task_id, "step_id": step_id or "", "now": now},
        )
        if rows:
            return dict(rows[0])
        st = self.task_status(task_id)
        if st is None:
            raise UnknownReference("task", [task_id])
        if not self.client.ro(self.graph, "relay/agent_exists", {"id": agent_id}):
            raise UnknownReference("agent", [agent_id])
        raise ClaimConflict(task_id, f"not failed (status is {st['status']})")

    def _finish(
        self,
        query: str,
        agent_id: str,
        task_id: str,
        expected_version: int,
        artifacts: Sequence[dict[str, Any]],
        now: int | None,
        extra: dict[str, Any],
        step_id: str | None = None,
    ) -> dict[str, Any]:
        if len(artifacts) > MAX_ARTIFACTS_PER_CALL:
            raise InvalidDag(f"at most {MAX_ARTIFACTS_PER_CALL} artifacts per call, got {len(artifacts)}")
        rows = [
            {
                "id": str(a.get("id") or new_id()),
                "kind": str(a.get("kind") or ""),
                "uri": str(a.get("uri") or ""),
                "hash": str(a.get("hash") or ""),
                "summary": str(a.get("summary") or ""),
            }
            for a in artifacts
        ]
        ids = [r["id"] for r in rows]
        if len(set(ids)) != len(ids):
            raise InvalidDag("duplicate artifact id in call")
        now = self._clock() if now is None else now
        res = self.client.rw(
            self.graph,
            query,
            {
                "agent": agent_id,
                "task": task_id,
                "expected_version": expected_version,
                "artifacts": rows,
                "artifact_ids": ids,
                "step_id": step_id or "",
                "now": now,
                **extra,
            },
        )
        if res:
            return {**dict(res[0]), "artifact_ids": ids}
        self._explain_rejected_finish(agent_id, task_id, expected_version, ids)
        raise AssertionError("unreachable")  # pragma: no cover

    def _explain_rejected_finish(self, agent_id: str, task_id: str, expected_version: int, ids: list[str]):
        st = self.task_status(task_id)
        if st is None:
            raise UnknownReference("task", [task_id])
        if st["status"] != "claimed":
            raise ClaimConflict(task_id, f"not claimed (status is {st['status']})")
        if st["claimed_by"] != agent_id:
            raise ClaimConflict(task_id, f"claimed by {st['claimed_by']}, not {agent_id}")
        if st["version"] != expected_version:
            raise ClaimConflict(task_id, f"stale version {expected_version}; current is {st['version']}")
        have = {r["id"] for r in self.client.ro(self.graph, "relay/existing_artifacts", {"ids": ids})}
        dup = [i for i in ids if i in have]
        if dup:
            raise DuplicateArtifact(dup)
        raise UnknownReference("agent", [agent_id])

    # -- handoffs, evidence, decisions -------------------------------------------------------------------
    def handoff(
        self,
        from_agent: str,
        to_agent: str,
        task_id: str,
        note: str,
        artifact_ids: Iterable[str] = (),
        fact_ids: Iterable[str] = (),
        now: int | None = None,
        *,
        step_id: str | None = None,
    ) -> str:
        """Create a Handoff node carrying artifacts and facts; returns its id.

        ``step_id`` (an existing Step) makes the same statement also write ``(Step)-[:WROTE]->(Handoff)``.

        All-or-nothing: raises :class:`UnknownReference` (and writes nothing) if either agent, the task, or
        any artifact/fact id does not exist.
        """
        arts, facts = unique(artifact_ids), unique(fact_ids)
        _bound_refs(arts, facts)
        hid = new_id()
        rows = self.client.rw(
            self.graph,
            "relay/handoff",
            {
                "id": hid,
                "from_agent": from_agent,
                "to_agent": to_agent,
                "task": task_id,
                "note": note,
                "artifact_ids": arts,
                "fact_ids": facts,
                "step_id": step_id or "",
                "now": self._clock() if now is None else now,
            },
        )
        if not rows:
            self._explain_missing(agents=[from_agent, to_agent], tasks=[task_id], facts=facts, artifacts=arts)
        return hid

    def verify_artifact(self, agent_id: str, artifact_id: str, now: int | None = None) -> dict[str, Any]:
        """Record ``(Artifact)-[:VERIFIED_BY]->(Agent)``. ``independent`` is False for a self-verification."""
        rows = self.client.rw(
            self.graph,
            "relay/verify_artifact",
            {"agent": agent_id, "artifact": artifact_id, "now": self._clock() if now is None else now},
        )
        if not rows:
            self._explain_missing(agents=[agent_id], tasks=[], facts=[], artifacts=[artifact_id])
        return dict(rows[0])

    def record_decision(
        self,
        agent_id: str,
        task_id: str,
        text: str,
        based_on_fact_ids: Iterable[str] = (),
        now: int | None = None,
        *,
        step_id: str | None = None,
    ) -> str:
        """Record a Decision BASED_ON facts; returns its id. If any fact id is unknown, nothing is written.

        ``step_id`` (an existing Step) makes the same statement also write ``(Step)-[:WROTE]->(Decision)``.
        """
        facts = unique(based_on_fact_ids)
        _bound_refs([], facts)
        did = new_id()
        rows = self.client.rw(
            self.graph,
            "relay/record_decision",
            {
                "id": did,
                "agent": agent_id,
                "task": task_id,
                "text": text,
                "fact_ids": facts,
                "step_id": step_id or "",
                "now": self._clock() if now is None else now,
            },
        )
        if not rows:
            self._explain_missing(agents=[agent_id], tasks=[task_id], facts=facts, artifacts=[])
        return did

    def _explain_missing(
        self, agents: list[str], tasks: list[str], facts: list[str], artifacts: list[str]
    ) -> None:
        have = self.client.ro(
            self.graph,
            "relay/missing_refs",
            {"agent_ids": agents, "task_ids": tasks, "fact_ids": facts, "artifact_ids": artifacts},
        )[0]
        for kind, wanted, found in (
            ("agent", agents, have["agents"]),
            ("task", tasks, have["tasks"]),
            ("artifact", artifacts, have["artifacts"]),
            ("fact", facts, have["facts"]),
        ):
            missing = [i for i in dict.fromkeys(wanted) if i not in found]
            if missing:
                raise UnknownReference(kind, missing)
        raise RuntimeError("write rejected although every referenced id exists")  # pragma: no cover

    # -- reads ------------------------------------------------------------------------------------------
    def ready_tasks(self, now: int | None = None, limit: int = 100) -> list[dict[str, Any]]:
        now = self._clock() if now is None else now
        return [
            dict(r) for r in self.client.ro(self.graph, "relay/ready_tasks", {"now": now, "limit": limit})
        ]

    def blocked_by_failure(self, task_id: str, depth: int = MAX_BLOCKED_DEPTH) -> list[str]:
        """Not-done tasks that depend (transitively, up to ``depth`` hops, 1..50) on ``task_id``.

        Nearest first, then by id. Level-wise expansion over distinct tasks (linear in the edges touched)
        inside ONE read statement, ``relay/dependents_closure`` (D-014): one snapshot even while tasks are
        being added. At most 5,000 tasks are returned. Done tasks are walked through but not reported.
        """
        check_between("depth", depth, MAX_BLOCKED_DEPTH)
        rows = self.client.ro(
            self.graph,
            "relay/dependents_closure",
            {"id": task_id, "depth": depth, "limit": MAX_BLOCKED_NODES},
        )
        return [r["id"] for r in rows]

    def task_status(self, task_id: str) -> dict[str, Any] | None:
        rows = self.client.ro(self.graph, "relay/task_status", {"id": task_id})
        if not rows:
            return None
        row = dict(rows[0])
        deps = row.pop("depends_on")
        statuses = row.pop("dependency_statuses")
        row["dependencies"] = [{"id": i, "status": s} for i, s in zip(deps, statuses, strict=True)]
        row["blocked_by"] = [d["id"] for d in row["dependencies"] if d["status"] != "done"]
        return row

    def _explain_rejected_create(self, ids: list[str], ext: list[str]) -> None:
        have = {r["id"] for r in self.client.ro(self.graph, "relay/existing_tasks", {"ids": ids + ext})}
        dup = [i for i in ids if i in have]
        if dup:
            raise DuplicateTask(dup)
        missing = [i for i in ext if i not in have]
        raise UnknownReference("dependency task", missing)


def _bound_refs(*lists: list[str]) -> None:
    for lst in lists:
        if len(lst) > MAX_REFS_PER_CALL:
            raise InvalidDag(f"at most {MAX_REFS_PER_CALL} referenced ids per list, got {len(lst)}")
