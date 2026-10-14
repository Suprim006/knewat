// name: relay/dependents_of
// purpose: One BFS level: the distinct tasks that directly depend on any task in the frontier.
// params: frontier:list[str]
// returns: id, status (one row per distinct dependent; the caller de-duplicates across levels)
// mode: ro
// Replaces the old variable-length path query (*1..10), which enumerated every PATH and was exponential on
// layered DAGs. The Python wrapper (Relay.blocked_by_failure) runs this level by level over DISTINCT nodes
// (<= 10 levels, <= 5000 nodes), so the cost is linear in the edges touched.
UNWIND $frontier AS fid
MATCH (:Task {id: fid})<-[:DEPENDS_ON]-(x:Task)
RETURN DISTINCT x.id AS id, x.status AS status
