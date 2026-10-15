"""Activation service: gathers events with ``activation/activation`` and computes A(f) in Python (D-012).

Read-only apart from the explicit pin / sweep / restore operations (added in later slices). Nothing is written
when a fact is read or recalled.
"""

from __future__ import annotations

import time
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass, field
from typing import Any

from plexus.activation import model
from plexus.activation.model import Event
from plexus.activation.settings import Settings
from plexus.graph.client import GraphClient

MAX_IDS = 200  # fact ids per activation query

_WEIGHTS = {
    "create": model.W_CREATE,
    "reassert": model.W_REASSERT,
    "decision": model.W_DECISION,
    "handoff": model.W_HANDOFF,
    "use": model.W_USE,
    "recall": model.W_RECALL,
    "verified": model.W_VERIFIED,
}


def _now_ms() -> int:
    return time.time_ns() // 1_000_000


@dataclass
class FactActivation:
    """What the model knows about one fact at one moment."""

    fact_id: str
    status: str
    created_at: int
    surprise: float
    pinned: bool
    verify_state: str
    suspect_since: int
    verify_after: int
    events: list[Event]  # the events that count (newest first, recall events after suspect_since removed)
    activation: float
    protected: bool
    protect_reasons: list[str] = field(default_factory=list)


class Activation:
    """Activation reads bound to one tenant graph."""

    def __init__(
        self,
        client: GraphClient,
        graph: str,
        settings: Settings | None = None,
        clock: Callable[[], int] = _now_ms,
    ):
        self.client = client
        self.graph = graph
        self.settings = settings or Settings.from_env()
        self._clock = clock

    def compute(self, fact_ids: Iterable[str], now: int | None = None) -> dict[str, FactActivation]:
        """Activation, protection and events for ``fact_ids`` (any number; queried 200 at a time).

        Unknown ids are absent from the result. A suspect fact (``verify_state = 'suspect'``) ignores the
        ``recall`` events after its ``suspect_since``: being surfaced does not strengthen a doubted fact.
        """
        t = self._clock() if now is None else now
        ids = list(dict.fromkeys(fact_ids))
        out: dict[str, FactActivation] = {}
        for i in range(0, len(ids), MAX_IDS):
            rows = self.client.ro(
                self.graph,
                "activation/activation",
                {"fact_ids": ids[i : i + MAX_IDS], "now": t, "events": self.settings.events},
            )
            for r in rows:
                out[r["id"]] = self._one(r, t)
        return out

    def _one(self, r: Mapping[str, Any], now: int) -> FactActivation:
        created = int(r["created_at"])
        events = [Event("create", created, _WEIGHTS["create"])]
        events += [Event(e["k"], e["t"], _WEIGHTS[e["k"]]) for e in r["reads"]]
        events += [Event("reassert", t, _WEIGHTS["reassert"]) for t in r["asserted_at"] if created < t <= now]
        events += [Event("decision", d["t"], _WEIGHTS["decision"]) for d in r["decisions"] if d["t"] <= now]
        events += [Event("handoff", h["t"], _WEIGHTS["handoff"]) for h in r["handoffs"] if h["t"] <= now]
        events += [Event("verified", t, _WEIGHTS["verified"]) for t in r["verified_at"] if t <= now]
        if r["verify_state"] == "suspect":  # a doubted fact is not strengthened by being surfaced
            events = [e for e in events if not (e.kind == "recall" and e.t > r["suspect_since"])]
        events.sort(key=lambda e: e.t, reverse=True)
        events = events[: self.settings.events]
        reasons: list[str] = []
        if r["pinned"]:
            reasons.append("pinned")
        reasons += [f"decision:{d['id']}" for d in r["decisions"] if not d["flagged"]][:1]
        reasons += [f"handoff:{h['id']}" for h in r["handoffs"]][:1]
        reasons += [f"supersedes:{x}" for x in r["supersedes"]][:1]
        reasons += [f"contradicts:{x}" for x in r["contradicts"]][:1]
        reasons += [f"trusted_source:{s['id']}" for s in r["sources"] if s["trust"] == "high"][:1]
        return FactActivation(
            fact_id=r["id"],
            status=r["status"],
            created_at=r["created_at"],
            surprise=float(r["surprise"]),
            pinned=bool(r["pinned"]),
            verify_state=r["verify_state"],
            suspect_since=int(r["suspect_since"]),
            verify_after=int(r["verify_after"]),
            events=events,
            activation=model.activation(
                events,
                now=now,
                created_at=r["created_at"],
                surprise=float(r["surprise"]),
                decay=self.settings.decay,
                max_events=self.settings.events,
            ),
            protected=bool(reasons),
            protect_reasons=reasons,
        )
