// name: lineage/release_quarantine
// purpose: ONE atomic statement (stretch): undo lineage/quarantine for a Source: quarantined facts that reach it through DERIVED_FROM*1..5 get their prior status back.
// params: source_id:str, limit:int
// returns: fact_ids (facts restored), truncated. Zero rows = no such Source.
// mode: rw
// Facts quarantined through ANOTHER source are restored too if they also reach this one; release the sources you trust again, in the order you like.
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
WITH src, [r IN reach WHERE r.status = 'quarantined'] AS cand
UNWIND CASE WHEN size(cand) = 0 THEN [null] ELSE cand END AS f
WITH DISTINCT src, f LIMIT $limit
WITH src, collect(f) AS fs
FOREACH (z IN fs | SET z.status = coalesce(z.prior_status, 'active') REMOVE z.prior_status, z.quarantined_at)
RETURN [a IN fs | a.id] AS fact_ids, size(fs) >= $limit AS truncated
