"""Engram service layer: Python wrappers around the named queries in ``queries/engram/``.

Every write is one Cypher statement (atomic; FalkorDB serialises writes per graph). Embeddings are made here
(local model, no LLM) and passed as parameters. Time is epoch milliseconds; ``now`` is injectable for tests.
"""

from __future__ import annotations

import json
import logging
import math
import os
import re
from collections.abc import Callable, Iterable
from typing import Any

from redis.exceptions import ResponseError

from plexus.activation import model as act
from plexus.activation.rank import Ranked, rerank
from plexus.activation.service import Activation
from plexus.activation.settings import Settings
from plexus.common import OPEN, check_between, normalize
from plexus.common import new_id as _new_id
from plexus.common import now_ms as _now_ms  # module attribute: crucible's l5 pins it to fake the clock
from plexus.embed import Embedder, embed_checked, get_embedder
from plexus.engram import relations
from plexus.engram.dedup import MAYBE_CAP, DedupSettings, features
from plexus.engram.errors import UnknownReference
from plexus.graph.client import GraphClient

NO_STEP = -1  # Episode.step when the caller has no step
MAX_ORIGINS = 100  # derived_from ids per fact (= Lineage.MAX_DERIVE_IDS)
MAX_SOURCES = 20  # source_ids per assert_fact call (P13)

ENTITY_NEAR = 0.10  # cosine distance: entity-name vector match (and the numeric tokens must agree)
FACT_DUP = 0.08  # cosine distance: value paraphrase duplicate (and the numeric tokens must agree)
FULLTEXT_JACCARD = 0.6  # token overlap needed to accept a full-text entity hit
EXPAND_BOOST = 0.05  # rank bonus for sibling facts reached through the ABOUT entity
OVERFETCH = 4  # first vector fetch = pool * OVERFETCH; each retry multiplies by RETRY_FACTOR
RETRY_FACTOR = 4
MAX_OVER = 512  # hard cap on the vector fetch size
MAX_K = 50  # recall clamps k to this
MAX_BUDGET_CHARS = 20_000  # recall clamps budget_chars to this
DEFAULT_K = 20  # P12: recall's default k (was 8: too few for a task that needs facts from many sprints)
DEFAULT_BUDGET_CHARS = 6000  # P12: recall's default text budget (was 2,000: about 8 facts' text)
POOL_FACTOR = 3  # P12: candidates ranked before the cut to k: max(POOL_FACTOR * k, MIN_POOL) <= MAX_POOL
MIN_POOL = 60
MAX_POOL = 150
# Lexical term of recall's relevance (P12 fuse_scores). The shipped default is none (recall-check, D-013
# amendment 3); FUSION_WEIGHT is the weight P12 designed and measured it with, opt-in via
# PLEXUS_RECALL_LEXICAL_WEIGHT=0.5.
LEXICAL_WEIGHT = 0.0
FUSION_WEIGHT = 0.5
SIBLINGS_PER_ENTITY = 5  # 1-hop expansion keeps the nearest 5 sibling facts per seed
MAX_KEYWORDS = 12  # distinct query words sent to the Fact full-text index (value + search_text)
RECALL_ENTITIES = 5  # entities the pattern-separation read resolves per recall (D-013 P1)
RECALL_PREDICATES = 10  # predicates the predicate-cue read counts per recall (CROSS_CHECK §3.2)
MAX_ENTITY_QUERY_TOKENS = 24  # name tokens OR-ed into the Entity.name full-text query
ENTITY_NEIGHBOURS = 5  # nearest entities the vector lookup of resolve_entity considers
NO_TOKEN = "plexusnomatchtoken"  # full-text query for a name without any word character: matches nothing
DEFAULT_HISTORY = 200  # fact_history default
MAX_HISTORY = 10_000  # fact_history ceiling: versions of ONE entity+predicate in one scope

PAGE_KEYS = ("truncated", "omitted_by_budget", "more_available", "candidates")  # recall_page note (P12)

log = logging.getLogger("plexus.engram")

_WORD = re.compile(r"[^\W_]+", re.UNICODE)
_NUMBER = re.compile(r"\d+(?:\.\d+)*")  # 16, 8080, 1.2.3 (a trailing '.' is not part of the number)


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


_TRAILING_LETTER = re.compile(r"[a-z0-9][-_]([a-z])$")


def entity_key(name: str) -> str:
    """The key two entity names must share for the vector path to merge them (``Entity.num_key``).

    P9-c's discriminator key (numbers, unit-normalised quantities, number words, negation / antonyms; see
    ``plexus.engram.dedup``) plus a hyphenated trailing single letter: ``auth-service-a`` and
    ``auth-service-b`` are two services, although every other token is the same and the embeddings are close.
    """
    letter = _TRAILING_LETTER.search(name.strip().lower())
    return " ".join(x for x in (features(name).key, f"s:{letter.group(1)}" if letter else "") if x)


_SHORT_STOP = frozenset(
    {"a", "an", "at", "as", "be", "by", "do", "if", "in", "is", "it", "of", "on", "or", "to", "we"}
)


def _query_words(query: str) -> list[str]:
    """The query words the full-text side searches for, at most ``MAX_KEYWORDS``.

    Words of >= 3 characters, plus (P12) shorter tokens that carry a digit (``v2``, ``p9``, ``s7``) or are
    2-letter words that are not stopwords (``db``, ``ui``): before P12 everything under 3 characters was
    dropped, so a query for ``v2`` had no keyword side at all.
    """
    keep = (
        w
        for w in _tokens(query)
        if len(w) >= 3 or any(ch.isdigit() for ch in w) or (len(w) == 2 and w not in _SHORT_STOP)
    )
    return list(dict.fromkeys(keep))[:MAX_KEYWORDS]


