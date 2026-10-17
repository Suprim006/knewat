// name: relay/record_decision
// purpose: Record a Decision (agent DECIDED it, FOR a task) BASED_ON facts; all-or-nothing.
// params: id:str, agent:str, task:str, text:str, fact_ids:list[str], step_id:str ('' = none), now:int
// returns: id (zero rows = agent, task or any fact id does not exist; no Decision node is created)
// mode: rw
// All facts are matched first and their count compared with size($fact_ids) in the same statement.
// step_id (P9-int): the Step opened before this call; the Decision is linked (Step)-[:WROTE]->(Decision) in the same statement (crash-consistency).
// Callers pass a de-duplicated fact id list. An empty list is allowed (a decision with no evidence).
// An unknown NON-EMPTY step_id is best-effort: the Decision is still created, without the WROTE edge.
// Empty-list form: `UNWIND CASE WHEN size($l) = 0 THEN [''] ELSE $l END AS k OPTIONAL MATCH (x:L {id: k})` instead of `OPTIONAL MATCH (x:L) WHERE x.id IN $l`: on FalkorDB 6.0.2 an empty `IN $l` scans the whole id index of L (the '' placeholder seeks and matches nothing: no id is '').
MATCH (a:Agent {id: $agent}), (t:Task {id: $task})
OPTIONAL MATCH (stp:Step {id: $step_id})
UNWIND CASE WHEN size($fact_ids) = 0 THEN [''] ELSE $fact_ids END AS fid
OPTIONAL MATCH (f:Fact {id: fid})
WITH a, t, stp, collect(f) AS facts
WHERE size(facts) = size($fact_ids)
CREATE (d:Decision {id: $id, text: $text, at: $now, created_at: $now})
CREATE (a)-[:DECIDED]->(d), (d)-[:FOR]->(t)
FOREACH (f IN facts | CREATE (d)-[:BASED_ON]->(f))
FOREACH (sw IN CASE WHEN stp IS NULL THEN [] ELSE [stp] END | CREATE (sw)-[:WROTE]->(d))
RETURN d.id AS id
