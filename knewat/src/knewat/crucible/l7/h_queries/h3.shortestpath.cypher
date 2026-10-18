// H3 attempt with shortestPath(): legal only in WITH/RETURN and takes no predicate, so the
// constraint can only be checked on the one path it returns (wrong on traps: kept to show it)
MATCH (a:Fact {id: $a}), (b:Fact {id: $b})
WITH a, b, shortestPath((a)-[:DERIVED_FROM*1..8]->(b)) AS p
WITH p WHERE p IS NOT NULL AND all(n IN nodes(p)[1..length(p)] WHERE n.status = 'active')
RETURN [n IN nodes(p) | n.id] AS path