def _lexical_weight() -> float:
    """``PLEXUS_RECALL_LEXICAL_WEIGHT`` (0..1, default ``LEXICAL_WEIGHT`` = 0: the vector-only relevance of
    main); ``FUSION_WEIGHT`` (0.5) is P12's fusion, opt-in since the recall-check."""
    raw = os.environ.get("PLEXUS_RECALL_LEXICAL_WEIGHT", "").strip()
    if not raw:
        return LEXICAL_WEIGHT
    w = float(raw)
    if not 0.0 <= w <= 1.0:
        raise ValueError(f"PLEXUS_RECALL_LEXICAL_WEIGHT must be within 0..1, got {raw}")
    return w


def search_text(entity_name: str, predicate: str) -> str:
    """``Fact.search_text``: the entity name and the predicate split into words (``billing_cycle`` ->
    ``billing cycle``), indexed by the Fact full-text index next to ``Fact.value`` (the full-text tokenizer
    keeps ``billing_cycle`` as one token, so the words are written out)."""
    return " ".join([entity_name, *re.split(r"[\W_]+", predicate)]).strip()


def fuse_scores(rows: list[dict[str, Any]], words: list[str], weight: float = FUSION_WEIGHT) -> None:
    """Hybrid relevance of every candidate, written into each row as ``fused`` in [0, 1] (P12).

    ``fused = (1 - weight) * vector + weight * lexical`` (``weight`` = ``Engram.lexical_weight``, from
    ``PLEXUS_RECALL_LEXICAL_WEIGHT``: 0 by default = the vector order of earlier versions; ``FUSION_WEIGHT``
    0.5 = P12's fusion, opt-in since the recall-check, and this function's own default):

    * ``vector = 1 - rank`` (``rank`` = cosine distance after the sibling boost; the only relevance before
      P12), clamped to [0, 1];
    * ``lexical`` = the share of the query's word weight the fact's text (entity name, predicate words, value)
      contains, each query word weighted by its rarity in the candidate pool, ``ln(1 + N / df)`` (``N`` rows,
      ``df`` = rows containing the word; words no candidate contains are left out). A fact that names every
      discriminating query word scores 1; ``S07`` or ``Bolt`` count for far more than ``API``, which every
      candidate contains.

    Before P12 keyword hits were only unioned into the candidates and then ranked by cosine distance alone. A
    score fusion is used rather than reciprocal rank fusion: on the L8 store (``crucible/l8/recall_bench``) an
    RRF variant still ranked ``Bolt Billing API S07 billing_cycle`` 7th-12th for "billing cycle decided in
    sprint S07" among twenty near-identical sprint facts, because the activation multiplier (0.9..1) outweighs
    RRF's flat rank curve and the keyword ranks of near-identical facts are mostly ties; this fusion ranks it
    first.
    """
    texts = [
        set(_tokens(f"{r.get('entity_name', '')} {r.get('predicate', '')} {r.get('value', '')}"))
        for r in rows
    ]
    n = len(rows)
    weights = {}
    for w in words:
        df = sum(1 for tx in texts if w in tx)
        if df:
            weights[w] = math.log(1.0 + n / df)
    total = sum(weights.values())
    for r, tx in zip(rows, texts, strict=True):
        vec = min(1.0, max(0.0, 1.0 - float(r["rank"])))
        lex = sum(v for w, v in weights.items() if w in tx) / total if total else 0.0
        r["lexical"] = lex
        r["fused"] = (1.0 - weight) * vec + weight * lex


def _sibling_boost(rows: list[dict[str, Any]], seeds: int) -> None:
    """Set each row's ``rank``: its own cosine distance, minus ``EXPAND_BOOST`` (floor 0) when it is a sibling
    (same ABOUT entity) of one of the ``seeds`` nearest candidates; ``via`` = that seed for a boosted row that
    is not itself one of them, else ``None``.

    This is the 1-hop expansion of earlier versions (the seeds were the ``2*k`` / ``k`` nearest facts). With
    P12's larger candidate pool almost every candidate is also a seed, so ``engram/recall``'s own boosted rank
    would boost nearly everything; the rule is re-applied here to the same number of seeds as before. Facts
    tied with the last seed's distance are all seeds, so the result does not depend on the order rows arrive
    in, and a fact with no similarity at all (distance >= 1) is never a seed (before P12 such zero-similarity
    facts could fill the seed list in index order and boost their siblings).
    """
    ordered = sorted(float(r["score"]) for r in rows if float(r["score"]) < 1.0)  # no similarity: no seed
    cut = ordered[min(seeds, len(ordered)) - 1] if ordered and seeds > 0 else -1.0
    top = {r["fact_id"] for r in rows if float(r["score"]) <= cut}  # ties at the cut all count (order-free)
    for r in rows:
        sib = next((s for s in (r.get("sib_of") or []) if s in top and s != r["fact_id"]), None)
        boost = EXPAND_BOOST * float(r.get("damp", 1.0))  # D-013: fan-damped by the entity's fan (1 = off)
        r["rank"] = max(0.0, float(r["score"]) - boost) if sib else float(r["score"])
        r["via"] = sib if sib and r["fact_id"] not in top else None


def fact_text(entity_name: str, predicate: str, value: str) -> str:
    return f"{entity_name} {predicate}: {value}"


