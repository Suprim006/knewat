// name: lineage/quarantine
// purpose: ONE atomic statement (stretch): quarantine a poisoned Source. Facts reaching it through (f)-[:DERIVED_FROM*1..5]->(src) get status 'quarantined' (hidden from recall / as_of, reversible), and the blast radius is returned: the Steps (hence agents) that READ them, the Decisions BASED_ON them and the Handoffs that CARRY them.
// params: source_id:str, now:int, limit:int
// returns: fact_ids (facts changed), reads [{agent_id, step_id, n, at, fact_id}], decision_ids, handoff_ids, truncated (true when `limit` facts were hit: call again). Zero rows = no such Source.
// mode: rw
// Only facts with status 'active' or 'superseded' are touched; the old status is kept in prior_status so lineage/release_quarantine can restore it. Decisions and handoffs are reported, not modified.
// The write is bounded by $limit (callers use <= 5000), applied BEFORE the SET because LIMIT does not stop eager writes.
MATCH (src:Source {id: $source_id})
OPTIONAL MATCH (f:Fact)-[:DERIVED_FROM*1..5]->(src)
WHERE f.status IN ['active', 'superseded']
WITH DISTINCT src, f LIMIT $limit
WITH src, collect(f) AS fs
UNWIND CASE WHEN size(fs) = 0 THEN [null] ELSE fs END AS x
OPTIONAL MATCH (s:Step)-[:READ]->(x)
WITH src, fs, collect(CASE WHEN s IS NULL THEN null ELSE {agent_id: s.agent_id, step_id: s.id, n: s.n, at: s.at, fact_id: x.id} END) AS reads
UNWIND CASE WHEN size(fs) = 0 THEN [null] ELSE fs END AS y
OPTIONAL MATCH (d:Decision)-[:BASED_ON]->(y)
WITH src, fs, reads, collect(DISTINCT d) AS ds
UNWIND CASE WHEN size(fs) = 0 THEN [null] ELSE fs END AS w
OPTIONAL MATCH (h:Handoff)-[:CARRIES]->(w)
WITH src, fs, reads, ds, collect(DISTINCT h) AS hs
FOREACH (z IN fs | SET z.prior_status = z.status, z.status = 'quarantined', z.quarantined_at = $now)
RETURN [a IN fs | a.id] AS fact_ids, reads, [b IN ds | b.id] AS decision_ids, [c IN hs | c.id] AS handoff_ids,
       size(fs) >= $limit AS truncated
