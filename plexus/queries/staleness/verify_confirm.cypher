// name: staleness/verify_confirm
// purpose: ONE atomic statement: an agent re-checked a fact and it still holds: verify_state='verified', verified_at=now, and a VERIFIED_BY {outcome:'confirmed'} edge to the agent (one edge per verification, so repeated checks are separate events).
// params: fact_id:str, agent_id:str, commit:str, evidence:str, now:int, open_to:int, unfinished_reason:str
// returns: fact_id. Zero rows = no such fact (nothing is written, not even the Agent).
// mode: rw
// Also clears Fact.verify_degraded (an interrupted verify_fact(changed) that never reached the supersede, P12-F3) and lifts the provisional decision flags staleness/mark_unfinished wrote (flag_reason = $unfinished_reason); decisions flagged for any other reason stay flagged.
// A review date (verify_after) that has already passed is consumed: it is reset to open_to, otherwise the fact would stay suspect by the date rule. A future review date is kept. SUSPECTED edges are never touched (they are the history).
MATCH (f:Fact {id: $fact_id})
OPTIONAL MATCH (d:Decision {flag_reason: $unfinished_reason})-[:BASED_ON]->(f)
WITH f, collect(DISTINCT d) AS ds
MERGE (ag:Agent {id: $agent_id})
  ON CREATE SET ag.name = $agent_id, ag.created_at = $now
SET f.verify_state = 'verified', f.verified_at = $now
REMOVE f.verify_degraded
FOREACH (e IN ds | SET e.flagged = false REMOVE e.flag_reason)
FOREACH (_ IN CASE WHEN f.verify_after IS NOT NULL AND f.verify_after <= $now THEN [1] ELSE [] END |
  SET f.verify_after = $open_to)
CREATE (f)-[:VERIFIED_BY {at: $now, commit: $commit, outcome: 'confirmed', evidence: $evidence}]->(ag)
RETURN f.id AS fact_id
