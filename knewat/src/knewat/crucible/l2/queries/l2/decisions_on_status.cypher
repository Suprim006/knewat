// name: l2/decisions_on_status
// purpose: decisions BASED_ON a fact in a given status (superseded / forgotten).
// params: status:str
// returns: text
// mode: ro
MATCH (d:Decision)-[:BASED_ON]->(f:Fact)
WHERE f.status = $status
RETURN DISTINCT d.text AS text
ORDER BY text ASC
