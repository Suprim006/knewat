// name: lineage/discard_step
// purpose: ONE atomic statement: delete a Step opened for a call that then failed and linked nothing (the runtime opens the Step BEFORE assert_fact / record_decision / handoff so their write can create the WROTE edge itself).
// params: step_id:str
// returns: discarded (true when the Step was deleted; false when it is not an empty Step and was kept)
// mode: rw
// Only a Step with no READ, no WROTE, no outgoing NEXT and no ToolCall (IN_STEP) is touched. DETACH DELETE also drops its BY edge and the NEXT edge from the previous Step.
OPTIONAL MATCH (s:Step {id: $step_id})
WITH s
WHERE s IS NOT NULL AND NOT (s)-[:READ]->() AND NOT (s)-[:WROTE]->() AND NOT (s)-[:NEXT]->() AND NOT ()-[:IN_STEP]->(s)
DETACH DELETE s
RETURN count(s) AS discarded
