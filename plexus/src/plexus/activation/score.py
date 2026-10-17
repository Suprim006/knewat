"""D-013 scoring: one function, four bounded additive axes on top of ln-relevance (pure, no database).

``score = ln(rel) + act + sep + sal + rel_term`` where every term is bounded, so the relevance order is kept
except among near-ties (docs/research/MEMORY_FORGETTING_IMPLEMENTATION_PLAN.md §1, note 01 §3.1):

* ``act = beta * tanh((A - A0) / (2 s))`` in ``(-beta, beta)``: use history decides ties, nothing else (P2);
* ``sep`` = the context term, a sum over the cues the query carries (ACT-R ``C = sum_j W_j (S - ln fan_j)``,
  docs/research/neuro-memory/CROSS_CHECK.md §3.2): the **entity** cue (the query names this fact's entity,
  ``fan`` = that entity's current facts in the searched scopes) weighted ``w_entity``, plus the **predicate**
  cue (the query names this fact's predicate, ``pred_fan`` = current facts with that predicate in the searched
  scopes) weighted ``w_predicate``; each cue is ``w * max(0, S - ln fan)``, floored at 0 (a hub cue adds
  nothing, it never subtracts). With ``cues = "entity"`` the pre-§3.2 single-cue form
  ``gamma * max(0, 1 - ln(fan) / S_max)`` is used instead (P1 as first shipped; kept for the A/B runs);
* ``sal = delta * salience`` inside the relevance band, ``-delta * s_max_band`` outside it when the band holds
  something critical (``s_max_band >= 0.8``), else 0: arousal-biased competition (P2, note 05 §3.4);
* ``rel_term = rho * ln(reliability / 0.67)``: 0 at the prior; P3, not wired yet (``reliability`` defaults to
  the prior).

A full exact-keyword match (``bypass``) keeps only ``ln(rel) + sep``: an exact lexical hit is never penalised
by use history or salience, but it still gets the cue lift it earned (the plan's "relevance only" would
strip the P1 term from the very rows P1 is for; see docs/DECISIONS.md D-013).
"""

from __future__ import annotations

import math

NEG_INF = float("-inf")
RELIABILITY_PRIOR = 2.0 / 3.0  # Beta(2, 1) mean; P3
CUE_MODES = ("entity+predicate", "entity")
CUE_S_DEFAULT = 5.0  # ACT-R S: a cue with fan >= e^S (148) adds nothing
# CROSS_CHECK §3.2's 0.6 / 0.4 scaled by 1/20: the entity cue at fan 12 (0.075) then equals the P1 lift that
# cleared every cross-entity twin. The registered 0.6 / 0.4 kept recall and raised the noise share by 4-11
# points (docs/BASELINE.md "Predicate cue results"); 0.03 / 0.02 was chosen post hoc, then confirmed in a
# registered run.
W_ENTITY_DEFAULT = 0.03
W_PREDICATE_DEFAULT = 0.02


def sep_term(ent_match: bool, fan: int, *, gamma: float, s_max: float) -> float:
    """The single-cue lift ``gamma * max(0, 1 - ln(max(fan, 1)) / S_max)`` when the entity matched (P1 as
    first shipped; ``cues = "entity"``)."""
    if not ent_match:
        return 0.0
    return gamma * max(0.0, 1.0 - math.log(max(fan, 1)) / s_max)


def cue_term(match: bool, fan: int, *, w: float, s: float) -> float:
    """One ACT-R cue: ``w * max(0, S - ln(max(fan, 1)))`` when the cue matched, else 0."""
    if not match:
        return 0.0
    return w * max(0.0, s - math.log(max(fan, 1)))


def context_term(
    ent_match: bool,
    fan: int,
    pred_match: bool = False,
    pred_fan: int = 0,
    *,
    cues: str = "entity+predicate",
    gamma: float = 0.15,
    s_max: float = math.log(50.0),
    w_entity: float = W_ENTITY_DEFAULT,
    w_predicate: float = W_PREDICATE_DEFAULT,
    s: float = CUE_S_DEFAULT,
) -> float:
    """The ``sep`` term: the matched cues summed (``cues = "entity+predicate"``, CROSS_CHECK §3.2) or the
    single damped entity term (``cues = "entity"``, the pre-§3.2 form; the predicate is ignored there)."""
    if cues == "entity":
        return sep_term(ent_match, fan, gamma=gamma, s_max=s_max)
    return cue_term(ent_match, fan, w=w_entity, s=s) + cue_term(pred_match, pred_fan, w=w_predicate, s=s)


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
    pred_match: bool = False,
    pred_fan: int = 0,
    cues: str = "entity+predicate",
    w_entity: float = W_ENTITY_DEFAULT,
    w_predicate: float = W_PREDICATE_DEFAULT,
    S: float = CUE_S_DEFAULT,
) -> float:
    """ln-relevance plus the bounded additive terms. Returns ``-inf`` for ``rel <= 0``."""
    if rel <= 0:
        return NEG_INF
    base = math.log(min(rel, 1.0))
    sep = context_term(
        ent_match,
        fan,
        pred_match,
        pred_fan,
        cues=cues,
        gamma=gamma,
        s_max=S_max,
        w_entity=w_entity,
        w_predicate=w_predicate,
        s=S,
    )
    if bypass:  # exact match of every query word in the fact text: no use-history or salience term
        return base + sep
    act = act_term(A, A0, beta=beta, s_noise=s_noise)
    sal = sal_term(salience, in_band=in_band, s_max_band=s_max_band, delta=delta)
    rel_term = rho * math.log(max(reliability, 1e-3) / RELIABILITY_PRIOR)
    return base + act + sep + sal + rel_term
