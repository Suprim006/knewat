// name: l2/fact_current
// purpose: the active fact(s) of (subject, predicate) in the global scope.
// params: norm_subject:str, predicate:str
// returns: value, valid_from
// mode: ro
MATCH (:Entity {norm_name: $norm_subject})<-[:ABOUT]-(f:Fact {predicate: $predicate})-[:IN_SCOPE]->(s:Scope {kind: 'global'})
WHERE f.status = 'active'
RETURN f.value AS value, f.valid_from AS valid_from
ORDER BY f.valid_from ASC, f.value ASC
