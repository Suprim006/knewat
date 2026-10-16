// name: relay/handoff
// purpose: Create a Handoff (FROM agent, TO agent, FOR task) that CARRIES artifacts and facts; all-or-nothing.
// params: id:str, from_agent:str, to_agent:str, task:str, note:str, artifact_ids:list[str], fact_ids:list[str], now:int, with_step:bool, step_id:str, step_n:int, step_at:int
// returns: id, step_id (the from-agent's Step that WROTE it; null without with_step) (zero rows = some agent/task/artifact/fact does not exist; nothing written)
// mode: rw
// Every referenced node is matched first and the counts compared in the same statement, so a missing id
// creates no Handoff and no partial CARRIES edges. Callers pass de-duplicated id lists.
// P9-f (Crucible L6-F, crash-consistency): the Step that made this write is created (or, for an explicit step number that
// already exists, reused) in THIS statement, with its BY / NEXT edges and (Step)-[:WROTE]->(new node) / (Step)-[:READ]->(facts it used).
// Before, the runtime wrote the memory, then the Step, then the links in separate statements; 7.6% of the records written
// before a hard kill had no Step/WROTE. $with_step = false (audit mode light/off, or a direct service call) writes no Step.
// Step rules = lineage/record_step: n < 0 means previous + 1; an n at or behind the agent's latest step that does not exist takes
// previous + 1 instead (the NEXT chain is append-only), as the runtime's open_step fallback did.
MATCH (f:Agent {id: $from_agent}), (to:Agent {id: $to_agent}), (t:Task {id: $task})
OPTIONAL MATCH (a:Artifact) WHERE a.id IN $artifact_ids
WITH f, to, t, collect(a) AS arts
OPTIONAL MATCH (x:Fact) WHERE x.id IN $fact_ids
WITH f, to, t, arts, collect(x) AS facts
WHERE size(arts) = size($artifact_ids) AND size(facts) = size($fact_ids)
OPTIONAL MATCH (sl:Step {agent_id: $from_agent})
WITH f, to, t, arts, facts, sl ORDER BY sl.n DESC LIMIT 1
OPTIONAL MATCH (sx:Step {agent_id: $from_agent, n: $step_n})
WITH f, to, t, arts, facts, sl, sx, CASE WHEN $step_n >= 0 AND (sl IS NULL OR sl.n < $step_n) THEN $step_n ELSE coalesce(sl.n, 0) + 1 END AS sn
CREATE (h:Handoff {id: $id, at: $now, note: $note, created_at: $now})
CREATE (h)-[:FROM]->(f), (h)-[:TO]->(to), (h)-[:FOR]->(t)
FOREACH (a IN arts | CREATE (h)-[:CARRIES]->(a))
FOREACH (x IN facts | CREATE (h)-[:CARRIES]->(x))
FOREACH (_t IN CASE WHEN $with_step AND sx IS NULL THEN [1] ELSE [] END |
  CREATE (ns:Step {id: $step_id, n: sn, at: $step_at, agent_id: f.id, created_at: $step_at})
  CREATE (ns)-[:BY]->(f)
  FOREACH (pp IN CASE WHEN sl IS NULL THEN [] ELSE [sl] END | CREATE (pp)-[:NEXT]->(ns))
  CREATE (ns)-[:WROTE]->(h)
  FOREACH (rx IN facts | MERGE (ns)-[rr:READ]->(rx) ON CREATE SET rr.via = 'use', rr.at = $step_at))
FOREACH (sxx IN CASE WHEN $with_step AND sx IS NOT NULL THEN [sx] ELSE [] END |
  MERGE (sxx)-[:WROTE]->(h)
  FOREACH (rx IN facts | MERGE (sxx)-[rr:READ]->(rx) ON CREATE SET rr.via = 'use', rr.at = sxx.at
    ON MATCH SET rr.via = 'use'))
RETURN h.id AS id, CASE WHEN NOT $with_step THEN null WHEN sx IS NOT NULL THEN sx.id ELSE $step_id END AS step_id
