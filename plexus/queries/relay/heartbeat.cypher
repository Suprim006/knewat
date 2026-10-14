// name: relay/heartbeat
// purpose: Extend a lease, only if the caller still owns the task (claimed_by = agent AND status = 'claimed').
// params: agent:str, task:str, lease_ms:int, now:int
// returns: lease_until (zero rows when the caller is not the current claimer)
// mode: rw
// Only Task.lease_until is extended; the CLAIMED edge keeps the lease granted at claim time.
MATCH (t:Task {id: $task})
WHERE t.claimed_by = $agent AND t.status = 'claimed'
SET t.lease_until = $now + $lease_ms
RETURN t.lease_until AS lease_until
