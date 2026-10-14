// name: relay/task_status
// purpose: One task with its direct dependencies and their statuses.
// params: id:str
// returns: id, title, status, priority, claimed_by, lease_until, version, done_at, created_at,
//   depends_on (ids), dependency_statuses (aligned with depends_on). Zero rows = unknown task.
// mode: ro
MATCH (t:Task {id: $id})
OPTIONAL MATCH (t)-[:DEPENDS_ON]->(d:Task)
WITH t, d ORDER BY d.id
RETURN t.id AS id, t.title AS title, t.status AS status, t.priority AS priority, t.claimed_by AS claimed_by,
       t.lease_until AS lease_until, t.version AS version, t.done_at AS done_at, t.created_at AS created_at,
       collect(d.id) AS depends_on, collect(d.status) AS dependency_statuses
