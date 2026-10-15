// name: staleness/anchor_mismatch
// purpose: ONE atomic statement for anchor_fact when the caller's hash differs from the hash the server already holds for the anchor: the fact was checked against older code, so it becomes suspect, with one Change and a SUSPECTED edge (the reason facts_to_verify shows).
// params: fact_id:str, change_id:str, paths:str, agent_id:str, at:int, now:int
// returns: change_id. Zero rows = no such fact.
// mode: rw
// Why not staleness/mark_changed: that compares the anchor's stored hash with a NEW hash; here the stored hash is the current code and is not changing, the caller's hash is the stale one. The Change has no TOUCHED edge to the anchor (the code did not change now, so no doc may be told to update) and no commit (the reason reads 'changed in working tree (<path>)'). $paths is a JSON list of one canonical path, $change_id is deterministic (fact, anchor and both hashes), so repeating the call writes nothing new; suspect_since keeps the first time.
MATCH (f:Fact {id: $fact_id})
MERGE (ch:Change {id: $change_id})
  ON CREATE SET ch.commit = '', ch.at = $at, ch.paths = $paths, ch.agent_id = $agent_id, ch.created_at = $now
MERGE (ch)-[r:SUSPECTED]->(f)
  ON CREATE SET r.at = $at
SET f.suspect_since = CASE WHEN coalesce(f.verify_state, 'verified') = 'suspect' AND coalesce(f.suspect_since, 0) > 0
                           THEN f.suspect_since ELSE $at END,
    f.verify_state = 'suspect'
RETURN ch.id AS change_id
