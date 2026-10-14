"""Relay service layer: thin Python wrappers around the named Cypher queries in ``queries/relay/``.

Every state change is ONE parameterised statement (FalkorDB serialises writes per graph, so one statement is
atomic and isolated). Python only validates input shape (cycle check, bounds) and turns an empty result into a
precise error.
"""

from __future__ import annotations

import time
import uuid
from collections.abc import Callable, Iterable, Sequence
from typing import Any

from plexus.graph.client import GraphClient
from plexus.relay.errors import ClaimConflict, DuplicateArtifact, DuplicateTask, InvalidDag, UnknownReference

MAX_TASKS_PER_CALL = 500
MAX_EDGES_PER_CALL = 5000
MAX_ARTIFACTS_PER_CALL = 100


def _now_ms() -> int:
    return int(time.time() * 1000)


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

    def __init__(self, client: GraphClient, graph: str, clock: Callable[[], int] = _now_ms):
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
    def create_tasks(self, tasks: Sequence[dict[str, Any]]) -> list[str]:
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
            tid = str(item.get("id") or uuid.uuid4())
            if tid in deps:
                raise InvalidDag(f"duplicate task id in batch: {tid}")
            depends = list(dict.fromkeys(str(d) for d in item.get("depends_on") or ()))
            if tid in depends:
                raise InvalidDag(f"task {tid} depends on itself")
            deps[tid] = depends
            rows.append({"id": tid, "title": str(item["title"]), "priority": int(item.get("priority", 0))})
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
            {"tasks": rows, "edges": edges, "ids": ids, "ext_dep_ids": ext, "now": self._clock()},
        )
        if res.stats.get("nodes_created", 0) != len(rows):
            self._explain_rejected_create(ids, ext)
        return ids

    # -- claims -----------------------------------------------------------------------------------------
    def claim_next_task(self, agent_id: str, lease_ms: int, now: int | None = None) -> dict[str, Any] | None:
        """Atomically claim the highest-priority ready task, or return None if nothing is claimable.

        Ready = open (or lease expired) with every dependency done. The returned dict carries ``version``
        (pass it to complete_task/fail_task) and ``reclaimed_from``
        ('' unless an expired lease was taken over).
        Raises :class:`UnknownReference` if the agent is not registered.
        """
        if lease_ms <= 0:
            raise ValueError("lease_ms must be positive")
        now = self._clock() if now is None else now
        rows = self.client.rw(
            self.graph, "relay/claim_next_task", {"agent": agent_id, "lease_ms": lease_ms, "now": now}
        )
        if rows:
            return dict(rows[0])
        if not self.client.ro(self.graph, "relay/agent_exists", {"id": agent_id}):
            raise UnknownReference("agent", [agent_id])
        return None

    def heartbeat(self, agent_id: str, task_id: str, lease_ms: int, now: int | None = None) -> bool:
        """Extend the lease to ``now + lease_ms``. False if the caller is not the current claimer."""
        if lease_ms <= 0:
            raise ValueError("lease_ms must be positive")
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
    ) -> dict[str, Any]:
        """Mark the task done if ``agent_id`` still holds it at ``expected_version``; record its artifacts.

        Artifacts: ``{id?, kind, uri, hash?, summary?}``. Returns ``{id, status, version, artifact_ids}``.
        Raises :class:`ClaimConflict` (stale version, wrong owner, not claimed), :class:`UnknownReference`
        (no such task) or :class:`DuplicateArtifact`; nothing is written then.
        """
        return self._finish("relay/complete_task", agent_id, task_id, expected_version, artifacts, now, {})

    def fail_task(
        self,
        agent_id: str,
        task_id: str,
        expected_version: int,
        artifacts: Sequence[dict[str, Any]] = (),
        reason: str = "",
        now: int | None = None,
    ) -> dict[str, Any]:
        """Like :meth:`complete_task` but marks the task failed (downstream tasks stay blocked)."""
        return self._finish(
            "relay/fail_task", agent_id, task_id, expected_version, artifacts, now, {"reason": reason}
        )

    def _finish(
        self,
        query: str,
        agent_id: str,
        task_id: str,
        expected_version: int,
        artifacts: Sequence[dict[str, Any]],
        now: int | None,
        extra: dict[str, Any],
    ) -> dict[str, Any]:
        if len(artifacts) > MAX_ARTIFACTS_PER_CALL:
            raise InvalidDag(f"at most {MAX_ARTIFACTS_PER_CALL} artifacts per call, got {len(artifacts)}")
        rows = [
            {
                "id": str(a.get("id") or uuid.uuid4()),
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

    # -- reads ------------------------------------------------------------------------------------------
    def ready_tasks(self, now: int | None = None, limit: int = 100) -> list[dict[str, Any]]:
        now = self._clock() if now is None else now
        return [
            dict(r) for r in self.client.ro(self.graph, "relay/ready_tasks", {"now": now, "limit": limit})
        ]

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


def _ids(values: Iterable[str] | None) -> list[str]:
    return list(dict.fromkeys(values or ()))
