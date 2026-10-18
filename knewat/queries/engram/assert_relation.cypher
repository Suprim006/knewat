// name: engram/assert_relation
// purpose: Idempotent typed relation between two Entities in a scope: MERGE (a)-[:RELATES {kind, scope_id}]->(b) (P9-b / P2).
// params: a_id:str, b_id:str, kind:str, scope_id:str, now:int
// returns: created (true when the edge is new), a, b (entity ids). Zero rows = an entity or the scope does not exist (nothing is written).
// mode: rw
// The edge is directed (subject -> object) and unique per (kind, scope). Recall (engram/relates_level) walks it in both directions.
MATCH (a:Entity {id: $a_id})
MATCH (b:Entity {id: $b_id})
MATCH (s:Scope {id: $scope_id})
MERGE (a)-[r:RELATES {kind: $kind, scope_id: $scope_id}]->(b)
  ON CREATE SET r.at = $now, r.new = true
  ON MATCH SET r.new = false
WITH r, r.new AS created, a, b
REMOVE r.new
RETURN created, a.id AS a, b.id AS b
