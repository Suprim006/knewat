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


def _age_s(t1: int, t0: int) -> float:
    return max(t1 - t0, MS_MIN_AGE) / 1000.0


def activation_spaced(
    events: Iterable[Event],
    *,
    now: int,
    created_at: int,
    surprise: float = 0.0,
    c: float = 0.217,
    a: float = 0.177,
    d_max: float = 1.0,
    kappa_s: float = 0.0,
    a0: float | None = None,
    max_events: int = 50,
    w_restudy: float = W_RECALL,
) -> tuple[float, list[float]]:
    """Base-level activation with activation-dependent decay (Pavlik & Anderson 2005; D-013, ``add`` mode).

    Each event ``i`` decays with its own exponent ``d_i = min(d_max, c * exp(m_{i-1}) + a)`` where ``m_{i-1}``
    is the activation just before it (``a`` for the first event): reads of an already-active fact decay fast,
    so a burst of massed reads is worth little more than one read while spaced reads keep their value.
    ``kappa_s`` (``kappa * salience``) slows every exponent: ``d_i * (1 - kappa_s)``. Testing-effect rule
    (note 03 §3.1): a
    ``recall`` event later than the fact's last ``use`` is a restudy and weighs ``w_restudy * (1 -
    sigmoid(m_prev
    - A0))`` (an easy re-exposure is worth ~0, a re-exposure of a faded fact up to ``w_restudy``); it needs
    ``a0``, so pass the neutral activation (``None`` = the plain weight). Only the newest ``max_events``
    count.

    Returns ``(A, [d_i per counted event, oldest first])``; ``A`` is ``-inf`` with no events and no surprise.
    """
    ev = sorted((e for e in events if e.t <= now), key=lambda e: e.t)[-max_events:]
    last_use = max((e.t for e in ev if e.kind == "use"), default=None)
    ds: list[float] = []
    ws: list[float] = []
    for i, e in enumerate(ev):
        if i == 0:
            m_prev = float("-inf")
        else:
            m_prev = math.log(sum(ws[j] * _age_s(e.t, ev[j].t) ** -ds[j] for j in range(i)))
        d_i = a if m_prev == float("-inf") else min(d_max, c * math.exp(m_prev) + a)
        ds.append(d_i * (1.0 - kappa_s))
        w = e.w
        if e.kind == "recall" and a0 is not None and (last_use is None or e.t > last_use):
            w = w_restudy * (1.0 - sigmoid(m_prev - a0)) if m_prev != float("-inf") else w_restudy
        ws.append(w)
    total = sum(ws[i] * _age_s(now, e.t) ** -ds[i] for i, e in enumerate(ev))
    total += surprise_events(surprise) * _age_s(now, created_at) ** -(a * (1.0 - kappa_s))
    return (math.log(total) if total > 0 else float("-inf")), ds


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
