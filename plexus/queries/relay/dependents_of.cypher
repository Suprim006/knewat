// name: relay/dependents_of
// purpose: One BFS level: the distinct tasks that directly depend on any task in the frontier.
// params: frontier:list[str]
// returns: id, status (one row per distinct dependent; the caller de-duplicates across levels)
// mode: ro
// Replaces the old variable-length path query (*1..10), which enumerated every PATH and was exponential on
// layered DAGs. The Python wrapper (Relay.blocked_by_failure) runs this level by level over DISTINCT nodes
// (<= 50 levels, <= 5000 nodes), so the cost is linear in the edges touched.
// P9-b plan shape: the frontier is bound by an index seek (`MATCH (t:Task {id: fid}) WITH t MATCH (t)<-[:DEPENDS_ON]-(x)`). With the traversal in the same MATCH as the id,
// the planner traversed EVERY DEPENDS_ON edge of the graph and filtered (399 records for a 1-task frontier on a 400-task chain), so each level cost the size of the graph.
UNWIND $frontier AS fid
MATCH (t:Task {id: fid})
WITH t
MATCH (t)<-[:DEPENDS_ON]-(x:Task)
RETURN DISTINCT x.id AS id, x.status AS status
