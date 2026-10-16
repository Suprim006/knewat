"""What one tool call is made of: the metered database client and the :class:`Outcome` a tool returns."""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import Any

from plexus.audit.recorder import Ref
from plexus.common import StepIntent
from plexus.graph.client import GraphClient, Rows

AUXILIARY_PREFIX = (
    "activation/"  # reads under this prefix never name a ToolCall when the tool ran another read
)


class ReadOnlyViolation(RuntimeError):
    """A tool that ran under a read-only client (audit mode ``off``) tried to write: it fails closed."""


_WRITE_ATTRS = frozenset({"rw", "rw_script", "delete_graph"})


class MeteredClient:
    """Per-call proxy over :class:`GraphClient` that sums the server-side ``run_time_ms`` of every query.

    With ``read_only=True`` (a tenant in audit mode ``off``) every write entry point raises
    :class:`ReadOnlyViolation` instead of reaching the database, so a read tool that is mislabelled, or grows a
    write later, cannot mutate an observer tenant.
    """

    def __init__(self, inner: GraphClient, read_only: bool = False):
        self._inner = inner
        self.read_only = read_only
        self.run_time_ms = 0.0
        self.queries: list[str] = []
        self.writes: list[str] = []
        # P9-f: the Step this call's write should create in its own statement (audit mode full); a tool hands
        # it to the service and reports ``Outcome(step_id=intent.used_id, linked=True)`` when it was used
        self.step_intent: StepIntent | None = None

    def _note(self, name: str, rows: Rows | None, write: bool) -> None:
        self.queries.append(name)
        if write:
            self.writes.append(name)
        if rows is not None:
            self.run_time_ms += rows.run_time_ms

    def ro(self, graph: str, name: str, params: dict | None = None, timeout_ms: int | None = None) -> Rows:
        rows = self._inner.ro(graph, name, params, timeout_ms)
        self._note(name, rows, False)
        return rows

    def rw(self, graph: str, name: str, params: dict | None = None, timeout_ms: int | None = None) -> Rows:
        if self.read_only:
            raise ReadOnlyViolation(f"write query {name!r} refused: this call runs on a read-only client")
        rows = self._inner.rw(graph, name, params, timeout_ms)
        self._note(name, rows, True)
        return rows

    def __getattr__(self, item: str) -> Any:
        if self.read_only and item in _WRITE_ATTRS:
            raise ReadOnlyViolation(f"{item!r} is not available on a read-only client")
        return getattr(self._inner, item)

    @property
    def query_name(self) -> str:
        """The write query if there was one (the last), else the last *main* read query.

        ``activation/*`` reads are auxiliary (they re-rank or annotate what the tool's own query found), so a
        forgetting-on ``recall`` is recorded as ``engram/recall``. A tool that only runs activation reads
        (``memory_strength``) still reports the last of them.
        """
        if self.writes:
            return self.writes[-1]
        main = [q for q in self.queries if not q.startswith(AUXILIARY_PREFIX)]
        if main:
            return main[-1]
        return self.queries[-1] if self.queries else ""


@dataclass
class Outcome:
    """What a tool function returns: the JSON-able result plus the nodes it touched (for the audit edges)."""

    data: dict[str, Any]
    created: Sequence[Ref] = ()
    updated: Sequence[Ref] = ()
    step_id: str | None = (
        None  # P9-f: the Step the tool's own write statement created (else the runtime opens one)
    )
    linked: bool = (
        False  # P9-f: that statement also wrote the WROTE / READ edges: the runtime adds no link_step
    )
    # Lineage attachment (ignored when plexus.lineage is not installed):
    read_ids: Sequence[str] = ()  # Facts the call looked at -> (Step)-[:READ]->(Fact)
    assert_result: dict[str, Any] | None = None  # Engram.assert_fact result -> Lineage.link_assert_result
    after: Callable[[Any, str | None], dict[str, Any] | None] | None = None
    """``after(lineage, step_id)`` runs once the Step exists; the dict it returns is merged into the result."""


def step_link(m: MeteredClient) -> dict[str, Any]:
    """``Outcome`` keywords for a tool whose write used ``m.step_intent`` (P9-f): its Step id, already linked."""
    intent = m.step_intent
    if intent is None or intent.used_id is None:
        return {}
    return {"step_id": intent.used_id, "linked": True}
