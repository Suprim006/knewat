"""D-013 P1: the context-term cues and the activation settings (no database)."""

from __future__ import annotations

import math

import pytest

from plexus.activation import Settings
from plexus.activation import score as S
from plexus.activation.model import neutral_activation

# -- context term ----------------------------------------------------------------------------------


def test_cue_term_is_w_times_s_minus_ln_fan_floored_at_zero_and_the_context_term_sums_the_cues():
    assert S.cue_term(True, 1, w=0.6, s=5.0) == pytest.approx(3.0)
    assert S.cue_term(True, 12, w=0.6, s=5.0) == pytest.approx(0.6 * (5 - math.log(12)))
    assert S.cue_term(True, 148, w=0.6, s=5.0) == pytest.approx(0.6 * (5 - math.log(148)))  # still > 0
    assert S.cue_term(True, 149, w=0.6, s=5.0) == 0.0, "fan > e^S: nothing, never negative"
    assert S.cue_term(True, 0, w=0.6, s=5.0) == pytest.approx(3.0), "fan 0 counts as 1"
    assert S.cue_term(False, 1, w=0.6, s=5.0) == 0.0
    we, wp = S.W_ENTITY_DEFAULT, S.W_PREDICATE_DEFAULT
    assert (we, wp, S.CUE_S_DEFAULT) == (0.03, 0.02, 5.0), "the confirmed defaults (docs/BASELINE.md)"
    both = S.context_term(True, 12, True, 20)
    assert both == pytest.approx(we * (5 - math.log(12)) + wp * (5 - math.log(20)))
    assert S.context_term(True, 12) == pytest.approx(we * (5 - math.log(12)))
    assert S.context_term(True, 12) == pytest.approx(0.075, abs=0.001)
    assert S.context_term(False, 0, True, 20) == pytest.approx(wp * (5 - math.log(20)))
    assert S.context_term(False, 0) == 0.0


# -- settings -----------------------------------------------------------------------------------------


def test_d013_settings_defaults_and_neutral():
    s = Settings.from_env({})
    assert s.separation is True
    assert s.s_max == pytest.approx(math.log(50))
    assert (s.cue_s, s.w_entity, s.w_predicate) == (5.0, 0.03, 0.02)
    assert s.neutral == pytest.approx(neutral_activation(0.5))


def test_every_d013_variable_is_read():
    s = Settings.from_env(
        {
            "PLEXUS_RECALL_SEPARATION": "off",
            "PLEXUS_ACT_SMAX": "5",
            "PLEXUS_ACT_CUE_S": "4",
            "PLEXUS_ACT_W_ENTITY": "1",
            "PLEXUS_ACT_W_PREDICATE": "0",
        }
    )
    assert (s.separation, s.s_max, s.cue_s, s.w_entity, s.w_predicate) == (False, 5.0, 4.0, 1.0, 0.0)


@pytest.mark.parametrize(
    "env",
    [
        {"PLEXUS_RECALL_SEPARATION": "maybe"},
        {"PLEXUS_ACT_SMAX": "-1"},
        {"PLEXUS_ACT_CUE_S": "0"},
        {"PLEXUS_ACT_W_ENTITY": "11"},
    ],
)
def test_bad_d013_values_are_rejected_loudly(env):
    with pytest.raises(ValueError, match="PLEXUS_"):
        Settings.from_env(env)
