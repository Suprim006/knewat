"""Activation-based forgetting (D-012): rank by use, never delete by decay."""

from knewat.activation.model import Event, activation, multiplier, neutral_activation, novelty
from knewat.activation.service import Activation, FactActivation
from knewat.activation.settings import Settings

__all__ = [
    "Activation",
    "Event",
    "FactActivation",
    "Settings",
    "activation",
    "multiplier",
    "neutral_activation",
    "novelty",
]
