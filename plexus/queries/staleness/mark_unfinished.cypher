// name: staleness/mark_unfinished
// purpose: Written by verify_fact(changed) BEFORE it supersedes the old fact (P12-F3): ONE atomic statement that makes an interrupted verification detectable. Sets Fact.verify_degraded = true, makes the fact suspect (so recall shows it) and flags the Decisions BASED_ON it.
// params: fact_id:str, now:int, reason:str, max_flag:int
// returns: fact_id, decision_ids (flagged, at most max_flag). Zero rows = no such fact.
// mode: rw
// Why flag the decisions here and not only in staleness/backdate: a process killed between the supersede and the backdate must not leave a Decision BASED_ON a now-wrong fact unflagged. If the verification then turns out to be a no-op (fact confirmed, staleness/verify_confirm) the flags with this reason are lifted again. A decision that is already flagged keeps its first reason (forget_source convention). staleness/backdate clears verify_degraded and re-flags with the final reason 'fact changed: <id>'.
// verify_state becomes 'suspect' (suspect_since = now) only when it was not already, so an existing suspect_since is kept. staleness/suspect_ids also returns verify_degraded facts that are no longer active.
MATCH (f:Fact {id: $fact_id})
OPTIONAL MATCH (d:Decision)-[:BASED_ON]->(f)
WITH f, collect(DISTINCT d)[0..$max_flag] AS ds
FOREACH (_ IN CASE WHEN coalesce(f.verify_state, 'verified') <> 'suspect' THEN [1] ELSE [] END |
  SET f.verify_state = 'suspect', f.suspect_since = $now)
SET f.verify_degraded = true
FOREACH (e IN ds |
  SET e.flag_reason = CASE WHEN coalesce(e.flagged, false) THEN e.flag_reason ELSE $reason END, e.flagged = true)
RETURN f.id AS fact_id, [x IN ds | x.id] AS decision_ids
