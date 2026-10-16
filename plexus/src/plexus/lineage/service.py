"""Lineage service layer: steps, recall records, provenance (``why``), time travel and forgetting.

Wrappers around the named queries in ``queries/lineage/``. Each write is ONE Cypher statement (atomic); reads
use ``ro``. Time is epoch ms; ``clock`` / ``now`` are injectable for tests.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable, Sequence
from typing import Any, NoReturn

from plexus.common import check_between, new_id, normalize, now_ms, unique
from plexus.graph.client import GraphClient
from plexus.lineage import explain

MAX_LINK_IDS = 200  # ids per list in link_step
MAX_RECALL_RESULTS = 200
MAX_DERIVE_IDS = 100
MAX_FORGET_FACTS = 5000
DEFAULT_DETAIL = 500  # forget / quarantine report: readers, decision ids and handoff ids listed per call
MAX_DETAIL = 5000
MAX_SOURCE_TEXT = 2000
MAX_WHY_ELEMENTS = explain.MAX_WHY_ELEMENTS
MAX_DEPTH = 12  # DERIVED_FROM hops a cascade / why may follow (P9-b: was 5 / 3, hard-coded)
DEFAULT_CASCADE_DEPTH = 8  # forget_source / quarantine / release_quarantine
DEFAULT_WHY_DEPTH = 6
DEFAULT_IMPACT_DETAIL = 50  # impact: ids listed per category
IMPACT_EARLIEST = 5  # impact: the earliest affected facts, with their times


TRUSTS = ("normal", "high")


def normalize_trust(trust: str | float | None) -> str:
    """``'normal'`` | ``'high'``, or ``''`` for "not given" (None or a legacy number): the query parameter."""
    if trust is None or isinstance(trust, (int, float)):  # a number is the legacy 0..1 float: no opinion
        return ""
    value = str(trust).strip().lower()
    if value == "":
        return ""
    if value not in TRUSTS:
        raise ValueError(f"trust must be 'normal' or 'high', not {trust!r}")
    return value


class LineageError(Exception):
    """Base class for lineage errors."""


class UnknownStep(LineageError, LookupError):
    """A step id (or a node id linked to a step) does not exist."""


class UnknownNode(LineageError, LookupError):
    """The id given to why / why_recalled / who_knew does not name a node of the expected kind."""


class StepOrderError(LineageError, ValueError):
    """record_step was asked for an ``n`` lower than the agent's latest step."""


