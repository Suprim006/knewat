"""Activation settings come from the environment, with the documented defaults."""

from __future__ import annotations

import pytest

from plexus.activation import Settings
from plexus.activation.model import neutral_activation


def test_defaults():
    s = Settings.from_env({})
    assert (s.decay, s.floor, s.events, s.forgetting, s.a0) == (0.5, 0.5, 50, True, None)
    assert s.neutral == pytest.approx(neutral_activation())


def test_every_variable_is_read():
    s = Settings.from_env(
        {
            "PLEXUS_ACT_DECAY": "0.4",
            "PLEXUS_ACT_A0": "-6.5",
            "PLEXUS_ACT_FLOOR": "0.25",
            "PLEXUS_ACT_EVENTS": "20",
            "PLEXUS_FORGETTING": "off",
        }
    )
    assert (s.decay, s.a0, s.floor, s.events, s.forgetting) == (0.4, -6.5, 0.25, 20, False)
    assert s.neutral == -6.5


@pytest.mark.parametrize("val", ["on", "ON", "1", "true"])
def test_forgetting_on_spellings(val):
    assert Settings.from_env({"PLEXUS_FORGETTING": val}).forgetting is True


@pytest.mark.parametrize(
    "env",
    [
        {"PLEXUS_FORGETTING": "maybe"},
        {"PLEXUS_ACT_DECAY": "0"},
        {"PLEXUS_ACT_DECAY": "fast"},
        {"PLEXUS_ACT_FLOOR": "1.5"},
        {"PLEXUS_ACT_EVENTS": "0"},
        {"PLEXUS_ACT_EVENTS": "5000"},
    ],
)
def test_bad_values_are_rejected_loudly(env):
    with pytest.raises(ValueError, match="PLEXUS_"):
        Settings.from_env(env)


def test_blank_values_mean_default():
    assert Settings.from_env({"PLEXUS_ACT_A0": "  ", "PLEXUS_FORGETTING": ""}).forgetting is True
