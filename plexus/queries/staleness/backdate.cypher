// name: staleness/backdate
// purpose: ONE atomic statement after verify_fact asserted the new value: put the old fact's end and the new fact's start at the time the code changed (event time), mark the old fact verified, record VERIFIED_BY {outcome:'changed'}, and flag the Decisions BASED_ON the old fact.
// params: old_id:str, new_id:str, backdate:bool, agent_id:str, commit:str, evidence:str, now:int, reason:str, max_flag:int
// returns: valid_to (the old fact's end now), change_at (the SUSPECTED Change time used, or the old valid_to when none applied), decision_ids (flagged, at most max_flag). Zero rows = old or new fact missing.
// mode: rw
// Backdating (only when $backdate, i.e. the new fact is brand new and the old one was its only predecessor): bt = the newest Change that SUSPECTED the old fact with at < now and at > the old fact's last confirmation (verified_at; P7-08: a value confirmed after the Change was true after it, so the window may not end before the confirmation). It applies only if old.valid_from < bt < old.valid_to, so valid_to never moves before valid_from and the two windows stay contiguous (new.valid_from = old.valid_to = bt). recorded_at is untouched: it stays the time Plexus learned the value (Graphiti's two timelines).
// Flagging is the forget_source convention: flagged=true and flag_reason; a decision that is already flagged keeps its first reason. The Decisions of a single fact are few; the list is cut at max_flag.
MATCH (old:Fact {id: $old_id}), (nw:Fact {id: $new_id})
OPTIONAL MATCH (ch:Change)-[:SUSPECTED]->(old)
WITH old, nw, max(CASE WHEN ch.at < $now AND ch.at > coalesce(old.verified_at, 0) THEN ch.at END) AS cat
WITH old, nw, cat,
     CASE WHEN $backdate AND cat IS NOT NULL AND cat > old.valid_from AND cat < old.valid_to THEN cat ELSE old.valid_to END AS bt
OPTIONAL MATCH (d:Decision)-[:BASED_ON]->(old)
WITH old, nw, cat, bt, collect(DISTINCT d)[0..$max_flag] AS ds
MERGE (ag:Agent {id: $agent_id})
  ON CREATE SET ag.name = $agent_id, ag.created_at = $now
SET old.valid_to = bt, old.verify_state = 'verified', old.verified_at = $now
FOREACH (_ IN CASE WHEN $backdate THEN [1] ELSE [] END | SET nw.valid_from = bt, nw.verified_at = $now)
FOREACH (e IN ds |
  SET e.flag_reason = CASE WHEN coalesce(e.flagged, false) THEN e.flag_reason ELSE $reason END, e.flagged = true)
CREATE (old)-[:VERIFIED_BY {at: $now, commit: $commit, outcome: 'changed', evidence: $evidence}]->(ag)
RETURN bt AS valid_to, cat AS change_at, [x IN ds | x.id] AS decision_ids
