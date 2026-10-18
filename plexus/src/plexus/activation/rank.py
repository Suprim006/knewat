"""Recall re-ranking: D-012 multiplier (``mult``) or D-013 additive banded score (``add``), plus pattern
separation.

Pure function over the candidate rows of ``engram/recall``, the activations of those facts and the entities
the query resolved to; no database.

``mult`` (PLEXUS_ACT_MODE=mult, the D-012 rule): ``final = relevance * (floor + (1 - floor) * sigmoid(A -
A0))``, protected facts use ``max(A, A0)``; with pattern separation on, ``final`` is also multiplied by
``exp(sep)``.
``add`` (D-013): ``score = ln(rel) + act + sep + sal`` from :mod:`plexus.activation.score`.
``sep`` is the context term (CROSS_CHECK §3.2): the entity cue (the query names the fact's entity) and the
predicate cue (the query names the fact's predicate), each ``w * max(0, S - ln fan)``, summed; or, with
``Settings.cues = "entity"``, the single damped entity term P1 first shipped.
With forgetting off the activation and salience terms are zero (relevance and separation only); with
separation off ``sep`` is zero and no lures are reported. Both off = the plain vector/keyword order.
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
    """One candidate: ``final`` is what the order is by (higher first), ``score = ln(final)``."""

    row: dict[str, Any]
    relevance: float
    multiplier: float  # mult mode: the D-012 multiplier; add mode: exp(act + sal) (1 with forgetting off)
    final: float
    activation: float | None  # None when the fact has no activation record
    protected: bool
    bypassed: bool  # exact keyword match: no use-history / salience term
    score: float = 0.0  # ln(final); -inf for a zero relevance in add mode
    act: float = 0.0  # the activation term (add mode) in (-beta, beta)
    sep: float = 0.0  # the context (pattern-separation) term: entity cue + predicate cue, >= 0
    sal: float = 0.0  # the salience term (add mode)
    ent_match: bool = False
    fan: int = 0
    pred_match: bool = False  # the query names this fact's predicate
    pred_fan: int = 0  # current facts with that predicate in the searched scopes
    salience: float = 0.0
    in_band: bool = True
    lures: tuple[str, ...] = ()


def _contains_every(value: str, words: Iterable[str]) -> bool:
    have = {w.casefold() for w in _WORD.findall(value)}
    return all(w in have for w in words)


def _bypass_text(r: Mapping[str, Any], kind: str) -> str:
    if kind == "value":
        return str(r.get("value") or "")
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
    A fact that is a full-text keyword hit **and** whose text (``PLEXUS_KW_BYPASS``: the whole fact text, or
    the value alone) contains every query keyword (``words``) is exempt from the use-history and salience
    terms.
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
    rel_top = max(rels, default=0.0)
    bands = [rel >= rel_top - settings.band for rel in rels]
    sals = [acts[r["fact_id"]].salience if r["fact_id"] in acts else 0.0 for r in rows]
    s_max_band = max((s for s, b in zip(sals, bands, strict=True) if b), default=0.0)
    scored: list[Ranked] = []
    for i, r in enumerate(rows):
        rel = rels[i]
        fa = acts.get(r["fact_id"])
        a = fa.activation if fa is not None else float("-inf")
        protected = bool(fa and fa.protected)
        bypass = (
            bool(words)
            and r["fact_id"] in kw_ids
            and _contains_every(_bypass_text(r, settings.kw_bypass), words)
        )
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
                cues=settings.cues,
                gamma=settings.gamma,
                s_max=settings.s_max,
                w_entity=settings.w_entity,
                w_predicate=settings.w_predicate,
                s=settings.cue_s,
            )
            if sp
            else 0.0
        )
        if not settings.additive:
            mult = model.multiplier(a, a0, settings.floor, protected=protected, bypass=bypass) if fg else 1.0
            final = rel * mult
            if sep:
                final *= math.exp(sep)
            act = math.log(mult) if mult > 0 else float("-inf")
            sal = 0.0
            sc = math.log(final) if final > 0 else float("-inf")
        else:
            # score.score() is the one formula; `act` / `sal` below are its reported components (the same
            # helpers), not a second computation. Forgetting off = the bypass form (ln rel + sep).
            sc = S.score(
                rel,
                A=a,
                A0=a0,
                s_noise=settings.s_noise,
                beta=settings.beta,
                ent_match=ent_match,
                fan=fan,
                S_max=settings.s_max,
                gamma=settings.gamma,
                salience=sals[i],
                in_band=bands[i],
                s_max_band=s_max_band,
                delta=settings.delta,
                bypass=bypass or not fg,
                pred_match=pred_match,
                pred_fan=pred_fan,
                cues=settings.cues,
                w_entity=settings.w_entity,
                w_predicate=settings.w_predicate,
                S=settings.cue_s,
            )
            act = (
                S.act_term(a, a0, beta=settings.beta, s_noise=settings.s_noise) if fg and not bypass else 0.0
            )
            sal = (
                S.sal_term(sals[i], in_band=bands[i], s_max_band=s_max_band, delta=settings.delta)
                if fg and not bypass
                else 0.0
            )
            mult = math.exp(act + sal)
            final = math.exp(sc) if sc != float("-inf") else 0.0
        scored.append(
            Ranked(
                row=r,
                relevance=rel,
                multiplier=mult,
                final=final,
                activation=None if fa is None else a,
                protected=protected,
                bypassed=bypass,
                score=sc,
                act=act,
                sep=sep,
                sal=sal,
                ent_match=ent_match,
                fan=fan,
                pred_match=pred_match,
                pred_fan=pred_fan,
                salience=sals[i],
                in_band=bands[i],
                lures=lures[i],
            )
        )
    if settings.additive:
        scored.sort(key=lambda s: (-s.score, s.row["rank"], s.row["fact_id"]))
    else:
        scored.sort(key=lambda s: (-s.final, s.row["rank"], s.row["fact_id"]))
    return scored[:k]
