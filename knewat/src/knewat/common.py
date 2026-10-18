"""Small helpers shared by the Plexus services (Engram, Relay, Lineage, Staleness, Activation, Audit, API).

Dependency-free on purpose: every service imports from here, so this module imports nothing from Plexus.
"""

from __future__ import annotations

import time
import uuid
from collections.abc import Iterable

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


def check_between(name: str, value: int, maximum: int) -> None:
    """Raise ``ValueError('<name> must be between 1 and <maximum>')`` unless ``0 < value <= maximum``."""
    if not 0 < value <= maximum:
        raise ValueError(f"{name} must be between 1 and {maximum}")