class _QueryEmbedder:
    """Adapts an ``embed_query`` callable to the :class:`Embedder` protocol (so the 384-dim guard applies)."""

    def __init__(self, fn: Callable[[list[str]], list[list[float]]]):
        self.embed = fn


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
        dedup: DedupSettings | None = None,
    ):
        self.client = client
        self.graph = graph
        self.embedder = embedder or get_embedder()
        self.entity_threshold = entity_threshold
        self.dup_threshold = dup_threshold
        self.dedup = dedup or DedupSettings.from_env()
        self.lexical_weight = _lexical_weight()

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
        """Resolve ``name`` to an Entity, creating it if needed. Atomic (``engram/resolve_entity``).

        Hot path: one ``find_entity_exact`` read; an existing normalised name never writes. On a miss ONE
        write statement does the rest: exact name again (a concurrent creator may have won since the read),
        full-text candidates (OR over the name tokens, same kind and numeric tokens, token Jaccard >=
        ``FULLTEXT_JACCARD``), vector nearest (same kind and numeric tokens, distance <=
        ``entity_threshold``), then ``MERGE (e:Entity {norm_name})``. FalkorDB serialises writes per graph,
        so no other creator can interleave between those lookups and the create: concurrent callers with the
        same name *or* with different spellings/paraphrases of it converge on one node (the oldest candidate
        wins ties).

        ``before_create`` runs before that statement, i.e. only when the exact read missed.
        :meth:`assert_fact` uses it to reject a bad scope / episode / source *before* an Entity is created
        for a call that will be rejected (P5 review Q8).

        Not transitive: A~B and B~C does not make A~C; the statement matches against what exists, so a third
        spelling joins whichever candidate ranks first. A UNIQUE(``Entity.norm_name``) constraint is the
        backstop; on its error the statement is retried once (the retry then finds the winner).
        """
        norm = normalize(name)
        if not norm:
            raise ValueError("entity name must not be empty")

        exact = self.client.ro(self.graph, "engram/find_entity_exact", {"norm_name": norm})
        if exact:
            return {**exact[0], "created": False, "matched_by": "exact"}

        emb = self._embed([name])[0]  # a wrong-sized vector is refused before anything is written
        if before_create is not None:
            before_create()
        tok = sorted(set(_tokens(name)))
        params = {
            "norm": norm,
            "name": " ".join(name.split()),
            "kind": kind,
            "tok": tok,
            # entities that differ only in numbers/versions are different things
            "num_key": entity_key(name),
            # OR of the tokens; a name without a word character gets a sentinel that matches nothing
            "q": "|".join(tok[:MAX_ENTITY_QUERY_TOKENS]) or NO_TOKEN,
            "emb": emb,
            "entity_id": _new_id(),
            "jac": FULLTEXT_JACCARD,
            "thr": self.entity_threshold,
            "k": ENTITY_NEIGHBOURS,
            "now": now if now is not None else _now_ms(),
        }
        try:
            rows = self.client.rw(self.graph, "engram/resolve_entity", params)
        except ResponseError as exc:
            if "unique constraint" not in str(exc).lower():
                raise
            params["entity_id"] = _new_id()  # lost a race to a creator outside the statement: retry once
            rows = self.client.rw(self.graph, "engram/resolve_entity", params)
        r = rows[0]
        return {
            "id": r["id"],
            "name": r["name"],
            "kind": r["kind"],
            "created": r["how"] == "new",
            "matched_by": r["how"],
        }

    def resolve_entity(self, name: str, kind: str = "thing", *, now: int | None = None) -> str:
        """Entity id for ``name`` (existing or newly created). See :meth:`resolve_entity_ex`."""
        return self.resolve_entity_ex(name, kind, now=now)["id"]

    def assert_relation(
        self,
        subject: str,
        kind: str,
        obj: str,
        scope_id: str,
        *,
        subject_kind: str = "thing",
        object_kind: str = "thing",
        now: int | None = None,
    ) -> dict[str, Any]:
        """Relate two entities: ``(subject)-[:RELATES {kind, scope_id}]->(object)``, typed and directed.

        Idempotent. ``recall(hops=1|2)`` walks these edges in both directions (``plexus.engram.relations``).
        Returns ``{created, subject_id, object_id, kind, scope_id}``; raises :class:`UnknownReference`
        (writing nothing) for an unknown scope and ``ValueError`` for an empty kind or a self-relation.
        """
        return relations.assert_relation(
            self, subject, kind, obj, scope_id, subject_kind=subject_kind, object_kind=object_kind, now=now
        )

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
        step_id: str | None = None,
        derived_from: Iterable[str] = (),
        source_ids: Iterable[str] = (),
    ) -> dict[str, Any]:
        """Assert ``subject predicate value`` in ``scope_id`` as ``agent_id``.

        ``source_ids`` (P13, trial 8; at most 20, unioned with ``source_id``): every listed Source gets its
        own ``(fact)-[:DERIVED_FROM]->(Source)`` edge, so a fact two documents support survives the quarantine
        of one. An id that is not a Source rejects the whole call (:class:`UnknownReference` ``'source'``,
        nothing written). Asserting an existing value again with sources it is not yet linked to corroborates
        it: the result carries ``sources_added`` (the newly linked ids, ``[]`` if none; absent for a new one).

        ``step_id`` (an existing Step): a NEW fact is linked ``(Step)-[:WROTE]->(Fact)`` by that statement.

        ``derived_from`` (Source / Episode / Fact ids, at most 100; P9-f, Crucible L6-F): linked
        ``(fact)-[:DERIVED_FROM]->(origin)`` in that same statement, so a hard kill cannot leave the fact
        without the link (it used to be ``Lineage.derive_from``, a second statement). An unknown id raises
        :class:`UnknownReference` ``'origin'`` and writes nothing.

        Returns ``{fact_id, superseded, duplicate_of, contradicts, entity_id, surprise}``. ``surprise`` is the
        value stored on the new fact (0.9 contradiction, 0.6 supersede, else novelty in 0..0.5; ``None`` for a
        duplicate, which stores nothing). For a duplicate no fact is
        created and ``fact_id == duplicate_of`` (the existing fact, which gains an ``ASSERTED_BY {at}`` edge
        and supersedes this agent's own earlier, different current facts: ``superseded`` lists them).

        ``dup_threshold`` overrides the service's paraphrase threshold for this call (a negative value turns
        the paraphrase check off, so only an equal normalised value is a duplicate; ``verify_fact`` uses it,
        because an agent that corrects a clause of a long fact means a different fact).

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
        origins = list(dict.fromkeys(derived_from or ()))
        if len(origins) > MAX_ORIGINS:
            raise ValueError(f"at most {MAX_ORIGINS} derived_from ids per fact")
        extra = list(dict.fromkeys(s for s in (source_ids or ()) if s))
        if len(extra) > MAX_SOURCES:
            raise ValueError(f"at most {MAX_SOURCES} source_ids per fact")
        # source_id keeps its own slot in the statement; the other sources travel as origins (one MERGE each)
        extra = [s for s in extra if s != source_id]
        origins = origins + [s for s in extra if s not in origins]

        self._check_sources(extra)  # before the Entity exists, and for an existing Entity too: Sources only

        def check() -> None:
            self._check_refs(scope_id, episode_id, source_id)
            self._check_origins(origins)

        entity = self.resolve_entity_ex(subject, subject_kind, now=t, before_create=check)
        text_emb, value_emb = self._embed([fact_text(entity["name"], pred, value), value])
        novelty = self._novelty(text_emb, scope_id)
        dup_t = self.dup_threshold if dup_threshold is None else dup_threshold
        feat = features(value)
        rows = self.client.rw(
            self.graph,
            "engram/assert_fact",
            {
                "entity_id": entity["id"],
                "predicate": pred,
                "value": " ".join(value.split()),
                "norm_value": norm_value,
                "value_tokens": token_key(value),
                "dup_key": feat.key,
                "tok": feat.tok,
                "tok_seq": feat.seq,
                "scope_id": scope_id,
                "agent_id": agent_id,
                "source_id": source_id,
                "episode_id": episode_id,
                "derived_ids": origins,
                "step_id": step_id or "",
                "confidence": float(confidence),
                "supersede": bool(supersede),
                "now": t,
                "open_to": OPEN,
                "fact_id": _new_id(),
                "search_text": search_text(entity["name"], pred),
                "emb": text_emb,
                "value_emb": value_emb,
                "dup_threshold": dup_t,
                "jac2": self.dedup.jaccard,
                "cos2": self.dedup.tier2_cos,
                "maybe_cos": self.dedup.maybe_cos,
                "maybe_jac": self.dedup.maybe_jaccard,
                "maybe_cap": MAYBE_CAP
                if dup_t >= 0
                else 0,  # a negative threshold = exact duplicates only (verify_fact)
                "novelty": novelty,
                "surprise_supersede": act.SURPRISE_SUPERSEDE,
                "surprise_contradict": act.SURPRISE_CONTRADICT,
            },
        )
        if not rows:
            check()
            raise RuntimeError("assert_fact rejected although every referenced id exists")  # pragma: no cover
        r = rows[0]
        return {
            "fact_id": r["fact_id"],
            "superseded": list(r["superseded"]),
            "duplicate_of": r["duplicate_of"],
            "contradicts": list(r["contradicts"]),
            "entity_id": entity["id"],
            "surprise": r["surprise"],
            **({"sources_added": sorted(r["sources_added"])} if r["duplicate_of"] else {}),
            "possible_duplicates": [
                {
                    "fact_id": m["id"],
                    "value": m["value"],
                    "cos": round(m["cos"], 4),
                    "jaccard": round(m["jac"], 4),
                }
                for m in sorted(r["maybe"], key=lambda m: m["cos"])
            ],
        }

    def _novelty(self, text_emb: list[float], scope_id: str) -> float:
        """Write-time novelty: one bounded vector read (k=5 nearest active facts of the scope)."""
        near = self.client.ro(
            self.graph,
            "activation/novelty",
            {"q": text_emb, "scope_id": scope_id, "over": act.NOVELTY_OVER, "k": act.NOVELTY_K},
        )
        return act.novelty(near[0]["distance"] if near else None)

    def _check_sources(self, ids: list[str]) -> None:
        """Raise :class:`UnknownReference` ``'source'`` for ids that name no Source (a Fact id is not one)."""
        if not ids:
            return
        rows = self.client.ro(self.graph, "engram/existing_origins", {"ids": ids})
        have = {r["id"] for r in rows if r["label"] == "Source"}
        missing = [i for i in ids if i not in have]
        if missing:
            raise UnknownReference("source", missing)

    def _check_origins(self, origins: list[str]) -> None:
        """Raise :class:`UnknownReference` ``'origin'`` for ids that name no Fact, Source or Episode."""
        if not origins:
            return
        have = {r["id"] for r in self.client.ro(self.graph, "engram/existing_origins", {"ids": origins})}
        missing = [o for o in origins if o not in have]
        if missing:
            raise UnknownReference("origin", missing)

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
        check_between("limit", limit, MAX_HISTORY)
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
        k: int = DEFAULT_K,
        as_of: int | None = None,
        budget_chars: int = DEFAULT_BUDGET_CHARS,
        *,
        include_dormant: bool = False,
        forgetting: bool | None = None,
        hops: int = 0,
        separation: bool | None = None,
        settings: Settings | None = None,
        all_scopes: bool = False,
    ) -> list[dict[str, Any]]:
        """Top-``k`` facts for ``query`` in ``scope_id`` (and the scopes it inherits), best first.

        See :meth:`recall_with_meta` for the full description; this returns the rows only.
        """
        return self.recall_with_meta(
            query,
            scope_id,
            k,
            as_of,
            budget_chars,
            include_dormant=include_dormant,
            forgetting=forgetting,
            hops=hops,
            separation=separation,
            settings=settings,
            all_scopes=all_scopes,
        )[0]

    def recall_page(
        self,
        query: str,
        scope_id: str,
        k: int = DEFAULT_K,
        as_of: int | None = None,
        budget_chars: int = DEFAULT_BUDGET_CHARS,
        *,
        include_dormant: bool = False,
        forgetting: bool | None = None,
        hops: int = 0,
        separation: bool | None = None,
        settings: Settings | None = None,
        all_scopes: bool = False,
    ) -> tuple[list[dict[str, Any]], dict[str, Any]]:
        """``(rows, page)`` with ``page = {truncated, omitted_by_budget, more_available, candidates}`` (P12).

        ``omitted_by_budget`` ranked rows were cut by ``budget_chars``, ``more_available`` = more candidates
        matched than were returned (ask again with a larger ``k`` / ``budget_chars`` or a narrower query),
        ``truncated`` = either. Nothing is cut silently. The same four keys are in the metadata of
        :meth:`recall_with_meta`; this is that call with the page keys split out.
        """
        rows, meta = self.recall_with_meta(
            query,
            scope_id,
            k,
            as_of,
            budget_chars,
            include_dormant=include_dormant,
            forgetting=forgetting,
            hops=hops,
            separation=separation,
            settings=settings,
            all_scopes=all_scopes,
        )
        return rows, {key: meta[key] for key in PAGE_KEYS}

    def recall_with_meta(
        self,
        query: str,
        scope_id: str,
        k: int = DEFAULT_K,
        as_of: int | None = None,
        budget_chars: int = DEFAULT_BUDGET_CHARS,
        *,
        include_dormant: bool = False,
        forgetting: bool | None = None,
        hops: int = 0,
        separation: bool | None = None,
        settings: Settings | None = None,
        all_scopes: bool = False,
    ) -> tuple[list[dict[str, Any]], dict[str, Any]]:
        """Top-``k`` facts for ``query`` in ``scope_id`` (and the scopes it inherits), best first, plus how.

        The second value is the recall's metadata: for ``why_recalled`` ``entities`` (the entities the query
        named, ``{id: {name, fan}}``), ``predicates`` (the predicates it named, ``{predicate: {fan}}``),
        ``entity_facts_added`` (candidates the named entities contributed, CROSS_CHECK §3.3), ``separation``
        and ``forgetting`` (what was on), ``mode``; and the page note (P12) ``truncated``,
        ``omitted_by_budget``, ``more_available``, ``candidates``.

        **Scope.** ``scope_id`` and every scope it INHERITS (<= 3 hops); ``all_scopes=True`` (the MCP tool's
        default scope ``all``, P12) searches every scope of the tenant graph, ``scope_id`` is then ignored
        (the entity / predicate fans of pattern separation are counted over every scope as well).

        **Candidates (P12).** Two channels: the vector index (cosine distance of the fact text to the query,
        with the 1-hop sibling expansion) and the full-text index over ``Fact.value`` and ``Fact.search_text``
        (the entity name and predicate words). A pool of ``max(POOL_FACTOR * k, MIN_POOL)`` (<=
        ``MAX_POOL``) candidates is fetched from each; every in-scope keyword hit survives into the pool, and
        the two rankings are fused (:func:`fuse_scores`: cosine relevance and an IDF-weighted query-word
        coverage) into ``relevance`` when ``PLEXUS_RECALL_LEXICAL_WEIGHT`` > 0; the default 0 keeps the cosine
        relevance (the fusion cost noise share and a critical probe on L5b and gained nothing on L6-C / L8,
        BASELINE "Recall-check"). Before P12 the pool was ``2*k`` and keyword hits competed on cosine
        distance only. The sibling boost is re-applied in Python to the siblings of the ``2*k`` (``k`` without
        re-ranking) nearest seeds (:func:`_sibling_boost`), scaled by the entity-fan damping below.

        **Pattern separation (D-013 P1, CROSS_CHECK §3.2-3.3).** With ``separation`` on (``True``, or ``None``
        and ``PLEXUS_RECALL_SEPARATION`` not ``off``) and no ``as_of``, the query's words are matched against
        ``Entity.name`` (one bounded full-text read, ``engram/recall_entities``); an entity counts as *named*
        when every word of its name is in the query. The named entities' own current facts join the
        candidates (one bounded read in the ``engram/recall_hop_facts`` shape, ``2k`` nearest per entity), so
        a named entity's fact is never missed because the vector over-fetch did not reach it. A candidate's
        predicate counts as *named* by the same rule (every word of the predicate in the query); one bounded
        read (``engram/recall_predicates``) counts each one's fan. Each candidate then gets the context term
        ``sep = w_entity * max(0, S - ln fan_entity) + w_predicate * max(0, S - ln fan_predicate)`` over the
        cues it matches (``fan`` = the entity's / predicate's current facts in the searched scopes; ACT-R's
        ``S - ln fan``; ``PLEXUS_ACT_CUES=entity`` restores the single damped entity term P1 first shipped),
        the sibling expansion is damped by the entity fan, and each row reports ``lures``: other candidates
        with the same predicate about another entity at nearly the same relevance. Rows gain
        ``entity_match``, ``predicate_match``, ``sep`` and ``lures``.

        **Forgetting (D-012).** With forgetting on (``forgetting=True``, or ``None`` and ``PLEXUS_FORGETTING``
        not ``off``) and no ``as_of``, the pool is re-ranked by ``relevance x (floor + (1 - floor) x sigmoid(A
        - A0))`` (``plexus.activation.rank``; ``relevance`` is the fused score), then cut to ``k``; the rows
        gain ``activation`` and ``protected``. With forgetting and separation both off, or with ``as_of``,
        the order is the fused relevance and those two fields are ``None``. Rows always carry ``surprise``,
        ``verify_state`` (``suspect`` when marked so or when the review date has passed), ``suspect_since``
        and ``suspect_reason``. ``include_dormant`` adds facts a sweep moved to ``dormant``; ``as_of``
        always includes them (forgetting never changes history).

        **Hops (P9-b).** ``hops`` 1 or 2 also follows the typed entity relations (:meth:`assert_relation`,
        either direction) from the entities of the ``k`` hits and appends their current facts, nearest to the
        query first, with ``hop`` (1|2) and ``relation_path`` on those rows: at most 20 entities and 20 facts
        per hop, 3 facts per entity, ranked behind every direct hit. ``hops=0`` (the default) runs no extra
        query.

        ``as_of`` (epoch ms) returns what was valid at that time, including since-superseded versions; the
        default is "now" with active facts only. The text budget is applied here: results are kept in rank
        order until ``budget_chars`` is spent (the first result is truncated rather than dropped). Returns
        data only; recording a ``Recall`` node is Lineage's job.

        ``k`` is clamped to 50 and ``budget_chars`` to 20,000. FalkorDB's vector search has **no pre-filter**:
        scope, status and validity are applied after the index returns its nearest nodes, so out-of-scope or
        superseded facts can crowd the target out. Recall therefore starts with ``OVERFETCH * pool`` nodes
        and, while fewer than ``pool`` rows survive the filters, retries with 4x more (up to 512). Beyond that
        cap a fact is only found by the keyword channel (which filters before its limit). Cost: an empty/short
        result on a large graph runs up to 3 vector queries.
        """
        if hops not in range(relations.MAX_HOPS + 1):
            raise ValueError(f"hops must be 0, 1 or {relations.MAX_HOPS}")
        settings = settings or Settings.from_env()
        fg = as_of is None and (settings.forgetting if forgetting is None else forgetting)
        sp = as_of is None and (settings.separation if separation is None else separation)
        meta: dict[str, Any] = {
            "entities": {},
            "predicates": {},
            "entity_facts_added": 0,
            "separation": sp,
            "forgetting": fg,
            "mode": settings.act_mode,
            "truncated": False,
            "omitted_by_budget": 0,
            "more_available": False,
            "candidates": 0,
        }
        if k <= 0:
            return [], meta
        k = min(k, MAX_K)
        budget_chars = min(budget_chars, MAX_BUDGET_CHARS)
        t = as_of if as_of is not None else _now_ms()
        if as_of is not None:
            statuses = ["active", "superseded", "dormant"]
        else:
            statuses = ["active", "dormant"] if include_dormant else ["active"]
        if sp:
            meta["entities"] = self._resolve_entities(query, scope_id, t, statuses, all_scopes)
        # Re-rank when use history counts or separation is on (a cue to apply, or candidates to merge).
        rerank_on = fg or sp
        # Seeds of the sibling expansion (and the named entities' per-entity cap): the nearest 2*k when
        # re-ranking, k otherwise, as before P12's larger pool.
        seeds = min(2 * k, 2 * MAX_K) if rerank_on else k
        pool = min(max(POOL_FACTOR * k, MIN_POOL), MAX_POOL)
        q = self._embed_query(query)
        kw_ids = self._keyword_ids(query, scope_id, pool, t, statuses, all_scopes)
        # CROSS_CHECK §3.3: the named entities' own facts, read before the main query so the ToolCall is
        # still named after engram/recall (plexus.mcp.metering); merged after it.
        named_rows = (
            self._entity_facts(list(meta["entities"]), q, scope_id, seeds, t, statuses, all_scopes)
            if sp and meta["entities"]
            else []
        )
        rows = self._fetch_candidates(
            q, scope_id, pool, t, statuses, kw_ids, all_scopes, damp=sp, smax=settings.s_max
        )
        _sibling_boost(rows, seeds)
        if named_rows:
            have = {r["fact_id"] for r in rows}
            added = [r for r in named_rows if r["fact_id"] not in have]
            rows, meta["entity_facts_added"] = rows + added, len(added)
        fuse_scores(rows, _query_words(query), self.lexical_weight)
        if sp:
            meta["predicates"] = self._resolve_predicates(query, rows, scope_id, t, statuses, all_scopes)
        acts: dict[str, Any] = {}
        ranked: dict[str, Ranked] = {}
        if rerank_on:
            if fg:
                acts = Activation(self.client, self.graph, settings).compute([r["fact_id"] for r in rows], t)
            best = rerank(
                rows,
                acts,
                settings=settings,
                k=k,
                kw_ids=set(kw_ids),
                words=_query_words(query),
                entities={eid: e["fan"] for eid, e in meta["entities"].items()},
                predicates={p: e["fan"] for p, e in meta["predicates"].items()},
                forgetting=fg,
                separation=sp,
            )
            top = [x.row for x in best]
            ranked = {x.row["fact_id"]: x for x in best}
        else:
            top = sorted(rows, key=lambda r: (-r["fused"], r["rank"], r["fact_id"]))[:k]
        more = len(rows) > len(top)
        hmeta: dict[str, Any] = {}
        if hops:
            extra, hmeta = relations.expand_hops(
                self, top, scope_id, hops, q, t, statuses, all_scopes=all_scopes
            )
            top = top + extra
        out = self._apply_budget(top, acts, t, budget_chars, ranked)
        for item in out:
            item.update(hmeta.get(item["fact_id"], {}))
        omitted = len(top) - len(out)
        meta.update(
            truncated=bool(omitted or more),
            omitted_by_budget=omitted,
            more_available=more,
            candidates=len(rows),
        )
        return out, meta

    def _embed_query(self, query: str) -> list[float]:
        """The query vector: the embedder's query form when it has one (BGE's retrieval instruction), else the
        same embedding as a stored fact text."""
        embed_query = getattr(self.embedder, "embed_query", None)
        if callable(embed_query):
            return embed_checked(_QueryEmbedder(embed_query), [query])[0]
        return self._embed([query])[0]

    def _resolve_entities(
        self, query: str, scope_id: str, t: int, statuses: list[str], all_scopes: bool = False
    ) -> dict[str, dict[str, Any]]:
        """The entities the query names, ``{entity_id: {name, fan, score}}`` (D-013 P1, at most 5).

        Candidates come from the ``Entity.name`` full-text index (OR of the query words >= 3 characters) plus
        an exact ``norm_name`` match of the whole query; an entity is kept only when every word of its name is
        in the query, so "Acme Notes API S07 api_version" names ``Acme Notes API S07`` but not its ``S08``
        twin.
        ``fan`` counts the entity's current facts in the searched scopes (every scope with ``all_scopes``).
        Empty when nothing is named.
        """
        words = _query_words(query)
        if not words:
            return {}
        have = set(_tokens(query))
        out: dict[str, dict[str, Any]] = {}
        try:
            rows = self.client.ro(
                self.graph,
                "engram/recall_entities",
                {
                    "q": "|".join(words),
                    "scope_id": scope_id,
                    "all": bool(all_scopes),
                    "limit": RECALL_ENTITIES,
                    "statuses": statuses,
                    "t": t,
                },
            )
        except ResponseError:  # every word is a stopword for the index
            rows = []
        for r in rows:
            name_words = _tokens(r["name"] or "")
            if name_words and all(w in have for w in name_words):
                out[r["entity_id"]] = {"name": r["name"], "fan": int(r["fan"]), "score": float(r["score"])}
        if not out:
            exact = self.client.ro(self.graph, "engram/find_entity_exact", {"norm_name": normalize(query)})
            if exact:
                fans = self.client.ro(
                    self.graph,
                    "engram/recall_entities",
                    {
                        "q": "|".join(_tokens(exact[0]["name"])) or exact[0]["name"],
                        "scope_id": scope_id,
                        "all": bool(all_scopes),
                        "limit": RECALL_ENTITIES,
                        "statuses": statuses,
                        "t": t,
                    },
                )
                fan = next((int(f["fan"]) for f in fans if f["entity_id"] == exact[0]["id"]), 0)
                out[exact[0]["id"]] = {"name": exact[0]["name"], "fan": fan, "score": float("inf")}
        return out

    def _entity_facts(
        self,
        entity_ids: list[str],
        q: list[float],
        scope_id: str,
        per_entity: int,
        t: int,
        statuses: list[str],
        all_scopes: bool = False,
    ) -> list[dict[str, Any]]:
        """The named entities' own current facts as candidate rows (CROSS_CHECK §3.3).

        One bounded read in the ``engram/recall_hop_facts`` shape (entity-first; the ``per_entity`` facts
        nearest to the query per entity, same scope / status / validity filters). The caller adds the ones
        the vector / keyword fetch missed: those rank by their own distance, as a seed would; a fact already
        among the candidates keeps its row (and its boosted ``rank``).
        """
        rows = self.client.ro(
            self.graph,
            "engram/recall_hop_facts",
            {
                "entity_ids": entity_ids,
                "scope_id": scope_id,
                "all": bool(all_scopes),
                "t": t,
                "statuses": statuses,
                "per_entity": per_entity,
                "q": q,
            },
        )
        return [dict(r) for r in rows]

    def _resolve_predicates(
        self,
        query: str,
        rows: list[dict[str, Any]],
        scope_id: str,
        t: int,
        statuses: list[str],
        all_scopes: bool = False,
    ) -> dict[str, dict[str, Any]]:
        """The predicates the query names, ``{predicate: {fan}}`` (CROSS_CHECK §3.2, at most 10).

        The mirror of :meth:`_resolve_entities` for the second cue: a candidate's predicate counts as named
        when every word of it is in the query (``Fact.predicate`` is stored normalised, so ``api_version``
        is the words ``api`` and ``version``), so "Acme Notes API S07 api_version" names ``api_version`` but
        not ``api_owner``. Only candidate predicates can matter (the cue lifts candidates), so no index is
        searched for them; one bounded read (``engram/recall_predicates``) counts each one's fan: current
        facts with that predicate in the searched scopes. Empty when nothing is named.
        """
        have = set(_tokens(query))
        if not have:
            return {}
        named: list[str] = []
        for r in rows:
            pred = str(r.get("predicate") or "")
            if pred in named:
                continue
            words = _tokens(pred)
            if words and all(w in have for w in words):
                named.append(pred)
        if not named:
            return {}
        fans = self.client.ro(
            self.graph,
            "engram/recall_predicates",
            {
                "predicates": named[:RECALL_PREDICATES],
                "scope_id": scope_id,
                "all": bool(all_scopes),
                "statuses": statuses,
                "t": t,
            },
        )
        return {r["predicate"]: {"fan": int(r["fan"])} for r in fans}

    def _fetch_candidates(
        self,
        q: list[float],
        scope_id: str,
        k: int,
        t: int,
        statuses: list[str],
        kw_ids: list[str],
        all_scopes: bool = False,
        *,
        damp: bool = False,
        smax: float = 1.0,
    ) -> list[dict[str, Any]]:
        """The ``engram/recall`` rows for ``q``: an adaptive over-fetch of the (pre-filter-less) vector index.

        Starts with ``k * OVERFETCH`` nodes and, while fewer than ``k`` rows survive the scope / status /
        validity filters, retries with ``RETRY_FACTOR`` times more, up to ``MAX_OVER``. Every keyword hit in
        ``kw_ids`` that passes the filters is returned on top of the ``k`` nearest (P12).
        """
        over = max(k * OVERFETCH, 1)
        while True:
            over = min(over, MAX_OVER)
            rows = self.client.ro(
                self.graph,
                "engram/recall",
                {
                    "q": q,
                    "scope_id": scope_id,
                    "all": bool(all_scopes),
                    "over": over,
                    "lim": k + len(kw_ids),
                    "t": t,
                    "statuses": statuses,
                    "boost": EXPAND_BOOST,
                    "sibs": SIBLINGS_PER_ENTITY,
                    "kw_ids": kw_ids,
                    "damp": bool(damp),
                    "smax": float(smax),
                },
            )
            # Stop: enough rows, index exhausted (returned fewer nodes than asked for), or cap hit.
            if len(rows) >= k or over >= MAX_OVER or (rows and rows[0]["raw"] < over):
                return rows
            over *= RETRY_FACTOR

    def _apply_budget(
        self,
        rows: list[dict[str, Any]],
        acts: dict[str, Any],
        t: int,
        budget_chars: int,
        ranked: dict[str, Ranked] | None = None,
    ) -> list[dict[str, Any]]:
        """Shape ranked rows into recall results, kept in order until ``budget_chars`` of text is spent."""
        suspects = [r["fact_id"] for r in rows if r["verify_state"] == "suspect"]
        reasons = self._suspect_reasons(suspects) if suspects else {}
        out: list[dict[str, Any]] = []
        used = 0
        for r in rows:
            text = fact_text(r["entity_name"], r["predicate"], r["value"])
            if used + len(text) > budget_chars:
                if out:
                    break
                text = text[: max(budget_chars - 1, 0)] + "…"  # first hit alone exceeds the budget
            used += len(text)
            out.append(self._recall_item(r, text, acts, t, reasons, (ranked or {}).get(r["fact_id"])))
            if used >= budget_chars:
                break
        return out

    def _recall_item(
        self,
        r: dict[str, Any],
        text: str,
        acts: dict[str, Any],
        t: int,
        reasons: dict[str, str],
        rk: Ranked | None = None,
    ) -> dict[str, Any]:
        """One recall result: the row's fields, its provenance ``path``, (when ranked) its activation and the
        D-013 terms (``entity_match``, ``sep``, ``lures``, ``salience``; ``None`` / ``[]`` when not ranked).
        """
        path: list[dict[str, Any]] = [
            {"rel": "ABOUT", "label": "Entity", "id": r["entity_id"], "name": r["entity_name"]},
            {"rel": "IN_SCOPE", "label": "Scope", "id": r["scope_id"]},
        ]
        path += [{"rel": "DERIVED_FROM", "label": d["label"], "id": d["id"]} for d in r["derived_from"]]
        path += [{"rel": "ASSERTED_BY", "label": "Agent", "id": a} for a in r["asserted_by"]]
        fa = acts.get(r["fact_id"])
        return {
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
            "activation": None if fa is None else fa.activation,
            "protected": None if fa is None else fa.protected,
            "maybe_duplicate_of": list(r.get("maybe_dup") or []),
            "entity_match": None if rk is None else rk.ent_match,
            "predicate_match": None if rk is None else rk.pred_match,
            "sep": None if rk is None else rk.sep,
            "lures": [] if rk is None else list(rk.lures),
            "salience": None if fa is None else fa.salience,
            **self._suspect_fields(r, t, reasons),
        }

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

    def _keyword_ids(
        self, query: str, scope_id: str, k: int, t: int, statuses: list[str], all_scopes: bool = False
    ) -> list[str]:
        """Ids of in-scope valid facts whose ``value`` or ``search_text`` (entity name + predicate words)
        contains a query word (full-text index, OR), best full-text score first."""
        words = _query_words(query)
        if not words:
            return []
        try:
            rows = self.client.ro(
                self.graph,
                "engram/recall_keywords",
                {
                    "text": "|".join(words),
                    "scope_id": scope_id,
                    "all": bool(all_scopes),
                    "k": k,
                    "t": t,
                    "statuses": statuses,
                },
            )
        except ResponseError as exc:  # e.g. every word is a stopword: the vector side still answers
            log.warning("recall: keyword channel failed for %r (vector side only): %s", words, exc)
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
