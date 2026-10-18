// name: l2/task_dependencies
// purpose: direct DEPENDS_ON targets of a task.
// params: task_id:str
// returns: id
// mode: ro
MATCH (:Task {id: $task_id})-[:DEPENDS_ON]->(d:Task)
RETURN d.id AS id
ORDER BY id ASC
