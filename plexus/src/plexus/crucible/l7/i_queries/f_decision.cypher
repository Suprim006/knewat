// F-multi statement 3/6: Decision BASED_ON the fact, DECIDED by the agent, FOR the task
MATCH (f:Fact {id: $fact}), (a:Agent {id: $agent}), (t:Task {id: $task})
CREATE (d:Decision {id: $dec, co: $co, text: $text, created_at: $now})
CREATE (d)-[:BASED_ON]->(f), (a)-[:DECIDED]->(d), (d)-[:FOR]->(t)
RETURN d.id
