"""Small helpers shared by the Plexus services (Engram, Relay, Lineage, Staleness, Activation, Audit, API).

Dependency-free on purpose: every service imports from here, so this module imports nothing from Plexus.
"""

from __future__ import annotations

import time
import uuid
from collections.abc import Iterable
from dataclasses import dataclass, field
from typing import Any

OPEN = 9_999_999_999_999  # open-ended valid_to / "no review date" (FalkorDB cannot store null)


def now_ms() -> int:
    """Current time as epoch milliseconds (the unit of every timestamp in the graph)."""
    return time.time_ns() // 1_000_000


def new_id() -> str:
    """A fresh random UUID string, used for every node id Plexus creates."""
    return str(uuid.uuid4())


def normalize(text: str) -> str:
    """Case-folded, whitespace-collapsed form used as the entity MERGE key and for value equality."""
    return " ".join(text.split()).casefold()


def unique(values: Iterable[str] | None) -> list[str]:
    """``values`` without duplicates, first occurrence kept, order preserved (``None`` -> ``[]``)."""
    return list(dict.fromkeys(values or ()))


NO_STEP: dict[str, Any] = {"with_step": False, "step_id": "", "step_n": -1, "step_at": 0}


@dataclass
class StepIntent:
    """The Step a memory write should create in its own statement (P9-f, Crucible L6-F crash-consistency).

    The MCP runtime makes one per call (audit mode ``full``) and hands it to the tool on the metered client;
    a service that supports it passes :meth:`params` to its write query, which creates the agent's Step (or
    reuses an existing explicit step number) with ``BY`` / ``NEXT`` and the ``WROTE`` / ``READ`` edges in the
    SAME statement as the memory node, then records the Step id in :attr:`used_id`. ``n < 0`` = next step.
    """

    agent_id: str
    n: int
    at: int
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    used_id: str | None = None  # set by the service once its statement created or reused the Step

    def params(self, writer: str) -> dict[str, Any]:
        """Query parameters for a write by ``writer`` (no Step unless the writer is the intent's agent)."""
        if writer != self.agent_id:
            return dict(NO_STEP)
        return {"with_step": True, "step_id": self.id, "step_n": int(self.n), "step_at": int(self.at)}


def step_params(intent: StepIntent | None, writer: str) -> dict[str, Any]:
    """``intent.params(writer)``, or the no-Step parameters when there is no intent."""
    return dict(NO_STEP) if intent is None else intent.params(writer)


def check_between(name: str, value: int, maximum: int) -> None:
    """Raise ``ValueError('<name> must be between 1 and <maximum>')`` unless ``0 < value <= maximum``."""
    if not 0 < value <= maximum:
        raise ValueError(f"{name} must be between 1 and {maximum}")
