"""Small shared helpers: clocks, file locks, fact classification, text scoring, percentiles."""

from __future__ import annotations

import contextlib
import os
import re
import sys
import time
import uuid
from collections.abc import Callable, Iterator, Sequence
from typing import Any

from plexus.engram.service import fact_text, normalize, token_key  # same text rules as Plexus

__all__ = [
    "FileLock",
    "classify",
    "fact_text",
    "fmt_ms",
    "iso_utc",
    "keyword_score",
    "new_id",
    "normalize",
    "now_ms",
    "percentile",
    "run_stamp",
    "scope_chain",
    "token_key",
    "words",
]

_WORD = re.compile(r"[^\W_]+", re.UNICODE)


def now_ms() -> int:
    return time.time_ns() // 1_000_000


def new_id() -> str:
    return str(uuid.uuid4())


def iso_utc(ts: float | None = None) -> str:
    """``2026-10-14T21:36:03Z`` for the epoch time ``ts`` (now when omitted)."""
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(ts))


def run_stamp(ts: float | None = None) -> str:
    """``20261014T213603Z``: the UTC timestamp that prefixes result directories and run ids."""
    return time.strftime("%Y%m%dT%H%M%SZ", time.gmtime(ts))


def fmt_ms(ms: float) -> str:
    return f"{ms:.1f} ms" if ms < 1000 else f"{ms / 1000:.2f} s"


def words(text: str) -> list[str]:
    return [w.casefold() for w in _WORD.findall(text)]


def scope_chain(scope: str) -> list[str]:
    """Scopes whose facts are visible from ``scope``: itself, then ``global`` (project/user inherit global)."""
    scope = (scope or "global").strip()
    kind, _, name = scope.partition(":")
    if scope == "global":
        return ["global"]
    if kind in ("project", "user") and name.strip():
        return [scope, "global"]
    raise ValueError(f"invalid scope '{scope}': use 'global', 'project:<name>' or 'user:<name>'")


def keyword_score(query_words: Sequence[str], text: str) -> float:
    """Fraction of distinct query words present in ``text`` (0..1). Used by the file arm (grep-like recall)."""
    qs = set(query_words)
    if not qs:
        return 0.0
    return len(qs & set(words(text))) / len(qs)


def classify(
    cur: Sequence[dict[str, Any]],
    agent_id: str,
    norm_value: str,
    supersede: bool,
    now: int,
    is_dup: Callable[[dict[str, Any]], bool] | None = None,
) -> tuple[dict[str, Any] | None, list[dict[str, Any]], list[dict[str, Any]], int]:
    """The assertion rules of ``engram/assert_fact`` on the *current* facts of one (entity, predicate, scope).

    Each fact is a dict with ``id``, ``norm_value``, ``asserted_by`` (agent ids) and ``valid_from``. Returns
    ``(dup, closing, clashing, ts)``: the existing duplicate (or None), the facts this assertion supersedes,
    the facts it contradicts, and the effective change time ``max(now, valid_from of every closing fact)``.
    """
    dup = next((f for f in cur if f["norm_value"] == norm_value), None)
    if dup is None and is_dup is not None:
        dup = next((f for f in cur if is_dup(f)), None)

    def own(f: dict[str, Any]) -> bool:
        return supersede or all(a == agent_id for a in f["asserted_by"])

    closing = [f for f in cur if (dup is None or f["id"] != dup["id"]) and own(f)]
    ts = max([now, *(f["valid_from"] for f in closing)])
    clashing = [] if dup is not None else [f for f in cur if not own(f)]
    return dup, closing, clashing, ts


def percentile(values: Sequence[float], p: float) -> float:
    """Nearest-rank percentile (``p`` in 0..100); 0.0 for an empty list."""
    if not values:
        return 0.0
    s = sorted(values)
    rank = max(1, min(len(s), int(-(-p / 100.0 * len(s) // 1))))
    return s[rank - 1]


# -- inter-process file lock ------------------------------------------------------------------------------


class FileLock:
    """Exclusive advisory lock on a lock file. Works across threads *and* processes, and is released by the OS
    when the holder dies (so a SIGKILLed claimer cannot wedge the others).

    POSIX: ``flock`` (blocking, so waiters sleep in the kernel). Windows: ``msvcrt.locking`` on byte 0, polled.
    Each ``with`` opens its own descriptor, so two threads of one process exclude each other too.
    """

    def __init__(self, path: str | os.PathLike[str]):
        self.path = os.fspath(path)

    @contextlib.contextmanager
    def hold(self) -> Iterator[None]:
        fd = os.open(self.path, os.O_RDWR | os.O_CREAT, 0o644)
        try:
            _lock(fd)
            try:
                yield
            finally:
                _unlock(fd)
        finally:
            os.close(fd)


if sys.platform == "win32":  # pragma: no cover - exercised on the dev machine only
    import msvcrt

    def _lock(fd: int) -> None:
        delay = 0.0005
        while True:
            try:
                os.lseek(fd, 0, os.SEEK_SET)
                msvcrt.locking(fd, msvcrt.LK_NBLCK, 1)
                return
            except OSError:
                time.sleep(delay)
                delay = min(delay * 1.5, 0.01)

    def _unlock(fd: int) -> None:
        os.lseek(fd, 0, os.SEEK_SET)
        msvcrt.locking(fd, msvcrt.LK_UNLCK, 1)

else:
    import fcntl

    def _lock(fd: int) -> None:
        fcntl.flock(fd, fcntl.LOCK_EX)

    def _unlock(fd: int) -> None:
        fcntl.flock(fd, fcntl.LOCK_UN)
