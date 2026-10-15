"""Activation-based forgetting (D-012): rank by use, never delete by decay."""

from plexus.activation.model import Event, activation, multiplier, neutral_activation, novelty
from plexus.activation.service import Activation, FactActivation
from plexus.activation.settings import Settings

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
