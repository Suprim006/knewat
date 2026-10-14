// name: engram/fact_history
// purpose: Every version (any status) of the facts about one entity+predicate in one scope, oldest first, with the ids it supersedes / contradicts.
// params: entity_id:str, predicate:str, scope_id:str
// returns: fact_id, value, status, valid_from, valid_to, asserted_by [agent ids], supersedes [ids], contradicts [ids]
// mode: ro
MATCH (f:Fact {subject_id: $entity_id, predicate: $predicate})-[:IN_SCOPE]->(:Scope {id: $scope_id})
RETURN f.id AS fact_id, f.value AS value, f.status AS status, f.valid_from AS valid_from, f.valid_to AS valid_to,
       [(f)-[:ASSERTED_BY]->(a:Agent) | a.id] AS asserted_by,
       [(f)-[:SUPERSEDES]->(o:Fact) | o.id] AS supersedes,
       [(f)-[:CONTRADICTS]->(o:Fact) | o.id] AS contradicts
ORDER BY valid_from ASC, fact_id ASC
