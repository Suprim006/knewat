// name: relay/blocked_by_failure
// purpose: Every not-done task that transitively depends (up to 10 hops) on the given task.
// params: task:str
// returns: id, depth (shortest dependency distance from the given task), one row per blocked task
// mode: ro
MATCH p = (t:Task {id: $task})<-[:DEPENDS_ON*1..10]-(x:Task)
WHERE x.status <> 'done'
RETURN x.id AS id, min(length(p)) AS depth
ORDER BY depth, id
