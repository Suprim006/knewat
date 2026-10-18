// name: lineage/quarantine
// purpose: ONE atomic statement (stretch): quarantine a poisoned Source. Facts reaching it through DERIVED_FROM within $depth hops (1..12) get status 'quarantined' (hidden from recall / as_of, reversible) UNLESS another live Source still supports them (D-015). Returns the blast radius: the Steps (hence agents) that READ them, the Decisions BASED_ON them and the Handoffs that CARRY them.
// params: source_id:str, now:int, limit:int, depth:int, max_detail:int
// returns: fact_ids (hidden by this call), corroborated [{fact_id, other_sources}] (reached facts that stay visible through another non-quarantined Source; at most max_detail listed), corroborated_total (exact), reads [{agent_id, step_id, n, at, fact_id}] (earliest first, at most max_detail), reads_total ((step, fact) pairs), agent_ids (never cut), decision_ids (at most max_detail), decisions_total, handoff_ids (at most max_detail), handoffs_total, truncated (true when `limit` facts were hit: call again). Zero rows = no such Source.
// mode: rw
// Multi-source (D-015): the Source is marked (Source.quarantined_at, first quarantine wins; release_quarantine removes it). A reached fact is hidden only without a direct DERIVED_FROM edge to another Source with quarantined_at IS NULL; otherwise it is corroborated and untouched. Direct Source edges only: a derived fact is rescued by its own Source, never by a corroborated parent.
// The Source check is ONE CALL { WITH src, fs ... } with a pattern comprehension and a plain list comprehension. Every later CALL imports all variables in scope (6.0.2) and works on the hidden list only, so reads / decisions / handoffs describe what this call changed.
// Only 'active', 'superseded' and 'dormant' facts are touched; the old status goes to prior_status for release_quarantine. $limit bounds the write because LIMIT does not stop eager writes: it is applied BEFORE the SET. Detail lists are cut at max_detail; totals and agent_ids are exact.
// reads / decisions / handoffs are three key-less CALL { WITH fs ... } aggregates, so the fact list is never a grouping key (D-014; carried through UNWIND/collect it timed out at 2,500 facts).
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
WITH src, [r IN reach WHERE r.status IN ['active', 'superseded', 'dormant']] AS cand
UNWIND CASE WHEN size(cand) = 0 THEN [null] ELSE cand END AS f
WITH DISTINCT src, f LIMIT $limit
WITH src, collect(f) AS fs
CALL {
  WITH src, fs
  UNWIND fs AS cx
  WITH src, cx, [(cx)-[:DERIVED_FROM]->(co:Source) | {id: co.id, q: co.quarantined_at}] AS oth
  RETURN collect({f: cx, live: [o IN oth WHERE o.id <> src.id AND o.q IS NULL | o.id]}) AS rows
}
WITH src, size(fs) >= $limit AS trunc, [w IN rows WHERE size(w.live) = 0 | w.f] AS hid, [w IN rows WHERE size(w.live) > 0 | w] AS cs
CALL {
  WITH src, trunc, hid, cs
  UNWIND CASE WHEN size(hid) = 0 THEN [null] ELSE hid END AS x
  OPTIONAL MATCH (s:Step)-[:READ]->(x)
  WITH x, s ORDER BY s.at ASC, s.agent_id ASC, x.id ASC
  RETURN collect(CASE WHEN s IS NULL THEN null ELSE {agent_id: s.agent_id, step_id: s.id, n: s.n, at: s.at, fact_id: x.id} END) AS reads,
         collect(DISTINCT s.agent_id) AS agent_ids
}
CALL {
  WITH src, trunc, hid, cs
  UNWIND CASE WHEN size(hid) = 0 THEN [null] ELSE hid END AS y
  OPTIONAL MATCH (d:Decision)-[:BASED_ON]->(y)
  RETURN collect(DISTINCT d) AS ds
}
CALL {
  WITH src, trunc, hid, cs
  UNWIND CASE WHEN size(hid) = 0 THEN [null] ELSE hid END AS w
  OPTIONAL MATCH (h:Handoff)-[:CARRIES]->(w)
  RETURN collect(DISTINCT h) AS hs
}
FOREACH (z IN hid | SET z.prior_status = z.status, z.status = 'quarantined', z.quarantined_at = $now)
FOREACH (sq IN [src] | SET sq.quarantined_at = coalesce(sq.quarantined_at, $now))
RETURN [a IN hid | a.id] AS fact_ids, reads[0..$max_detail] AS reads, size(reads) AS reads_total, agent_ids,
       [b IN ds[0..$max_detail] | b.id] AS decision_ids, size(ds) AS decisions_total,
       [c IN hs[0..$max_detail] | c.id] AS handoff_ids, size(hs) AS handoffs_total,
       [k IN cs[0..$max_detail] | {fact_id: k.f.id, other_sources: k.live}] AS corroborated, size(cs) AS corroborated_total,
       trunc AS truncated
