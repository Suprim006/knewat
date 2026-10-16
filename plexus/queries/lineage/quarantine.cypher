// name: lineage/quarantine
// purpose: ONE atomic statement (stretch): quarantine a poisoned Source. Facts reaching it through (f)-[:DERIVED_FROM*1..depth]->(src) (depth = $depth, 1..12, callers default to 8) get status 'quarantined' (hidden from recall / as_of, reversible), and the blast radius is returned: the Steps (hence agents) that READ them, the Decisions BASED_ON them and the Handoffs that CARRY them.
// params: source_id:str, now:int, limit:int, depth:int, max_detail:int
// returns: fact_ids (facts changed), reads [{agent_id, step_id, n, at, fact_id}] (earliest first, at most max_detail), reads_total, agent_ids (every agent that read one; never cut), decision_ids (at most max_detail), decisions_total, handoff_ids (at most max_detail), handoffs_total, truncated (true when `limit` facts were hit: call again). Zero rows = no such Source.
// mode: rw
// Only facts with status 'active', 'superseded' or 'dormant' are touched (a dormant fact is quarantined too, and released back to dormant, P7-int); the old status is kept in prior_status so lineage/release_quarantine can restore it. Decisions and handoffs are reported, not modified.
// The write is bounded by $limit (callers use <= 5000), applied BEFORE the SET because LIMIT does not stop eager writes.
// The response is bounded (P5 review Q11): reads / decision_ids / handoff_ids are cut at max_detail (callers use <= 5000), the *_total counts and agent_ids are exact.
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
WITH src, [r IN reach WHERE r.status IN ['active', 'superseded', 'dormant']] AS cand
UNWIND CASE WHEN size(cand) = 0 THEN [null] ELSE cand END AS f
WITH DISTINCT src, f LIMIT $limit
WITH src, collect(f) AS fs
UNWIND CASE WHEN size(fs) = 0 THEN [null] ELSE fs END AS x
OPTIONAL MATCH (s:Step)-[:READ]->(x)
WITH src, fs, x, s ORDER BY s.at ASC, s.agent_id ASC, x.id ASC
WITH src, fs, collect(CASE WHEN s IS NULL THEN null ELSE {agent_id: s.agent_id, step_id: s.id, n: s.n, at: s.at, fact_id: x.id} END) AS reads,
     collect(DISTINCT s.agent_id) AS agent_ids
UNWIND CASE WHEN size(fs) = 0 THEN [null] ELSE fs END AS y
OPTIONAL MATCH (d:Decision)-[:BASED_ON]->(y)
WITH src, fs, reads, agent_ids, collect(DISTINCT d) AS ds
UNWIND CASE WHEN size(fs) = 0 THEN [null] ELSE fs END AS w
OPTIONAL MATCH (h:Handoff)-[:CARRIES]->(w)
WITH src, fs, reads, agent_ids, ds, collect(DISTINCT h) AS hs
FOREACH (z IN fs | SET z.prior_status = z.status, z.status = 'quarantined', z.quarantined_at = $now)
RETURN [a IN fs | a.id] AS fact_ids, reads[0..$max_detail] AS reads, size(reads) AS reads_total, agent_ids,
       [b IN ds[0..$max_detail] | b.id] AS decision_ids, size(ds) AS decisions_total,
       [c IN hs[0..$max_detail] | c.id] AS handoff_ids, size(hs) AS handoffs_total, size(fs) >= $limit AS truncated
