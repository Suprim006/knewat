// name: engram/entity_duplicate_names
// purpose: Normalised names held by more than one Entity (they would leave the UNIQUE(Entity.norm_name) constraint FAILED).
// params: limit:int
// returns: norm_name, n (entities with that name), most duplicated first
// mode: ro
MATCH (e:Entity)
WITH e.norm_name AS norm_name, count(e) AS n
WHERE n > 1
RETURN norm_name, n
ORDER BY n DESC, norm_name ASC
LIMIT $limit
