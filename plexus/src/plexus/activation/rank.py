"""Recall re-ranking (D-012): rank by relevance x (floor + (1 - floor) * sigmoid(A - A0)).

Pure function over the candidate rows of ``engram/recall`` and the activations of those facts; no database.
"""

from __future__ import annotations

import re
from collections.abc import Collection, Iterable, Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from plexus.activation import model
from plexus.activation.service import FactActivation
from plexus.activation.settings import Settings

_WORD = re.compile(r"[^\W_]+", re.UNICODE)


@dataclass(frozen=True)
class Ranked:
    """One candidate after scoring: ``final = relevance * multiplier``."""

    row: dict[str, Any]
    relevance: float
    multiplier: float
    final: float
    activation: float | None  # None when the fact has no activation record
    protected: bool
    bypassed: bool  # exact keyword match: the multiplier is 1


def _contains_every(value: str, words: Iterable[str]) -> bool:
    have = {w.casefold() for w in _WORD.findall(value)}
    return all(w in have for w in words)


def rerank(
    rows: Sequence[dict[str, Any]],
    acts: Mapping[str, FactActivation],
    *,
    settings: Settings,
    k: int,
    kw_ids: Collection[str] = (),
    words: Sequence[str] = (),
) -> list[Ranked]:
    """Score the candidates and keep the best ``k``.

    ``relevance`` = the row's ``fused`` score when it has one (P12: hybrid of the vector and keyword channels,
    ``plexus.engram.service.fuse_scores``), else ``1 - rank`` (``rank`` is the cosine distance after the
    sibling boost); clamped to [0, 1]. The multiplier is ``floor + (1 - floor) * sigmoid(A - A0)``; protected
    facts use ``max(A, A0)``. A fact that is a full-text keyword hit **and** whose text (entity name,
    predicate and value; the value only before P12) contains every query keyword (``words``) is exempt (1.0).
    Order: ``final`` descending, then vector rank, then id, so the result never depends on the input order.
    """
    a0 = settings.neutral
    scored: list[Ranked] = []
    for r in rows:
        fa = acts.get(r["fact_id"])
        a = fa.activation if fa is not None else float("-inf")
        protected = bool(fa and fa.protected)
        text = " ".join(str(r.get(x) or "") for x in ("entity_name", "predicate", "value"))
        bypass = bool(words) and r["fact_id"] in kw_ids and _contains_every(text, words)
        mult = model.multiplier(a, a0, settings.floor, protected=protected, bypass=bypass)
        raw = r["fused"] if r.get("fused") is not None else 1.0 - float(r["rank"])
        rel = min(1.0, max(0.0, float(raw)))
        scored.append(
            Ranked(
                row=r,
                relevance=rel,
                multiplier=mult,
                final=rel * mult,
                activation=None if fa is None else a,
                protected=protected,
                bypassed=bypass,
            )
        )
    scored.sort(key=lambda s: (-s.final, s.row["rank"], s.row["fact_id"]))
    return scored[:k]
