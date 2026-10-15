// name: staleness/fact_for_verify
// purpose: Everything verify_fact needs to know about one fact in one read: what it says, where (subject entity + scope), its state and validity window.
// params: fact_id:str
// returns: id, predicate, value, norm_value, status, valid_from, valid_to, verify_state, subject (entity name), subject_kind, scope_id, verify_degraded (true when an earlier verify_fact superseded it but could not finish), successors ([{id, norm_value}] of the facts that SUPERSEDE it). Zero rows = no such fact.
// mode: ro
MATCH (f:Fact {id: $fact_id})-[:ABOUT]->(e:Entity)
MATCH (f)-[:IN_SCOPE]->(sc:Scope)
RETURN f.id AS id, f.predicate AS predicate, f.value AS value, f.norm_value AS norm_value, f.status AS status,
       f.valid_from AS valid_from, f.valid_to AS valid_to, coalesce(f.verify_state, 'verified') AS verify_state,
       e.name AS subject, e.kind AS subject_kind, sc.id AS scope_id,
       coalesce(f.verify_degraded, false) AS verify_degraded,
       [(n:Fact)-[:SUPERSEDES]->(f) | {id: n.id, norm_value: n.norm_value}] AS successors
