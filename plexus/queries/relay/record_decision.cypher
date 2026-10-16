// name: relay/record_decision
// purpose: Record a Decision (agent DECIDED it, FOR a task) BASED_ON facts; all-or-nothing.
// params: id:str, agent:str, task:str, text:str, fact_ids:list[str], step_id:str ('' = none), now:int
// returns: id (zero rows = agent, task or any fact id does not exist; no Decision node is created)
// mode: rw
// All facts are matched first and their count compared with size($fact_ids) in the same statement.
// step_id (P9-int): the Step opened before this call; the Decision is linked (Step)-[:WROTE]->(Decision) in the same statement (crash-consistency).
// Callers pass a de-duplicated fact id list. An empty list is allowed (a decision with no evidence).
MATCH (a:Agent {id: $agent}), (t:Task {id: $task})
OPTIONAL MATCH (stp:Step {id: $step_id})
OPTIONAL MATCH (f:Fact) WHERE f.id IN $fact_ids
WITH a, t, stp, collect(f) AS facts
WHERE size(facts) = size($fact_ids)
CREATE (d:Decision {id: $id, text: $text, at: $now, created_at: $now})
CREATE (a)-[:DECIDED]->(d), (d)-[:FOR]->(t)
FOREACH (f IN facts | CREATE (d)-[:BASED_ON]->(f))
FOREACH (sw IN CASE WHEN stp IS NULL THEN [] ELSE [stp] END | CREATE (sw)-[:WROTE]->(d))
RETURN d.id AS id
