// name: lineage/impact_source
// purpose: READ-ONLY blast radius of a Source: every Fact that reaches the Source through up to $depth DERIVED_FROM hops, the Steps (hence agents) that READ them, the Decisions BASED_ON them (and the Tasks those decisions are FOR) and the Handoffs that CARRY them. Nothing is written.
// params: id:str, depth:int, limit:int
// returns: fact_ids, statuses (parallel lists; at most `limit` facts, any status), truncated (true when `limit` facts were hit), steps_total, agent_ids (every agent that read one; never cut), decision_ids, task_ids, handoff_ids (all distinct, uncut: the caller slices). Zero rows = no such Source.
// mode: ro
// Same level-wise expansion as lineage/quarantine (P9-b): up to 12 fixed one-hop OPTIONAL MATCHes over DISTINCT facts, each skipped once $depth is reached, so a diamond lineage costs its edges, not its paths. One statement = one snapshot.
MATCH (src:Source {id: $id})
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
WITH src, reach AS reach
UNWIND CASE WHEN size(reach) = 0 THEN [null] ELSE reach END AS f
WITH DISTINCT src, f LIMIT $limit
WITH src, collect(f) AS fs
UNWIND CASE WHEN size(fs) = 0 THEN [null] ELSE fs END AS x
OPTIONAL MATCH (s:Step)-[:READ]->(x)
WITH src, fs, collect(DISTINCT s.id) AS step_ids, collect(DISTINCT s.agent_id) AS agent_ids
UNWIND CASE WHEN size(fs) = 0 THEN [null] ELSE fs END AS y
OPTIONAL MATCH (d:Decision)-[:BASED_ON]->(y)
WITH src, fs, step_ids, agent_ids, collect(DISTINCT d) AS ds
UNWIND CASE WHEN size(fs) = 0 THEN [null] ELSE fs END AS w
OPTIONAL MATCH (h:Handoff)-[:CARRIES]->(w)
WITH src, fs, step_ids, agent_ids, ds, collect(DISTINCT h) AS hs
UNWIND CASE WHEN size(ds) = 0 THEN [null] ELSE ds END AS dd
OPTIONAL MATCH (dd)-[:FOR]->(t:Task)
WITH fs, step_ids, agent_ids, ds, hs, collect(DISTINCT t) AS tks
RETURN [a IN fs | a.id] AS fact_ids, [a IN fs | a.status] AS statuses, size(fs) >= $limit AS truncated, size(step_ids) AS steps_total,
       agent_ids, [b IN ds | b.id] AS decision_ids, [c IN tks | c.id] AS task_ids, [e IN hs | e.id] AS handoff_ids
