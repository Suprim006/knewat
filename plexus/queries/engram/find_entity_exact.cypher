// name: engram/find_entity_exact
// purpose: Exact (case/whitespace-normalised) entity lookup through the Entity.norm_name range index.
// params: norm_name:str
// returns: id, name, kind (zero or one row)
// mode: ro
MATCH (e:Entity {norm_name: $norm_name})
RETURN e.id AS id, e.name AS name, e.kind AS kind
LIMIT 1
