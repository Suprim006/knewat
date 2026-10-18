// F-1stmt, guard last: every CREATE comes first, then a runtime error (1/0) fires when the version does not match
MATCH (t:Task {id: $task}), (s:Source {id: $src}), (a:Agent {id: $agent}), (to:Agent {id: $to})
CREATE (st:Step {id: $step, co: $co, agent_id: $agent, at: $now})
CREATE (f:Fact {id: $fact, co: $co, value: $value, status: 'active', created_at: $now})
CREATE (f)-[:DERIVED_FROM]->(s), (f)-[:ASSERTED_BY]->(a), (st)-[:WROTE]->(f)
CREATE (d:Decision {id: $dec, co: $co, text: $text, created_at: $now})
CREATE (d)-[:BASED_ON]->(f), (a)-[:DECIDED]->(d), (d)-[:FOR]->(t)
CREATE (x:Artifact {id: $art, co: $co, summary: $summary, created_at: $now})
CREATE (x)-[:PRODUCED_BY]->(a), (x)-[:FOR]->(t)
CREATE (h:Handoff {id: $ho, co: $co, note: $note, created_at: $now})
CREATE (h)-[:FROM]->(a), (h)-[:TO]->(to), (h)-[:FOR]->(t), (h)-[:CARRIES]->(f)
WITH t, CASE WHEN t.status = 'claimed' AND t.claimed_by = $agent AND t.version = $v THEN 1 ELSE 1 / 0 END AS ok
SET t.status = 'done', t.done_at = $now, t.version = t.version + 1, t.co = $co
RETURN t.version
