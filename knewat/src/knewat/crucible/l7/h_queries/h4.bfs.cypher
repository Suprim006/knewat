// H4 per source: distinct agents with a decision that depends on it at any depth, closure by algo.BFS
// (FalkorDB's node-deduplicating reachability procedure; max_level -1 = unbounded; it also returns Sources)
MATCH (x:Agent)-[:DECIDED]->(:Decision)-[:BASED_ON]->(g:Fact)
WITH DISTINCT x, g
CALL algo.BFS(g, -1, 'DERIVED_FROM') YIELD nodes
UNWIND nodes + [g] AS f
WITH DISTINCT x, f
MATCH (f:Fact)-[:DERIVED_FROM]->(s:Source)
WITH s.id AS s, count(DISTINCT x) AS n ORDER BY n DESC, s ASC LIMIT 10
RETURN s, n
