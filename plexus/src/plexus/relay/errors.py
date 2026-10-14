"""Relay errors. All derive from :class:`RelayError`."""

from __future__ import annotations


class RelayError(Exception):
    """Base class for Relay failures."""


class InvalidDag(RelayError, ValueError):
    """The submitted task batch is malformed: duplicate ids, cycle, self-dependency, too many tasks."""


class DuplicateTask(RelayError):
    """A task id in the batch already exists in the graph."""

    def __init__(self, ids: list[str]):
        self.ids = ids
        super().__init__(f"task id(s) already exist: {', '.join(ids)}")


class UnknownReference(RelayError):
    """An id (task, agent, fact, artifact, dependency) does not exist, so nothing was written."""

    def __init__(self, kind: str, ids: list[str]):
        self.kind = kind
        self.ids = ids
        super().__init__(f"unknown {kind} id(s): {', '.join(ids)}")


class ClaimConflict(RelayError):
    """complete/fail rejected: the caller no longer owns the task at that version (stale CAS)."""

    def __init__(self, task_id: str, reason: str):
        self.task_id = task_id
        self.reason = reason
        super().__init__(f"task {task_id}: {reason}")
