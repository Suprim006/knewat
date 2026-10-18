// F-multi statement 5/6: Artifact PRODUCED_BY the agent, FOR the task
MATCH (a:Agent {id: $agent}), (t:Task {id: $task})
CREATE (x:Artifact {id: $art, co: $co, summary: $summary, created_at: $now})
CREATE (x)-[:PRODUCED_BY]->(a), (x)-[:FOR]->(t)
RETURN x.id
