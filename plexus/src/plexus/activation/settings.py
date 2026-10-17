"""Activation settings, read from the environment (defaults in brackets).

Shared: ``PLEXUS_FORGETTING`` [on] (``on``/``off``) · ``PLEXUS_ACT_EVENTS`` [50] · ``PLEXUS_ACT_A0`` [the
activation of a fact created once, one day ago, under the active mode] · ``PLEXUS_ACT_MODE`` [mult] (``mult``
= D-012 multiplier,
``add`` = D-013 additive banded score).

``mult`` mode: ``PLEXUS_ACT_DECAY`` [0.5] · ``PLEXUS_ACT_FLOOR`` [0.9].

``add`` mode (D-013, docs/research/MEMORY_FORGETTING_IMPLEMENTATION_PLAN.md §1): ``PLEXUS_ACT_BETA`` [0.05] ·
``PLEXUS_ACT_S`` [1.0] (noise scale, nats) · ``PLEXUS_ACT_C`` [0.217] / ``PLEXUS_ACT_A`` [0.177] (Pavlik &
Anderson 2005 activation-dependent decay) · ``PLEXUS_ACT_DMAX`` [1.0] · ``PLEXUS_ACT_KAPPA`` [0.4] (salience
slows decay) ·
``PLEXUS_ACT_DELTA`` [0.03] / ``PLEXUS_ACT_BAND`` [0.02] (salience sharpening inside the relevance band).

Pattern separation (P1): ``PLEXUS_RECALL_SEPARATION`` [on] · ``PLEXUS_ACT_CUES`` [entity+predicate] (the
context term: ``entity+predicate`` = the two ACT-R cues summed, CROSS_CHECK §3.2; ``entity`` = the single
damped entity term P1 first shipped) · ``PLEXUS_ACT_CUE_S`` [5] · ``PLEXUS_ACT_W_ENTITY`` [0.6] ·
``PLEXUS_ACT_W_PREDICATE`` [0.4] · ``PLEXUS_ACT_GAMMA`` [0.15] · ``PLEXUS_ACT_SMAX`` [ln 50] (the single-cue
form, and the fan at which the sibling expansion of ``engram/recall`` is damped to nothing) ·
``PLEXUS_KW_BYPASS`` [fact] (``fact`` = the exact-keyword bypass tests the whole fact text, ``value`` = the
pre-D-013 rule).
"""

from __future__ import annotations

import math
import os
from collections.abc import Mapping
from dataclasses import dataclass

from plexus.activation.model import neutral_activation
from plexus.activation.score import CUE_MODES, CUE_S_DEFAULT, W_ENTITY_DEFAULT, W_PREDICATE_DEFAULT

MAX_EVENTS = 200
_ON = {"on", "1", "true", "yes"}
_OFF = {"off", "0", "false", "no"}
MODES = ("mult", "add")
BYPASS_KINDS = ("fact", "value")
S_MAX_DEFAULT = math.log(50.0)  # an entity with >= 50 current facts gets no entity lift (ACT-R fan)
# memory_sweep default threshold = A0 - margin, "about 55-60 days unused": 2.0 under d = 0.5, 0.72 under
# Pavlik-Anderson a = 0.177 (docs/research/neuro-memory/CROSS_CHECK.md §3.1: A0 - 2 would never fire there).
SWEEP_MARGIN_MULT = 2.0
SWEEP_MARGIN_ADD = 0.72


