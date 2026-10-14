"""Engram service layer: Python wrappers around the named queries in ``queries/engram/``.

Every write is one Cypher statement (atomic; FalkorDB serialises writes per graph). Embeddings are made here
(local model, no LLM) and passed as parameters. Time is epoch milliseconds; ``now`` is injectable for tests.
"""

from __future__ import annotations

import json
import re
import time
import uuid
from typing import Any

from plexus.embed import Embedder, get_embedder
from plexus.graph.client import GraphClient

OPEN = 9_999_999_999_999  # open-ended valid_to (FalkorDB cannot store null)
NO_STEP = -1  # Episode.step when the caller has no step

ENTITY_NEAR = 0.15  # cosine distance: entity-name vector match
FACT_DUP = 0.08  # cosine distance: value paraphrase duplicate
FULLTEXT_JACCARD = 0.6  # token overlap needed to accept a full-text entity hit
EXPAND_BOOST = 0.05  # rank bonus for sibling facts reached through the ABOUT entity
OVERFETCH = 4  # vector seeds fetched = k * OVERFETCH

_WORD = re.compile(r"[^\W_]+", re.UNICODE)


def normalize(text: str) -> str:
    """Case-folded, whitespace-collapsed form used as the entity MERGE key and for value equality."""
    return " ".join(text.split()).casefold()


def _now_ms() -> int:
    return time.time_ns() // 1_000_000


def _new_id() -> str:
    return str(uuid.uuid4())


def _tokens(text: str) -> list[str]:
    return [t.casefold() for t in _WORD.findall(text)]


def _jaccard(a: set[str], b: set[str]) -> float:
    return len(a & b) / len(a | b) if (a | b) else 0.0


def fact_text(entity_name: str, predicate: str, value: str) -> str:
    return f"{entity_name} {predicate}: {value}"


