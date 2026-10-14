// name: l2/facts_visible
// purpose: current (active) facts visible from a scope: the scope's own facts plus those of the scopes it INHERITS.
// params: kind:str, name:str
// returns: predicate, value, scope_kind, scope_name
// mode: ro
MATCH p = (:Scope {kind: $kind, name: $name})-[:INHERITS*0..3]->(sc:Scope)
WITH collect(DISTINCT sc.id) AS visible
MATCH (f:Fact)-[:IN_SCOPE]->(s:Scope)
WHERE s.id IN visible AND f.status = 'active'
RETURN f.predicate AS predicate, f.value AS value, s.kind AS scope_kind, s.name AS scope_name
ORDER BY f.valid_from ASC, f.value ASC
