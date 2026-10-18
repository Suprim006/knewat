// H3 variable-length paths filtered on the intermediate nodes, shortest first (enumerates paths)
MATCH (a:Fact {id: $a}), (b:Fact {id: $b})
MATCH p = (a)-[:DERIVED_FROM*1..8]->(b)
WHERE all(n IN nodes(p)[1..length(p)] WHERE n.status = 'active')
RETURN [n IN nodes(p) | n.id] AS path ORDER BY length(p) LIMIT 1
