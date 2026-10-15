"""Engram service layer: Python wrappers around the named queries in ``queries/engram/``.

Every write is one Cypher statement (atomic; FalkorDB serialises writes per graph). Embeddings are made here
(local model, no LLM) and passed as parameters. Time is epoch milliseconds; ``now`` is injectable for tests.
"""

from __future__ import annotations

import json
import re
import time
import uuid
from collections.abc import Callable
from typing import Any

from redis.exceptions import ResponseError

from plexus.activation import model as act
from plexus.activation.rank import rerank
from plexus.activation.service import Activation
from plexus.activation.settings import Settings
from plexus.embed import Embedder, embed_checked, get_embedder
from plexus.engram.errors import UnknownReference
from plexus.graph.client import GraphClient

OPEN = 9_999_999_999_999  # open-ended valid_to (FalkorDB cannot store null)
NO_STEP = -1  # Episode.step when the caller has no step

ENTITY_NEAR = 0.10  # cosine distance: entity-name vector match (and the numeric tokens must agree)
FACT_DUP = 0.08  # cosine distance: value paraphrase duplicate (and the numeric tokens must agree)
FULLTEXT_JACCARD = 0.6  # token overlap needed to accept a full-text entity hit
EXPAND_BOOST = 0.05  # rank bonus for sibling facts reached through the ABOUT entity
OVERFETCH = 4  # first vector fetch = k * OVERFETCH; each retry multiplies by RETRY_FACTOR
RETRY_FACTOR = 4
MAX_OVER = 512  # hard cap on the vector fetch size
MAX_K = 50  # recall clamps k to this
MAX_BUDGET_CHARS = 20_000  # recall clamps budget_chars to this
SIBLINGS_PER_ENTITY = 5  # 1-hop expansion keeps the nearest 5 sibling facts per seed
MAX_KEYWORDS = 10  # distinct query words sent to the Fact.value full-text index
DEFAULT_HISTORY = 200  # fact_history default
MAX_HISTORY = 10_000  # fact_history ceiling: versions of ONE entity+predicate in one scope

_WORD = re.compile(r"[^\W_]+", re.UNICODE)
_NUMBER = re.compile(r"\d+(?:\.\d+)*")  # 16, 8080, 1.2.3 (a trailing '.' is not part of the number)


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


def numeric_tokens(text: str) -> list[str]:
    """Sorted multiset of the numbers / version strings in ``text``.

    ``'v1.2.3 on 8080'`` -> ``['1.2.3', '8080']``.

    Embeddings barely move when one digit changes, so two values or entity names are only treated as the same
    thing when this multiset is identical (P1-01, P1-04).
    """
    return sorted(_NUMBER.findall(text))


def token_key(text: str) -> str:
    """:func:`numeric_tokens` joined by spaces; stored as ``Fact.value_tokens`` and compared by equality."""
    return " ".join(numeric_tokens(text))


