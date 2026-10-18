// H3 app-side BFS, one statement per level: the parents of the frontier with their status
MATCH (p:Fact) WHERE p.id IN $frontier
MATCH (p)-[:DERIVED_FROM]->(q:Fact)
RETURN p.id AS p, q.id AS q, q.status AS status
