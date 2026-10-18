"""Engram errors. All derive from :class:`EngramError`."""

from __future__ import annotations


class EngramError(Exception):
    """Base class for Engram failures."""


class UnknownReference(EngramError, LookupError):
    """A scope, episode or source id does not exist, so nothing was written.

    Also a ``LookupError``: ``assert_fact`` raised a bare ``LookupError`` for an unknown scope before.
    """

    def __init__(self, kind: str, ids: list[str]):
        self.kind = kind
        self.ids = ids
        super().__init__(f"unknown {kind} id(s): {', '.join(ids)}")
