// name: engram/upsert_entity
// purpose: MERGE an Entity on its normalised name (the MERGE key); two concurrent creates of the same name yield one node.
// params: norm_name:str, entity_id:str, name:str, kind:str, emb:list[float], now:int
// returns: id, name, kind, created (true when this call created the node)
// mode: rw
MERGE (e:Entity {norm_name: $norm_name})
  ON CREATE SET e.id = $entity_id, e.name = $name, e.kind = $kind, e.embedding = vecf32($emb), e.created_at = $now
RETURN e.id AS id, e.name AS name, e.kind AS kind, e.id = $entity_id AS created
