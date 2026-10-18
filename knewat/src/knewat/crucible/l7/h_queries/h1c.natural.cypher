// H1c independent corroboration: two active facts, same subject+predicate, different agents,
// derived directly from different sources, neither derived from the other at any depth.
// The NATURAL form: FalkorDB 6.0.2 returns a wrong count for it (no error); kept as a reported variant.
MATCH (f1:Fact {status: 'active'})-[:DERIVED_FROM]->(s1:Source)
MATCH (f2:Fact {subject: f1.subject, predicate: f1.predicate, status: 'active'})-[:DERIVED_FROM]->(s2:Source)
WHERE f1.id < f2.id AND s1 <> s2
MATCH (f1)-[:ASSERTED_BY]->(a1:Agent), (f2)-[:ASSERTED_BY]->(a2:Agent)
WHERE a1 <> a2 AND NOT (f1)-[:DERIVED_FROM*1..]->(f2) AND NOT (f2)-[:DERIVED_FROM*1..]->(f1)
WITH f1.id AS a, f2.id AS b ORDER BY a, b
RETURN count(*) AS n, collect([a, b])[0..5] AS first
