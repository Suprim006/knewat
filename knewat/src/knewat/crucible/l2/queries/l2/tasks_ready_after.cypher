// name: l2/tasks_ready_after
// purpose: tasks not in `done` that have dependencies, all of which are in `done`.
// params: done:list[str]
// returns: id
// mode: ro
MATCH (t:Task)
WHERE NOT t.id IN $done
OPTIONAL MATCH (t)-[:DEPENDS_ON]->(d:Task)
WITH t, collect(d.id) AS deps
WHERE size(deps) > 0 AND all(x IN deps WHERE x IN $done)
RETURN t.id AS id
ORDER BY id ASC
