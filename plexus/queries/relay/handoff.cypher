// name: relay/handoff
// purpose: Create a Handoff (FROM agent, TO agent, FOR task) that CARRIES artifacts and facts; all-or-nothing.
// params: id:str, from_agent:str, to_agent:str, task:str, note:str, artifact_ids:list[str], fact_ids:list[str], step_id:str ('' = none), now:int
// returns: id (zero rows = some agent/task/artifact/fact does not exist; nothing written)
// mode: rw
// step_id: the Step opened before this call; the Handoff is linked (Step)-[:WROTE]->(Handoff) in the same statement. An unknown NON-EMPTY step_id is best-effort: the Handoff is still created, without the WROTE edge.
// Every referenced node is matched first and the counts compared in the same statement, so a missing id creates no Handoff and no partial CARRIES edges. Callers pass de-duplicated id lists.
// Empty-list form: `UNWIND CASE WHEN size($l) = 0 THEN [''] ELSE $l END AS k OPTIONAL MATCH (x:L {id: k})` instead of `WHERE x.id IN $l`: on 6.0.2 an empty `IN $l` scans the whole id index.
MATCH (f:Agent {id: $from_agent}), (to:Agent {id: $to_agent}), (t:Task {id: $task})
OPTIONAL MATCH (stp:Step {id: $step_id})
UNWIND CASE WHEN size($artifact_ids) = 0 THEN [''] ELSE $artifact_ids END AS aid
OPTIONAL MATCH (a:Artifact {id: aid})
WITH f, to, t, stp, collect(a) AS arts
UNWIND CASE WHEN size($fact_ids) = 0 THEN [''] ELSE $fact_ids END AS fid
OPTIONAL MATCH (x:Fact {id: fid})
WITH f, to, t, stp, arts, collect(x) AS facts
WHERE size(arts) = size($artifact_ids) AND size(facts) = size($fact_ids)
CREATE (h:Handoff {id: $id, at: $now, note: $note, created_at: $now})
CREATE (h)-[:FROM]->(f), (h)-[:TO]->(to), (h)-[:FOR]->(t)
FOREACH (a IN arts | CREATE (h)-[:CARRIES]->(a))
FOREACH (x IN facts | CREATE (h)-[:CARRIES]->(x))
FOREACH (sw IN CASE WHEN stp IS NULL THEN [] ELSE [stp] END | CREATE (sw)-[:WROTE]->(h))
RETURN h.id AS id
