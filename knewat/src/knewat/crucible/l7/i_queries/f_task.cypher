// F-multi statement 4/6: the Task update, guarded by the expected version (0 rows = guard miss)
MATCH (t:Task {id: $task})
WHERE t.status = 'claimed' AND t.claimed_by = $agent AND t.version = $v
SET t.status = 'done', t.done_at = $now, t.version = t.version + 1, t.co = $co
RETURN t.version