class Lineage:
    """Provenance and time-travel operations bound to one tenant graph."""

    def __init__(self, client: GraphClient, graph: str, clock: Callable[[], int] = now_ms):
        self.client = client
        self.graph = graph
        self._clock = clock

    def _t(self, now: int | None) -> int:
        return self._clock() if now is None else now

    # -- sources ----------------------------------------------------------------------------------------
    def create_source(
        self,
        uri: str,
        kind: str = "doc",
        trust: str | float | None = None,
        *,
        source_id: str | None = None,
        title: str = "",
        text: str = "",
        now: int | None = None,
    ) -> str:
        """MERGE a ``Source`` by ``uri`` (idempotent) and return its id. Pass it to ``Engram.assert_fact``.

        ``title`` / ``text`` are optional display properties (text is cut to 2000 chars).
        ``trust`` is ``'normal'`` or ``'high'`` (``'high'`` protects the facts derived from the source from
        fading, D-012). ``None`` or a number (the old 0..1 float, which never had an effect) means *no
        opinion*: a new source is ``'normal'`` and an existing one keeps its trust.
        """
        if not uri.strip():
            raise ValueError("source uri must not be empty")
        rows = self.client.rw(
            self.graph,
            "lineage/create_source",
            {
                "source_id": source_id or new_id(),
                "uri": uri,
                "kind": kind,
                "trust": normalize_trust(trust),
                "title": title,
                "text": text[:MAX_SOURCE_TEXT],
                "now": self._t(now),
            },
        )
        return rows[0]["id"]

    # -- steps ------------------------------------------------------------------------------------------
    def record_step(self, agent_id: str, n: int | None = None, at: int | None = None) -> str:
        """Create the agent's step ``n`` (default: previous + 1), ``BY`` it, ``NEXT`` from its previous.

        Idempotent: asking again for an existing ``n`` returns the existing step id. Raises
        :class:`StepOrderError` if the agent already has a later step.
        """
        rows = self.client.rw(
            self.graph,
            "lineage/record_step",
            {"agent_id": agent_id, "step_id": new_id(), "n": -1 if n is None else int(n), "at": self._t(at)},
        )
        r = rows[0]
        if r["step_id"] is None:
            raise StepOrderError(f"agent '{agent_id}' already has a step after n={r['n']}")
        return r["step_id"]

    def link_step(
        self,
        step_id: str,
        wrote_ids: Iterable[str] = (),
        read_ids: Iterable[str] = (),
        *,
        via: str = "use",
    ) -> dict[str, int]:
        """Attach ``(Step)-[:WROTE]->(Fact|Decision|Handoff|Task)`` and ``(Step)-[:READ]->(Fact)`` edges.

        All-or-nothing; raises :class:`UnknownStep` (nothing written) if the step or any id is unknown.
        Returns ``{"read": n, "wrote": n}``. The READ edges get ``via`` (default ``'use'``: the agent acted on
        or cited the fact; ``'recall'`` only surfaced it) and ``at`` = the step's time; ``'use'`` is never
        downgraded (D-012).
        """
        if via not in ("use", "recall"):
            raise ValueError("via must be 'use' or 'recall'")
        wrote, read = unique(wrote_ids), unique(read_ids)
        if len(wrote) > MAX_LINK_IDS or len(read) > MAX_LINK_IDS:
            raise ValueError(f"at most {MAX_LINK_IDS} ids per list")
        rows = self.client.rw(
            self.graph,
            "lineage/link_step",
            {"step_id": step_id, "read_ids": read, "wrote_ids": wrote, "via": via},
        )
        if not rows:
            self._raise_unknown([step_id, *wrote, *read])
        return {"read": rows[0]["n_read"], "wrote": rows[0]["n_wrote"]}

    def _raise_unknown(self, wanted: list[str]) -> NoReturn:
        """Raise :class:`UnknownStep` naming the ids in ``wanted`` that no node carries."""
        have = {r["id"] for r in self.client.ro(self.graph, "lineage/existing_ids", {"ids": wanted})}
        raise UnknownStep(f"unknown id(s): {', '.join(i for i in wanted if i not in have)}")

    # -- derivation and recall records ------------------------------------------------------------------
    def derive_from(self, fact_id: str, from_ids: Iterable[str]) -> int:
        """Record ``(Fact)-[:DERIVED_FROM]->(Source|Episode|Fact)`` for an inferred / consolidated fact.

        All-or-nothing; raises :class:`UnknownStep` (a LookupError) if the fact or any origin does not exist.
        Returns the number of origins linked.
        """
        origins = unique(from_ids)
        if fact_id in origins:
            raise ValueError("a fact cannot be derived from itself")
        if len(origins) > MAX_DERIVE_IDS:
            raise ValueError(f"at most {MAX_DERIVE_IDS} origins per call")
        rows = self.client.rw(self.graph, "lineage/link_derived", {"fact_id": fact_id, "from_ids": origins})
        if not rows:
            raise UnknownStep(f"fact '{fact_id}' or one of its origins does not exist")
        return rows[0]["linked"]

    def record_recall(
        self,
        agent_id: str,
        step_id: str | None,
        query: str,
        scope_id: str,
        k: int,
        results: Sequence[dict[str, Any]],
        *,
        now: int | None = None,
    ) -> str:
        """Store what a recall returned so ``why_recalled`` can explain it later. Returns the recall id.

        ``results`` is ``[{fact_id, rank?, score}]``; the output of ``Engram.recall`` can be passed as is
        (``rank`` defaults to the 1-based position). Creates ``Recall`` + ``BY`` + ``IN_STEP`` + ``RETURNED``
        and ``(Step)-[:READ]->(Fact)`` for every returned fact, in one statement. All-or-nothing: raises
        :class:`UnknownStep` if ``step_id`` or a fact id does not exist.
        """
        rows: list[dict[str, Any]] = []
        seen: set[str] = set()
        for pos, r in enumerate(results, start=1):
            fid = r["fact_id"]
            if fid in seen:
                continue
            seen.add(fid)
            rows.append(
                {"fact_id": fid, "rank": int(r.get("rank") or pos), "score": float(r.get("score") or 0.0)}
            )
        if len(rows) > MAX_RECALL_RESULTS:
            raise ValueError(f"at most {MAX_RECALL_RESULTS} results per recall record")
        recall_id = new_id()
        res = self.client.rw(
            self.graph,
            "lineage/record_recall",
            {
                "recall_id": recall_id,
                "agent_id": agent_id,
                "step_id": step_id or "",
                "query": query,
                "scope_id": scope_id,
                "k": int(k),
                "now": self._t(now),
                "fact_ids": [r["fact_id"] for r in rows],
                "results": rows,
            },
        )
        if not res:
            self._raise_unknown(([step_id] if step_id else []) + [r["fact_id"] for r in rows])
        return recall_id

    def link_assert_result(self, step_id: str, result: dict[str, Any]) -> dict[str, int]:
        """Link the outcome of ``Engram.assert_fact`` to a step.

        A new fact is WROTE; a duplicate, and the facts the assertion superseded or contradicts, are READ (the
        writer had to look at them).
        """
        fid = result["fact_id"]
        read = [*result.get("superseded", ()), *result.get("contradicts", ())]
        if result.get("duplicate_of"):
            return self.link_step(step_id, read_ids=[fid, *read])
        return self.link_step(step_id, wrote_ids=[fid], read_ids=read)

    # -- forgetting -------------------------------------------------------------------------------------
    def forget_source(
        self,
        source_id: str,
        mode: str = "forget",
        *,
        now: int | None = None,
        limit: int = MAX_FORGET_FACTS,
        max_detail: int = DEFAULT_DETAIL,
        depth: int = DEFAULT_CASCADE_DEPTH,
    ) -> dict[str, Any]:
        """Forget everything derived from a source, in one bounded statement.

        Every fact that reaches the source through up to ``depth`` (1..12, default 8) ``DERIVED_FROM`` hops
        becomes ``status='forgotten'`` with
        ``valid_to = min(valid_to, now)``, so ``Engram.recall`` and :meth:`as_of` stop returning it. Decisions
        ``BASED_ON`` those facts are flagged (``flagged = true``), never deleted. Handoffs that ``CARRIES``
        them are reported. Idempotent; at most ``limit`` (<= 5000) facts per call, ``truncated`` says to call
        again. Returns ``{source_id, mode, fact_ids, decision_ids, decisions_total, handoff_ids,
        handoffs_total, detail_truncated, truncated}``: ``decision_ids`` / ``handoff_ids`` list at most
        ``max_detail`` (1..5000, default 500) ids, the ``*_total`` counts are exact (every decision is flagged
        regardless). ``mode='quarantine'`` delegates to :meth:`quarantine`. The cascade expands level by level
        over distinct facts, so a diamond-shaped lineage costs its edges, not its paths. Raises
        :class:`UnknownNode`
        (unknown source).
        """
        if mode == "quarantine":
            return self.quarantine(source_id, now=now, limit=limit, max_detail=max_detail, depth=depth)
        if mode != "forget":
            raise ValueError("mode must be 'forget' or 'quarantine'")
        check_between("limit", limit, MAX_FORGET_FACTS)
        check_between("max_detail", max_detail, MAX_DETAIL)
        check_between("depth", depth, MAX_DEPTH)
        rows = self.client.rw(
            self.graph,
            "lineage/forget_source",
            {
                "source_id": source_id,
                "now": self._t(now),
                "limit": limit,
                "depth": depth,
                "reason": f"derived from forgotten source {source_id}",
                "max_detail": max_detail,
            },
        )
        if not rows:
            raise UnknownNode(f"no source with id '{source_id}'")
        r = rows[0]
        return {
            "source_id": source_id,
            "mode": mode,
            "fact_ids": sorted(r["fact_ids"]),
            "decision_ids": sorted(r["decision_ids"]),
            "decisions_total": r["decisions_total"],
            "handoff_ids": sorted(r["handoff_ids"]),
            "handoffs_total": r["handoffs_total"],
            "detail_truncated": r["decisions_total"] > max_detail or r["handoffs_total"] > max_detail,
            "truncated": bool(r["truncated"]),
        }

    def quarantine(
        self,
        source_id: str,
        *,
        now: int | None = None,
        limit: int = MAX_FORGET_FACTS,
        max_detail: int = DEFAULT_DETAIL,
        depth: int = DEFAULT_CASCADE_DEPTH,
    ) -> dict[str, Any]:
        """Quarantine a poisoned source and report its blast radius (stretch feature; reversible).

        Same traversal as :meth:`forget_source` (up to ``depth`` ``DERIVED_FROM`` hops, 1..12, default 8) but
        the facts become
        ``status='quarantined'`` (hidden from recall and :meth:`as_of`, ``valid_to`` untouched, old status
        kept so :meth:`release_quarantine` can restore it). Nothing else is modified. Returns
        ``{source_id, mode, fact_ids, readers: [{agent_id, step_id, step_n, at, fact_id}], readers_total,
        agents, decision_ids, decisions_total, handoff_ids, handoffs_total, detail_truncated, truncated}``:
        ``readers`` / ``agents`` are the Steps / agents that READ a quarantined fact, the decisions are
        ``BASED_ON`` them and the handoffs ``CARRIES`` them. The response is bounded: ``readers``,
        ``decision_ids`` and ``handoff_ids`` list at most ``max_detail`` (1..5000, default 500) entries
        (readers: the earliest), the ``*_total`` counts and ``agents`` are always complete. Raises
        :class:`UnknownNode`.
        """
        check_between("limit", limit, MAX_FORGET_FACTS)
        check_between("max_detail", max_detail, MAX_DETAIL)
        check_between("depth", depth, MAX_DEPTH)
        rows = self.client.rw(
            self.graph,
            "lineage/quarantine",
            {
                "source_id": source_id,
                "now": self._t(now),
                "limit": limit,
                "max_detail": max_detail,
                "depth": depth,
            },
        )
        if not rows:
            raise UnknownNode(f"no source with id '{source_id}'")
        r = rows[0]
        readers = sorted(
            (
                {
                    "agent_id": x["agent_id"],
                    "step_id": x["step_id"],
                    "step_n": x["n"],
                    "at": x["at"],
                    "fact_id": x["fact_id"],
                }
                for x in r["reads"]
            ),
            key=lambda x: (x["at"], x["agent_id"], x["fact_id"]),
        )
        return {
            "source_id": source_id,
            "mode": "quarantine",
            "fact_ids": sorted(r["fact_ids"]),
            "readers": readers,
            "readers_total": r["reads_total"],
            "agents": sorted(r["agent_ids"]),
            "decision_ids": sorted(r["decision_ids"]),
            "decisions_total": r["decisions_total"],
            "handoff_ids": sorted(r["handoff_ids"]),
            "handoffs_total": r["handoffs_total"],
            "detail_truncated": max(r["reads_total"], r["decisions_total"], r["handoffs_total"]) > max_detail,
            "truncated": bool(r["truncated"]),
        }

    def release_quarantine(
        self, source_id: str, *, limit: int = MAX_FORGET_FACTS, depth: int = DEFAULT_CASCADE_DEPTH
    ) -> dict[str, Any]:
        """Undo :meth:`quarantine`: quarantined facts under the source get their previous status back.

        ``depth`` (1..12, default 8) should be at least the depth the quarantine used.
        """
        check_between("limit", limit, MAX_FORGET_FACTS)
        check_between("depth", depth, MAX_DEPTH)
        rows = self.client.rw(
            self.graph,
            "lineage/release_quarantine",
            {"source_id": source_id, "limit": limit, "depth": depth},
        )
        if not rows:
            raise UnknownNode(f"no source with id '{source_id}'")
        return {
            "source_id": source_id,
            "fact_ids": sorted(rows[0]["fact_ids"]),
            "truncated": bool(rows[0]["truncated"]),
        }

    # -- impact (read-only blast radius) ------------------------------------------------------------------
    def impact(
        self,
        kind: str,
        node_id: str,
        *,
        depth: int = DEFAULT_CASCADE_DEPTH,
        limit: int = MAX_FORGET_FACTS,
        max_detail: int = DEFAULT_IMPACT_DETAIL,
    ) -> dict[str, Any]:
        """What would be affected if a ``'source'`` or a ``'fact'`` were wrong? Nothing is written.

        Expands ``DERIVED_FROM`` (up to ``depth`` hops, 1..12, default 8) level by level over distinct
        facts, as :meth:`forget_source` / :meth:`quarantine` do, in one read-only statement (one snapshot).
        Returns ``{kind, id, depth, facts: {total, by_status, ids}, readers: {steps_total, agents_total,
        agents}, decisions: {total, ids}, tasks: {total, ids}, handoffs: {total, ids}, truncated}``. For a
        fact, the fact itself is part of ``facts``. ``tasks`` are the tasks the affected decisions are
        ``FOR``. Lists hold at most ``max_detail`` (1..5000, default 50) ids; the totals are exact up to
        ``limit`` facts (``truncated`` says whether that bound was hit). Every list category also carries
        ``earliest_at`` / ``latest_at`` over the WHOLE set (epoch ms: ``valid_from``, step / decision /
        handoff ``at``; ``None`` when empty), and ``facts.earliest`` is the 5 earliest affected facts
        ``[{id, at}]``. Raises :class:`UnknownNode`.
        """
        if kind not in ("source", "fact"):
            raise ValueError("kind must be 'source' or 'fact'")
        check_between("depth", depth, MAX_DEPTH)
        check_between("limit", limit, MAX_FORGET_FACTS)
        check_between("max_detail", max_detail, MAX_DETAIL)
        rows = self.client.ro(
            self.graph, f"lineage/impact_{kind}", {"id": node_id, "depth": depth, "limit": limit + 1}
        )  # one more than the bound: "truncated" means a further fact exists, not "exactly `limit` found"
        if not rows:
            raise UnknownNode(f"no {kind} with id '{node_id}'")
        r = dict(rows[0])
        if r["truncated"]:
            for key in ("fact_ids", "statuses", "fact_ats"):
                r[key] = r[key][:limit]
        by_status: dict[str, int] = {}
        for st in r["statuses"]:
            by_status[st] = by_status.get(st, 0) + 1
        agents = sorted(r["agent_ids"])

        def span(ats: Iterable[int | None]) -> dict[str, int | None]:
            vals = [a for a in ats if a is not None]
            return {"earliest_at": min(vals) if vals else None, "latest_at": max(vals) if vals else None}

        def cut(ids: Iterable[str], ats: Iterable[int | None]) -> dict[str, Any]:
            ordered = sorted(ids)
            return {"total": len(ordered), "ids": ordered[:max_detail], **span(ats)}

        by_time = sorted(
            zip(r["fact_ats"], r["fact_ids"], strict=True),
            key=lambda p: (2**62 if p[0] is None else p[0], p[1]),
        )
        return {
            "kind": kind,
            "id": node_id,
            "depth": depth,
            "facts": {
                **cut(r["fact_ids"], r["fact_ats"]),
                "by_status": dict(sorted(by_status.items())),
                "earliest": [{"id": i, "at": at} for at, i in by_time[:IMPACT_EARLIEST]],
            },
            "readers": {
                "steps_total": r["steps_total"],
                "agents_total": len(agents),
                "agents": agents[:max_detail],
                **span([r["step_first"], r["step_last"]]),
            },
            "decisions": cut(r["decision_ids"], r["decision_ats"]),
            "tasks": {"total": len(r["task_ids"]), "ids": sorted(r["task_ids"])[:max_detail]},
            "handoffs": cut(r["handoff_ids"], r["handoff_ats"]),
            "truncated": bool(r["truncated"]),
        }

    # -- why --------------------------------------------------------------------------------------------
    def why(
        self, node_id: str, *, max_elements: int = MAX_WHY_ELEMENTS, depth: int = DEFAULT_WHY_DEPTH
    ) -> dict[str, Any]:
        """Explain a Decision or a Fact: the facts it rests on, who asserted them, where they came from.

        Walks ``BASED_ON``, ``ASSERTED_BY``, ``DERIVED_FROM`` to ``depth`` hops (1..12, default 6; Episode /
        Source / Fact, plus the Session and agent behind an Episode; expanded level by level over distinct
        facts), ``SUPERSEDES`` / ``CONTRADICTS`` / ``DUPLICATES`` neighbours and the
        ``Step`` (with its agent) that wrote the decision and each fact. Returns::

            {root, kind, facts: [{id, props, asserted_by, sources, episodes, derived_from_facts, supersedes,
                                  superseded_by, contradicts, contradicted_by, written_by_steps}],
             agents, sources, episodes, steps, paths: [[hop, ...]], nodes: [{id, label, props}],
             edges: [{from, rel, to}], truncated}

        ``nodes`` + ``edges`` hold at most ``max_elements`` (default 200) elements, closest to the root first;
        ``truncated`` says whether anything was cut. A path hop is ``{from, rel, to, reverse}``, where
        ``reverse`` marks an edge that is stored ``to -> from``. Raises :class:`UnknownNode`.
        """
        if max_elements < 2:
            raise ValueError("max_elements must be at least 2")
        check_between("depth", depth, MAX_DEPTH)
        rows = list(self.client.ro(self.graph, "lineage/why_edges", {"id": node_id, "limit": max_elements}))
        rows += self._derived_edges(node_id, rows, max_elements, depth)
        edges, labels, truncated = explain.bound_edges(rows, node_id, max_elements)
        info = self._node_info([node_id, *labels])
        root = info.get(node_id)
        if root is None:
            raise UnknownNode(f"no node with id '{node_id}'")
        if root["label"] not in ("Decision", "Fact"):
            raise UnknownNode(f"why() explains a Decision or a Fact, '{node_id}' is a {root['label']}")
        labels = {node_id: root["label"], **labels}
        nodes = [
            {"id": i, "label": lab, "props": explain.clean(info[i]["props"]) if i in info else {}}
            for i, lab in labels.items()
        ]
        out = explain.summarise(node_id, root["label"], nodes, edges)
        out["truncated"] = truncated
        return out

    def _derived_edges(
        self, node_id: str, rows: Sequence[dict[str, Any]], limit: int, depth: int
    ) -> list[dict[str, Any]]:
        """The DERIVED_FROM ancestry of the base facts: one query per level over DISTINCT facts."""
        frontier = sorted({r["t"] for r in rows if r["rel"] == "BASED_ON"} | {node_id})
        seen = set(frontier)
        out: list[dict[str, Any]] = []
        for _ in range(depth):
            level = self.client.ro(
                self.graph, "lineage/why_derived_level", {"frontier": frontier, "limit": limit}
            )
            out += [dict(r) for r in level]
            frontier = sorted(
                {r["t"] for r in level if r["rel"] == "DERIVED_FROM" and r["tl"] == "Fact"} - seen
            )
            if not frontier:
                break
            seen.update(frontier)
        return out

    def _node_info(self, ids: Iterable[str]) -> dict[str, dict[str, Any]]:
        rows = self.client.ro(self.graph, "lineage/node_info", {"ids": sorted(set(ids))})
        return {r["id"]: dict(r) for r in rows}

    def why_recalled(self, recall_id: str, *, max_elements: int = MAX_WHY_ELEMENTS) -> dict[str, Any]:
        """Explain a stored recall: what it returned, in which order, and the provenance of each fact.

        Returns ``{recall: {id, query, at, k, scope_id, agent_id, step}, results: [{rank, score, fact_id,
        props, entity, asserted_by, derived_from, scope}], nodes, edges, truncated}``. ``results`` are in
        rank order and match what ``record_recall`` stored. ``nodes`` + ``edges`` are capped at
        ``max_elements`` (lowest ranked results are cut first; ``results`` is cut with them). Raises
        :class:`UnknownNode`.
        """
        rows = self.client.ro(
            self.graph, "lineage/why_recalled", {"recall_id": recall_id, "limit": MAX_RECALL_RESULTS}
        )
        if not rows:
            raise UnknownNode(f"no recall with id '{recall_id}'")
        head = rows[0]
        step = head["step"][0] if head["step"] else None
        recall = {
            "id": head["recall_id"],
            "query": head["query"],
            "at": head["at"],
            "k": head["k"],
            "scope_id": head["scope_id"],
            "agent_id": head["agent_id"],
            "step": step,
        }
        results = [explain.recall_result(r) for r in rows if r["fact_id"] is not None]
        nodes, edges, results, truncated = explain.recall_graph(recall, results, max_elements)
        info = self._node_info(n["id"] for n in nodes)
        for n in nodes:
            n["props"] = explain.clean(info[n["id"]]["props"]) if n["id"] in info else {}
        return {"recall": recall, "results": results, "nodes": nodes, "edges": edges, "truncated": truncated}

    # -- who knew what, when --------------------------------------------------------------------------
    def who_knew(self, fact_id: str, *, limit: int = 200) -> dict[str, Any]:
        """Agents whose Steps READ the fact (oldest first), and who asserted / wrote it.

        Returns ``{fact_id, asserted_by: [agent ids], written_by: [{step_id, n, at, agent_id}], readers:
        [{agent_id, step_id, step_n, at, recall_ids}], agents: [agent ids that read it]}``. Raises
        :class:`UnknownNode` for an unknown fact.
        """
        rows = self.client.ro(self.graph, "lineage/who_knew", {"fact_id": fact_id, "limit": limit})
        if not rows:
            raise UnknownNode(f"no fact with id '{fact_id}'")
        head = rows[0]
        readers = [
            {
                "agent_id": r["agent_id"],
                "step_id": r["step_id"],
                "step_n": r["step_n"],
                "at": r["step_at"],
                "recall_ids": sorted(r["recall_ids"]),
            }
            for r in rows
            if r["step_id"] is not None
        ]
        return {
            "fact_id": fact_id,
            "asserted_by": sorted(head["asserted_by"]),
            "written_by": sorted(head["written_by"], key=lambda w: (w["at"], w["n"])),
            "readers": readers,
            "agents": sorted({r["agent_id"] for r in readers}),
        }

    def knew_at(self, agent_id: str, step_n: int, *, limit: int = 200) -> dict[str, Any]:
        """What ``agent_id`` knew at step ``step_n``.

        ``facts``: facts its steps READ up to that step that were valid at that step's time (so a fact read
        earlier but superseded or forgotten since is gone); ``wrote``: everything its steps WROTE up to then.
        The cut is the agent's latest step with ``n <= step_n`` (``None`` values when it has none).
        Returns ``{agent_id, step_n, at, facts: [...], wrote: [...]}``.
        """
        rows = self.client.ro(
            self.graph, "lineage/knew_at", {"agent_id": agent_id, "n": step_n, "limit": limit}
        )
        out: dict[str, Any] = {"agent_id": agent_id, "step_n": None, "at": None, "facts": [], "wrote": []}
        for r in rows:
            out["step_n"], out["at"] = r["at_step"], r["at_time"]
            if r["kind"] == "read":
                out["facts"].append(
                    {
                        "fact_id": r["id"],
                        "entity": r["entity"],
                        "predicate": r["predicate"],
                        "value": r["value"],
                        "status": r["status"],
                        "valid_from": r["valid_from"],
                        "valid_to": r["valid_to"],
                        "read_at_step": r["step_n"],
                    }
                )
            else:
                out["wrote"].append(
                    {"id": r["id"], "label": r["label"], "summary": r["summary"], "step_n": r["step_n"]}
                )
        return out

    def as_of(self, subject: str, predicate: str, t: int, scope_id: str) -> dict[str, Any] | None:
        """The fact for (subject, predicate) that was valid at ``t`` in ``scope_id`` (or a scope it inherits).

        The subject is resolved by its normalised name (exact match, as ``Engram.fact_history``). Returns the
        best match (nearest scope, then latest ``valid_from``) with ``also_valid`` listing any other fact
        valid at the same time (a contradiction), or ``None`` if nothing was valid then. Forgotten and
        quarantined facts never answer.
        """
        rows = self.client.ro(
            self.graph,
            "lineage/as_of",
            {
                "norm_subject": normalize(subject),
                "predicate": normalize(predicate),
                "t": int(t),
                "scope_id": scope_id,
                "limit": 20,
            },
        )
        if not rows:
            return None
        best = dict(rows[0])
        best["subject"] = subject
        best["predicate"] = normalize(predicate)
        best["at"] = int(t)
        best["also_valid"] = [dict(r) for r in rows[1:]]
        return best
