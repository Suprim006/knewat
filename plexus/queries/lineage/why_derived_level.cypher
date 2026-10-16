// name: lineage/why_derived_level
// purpose: One level of the DERIVED_FROM ancestry for lineage/why: the edges out of a frontier of Facts, plus the asserting agent of derived Facts and the Session / agent behind derived Episodes.
// params: frontier:list[str], limit:int
// returns: s, sl, rel, t, tl, prio (same shape as lineage/why_edges). One row per distinct edge; the caller feeds the Fact targets back as the next frontier.
// mode: ro
// Level-wise over DISTINCT nodes (P9-b): `(f)-[:DERIVED_FROM*1..N]->(x)` enumerates PATHS, which explode on a diamond lineage (fan-in 3, depth 12 = ~500k paths for 60 facts).
// Each branch is capped by $limit rows and anchored at the frontier ids (index seek on Fact.id).
UNWIND $frontier AS fid
MATCH (f:Fact {id: fid})-[:DERIVED_FROM]->(x)
RETURN DISTINCT f.id AS s, 'Fact' AS sl, 'DERIVED_FROM' AS rel, x.id AS t, labels(x)[0] AS tl, 3 AS prio LIMIT $limit
UNION
UNWIND $frontier AS fid
MATCH (:Fact {id: fid})-[:DERIVED_FROM]->(g:Fact)-[:ASSERTED_BY]->(a:Agent)
RETURN DISTINCT g.id AS s, 'Fact' AS sl, 'ASSERTED_BY' AS rel, a.id AS t, 'Agent' AS tl, 4 AS prio LIMIT $limit
UNION
UNWIND $frontier AS fid
MATCH (:Fact {id: fid})-[:DERIVED_FROM]->(e:Episode)<-[:HAS_EPISODE]-(se:Session)
RETURN DISTINCT se.id AS s, 'Session' AS sl, 'HAS_EPISODE' AS rel, e.id AS t, 'Episode' AS tl, 4 AS prio LIMIT $limit
UNION
UNWIND $frontier AS fid
MATCH (:Fact {id: fid})-[:DERIVED_FROM]->(:Episode)<-[:HAS_EPISODE]-(se:Session)<-[:HAD]-(a:Agent)
RETURN DISTINCT a.id AS s, 'Agent' AS sl, 'HAD' AS rel, se.id AS t, 'Session' AS tl, 4 AS prio LIMIT $limit
