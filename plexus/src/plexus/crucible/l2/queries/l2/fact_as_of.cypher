// name: l2/fact_as_of
// purpose: validity-window time travel in the global scope: facts of (subject, predicate) with valid_from <= t < valid_to, ignoring forgotten facts.
// params: norm_subject:str, predicate:str, t:int
// returns: predicate, value, status, valid_from, valid_to, asserted_by [agent ids]
// mode: ro
MATCH (:Entity {norm_name: $norm_subject})<-[:ABOUT]-(f:Fact {predicate: $predicate})-[:IN_SCOPE]->(s:Scope {kind: 'global'})
WHERE f.status IN ['active', 'superseded'] AND f.valid_from <= $t AND $t < f.valid_to
RETURN f.predicate AS predicate, f.value AS value, f.status AS status, f.valid_from AS valid_from, f.valid_to AS valid_to,
       [(f)-[:ASSERTED_BY]->(a:Agent) | a.id] AS asserted_by
ORDER BY f.valid_from ASC, f.value ASC
