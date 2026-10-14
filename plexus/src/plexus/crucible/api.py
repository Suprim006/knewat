"""The ``CoordinationBackend`` protocol: the one tool surface every Crucible arm implements (BASELINE §0).

Only the backend changes between arms. The method names and signatures mirror the Plexus MCP tools the
benchmark uses (``remember_episode``, ``assert_fact``, ``recall``, ``forget_source``, ``create_tasks``,
``claim_next_task``, ``heartbeat``, ``complete_task``, ``handoff``, ``record_decision``, ``why``, ``knew_at``,
``as_of``) plus a few read helpers the harness needs to count violations (``facts``, ``task_status``,
``list_tasks``). Return values are plain dicts so results can be dumped to JSON.

Conventions shared by every arm (the unit suite in ``tests/crucible/test_backends.py`` pins them):

* time is epoch milliseconds; ``now`` parameters exist so tests can drive the clock;
* a task is *ready* when it is ``open`` (or ``claimed`` with an expired lease) and every dependency is ``done``;
  claims go to the highest ``priority``, then the lowest creation sequence;
* a lease is ``lease_until = now + lease_ms``; ``heartbeat`` never shortens it and fails for a non-owner;
* ``complete_task`` is a compare-and-set on (owner, version) and raises :class:`ClaimConflict` otherwise;
* facts live in a *scope* (``global`` | ``project:<name>`` | ``user:<name>``); project/user scopes also see
  ``global``. A fact is identified by (subject, predicate); asserting the same normalised value again is a
  duplicate, a different value from the same agent supersedes its own earlier value, and a different value
  from another agent is a *contradiction*: both stay active and the newer one lists the older in ``contradicts``;
* ``forget_source`` forgets every fact that reaches the source through ``derived_from`` links (transitively).

Lineage methods (``why``, ``knew_at``) may raise :class:`Unsupported` in arms that keep no provenance: the
Layer 2 harness answers those questions by LLM over the arm's artifacts, which is the point of the comparison.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field
from typing import Any, Protocol, runtime_checkable

OPEN = 9_999_999_999_999  # open-ended valid_to, identical to the Plexus graph model

TOOLS = (
    "remember_episode",
    "assert_fact",
    "recall",
    "forget_source",
    "create_tasks",
    "claim_next_task",
    "heartbeat",
    "complete_task",
    "handoff",
    "record_decision",
    "why",
    "knew_at",
    "as_of",
)
LINEAGE_TOOLS = ("why", "knew_at")


class CrucibleError(Exception):
    """Base class for backend errors."""


class Unsupported(CrucibleError, NotImplementedError):
    """This arm keeps no data that could answer the call deterministically (Layer 2 asks an LLM instead)."""


class ClaimConflict(CrucibleError):
    """complete/heartbeat rejected: the caller no longer owns the task at that version."""


class UnknownReference(CrucibleError, LookupError):
    """An id (task, agent, fact, artifact, source, scope) does not exist; nothing was written."""


class InvalidTenant(CrucibleError, ValueError):
    """The tenant name is not acceptable (same rule for every arm: ``^[a-z0-9_]{1,48}$``)."""


@dataclass(frozen=True)
class BackendSpec:
    """Everything needed to (re)open a backend in another thread or process (e.g. the C2 victim)."""

    arm: str  # B0 | B1 | B2 | P | P-mcp
    tenant: str
    root: str  # directory for file-based arms (ignored by Plexus)
    host: str = ""  # FalkorDB host (Plexus arms)
    port: int = 0
    embedder: str = "fastembed"  # fastembed | hash
    options: dict[str, Any] = field(default_factory=dict)

    def to_json(self) -> dict[str, Any]:
        return {
            "arm": self.arm,
            "tenant": self.tenant,
            "root": self.root,
            "host": self.host,
            "port": self.port,
            "embedder": self.embedder,
            "options": dict(self.options),
        }

    @classmethod
    def from_json(cls, data: dict[str, Any]) -> BackendSpec:
        return cls(**data)


@runtime_checkable
class CoordinationBackend(Protocol):
    """One tenant's memory + coordination store. Implementations must be safe to call from many threads."""

    name: str  # arm id
    label: str  # human name, e.g. "SQLite"
    capabilities: frozenset[str]  # subset of CAPABILITIES

    # -- agents ------------------------------------------------------------------------------------------
    def register_agent(self, agent_id: str, role: str = "") -> None: ...

    # -- memory ------------------------------------------------------------------------------------------
    def remember_episode(self, agent_id: str, text: str, step: int | None = None) -> str: ...

    def add_source(self, uri: str, kind: str = "doc", trust: float = 1.0) -> str:
        """Idempotent on ``uri``. Returns the source id to pass to ``assert_fact``."""
        ...

    def assert_fact(
        self,
        agent_id: str,
        subject: str,
        predicate: str,
        value: str,
        scope: str = "global",
        source_id: str | None = None,
        derived_from: Sequence[str] = (),
        confidence: float = 1.0,
        supersede: bool = False,
        now: int | None = None,
    ) -> dict[str, Any]:
        """Returns ``{fact_id, duplicate_of, superseded: [ids], contradicts: [ids]}``.

        ``derived_from`` lists fact ids this fact was inferred from (a fact derived from a forgotten source
        is forgotten with it). Raises :class:`UnknownReference` (nothing written) for an unknown source/fact.
        """
        ...

    def recall(
        self, agent_id: str, query: str, scope: str = "global", k: int = 8, as_of: int | None = None
    ) -> list[dict[str, Any]]:
        """Top-``k`` facts, best first: ``[{fact_id, text, entity, predicate, value, score, status}]``."""
        ...

    def forget_source(self, source_id: str) -> dict[str, Any]:
        """Returns ``{source_id, fact_ids: [forgotten ids]}``. Idempotent."""
        ...

    def facts(self, subject: str, predicate: str, scope: str = "global") -> list[dict[str, Any]]:
        """Every version, oldest first: ``[{fact_id, value, status, valid_from, valid_to, asserted_by,
        supersedes, contradicts}]`` (the ``fact_history`` tool)."""
        ...

    # -- coordination --------------------------------------------------------------------------------------
    def create_tasks(self, tasks: Sequence[dict[str, Any]]) -> list[str]:
        """``[{id?, title, priority?, depends_on?}]`` -> ids in input order. Atomic."""
        ...

    def claim_next_task(
        self, agent_id: str, lease_ms: int = 60_000, now: int | None = None
    ) -> dict[str, Any] | None:
        """``{id, title, priority, version, lease_until, reclaimed_from}`` or ``None``."""
        ...

    def heartbeat(
        self, agent_id: str, task_id: str, lease_ms: int = 60_000, now: int | None = None
    ) -> bool: ...

    def complete_task(
        self, agent_id: str, task_id: str, expected_version: int, artifacts: Sequence[dict[str, Any]] = ()
    ) -> dict[str, Any]:
        """``{id, status, version, artifact_ids}``. Raises :class:`ClaimConflict` / :class:`UnknownReference`."""
        ...

    def handoff(
        self,
        agent_id: str,
        to_agent: str,
        task_id: str,
        note: str,
        artifact_ids: Iterable[str] = (),
        fact_ids: Iterable[str] = (),
    ) -> str: ...

    def record_decision(
        self, agent_id: str, task_id: str, text: str, based_on_fact_ids: Iterable[str] = ()
    ) -> str: ...

    def task_status(self, task_id: str) -> dict[str, Any] | None:
        """``{id, status, claimed_by, version, lease_until, dependencies: [{id, status}]}`` or ``None``."""
        ...

    def list_tasks(self) -> list[dict[str, Any]]:
        """``[{id, status, claimed_by, version, lease_until}]`` for every task (verification read)."""
        ...

    # -- lineage -------------------------------------------------------------------------------------------
    def why(self, node_id: str) -> dict[str, Any]:
        """Explain a Decision or Fact: ``{root, kind, facts: [{id, value, asserted_by, sources}], ...}``."""
        ...

    def knew_at(self, agent_id: str, step_n: int) -> dict[str, Any]:
        """``{agent_id, step_n, at, facts: [{fact_id, ...}], wrote: [...]}``: what the agent knew at step n."""
        ...

    def as_of(self, subject: str, predicate: str, t: int, scope: str = "global") -> dict[str, Any] | None:
        """The fact valid at ``t``: ``{fact_id, value, valid_from, valid_to, also_valid: [...]}`` or ``None``."""
        ...

    def close(self) -> None: ...


CAPABILITIES = (
    "why",
    "knew_at",
    "as_of",
    "semantic_dedupe",
    "contradictions",
    "forget_cascade",
    "dependencies",
)


def valid_tenant(tenant: str) -> str:
    """The shared tenant-name rule (identical to ``plexus.graph.tenancy``): no case folding, no separators."""
    import re

    if not isinstance(tenant, str) or re.fullmatch(r"[a-z0-9_]{1,48}", tenant) is None:
        raise InvalidTenant(f"invalid tenant {tenant!r}: must match ^[a-z0-9_]{{1,48}}$")
    return tenant
