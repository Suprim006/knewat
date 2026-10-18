// name: engram/find_entity_fulltext
// purpose: Full-text candidates for an entity name (all query tokens must appear in Entity.name).
// params: q:str, limit:int
// returns: id, name, kind, norm_name, score (higher = better), best first
// mode: ro
CALL db.idx.fulltext.queryNodes('Entity', $q) YIELD node, score
RETURN node.id AS id, node.name AS name, node.kind AS kind, node.norm_name AS norm_name, score
ORDER BY score DESC
LIMIT $limit
