// name: l2/fact_versions
// purpose: every version of (subject, predicate) in the global scope, oldest first.
// params: norm_subject:str, predicate:str
// returns: value, status, valid_from, valid_to
// mode: ro
MATCH (:Entity {norm_name: $norm_subject})<-[:ABOUT]-(f:Fact {predicate: $predicate})-[:IN_SCOPE]->(s:Scope {kind: 'global'})
WHERE f.status IN ['active', 'superseded']
RETURN f.value AS value, f.status AS status, f.valid_from AS valid_from, f.valid_to AS valid_to
ORDER BY f.valid_from ASC, f.value ASC
