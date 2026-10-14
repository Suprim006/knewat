// name: l2scale/facts_visible_subject
// purpose: current (active) facts ABOUT one subject that are visible from a scope: the scope's own facts plus those of the scopes it INHERITS (sprint-scoped variant of l2/facts_visible).
// params: kind:str, name:str, norm_subject:str
// returns: predicate, value, scope_kind, scope_name
// mode: ro
MATCH (:Scope {kind: $kind, name: $name})-[:INHERITS*0..3]->(s:Scope)<-[:IN_SCOPE]-(f:Fact)-[:ABOUT]->(:Entity {norm_name: $norm_subject})
WHERE f.status = 'active'
RETURN DISTINCT f.predicate AS predicate, f.value AS value, s.kind AS scope_kind, s.name AS scope_name, f.valid_from AS valid_from
ORDER BY valid_from ASC, value ASC
