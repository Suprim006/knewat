// F-multi statement 6/6: Handoff FROM/TO agents, FOR the task, CARRIES the fact
MATCH (f:Agent {id: $agent}), (to:Agent {id: $to}), (t:Task {id: $task}), (x:Fact {id: $fact})
CREATE (h:Handoff {id: $ho, co: $co, note: $note, created_at: $now})
CREATE (h)-[:FROM]->(f), (h)-[:TO]->(to), (h)-[:FOR]->(t), (h)-[:CARRIES]->(x)
RETURN h.id
