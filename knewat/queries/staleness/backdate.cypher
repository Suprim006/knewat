// name: staleness/backdate
// purpose: ONE atomic statement after verify_fact asserted the new value: put the old fact's end and the new fact's start at the time the code changed (event time), mark the old fact verified, record VERIFIED_BY {outcome:'changed'}, and flag the Decisions BASED_ON the old fact.
// params: old_id:str, new_id:str, backdate:bool, change_at:int, agent_id:str, commit:str, evidence:str, now:int, reason:str, max_flag:int
// returns: valid_to (the old fact's end now), change_at (the SUSPECTED Change time given, null when none), decision_ids (flagged, at most max_flag). Zero rows = old or new fact missing. Clears Fact.verify_degraded on the old fact.
// mode: rw
// Backdating only when $backdate (the new fact is brand new and the old one was its only predecessor): bt = $change_at, read BEFORE the supersede by staleness/backdate_point (-1 = none). Applied only if old.valid_from < bt < old.valid_to, so valid_to never moves before valid_from and the windows stay contiguous. recorded_at is untouched (the time Plexus learned the value).
// Flagging follows forget_source: flagged=true and flag_reason; an already flagged decision keeps its first reason, except the provisional 'fact changed (verification unfinished): <id>' from staleness/mark_unfinished, which is replaced. The list is cut at max_flag.
MATCH (old:Fact {id: $old_id}), (nw:Fact {id: $new_id})
WITH old, nw,
     CASE WHEN $backdate AND $change_at > old.valid_from AND $change_at < old.valid_to THEN $change_at ELSE old.valid_to END AS bt
OPTIONAL MATCH (d:Decision)-[:BASED_ON]->(old)
WITH old, nw, bt, collect(DISTINCT d)[0..$max_flag] AS ds
MERGE (ag:Agent {id: $agent_id})
  ON CREATE SET ag.name = $agent_id, ag.created_at = $now
SET old.valid_to = bt, old.verify_state = 'verified', old.verified_at = $now
REMOVE old.verify_degraded
FOREACH (_ IN CASE WHEN $backdate THEN [1] ELSE [] END | SET nw.valid_from = bt, nw.verified_at = $now)
FOREACH (e IN ds |
  SET e.flag_reason = CASE WHEN coalesce(e.flagged, false) AND NOT coalesce(e.flag_reason, '') STARTS WITH 'fact changed (verification unfinished)' THEN e.flag_reason ELSE $reason END, e.flagged = true)
CREATE (old)-[:VERIFIED_BY {at: $now, commit: $commit, outcome: 'changed', evidence: $evidence}]->(ag)
RETURN bt AS valid_to, CASE WHEN $change_at >= 0 THEN $change_at ELSE null END AS change_at, [x IN ds | x.id] AS decision_ids
