// name: l2/decisions
// purpose: every Decision with the task it is FOR, who DECIDED it and the facts it is BASED_ON (one row per decision-fact pair), with each fact's status, asserting agents, source uris.
// params: none
// returns: text, agent, task_id, predicate, value, status, asserted_by [agent ids], sources [uris]; one row per BASED_ON fact (null fact columns for a decision with none)
// mode: ro
MATCH (d:Decision)
OPTIONAL MATCH (a:Agent)-[:DECIDED]->(d)
OPTIONAL MATCH (d)-[:FOR]->(t:Task)
OPTIONAL MATCH (d)-[:BASED_ON]->(f:Fact)
RETURN d.text AS text, a.id AS agent, t.id AS task_id, f.predicate AS predicate, f.value AS value, f.status AS status,
       [(f)-[:ASSERTED_BY]->(x:Agent) | x.id] AS asserted_by,
       [(f)-[:DERIVED_FROM]->(s:Source) | s.uri] AS sources
ORDER BY d.at ASC, d.id ASC, f.predicate ASC, f.value ASC
