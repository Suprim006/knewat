"""Helpers shared by the file, SQLite and Plexus arms: argument checks and result shaping that are identical.

Only logic that is the same in every arm lives here; anything storage-specific stays in the backend. These helpers
never read the clock or mint ids themselves: callers pass ``now_ms`` / ``new_id`` in. That matters because the L2
scenario player (``l2.scenario.deterministic``) swaps ``new_id`` / ``now_ms`` in each *backend module's* namespace
to make the stores byte-reproducible, and a call made from inside this module would bypass that patch.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from plexus.crucible.api import ClaimConflict, UnknownReference
from plexus.crucible.util import normalize, scope_chain, words

MAX_BASED_ON = 100  # a decision may reference at most this many facts
MAX_RECALL_K = 50
MAX_QUERY_WORDS = 10
TASK_LIST_KEYS = (
    "id",
    "status",
    "claimed_by",
    "version",
    "lease_until",
)  # what ``list_tasks`` reports per task
ARTIFACT_FIELDS = ("kind", "uri", "hash", "summary")


# -- argument checks ------------------------------------------------------------------------------------------


def check_lease(lease_ms: int) -> None:
    if lease_ms <= 0:
        raise ValueError("lease_ms must be positive")


def check_source_uri(uri: str) -> None:
    if not uri.strip():
        raise ValueError("source uri must not be empty")


def unique(ids: Iterable[str]) -> list[str]:
    """``ids`` without duplicates, first occurrence kept."""
    return list(dict.fromkeys(ids))


def decision_facts(based_on_fact_ids: Iterable[str]) -> list[str]:
    facts = unique(based_on_fact_ids)
    if len(facts) > MAX_BASED_ON:
        raise ValueError(f"at most {MAX_BASED_ON} referenced ids")
    return facts


# -- assert_fact ------------------------------------------------------------------------------------------------


@dataclass(frozen=True)
class Assertion:
    """The validated, normalised arguments of one ``assert_fact`` call."""

    entity: str
    predicate: str
    norm_value: str
    t: int  # recorded_at
    origins: list[str]  # source id (if any) followed by the facts it is derived from, without duplicates


def prepare_assertion(
    subject: str,
    predicate: str,
    value: str,
    scope: str,
    source_id: str | None,
    derived_from: Sequence[str],
    now: int | None,
    now_ms: Callable[[], int],
) -> Assertion:
    entity, pred, norm_value = normalize(subject), normalize(predicate), normalize(value)
    if not entity or not pred or not norm_value:
        raise ValueError("subject, predicate and value must not be empty")
    scope_chain(scope)  # validates the scope spec
    t = now if now is not None else now_ms()
    origins = unique([*([source_id] if source_id else []), *derived_from])
    return Assertion(entity, pred, norm_value, t, origins)


def assert_result(
    fact_id: str,
    duplicate_of: str | None,
    closing: Sequence[Mapping[str, Any]],
    clashing: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    """The ``assert_fact`` return value: ``closing`` facts were superseded, ``clashing`` ones contradict."""
    return {
        "fact_id": fact_id,
        "duplicate_of": duplicate_of,
        "superseded": [f["id"] for f in closing],
        "contradicts": [f["id"] for f in clashing],
    }


# -- recall -----------------------------------------------------------------------------------------------------


def query_words(query: str) -> list[str]:
    """Distinct lower-cased words of at least two letters, first ten (what the keyword/BM25 recall matches on)."""
    return list(dict.fromkeys(w for w in words(query) if len(w) >= 2))[:MAX_QUERY_WORDS]


def recall_hit(
    fact_id: str, text: str, entity: str, predicate: str, value: str, status: str, score: float
) -> dict[str, Any]:
    return {
        "fact_id": fact_id,
        "text": text,
        "entity": entity,
        "predicate": predicate,
        "value": value,
        "status": status,
        "score": score,
    }


# -- tasks ------------------------------------------------------------------------------------------------------


def new_task_ids(tasks: Sequence[Mapping[str, Any]], new_id: Callable[[], str]) -> list[str]:
    """Ids for a batch of ``create_tasks`` specs (given or minted); rejects a batch that repeats an id."""
    ids = [str(t.get("id") or new_id()) for t in tasks]
    if len(set(ids)) != len(ids):
        raise ValueError("duplicate task id in batch")
    return ids


def task_deps(task: Mapping[str, Any]) -> list[str]:
    """The task's ``depends_on`` as distinct strings, in order."""
    return unique(str(d) for d in (task.get("depends_on") or ()))


def external_deps(tasks: Sequence[Mapping[str, Any]], ids: Sequence[str]) -> list[str]:
    """Sorted dependency ids that the batch refers to but does not itself create (they must already exist)."""
    own = set(ids)
    return sorted({str(d) for t in tasks for d in (t.get("depends_on") or ()) if str(d) not in own})


def raise_missing_deps(missing: Sequence[str]) -> None:
    if missing:
        raise UnknownReference(f"unknown dependency task id(s): {', '.join(missing)}")


def claim_result(
    task: Mapping[str, Any], version: int, lease_until: int, reclaimed_from: str
) -> dict[str, Any]:
    """What ``claim_next_task`` returns; ``version`` is the post-claim version, ``task`` supplies id/title/priority."""
    return {
        "id": task["id"],
        "title": task["title"],
        "priority": task["priority"],
        "version": version,
        "lease_until": lease_until,
        "reclaimed_from": reclaimed_from,
    }


def artifact_specs(artifacts: Iterable[Mapping[str, Any]], new_id: Callable[[], str]) -> list[dict[str, Any]]:
    """Normalise the artifacts handed to ``complete_task``: an id (given or minted) and four string fields."""
    return [
        {
            "id": str(a.get("id") or new_id()),
            **{k: str(a.get(k) or "") for k in ARTIFACT_FIELDS},
        }
        for a in artifacts
    ]


def check_completable(
    task_id: str, agent_id: str, expected_version: int, task: Mapping[str, Any] | None
) -> None:
    """Raise unless ``agent_id`` holds ``task_id`` at ``expected_version`` (``task`` has status/claimed_by/version)."""
    if task is None:
        raise UnknownReference(f"unknown task id(s): {task_id}")
    if task["status"] != "claimed":
        raise ClaimConflict(f"task {task_id}: not claimed (status is {task['status']})")
    if task["claimed_by"] != agent_id:
        raise ClaimConflict(f"task {task_id}: claimed by {task['claimed_by']}, not {agent_id}")
    if task["version"] != expected_version:
        raise ClaimConflict(f"task {task_id}: stale version {expected_version}; current is {task['version']}")


def complete_result(task_id: str, expected_version: int, arts: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    return {
        "id": task_id,
        "status": "done",
        "version": expected_version + 1,
        "artifact_ids": [a["id"] for a in arts],
    }


def task_status_view(task: Mapping[str, Any], dependencies: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    """The ``task_status`` return value; ``dependencies`` are ``{id, status}`` rows."""
    return {
        "id": task["id"],
        "title": task["title"],
        "status": task["status"],
        "claimed_by": task["claimed_by"],
        "version": task["version"],
        "lease_until": task["lease_until"],
        "dependencies": [{"id": d["id"], "status": d["status"]} for d in dependencies],
    }


def list_row(task: Mapping[str, Any]) -> dict[str, Any]:
    return {k: task[k] for k in TASK_LIST_KEYS}
