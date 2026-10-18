// name: lineage/knew_at
// purpose: Time machine, "what did agent X know at step N": the facts it had READ at or before step N that were still valid at that step's time, plus everything its Steps WROTE up to N.
// params: agent_id:str, n:int, limit:int
// returns: kind ('read' | 'wrote'), id, label, entity, predicate, value, status, valid_from, valid_to, summary, step_n (first step that read / the step that wrote it), at_step (the cut step), at_time (its time). No rows when the agent has no step <= N.
// mode: ro
// The cut step is the agent's latest step with n <= $n, so asking for step 10 when the agent stopped at 7 answers for step 7. Valid means valid_from <= at < valid_to.
MATCH (cut:Step {agent_id: $agent_id}) WHERE cut.n <= $n
WITH cut ORDER BY cut.n DESC LIMIT 1
MATCH (s:Step {agent_id: $agent_id})-[:READ]->(f:Fact)
WHERE s.n <= cut.n AND f.valid_from <= cut.at AND cut.at < f.valid_to
WITH cut, f, min(s.n) AS first_n
OPTIONAL MATCH (f)-[:ABOUT]->(e:Entity)
RETURN 'read' AS kind, f.id AS id, 'Fact' AS label, e.name AS entity, f.predicate AS predicate, f.value AS value,
       f.status AS status, f.valid_from AS valid_from, f.valid_to AS valid_to, f.value AS summary,
       first_n AS step_n, cut.n AS at_step, cut.at AS at_time
ORDER BY first_n ASC, id ASC LIMIT $limit
UNION
MATCH (cut:Step {agent_id: $agent_id}) WHERE cut.n <= $n
WITH cut ORDER BY cut.n DESC LIMIT 1
MATCH (s:Step {agent_id: $agent_id})-[:WROTE]->(x) WHERE s.n <= cut.n
RETURN 'wrote' AS kind, x.id AS id, labels(x)[0] AS label, null AS entity, x.predicate AS predicate, x.value AS value,
       x.status AS status, x.valid_from AS valid_from, x.valid_to AS valid_to,
       coalesce(x.value, x.text, x.title, x.note) AS summary,
       s.n AS step_n, cut.n AS at_step, cut.at AS at_time
ORDER BY step_n ASC, id ASC LIMIT $limit
