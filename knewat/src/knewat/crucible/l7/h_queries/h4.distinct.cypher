// H4 per source: distinct agents with a decision that depends on it at any depth (DISTINCT between hops)
MATCH (x:Agent)-[:DECIDED]->(:Decision)-[:BASED_ON]->(g:Fact)
WITH DISTINCT x, g
MATCH (g)-[:DERIVED_FROM*0..]->(f:Fact)
WITH DISTINCT x, f
MATCH (f)-[:DERIVED_FROM]->(s:Source)
WITH s.id AS s, count(DISTINCT x) AS n ORDER BY n DESC, s ASC LIMIT 10
RETURN s, n
