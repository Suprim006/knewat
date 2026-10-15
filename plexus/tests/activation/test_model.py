"""Slice 3a: the pure activation model against the ACT-R table in docs/research/forgetting-A section 1.3."""

from __future__ import annotations

import math

import pytest

from plexus.activation.model import (
    DAY_MS,
    W_RECALL,
    Event,
    activation,
    final_score,
    multiplier,
    neutral_activation,
    novelty,
    sigmoid,
    surprise_events,
)

NOW = 10_000 * DAY_MS
HOUR = 3_600_000


def uses(*ages_ms: int, w: float = 1.0) -> list[Event]:
    return [Event("use", NOW - a, w) for a in ages_ms]


@pytest.mark.parametrize(
    ("ages_days", "expected"),
    [
        ([1 / 24], -4.09),  # 1 access, 1 h ago
        ([1], -5.68),
        ([7], -6.66),
        ([30], -7.38),
        ([90], -7.93),
        ([1, 3, 7, 14, 30], -4.81),  # 5 accesses
        ([60] * 5, -6.12),  # burst 60 d ago
        ([1 + 7 * i for i in range(10)], -4.68),  # 10 weekly accesses, last 1 d ago
    ],
)
def test_matches_the_act_r_table(ages_days, expected):
    events = uses(*[round(d * DAY_MS) for d in ages_days])
    assert activation(events, now=NOW, created_at=0) == pytest.approx(expected, abs=0.006)


def test_a_minute_floor_keeps_a_brand_new_event_finite():
    just_now = [Event("use", NOW - 1, 1.0)]
    assert activation(just_now, now=NOW, created_at=0) == pytest.approx(math.log(60**-0.5))
    assert activation(just_now, now=NOW, created_at=0) == activation(
        [Event("use", NOW - 59_000, 1.0)], now=NOW, created_at=0
    )


def test_recall_events_weigh_point_three():
    a_recall = activation([Event("recall", NOW - DAY_MS, W_RECALL)], now=NOW, created_at=0)
    a_use = activation([Event("use", NOW - DAY_MS, 1.0)], now=NOW, created_at=0)
    assert a_recall == pytest.approx(a_use + math.log(0.3))


def test_only_the_newest_k_events_count_and_future_events_are_ignored():
    old = uses(*[100 * DAY_MS] * 80)
    recent = uses(*[DAY_MS] * 3)
    k3 = activation(old + recent, now=NOW, created_at=0, max_events=3)
    assert k3 == pytest.approx(activation(recent, now=NOW, created_at=0))
    future = [Event("use", NOW + DAY_MS, 1.0)]
    assert activation(future + recent, now=NOW, created_at=0) == pytest.approx(
        activation(recent, now=NOW, created_at=0)
    )


def test_decay_parameter_is_used():
    ev = uses(DAY_MS)
    assert activation(ev, now=NOW, created_at=0, decay=0.25) == pytest.approx(math.log(86400**-0.25))


@pytest.mark.parametrize(
    ("surprise", "n"), [(0.0, 0), (0.1, 1), (0.125, 1 + 1), (0.5, 3), (0.6, 3), (0.9, 5), (1.0, 5)]
)
def test_surprise_adds_one_plus_round_four_s_pseudo_events(surprise, n):
    assert surprise_events(surprise) == n


def test_surprise_bonus_is_counted_at_creation_time():
    created = NOW - 30 * DAY_MS
    plain = activation(uses(30 * DAY_MS), now=NOW, created_at=created)
    boosted = activation(uses(30 * DAY_MS), now=NOW, created_at=created, surprise=0.9)
    assert boosted == pytest.approx(plain + math.log(1 + 5))  # five extra creation-time events on top of one


def test_no_events_and_no_surprise_is_minus_infinity():
    assert activation([], now=NOW, created_at=0) == float("-inf")


def test_neutral_activation_is_a_fact_created_once_one_day_ago():
    assert neutral_activation() == pytest.approx(activation(uses(DAY_MS), now=NOW, created_at=0))
    assert neutral_activation(a0=-3.0) == -3.0


def test_multiplier_has_a_floor_and_a_ceiling_and_is_half_way_at_neutral():
    a0 = neutral_activation()
    assert multiplier(a0, a0, 0.5) == pytest.approx(0.75)
    assert multiplier(a0 - 50, a0, 0.5) == pytest.approx(0.5, abs=1e-9)
    assert multiplier(a0 + 50, a0, 0.5) == pytest.approx(1.0, abs=1e-9)
    assert multiplier(float("-inf"), a0, 0.5) == 0.5
    assert multiplier(a0, a0, 0.0) == pytest.approx(0.5)


def test_protected_facts_never_fall_below_neutral_and_keyword_hits_bypass():
    a0 = neutral_activation()
    assert multiplier(a0 - 10, a0, 0.5, protected=True) == pytest.approx(0.75)
    assert multiplier(a0 + 2, a0, 0.5, protected=True) == pytest.approx(multiplier(a0 + 2, a0, 0.5))
    assert multiplier(a0 - 10, a0, 0.5, bypass=True) == 1.0


def test_final_score_clamps_relevance_and_sigmoid_is_stable():
    assert final_score(1.4, 0.5) == 0.5 and final_score(-0.2, 0.5) == 0.0
    assert sigmoid(-1000) == 0.0 and sigmoid(1000) == 1.0


def test_novelty_clamps_and_empty_scope_is_the_maximum():
    assert novelty(None) == 0.5
    assert novelty(0.2) == pytest.approx(0.2)
    assert novelty(0.9) == 0.5
    assert novelty(-0.01) == 0.0