class Engram:
    """Memory operations bound to one tenant graph (``graph``) on a :class:`GraphClient`."""

    def __init__(
        self,
        client: GraphClient,
        graph: str,
        embedder: Embedder | None = None,
        *,
        entity_threshold: float = ENTITY_NEAR,
        dup_threshold: float = FACT_DUP,
    ):
        self.client = client
        self.graph = graph
        self.embedder = embedder or get_embedder()
        self.entity_threshold = entity_threshold
        self.dup_threshold = dup_threshold

    # -- sessions and episodes -------------------------------------------------------------------------

    def start_session(
        self, agent_id: str, agent_role: str = "", *, harness: str = "", now: int | None = None
    ) -> str:
        """MERGE the Agent, create a Session + ``HAD`` edge. Returns the session id."""
        session_id = _new_id()
        rows = self.client.rw(
            self.graph,
            "engram/start_session",
            {
                "agent_id": agent_id,
                "agent_role": agent_role,
                "harness": harness,
                "session_id": session_id,
                "now": now if now is not None else _now_ms(),
            },
        )
        return rows[0]["session_id"]

    def remember_episode(
        self, session_id: str, role: str, text: str, step: int | None = None, *, now: int | None = None
    ) -> str:
        """Append an episode to the session chain (``HAS_EPISODE`` + ``NEXT``) in one statement."""
        episode_id = _new_id()
        rows = self.client.rw(
            self.graph,
            "engram/remember_episode",
            {
                "session_id": session_id,
                "episode_id": episode_id,
                "role": role,
                "text": text,
                "step": NO_STEP if step is None else step,
                "now": now if now is not None else _now_ms(),
                "emb": self.embedder.embed([text])[0],
            },
        )
        if not rows:
            raise LookupError(f"session '{session_id}' does not exist")
        return rows[0]["episode_id"]

    # -- entities --------------------------------------------------------------------------------------

    def resolve_entity_ex(self, name: str, kind: str = "thing", *, now: int | None = None) -> dict[str, Any]:
        """Resolve ``name`` to an Entity, creating it if needed.

        Order: exact normalised name -> full-text (token Jaccard >= 0.6, same kind) -> vector (distance <=
        ``entity_threshold``, same kind) -> ``MERGE (e:Entity {norm_name})``.

        Race behaviour: the lookups are reads, the create is an atomic MERGE on ``norm_name``. Two concurrent
        calls with the *same* name converge on one node. Two concurrent calls with *different* spellings of
        the same thing (a paraphrase) can both miss and create two entities; a later call resolves to the
        nearest (older) one but the two nodes are not merged.
        """
        norm = normalize(name)
        if not norm:
            raise ValueError("entity name must not be empty")

        hit = self.client.ro(self.graph, "engram/find_entity_exact", {"norm_name": norm})
        if hit:
            return {**hit[0], "created": False, "matched_by": "exact"}

        q_tokens = set(_tokens(name))
        if q_tokens:
            cands = self.client.ro(
                self.graph,
                "engram/find_entity_fulltext",
                {"q": " ".join(sorted(q_tokens)), "limit": 5},
            )
            best, best_j = None, 0.0
            for c in cands:
                if c["kind"] != kind:
                    continue
                j = _jaccard(q_tokens, set(_tokens(c["norm_name"] or c["name"])))
                if j >= FULLTEXT_JACCARD and j > best_j:
                    best, best_j = c, j
            if best:
                return {
                    "id": best["id"],
                    "name": best["name"],
                    "kind": best["kind"],
                    "created": False,
                    "matched_by": "fulltext",
                }

        emb = self.embedder.embed([name])[0]
        near = self.client.ro(self.graph, "engram/find_entity_vector", {"emb": emb, "k": 3})
        for c in near:
            if c["kind"] == kind and c["distance"] <= self.entity_threshold:
                return {
                    "id": c["id"],
                    "name": c["name"],
                    "kind": c["kind"],
                    "created": False,
                    "matched_by": "vector",
                }

        rows = self.client.rw(
            self.graph,
            "engram/upsert_entity",
            {
                "norm_name": norm,
                "entity_id": _new_id(),
                "name": " ".join(name.split()),
                "kind": kind,
                "emb": emb,
                "now": now if now is not None else _now_ms(),
            },
        )
        r = rows[0]
        return {
            "id": r["id"],
            "name": r["name"],
            "kind": r["kind"],
            "created": bool(r["created"]),
            "matched_by": "new" if r["created"] else "exact",
        }

    def resolve_entity(self, name: str, kind: str = "thing", *, now: int | None = None) -> str:
        """Entity id for ``name`` (existing or newly created). See :meth:`resolve_entity_ex`."""
        return self.resolve_entity_ex(name, kind, now=now)["id"]

    # -- scopes ----------------------------------------------------------------------------------------

    def create_scope(
        self, kind: str, name: str, inherits: list[str] | None = None, *, now: int | None = None
    ) -> str:
        """MERGE a Scope on (kind, name) and ``INHERITS`` edges to ``inherits`` (ids). Returns the scope id.

        Idempotent. Raises ``LookupError`` (and writes nothing) if an inherited scope does not exist.
        Cycles are not checked: recall follows at most 3 INHERITS hops, so a cycle only wastes work.
        """
        if kind not in ("user", "project", "global"):
            raise ValueError("scope kind must be 'user', 'project' or 'global'")
        parents = sorted(set(inherits or []))
        rows = self.client.rw(
            self.graph,
            "engram/create_scope",
            {
                "kind": kind,
                "name": name,
                "scope_id": _new_id(),
                "inherits": parents,
                "now": now if now is not None else _now_ms(),
            },
        )
        if not rows:
            raise LookupError("an inherited scope does not exist")
        return rows[0]["id"]

    # -- facts -----------------------------------------------------------------------------------------

    def assert_fact(
        self,
        subject: str,
        predicate: str,
        value: str,
        scope_id: str,
        agent_id: str,
        source_id: str | None = None,
        episode_id: str | None = None,
        confidence: float = 1.0,
        now: int | None = None,
        *,
        supersede: bool = False,
        subject_kind: str = "thing",
        step: int | None = None,  # noqa: ARG002 - reserved: Lineage appends the Step edges to the statement
    ) -> dict[str, Any]:
        """Assert ``subject predicate value`` in ``scope_id`` as ``agent_id``.

        Returns ``{fact_id, superseded, duplicate_of, contradicts, entity_id}``. For a duplicate no fact is
        created and ``fact_id == duplicate_of`` (the existing fact, which gains an ``ASSERTED_BY`` edge).
        The classification and the writes happen in one Cypher statement (``engram/assert_fact``); the
        entity resolution before it is a separate (idempotent) step.
        """
        pred = normalize(predicate)
        norm_value = normalize(value)
        if not pred or not norm_value:
            raise ValueError("predicate and value must not be empty")
        t = now if now is not None else _now_ms()
        entity = self.resolve_entity_ex(subject, subject_kind, now=t)
        text_emb, value_emb = self.embedder.embed([fact_text(entity["name"], pred, value), value])
        rows = self.client.rw(
            self.graph,
            "engram/assert_fact",
            {
                "entity_id": entity["id"],
                "predicate": pred,
                "value": " ".join(value.split()),
                "norm_value": norm_value,
                "scope_id": scope_id,
                "agent_id": agent_id,
                "source_id": source_id or "",
                "episode_id": episode_id or "",
                "confidence": float(confidence),
                "supersede": bool(supersede),
                "now": t,
                "open_to": OPEN,
                "fact_id": _new_id(),
                "emb": text_emb,
                "value_emb": value_emb,
                "dup_threshold": self.dup_threshold,
            },
        )
        if not rows:
            raise LookupError(f"scope '{scope_id}' does not exist")
        r = rows[0]
        return {
            "fact_id": r["fact_id"],
            "superseded": list(r["superseded"]),
            "duplicate_of": r["duplicate_of"],
            "contradicts": list(r["contradicts"]),
            "entity_id": entity["id"],
        }

    def fact_history(self, subject: str, predicate: str, scope_id: str) -> list[dict[str, Any]]:
        """All versions of (subject, predicate) in a scope, oldest first (does not create the entity)."""
        hit = self.client.ro(self.graph, "engram/find_entity_exact", {"norm_name": normalize(subject)})
        if not hit:
            return []
        return list(
            self.client.ro(
                self.graph,
                "engram/fact_history",
                {"entity_id": hit[0]["id"], "predicate": normalize(predicate), "scope_id": scope_id},
            )
        )

    # -- recall ----------------------------------------------------------------------------------------

    def recall(
        self,
        query: str,
        scope_id: str,
        k: int = 8,
        as_of: int | None = None,
        budget_chars: int = 2000,
    ) -> list[dict[str, Any]]:
        """Top-``k`` facts for ``query`` in ``scope_id`` (and the scopes it inherits), nearest first.

        ``as_of`` (epoch ms) returns what was valid at that time, including since-superseded versions; the
        default is "now" with active facts only. The text budget is applied here: results are kept in rank
        order until ``budget_chars`` is spent (the first result is truncated rather than dropped).
        Returns data only; recording a ``Recall`` node is Lineage's job.
        """
        if k <= 0:
            return []
        t = as_of if as_of is not None else _now_ms()
        rows = self.client.ro(
            self.graph,
            "engram/recall",
            {
                "q": self.embedder.embed([query])[0],
                "scope_id": scope_id,
                "over": k * OVERFETCH,
                "k": k,
                "t": t,
                "statuses": ["active"] if as_of is None else ["active", "superseded"],
                "boost": EXPAND_BOOST,
            },
        )
        out: list[dict[str, Any]] = []
        used = 0
        for r in rows:
            text = fact_text(r["entity_name"], r["predicate"], r["value"])
            if used + len(text) > budget_chars:
                if out:
                    break
                text = text[: max(budget_chars - 1, 0)] + "\u2026"  # first hit alone exceeds the budget
            used += len(text)
            path: list[dict[str, Any]] = [
                {"rel": "ABOUT", "label": "Entity", "id": r["entity_id"], "name": r["entity_name"]},
                {"rel": "IN_SCOPE", "label": "Scope", "id": r["scope_id"]},
            ]
            path += [{"rel": "DERIVED_FROM", "label": d["label"], "id": d["id"]} for d in r["derived_from"]]
            path += [{"rel": "ASSERTED_BY", "label": "Agent", "id": a} for a in r["asserted_by"]]
            out.append(
                {
                    "fact_id": r["fact_id"],
                    "text": text,
                    "score": r["score"],
                    "path": path,
                    "entity": r["entity_name"],
                    "predicate": r["predicate"],
                    "value": r["value"],
                    "status": r["status"],
                    "valid_from": r["valid_from"],
                    "valid_to": r["valid_to"],
                    "via": r["via"],
                }
            )
            if used >= budget_chars:
                break
        return out

    # -- procedures ------------------------------------------------------------------------------------

    def log_procedure_run(
        self,
        procedure_name: str,
        task_type: str,
        agent_id: str,
        success: bool,
        task_id: str | None = None,
        notes: str = "",
        *,
        steps: list[str] | None = None,
        now: int | None = None,
        step: int | None = None,  # noqa: ARG002 - reserved for Lineage
    ) -> str:
        """Record one run of a procedure (MERGE Procedure, create Run). Returns the run id."""
        rows = self.client.rw(
            self.graph,
            "engram/log_procedure_run",
            {
                "procedure_name": procedure_name,
                "task_type": task_type,
                "procedure_id": _new_id(),
                "steps_json": json.dumps(steps or []),
                "run_id": _new_id(),
                "agent_id": agent_id,
                "task_id": task_id or "",
                "success": bool(success),
                "notes": notes,
                "now": now if now is not None else _now_ms(),
            },
        )
        return rows[0]["run_id"]

    def best_procedure(self, task_type: str, min_runs: int = 1, limit: int = 5) -> list[dict[str, Any]]:
        """Procedures for ``task_type`` ordered by success rate, then run count (then name)."""
        return list(
            self.client.ro(
                self.graph,
                "engram/best_procedure",
                {"task_type": task_type, "min_runs": min_runs, "limit": limit},
            )
        )
