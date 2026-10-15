"""Activation settings, read from the environment (defaults in brackets).

``PLEXUS_ACT_DECAY`` [0.5] · ``PLEXUS_ACT_A0`` [activation of a fact created once, one day ago] ·
``PLEXUS_ACT_FLOOR`` [0.9] · ``PLEXUS_ACT_EVENTS`` [50] · ``PLEXUS_FORGETTING`` [on] (``on``/``off``).
"""

from __future__ import annotations

import os
from collections.abc import Mapping
from dataclasses import dataclass

from plexus.activation.model import neutral_activation

MAX_EVENTS = 200
_ON = {"on", "1", "true", "yes"}
_OFF = {"off", "0", "false", "no"}


@dataclass(frozen=True)
class Settings:
    decay: float = 0.5
    a0: float | None = None  # None = the activation of a fact created once, 1 day ago
    # 0.5 let popular near-twin facts outrank the relevant one (Crucible L5b); 0.9 kept the critical probes
    floor: float = 0.9
    events: int = 50
    forgetting: bool = True

    def __post_init__(self) -> None:
        if not 0.0 < self.decay <= 2.0:
            raise ValueError("PLEXUS_ACT_DECAY must be in (0, 2]")
        if not 0.0 <= self.floor <= 1.0:
            raise ValueError("PLEXUS_ACT_FLOOR must be between 0 and 1")
        if not 1 <= self.events <= MAX_EVENTS:
            raise ValueError(f"PLEXUS_ACT_EVENTS must be between 1 and {MAX_EVENTS}")

    @property
    def neutral(self) -> float:
        """``A0``: the activation at which the multiplier is half way between the floor and 1."""
        return neutral_activation(self.decay, self.a0)

    @classmethod
    def from_env(cls, env: Mapping[str, str] | None = None) -> Settings:
        e = os.environ if env is None else env

        def get(name: str) -> str | None:
            v = e.get(name)
            return v.strip() if v and v.strip() else None

        flag = (get("PLEXUS_FORGETTING") or "on").lower()
        if flag not in _ON | _OFF:
            raise ValueError("PLEXUS_FORGETTING must be 'on' or 'off'")
        try:
            return cls(
                decay=float(get("PLEXUS_ACT_DECAY") or 0.5),
                a0=float(v) if (v := get("PLEXUS_ACT_A0")) is not None else None,
                floor=float(get("PLEXUS_ACT_FLOOR") or 0.9),
                events=int(get("PLEXUS_ACT_EVENTS") or 50),
                forgetting=flag in _ON,
            )
        except ValueError as exc:
            if "PLEXUS_" in str(exc):
                raise
            raise ValueError(f"invalid PLEXUS_ACT_* / PLEXUS_FORGETTING setting: {exc}") from None
