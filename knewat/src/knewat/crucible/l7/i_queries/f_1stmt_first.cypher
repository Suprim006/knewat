// F-1stmt, guard first: the version guard precedes every CREATE; a miss returns no rows and writes nothing
MATCH (t:Task {id: $task})
WHERE t.status = 'claimed' AND t.claimed_by = $agent AND t.version = $v
MATCH (s:Source {id: $src}), (a:Agent {id: $agent}), (to:Agent {id: $to})
SET t.status = 'done', t.done_at = $now, t.version = t.version + 1, t.co = $co
CREATE (st:Step {id: $step, co: $co, agent_id: $agent, at: $now})
CREATE (f:Fact {id: $fact, co: $co, value: $value, status: 'active', created_at: $now})
CREATE (f)-[:DERIVED_FROM]->(s), (f)-[:ASSERTED_BY]->(a), (st)-[:WROTE]->(f)
CREATE (d:Decision {id: $dec, co: $co, text: $text, created_at: $now})
CREATE (d)-[:BASED_ON]->(f), (a)-[:DECIDED]->(d), (d)-[:FOR]->(t)
CREATE (x:Artifact {id: $art, co: $co, summary: $summary, created_at: $now})
CREATE (x)-[:PRODUCED_BY]->(a), (x)-[:FOR]->(t)
CREATE (h:Handoff {id: $ho, co: $co, note: $note, created_at: $now})
CREATE (h)-[:FROM]->(a), (h)-[:TO]->(to), (h)-[:FOR]->(t), (h)-[:CARRIES]->(f)
RETURN t.version
