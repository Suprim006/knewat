"""Activation service: gathers events with ``activation/activation`` and computes A(f) in Python (D-012).

Read-only apart from the explicit pin / sweep / restore operations. Nothing is written when a fact is read or
recalled, and nothing here ever deletes: a sweep only moves facts to ``dormant`` and ``restore`` undoes it.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass, field
from typing import Any

from plexus.activation import model
from plexus.activation.model import Event
from plexus.activation.settings import Settings
from plexus.common import check_between, now_ms, unique
from plexus.graph.client import GraphClient

MAX_IDS = 200  # fact ids per activation query
MAX_SWEEP_SCAN = 5000  # active facts of a scope that one sweep looks at (oldest first)
SWEEP_MARGIN = 2.0  # default threshold = A0 - 2

_WEIGHTS = {
    "create": model.W_CREATE,
    "reassert": model.W_REASSERT,
    "decision": model.W_DECISION,
    "handoff": model.W_HANDOFF,
    "use": model.W_USE,
    "recall": model.W_RECALL,
    "verified": model.W_VERIFIED,
}


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
    entity: str = ""
    predicate: str = ""
    value: str = ""


class Activation:
    """Activation reads bound to one tenant graph."""

    def __init__(
        self,
        client: GraphClient,
        graph: str,
        settings: Settings | None = None,
        clock: Callable[[], int] = now_ms,
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
        ids = unique(fact_ids)
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
            entity=r["entity"] or "",
            predicate=r["predicate"] or "",
            value=r["value"] or "",
        )

    # -- pin ---------------------------------------------------------------------------------------------
    def pin(self, fact_id: str, pinned: bool = True) -> bool:
        """Pin (or unpin) a fact. Returns False when there is no such fact (nothing written)."""
        rows = self.client.rw(self.graph, "activation/pin", {"fact_id": fact_id, "pinned": bool(pinned)})
        return bool(rows)

    # -- strength ----------------------------------------------------------------------------------------
    def strength(self, fact_id: str, now: int | None = None) -> dict[str, Any] | None:
        """Everything the ranking knows about one fact, with a one-line explanation; ``None`` if unknown.

        Read-only: asking does not count as using the fact.
        """
        t = self._clock() if now is None else now
        fa = self.compute([fact_id], t).get(fact_id)
        if fa is None:
            return None
        st = self.settings
        a0 = st.neutral
        mult = model.multiplier(fa.activation, a0, st.floor, protected=fa.protected)
        counts = {k: 0 for k in _WEIGHTS}
        last: dict[str, int] = {}
        for e in fa.events:  # newest first
            counts[e.kind] += 1
            last.setdefault(e.kind, e.t)
        finite = fa.activation != float("-inf")
        return {
            "fact_id": fa.fact_id,
            "status": fa.status,
            "activation": fa.activation if finite else None,
            "a0": a0,
            "multiplier": mult,
            "floor": st.floor,
            "decay": st.decay,
            "protected": fa.protected,
            "protect_reasons": fa.protect_reasons,
            "pinned": fa.pinned,
            "surprise": fa.surprise,
            "created_at": fa.created_at,
            "verify_state": fa.verify_state,
            "suspect_since": fa.suspect_since,
            "counts": counts,
            "events_considered": len(fa.events),
            "last_use": last.get("use"),
            "last_recall": last.get("recall"),
            "explanation": _explain(fa, counts, last, t, a0, mult, finite),
        }

    # -- sweep -------------------------------------------------------------------------------------------
    def sweep(
        self,
        scope_id: str,
        threshold: float | None = None,
        dry_run: bool = True,
        limit: int = 200,
        now: int | None = None,
        scan: int = MAX_SWEEP_SCAN,
    ) -> dict[str, Any]:
        """List (and with ``dry_run=False`` move to ``dormant``) the faintest unprotected facts of one scope.

        Looks at the ``scan`` oldest active facts of ``scope_id`` itself, keeps those that are not protected,
        not suspect and have ``A < threshold`` (default ``A0 - 2``), and takes the ``limit`` faintest. A real
        run moves them in ONE bounded statement that re-checks protection, so a fact that became protected
        since the listing is skipped. Never deletes; ``restore`` puts a fact back.
        """
        check_between("limit", limit, MAX_IDS)
        check_between("scan", scan, MAX_SWEEP_SCAN)
        t = self._clock() if now is None else now
        thr = self.settings.neutral - SWEEP_MARGIN if threshold is None else float(threshold)
        ids = [
            r["id"]
            for r in self.client.ro(
                self.graph, "activation/scope_facts", {"scope_id": scope_id, "scan": scan}
            )
        ]
        faint: list[FactActivation] = []
        for fa in self.compute(ids, t).values():
            suspect = fa.verify_state == "suspect" or fa.verify_after <= t
            if not fa.protected and not suspect and fa.activation < thr:
                faint.append(fa)
        faint.sort(key=lambda f: (f.activation, f.created_at, f.fact_id))
        chosen = faint[:limit]
        moved = self.apply_sweep([f.fact_id for f in chosen], t) if (chosen and not dry_run) else []
        return {
            "scope_id": scope_id,
            "threshold": thr,
            "dry_run": dry_run,
            "scanned": len(ids),
            "scan_truncated": len(ids) >= scan,
            "candidates": [
                {
                    "fact_id": f.fact_id,
                    "text": f"{f.entity} {f.predicate}: {f.value}",
                    "activation": f.activation,
                    "created_at": f.created_at,
                }
                for f in chosen
            ],
            "would_move": len(chosen),
            "moved": moved,
            "skipped": len(chosen) - len(moved) if not dry_run else 0,
            "truncated": len(faint) > limit or len(ids) >= scan,
        }

    def apply_sweep(self, fact_ids: Iterable[str], now: int | None = None) -> list[str]:
        """Move these facts to ``dormant`` if they are still active and unprotected (one statement per 200).

        Returns the ids that were moved. Protection is re-checked inside the statement; the activation
        threshold is the caller's decision.
        """
        t = self._clock() if now is None else now
        ids = unique(fact_ids)
        moved: list[str] = []
        for i in range(0, len(ids), MAX_IDS):
            rows = self.client.rw(
                self.graph, "activation/sweep_apply", {"fact_ids": ids[i : i + MAX_IDS], "now": t}
            )
            moved += [r["id"] for r in rows]
        return moved

    def restore(self, fact_id: str) -> dict[str, Any] | None:
        """Bring a dormant fact back to its previous status. ``None`` if there is no such fact.

        A fact that is not dormant is left alone and reported with ``restored = False``; so is a dormant fact
        derived from a forgotten or quarantined fact (it stays dormant).
        """
        rows = self.client.rw(self.graph, "activation/restore", {"fact_id": fact_id})
        if not rows:
            return None
        r = rows[0]
        return {
            "fact_id": r["id"],
            "restored": r["was"] == "dormant" and r["status"] != "dormant",
            "status": r["status"],
            "was": r["was"],
        }


def _ago(ms: int) -> str:
    """``1 hour ago`` / ``3 days ago`` for a non-negative age in milliseconds."""
    s = max(ms, 0) // 1000
    for unit, size in (("day", 86_400), ("hour", 3_600), ("minute", 60)):
        if s >= size:
            n = s // size
            return f"{n} {unit}{'' if n == 1 else 's'} ago"
    return "just now"


def _explain(
    fa: FactActivation,
    counts: dict[str, int],
    last: dict[str, int],
    now: int,
    a0: float,
    mult: float,
    finite: bool,
) -> str:
    use = f"last use {_ago(now - last['use'])}" if "use" in last else "never used"
    protected = "; protected: " + ", ".join(fa.protect_reasons) if fa.protected else "; not protected"
    suspect = "; suspect (recalls do not strengthen it)" if fa.verify_state == "suspect" else ""
    act = f"activation {fa.activation:.2f}" if finite else "activation -inf"
    return (
        f"recalled {counts['recall']}x, used {counts['use']}x, {use}; created {_ago(now - fa.created_at)}; "
        f"{act} vs neutral {a0:.2f}, ranking multiplier {mult:.2f}{protected}{suspect}"
    )
