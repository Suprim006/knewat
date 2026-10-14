// name: view/flow
// purpose: Tool calls in landing order with the nodes each created/updated, for the flow timeline and the SSE feed.
// params: after:int, limit:int
// returns: id, tool, at, agent_id, query_name, run_time_ms, wrote, step, step_id, step_n, created [{id,label}], updated [{id,label}]
// mode: ro
// at > $after, ordered by (at, id). The SSE poller re-reads a small look-back window and de-duplicates by id.
MATCH (t:ToolCall) WHERE t.at > $after
WITH t ORDER BY t.at ASC, t.id ASC LIMIT $limit
OPTIONAL MATCH (t)-[:CREATED]->(c)
WITH t, collect(CASE WHEN c IS NULL THEN null ELSE {id: c.id, label: labels(c)[0]} END) AS created
OPTIONAL MATCH (t)-[:UPDATED]->(u)
WITH t, created, collect(CASE WHEN u IS NULL THEN null ELSE {id: u.id, label: labels(u)[0]} END) AS updated
OPTIONAL MATCH (t)-[:IN_STEP]->(s:Step)
RETURN t.id AS id, t.tool AS tool, t.at AS at, t.agent_id AS agent_id, t.query_name AS query_name,
       t.run_time_ms AS run_time_ms, t.wrote AS wrote, t.step AS step, s.id AS step_id, s.n AS step_n,
       created, updated
ORDER BY at ASC, id ASC