@dataclass(frozen=True)
class Settings:
    decay: float = 0.5
    a0: float | None = None  # None = the activation of a fact created once, 1 day ago
    # 0.5 let popular near-twin facts outrank the relevant one (Crucible L5b); 0.9 kept the critical probes
    floor: float = 0.9
    events: int = 50
    forgetting: bool = True
    # D-013
    act_mode: str = "mult"
    beta: float = 0.05
    s_noise: float = 1.0
    c: float = 0.217
    a: float = 0.177
    d_max: float = 1.0
    kappa: float = 0.4
    delta: float = 0.03
    band: float = 0.02
    separation: bool = True
    gamma: float = 0.15
    s_max: float = S_MAX_DEFAULT
    kw_bypass: str = "fact"
    # CROSS_CHECK §3.2: the context term as a sum of weighted cues
    cues: str = "entity+predicate"
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
        if self.act_mode not in MODES:
            raise ValueError("PLEXUS_ACT_MODE must be 'mult' or 'add'")
        if self.kw_bypass not in BYPASS_KINDS:
            raise ValueError("PLEXUS_KW_BYPASS must be 'fact' or 'value'")
        if self.cues not in CUE_MODES:
            raise ValueError("PLEXUS_ACT_CUES must be 'entity+predicate' or 'entity'")
        for name, v, lo, hi in (
            ("PLEXUS_ACT_BETA", self.beta, 0.0, 1.0),
            ("PLEXUS_ACT_GAMMA", self.gamma, 0.0, 1.0),
            ("PLEXUS_ACT_W_ENTITY", self.w_entity, 0.0, 10.0),
            ("PLEXUS_ACT_W_PREDICATE", self.w_predicate, 0.0, 10.0),
            ("PLEXUS_ACT_DELTA", self.delta, 0.0, 1.0),
            ("PLEXUS_ACT_BAND", self.band, 0.0, 1.0),
            ("PLEXUS_ACT_KAPPA", self.kappa, 0.0, 0.99),
            ("PLEXUS_ACT_C", self.c, 0.0, 2.0),
        ):
            if not lo <= v <= hi:
                raise ValueError(f"{name} must be between {lo:g} and {hi:g}")
        for name, v, lo, hi in (
            ("PLEXUS_ACT_S", self.s_noise, 0.0, 10.0),
            ("PLEXUS_ACT_A", self.a, 0.0, 2.0),
            ("PLEXUS_ACT_DMAX", self.d_max, 0.0, 2.0),
            ("PLEXUS_ACT_SMAX", self.s_max, 0.0, 20.0),
            ("PLEXUS_ACT_CUE_S", self.cue_s, 0.0, 20.0),
        ):
            if not lo < v <= hi:
                raise ValueError(f"{name} must be in ({lo:g}, {hi:g}]")
        if self.d_max < self.a:
            raise ValueError("PLEXUS_ACT_DMAX must be >= PLEXUS_ACT_A")

    @property
    def additive(self) -> bool:
        return self.act_mode == "add"

    @property
    def neutral(self) -> float:
        """``A0``: a fact created once, one day ago (under the active decay model), unless overridden."""
        if self.additive:
            return neutral_activation(self.a, self.a0)
        return neutral_activation(self.decay, self.a0)

    @property
    def sweep_margin(self) -> float:
        """``memory_sweep``'s default threshold is ``neutral - sweep_margin`` ("about 55-60 days unused")."""
        return SWEEP_MARGIN_ADD if self.additive else SWEEP_MARGIN_MULT

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
                act_mode=(get("PLEXUS_ACT_MODE") or "mult").lower(),
                beta=num("PLEXUS_ACT_BETA", 0.05),
                s_noise=num("PLEXUS_ACT_S", 1.0),
                c=num("PLEXUS_ACT_C", 0.217),
                a=num("PLEXUS_ACT_A", 0.177),
                d_max=num("PLEXUS_ACT_DMAX", 1.0),
                kappa=num("PLEXUS_ACT_KAPPA", 0.4),
                delta=num("PLEXUS_ACT_DELTA", 0.03),
                band=num("PLEXUS_ACT_BAND", 0.02),
                separation=separation,
                gamma=num("PLEXUS_ACT_GAMMA", 0.15),
                s_max=num("PLEXUS_ACT_SMAX", S_MAX_DEFAULT),
                kw_bypass=(get("PLEXUS_KW_BYPASS") or "fact").lower(),
                cues=(get("PLEXUS_ACT_CUES") or "entity+predicate").lower(),
                cue_s=num("PLEXUS_ACT_CUE_S", CUE_S_DEFAULT),
                w_entity=num("PLEXUS_ACT_W_ENTITY", W_ENTITY_DEFAULT),
                w_predicate=num("PLEXUS_ACT_W_PREDICATE", W_PREDICATE_DEFAULT),
            )
        except ValueError as exc:
            if "PLEXUS_" in str(exc):
                raise
            raise ValueError(f"invalid PLEXUS_ACT_* / PLEXUS_FORGETTING setting: {exc}") from None
