"""``plexus migrate entities``: move a pre-P9-d tenant to atomic entity resolution (analysis C.5).

1. list normalised names held by more than one Entity (they would leave UNIQUE(``Entity.norm_name``) FAILED);
2. backfill ``Entity.tok`` / ``Entity.num_key`` in batches of ``BATCH`` (entities without them never match the
   full-text / vector lookups of ``engram/resolve_entity``, so run this before relying on the new resolution);
3. apply the schema (idempotent: adds the UNIQUE constraint) and report its status;
4. dry-run report of near-duplicate *legacy* entities, read-only: for every entity, the older entities the new
   resolution would have joined it to (same kind and numeric tokens; token Jaccard or vector distance).

There is no automatic merge and no ``SAME_AS`` bridge: facts of the two spellings already live on two nodes,
and re-pointing them needs the duplicate / supersede / contradiction logic re-run (and alias-aware reads in
other owners' queries). The report is for the owner to review.
"""

from __future__ import annotations

import json
from collections.abc import Iterator
from typing import Any

from plexus.engram.service import (
    ENTITY_NEAR,
    FULLTEXT_JACCARD,
    MAX_ENTITY_QUERY_TOKENS,
    _jaccard,
    _tokens,
    token_key,
)
from plexus.graph.client import GraphClient
from plexus.graph.schema import ENTITY_KEY, apply_schema

_NEVER = (1 << 62, "")  # sorts after every real (created_at, id)
BATCH = 200  # entities per backfill statement and per page
FULLTEXT_CANDIDATES = 20  # full-text candidates read per entity (older ones are kept)
VECTOR_CANDIDATES = 10  # vector neighbours read per entity


def _page(client: GraphClient, graph: str) -> Iterator[list[dict[str, Any]]]:
    """Entities in id order, ``BATCH`` per read (keyset pagination on ``id``)."""
    after = ""
    while True:
        rows = client.ro(graph, "engram/entities_page", {"after": after, "limit": BATCH})
        if not rows:
            return
        yield list(rows)
        after = rows[-1]["id"]


def _keys(name: str) -> tuple[list[str], str]:
    return sorted(set(_tokens(name))), token_key(name)


def duplicate_names(client: GraphClient, graph: str, limit: int = 100) -> list[dict[str, Any]]:
    """Normalised names held by more than one Entity: ``[{norm_name, n}]``, most duplicated first."""
    return [dict(r) for r in client.ro(graph, "engram/entity_duplicate_names", {"limit": limit})]


def backfill_entity_keys(client: GraphClient, graph: str, *, dry_run: bool = False) -> dict[str, int]:
    """Set ``tok`` / ``num_key`` on every Entity that lacks them. Idempotent. ``dry_run`` only counts."""
    total = missing = updated = 0
    for page in _page(client, graph):
        todo = []
        for e in page:
            total += 1
            if e["tok"] is None or e["num_key"] is None:
                tok, num_key = _keys(e["name"] or e["norm_name"] or "")
                todo.append({"id": e["id"], "tok": tok, "num_key": num_key})
        missing += len(todo)
        if todo and not dry_run:
            rows = client.rw(graph, "engram/backfill_entity_keys", {"rows": todo})
            updated += rows[0]["n"]
    return {"total": total, "missing": missing, "updated": updated}


def _older_candidates(
    client: GraphClient,
    graph: str,
    e: dict[str, Any],
    born: dict[str, tuple[int, str]],
    jaccard: float,
    entity_threshold: float,
) -> dict[str, dict[str, Any]]:
    """Older, same-kind, same-numbers entities that the new resolution would have joined ``e`` to."""
    tok, num_key = _keys(e["name"] or e["norm_name"] or "")
    cands: dict[str, dict[str, Any]] = {}

    def see(c: dict[str, Any], how: str, distance: float | None) -> None:
        if c["kind"] != e["kind"] or born.get(c["id"], _NEVER) >= born[e["id"]]:
            return  # other kind, or not older than e (this also drops e itself)
        c_tok, c_num = _keys(c["name"] or "")
        if c_num != num_key:
            return
        j = _jaccard(set(tok), set(c_tok))
        if how == "fulltext" and (j < jaccard or not (set(tok) <= set(c_tok) or set(c_tok) <= set(tok))):
            return
        if how == "vector" and (distance or 0.0) > entity_threshold:
            return
        hit = cands.setdefault(c["id"], {"name": c["name"], "how": set(), "distance": None, "jaccard": j})
        hit["how"].add(how)
        if distance is not None:
            hit["distance"] = distance

    if tok:
        q = "|".join(tok[:MAX_ENTITY_QUERY_TOKENS])
        for c in client.ro(graph, "engram/find_entity_fulltext", {"q": q, "limit": FULLTEXT_CANDIDATES}):
            see(c, "fulltext", None)
    if e["embedding"] is not None:
        emb = list(e["embedding"])
        for c in client.ro(graph, "engram/find_entity_vector", {"emb": emb, "k": VECTOR_CANDIDATES}):
            see(c, "vector", c["distance"])
    return cands


