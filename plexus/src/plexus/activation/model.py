"""The activation model (D-012): pure functions, no database.

``A(f) = ln( sum_events w * max(now - t, 60 s) ** -d + surprise_bonus )`` over the newest ``K`` events; time
**seconds** (after the 60 s floor), ``d = 0.5`` by default. See ``docs/forgetting.md``.
"""

from __future__ import annotations

import math
from collections.abc import Iterable, Sequence
from dataclasses import dataclass

MS_MIN_AGE = 60_000  # an event younger than a minute counts as a minute old (keeps the power finite)
DAY_MS = 86_400_000

# event weights (docs/P7-contract.md)
W_CREATE = 1.0
W_REASSERT = 1.0
W_DECISION = 1.0
W_HANDOFF = 1.0
W_USE = 1.0
W_RECALL = 0.3
W_VERIFIED = 2.0

# surprise at write time (D-012)
SURPRISE_SUPERSEDE = 0.6
SURPRISE_CONTRADICT = 0.9
NOVELTY_CAP = 0.5
NOVELTY_K = 5  # nearest active facts of the scope that are looked at
NOVELTY_OVER = 20  # vector fetch size: the index has no scope pre-filter, so ask for more than k


@dataclass(frozen=True)
class Event:
    """One access to a fact: ``kind`` is a label for explanations, ``t`` is epoch ms, ``w`` the weight."""

    kind: str
    t: int
    w: float


def novelty(nearest_distance: float | None) -> float:
    """``min(0.5, max(0, 1 - maxcos))``; the vector score is a cosine *distance* (= ``1 - maxcos``).

    ``None`` (no active fact in the scope) is the first fact of an empty scope: the maximum, 0.5.
    """
    if nearest_distance is None:
        return NOVELTY_CAP
    return min(NOVELTY_CAP, max(0.0, float(nearest_distance)))


def surprise_events(surprise: float) -> int:
    """Pseudo-events a surprise adds at creation: ``1 + round(4 * surprise)`` when surprise > 0, else 0.

    Rounds half up (not Python's banker's rounding) so the result is easy to state and to test.
    """
    if surprise <= 0:
        return 0
    return 1 + int(math.floor(4 * min(surprise, 1.0) + 0.5))


def _weight_at(now: int, t: int, d: float) -> float:
    age_s = max(now - t, MS_MIN_AGE) / 1000.0
    return age_s**-d


def activation(
    events: Iterable[Event],
    *,
    now: int,
    created_at: int,
    surprise: float = 0.0,
    decay: float = 0.5,
    max_events: int = 50,
) -> float:
    """Base-level activation ``A`` of a fact.

    ``events`` may be in any order and may contain events from the future (ignored). Only the newest
    ``max_events`` count; the surprise bonus is added on top of them. With no events and no surprise the
    activation is ``-inf`` (nothing ever touched it); a stored fact always has at least its creation event.
    """
    newest = sorted((e for e in events if e.t <= now), key=lambda e: e.t, reverse=True)[:max_events]
    total = sum(e.w * _weight_at(now, e.t, decay) for e in newest)
    total += surprise_events(surprise) * _weight_at(now, created_at, decay)
    return math.log(total) if total > 0 else float("-inf")


def neutral_activation(decay: float = 0.5, a0: float | None = None) -> float:
    """``A0``: the activation of a fact created once, one day ago (unless overridden)."""
    if a0 is not None:
        return a0
    return math.log((DAY_MS / 1000.0) ** -decay)


def sigmoid(x: float) -> float:
    if x >= 0:
        return 1.0 / (1.0 + math.exp(-x))
    e = math.exp(x)
    return e / (1.0 + e)


def multiplier(a: float, a0: float, floor: float, *, protected: bool = False, bypass: bool = False) -> float:
    """``floor + (1 - floor) * sigmoid(A - A0)``; protected facts use ``max(A, A0)``; exact keyword hit: 1."""
    if bypass:
        return 1.0
    eff = max(a, a0) if protected else a
    if eff == float("-inf"):
        return floor
    return floor + (1.0 - floor) * sigmoid(eff - a0)


def final_score(relevance: float, mult: float) -> float:
    """``relevance`` (clamped to 0..1) times the activation multiplier."""
    return min(1.0, max(0.0, relevance)) * mult


def counts(events: Sequence[Event]) -> dict[str, int]:
    out: dict[str, int] = {}
    for e in events:
        out[e.kind] = out.get(e.kind, 0) + 1
    return out