def _query_words(query: str) -> list[str]:
    """The query words the full-text side searches for (>= 3 characters, at most ``MAX_KEYWORDS``)."""
    return list(dict.fromkeys(w for w in _tokens(query) if len(w) >= 3))[:MAX_KEYWORDS]


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

    def _embed(self, texts: list[str]) -> list[list[float]]:
        """Embed ``texts`` and refuse a vector that is not 384 floats (FalkorDB would store it silently)."""
        return embed_checked(self.embedder, texts)

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
                "emb": self._embed([text])[0],
            },
        )
        if not rows:
            raise LookupError(f"session '{session_id}' does not exist")
        return rows[0]["episode_id"]

    # -- entities --------------------------------------------------------------------------------------

    def resolve_entity_ex(
        self,
        name: str,
        kind: str = "thing",
        *,
        now: int | None = None,
        before_create: Callable[[], None] | None = None,
    ) -> dict[str, Any]:
        """Resolve ``name`` to an Entity, creating it if needed.

        ``before_create`` runs right before the only write (the ``upsert_entity`` MERGE), i.e. only when no
        existing entity matched. :meth:`assert_fact` uses it to reject a bad scope / episode / source *before*
        an Entity is created for a call that will be rejected (P5 review Q8).

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

        num_key = token_key(name)  # entities that differ only in numbers/versions are different things
        q_tokens = set(_tokens(name))
        if q_tokens:
            cands = self.client.ro(
                self.graph,
                "engram/find_entity_fulltext",
                {"q": " ".join(sorted(q_tokens)), "limit": 5},
            )
            best, best_j = None, 0.0
            for c in cands:
                if c["kind"] != kind or token_key(c["name"]) != num_key:
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

        emb = self._embed([name])[0]
        near = self.client.ro(self.graph, "engram/find_entity_vector", {"emb": emb, "k": 3})
        for c in near:
            if (
                c["kind"] == kind
                and c["distance"] <= self.entity_threshold
                and token_key(c["name"]) == num_key
            ):
                return {
                    "id": c["id"],
                    "name": c["name"],
                    "kind": c["kind"],
                    "created": False,
                    "matched_by": "vector",
                }

        if before_create is not None:
            before_create()
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
        dup_threshold: float | None = None,
    ) -> dict[str, Any]:
        """Assert ``subject predicate value`` in ``scope_id`` as ``agent_id``.

        Returns ``{fact_id, superseded, duplicate_of, contradicts, entity_id, surprise}``. ``surprise`` is the
        value stored on the new fact (0.9 contradiction, 0.6 supersede, else novelty in 0..0.5; ``None`` for a
        duplicate, which stores nothing). For a duplicate no fact is
        created and ``fact_id == duplicate_of`` (the existing fact, which gains an ``ASSERTED_BY {at}`` edge
        and supersedes this agent's own earlier, different current facts: ``superseded`` lists them).

        ``dup_threshold`` overrides the service's paraphrase threshold for this call (a negative value turns the
        paraphrase check off, so only an equal normalised value is a duplicate; ``verify_fact`` uses it, because an agent
        that corrects a clause of a long fact means a different fact).

        A value is a duplicate only if its normalised text is equal, or its embedding is within
        ``dup_threshold`` **and** its numeric/version tokens are identical (``16`` != ``15``, ``v1.2.3`` !=
        ``v1.2.4``); anything else follows the update / contradiction path.

        Raises :class:`UnknownReference` (a ``LookupError``) and writes nothing if the scope, or a given
        ``episode_id`` / ``source_id``, does not exist: a new subject Entity is only created after those ids
        were checked, so a rejected call leaves no orphan Entity (P5 Q8).
        The classification and the writes happen in one Cypher statement (``engram/assert_fact``); the
        entity resolution before it is a separate (idempotent) step.
        """
        pred = normalize(predicate)
        norm_value = normalize(value)
        if not pred or not norm_value:
            raise ValueError("predicate and value must not be empty")
        t = now if now is not None else _now_ms()
        episode_id, source_id = episode_id or "", source_id or ""
        entity = self.resolve_entity_ex(
            subject,
            subject_kind,
            now=t,
            before_create=lambda: self._check_refs(scope_id, episode_id, source_id),
        )
        text_emb, value_emb = self._embed([fact_text(entity["name"], pred, value), value])
        novelty = self._novelty(text_emb, scope_id)
        rows = self.client.rw(
            self.graph,
            "engram/assert_fact",
            {
                "entity_id": entity["id"],
                "predicate": pred,
                "value": " ".join(value.split()),
                "norm_value": norm_value,
                "value_tokens": token_key(value),
                "scope_id": scope_id,
                "agent_id": agent_id,
                "source_id": source_id,
                "episode_id": episode_id,
                "confidence": float(confidence),
                "supersede": bool(supersede),
                "now": t,
                "open_to": OPEN,
                "fact_id": _new_id(),
                "emb": text_emb,
                "value_emb": value_emb,
                "dup_threshold": self.dup_threshold if dup_threshold is None else dup_threshold,
                "novelty": novelty,
                "surprise_supersede": act.SURPRISE_SUPERSEDE,
                "surprise_contradict": act.SURPRISE_CONTRADICT,
            },
        )
        if not rows:
            self._check_refs(scope_id, episode_id, source_id)
            raise RuntimeError("assert_fact rejected although every referenced id exists")  # pragma: no cover
        r = rows[0]
        return {
            "fact_id": r["fact_id"],
            "superseded": list(r["superseded"]),
            "duplicate_of": r["duplicate_of"],
            "contradicts": list(r["contradicts"]),
            "entity_id": entity["id"],
            "surprise": r["surprise"],
        }

    def _novelty(self, text_emb: list[float], scope_id: str) -> float:
        """Write-time novelty: one bounded vector read (k=5 nearest active facts of the scope)."""
        near = self.client.ro(
            self.graph,
            "activation/novelty",
            {"q": text_emb, "scope_id": scope_id, "over": act.NOVELTY_OVER, "k": act.NOVELTY_K},
        )
        return act.novelty(near[0]["distance"] if near else None)

    def _check_refs(self, scope_id: str, episode_id: str, source_id: str) -> None:
        """Raise :class:`UnknownReference` for the first scope / episode / source id that does not exist."""
        have = self.client.ro(
            self.graph,
            "engram/missing_refs",
            {"scope_id": scope_id, "episode_id": episode_id, "source_id": source_id},
        )[0]
        if not have["scopes"]:
            raise UnknownReference("scope", [scope_id])
        if episode_id and not have["episodes"]:
            raise UnknownReference("episode", [episode_id])
        if source_id and not have["sources"]:
            raise UnknownReference("source", [source_id])

    def fact_history(
        self, subject: str, predicate: str, scope_id: str, limit: int = DEFAULT_HISTORY
    ) -> list[dict[str, Any]]:
        """Versions of (subject, predicate) in a scope, oldest first (does not create the entity).

        At most ``limit`` (1..10,000, default 200) versions: the **newest** ones, oldest first.
        """
        if not 0 < limit <= MAX_HISTORY:
            raise ValueError(f"limit must be between 1 and {MAX_HISTORY}")
        hit = self.client.ro(self.graph, "engram/find_entity_exact", {"norm_name": normalize(subject)})
        if not hit:
            return []
        return list(
            self.client.ro(
                self.graph,
                "engram/fact_history",
                {
                    "entity_id": hit[0]["id"],
                    "predicate": normalize(predicate),
                    "scope_id": scope_id,
                    "limit": limit,
                },
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
        *,
        include_dormant: bool = False,
        forgetting: bool | None = None,
    ) -> list[dict[str, Any]]:
        """Top-``k`` facts for ``query`` in ``scope_id`` (and the scopes it inherits), best first.

        **Forgetting (D-012).** With forgetting on (``forgetting=True``, or ``None`` and ``PLEXUS_FORGETTING``
        not ``off``) and no ``as_of``, ``2*k`` candidates are fetched and re-ranked by ``relevance x (floor +
        (1 - floor) x sigmoid(A - A0))`` (``plexus.activation.rank``), then cut to ``k``; the rows gain
        ``activation`` and ``protected``. With it off, or with ``as_of``, the order is exactly the vector /
        keyword rank order of earlier versions and those two fields are ``None``. Rows always carry
        ``surprise``, ``verify_state`` (``suspect`` when marked so or when the review date has passed),
        ``suspect_since`` and ``suspect_reason``. ``include_dormant`` adds facts a sweep moved to ``dormant``;
        ``as_of`` always includes them (forgetting never changes history).

        ``as_of`` (epoch ms) returns what was valid at that time, including since-superseded versions; the
        default is "now" with active facts only. The text budget is applied here: results are kept in rank
        order until ``budget_chars`` is spent (the first result is truncated rather than dropped).
        Returns data only; recording a ``Recall`` node is Lineage's job.

        ``k`` is clamped to 50 and ``budget_chars`` to 20,000. FalkorDB's vector search has **no
        pre-filter**: scope, status and validity are applied after the index returns its nearest nodes, so
        out-of-scope or superseded facts can crowd the target out. Recall therefore starts with ``4*k``
        nodes and, while fewer than ``k`` rows survive the filters, retries with 4x more (up to 512). Beyond
        that cap a fact is only found if its ``value`` shares a keyword with the query (full-text union,
        which filters before its limit). Cost: an empty/short result on a large graph runs up to 3 queries.
        """
        if k <= 0:
            return []
        k = min(k, MAX_K)
        budget_chars = min(budget_chars, MAX_BUDGET_CHARS)
        t = as_of if as_of is not None else _now_ms()
        if as_of is not None:
            statuses = ["active", "superseded", "dormant"]
        else:
            statuses = ["active", "dormant"] if include_dormant else ["active"]
        settings = Settings.from_env()
        rerank_on = as_of is None and (settings.forgetting if forgetting is None else forgetting)
        want = k
        if rerank_on:
            k = min(2 * k, 2 * MAX_K)  # candidates; the cut back to `want` happens after the re-ranking
        q = self._embed([query])[0]
        kw_ids = self._keyword_ids(query, scope_id, k, t, statuses)
        over = max(k * OVERFETCH, 1)
        while True:
            over = min(over, MAX_OVER)
            rows = self.client.ro(
                self.graph,
                "engram/recall",
                {
                    "q": q,
                    "scope_id": scope_id,
                    "over": over,
                    "k": k,
                    "t": t,
                    "statuses": statuses,
                    "boost": EXPAND_BOOST,
                    "sibs": SIBLINGS_PER_ENTITY,
                    "kw_ids": kw_ids,
                },
            )
            # Stop: enough rows, index exhausted (returned fewer nodes than asked for), or cap hit.
            if len(rows) >= k or over >= MAX_OVER or (rows and rows[0]["raw"] < over):
                break
            over *= RETRY_FACTOR
        acts: dict[str, Any] = {}
        if rerank_on:
            acts = Activation(self.client, self.graph, settings).compute([r["fact_id"] for r in rows], t)
            ranked = rerank(
                rows,
                acts,
                settings=settings,
                k=want,
                kw_ids=set(kw_ids),
                words=_query_words(query),
            )
            rows = [x.row for x in ranked]
        suspects = [r["fact_id"] for r in rows if r["verify_state"] == "suspect"]
        reasons = self._suspect_reasons(suspects) if suspects else {}
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
                    "surprise": r["surprise"],
                    "activation": None if r["fact_id"] not in acts else acts[r["fact_id"]].activation,
                    "protected": acts[r["fact_id"]].protected if r["fact_id"] in acts else None,
                    **self._suspect_fields(r, t, reasons),
                }
            )
            if used >= budget_chars:
                break
        return out

    def _suspect_reasons(self, fact_ids: list[str]) -> dict[str, str]:
        """Why each (stored-)suspect fact is doubted: the newest ``SUSPECTED`` Change, as one line."""
        out: dict[str, str] = {}
        for r in self.client.ro(self.graph, "activation/suspect_reason", {"fact_ids": fact_ids}):
            if not r["has_change"]:
                out[r["fact_id"]] = "marked suspect"
                continue
            try:
                paths = json.loads(r["paths"]) if r["paths"] else []
            except ValueError:
                paths = []
            first = paths[0] if isinstance(paths, list) and paths else ""
            where = r["commit"] or "working tree"
            out[r["fact_id"]] = f"changed in {where} ({first})" if first else f"changed in {where}"
        return out

    @staticmethod
    def _suspect_fields(r: dict[str, Any], t: int, reasons: dict[str, str]) -> dict[str, Any]:
        """``verify_state`` / ``suspect_since`` / ``suspect_reason`` using the contract's suspect rule."""
        if r["verify_state"] == "suspect":
            return {
                "verify_state": "suspect",
                "suspect_since": r["suspect_since"],
                "suspect_reason": reasons.get(r["fact_id"], "marked suspect"),
            }
        if r["verify_after"] <= t:
            return {
                "verify_state": "suspect",
                "suspect_since": r["verify_after"],
                "suspect_reason": "review date passed",
            }
        return {"verify_state": "verified", "suspect_since": 0, "suspect_reason": None}

    def _keyword_ids(self, query: str, scope_id: str, k: int, t: int, statuses: list[str]) -> list[str]:
        """Ids of in-scope valid facts whose ``value`` contains a query word (full-text index, OR)."""
        words = _query_words(query)
        if not words:
            return []
        try:
            rows = self.client.ro(
                self.graph,
                "engram/recall_keywords",
                {"text": "|".join(words), "scope_id": scope_id, "k": k, "t": t, "statuses": statuses},
            )
        except ResponseError:  # e.g. every word is a stopword for the index: the vector side still answers
            return []
        return [r["id"] for r in rows]

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
