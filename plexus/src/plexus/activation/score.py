"""The context term of pattern separation (D-013 P1, pure, no database).

``sep`` is a sum over the cues the query carries (ACT-R ``C = sum_j W_j (S - ln fan_j)``,
docs/research/neuro-memory/CROSS_CHECK.md §3.2): the **entity** cue (the query names this fact's entity,
``fan`` = that entity's current facts in the searched scopes) weighted ``w_entity``, plus the **predicate**
cue (the query names this fact's predicate, ``pred_fan`` = current facts with that predicate in the searched
scopes) weighted ``w_predicate``. Each cue is ``w * max(0, S - ln fan)``, floored at 0: a hub cue adds
nothing, it never subtracts.
"""

from __future__ import annotations

import math

CUE_S_DEFAULT = 5.0  # ACT-R S: a cue with fan >= e^S (148) adds nothing
# CROSS_CHECK §3.2's 0.6 / 0.4 scaled by 1/20 (the registered 0.6 / 0.4 raised the noise share by 4-11 points,
# docs/BASELINE.md "Predicate cue results"); chosen post hoc, then confirmed in a registered run.
W_ENTITY_DEFAULT = 0.03
W_PREDICATE_DEFAULT = 0.02


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
    w_entity: float = W_ENTITY_DEFAULT,
    w_predicate: float = W_PREDICATE_DEFAULT,
    s: float = CUE_S_DEFAULT,
) -> float:
    """The ``sep`` term: the entity cue and the predicate cue, summed."""
    return cue_term(ent_match, fan, w=w_entity, s=s) + cue_term(pred_match, pred_fan, w=w_predicate, s=s)
