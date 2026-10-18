"""Typed entity relations and ``recall(hops)`` (P9-b / P2).

``assert_relation`` writes ``(Entity)-[:RELATES {kind, scope_id, at}]->(Entity)``. ``expand_hops`` walks
those edges (either direction) from the entities of the direct recall hits, level by level over DISTINCT
entities, and returns their current facts with a distance penalty. Everything is bounded: at most
``HOP_ENTITIES`` entities and ``HOP_FACTS`` facts per hop, ``HOP_FACTS_PER_ENTITY`` facts per entity,
``MAX_HOPS`` hops. No LLM: the relations are only as good as the agents' ``assert_relation`` calls.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from knewat.common import normalize, now_ms
from knewat.engram.errors import UnknownReference

if TYPE_CHECKING:
    from knewat.engram.service import Engram

MAX_HOPS = 2
HOP_ENTITIES = 20  # entities followed per hop
HOP_FACTS = 20  # facts added per hop
HOP_FACTS_PER_ENTITY = 3  # nearest facts kept per reached entity
HOP_EDGE_FETCH = 200  # RELATES rows read per direction per hop (a hub entity cannot blow up a level)
HOP_PENALTY = (
    0.25  # added to a hop fact's cosine distance per hop: its rank, never better than a direct hit's
)
MAX_KIND = 128


def assert_relation(
    eng: Engram,
    subject: str,
    kind: str,
    obj: str,
    scope_id: str,
    *,
    subject_kind: str = "thing",
    object_kind: str = "thing",
    now: int | None = None,
) -> dict[str, Any]:
    """Relate two entities (resolved or created like ``assert_fact``'s subject) with a typed edge in a scope.

    Idempotent per ``(subject, kind, object, scope)``. The scope is checked before any Entity is created, so a
    rejected call leaves nothing behind. Returns ``{created, subject_id, object_id, kind, scope_id}``.
    """
    rel = normalize(kind)
    if not rel:
        raise ValueError("relation kind must not be empty")
    if len(rel) > MAX_KIND:
        raise ValueError(f"relation kind must be at most {MAX_KIND} characters")
    if not normalize(subject) or not normalize(obj):
        raise ValueError("subject and object must not be empty")
    if normalize(subject) == normalize(obj):
        raise ValueError(f"'{subject}' and '{obj}' are the same entity; a relation needs two")
    eng._check_refs(scope_id, "", "")  # UnknownReference before any Entity is created
    a = eng.resolve_entity_ex(subject, subject_kind, now=now)
    b = eng.resolve_entity_ex(obj, object_kind, now=now)
    if a["id"] == b["id"]:
        raise ValueError(f"'{subject}' and '{obj}' are the same entity; a relation needs two")
    rows = eng.client.rw(
        eng.graph,
        "engram/assert_relation",
        {"a_id": a["id"], "b_id": b["id"], "kind": rel, "scope_id": scope_id, "now": now or now_ms()},
    )
    if not rows:
        raise UnknownReference("scope", [scope_id])
    return {
        "created": bool(rows[0]["created"]),
        "subject_id": a["id"],
        "object_id": b["id"],
        "kind": rel,
        "scope_id": scope_id,
    }


def expand_hops(
    eng: Engram,
    rows: list[dict[str, Any]],
    scope_id: str,
    hops: int,
    q: list[float],
    t: int,
    statuses: list[str],
    *,
    all_scopes: bool = False,
) -> tuple[list[dict[str, Any]], dict[str, dict[str, Any]]]:
    """Facts of the entities up to ``hops`` RELATES edges away from the entities of ``rows``.

    Returns ``(extra_rows, meta)``: ``extra_rows`` are in the ``engram/recall`` row shape (``rank`` = own
    distance + ``HOP_PENALTY`` x hop), ordered by (hop, rank), without any fact already in ``rows``;
    ``meta[fact_id] = {hop, relation_path}`` where the path lists ``{from, kind, to, dir}`` edges from the
    seed entity. Empty when there are no seeds, no relations or no hops. ``all_scopes`` (recall's scope
    ``all``) follows relations and keeps facts of every scope instead of ``scope_id`` and the scopes it
    inherits.
    """
    if hops <= 0 or not rows:
        return [], {}
    seeds = list(dict.fromkeys(r["entity_id"] for r in rows))
    visited = set(seeds)
    paths: dict[str, list[dict[str, str]]] = {s: [] for s in seeds}
    hop_of: dict[str, int] = {}
    frontier = seeds
    for hop in range(1, hops + 1):
        edges = eng.client.ro(
            eng.graph,
            "engram/relates_level",
            {"frontier": frontier, "scope_id": scope_id, "all": all_scopes, "limit": HOP_EDGE_FETCH},
        )
        found: dict[str, dict[str, Any]] = {}
        for e in sorted(edges, key=lambda e: (e["to_name"], e["to_id"], e["from_id"], e["kind"], e["dir"])):
            if e["to_id"] in visited or e["to_id"] in found:
                continue
            found[e["to_id"]] = e
        chosen = sorted(found.values(), key=lambda e: (e["to_name"], e["to_id"]))[:HOP_ENTITIES]
        if not chosen:
            break
        for e in chosen:
            visited.add(e["to_id"])
            hop_of[e["to_id"]] = hop
            paths[e["to_id"]] = [
                *paths[e["from_id"]],
                {"from": e["from_id"], "kind": e["kind"], "to": e["to_id"], "dir": e["dir"]},
            ]
        frontier = [e["to_id"] for e in chosen]
    if not hop_of:
        return [], {}
    have = {r["fact_id"] for r in rows}
    facts = eng.client.ro(
        eng.graph,
        "engram/recall_hop_facts",
        {
            "entity_ids": sorted(hop_of),
            "scope_id": scope_id,
            "all": all_scopes,
            "t": t,
            "statuses": statuses,
            "per_entity": HOP_FACTS_PER_ENTITY,
            "q": q,
        },
    )
    out: list[dict[str, Any]] = []
    meta: dict[str, dict[str, Any]] = {}
    per_hop: dict[int, int] = {}
    for f in sorted(facts, key=lambda f: (hop_of[f["entity_id"]], f["score"], f["fact_id"])):
        h = hop_of[f["entity_id"]]
        if f["fact_id"] in have or per_hop.get(h, 0) >= HOP_FACTS:
            continue
        per_hop[h] = per_hop.get(h, 0) + 1
        have.add(f["fact_id"])
        row = dict(f)
        row["rank"] = row["score"] + HOP_PENALTY * h
        out.append(row)
        meta[row["fact_id"]] = {"hop": h, "relation_path": paths[f["entity_id"]]}
    return out, meta
