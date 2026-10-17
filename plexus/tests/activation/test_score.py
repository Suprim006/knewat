"""D-013: the additive score terms, the Pavlik-Anderson activation and the new settings (no database)."""

from __future__ import annotations

import math

import pytest

from plexus.activation import Settings
from plexus.activation import score as S
from plexus.activation.model import DAY_MS, Event, activation, activation_spaced, neutral_activation

HOUR_MS = 3_600_000
NOW = 10_000 * DAY_MS


def ev(kind: str, days_ago: float, w: float = 1.0) -> Event:
    return Event(kind, NOW - round(days_ago * DAY_MS), w)


# -- score terms --------------------------------------------------------------------------------------


def test_sep_term_is_gamma_for_a_lonely_entity_and_zero_for_a_hub():
    g, smax = 0.15, math.log(50)
    assert S.sep_term(True, 1, gamma=g, s_max=smax) == pytest.approx(0.15)
    assert S.sep_term(True, 12, gamma=g, s_max=smax) == pytest.approx(0.15 * (1 - math.log(12) / smax))
    assert S.sep_term(True, 50, gamma=g, s_max=smax) == 0.0
    assert S.sep_term(True, 200, gamma=g, s_max=smax) == 0.0
    assert S.sep_term(False, 1, gamma=g, s_max=smax) == 0.0
    assert S.sep_term(True, 0, gamma=g, s_max=smax) == pytest.approx(0.15), "fan 0 counts as 1"


def test_act_term_is_bounded_by_beta_and_minus_beta_for_an_unknown_activation():
    for a in (-50.0, -5.0, -2.0, 0.0, 3.0, 40.0):
        t = S.act_term(a, -2.0, beta=0.05, s_noise=1.0)
        assert -0.05 <= t <= 0.05
    assert S.act_term(-2.0, -2.0, beta=0.05, s_noise=1.0) == 0.0
    assert S.act_term(float("-inf"), -2.0, beta=0.05, s_noise=1.0) == -0.05
    assert S.act_term(-1.0, -2.0, beta=0.05, s_noise=1.0) > S.act_term(-1.0, -2.0, beta=0.05, s_noise=2.0)


def test_sal_term_lifts_inside_the_band_and_suppresses_the_tail_only_when_the_band_is_critical():
    assert S.sal_term(0.6, in_band=True, s_max_band=0.9, delta=0.03) == pytest.approx(0.018)
    assert S.sal_term(0.6, in_band=False, s_max_band=0.9, delta=0.03) == pytest.approx(-0.027)
    assert S.sal_term(0.6, in_band=False, s_max_band=0.5, delta=0.03) == 0.0
    assert S.sal_term(0.0, in_band=False, s_max_band=0.0, delta=0.03) == 0.0


def test_score_is_ln_relevance_plus_bounded_terms_and_a_bypass_keeps_only_the_entity_lift():
    kw: dict = dict(A=-1.0, A0=-2.0, s_noise=1.0, beta=0.05, S_max=math.log(50), gamma=0.15, delta=0.03)
    plain = S.score(0.7, ent_match=False, fan=0, salience=0.0, in_band=True, s_max_band=0.0, **kw)
    assert plain == pytest.approx(math.log(0.7) + 0.05 * math.tanh(0.5))
    lifted = S.score(0.7, ent_match=True, fan=5, salience=0.0, in_band=True, s_max_band=0.0, **kw)
    assert lifted - plain == pytest.approx(S.sep_term(True, 5, gamma=0.15, s_max=math.log(50)))
    byp = S.score(0.7, ent_match=True, fan=5, salience=0.9, in_band=True, s_max_band=0.9, bypass=True, **kw)
    assert byp == pytest.approx(math.log(0.7) + S.sep_term(True, 5, gamma=0.15, s_max=math.log(50)))
    assert S.score(0.0, ent_match=True, fan=1, salience=0.0, in_band=True, s_max_band=0.0, **kw) == float(
        "-inf"
    )
    assert S.score(1.7, ent_match=False, fan=0, salience=0.0, in_band=True, s_max_band=0.0, **kw) <= 0.05


# -- activation with activation-dependent decay --------------------------------------------------------


def test_neutral_under_the_pavlik_anderson_scale_is_about_minus_two():
    a0 = neutral_activation(0.177)
    assert a0 == pytest.approx(-2.01, abs=0.01)
    a, ds = activation_spaced([ev("create", 1.0)], now=NOW, created_at=NOW - DAY_MS)
    assert a == pytest.approx(a0) and ds == [pytest.approx(0.177)]


def test_a_burst_of_massed_reads_is_worth_about_one_read_while_spaced_reads_keep_their_value():
    created = ev("create", 90)
    burst = [created] + [
        Event("use", NOW - 45 * DAY_MS + i * 40_000, 1.0) for i in range(90)
    ]  # 90 reads in one hour
    spaced = [created] + [ev("use", d) for d in (89, 60, 30, 14, 7, 3, 1)]
    one = [created, ev("use", 45)]
    a_burst, ds_burst = activation_spaced(burst, now=NOW, created_at=created.t)
    a_spaced, _ = activation_spaced(spaced, now=NOW, created_at=created.t)
    a_one, _ = activation_spaced(one, now=NOW, created_at=created.t)
    assert a_spaced > a_burst, "7 spaced reads beat 90 massed ones"
    assert a_burst - a_one < 1.0, "the burst is worth less than one extra nat over a single read"
    assert max(ds_burst) > 3 * 0.177, "massed reads decay much faster than the base exponent a"
    # under the plain d = 0.5 model the burst wins by about a nat (the defect D-013 removes)
    assert (
        activation(burst, now=NOW, created_at=created.t) - activation(spaced, now=NOW, created_at=created.t)
        > 0.9
    )


