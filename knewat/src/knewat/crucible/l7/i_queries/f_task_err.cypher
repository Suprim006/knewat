// F-multiexec-err variant of the task statement: a version-guard miss is a RUNTIME ERROR (1/0), not an empty result
MATCH (t:Task {id: $task})
WITH t, CASE WHEN t.status = 'claimed' AND t.claimed_by = $agent AND t.version = $v THEN 1 ELSE 1 / 0 END AS ok
SET t.status = 'done', t.done_at = $now, t.version = t.version + 1, t.co = $co
RETURN t.version
