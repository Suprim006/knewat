// name: engram/create_scope
// purpose: MERGE a Scope on (kind, name) and its INHERITS edges to existing parent scopes; no row (and no write) if a parent id does not exist.
// params: kind:str, name:str, scope_id:str, inherits:list[str], now:int
// returns: id, kind, name
// mode: rw
// Empty-list form: `UNWIND CASE WHEN size($l) = 0 THEN [''] ELSE $l END AS k OPTIONAL MATCH (x:L {id: k})` instead of `OPTIONAL MATCH (x:L) WHERE x.id IN $l`: on FalkorDB 6.0.2 an empty `IN $l` scans the whole id index of L (the '' placeholder seeks and matches nothing: no id is '').
// (An empty $inherits, a root scope, is the common case.) The key-less collect keeps one row even when no parent matches.
UNWIND CASE WHEN size($inherits) = 0 THEN [''] ELSE $inherits END AS pid
MATCH (p:Scope {id: pid})
WITH collect(p) AS parents
WHERE size(parents) = size($inherits)
MERGE (s:Scope {kind: $kind, name: $name})
  ON CREATE SET s.id = $scope_id, s.created_at = $now
FOREACH (p IN parents | MERGE (s)-[:INHERITS]->(p))
RETURN s.id AS id, s.kind AS kind, s.name AS name
