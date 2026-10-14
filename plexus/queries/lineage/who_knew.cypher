// name: lineage/who_knew
// purpose: Which agents READ a fact (via Steps), at which step number and time, through which recalls; plus who asserted it and which Steps wrote it.
// params: fact_id:str, limit:int
// returns: one row per reading Step, oldest first: fact_id, asserted_by [agent ids], written_by [{step_id,n,at,agent_id}], step_id, agent_id, step_n, step_at, recall_ids. A fact nobody read gives one row with step_id null; an unknown fact gives no rows.
// mode: ro
MATCH (f:Fact {id: $fact_id})
OPTIONAL MATCH (s:Step)-[:READ]->(f)
WITH f, s ORDER BY s.at ASC, s.n ASC LIMIT $limit
RETURN f.id AS fact_id,
       [(f)-[:ASSERTED_BY]->(a:Agent) | a.id] AS asserted_by,
       [(w:Step)-[:WROTE]->(f) | {step_id: w.id, n: w.n, at: w.at, agent_id: w.agent_id}] AS written_by,
       s.id AS step_id, s.agent_id AS agent_id, s.n AS step_n, s.at AS step_at,
       [(s)<-[:IN_STEP]-(r:Recall)-[:RETURNED]->(f) | r.id] AS recall_ids
