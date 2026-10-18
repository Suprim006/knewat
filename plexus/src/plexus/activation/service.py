"""Activation service: gathers events with ``activation/activation`` and computes A(f) in Python (D-012).

Read-only apart from the explicit pin / sweep / restore operations. Nothing is written when a fact is read or
recalled, and nothing here ever deletes: a sweep only moves facts to ``dormant`` and ``restore`` undoes it.
"""

from __future__ import annotations

import math
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass, field
from typing import Any

from plexus.activation import model
from plexus.activation import score as score_mod
from plexus.activation.model import Event
from plexus.activation.settings import Settings
from plexus.common import check_between, now_ms, unique
from plexus.graph.client import GraphClient

MAX_IDS = 200  # fact ids per activation query
MAX_SWEEP_SCAN = 5000  # active facts of a scope that one sweep looks at (oldest first)
# D-013, add mode only: salience >= SALIENCE_PROTECT protects from sweeps (the boolean rules stay the floor)
SALIENCE_PROTECT = 0.5

_WEIGHTS = {
    "create": model.W_CREATE,
    "reassert": model.W_REASSERT,
    "decision": model.W_DECISION,
    "handoff": model.W_HANDOFF,
    "use": model.W_USE,
    "recall": model.W_RECALL,
    "verified": model.W_VERIFIED,
}


# D-013 salience weights (docs/research/neuro-memory/05-salience-and-emotional-tagging.md §3.1)
SALIENCE_W = {
    "decisions": 1.0,  # unflagged decisions BASED_ON the fact
    "verified": 1.5,  # VERIFIED_BY confirmations
    "artifacts_ok": 1.0,  # independently verified artifacts of the decisions' tasks
    "tasks_done": 0.5,  # done tasks of those decisions
    "use_agents": 0.5,  # distinct agents that used it, minus one
    "handoffs": 0.5,
    "trusted_source": 1.0,
    "pinned": 3.0,
}


