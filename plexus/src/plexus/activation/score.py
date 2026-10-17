"""D-013 scoring: one function, four bounded additive axes on top of ln-relevance (pure, no database).

``score = ln(rel) + act + sep + sal + rel_term`` where every term is bounded, so the relevance order is kept
except among near-ties (docs/research/MEMORY_FORGETTING_IMPLEMENTATION_PLAN.md §1, note 01 §3.1):

* ``act = beta * tanh((A - A0) / (2 s))`` in ``(-beta, beta)``: use history decides ties, nothing else (P2);
* ``sep = gamma * ent_match * max(0, 1 - ln(fan) / S_max)``: the query names this fact's entity, damped by the
  entity's fan (ACT-R ``S - ln(fan)``); zero for hub entities with >= e^S_max facts (P1);
* ``sal = delta * salience`` inside the relevance band, ``-delta * s_max_band`` outside it when the band holds
  something critical (``s_max_band >= 0.8``), else 0: arousal-biased competition (P2, note 05 §3.4);
* ``rel_term = rho * ln(reliability / 0.67)``: 0 at the prior; P3, not wired yet (``reliability`` defaults to
  the prior).

A full exact-keyword match (``bypass``) keeps only ``ln(rel) + sep``: an exact lexical hit is never penalised
by use history or salience, but it still gets the entity lift it earned (the plan's "relevance only" would
strip the P1 term from the very rows P1 is for; see docs/DECISIONS.md D-013).
"""

from __future__ import annotations

import math

NEG_INF = float("-inf")
RELIABILITY_PRIOR = 2.0 / 3.0  # Beta(2, 1) mean; P3


def sep_term(ent_match: bool, fan: int, *, gamma: float, s_max: float) -> float:
    """The pattern-separation lift ``gamma * max(0, 1 - ln(max(fan, 1)) / S_max)`` when the entity matched."""
    if not ent_match:
        return 0.0
    return gamma * max(0.0, 1.0 - math.log(max(fan, 1)) / s_max)


def act_term(a: float, a0: float, *, beta: float, s_noise: float) -> float:
    """``beta * tanh((A - A0) / (2 s))``; an unknown activation (``-inf``) is the full penalty ``-beta``."""
    if a == NEG_INF:
        return -beta
    return beta * math.tanh((a - a0) / (2.0 * s_noise))


def sal_term(salience: float, *, in_band: bool, s_max_band: float, delta: float) -> float:
    """``+delta * salience`` in the band; ``-delta * s_max_band`` outside it when the band is critical."""
    if in_band:
        return delta * salience
    return -delta * s_max_band if s_max_band >= 0.8 else 0.0


def score(
    rel: float,
    *,
    A: float,
    A0: float,
    s_noise: float,
    beta: float,
    ent_match: bool,
    fan: int,
    S_max: float,
    gamma: float,
    salience: float,
    in_band: bool,
    s_max_band: float,
    delta: float,
    reliability: float = RELIABILITY_PRIOR,
    rho: float = 0.0,
    bypass: bool = False,
) -> float:
    """ln-relevance plus the bounded additive terms. Returns ``-inf`` for ``rel <= 0``."""
    if rel <= 0:
        return NEG_INF
    base = math.log(min(rel, 1.0))
    sep = sep_term(ent_match, fan, gamma=gamma, s_max=S_max)
    if bypass:  # exact match of every query word in the fact text: no use-history or salience term
        return base + sep
    act = act_term(A, A0, beta=beta, s_noise=s_noise)
    sal = sal_term(salience, in_band=in_band, s_max_band=s_max_band, delta=delta)
    rel_term = rho * math.log(max(reliability, 1e-3) / RELIABILITY_PRIOR)
    return base + act + sep + sal + rel_term
