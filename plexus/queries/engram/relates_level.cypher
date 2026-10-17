// name: engram/relates_level
// purpose: One hop of the entity-relation walk for recall(hops): the distinct entities one RELATES edge (either direction) away from a frontier, through relations visible from the scope.
// params: frontier:list[str], scope_id:str, limit:int
// returns: from_id, to_id, to_name, kind, dir ('out' = from -> to as stored, 'in' = to -> from). One row per distinct (from, to, kind, dir); at most `limit` per direction.
// mode: ro
// A relation is visible from the given scope and from every scope it INHERITS (<= 3 hops), like facts. Level-wise over distinct entities (P9-b), anchored at the frontier ids (`MATCH (e:Entity {id: fid}) WITH e MATCH (e)-[...]`: an index seek; with the traversal in the same MATCH the planner traversed the whole relationship matrix and filtered); the scope test is a second MATCH on the relation's own scope_id (a `WITH collect(sids) UNWIND $frontier MATCH` form returned no rows on 6.0.2); the Python caller de-duplicates across levels and caps each hop.
// Audit S1 (suspected, NOT confirmed, not fixed): `LIMIT $limit` is global per direction with no ORDER BY, so a hub entity in the frontier could fill the limit and starve the other frontier entities; which rows survive is planner order (related to the recall(hops) ranking defect in PLEXUS_REPORT §9.3). A per-source limit would need a per-entity CALL subquery; measure before changing.
UNWIND $frontier AS fid
MATCH (e:Entity {id: fid})
WITH e
MATCH (e)-[r:RELATES]->(n:Entity)
WITH e, r, n
MATCH (:Scope {id: $scope_id})-[:INHERITS*0..3]->(:Scope {id: r.scope_id})
RETURN DISTINCT e.id AS from_id, n.id AS to_id, n.name AS to_name, r.kind AS kind, 'out' AS dir LIMIT $limit
UNION
UNWIND $frontier AS fid
MATCH (e:Entity {id: fid})
WITH e
MATCH (e)<-[r:RELATES]-(n:Entity)
WITH e, r, n
MATCH (:Scope {id: $scope_id})-[:INHERITS*0..3]->(:Scope {id: r.scope_id})
RETURN DISTINCT e.id AS from_id, n.id AS to_id, n.name AS to_name, r.kind AS kind, 'in' AS dir LIMIT $limit
