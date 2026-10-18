// name: lineage/as_of
// purpose: Validity-window time travel: the fact(s) for (subject, predicate) valid at time t in a scope (or one it INHERITS, nearest first), ignoring forgotten / quarantined facts.
// params: norm_subject:str, predicate:str, t:int, scope_id:str, limit:int
// returns: fact_id, value, status, valid_from, valid_to, confidence, scope_id, scope_hops (0 = the scope itself), asserted_by [agent ids], supersedes [ids], contradicts [ids]; best match first (nearest scope, then latest valid_from). No rows when the subject is unknown or nothing was valid at t.
// mode: ro
// Valid at t means valid_from <= t < valid_to; 'superseded' facts still answer for the times before their successor started. A 'dormant' fact (parked by memory_sweep) still answers: forgetting changes rank, never history (D-012).
MATCH p = (:Scope {id: $scope_id})-[:INHERITS*0..3]->(sc:Scope)
WITH sc.id AS sid, min(length(p)) AS hops
WITH collect({id: sid, hops: hops}) AS scopes
MATCH (e:Entity {norm_name: $norm_subject})<-[:ABOUT]-(f:Fact {predicate: $predicate})-[:IN_SCOPE]->(fs:Scope)
WHERE f.status IN ['active', 'superseded', 'dormant'] AND f.valid_from <= $t AND $t < f.valid_to
WITH f, fs, [x IN scopes WHERE x.id = fs.id] AS hit
WHERE size(hit) > 0
RETURN f.id AS fact_id, f.value AS value, f.status AS status, f.valid_from AS valid_from, f.valid_to AS valid_to,
       f.confidence AS confidence, fs.id AS scope_id, hit[0].hops AS scope_hops,
       [(f)-[:ASSERTED_BY]->(a:Agent) | a.id] AS asserted_by,
       [(f)-[:SUPERSEDES]->(o:Fact) | o.id] AS supersedes,
       [(f)-[:CONTRADICTS]->(c:Fact) | c.id] AS contradicts
ORDER BY scope_hops ASC, f.valid_from DESC, f.id ASC LIMIT $limit
