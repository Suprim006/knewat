// name: engram/relates_level
// purpose: One hop of the entity-relation walk for recall(hops): the distinct entities one RELATES edge (either direction) away from a frontier, through relations visible from the scope.
// params: frontier:list[str], scope_id:str, all:bool, limit:int
// returns: from_id, to_id, to_name, kind, dir ('out' = from -> to as stored, 'in' = to -> from). One row per distinct (from, to, kind, dir); at most `limit` per direction.
// mode: ro
// A relation is visible from the given scope and from every scope it INHERITS (<= 3 hops), like facts. Level-wise over distinct entities (P9-b), anchored at the frontier ids (`MATCH (e:Entity {id: fid}) WITH e MATCH (e)-[...]`: an index seek; with the traversal in the same MATCH the planner traversed the whole relationship matrix and filtered); the scope test is a second (OPTIONAL, P12: $all = recall scope 'all' keeps every relation) MATCH on the relation's own scope_id (a `WITH collect(sids) UNWIND $frontier MATCH` form returned no rows on 6.0.2); the Python caller de-duplicates across levels and caps each hop.
UNWIND $frontier AS fid
MATCH (e:Entity {id: fid})
WITH e
MATCH (e)-[r:RELATES]->(n:Entity)
WITH e, r, n
OPTIONAL MATCH (s0:Scope {id: $scope_id})-[:INHERITS*0..3]->(:Scope {id: r.scope_id})
WITH e, r, n, s0 WHERE $all OR s0 IS NOT NULL
RETURN DISTINCT e.id AS from_id, n.id AS to_id, n.name AS to_name, r.kind AS kind, 'out' AS dir LIMIT $limit
UNION
UNWIND $frontier AS fid
MATCH (e:Entity {id: fid})
WITH e
MATCH (e)<-[r:RELATES]-(n:Entity)
WITH e, r, n
OPTIONAL MATCH (s0:Scope {id: $scope_id})-[:INHERITS*0..3]->(:Scope {id: r.scope_id})
WITH e, r, n, s0 WHERE $all OR s0 IS NOT NULL
RETURN DISTINCT e.id AS from_id, n.id AS to_id, n.name AS to_name, r.kind AS kind, 'in' AS dir LIMIT $limit
