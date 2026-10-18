// name: engram/fact_history
// purpose: The versions (any status) of the facts about one entity+predicate in one scope, oldest first, with the ids it supersedes / contradicts. At most `limit` versions: the NEWEST ones.
// params: entity_id:str, predicate:str, scope_id:str, limit:int
// returns: fact_id, value, status, valid_from, valid_to, asserted_by [agent ids], supersedes [ids], contradicts [ids]
// mode: ro
// Plan shape (P5 review Q2): anchored at the Entity (its ABOUT edges), then the predicate filter and the scope test. Starting from the
// Scope (as `Fact {subject_id: ...}-[:IN_SCOPE]->(:Scope {id})` was planned) enumerates every fact of the scope. subject_id always
// equals the ABOUT entity's id (assert_fact is the only writer), so it is not needed in the pattern.
// The cap keeps the newest versions (ORDER BY ... DESC LIMIT) and the final ORDER BY puts them oldest first; the three pattern
// comprehensions only run for the rows that survive the LIMIT.
MATCH (:Entity {id: $entity_id})<-[:ABOUT]-(f:Fact {predicate: $predicate})-[:IN_SCOPE]->(:Scope {id: $scope_id})
WITH f ORDER BY f.valid_from DESC, f.id DESC LIMIT $limit
RETURN f.id AS fact_id, f.value AS value, f.status AS status, f.valid_from AS valid_from, f.valid_to AS valid_to,
       [(f)-[:ASSERTED_BY]->(a:Agent) | a.id] AS asserted_by,
       [(f)-[:SUPERSEDES]->(o:Fact) | o.id] AS supersedes,
       [(f)-[:CONTRADICTS]->(o:Fact) | o.id] AS contradicts
ORDER BY valid_from ASC, fact_id ASC
