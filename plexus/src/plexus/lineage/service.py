"""Lineage service layer: steps, recall records, provenance (``why``), time travel and forgetting.

Wrappers around the named queries in ``queries/lineage/``. Each write is ONE Cypher statement (atomic); reads
use ``ro``. Time is epoch ms; ``clock`` / ``now`` are injectable for tests.
"""

from __future__ import annotations

import time
import uuid
from collections.abc import Callable, Iterable, Sequence
from typing import Any

from plexus.engram import normalize
from plexus.graph.client import GraphClient
from plexus.lineage import explain

MAX_LINK_IDS = 200  # ids per list in link_step
MAX_RECALL_RESULTS = 200
MAX_DERIVE_IDS = 100
MAX_WHY_ELEMENTS = explain.MAX_WHY_ELEMENTS


class LineageError(Exception):
    """Base class for lineage errors."""


class UnknownStep(LineageError, LookupError):
    """A step id (or a node id linked to a step) does not exist."""


class UnknownNode(LineageError, LookupError):
    """The id given to why / why_recalled / who_knew does not name a node of the expected kind."""


class StepOrderError(LineageError, ValueError):
    """record_step was asked for an ``n`` lower than the agent's latest step."""


def _now_ms() -> int:
    return time.time_ns() // 1_000_000


def _new_id() -> str:
    return str(uuid.uuid4())


def _ids(values: Iterable[str] | None) -> list[str]:
    return list(dict.fromkeys(values or ()))


class Lineage:
    """Provenance and time-travel operations bound to one tenant graph."""

    def __init__(self, client: GraphClient, graph: str, clock: Callable[[], int] = _now_ms):
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
        trust: float = 1.0,
        *,
        source_id: str | None = None,
        now: int | None = None,
    ) -> str:
        """MERGE a ``Source`` by ``uri`` (idempotent) and return its id. Pass it to ``Engram.assert_fact``."""
        if not uri.strip():
            raise ValueError("source uri must not be empty")
        rows = self.client.rw(
            self.graph,
            "lineage/create_source",
            {
                "source_id": source_id or _new_id(),
                "uri": uri,
                "kind": kind,
                "trust": float(trust),
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
            {"agent_id": agent_id, "step_id": _new_id(), "n": -1 if n is None else int(n), "at": self._t(at)},
        )
        r = rows[0]
        if r["step_id"] is None:
            raise StepOrderError(f"agent '{agent_id}' already has a step after n={r['n']}")
        return r["step_id"]

    def link_step(
        self, step_id: str, wrote_ids: Iterable[str] = (), read_ids: Iterable[str] = ()
    ) -> dict[str, int]:
        """Attach ``(Step)-[:WROTE]->(Fact|Decision|Handoff|Task)`` and ``(Step)-[:READ]->(Fact)`` edges.

        All-or-nothing; raises :class:`UnknownStep` (nothing written) if the step or any id is unknown.
        Returns ``{"read": n, "wrote": n}``.
        """
        wrote, read = _ids(wrote_ids), _ids(read_ids)
        if len(wrote) > MAX_LINK_IDS or len(read) > MAX_LINK_IDS:
            raise ValueError(f"at most {MAX_LINK_IDS} ids per list")
        rows = self.client.rw(
            self.graph, "lineage/link_step", {"step_id": step_id, "read_ids": read, "wrote_ids": wrote}
        )
        if not rows:
            wanted = [step_id, *wrote, *read]
            have = {r["id"] for r in self.client.ro(self.graph, "lineage/existing_ids", {"ids": wanted})}
            raise UnknownStep(f"unknown id(s): {', '.join(i for i in wanted if i not in have)}")
        return {"read": rows[0]["n_read"], "wrote": rows[0]["n_wrote"]}

    # -- derivation and recall records ------------------------------------------------------------------
    def derive_from(self, fact_id: str, from_ids: Iterable[str]) -> int:
        """Record ``(Fact)-[:DERIVED_FROM]->(Source|Episode|Fact)`` for an inferred / consolidated fact.

        All-or-nothing; raises :class:`UnknownStep` (a LookupError) if the fact or any origin does not exist.
        Returns the number of origins linked.
        """
        origins = _ids(from_ids)
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
        recall_id = _new_id()
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
            wanted = ([step_id] if step_id else []) + [r["fact_id"] for r in rows]
            have = {r["id"] for r in self.client.ro(self.graph, "lineage/existing_ids", {"ids": wanted})}
            raise UnknownStep(f"unknown id(s): {', '.join(i for i in wanted if i not in have)}")
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

    # -- why --------------------------------------------------------------------------------------------
    def why(self, node_id: str, *, max_elements: int = MAX_WHY_ELEMENTS) -> dict[str, Any]:
        """Explain a Decision or a Fact: the facts it rests on, who asserted them, where they came from.

        Walks ``BASED_ON``, ``ASSERTED_BY``, ``DERIVED_FROM*1..3`` (Episode / Source / Fact, plus the Session
        and agent behind an Episode), ``SUPERSEDES`` / ``CONTRADICTS`` / ``DUPLICATES`` neighbours and the
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
        rows = self.client.ro(self.graph, "lineage/why_edges", {"id": node_id, "limit": max_elements})
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
