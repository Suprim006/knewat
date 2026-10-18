// name: demo/ablation_reset_tasks
// purpose: Put every task of a SCRATCH copy back to 'open' (unclaimed), so the claim and blocked_by_failure probes have something to claim on a finished run.
// params: limit:int
// returns: n (tasks reset). At most $limit.
// mode: rw
// Only `knewat demo ablation` calls this, and only on its own throw-away copies of the tenant, never on a real tenant graph.
MATCH (t:Task)
WITH t LIMIT $limit
SET t.status = 'open', t.claimed_by = '', t.lease_until = 0, t.version = 0, t.done_at = 0
RETURN count(t) AS n
