"""Recall re-ranking: the D-012 multiplier plus pattern separation (D-013 P1).

Pure function over the candidate rows of ``engram/recall``, the activations of those facts and the entities
the query resolved to; no database.

``final = relevance * (floor + (1 - floor) * sigmoid(A - A0))``, protected facts use ``max(A, A0)``; with
pattern separation on, ``final`` is also multiplied by ``exp(sep)``. ``sep`` is the context term
(:mod:`plexus.activation.score`): the entity cue (the query names the fact's entity) and the predicate cue
(the query names the fact's predicate), each ``w * max(0, S - ln fan)``, summed.
With forgetting off the multiplier is 1 (relevance and separation only); with separation off ``sep`` is zero
and no lures are reported. Both off = the plain vector/keyword order.
"""

from __future__ import annotations

import math
import re
from collections.abc import Collection, Iterable, Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from plexus.activation import model
from plexus.activation import score as S
from plexus.activation.service import FactActivation
from plexus.activation.settings import Settings

_WORD = re.compile(r"[^\W_]+", re.UNICODE)
LURE_GAP = (
    0.02  # two candidates with the same predicate, different entities and relevance within this are lures
)


@dataclass(frozen=True)
class Ranked:
    """One candidate: ``final`` is what the order is by (higher first)."""

    row: dict[str, Any]
    relevance: float
    multiplier: float  # the D-012 multiplier (1 with forgetting off)
    final: float
    activation: float | None  # None when the fact has no activation record
    protected: bool
    bypassed: bool  # exact keyword match: multiplier 1
    sep: float = 0.0  # the context (pattern-separation) term: entity cue + predicate cue, >= 0
    ent_match: bool = False
    fan: int = 0
    pred_match: bool = False  # the query names this fact's predicate
    pred_fan: int = 0  # current facts with that predicate in the searched scopes
    lures: tuple[str, ...] = ()


def _contains_every(value: str, words: Iterable[str]) -> bool:
    have = {w.casefold() for w in _WORD.findall(value)}
    return all(w in have for w in words)


def _bypass_text(r: Mapping[str, Any]) -> str:
    return f"{r.get('entity_name') or ''} {r.get('predicate') or ''}: {r.get('value') or ''}"


def lures_of(
    rows: Sequence[Mapping[str, Any]], rels: Sequence[float], gap: float = LURE_GAP
) -> list[tuple[str, ...]]:
    """Per row: ids of other candidates with the same predicate, another entity, relevance within ``gap``."""
    out: list[tuple[str, ...]] = []
    for i, r in enumerate(rows):
        ids = [
            g["fact_id"]
            for j, g in enumerate(rows)
            if j != i
            and g.get("predicate") == r.get("predicate")
            and g.get("entity_id") != r.get("entity_id")
            and abs(rels[i] - rels[j]) < gap
        ]
        out.append(tuple(sorted(ids)))
    return out


def rerank(
    rows: Sequence[dict[str, Any]],
    acts: Mapping[str, FactActivation],
    *,
    settings: Settings,
    k: int,
    kw_ids: Collection[str] = (),
    words: Sequence[str] = (),
    entities: Mapping[str, int] | None = None,
    predicates: Mapping[str, int] | None = None,
    forgetting: bool | None = None,
    separation: bool | None = None,
) -> list[Ranked]:
    """Score the candidates and keep the best ``k``.

    ``relevance`` = ``1 - rank`` (``rank`` is the cosine distance after the sibling boost), clamped to [0, 1].
    ``entities`` maps the ids of the entities the query names to their fan (current facts about them);
    ``predicates`` maps the predicates the query names to their fan (current facts with that predicate in
    the searched scopes). Both are cues of the context term (:func:`plexus.activation.score.context_term`).
    A fact that is a full-text keyword hit **and** whose text (``entity predicate: value``) contains every
    query keyword (``words``) is exempt from the use-history multiplier.
    ``forgetting`` / ``separation`` default to the settings. Order: ``final`` descending, then vector rank,
    then id, so the result never depends on the input order.
    """
    fg = settings.forgetting if forgetting is None else forgetting
    sp = settings.separation if separation is None else separation
    ents = entities or {}
    preds = predicates or {}
    a0 = settings.neutral
    rels = [min(1.0, max(0.0, 1.0 - float(r["rank"]))) for r in rows]
    lures = lures_of(rows, rels) if sp else [()] * len(rows)
    scored: list[Ranked] = []
    for i, r in enumerate(rows):
        rel = rels[i]
        fa = acts.get(r["fact_id"])
        a = fa.activation if fa is not None else float("-inf")
        protected = bool(fa and fa.protected)
        bypass = bool(words) and r["fact_id"] in kw_ids and _contains_every(_bypass_text(r), words)
        ent_match = sp and r.get("entity_id") in ents
        fan = int(ents.get(r.get("entity_id"), 0)) if ent_match else 0
        pred_match = sp and r.get("predicate") in preds
        pred_fan = int(preds.get(str(r.get("predicate")), 0)) if pred_match else 0
        sep = (
            S.context_term(
                ent_match,
                fan,
                pred_match,
                pred_fan,
                w_entity=settings.w_entity,
                w_predicate=settings.w_predicate,
                s=settings.cue_s,
            )
            if sp
            else 0.0
        )
        mult = model.multiplier(a, a0, settings.floor, protected=protected, bypass=bypass) if fg else 1.0
        final = rel * mult
        if sep:
            final *= math.exp(sep)
        scored.append(
            Ranked(
                row=r,
                relevance=rel,
                multiplier=mult,
                final=final,
                activation=None if fa is None else a,
                protected=protected,
                bypassed=bypass,
                sep=sep,
                ent_match=ent_match,
                fan=fan,
                pred_match=pred_match,
                pred_fan=pred_fan,
                lures=lures[i],
            )
        )
    scored.sort(key=lambda s: (-s.final, s.row["rank"], s.row["fact_id"]))
    return scored[:k]
