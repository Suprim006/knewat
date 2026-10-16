// name: lineage/forget_source
// purpose: ONE atomic statement: forget everything derived from a Source: every Fact reaching it through (f)-[:DERIVED_FROM*1..depth]->(src) (depth = $depth, 1..12, callers default to 8) gets status 'forgotten' and valid_to = min(valid_to, now); Decisions BASED_ON those facts are flagged (not deleted).
// params: source_id:str, now:int, limit:int, depth:int, reason:str, max_detail:int
// returns: fact_ids (facts changed by this call), decision_ids (decisions flagged; at most max_detail listed), decisions_total, handoff_ids (handoffs that CARRY a forgotten fact, reported only; at most max_detail listed), handoffs_total, truncated (true when `limit` facts were hit: call again to continue). Zero rows = no such Source.
// mode: rw
// A 'dormant' fact (moved by memory_sweep) is forgotten too, so restore_fact cannot bring it back (P7-int).
// Idempotent: facts that are already 'forgotten' are skipped, so a second call changes nothing. The write is bounded by $limit (callers use <= 5000) because LIMIT does not stop eager writes: it is applied BEFORE the SET.
// A fact derived from several sources is forgotten as soon as ANY of them is forgotten (forget is strict; quarantine is the reversible variant).
// The decision / handoff lists in the response are cut at max_detail (the totals are exact); every affected decision is still flagged.
// Plan shape (P5 review Q3, P9-b): the cascade is expanded level by level FROM the Source (up to 12 fixed one-hop OPTIONAL MATCHes, each driven by the
// DISTINCT facts found at the previous level and skipped once $depth is reached), so the work follows DERIVED_FROM edges and a diamond lineage
// (fan-in 3, depth 12 = ~500k paths, 60 facts) costs its edges, not its paths. `(f:Fact)-[:DERIVED_FROM*1..N]->(src)` would be planned from the
// Fact side (a scan of EVERY fact) and enumerates paths. A fact that is only a stepping stone (status not selected) still links the facts behind it
// to the source.
// P9-f (Crucible L6-A, 5,000-fact blast: timed out): the reader / decision / handoff joins run in ONE pass over the
// distinct facts, keyed only by the source. The old form chained `UNWIND fs` joins whose `WITH src, fs, collect(...)`
// grouped by the whole fact list (a 5,000-element key hashed once per row). Per fact the OPTIONAL MATCHes multiply
// (readers x decisions x handoffs), which is small for one fact; collect(DISTINCT ...) removes the repeats.
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
WITH src, [r IN reach WHERE r.status IN ['active', 'superseded', 'quarantined', 'dormant']] AS cand
UNWIND CASE WHEN size(cand) = 0 THEN [null] ELSE cand END AS f
WITH DISTINCT src, f LIMIT $limit
OPTIONAL MATCH (d:Decision)-[:BASED_ON]->(f)
OPTIONAL MATCH (h:Handoff)-[:CARRIES]->(f)
WITH src, collect(DISTINCT f) AS fs, collect(DISTINCT d) AS ds, collect(DISTINCT h) AS hs
FOREACH (z IN fs |
  SET z.status = 'forgotten', z.forgotten_at = $now,
      z.valid_to = CASE WHEN z.valid_to < $now THEN z.valid_to ELSE $now END)
FOREACH (e IN ds | SET e.flagged = true, e.flag_reason = $reason)
RETURN [a IN fs | a.id] AS fact_ids, [b IN ds[0..$max_detail] | b.id] AS decision_ids, size(ds) AS decisions_total,
       [c IN hs[0..$max_detail] | c.id] AS handoff_ids, size(hs) AS handoffs_total, size(fs) >= $limit AS truncated
