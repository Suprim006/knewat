// name: l2/decisions_on_fact
// purpose: decisions BASED_ON a given fact (predicate + value).
// params: predicate:str, value:str
// returns: text
// mode: ro
MATCH (d:Decision)-[:BASED_ON]->(:Fact {predicate: $predicate, value: $value})
RETURN DISTINCT d.text AS text
ORDER BY text ASC
