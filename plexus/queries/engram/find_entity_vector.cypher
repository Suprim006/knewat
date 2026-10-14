// name: engram/find_entity_vector
// purpose: Nearest entities by name embedding (cosine distance, nearest first).
// params: emb:list[float], k:int
// returns: id, name, kind, distance
// mode: ro
CALL db.idx.vector.queryNodes('Entity', 'embedding', $k, vecf32($emb)) YIELD node, score
RETURN node.id AS id, node.name AS name, node.kind AS kind, score AS distance
ORDER BY distance ASC
