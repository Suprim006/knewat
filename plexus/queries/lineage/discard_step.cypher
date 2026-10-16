// name: lineage/discard_step
// purpose: ONE atomic statement: delete a Step that was opened for a call which then failed and so never linked anything (P9-int: the runtime now opens the Step BEFORE assert_fact / record_decision / handoff, so their write statement can create the WROTE edge itself).
// params: step_id:str
// returns: discarded (true when the Step was deleted; false when it is not an empty Step: it has READ/WROTE edges, a later Step or an audit ToolCall, so it is kept)
// mode: rw
// Only a Step with no READ, no WROTE, no outgoing NEXT and no ToolCall (IN_STEP) is touched: a reused explicit step number or a Step the agent already worked in is never removed. DETACH DELETE also drops its BY edge and the NEXT edge from the previous Step.
OPTIONAL MATCH (s:Step {id: $step_id})
WITH s
WHERE s IS NOT NULL AND NOT (s)-[:READ]->() AND NOT (s)-[:WROTE]->() AND NOT (s)-[:NEXT]->() AND NOT ()-[:IN_STEP]->(s)
DETACH DELETE s
RETURN count(s) AS discarded
