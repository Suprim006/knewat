// name: engram/remember_episode
// purpose: Append an Episode to a session's chain: HAS_EPISODE from the session and NEXT from the previous last episode, in one statement.
// params: session_id:str, episode_id:str, role:str, text:str, step:int, now:int, emb:list[float]
// returns: episode_id, prev_id (null for the first episode of the session); no row when the session does not exist
// mode: rw
// Lineage tail: replace the final RETURN by `WITH e, last MERGE (st:Step {id: $step_id}) CREATE (st)-[:WROTE]->(e) RETURN ...`.
// step is -1 when the caller has no step (FalkorDB cannot store null).
MATCH (s:Session {id: $session_id})
OPTIONAL MATCH (s)-[:HAS_EPISODE]->(last:Episode) WHERE NOT (last)-[:NEXT]->(:Episode)
CREATE (e:Episode {id: $episode_id, role: $role, text: $text, at: $now, step: $step, embedding: vecf32($emb), created_at: $now})
CREATE (s)-[:HAS_EPISODE]->(e)
FOREACH (p IN CASE WHEN last IS NULL THEN [] ELSE [last] END | CREATE (p)-[:NEXT]->(e))
RETURN e.id AS episode_id, last.id AS prev_id
