// name: demo/ablation_targets
// purpose: Pick the objects the `plexus demo ablation` probes run on, from the intact tenant: the Decision resting on the most facts (BASED_ON), the agent that READ the most facts, the Source whose forgetting reaches the most decisions, then the most facts (DERIVED_FROM*1..5 then BASED_ON, the reach of forget_source) and the root Task (no dependencies) with the most direct dependents.
// params: none
// returns: kind ('decision' | 'reader' | 'source' | 'root_task'), id, n (the count that made it the pick; for 'source' the facts derived from it). A kind is missing when the tenant has none (e.g. no decisions).
// mode: ro
// The source pick scans sources x derived facts: fine for a demo tenant (hundreds of nodes), not meant for a huge one.
// Always read on the INTACT tenant: on the stripped copy these edges are gone, which is the point of the demo.
MATCH (d:Decision)-[r:BASED_ON]->(:Fact)
WITH d, count(r) AS n ORDER BY n DESC, d.created_at DESC, d.id LIMIT 1
RETURN 'decision' AS kind, d.id AS id, n
UNION ALL
MATCH (s:Step)-[r:READ]->(:Fact)
WITH s.agent_id AS aid, count(r) AS n ORDER BY n DESC, aid LIMIT 1
RETURN 'reader' AS kind, aid AS id, n
UNION ALL
MATCH (s:Source)
OPTIONAL MATCH (f:Fact)-[:DERIVED_FROM*1..5]->(s)
OPTIONAL MATCH (d:Decision)-[:BASED_ON]->(f)
WITH s, count(DISTINCT f) AS n, count(DISTINCT d) AS decisions ORDER BY decisions DESC, n DESC, s.uri LIMIT 1
RETURN 'source' AS kind, s.id AS id, n
UNION ALL
MATCH (t:Task) WHERE NOT (t)-[:DEPENDS_ON]->(:Task)
OPTIONAL MATCH (x:Task)-[:DEPENDS_ON]->(t)
WITH t, count(x) AS n ORDER BY n DESC, t.id LIMIT 1
RETURN 'root_task' AS kind, t.id AS id, n
