// name: lineage/release_quarantine
// purpose: ONE atomic statement (stretch): undo lineage/quarantine for a Source: quarantined facts that reach it through DERIVED_FROM*1..5 get their prior status back.
// params: source_id:str, limit:int
// returns: fact_ids (facts restored), truncated. Zero rows = no such Source.
// mode: rw
// Facts quarantined through ANOTHER source are restored too if they also reach this one; release the sources you trust again, in the order you like.
MATCH (src:Source {id: $source_id})
OPTIONAL MATCH (f:Fact)-[:DERIVED_FROM*1..5]->(src)
WHERE f.status = 'quarantined'
WITH DISTINCT src, f LIMIT $limit
WITH src, collect(f) AS fs
FOREACH (z IN fs | SET z.status = coalesce(z.prior_status, 'active') REMOVE z.prior_status, z.quarantined_at)
RETURN [a IN fs | a.id] AS fact_ids, size(fs) >= $limit AS truncated
