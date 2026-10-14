"""Lineage service layer: steps, recall records, provenance (``why``), time travel and forgetting.

Wrappers around the named queries in ``queries/lineage/``. Each write is ONE Cypher statement (atomic); reads
use ``ro``. Time is epoch ms; ``clock`` / ``now`` are injectable for tests.
"""

from __future__ import annotations

import time
import uuid
from collections.abc import Callable, Iterable
from typing import Any

from plexus.graph.client import GraphClient

MAX_LINK_IDS = 200  # ids per list in link_step
MAX_RECALL_RESULTS = 200


class LineageError(Exception):
    """Base class for lineage errors."""


class UnknownStep(LineageError, LookupError):
    """A step id (or a node id linked to a step) does not exist."""


class StepOrderError(LineageError, ValueError):
    """record_step was asked for an ``n`` lower than the agent's latest step."""


def _now_ms() -> int:
    return time.time_ns() // 1_000_000


def _new_id() -> str:
    return str(uuid.uuid4())


def _ids(values: Iterable[str] | None) -> list[str]:
    return list(dict.fromkeys(values or ()))


class Lineage:
    """Provenance and time-travel operations bound to one tenant graph."""

    def __init__(self, client: GraphClient, graph: str, clock: Callable[[], int] = _now_ms):
        self.client = client
        self.graph = graph
        self._clock = clock

    def _t(self, now: int | None) -> int:
        return self._clock() if now is None else now

    # -- sources ----------------------------------------------------------------------------------------
    def create_source(
        self,
        uri: str,
        kind: str = "doc",
        trust: float = 1.0,
        *,
        source_id: str | None = None,
        now: int | None = None,
    ) -> str:
        """MERGE a ``Source`` by ``uri`` (idempotent) and return its id. Pass it to ``Engram.assert_fact``."""
        if not uri.strip():
            raise ValueError("source uri must not be empty")
        rows = self.client.rw(
            self.graph,
            "lineage/create_source",
            {
                "source_id": source_id or _new_id(),
                "uri": uri,
                "kind": kind,
                "trust": float(trust),
                "now": self._t(now),
            },
        )
        return rows[0]["id"]

    # -- steps ------------------------------------------------------------------------------------------
    def record_step(self, agent_id: str, n: int | None = None, at: int | None = None) -> str:
        """Create the agent's step ``n`` (default: previous + 1), ``BY`` it, ``NEXT`` from its previous.

        Idempotent: asking again for an existing ``n`` returns the existing step id. Raises
        :class:`StepOrderError` if the agent already has a later step.
        """
        rows = self.client.rw(
            self.graph,
            "lineage/record_step",
            {"agent_id": agent_id, "step_id": _new_id(), "n": -1 if n is None else int(n), "at": self._t(at)},
        )
        r = rows[0]
        if r["step_id"] is None:
            raise StepOrderError(f"agent '{agent_id}' already has a step after n={r['n']}")
        return r["step_id"]

    def link_step(
        self, step_id: str, wrote_ids: Iterable[str] = (), read_ids: Iterable[str] = ()
    ) -> dict[str, int]:
        """Attach ``(Step)-[:WROTE]->(Fact|Decision|Handoff|Task)`` and ``(Step)-[:READ]->(Fact)`` edges.

        All-or-nothing; raises :class:`UnknownStep` (nothing written) if the step or any id is unknown.
        Returns ``{"read": n, "wrote": n}``.
        """
        wrote, read = _ids(wrote_ids), _ids(read_ids)
        if len(wrote) > MAX_LINK_IDS or len(read) > MAX_LINK_IDS:
            raise ValueError(f"at most {MAX_LINK_IDS} ids per list")
        rows = self.client.rw(
            self.graph, "lineage/link_step", {"step_id": step_id, "read_ids": read, "wrote_ids": wrote}
        )
        if not rows:
            wanted = [step_id, *wrote, *read]
            have = {r["id"] for r in self.client.ro(self.graph, "lineage/existing_ids", {"ids": wanted})}
            raise UnknownStep(f"unknown id(s): {', '.join(i for i in wanted if i not in have)}")
        return {"read": rows[0]["n_read"], "wrote": rows[0]["n_wrote"]}

    def link_assert_result(self, step_id: str, result: dict[str, Any]) -> dict[str, int]:
        """Link the outcome of ``Engram.assert_fact`` to a step.

        A new fact is WROTE; a duplicate, and the facts the assertion superseded or contradicts, are READ (the
        writer had to look at them).
        """
        fid = result["fact_id"]
        read = [*result.get("superseded", ()), *result.get("contradicts", ())]
        if result.get("duplicate_of"):
            return self.link_step(step_id, read_ids=[fid, *read])
        return self.link_step(step_id, wrote_ids=[fid], read_ids=read)
