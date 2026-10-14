// name: lineage/forget_source
// purpose: ONE atomic statement: forget everything derived from a Source: every Fact reaching it through (f)-[:DERIVED_FROM*1..5]->(src) gets status 'forgotten' and valid_to = min(valid_to, now); Decisions BASED_ON those facts are flagged (not deleted).
// params: source_id:str, now:int, limit:int, reason:str, max_detail:int
// returns: fact_ids (facts changed by this call), decision_ids (decisions flagged; at most max_detail listed), decisions_total, handoff_ids (handoffs that CARRY a forgotten fact, reported only; at most max_detail listed), handoffs_total, truncated (true when `limit` facts were hit: call again to continue). Zero rows = no such Source.
// mode: rw
// Idempotent: facts that are already 'forgotten' are skipped, so a second call changes nothing. The write is bounded by $limit (callers use <= 5000) because LIMIT does not stop eager writes: it is applied BEFORE the SET.
// A fact derived from several sources is forgotten as soon as ANY of them is forgotten (forget is strict; quarantine is the reversible variant).
// The decision / handoff lists in the response are cut at max_detail (the totals are exact); every affected decision is still flagged.
// Plan shape (P5 review Q3): the cascade is expanded level by level FROM the Source (five fixed one-hop OPTIONAL MATCHes, each driven by the
// facts found at the previous level), so the work follows DERIVED_FROM edges. `(f:Fact)-[:DERIVED_FROM*1..5]->(src)` is planned from the
// Fact side (a label scan or a status-index scan of EVERY fact) whatever the pattern direction. Reach and depth are the same as *1..5; a fact
// that is only a stepping stone (status not selected) still links the facts behind it to the source.
MATCH (src:Source {id: $source_id})
OPTIONAL MATCH (n1:Fact)-[:DERIVED_FROM]->(src)
WITH src, collect(DISTINCT n1) AS l1
UNWIND CASE WHEN size(l1) = 0 THEN [null] ELSE l1 END AS x1
OPTIONAL MATCH (n2:Fact)-[:DERIVED_FROM]->(x1)
WITH src, l1, collect(DISTINCT n2) AS l2
UNWIND CASE WHEN size(l2) = 0 THEN [null] ELSE l2 END AS x2
OPTIONAL MATCH (n3:Fact)-[:DERIVED_FROM]->(x2)
WITH src, l1, l2, collect(DISTINCT n3) AS l3
UNWIND CASE WHEN size(l3) = 0 THEN [null] ELSE l3 END AS x3
OPTIONAL MATCH (n4:Fact)-[:DERIVED_FROM]->(x3)
WITH src, l1, l2, l3, collect(DISTINCT n4) AS l4
UNWIND CASE WHEN size(l4) = 0 THEN [null] ELSE l4 END AS x4
OPTIONAL MATCH (n5:Fact)-[:DERIVED_FROM]->(x4)
WITH src, l1, l2, l3, l4, collect(DISTINCT n5) AS l5
WITH src, l1 + l2 + l3 + l4 + l5 AS reach
WITH src, [r IN reach WHERE r.status IN ['active', 'superseded', 'quarantined']] AS cand
UNWIND CASE WHEN size(cand) = 0 THEN [null] ELSE cand END AS f
WITH DISTINCT src, f LIMIT $limit
WITH src, collect(f) AS fs
UNWIND CASE WHEN size(fs) = 0 THEN [null] ELSE fs END AS x
OPTIONAL MATCH (d:Decision)-[:BASED_ON]->(x)
WITH src, fs, collect(DISTINCT d) AS ds
UNWIND CASE WHEN size(fs) = 0 THEN [null] ELSE fs END AS y
OPTIONAL MATCH (h:Handoff)-[:CARRIES]->(y)
WITH src, fs, ds, collect(DISTINCT h) AS hs
FOREACH (z IN fs |
  SET z.status = 'forgotten', z.forgotten_at = $now,
      z.valid_to = CASE WHEN z.valid_to < $now THEN z.valid_to ELSE $now END)
FOREACH (e IN ds | SET e.flagged = true, e.flag_reason = $reason)
RETURN [a IN fs | a.id] AS fact_ids, [b IN ds[0..$max_detail] | b.id] AS decision_ids, size(ds) AS decisions_total,
       [c IN hs[0..$max_detail] | c.id] AS handoff_ids, size(hs) AS handoffs_total, size(fs) >= $limit AS truncated