def near_duplicates(
    client: GraphClient,
    graph: str,
    *,
    entity_threshold: float = ENTITY_NEAR,
    jaccard: float = FULLTEXT_JACCARD,
) -> list[dict[str, Any]]:
    """Read-only: ``(younger, older)`` entity pairs that ``engram/resolve_entity`` would have joined.

    Candidates must be older by ``(created_at, id)``, of the same kind and numeric tokens, and either share
    >= ``jaccard`` of their name tokens with one token set containing the other (full-text), or lie within
    ``entity_threshold`` distance (vector).
    """
    born: dict[str, tuple[int, str]] = {}  # id -> (created_at, id): who is older
    for page in _page(client, graph):
        for e in page:
            born[e["id"]] = (e["created_at"] or 0, e["id"])

    pairs: list[dict[str, Any]] = []
    for page in _page(client, graph):
        for e in page:
            for c_id, c in _older_candidates(client, graph, e, born, jaccard, entity_threshold).items():
                pairs.append(
                    {
                        "younger_id": e["id"],
                        "younger_name": e["name"],
                        "older_id": c_id,
                        "older_name": c["name"],
                        "kind": e["kind"],
                        "how": "+".join(sorted(c["how"])),
                        "distance": c["distance"],
                        "jaccard": c["jaccard"],
                    }
                )
    return sorted(pairs, key=lambda p: (p["younger_id"], p["older_id"]))


def constraint_status(client: GraphClient, graph: str) -> str:
    label, prop = ENTITY_KEY
    for r in client.ro(graph, "schema/list_constraints"):
        if r["type"] == "UNIQUE" and r["label"] == label and r["properties"] == [prop]:
            return r["status"]
    return "MISSING"


def run(client: GraphClient, graph: str, *, dry_run: bool = False) -> dict[str, Any]:
    """The whole migration. Returns the report dict printed (or dumped as JSON) by the CLI."""
    dups = duplicate_names(client, graph)
    backfill = backfill_entity_keys(client, graph, dry_run=dry_run)
    if not dry_run:
        apply_schema(
            client, graph
        )  # adds UNIQUE(Entity.norm_name) if missing; a FAILED one only logs a warning
    return {
        "graph": graph,
        "dry_run": dry_run,
        "duplicate_names": dups,
        "backfill": backfill,
        "constraint": constraint_status(client, graph),
        "near_duplicates": near_duplicates(client, graph),
    }


def format_report(rep: dict[str, Any], max_pairs: int = 50) -> str:
    b = rep["backfill"]
    lines = [f"graph {rep['graph']}" + ("  (dry run: nothing written)" if rep["dry_run"] else "")]
    verb = "would update" if rep["dry_run"] else "updated"
    lines.append(
        f"entities: {b['total']}; without tok/num_key: {b['missing']}; {verb}: "
        f"{b['missing'] if rep['dry_run'] else b['updated']}"
    )
    lines.append(f"UNIQUE(Entity.norm_name): {rep['constraint']}")
    for d in rep["duplicate_names"]:
        lines.append(
            f"DUPLICATE KEY: {d['n']} entities share the name '{d['norm_name']}' (resolve them by hand first)"
        )
    pairs = rep["near_duplicates"]
    lines.append(
        f"near-duplicate legacy entities: {len(pairs)} pair(s) (younger -> older; review, nothing is merged)"
    )
    for p in pairs[:max_pairs]:
        dist = "-" if p["distance"] is None else f"{p['distance']:.3f}"
        lines.append(
            f"  {p['younger_name']!r} -> {p['older_name']!r}  [{p['kind']}] via {p['how']}  "
            f"jaccard {p['jaccard']:.2f}  distance {dist}  ({p['younger_id']} -> {p['older_id']})"
        )
    if len(pairs) > max_pairs:
        lines.append(f"  ... {len(pairs) - max_pairs} more (use --json for all)")
    return "\n".join(lines)


def to_json(rep: dict[str, Any]) -> str:
    return json.dumps(rep, indent=2, default=list)
