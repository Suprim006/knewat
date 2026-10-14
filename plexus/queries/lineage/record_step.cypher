// name: lineage/record_step
// purpose: ONE atomic statement: create the agent's next Step (BY the agent, NEXT from its previous Step). Idempotent per (agent, n).
// params: agent_id:str, step_id:str, n:int, at:int
// returns: step_id (null if refused), n (the step number used), created (bool), previous_id (id of the preceding Step or null).
//   created=false with step_id set = a Step with that n already existed (returned unchanged); step_id null = out of order (a later n exists).
// mode: rw
// n < 0 means "auto": previous n + 1 (1 for the first step). Steps must be recorded in increasing n: the NEXT chain is append-only.
MERGE (a:Agent {id: $agent_id})
  ON CREATE SET a.name = $agent_id, a.created_at = $at
WITH a
OPTIONAL MATCH (p:Step {agent_id: $agent_id})
WITH a, p ORDER BY p.n DESC LIMIT 1
WITH a, p AS last, CASE WHEN $n < 0 THEN coalesce(p.n, 0) + 1 ELSE $n END AS want
OPTIONAL MATCH (ex:Step {agent_id: $agent_id, n: want})
WITH a, last, want, ex, (ex IS NULL AND (last IS NULL OR last.n < want)) AS can
FOREACH (_ IN CASE WHEN can THEN [1] ELSE [] END |
  CREATE (s:Step {id: $step_id, n: want, at: $at, agent_id: $agent_id, created_at: $at})
  CREATE (s)-[:BY]->(a)
  FOREACH (pp IN CASE WHEN last IS NULL THEN [] ELSE [last] END | CREATE (pp)-[:NEXT]->(s)))
RETURN CASE WHEN ex IS NOT NULL THEN ex.id WHEN can THEN $step_id ELSE null END AS step_id,
       want AS n, can AS created, last.id AS previous_id
