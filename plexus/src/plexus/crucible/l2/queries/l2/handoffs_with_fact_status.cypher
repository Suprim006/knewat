// name: l2/handoffs_with_fact_status
// purpose: tasks whose Handoff CARRIES a fact in a given status (superseded / forgotten).
// params: status:str
// returns: task_id; one row per such handoff
// mode: ro
MATCH (h:Handoff)-[:CARRIES]->(f:Fact)
WHERE f.status = $status
MATCH (h)-[:FOR]->(t:Task)
RETURN DISTINCT t.id AS task_id
ORDER BY task_id ASC
