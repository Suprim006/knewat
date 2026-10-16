// name: relay/record_decision
// purpose: Record a Decision (agent DECIDED it, FOR a task) BASED_ON facts; all-or-nothing.
// params: id:str, agent:str, task:str, text:str, fact_ids:list[str], now:int, with_step:bool, step_id:str, step_n:int, step_at:int
// returns: id, step_id (the Step that WROTE it; null without with_step) (zero rows = agent, task or any fact id does not exist; no Decision node is created)
// mode: rw
// All facts are matched first and their count compared with size($fact_ids) in the same statement.
// Callers pass a de-duplicated fact id list. An empty list is allowed (a decision with no evidence).
// P9-f (Crucible L6-F, crash-consistency): the Step that made this write is created (or, for an explicit step number that
// already exists, reused) in THIS statement, with its BY / NEXT edges and (Step)-[:WROTE]->(new node) / (Step)-[:READ]->(facts it used).
// Before, the runtime wrote the memory, then the Step, then the links in separate statements; 7.6% of the records written
// before a hard kill had no Step/WROTE. $with_step = false (audit mode light/off, or a direct service call) writes no Step.
// Step rules = lineage/record_step: n < 0 means previous + 1; an n at or behind the agent's latest step that does not exist takes
// previous + 1 instead (the NEXT chain is append-only), as the runtime's open_step fallback did.
MATCH (a:Agent {id: $agent}), (t:Task {id: $task})
OPTIONAL MATCH (f:Fact) WHERE f.id IN $fact_ids
WITH a, t, collect(f) AS facts
WHERE size(facts) = size($fact_ids)
OPTIONAL MATCH (sl:Step {agent_id: $agent})
WITH a, t, facts, sl ORDER BY sl.n DESC LIMIT 1
OPTIONAL MATCH (sx:Step {agent_id: $agent, n: $step_n})
WITH a, t, facts, sl, sx, CASE WHEN $step_n >= 0 AND (sl IS NULL OR sl.n < $step_n) THEN $step_n ELSE coalesce(sl.n, 0) + 1 END AS sn
CREATE (d:Decision {id: $id, text: $text, at: $now, created_at: $now})
CREATE (a)-[:DECIDED]->(d), (d)-[:FOR]->(t)
FOREACH (f IN facts | CREATE (d)-[:BASED_ON]->(f))
FOREACH (_t IN CASE WHEN $with_step AND sx IS NULL THEN [1] ELSE [] END |
  CREATE (ns:Step {id: $step_id, n: sn, at: $step_at, agent_id: a.id, created_at: $step_at})
  CREATE (ns)-[:BY]->(a)
  FOREACH (pp IN CASE WHEN sl IS NULL THEN [] ELSE [sl] END | CREATE (pp)-[:NEXT]->(ns))
  CREATE (ns)-[:WROTE]->(d)
  FOREACH (rx IN facts | MERGE (ns)-[rr:READ]->(rx) ON CREATE SET rr.via = 'use', rr.at = $step_at))
FOREACH (sxx IN CASE WHEN $with_step AND sx IS NOT NULL THEN [sx] ELSE [] END |
  MERGE (sxx)-[:WROTE]->(d)
  FOREACH (rx IN facts | MERGE (sxx)-[rr:READ]->(rx) ON CREATE SET rr.via = 'use', rr.at = sxx.at
    ON MATCH SET rr.via = 'use'))
RETURN d.id AS id, CASE WHEN NOT $with_step THEN null WHEN sx IS NOT NULL THEN sx.id ELSE $step_id END AS step_id
