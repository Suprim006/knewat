// name: activation/novelty
// purpose: Surprise at write time: the nearest ACTIVE facts of one scope to a new fact's text embedding (D-012 novelty = 1 - max cosine).
// params: q:list[float], scope_id:str, over:int, k:int
// returns: id, distance (cosine DISTANCE to the new fact's text, lower = nearer; the vector score is a distance, FALKORDB_REFERENCE section 2); at most k rows, nearest first; no rows = nothing active in the scope within the first `over` vector hits
// mode: ro

// The vector procedure has no pre-filter: it returns the `over` nearest facts of the WHOLE graph and the status / scope tests run after it, so
// `over` is larger than k (the wrapper uses 20 for k=5). An empty result is read as "nothing similar in this scope" = the maximum novelty 0.5.
// Only facts IN_SCOPE the given scope itself count (not the scopes it inherits): novelty is relative to what this scope already holds.
CALL db.idx.vector.queryNodes('Fact', 'embedding', $over, vecf32($q)) YIELD node, score
WITH node AS f, score
WHERE f.status = 'active'
MATCH (f)-[:IN_SCOPE]->(:Scope {id: $scope_id})
RETURN f.id AS id, score AS distance
ORDER BY distance ASC
LIMIT $k
