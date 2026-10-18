"""Activation settings, read from the environment (defaults in brackets).

Forgetting (D-012): ``PLEXUS_FORGETTING`` [on] (``on``/``off``) · ``PLEXUS_ACT_EVENTS`` [50] ·
``PLEXUS_ACT_A0`` [the activation of a fact created once, one day ago] · ``PLEXUS_ACT_DECAY`` [0.5] ·
``PLEXUS_ACT_FLOOR`` [0.9].

Pattern separation (D-013 P1): ``PLEXUS_RECALL_SEPARATION`` [on] · ``PLEXUS_ACT_CUE_S`` [5] ·
``PLEXUS_ACT_W_ENTITY`` [0.03] · ``PLEXUS_ACT_W_PREDICATE`` [0.02] · ``PLEXUS_ACT_SMAX`` [ln 50] (the fan at
which the sibling expansion of ``engram/recall`` is damped to nothing).
"""

from __future__ import annotations

import math
import os
from collections.abc import Mapping
from dataclasses import dataclass

from plexus.activation.model import neutral_activation
from plexus.activation.score import CUE_S_DEFAULT, W_ENTITY_DEFAULT, W_PREDICATE_DEFAULT

MAX_EVENTS = 200
_ON = {"on", "1", "true", "yes"}
_OFF = {"off", "0", "false", "no"}
S_MAX_DEFAULT = math.log(50.0)  # an entity with >= 50 current facts gets no entity lift (ACT-R fan)
SWEEP_MARGIN = 2.0  # memory_sweep default threshold = A0 - margin: "about 55-60 days unused" under d = 0.5


@dataclass(frozen=True)
class Settings:
    decay: float = 0.5
    a0: float | None = None  # None = the activation of a fact created once, 1 day ago
    # 0.5 let popular near-twin facts outrank the relevant one (Crucible L5b); 0.9 kept the critical probes
    floor: float = 0.9
    events: int = 50
    forgetting: bool = True
    separation: bool = True
    s_max: float = S_MAX_DEFAULT
    # CROSS_CHECK §3.2: the context term as a sum of weighted cues
    cue_s: float = CUE_S_DEFAULT
    w_entity: float = W_ENTITY_DEFAULT
    w_predicate: float = W_PREDICATE_DEFAULT

    def __post_init__(self) -> None:
        if not 0.0 < self.decay <= 2.0:
            raise ValueError("PLEXUS_ACT_DECAY must be in (0, 2]")
        if not 0.0 <= self.floor <= 1.0:
            raise ValueError("PLEXUS_ACT_FLOOR must be between 0 and 1")
        if not 1 <= self.events <= MAX_EVENTS:
            raise ValueError(f"PLEXUS_ACT_EVENTS must be between 1 and {MAX_EVENTS}")
        for name, v in (("PLEXUS_ACT_W_ENTITY", self.w_entity), ("PLEXUS_ACT_W_PREDICATE", self.w_predicate)):
            if not 0.0 <= v <= 10.0:
                raise ValueError(f"{name} must be between 0 and 10")
        for name, v, hi in (("PLEXUS_ACT_SMAX", self.s_max, 20.0), ("PLEXUS_ACT_CUE_S", self.cue_s, 20.0)):
            if not 0.0 < v <= hi:
                raise ValueError(f"{name} must be in (0, {hi:g}]")

    @property
    def neutral(self) -> float:
        """``A0``: a fact created once, one day ago, unless overridden."""
        return neutral_activation(self.decay, self.a0)

    @classmethod
    def from_env(cls, env: Mapping[str, str] | None = None) -> Settings:
        e = os.environ if env is None else env

        def get(name: str) -> str | None:
            v = e.get(name)
            return v.strip() if v and v.strip() else None

        def flag(name: str) -> bool:
            v = (get(name) or "on").lower()
            if v not in _ON | _OFF:
                raise ValueError(f"{name} must be 'on' or 'off'")
            return v in _ON

        def num(name: str, default: float) -> float:
            v = get(name)
            return default if v is None else float(v)

        forgetting = flag("PLEXUS_FORGETTING")
        separation = flag("PLEXUS_RECALL_SEPARATION")
        try:
            return cls(
                decay=num("PLEXUS_ACT_DECAY", 0.5),
                a0=float(v) if (v := get("PLEXUS_ACT_A0")) is not None else None,
                floor=num("PLEXUS_ACT_FLOOR", 0.9),
                events=int(get("PLEXUS_ACT_EVENTS") or 50),
                forgetting=forgetting,
                separation=separation,
                s_max=num("PLEXUS_ACT_SMAX", S_MAX_DEFAULT),
                cue_s=num("PLEXUS_ACT_CUE_S", CUE_S_DEFAULT),
                w_entity=num("PLEXUS_ACT_W_ENTITY", W_ENTITY_DEFAULT),
                w_predicate=num("PLEXUS_ACT_W_PREDICATE", W_PREDICATE_DEFAULT),
            )
        except ValueError as exc:
            if "PLEXUS_" in str(exc):
                raise
            raise ValueError(f"invalid PLEXUS_ACT_* / PLEXUS_FORGETTING setting: {exc}") from None
