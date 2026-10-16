// name: relay/handoff
// purpose: Create a Handoff (FROM agent, TO agent, FOR task) that CARRIES artifacts and facts; all-or-nothing.
// params: id:str, from_agent:str, to_agent:str, task:str, note:str, artifact_ids:list[str], fact_ids:list[str], step_id:str ('' = none), now:int
// returns: id (zero rows = some agent/task/artifact/fact does not exist; nothing written)
// mode: rw
// step_id (P9-int): the Step opened before this call; the Handoff is linked (Step)-[:WROTE]->(Handoff) in the same statement (crash-consistency).
// Every referenced node is matched first and the counts compared in the same statement, so a missing id
// creates no Handoff and no partial CARRIES edges. Callers pass de-duplicated id lists.
MATCH (f:Agent {id: $from_agent}), (to:Agent {id: $to_agent}), (t:Task {id: $task})
OPTIONAL MATCH (stp:Step {id: $step_id})
OPTIONAL MATCH (a:Artifact) WHERE a.id IN $artifact_ids
WITH f, to, t, stp, collect(a) AS arts
OPTIONAL MATCH (x:Fact) WHERE x.id IN $fact_ids
WITH f, to, t, stp, arts, collect(x) AS facts
WHERE size(arts) = size($artifact_ids) AND size(facts) = size($fact_ids)
CREATE (h:Handoff {id: $id, at: $now, note: $note, created_at: $now})
CREATE (h)-[:FROM]->(f), (h)-[:TO]->(to), (h)-[:FOR]->(t)
FOREACH (a IN arts | CREATE (h)-[:CARRIES]->(a))
FOREACH (x IN facts | CREATE (h)-[:CARRIES]->(x))
FOREACH (sw IN CASE WHEN stp IS NULL THEN [] ELSE [stp] END | CREATE (sw)-[:WROTE]->(h))
RETURN h.id AS id
