// name: relay/existing_tasks
// purpose: Which of the given task ids exist (used to explain a rejected create_tasks / handoff / decision).
// params: ids:list[str]
// returns: id (one row per existing task)
// mode: ro
MATCH (t:Task) WHERE t.id IN $ids
RETURN t.id AS id
