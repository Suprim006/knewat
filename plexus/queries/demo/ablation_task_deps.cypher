// name: demo/ablation_task_deps
// purpose: Every task with the ids it depends on (DEPENDS_ON), read on the intact tenant as the ground truth the dependency-aware claim probe is judged against.
// params: limit:int
// returns: id, deps (list of task ids; empty for a root task). At most $limit tasks.
// mode: ro
MATCH (t:Task)
WITH t ORDER BY t.id LIMIT $limit
OPTIONAL MATCH (t)-[:DEPENDS_ON]->(d:Task)
RETURN t.id AS id, collect(d.id) AS deps
