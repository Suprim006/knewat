// H4 per source: distinct agents with a decision that depends on it at any depth (path enumeration)
MATCH (x:Agent)-[:DECIDED]->(:Decision)-[:BASED_ON]->(:Fact)-[:DERIVED_FROM*0..]->(:Fact)-[:DERIVED_FROM]->(s:Source)
WITH s.id AS s, count(DISTINCT x) AS n ORDER BY n DESC, s ASC LIMIT 10
RETURN s, n
