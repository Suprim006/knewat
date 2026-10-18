// name: crucible/list_tasks
// purpose: Crucible verification read: every task with its state (the harness counts double claims, lost updates and orphans from this).
// params: limit:int
// returns: id, status, claimed_by, version, lease_until, done_at, deps (number of DEPENDS_ON edges) - one row per task, bounded by limit
// mode: ro
MATCH (t:Task)
RETURN t.id AS id, t.status AS status, t.claimed_by AS claimed_by, t.version AS version,
       t.lease_until AS lease_until, t.done_at AS done_at,
       size([(t)-[:DEPENDS_ON]->(d:Task) | d.id]) AS deps
ORDER BY t.seq ASC, t.id ASC
LIMIT $limit
