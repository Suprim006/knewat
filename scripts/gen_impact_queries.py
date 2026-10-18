"""Generate ``knewat/queries/lineage/impact_source.cypher`` and ``impact_fact.cypher`` (never hand-edit 12 copies).

Run from the repo root: ``python scripts/gen_impact_queries.py``. Both files share the 12-hop level-wise expansion of
``lineage/quarantine`` and ``forget_source``, then four ``CALL`` subqueries read the collected fact list once each.
"""

from __future__ import annotations

from pathlib import Path

QUERIES = Path(__file__).resolve().parent.parent / "knewat" / "queries" / "lineage"
MAX_DEPTH = 12

HEADER = """// name: lineage/impact_{kind}
// purpose: READ-ONLY blast radius of a {Kind}: {what} within $depth DERIVED_FROM hops, the Steps (hence agents) that READ them, the Decisions BASED_ON them (and their Tasks) and the Handoffs that CARRY them. Nothing is written.
// params: id:str, depth:int, limit:int
// returns: {corroborated}fact_ids, statuses, fact_ats (valid_from), fact_created (created_at) (parallel lists; at most `limit` facts, any status), truncated (true when `limit` facts were hit), steps_total, agent_ids (never cut), step_first, step_last (min / max Step.at over the reads), decision_ids, decision_ats, handoff_ids, handoff_ats, task_ids (all distinct, uncut: the caller slices). Zero rows = no such {Kind}.
// mode: ro
// Same level-wise expansion as lineage/{twin} (D-014: a diamond lineage costs its edges, not its paths). The joins are four CALL subqueries that each read the collected fact list once, so the list is never a grouping key (it was hashed once per row and never finished).{note}
"""

CORROBORATED_COL = (
    "corroborated_ids (source only: reached facts with a direct DERIVED_FROM edge to ANOTHER Source that is not quarantined, "
    "i.e. the ones lineage/quarantine keeps visible; a subset of fact_ids, uncut), "
)
CORROBORATED_NOTE = " corroborated_ids is one more CALL subquery of the same shape (D-015)."


def build(kind: str) -> str:
    twin = {"source": "quarantine", "fact": "forget_source"}[kind]
    what = {
        "source": "every Fact that reaches the Source",
        "fact": "the Fact itself and every Fact derived from it",
    }[kind]
    label = "Source" if kind == "source" else "Fact"
    is_src = kind == "source"
    out = [
        HEADER.format(
            kind=kind,
            Kind=label,
            what=what,
            twin=twin,
            corroborated=CORROBORATED_COL if is_src else "",
            note=CORROBORATED_NOTE if is_src else "",
        ).rstrip("\n")
    ]
    out.append(f"MATCH (src:{label} {{id: $id}})")
    out.append("OPTIONAL MATCH (n1:Fact)-[:DERIVED_FROM]->(src)")
    out.append("WITH src, collect(DISTINCT n1) AS l1")
    out.append("WITH src, l1 AS reach, l1 AS fr")
    for k in range(2, MAX_DEPTH + 1):
        out.append(f"UNWIND CASE WHEN size(fr) = 0 OR $depth < {k} THEN [null] ELSE fr END AS x{k}")
        out.append(f"OPTIONAL MATCH (n{k}:Fact)-[:DERIVED_FROM]->(x{k})")
        out.append(f"WITH src, reach, collect(DISTINCT n{k}) AS l{k}")
        out.append(f"WITH src, reach + l{k} AS reach, l{k} AS fr")
    out.append("WITH src, reach" if kind == "source" else "WITH src, [src] + reach AS reach")
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
        *(
            [
                "CALL {",
                "  WITH src, fs",
                "  UNWIND fs AS cx",
                "  WITH src, cx, [(cx)-[:DERIVED_FROM]->(co:Source) | {id: co.id, q: co.quarantined_at}] AS oth",
                "  RETURN collect(CASE WHEN size([o IN oth WHERE o.id <> src.id AND o.q IS NULL]) > 0 THEN cx.id END) AS corroborated_ids",
                "}",
            ]
            if is_src
            else []
        ),
        "RETURN [a IN fs | a.id] AS fact_ids, [a IN fs | a.status] AS statuses, [a IN fs | a.valid_from] AS fact_ats, [a IN fs | a.created_at] AS fact_created,",
        "       size(fs) >= $limit AS truncated, steps_total, agent_ids, step_first, step_last,",
        "       [b IN ds | b.id] AS decision_ids, [b IN ds | b.at] AS decision_ats,",
        "       [e IN hs | e.id] AS handoff_ids, [e IN hs | e.at] AS handoff_ats, [c IN tks | c.id] AS task_ids"
        + (", corroborated_ids" if is_src else ""),
    ]
    return "\n".join(out) + "\n"


def main() -> None:
    for kind in ("source", "fact"):
        (QUERIES / f"impact_{kind}.cypher").write_text(build(kind), encoding="utf-8", newline="\n")


if __name__ == "__main__":
    main()
