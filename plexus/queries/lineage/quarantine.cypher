// name: lineage/quarantine
// purpose: ONE atomic statement (stretch): quarantine a poisoned Source. Facts reaching it through (f)-[:DERIVED_FROM*1..5]->(src) get status 'quarantined' (hidden from recall / as_of, reversible), and the blast radius is returned: the Steps (hence agents) that READ them, the Decisions BASED_ON them and the Handoffs that CARRY them.
// params: source_id:str, now:int, limit:int, max_detail:int
// returns: fact_ids (facts changed), reads [{agent_id, step_id, n, at, fact_id}] (earliest first, at most max_detail), reads_total, agent_ids (every agent that read one; never cut), decision_ids (at most max_detail), decisions_total, handoff_ids (at most max_detail), handoffs_total, truncated (true when `limit` facts were hit: call again). Zero rows = no such Source.
// mode: rw
// Only facts with status 'active', 'superseded' or 'dormant' are touched (a dormant fact is quarantined too, and released back to dormant, P7-int); the old status is kept in prior_status so lineage/release_quarantine can restore it. Decisions and handoffs are reported, not modified.
// The write is bounded by $limit (callers use <= 5000), applied BEFORE the SET because LIMIT does not stop eager writes.
// The response is bounded (P5 review Q11): reads / decision_ids / handoff_ids are cut at max_detail (callers use <= 5000), the *_total counts and agent_ids are exact.
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
