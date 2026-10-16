// F-multi statement 2/6: Fact DERIVED_FROM Source, ASSERTED_BY agent, WROTE by the step
MATCH (s:Source {id: $src}), (a:Agent {id: $agent}), (st:Step {id: $step})
CREATE (f:Fact {id: $fact, co: $co, value: $value, status: 'active', created_at: $now})
CREATE (f)-[:DERIVED_FROM]->(s), (f)-[:ASSERTED_BY]->(a), (st)-[:WROTE]->(f)
RETURN f.id
