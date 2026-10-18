// H2 for agent $agent: pairs (D, f) where the agent DECIDED D, D BASED_ON g, g-[:DERIVED_FROM*0..N]->f,
// and a Step BY the agent READ f before D. N is a literal: FalkorDB takes no parameter in a hop bound.
MATCH (x:Agent {id: $agent})-[:DECIDED]->(d:Decision)-[:BASED_ON]->(g:Fact)
MATCH (g)-[:DERIVED_FROM*0..{N}]->(f:Fact)
MATCH (x)<-[:BY]-(s:Step)-[:READ]->(f)
WHERE s.at < d.at
WITH DISTINCT d.id AS d, f.id AS f ORDER BY d, f
RETURN count(*) AS n, collect([d, f])[0..5] AS first
