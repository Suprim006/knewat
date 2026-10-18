// name: lineage/release_quarantine
// purpose: ONE atomic statement (stretch): undo lineage/quarantine for a Source: quarantined facts that reach it through DERIVED_FROM*1..$depth (1..12; use the depth the quarantine used, default 8) get their prior status back.
// params: source_id:str, limit:int, depth:int
// returns: fact_ids (facts restored), truncated. Zero rows = no such Source.
// mode: rw
// P13 (D-015): also clears Source.quarantined_at, so the Source counts as live again for the facts it shares with other (still quarantined) Sources: a fact hidden because ALL its sources were quarantined is restored as soon as ONE of them
// is released (it reaches the released Source, so it is in the cascade). Corroborated facts were never touched by quarantine, so there is nothing to undo for them.
// Facts quarantined through ANOTHER source are restored too if they also reach this one; release the sources you trust again, in the order you like.
// Plan shape (P5 review Q3, P9-b): the cascade is expanded level by level FROM the Source (up to 12 fixed one-hop OPTIONAL MATCHes, each driven by the
// DISTINCT facts found at the previous level and skipped once $depth is reached), so the work follows DERIVED_FROM edges and a diamond lineage
// (fan-in 3, depth 12 = ~500k paths, 60 facts) costs its edges, not its paths. `(f:Fact)-[:DERIVED_FROM*1..N]->(src)` would be planned from the
// Fact side (a scan of EVERY fact) and enumerates paths. A fact that is only a stepping stone (status not selected) still links the facts behind it
// to the source.
MATCH (src:Source {id: $source_id})
OPTIONAL MATCH (n1:Fact)-[:DERIVED_FROM]->(src)
WITH src, collect(DISTINCT n1) AS l1
WITH src, l1 AS reach, l1 AS fr
UNWIND CASE WHEN size(fr) = 0 OR $depth < 2 THEN [null] ELSE fr END AS x2
OPTIONAL MATCH (n2:Fact)-[:DERIVED_FROM]->(x2)
WITH src, reach, collect(DISTINCT n2) AS l2
WITH src, reach + l2 AS reach, l2 AS fr
UNWIND CASE WHEN size(fr) = 0 OR $depth < 3 THEN [null] ELSE fr END AS x3
OPTIONAL MATCH (n3:Fact)-[:DERIVED_FROM]->(x3)
WITH src, reach, collect(DISTINCT n3) AS l3
WITH src, reach + l3 AS reach, l3 AS fr
UNWIND CASE WHEN size(fr) = 0 OR $depth < 4 THEN [null] ELSE fr END AS x4
OPTIONAL MATCH (n4:Fact)-[:DERIVED_FROM]->(x4)
WITH src, reach, collect(DISTINCT n4) AS l4
WITH src, reach + l4 AS reach, l4 AS fr
UNWIND CASE WHEN size(fr) = 0 OR $depth < 5 THEN [null] ELSE fr END AS x5
OPTIONAL MATCH (n5:Fact)-[:DERIVED_FROM]->(x5)
WITH src, reach, collect(DISTINCT n5) AS l5
WITH src, reach + l5 AS reach, l5 AS fr
UNWIND CASE WHEN size(fr) = 0 OR $depth < 6 THEN [null] ELSE fr END AS x6
OPTIONAL MATCH (n6:Fact)-[:DERIVED_FROM]->(x6)
WITH src, reach, collect(DISTINCT n6) AS l6
WITH src, reach + l6 AS reach, l6 AS fr
UNWIND CASE WHEN size(fr) = 0 OR $depth < 7 THEN [null] ELSE fr END AS x7
OPTIONAL MATCH (n7:Fact)-[:DERIVED_FROM]->(x7)
WITH src, reach, collect(DISTINCT n7) AS l7
WITH src, reach + l7 AS reach, l7 AS fr
UNWIND CASE WHEN size(fr) = 0 OR $depth < 8 THEN [null] ELSE fr END AS x8
OPTIONAL MATCH (n8:Fact)-[:DERIVED_FROM]->(x8)
WITH src, reach, collect(DISTINCT n8) AS l8
WITH src, reach + l8 AS reach, l8 AS fr
UNWIND CASE WHEN size(fr) = 0 OR $depth < 9 THEN [null] ELSE fr END AS x9
OPTIONAL MATCH (n9:Fact)-[:DERIVED_FROM]->(x9)
WITH src, reach, collect(DISTINCT n9) AS l9
WITH src, reach + l9 AS reach, l9 AS fr
UNWIND CASE WHEN size(fr) = 0 OR $depth < 10 THEN [null] ELSE fr END AS x10
OPTIONAL MATCH (n10:Fact)-[:DERIVED_FROM]->(x10)
WITH src, reach, collect(DISTINCT n10) AS l10
WITH src, reach + l10 AS reach, l10 AS fr
UNWIND CASE WHEN size(fr) = 0 OR $depth < 11 THEN [null] ELSE fr END AS x11
OPTIONAL MATCH (n11:Fact)-[:DERIVED_FROM]->(x11)
WITH src, reach, collect(DISTINCT n11) AS l11
WITH src, reach + l11 AS reach, l11 AS fr
UNWIND CASE WHEN size(fr) = 0 OR $depth < 12 THEN [null] ELSE fr END AS x12
OPTIONAL MATCH (n12:Fact)-[:DERIVED_FROM]->(x12)
WITH src, reach, collect(DISTINCT n12) AS l12
WITH src, reach + l12 AS reach, l12 AS fr
WITH src, reach
WITH src, [r IN reach WHERE r.status = 'quarantined'] AS cand
UNWIND CASE WHEN size(cand) = 0 THEN [null] ELSE cand END AS f
WITH DISTINCT src, f LIMIT $limit
WITH src, collect(f) AS fs
FOREACH (z IN fs | SET z.status = coalesce(z.prior_status, 'active') REMOVE z.prior_status, z.quarantined_at)
FOREACH (sq IN [src] | REMOVE sq.quarantined_at)
RETURN [a IN fs | a.id] AS fact_ids, size(fs) >= $limit AS truncated
