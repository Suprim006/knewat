// name: relay/ready_tasks
// purpose: List tasks an agent could claim right now (same readiness rule as claim_next_task), best first.
// params: now:int, limit:int
// returns: id, title, priority, status, claimed_by, lease_until (one row per ready task)
// mode: ro
MATCH (t:Task)
WHERE t.status IN ['open', 'claimed'] AND (t.status = 'open' OR t.lease_until < $now)
OPTIONAL MATCH (t)-[:DEPENDS_ON]->(d:Task) WHERE d.status <> 'done'
WITH t, count(d) AS open_deps
WHERE open_deps = 0
RETURN t.id AS id, t.title AS title, t.priority AS priority, t.status AS status,
       t.claimed_by AS claimed_by, t.lease_until AS lease_until
ORDER BY t.priority DESC, t.created_at ASC, t.id ASC
LIMIT $limit
