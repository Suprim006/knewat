// H1a shortcut triangle: a->b->c and a->c (DERIVED_FROM), three distinct asserting agents
MATCH (a:Fact)-[:DERIVED_FROM]->(b:Fact)-[:DERIVED_FROM]->(c:Fact), (a)-[:DERIVED_FROM]->(c)
MATCH (a)-[:ASSERTED_BY]->(x:Agent), (b)-[:ASSERTED_BY]->(y:Agent), (c)-[:ASSERTED_BY]->(z:Agent)
WHERE x <> y AND y <> z AND x <> z
WITH a.id AS a, b.id AS b, c.id AS c ORDER BY a, b, c
RETURN count(*) AS n, collect([a, b, c])[0..5] AS first