def test_only_the_newest_max_events_count_and_future_events_are_ignored():
    created = ev("create", 10)
    future = Event("use", NOW + DAY_MS, 1.0)
    a, ds = activation_spaced([created, future], now=NOW, created_at=created.t)
    assert ds == [pytest.approx(0.177)]
    many = [created] + [ev("use", d / 10) for d in range(1, 80)]
    _, ds = activation_spaced(many, now=NOW, created_at=created.t, max_events=50)
    assert len(ds) == 50


def test_salience_slows_every_decay_exponent():
    events = [ev("create", 60), ev("use", 30)]
    slow, ds_slow = activation_spaced(events, now=NOW, created_at=events[0].t, kappa_s=0.4)
    fast, ds_fast = activation_spaced(events, now=NOW, created_at=events[0].t)
    assert slow > fast
    assert ds_slow[0] == pytest.approx(ds_fast[0] * 0.6)
    assert all(s < f for s, f in zip(ds_slow, ds_fast, strict=True))


def test_a_recall_after_the_last_use_is_a_restudy_worth_less_when_the_fact_is_already_active():
    a0 = neutral_activation(0.177)
    base = [ev("create", 30), ev("use", 2)]
    with_recall = [*base, ev("recall", 1, 0.3)]
    with_use = [*base, ev("use", 1, 1.0)]
    a_base, _ = activation_spaced(base, now=NOW, created_at=base[0].t, a0=a0)
    a_rec, _ = activation_spaced(with_recall, now=NOW, created_at=base[0].t, a0=a0)
    a_use, _ = activation_spaced(with_use, now=NOW, created_at=base[0].t, a0=a0)
    assert a_base < a_rec < a_use
    # the same recall without the testing-effect rule (no a0) counts its full 0.3
    a_plain, _ = activation_spaced(with_recall, now=NOW, created_at=base[0].t)
    assert a_plain > a_rec
    # a recall BEFORE the last use is not a restudy: full weight either way
    before = [ev("create", 30), ev("recall", 5, 0.3), ev("use", 2)]
    x, _ = activation_spaced(before, now=NOW, created_at=before[0].t, a0=a0)
    y, _ = activation_spaced(before, now=NOW, created_at=before[0].t)
    assert x == pytest.approx(y)


def test_no_events_and_no_surprise_is_minus_infinity_and_surprise_adds_pseudo_events():
    a, ds = activation_spaced([], now=NOW, created_at=NOW - DAY_MS)
    assert a == float("-inf") and ds == []
    s, _ = activation_spaced([], now=NOW, created_at=NOW - DAY_MS, surprise=0.9)
    assert s > neutral_activation(0.177)


# -- settings -----------------------------------------------------------------------------------------


def test_d013_settings_defaults_and_mode_aware_neutral_and_sweep_margin():
    s = Settings.from_env({})
    assert (s.act_mode, s.separation, s.kw_bypass) == ("mult", True, "fact")
    assert (s.beta, s.s_noise, s.gamma, s.delta, s.band, s.kappa, s.c, s.a, s.d_max) == (
        0.05,
        1.0,
        0.15,
        0.03,
        0.02,
        0.4,
        0.217,
        0.177,
        1.0,
    )
    assert s.s_max == pytest.approx(math.log(50))
    assert s.sweep_margin == 2.0 and s.neutral == pytest.approx(neutral_activation(0.5))
    add = Settings.from_env({"PLEXUS_ACT_MODE": "add"})
    assert add.additive and add.sweep_margin == 0.72
    assert add.neutral == pytest.approx(-2.01, abs=0.01)
    assert Settings.from_env({"PLEXUS_ACT_MODE": "add", "PLEXUS_ACT_A0": "-3"}).neutral == -3.0


def test_every_d013_variable_is_read():
    s = Settings.from_env(
        {
            "PLEXUS_ACT_MODE": "ADD",
            "PLEXUS_ACT_BETA": "0.1",
            "PLEXUS_ACT_S": "0.5",
            "PLEXUS_ACT_C": "0.2",
            "PLEXUS_ACT_A": "0.2",
            "PLEXUS_ACT_DMAX": "0.9",
            "PLEXUS_ACT_KAPPA": "0.3",
            "PLEXUS_ACT_DELTA": "0.02",
            "PLEXUS_ACT_BAND": "0.05",
            "PLEXUS_RECALL_SEPARATION": "off",
            "PLEXUS_ACT_GAMMA": "0.2",
            "PLEXUS_ACT_SMAX": "5",
            "PLEXUS_KW_BYPASS": "value",
        }
    )
    assert (s.act_mode, s.beta, s.s_noise, s.c, s.a, s.d_max, s.kappa, s.delta, s.band) == (
        "add",
        0.1,
        0.5,
        0.2,
        0.2,
        0.9,
        0.3,
        0.02,
        0.05,
    )
    assert (s.separation, s.gamma, s.s_max, s.kw_bypass) == (False, 0.2, 5.0, "value")


@pytest.mark.parametrize(
    "env",
    [
        {"PLEXUS_ACT_MODE": "both"},
        {"PLEXUS_KW_BYPASS": "text"},
        {"PLEXUS_RECALL_SEPARATION": "maybe"},
        {"PLEXUS_ACT_BETA": "2"},
        {"PLEXUS_ACT_S": "0"},
        {"PLEXUS_ACT_SMAX": "-1"},
        {"PLEXUS_ACT_KAPPA": "1"},
        {"PLEXUS_ACT_DMAX": "0.1", "PLEXUS_ACT_A": "0.5"},
    ],
)
def test_bad_d013_values_are_rejected_loudly(env):
    with pytest.raises(ValueError, match="PLEXUS_"):
        Settings.from_env(env)
