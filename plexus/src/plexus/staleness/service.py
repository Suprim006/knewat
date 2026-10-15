"""Staleness service: wrappers around the named queries in ``queries/staleness/``.

A code change never makes a fact false, it makes it *suspect* (``verify_state = 'suspect'``); an agent
re-checks it and calls :meth:`Staleness.verify_fact`. Every write is ONE bounded Cypher statement; reads use
``ro``. Time is epoch ms (``clock`` / ``now`` are injectable for tests). No LLM anywhere.
"""

from __future__ import annotations

import hashlib
import time
from collections.abc import Callable, Sequence
from typing import Any

from plexus.codescan.paths import anchor_id, canonical_path
from plexus.engram import Engram
from plexus.graph.client import GraphClient

KINDS = ("file", "function", "class")
MAX_CHANGES = 200  # entries per mark_changed call (bounds the UNWIND of the write)
MAX_AFFECTED = 2000  # facts made suspect per mark_changed call
DEFAULT_DETAIL = 50  # decisions listed per call (the total is exact)


def _now_ms() -> int:
    return time.time_ns() // 1_000_000


class Staleness:
    """Staleness operations bound to one tenant graph."""

    def __init__(
        self,
        client: GraphClient,
        graph: str,
        *,
        engram: Engram | None = None,
        clock: Callable[[], int] = _now_ms,
    ):
        self.client = client
        self.graph = graph
        self._engram = engram
        self._clock = clock

    def _t(self, now: int | None) -> int:
        return self._clock() if now is None else int(now)

    # -- anchors and descriptions ---------------------------------------------------------------------
    def _upsert_anchor(
        self,
        path: str,
        symbol: str,
        hash: str,
        kind: str,
        repo: str,
        *,
        fact_id: str = "",
        source_id: str = "",
        now: int | None,
    ) -> dict[str, Any] | None:
        cpath = canonical_path(path)
        symbol = symbol.strip()
        kind = kind or ("function" if symbol else "file")
        if kind not in KINDS:
            raise ValueError(f"kind must be one of {', '.join(KINDS)}")
        if (kind == "file") != (symbol == ""):
            raise ValueError("a file anchor has no symbol; a function / class anchor needs one")
        rows = self.client.rw(
            self.graph,
            "staleness/upsert_anchor",
            {
                "anchor_id": anchor_id(cpath, symbol),
                "repo": repo,
                "path": cpath,
                "symbol": symbol,
                "kind": kind,
                "hash": hash,
                "fact_id": fact_id,
                "source_id": source_id,
                "now": self._t(now),
            },
        )
        if not rows:
            return None
        r = rows[0]
        return {"anchor_id": r["anchor_id"], "path": cpath, "symbol": symbol, "kind": kind, "hash": r["hash"]}

    def anchor_fact(
        self,
        fact_id: str,
        path: str,
        symbol: str = "",
        hash: str = "",
        *,
        kind: str = "",
        repo: str = "",
        now: int | None = None,
    ) -> dict[str, Any]:
        """Link a Fact to a file (``symbol=''``) or a Python function / class (``ANCHORED_TO`` a CodeAnchor).

        ``path`` is normalised to the canonical form (absolute, ``/``, upper-case drive). ``hash`` is the code
        hash the fact was verified against; it is stored only when the anchor has none yet. Raises
        :class:`LookupError` (nothing written) for an unknown fact, :class:`ValueError` for a bad path / kind.
        """
        out = self._upsert_anchor(path, symbol, hash, kind, repo, fact_id=fact_id, now=now)
        if out is None:
            raise LookupError(f"no fact with id '{fact_id}'")
        return {"fact_id": fact_id, **out}

    def describe_code(
        self,
        source_id: str,
        path: str,
        symbol: str = "",
        hash: str = "",
        *,
        kind: str = "",
        repo: str = "",
        now: int | None = None,
    ) -> dict[str, Any]:
        """Record that a doc Source describes a file / function: ``(Source)-[:DESCRIBES]->(CodeAnchor)``.

        When the code changes, :meth:`docs_to_update` lists the doc. Raises :class:`LookupError` for an
        unknown source (nothing written).
        """
        out = self._upsert_anchor(path, symbol, hash, kind, repo, source_id=source_id, now=now)
        if out is None:
            raise LookupError(f"no source with id '{source_id}'")
        return {"source_id": source_id, **out}

    # -- changes --------------------------------------------------------------------------------------
    def mark_changed(
        self,
        changes: Sequence[dict[str, Any]],
        commit: str = "",
        at: int | None = None,
        agent_id: str = "code-hook",
        *,
        limit: int = MAX_AFFECTED,
        max_detail: int = DEFAULT_DETAIL,
        repo: str = "",
        now: int | None = None,
    ) -> dict[str, Any]:
        """Record code changes; the active facts that depend on a changed file / symbol become suspect.

        ``changes`` is ``[{path, symbol='', new_hash, old_hash='', kind?}]`` (at most 200). An entry is
        *changed* when the hash stored for its anchor (or, when none is stored yet, ``old_hash``) differs from
        ``new_hash``; a first sighting without ``old_hash`` is a baseline and marks nothing. ``new_hash=''``
        means the file / symbol is gone. A file-level change covers the symbol anchors of that file only when
        the batch has no symbol entries for it. Affected facts: those ``ANCHORED_TO`` a changed anchor, plus
        those ``DERIVED_FROM*1..5`` a ``Source`` whose uri is the changed (canonical) path. Only ``active``
        facts. Returns ``{change_id, at, changed, unchanged, suspect_fact_ids, decisions, decisions_total,
        docs_to_update, truncated}``. ``change_id`` is ``None`` when nothing changed (no Change is created).

        At most ``limit`` (<= 2000) facts are marked per call. When more are affected ``truncated`` is true
        and the hashes are not advanced: call again with the same arguments (including the returned ``at``) to
        continue with the same Change.
        """
        if not 0 < limit <= MAX_AFFECTED:
            raise ValueError(f"limit must be between 1 and {MAX_AFFECTED}")
        if not 0 < max_detail <= 5000:
            raise ValueError("max_detail must be between 1 and 5000")
        if len(changes) > MAX_CHANGES:
            raise ValueError(f"at most {MAX_CHANGES} changes per call")
        if not changes:
            raise ValueError("changes must not be empty")
        entries: dict[str, dict[str, Any]] = {}
        for ch in changes:
            cpath = canonical_path(ch["path"])
            symbol = (ch.get("symbol") or "").strip()
            kind = ch.get("kind") or ("function" if symbol else "file")
            if kind not in KINDS or (kind == "file") != (symbol == ""):
                raise ValueError(f"bad kind '{kind}' for symbol '{symbol}'")
            aid = anchor_id(cpath, symbol)
            entries[aid] = {  # the last entry for an anchor wins
                "anchor_id": aid,
                "path": cpath,
                "symbol": symbol,
                "kind": kind,
                "repo": ch.get("repo") or repo,
                "new_hash": ch.get("new_hash") or "",
                "old_hash": ch.get("old_hash") or "",
                "cover": False,
            }
        with_symbols = {e["path"] for e in entries.values() if e["symbol"]}
        for e in entries.values():
            e["cover"] = e["kind"] == "file" and e["path"] not in with_symbols
        rows = list(entries.values())
        t = self._t(at)
        change_id = (
            "chg:"
            + hashlib.sha1(  # noqa: S324
                "|".join(
                    [commit, str(t), *sorted(f"{e['anchor_id']}={e['new_hash']}" for e in rows)]
                ).encode()
            ).hexdigest()[:16]
        )
        res = self.client.rw(
            self.graph,
            "staleness/mark_changed",
            {
                "changes": rows,
                "paths": sorted({e["path"] for e in rows}),
                "change_id": change_id,
                "commit": commit,
                "at": t,
                "now": self._t(now),
                "agent_id": agent_id,
                "limit": limit,
                "limit_plus": limit + 1,
                "max_detail": max_detail,
            },
        )
        r = res[0]
        return {
            "change_id": r["change_id"],
            "at": t,
            "changed": r["changed"],
            "unchanged": len(rows) - r["changed"],
            "suspect_fact_ids": list(r["fact_ids"]),
            "decisions": [dict(d) for d in r["decisions"]],
            "decisions_total": r["decisions_total"],
            "docs_to_update": sorted((dict(d) for d in r["docs"]), key=lambda d: (d["uri"], d["anchor"])),
            "truncated": bool(r["truncated"]),
        }
