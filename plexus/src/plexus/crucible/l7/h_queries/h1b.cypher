// H1b handoff 3-cycle x->y->z->x of distinct agents (x = smallest id), each handoff carrying a fact
// derived directly from one common source. Three separate MATCHes: in ONE pattern Cypher's relationship
// uniqueness would drop cycles where two handoffs carry the same fact (the same DERIVED_FROM edge twice).
MATCH (x:Agent)<-[:FROM]-(h1:Handoff)-[:TO]->(y:Agent)<-[:FROM]-(h2:Handoff)-[:TO]->(z:Agent)<-[:FROM]-(h3:Handoff)-[:TO]->(x)
WHERE x.id < y.id AND x.id < z.id AND y <> z
MATCH (h1)-[:CARRIES]->(:Fact)-[:DERIVED_FROM]->(s:Source)
MATCH (h2)-[:CARRIES]->(:Fact)-[:DERIVED_FROM]->(s)
MATCH (h3)-[:CARRIES]->(:Fact)-[:DERIVED_FROM]->(s)
WITH DISTINCT x.id AS x, y.id AS y, z.id AS z ORDER BY x, y, z
RETURN count(*) AS n, collect([x, y, z])[0..5] AS first
