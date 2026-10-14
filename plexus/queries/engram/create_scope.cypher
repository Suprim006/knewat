// name: engram/create_scope
// purpose: MERGE a Scope on (kind, name) and its INHERITS edges to existing parent scopes; no row (and no write) if a parent id does not exist.
// params: kind:str, name:str, scope_id:str, inherits:list[str], now:int
// returns: id, kind, name
// mode: rw
MATCH (p:Scope) WHERE p.id IN $inherits
WITH collect(p) AS parents
WHERE size(parents) = size($inherits)
MERGE (s:Scope {kind: $kind, name: $name})
  ON CREATE SET s.id = $scope_id, s.created_at = $now
FOREACH (p IN parents | MERGE (s)-[:INHERITS]->(p))
RETURN s.id AS id, s.kind AS kind, s.name AS name
