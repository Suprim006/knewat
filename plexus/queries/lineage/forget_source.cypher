// name: lineage/forget_source
// purpose: ONE atomic statement: forget everything derived from a Source. Every Fact reaching it through DERIVED_FROM within $depth hops (1..12) gets status 'forgotten' and valid_to = min(valid_to, now), unless another Source still supports it (D-015): then only its edge to this Source is deleted. Decisions BASED_ON the forgotten facts are flagged, not deleted.
// params: source_id:str, now:int, limit:int, depth:int, reason:str, max_detail:int
// returns: fact_ids (forgotten by this call), unlinked [{fact_id, other_sources}] (reached facts that keep another Source: edge to this Source deleted, fact kept; at most max_detail listed), unlinked_total (exact), decision_ids (flagged; at most max_detail listed), decisions_total, handoff_ids (handoffs that CARRY a forgotten fact, reported only; at most max_detail listed), handoffs_total, truncated (true when `limit` facts were hit: call again). Zero rows = no such Source.
// mode: rw
// Idempotent (already 'forgotten' facts are skipped). A 'dormant' fact is forgotten too. $limit bounds the write because LIMIT does not stop eager writes: it is applied BEFORE the SET.
// Multi-source (D-015): a reached fact with a direct edge to some OTHER Source is unlinked (the edge delete is the only write inside a CALL); if every remaining Source is quarantined it becomes 'quarantined' (prior_status kept). Direct Source edges only, as in lineage/quarantine.
// decisions / handoffs describe only the facts this call forgot. They are CALL { WITH fs ... } subqueries returning key-less aggregates, so the fact list is never a grouping key (D-014).
// Cascade (D-014): expanded level by level FROM the Source (12 fixed one-hop OPTIONAL MATCHes over DISTINCT facts, each skipped once $depth is reached), so a diamond lineage costs its edges, not its paths; `(f:Fact)-[:DERIVED_FROM*1..N]->(src)` is planned from the Fact side (scans every fact) and enumerates paths.
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
WITH src, collect(f) AS fs
CALL {
  WITH src, fs
  UNWIND fs AS cx
  WITH src, cx, [(cx)-[:DERIVED_FROM]->(co:Source) | {id: co.id, q: co.quarantined_at}] AS oth
  RETURN collect({f: cx, oth: [o IN oth WHERE o.id <> src.id | {id: o.id, live: o.q IS NULL}]}) AS rows
}
WITH src, size(fs) >= $limit AS trunc, [w IN rows WHERE size(w.oth) = 0 | w.f] AS gone, [w IN rows WHERE size(w.oth) > 0 | w] AS kept
CALL {
  WITH src, trunc, gone, kept
  UNWIND CASE WHEN size(kept) = 0 THEN [null] ELSE kept END AS kw
  WITH src, kw, kw.f AS kf
  OPTIONAL MATCH (kf)-[r:DERIVED_FROM]->(src)
  DELETE r
  RETURN count(kw) AS nk
}
CALL {
  WITH src, trunc, gone, kept, nk
  UNWIND CASE WHEN size(gone) = 0 THEN [null] ELSE gone END AS x
  OPTIONAL MATCH (d:Decision)-[:BASED_ON]->(x)
  RETURN collect(DISTINCT d) AS ds
}
CALL {
  WITH src, trunc, gone, kept, nk, ds
  UNWIND CASE WHEN size(gone) = 0 THEN [null] ELSE gone END AS y
  OPTIONAL MATCH (h:Handoff)-[:CARRIES]->(y)
  RETURN collect(DISTINCT h) AS hs
}
FOREACH (z IN gone |
  SET z.status = 'forgotten', z.forgotten_at = $now,
      z.valid_to = CASE WHEN z.valid_to < $now THEN z.valid_to ELSE $now END)
FOREACH (u IN [w IN kept WHERE NOT any(o IN w.oth WHERE o.live) AND w.f.status IN ['active', 'superseded', 'dormant'] | w.f] |
  SET u.prior_status = u.status, u.status = 'quarantined', u.quarantined_at = $now)
FOREACH (e IN ds | SET e.flagged = true, e.flag_reason = $reason)
RETURN [a IN gone | a.id] AS fact_ids, [b IN ds[0..$max_detail] | b.id] AS decision_ids, size(ds) AS decisions_total,
       [c IN hs[0..$max_detail] | c.id] AS handoff_ids, size(hs) AS handoffs_total,
       [k IN kept[0..$max_detail] | {fact_id: k.f.id, other_sources: [o IN k.oth | o.id]}] AS unlinked, size(kept) AS unlinked_total,
       trunc AS truncated
