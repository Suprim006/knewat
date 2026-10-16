"""Generate ``plexus/queries/lineage/impact_source.cypher`` and ``impact_fact.cypher`` (never hand-edit 12 copies).

Run from the repo root: ``python scripts/gen_impact_queries.py``. Both files share the same 12-hop level-wise
expansion as ``lineage/quarantine`` and ``forget_source``; the joins to readers / decisions / handoffs / tasks are four
``CALL`` subqueries that each read the collected fact list once (P9-int).
"""

from __future__ import annotations

from pathlib import Path

QUERIES = Path(__file__).resolve().parent.parent / "plexus" / "queries" / "lineage"
MAX_DEPTH = 12

HEADER = """// name: lineage/impact_{kind}
// purpose: READ-ONLY blast radius of a {Kind}: {what} through up to $depth DERIVED_FROM hops, the Steps (hence agents) that READ them, the Decisions BASED_ON them (and the Tasks those decisions are FOR) and the Handoffs that CARRY them. Nothing is written.
// params: id:str, depth:int, limit:int
// returns: fact_ids, statuses, fact_ats (parallel lists; at most `limit` facts, any status; fact_ats = valid_from), truncated (true when `limit` facts were hit), steps_total, agent_ids (every agent that read one; never cut), step_first, step_last (min / max Step.at over the reads), decision_ids, decision_ats, handoff_ids, handoff_ats, task_ids (all distinct, uncut: the caller slices). Zero rows = no such {Kind}.
// mode: ro
// Same level-wise expansion as lineage/{twin} (P9-b): up to 12 fixed one-hop OPTIONAL MATCHes over DISTINCT facts, each skipped once $depth is reached, so a diamond lineage costs its edges, not its paths. The joins are four CALL subqueries, each reading the collected fact list ONCE as one Unwind -> Conditional Traverse from the bound fact (P9-int: the old form carried the 5,000-element list as a grouping key through three UNWINDs, which hashed it once per row and never finished). One statement = one snapshot.
"""


def build(kind: str) -> str:
    twin = {"source": "quarantine", "fact": "forget_source"}[kind]
    what = {
        "source": "every Fact that reaches the Source",
        "fact": "the Fact itself and every Fact derived from it",
    }[kind]
    label = "Source" if kind == "source" else "Fact"
    out = [HEADER.format(kind=kind, Kind=label, what=what, twin=twin).rstrip("\n")]
    out.append(f"MATCH (src:{label} {{id: $id}})")
    out.append("OPTIONAL MATCH (n1:Fact)-[:DERIVED_FROM]->(src)")
    out.append("WITH src, collect(DISTINCT n1) AS l1")
    out.append("WITH src, l1 AS reach, l1 AS fr")
    for k in range(2, MAX_DEPTH + 1):
        out.append(f"UNWIND CASE WHEN size(fr) = 0 OR $depth < {k} THEN [null] ELSE fr END AS x{k}")
        out.append(f"OPTIONAL MATCH (n{k}:Fact)-[:DERIVED_FROM]->(x{k})")
        out.append(f"WITH src, reach, collect(DISTINCT n{k}) AS l{k}")
        out.append(f"WITH src, reach + l{k} AS reach, l{k} AS fr")
    out.append("WITH src, reach" if kind == "source" else "WITH src, reach + [src] AS reach")
    out.append("UNWIND CASE WHEN size(reach) = 0 THEN [null] ELSE reach END AS f")
    out.append("WITH DISTINCT src, f LIMIT $limit")
    out.append("WITH src, collect(f) AS fs")
    out += [
        "CALL {",
        "  WITH fs",
        "  UNWIND CASE WHEN size(fs) = 0 THEN [null] ELSE fs END AS x",
        "  OPTIONAL MATCH (s:Step)-[:READ]->(x)",
        "  RETURN count(DISTINCT s) AS steps_total, collect(DISTINCT s.agent_id) AS agent_ids, min(s.at) AS step_first, max(s.at) AS step_last",
        "}",
        "CALL {",
        "  WITH fs",
        "  UNWIND CASE WHEN size(fs) = 0 THEN [null] ELSE fs END AS y",
        "  OPTIONAL MATCH (d:Decision)-[:BASED_ON]->(y)",
        "  RETURN collect(DISTINCT d) AS ds",
        "}",
        "CALL {",
        "  WITH fs",
        "  UNWIND CASE WHEN size(fs) = 0 THEN [null] ELSE fs END AS w",
        "  OPTIONAL MATCH (h:Handoff)-[:CARRIES]->(w)",
        "  RETURN collect(DISTINCT h) AS hs",
        "}",
        "CALL {",
        "  WITH ds",
        "  UNWIND CASE WHEN size(ds) = 0 THEN [null] ELSE ds END AS dd",
        "  OPTIONAL MATCH (dd)-[:FOR]->(t:Task)",
        "  RETURN collect(DISTINCT t) AS tks",
        "}",
        "RETURN [a IN fs | a.id] AS fact_ids, [a IN fs | a.status] AS statuses, [a IN fs | a.valid_from] AS fact_ats,",
        "       size(fs) >= $limit AS truncated, steps_total, agent_ids, step_first, step_last,",
        "       [b IN ds | b.id] AS decision_ids, [b IN ds | b.at] AS decision_ats,",
        "       [e IN hs | e.id] AS handoff_ids, [e IN hs | e.at] AS handoff_ats, [c IN tks | c.id] AS task_ids",
    ]
    return "\n".join(out) + "\n"


def main() -> None:
    for kind in ("source", "fact"):
        (QUERIES / f"impact_{kind}.cypher").write_text(build(kind), encoding="utf-8", newline="\n")


if __name__ == "__main__":
    main()
