// name: l2/handoffs
// purpose: every Handoff with sender, receiver, task, note, the artifacts and facts it CARRIES.
// params: none
// returns: from_agent, to_agent, task_id, note, artifacts [uris], facts [{predicate, value, status}]; one row per handoff
// mode: ro
MATCH (h:Handoff)
OPTIONAL MATCH (h)-[:FROM]->(a:Agent)
OPTIONAL MATCH (h)-[:TO]->(b:Agent)
OPTIONAL MATCH (h)-[:FOR]->(t:Task)
RETURN a.id AS from_agent, b.id AS to_agent, t.id AS task_id, h.note AS note,
       [(h)-[:CARRIES]->(x:Artifact) | x.uri] AS artifacts,
       [(h)-[:CARRIES]->(f:Fact) | {predicate: f.predicate, value: f.value, status: f.status}] AS facts
ORDER BY h.at ASC, h.id ASC
