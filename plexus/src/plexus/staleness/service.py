"""Staleness service: wrappers around the named queries in ``queries/staleness/``.

A code change never makes a fact false, it makes it *suspect* (``verify_state = 'suspect'``); an agent
re-checks it and calls :meth:`Staleness.verify_fact`. Every write is ONE bounded Cypher statement; reads use
``ro``. Time is epoch ms (``clock`` / ``now`` are injectable for tests). No LLM anywhere.
"""

from __future__ import annotations

import time
from collections.abc import Callable
from typing import Any

from plexus.codescan.paths import anchor_id, canonical_path
from plexus.engram import Engram
from plexus.graph.client import GraphClient

KINDS = ("file", "function", "class")


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
