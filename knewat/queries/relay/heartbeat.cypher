// name: relay/heartbeat
// purpose: Extend a lease (never shorten it), only if the caller still owns the task (claimed_by = agent AND status = 'claimed').
// params: agent:str, task:str, lease_ms:int, now:int
// returns: lease_until (zero rows when the caller is not the current claimer)
// mode: rw
// lease_until = max(current, now + lease_ms): a smaller lease_ms or an older `now` is a no-op that still returns the row.
// Only Task.lease_until is extended; the CLAIMED edge keeps the lease granted at claim time.
MATCH (t:Task {id: $task})
WHERE t.claimed_by = $agent AND t.status = 'claimed'
SET t.lease_until = CASE WHEN $now + $lease_ms > t.lease_until THEN $now + $lease_ms ELSE t.lease_until END
RETURN t.lease_until AS lease_until
