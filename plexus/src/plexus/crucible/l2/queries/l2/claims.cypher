// name: l2/claims
// purpose: every CLAIMED edge (the claim history), with the task's final status and last claimer.
// params: none
// returns: agent, task_id, reclaimed_from, at, task_status, task_claimed_by
// mode: ro
MATCH (a:Agent)-[c:CLAIMED]->(t:Task)
RETURN a.id AS agent, t.id AS task_id, c.reclaimed_from AS reclaimed_from, c.at AS at,
       t.status AS task_status, t.claimed_by AS task_claimed_by
ORDER BY c.at ASC, t.id ASC
