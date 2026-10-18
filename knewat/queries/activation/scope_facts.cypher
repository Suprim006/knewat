// name: activation/scope_facts
// purpose: The active facts of ONE scope, oldest first, for a sweep to look at (ids only; the activation lookup does the rest).
// params: scope_id:str, scan:int
// returns: id; at most `scan` rows, oldest created_at first (the oldest facts are the ones that can be faint)
// mode: ro

// The scope itself only (not the scopes it inherits): a sweep of 'project:x' never touches global facts. Callers pass scan <= 5000.
MATCH (f:Fact {status: 'active'})-[:IN_SCOPE]->(:Scope {id: $scope_id})
RETURN f.id AS id
ORDER BY f.created_at ASC, f.id ASC
LIMIT $scan
