"""Activation-based forgetting (D-012): rank by use, never delete by decay."""

from plexus.activation.model import Event, activation, multiplier, neutral_activation, novelty

__all__ = ["Event", "activation", "multiplier", "neutral_activation", "novelty"]