def salience_of(r: Mapping[str, Any], now: int) -> tuple[float, dict[str, int]]:
    """Graded salience ``1 - exp(-sum(w * count))`` of one ``activation/activation`` row, and its inputs.

    Pure graph structure, no LLM: what was decided on, verified, handed over, used by several agents, built
    and independently checked downstream, pinned, or derived from a trusted source. Events after ``now`` do
    not count. Never fed into ``confidence`` (note 05 §3.5).
    """
    decisions = [d for d in r["decisions"] if d["t"] <= now]
    inputs = {
        "decisions": sum(1 for d in decisions if not d["flagged"]),
        "verified": sum(1 for t in r["verified_at"] if t <= now),
        # distinct independently verified artifacts of the decision's DONE tasks (audit C1: the query returns
        # one id per VERIFIED_BY path; an artifact verified by two agents is one artifact)
        "artifacts_ok": sum(
            len(set(d.get("verified_artifacts") or ())) for d in decisions if not d["flagged"]
        ),
        "tasks_done": sum(int(d.get("tasks_done") or 0) for d in decisions if not d["flagged"]),
        "use_agents": max(
            0, len({e.get("ag") for e in r["reads"] if e["k"] == "use" and e.get("ag") and e["t"] <= now}) - 1
        ),
        "handoffs": sum(1 for h in r["handoffs"] if h["t"] <= now),
        "trusted_source": int(any(s["trust"] == "high" for s in r["sources"])),
        "pinned": int(bool(r["pinned"])),
    }
    total = sum(SALIENCE_W[k] * v for k, v in inputs.items())
    return (1.0 - math.exp(-total)) if total > 0 else 0.0, inputs


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
    salience: float = 0.0  # D-013 graded salience in [0, 1), from the graph (docs/forgetting.md)
    salience_inputs: dict[str, int] = field(default_factory=dict)
    decays: list[float] = field(default_factory=list)  # per counted event (oldest first), add mode only


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

        Unknown ids are absent from the result. ``recall`` events that happened while the fact was doubted
        (``READ.suspect``: the contract rule at the time of the READ) do not count: being surfaced does not
        strengthen a doubted fact, and verifying it later does not undo that.
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

    @staticmethod
    def _doubted(read: Mapping[str, Any], r: Mapping[str, Any]) -> bool:
        """Was the fact suspect (contract rule) when this recall READ happened?

        ``READ.suspect`` records it at write time (edges since P7-04). The fact's current state also counts,
        so a back-dated doubt (``mark_changed`` at a commit time earlier than the recall) and edges written
        before the flag existed are covered: suspect since before the read, or a review date at or before it.
        """
        if read["s"] == 1:
            return True
        late = r["verify_state"] == "suspect" and read["t"] > r["suspect_since"]
        return late or r["verify_after"] <= read["t"]

    def _one(self, r: Mapping[str, Any], now: int) -> FactActivation:
        created = int(r["created_at"])
        st = self.settings
        sal, sal_in = salience_of(r, now)
        events = [Event("create", created, _WEIGHTS["create"])]
        # a doubted fact is not strengthened by being surfaced: recalls taken while suspect do not count
        events += [
            Event(e["k"], e["t"], _WEIGHTS[e["k"]])
            for e in r["reads"]
            if not (e["k"] == "recall" and self._doubted(e, r))
        ]
        events += [Event("reassert", t, _WEIGHTS["reassert"]) for t in r["asserted_at"] if created < t <= now]
        events += [Event("decision", d["t"], _WEIGHTS["decision"]) for d in r["decisions"] if d["t"] <= now]
        events += [Event("handoff", h["t"], _WEIGHTS["handoff"]) for h in r["handoffs"] if h["t"] <= now]
        events += [Event("verified", t, _WEIGHTS["verified"]) for t in r["verified_at"] if t <= now]
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
        # D-013 P2 rule, gated on the mode: `mult` is D-012 + the bypass fix + separation and nothing else
        # (BRANCH_REVIEW finding 1; D-013 amendment). Salience is still computed and reported in both modes.
        if st.additive and sal >= SALIENCE_PROTECT and not reasons:
            reasons.append(f"salience:{sal:.2f}")
        decays: list[float] = []
        if st.additive:
            act, decays = model.activation_spaced(
                events,
                now=now,
                created_at=created,
                surprise=float(r["surprise"]),
                c=st.c,
                a=st.a,
                d_max=st.d_max,
                kappa_s=st.kappa * sal,
                a0=st.neutral,
                max_events=st.events,
            )
        else:
            act = model.activation(
                events,
                now=now,
                created_at=created,
                surprise=float(r["surprise"]),
                decay=st.decay,
                max_events=st.events,
            )
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
            activation=act,
            protected=bool(reasons),
            protect_reasons=reasons,
            entity=r["entity"] or "",
            predicate=r["predicate"] or "",
            value=r["value"] or "",
            salience=sal,
            salience_inputs=sal_in,
            decays=decays,
        )

    # -- pin ---------------------------------------------------------------------------------------------
    def pin(self, fact_id: str, pinned: bool = True) -> bool:
        """Pin (or unpin) a fact. Returns False when there is no such fact (nothing written)."""
        rows = self.client.rw(
            self.graph,
            "activation/pin",
            {"fact_id": fact_id, "pinned": bool(pinned), "now": self._clock()},
        )
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
        fan = self._fan(fact_id)
        st = self.settings
        a0 = st.neutral
        if st.additive:
            act_term = score_mod.act_term(fa.activation, a0, beta=st.beta, s_noise=st.s_noise)
            mult = math.exp(act_term)
        else:
            act_term = None
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
            # D-013
            "mode": st.act_mode,
            "act_term": act_term,
            "salience": fa.salience,
            "salience_inputs": fa.salience_inputs,
            "decays": [round(d, 3) for d in fa.decays],
            "fan": fan,
            "entity_lift": (
                score_mod.context_term(
                    True,
                    fan,
                    cues=st.cues,
                    gamma=st.gamma,
                    s_max=st.s_max,
                    w_entity=st.w_entity,
                    w_predicate=st.w_predicate,
                    s=st.cue_s,
                )
                if fan
                else 0.0
            ),
            "suggested_verify_after": (
                self._suggest_verify_after(fa, t) if fa.salience >= SALIENCE_PROTECT else None
            ),
            "explanation": _explain(fa, counts, last, t, a0, mult, finite),
        }

    def _fan(self, fact_id: str) -> int:
        rows = self.client.ro(self.graph, "activation/entity_fan", {"fact_id": fact_id})
        return int(rows[0]["fan"]) if rows else 0

    def _activation_at(self, fa: FactActivation, t: int) -> float:
        st = self.settings
        if st.additive:
            return model.activation_spaced(
                fa.events,
                now=t,
                created_at=fa.created_at,
                surprise=fa.surprise,
                c=st.c,
                a=st.a,
                d_max=st.d_max,
                kappa_s=st.kappa * fa.salience,
                a0=st.neutral,
                max_events=st.events,
            )[0]
        return model.activation(
            fa.events,
            now=t,
            created_at=fa.created_at,
            surprise=fa.surprise,
            decay=st.decay,
            max_events=st.events,
        )

    def _suggest_verify_after(self, fa: FactActivation, now: int) -> int | None:
        """When this fact's activation would cross the sweep threshold if nobody touches it (epoch ms).

        A review-date suggestion for salient facts (plan §3.3): reported by ``memory_strength``, never
        written.
        ``None`` when the fact stays above the threshold for a year; ``now`` when it is already below.
        """
        thr = self.settings.neutral - self.settings.sweep_margin
        if fa.activation < thr:
            return now
        lo, hi = now, now + 365 * model.DAY_MS
        if self._activation_at(fa, hi) >= thr:
            return None
        for _ in range(24):  # bisection to about an hour
            mid = (lo + hi) // 2
            if self._activation_at(fa, mid) >= thr:
                lo = mid
            else:
                hi = mid
        return hi

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
        thr = self.settings.neutral - self.settings.sweep_margin if threshold is None else float(threshold)
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
        derived from a forgotten or quarantined fact (it stays dormant), and one that a newer active fact of
        the same entity, predicate and scope has replaced (``reason = 'already_superseded'``,
        ``superseded_by`` lists the newer facts; a recorded ``CONTRADICTS`` does not block).
        """
        rows = self.client.rw(self.graph, "activation/restore", {"fact_id": fact_id})
        if not rows:
            return None
        r = rows[0]
        out: dict[str, Any] = {
            "fact_id": r["id"],
            "restored": r["was"] == "dormant" and r["status"] != "dormant",
            "status": r["status"],
            "was": r["was"],
        }
        if r["superseded_by"]:  # a newer current fact exists: reviving this one would give two live values
            out["reason"] = "already_superseded"
            out["superseded_by"] = list(r["superseded_by"])
        return out


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
