// H1c independent corroboration: two active facts, same subject+predicate, different agents,
// derived directly from different sources, neither derived from the other at any depth.
// WITH barriers are required on FalkorDB 6.0.2: without them a later MATCH on bound f1/f2 is re-planned as a
// Cartesian product (millions of rows) and an inline map referencing f1 ({subject: f1.subject}) matches nothing.
MATCH (f1:Fact {status: 'active'})-[:DERIVED_FROM]->(s1:Source)
WITH f1, s1
MATCH (f2:Fact)-[:DERIVED_FROM]->(s2:Source)
WHERE f2.subject = f1.subject AND f2.predicate = f1.predicate AND f2.status = 'active' AND f1.id < f2.id AND s1 <> s2
WITH f1, f2
MATCH (f1)-[:ASSERTED_BY]->(a1:Agent)
WITH f1, f2, a1
MATCH (f2)-[:ASSERTED_BY]->(a2:Agent)
WHERE a1 <> a2
WITH f1, f2
WHERE NOT (f1)-[:DERIVED_FROM*1..]->(f2) AND NOT (f2)-[:DERIVED_FROM*1..]->(f1)
WITH f1.id AS a, f2.id AS b ORDER BY a, b
RETURN count(*) AS n, collect([a, b])[0..5] AS first
