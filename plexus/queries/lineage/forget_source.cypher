// name: lineage/forget_source
// purpose: ONE atomic statement: forget everything derived from a Source: every Fact reaching it through (f)-[:DERIVED_FROM*1..5]->(src) gets status 'forgotten' and valid_to = min(valid_to, now); Decisions BASED_ON those facts are flagged (not deleted).
// params: source_id:str, now:int, limit:int, reason:str
// returns: fact_ids (facts changed by this call), decision_ids (decisions flagged), handoff_ids (handoffs that CARRY a forgotten fact, reported only), truncated (true when `limit` facts were hit: call again to continue). Zero rows = no such Source.
// mode: rw
// Idempotent: facts that are already 'forgotten' are skipped, so a second call changes nothing. The write is bounded by $limit (callers use <= 5000) because LIMIT does not stop eager writes: it is applied BEFORE the SET.
// A fact derived from several sources is forgotten as soon as ANY of them is forgotten (forget is strict; quarantine is the reversible variant).
MATCH (src:Source {id: $source_id})
OPTIONAL MATCH (f:Fact)-[:DERIVED_FROM*1..5]->(src)
WHERE f.status <> 'forgotten'
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
RETURN [a IN fs | a.id] AS fact_ids, [b IN ds | b.id] AS decision_ids, [c IN hs | c.id] AS handoff_ids,
       size(fs) >= $limit AS truncated
