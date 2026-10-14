// name: l2/tasks_downstream
// purpose: tasks that transitively DEPEND_ON a task (blocked if it fails).
// params: task_id:str
// returns: id
// mode: ro
MATCH (t:Task)-[:DEPENDS_ON*1..20]->(:Task {id: $task_id})
RETURN DISTINCT t.id AS id
ORDER BY id ASC
