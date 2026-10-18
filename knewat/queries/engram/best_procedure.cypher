// name: engram/best_procedure
// purpose: Procedures for a task type ranked by success rate, then number of runs (aggregation over Procedure-USED_IN->Run).
// params: task_type:str, min_runs:int, limit:int
// returns: procedure_id, name, task_type, steps_json, runs, successes, success_rate, best first
// mode: ro
MATCH (p:Procedure {task_type: $task_type})-[:USED_IN]->(r:Run)
WITH p, count(r) AS runs, sum(CASE WHEN r.success THEN 1 ELSE 0 END) AS successes
WHERE runs >= $min_runs
RETURN p.id AS procedure_id, p.name AS name, p.task_type AS task_type, p.steps_json AS steps_json,
       runs, successes, toFloat(successes) / runs AS success_rate
ORDER BY success_rate DESC, runs DESC, name ASC
LIMIT $limit
