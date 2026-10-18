// name: engram/log_procedure_run
// purpose: MERGE the Procedure (name, task_type), create a Run with USED_IN from the procedure, BY the agent, and FOR the Task when it exists, in one statement.
// params: procedure_name:str, task_type:str, procedure_id:str, steps_json:str, run_id:str, agent_id:str, task_id:str, success:bool, notes:str, now:int
// returns: run_id, procedure_id
// mode: rw

// task_id is '' when absent; the FOR edge is only made if a Task with that id exists (Relay owns Task nodes). steps_json is only stored when the procedure is created.
MERGE (ag:Agent {id: $agent_id})
  ON CREATE SET ag.name = $agent_id, ag.created_at = $now
MERGE (p:Procedure {name: $procedure_name, task_type: $task_type})
  ON CREATE SET p.id = $procedure_id, p.steps_json = $steps_json, p.created_at = $now
WITH ag, p
OPTIONAL MATCH (t:Task {id: $task_id})
CREATE (r:Run {id: $run_id, at: $now, success: $success, notes: $notes, created_at: $now})
CREATE (p)-[:USED_IN]->(r)
CREATE (r)-[:BY]->(ag)
FOREACH (x IN CASE WHEN t IS NULL THEN [] ELSE [t] END | CREATE (r)-[:FOR]->(x))
RETURN r.id AS run_id, p.id AS procedure_id
