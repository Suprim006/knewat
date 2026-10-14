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
from plexus.relay.errors import DuplicateTask, InvalidDag, UnknownReference

MAX_TASKS_PER_CALL = 500
MAX_EDGES_PER_CALL = 5000


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

    def _explain_rejected_create(self, ids: list[str], ext: list[str]) -> None:
        have = {r["id"] for r in self.client.ro(self.graph, "relay/existing_tasks", {"ids": ids + ext})}
        dup = [i for i in ids if i in have]
        if dup:
            raise DuplicateTask(dup)
        missing = [i for i in ext if i not in have]
        raise UnknownReference("dependency task", missing)


def _ids(values: Iterable[str] | None) -> list[str]:
    return list(dict.fromkeys(values or ()))
