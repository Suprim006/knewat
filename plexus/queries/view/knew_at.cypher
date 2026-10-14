// name: view/knew_at
// purpose: What each agent knew and wrote up to step $n: facts it READ (via its Steps) that were valid at its latest step's time, and nodes it WROTE.
// params: n:int
// returns: agent_id, step_n (the agent's latest step <= n), step_at, read [{id,predicate,value,status,valid_from,valid_to}], wrote [{id,label}]
// mode: ro
// Needs Lineage's Step/READ/WROTE edges (graph model v1); a graph without Steps returns no rows.
MATCH (s:Step) WHERE s.n <= $n
WITH s ORDER BY s.n DESC LIMIT 5000
WITH s.agent_id AS agent, collect(s) AS steps, max(s.n) AS last_n
WITH agent, steps, last_n, [x IN steps WHERE x.n = last_n][0].at AS cur_at
UNWIND steps AS st
OPTIONAL MATCH (st)-[:READ]->(f:Fact) WHERE f.valid_from <= cur_at AND f.valid_to > cur_at
WITH agent, last_n, cur_at, collect(DISTINCT CASE WHEN f IS NULL THEN null ELSE {
  id: f.id, predicate: f.predicate, value: left(f.value, 200), status: f.status, valid_from: f.valid_from, valid_to: f.valid_to
} END) AS read, collect(DISTINCT st) AS sts
UNWIND sts AS st2
OPTIONAL MATCH (st2)-[:WROTE]->(w)
RETURN agent AS agent_id, last_n AS step_n, cur_at AS step_at, read,
       collect(DISTINCT CASE WHEN w IS NULL THEN null ELSE {id: w.id, label: labels(w)[0]} END) AS wrote
ORDER BY agent_id
