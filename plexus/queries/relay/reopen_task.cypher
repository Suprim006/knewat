// name: relay/reopen_task
// purpose: Compare-and-set a FAILED task back to 'open' so it can be claimed again (retry); clears the lease and done_at.
// params: agent:str, task:str, now:int
// returns: id, status, version (zero rows = unknown agent, unknown task, or the task is not 'failed'; nothing written)
// mode: rw
// version+1 so a stale holder of the old claim cannot complete the task. Dependents stay blocked until the reopened task is done.
// The previous fail_reason is kept; reopened_by / reopened_at record who retried and when.
MATCH (t:Task {id: $task}), (a:Agent {id: $agent})
WHERE t.status = 'failed'
SET t.status = 'open', t.claimed_by = '', t.lease_until = 0, t.done_at = 0, t.version = t.version + 1,
    t.reopened_by = $agent, t.reopened_at = $now
RETURN t.id AS id, t.status AS status, t.version AS version
