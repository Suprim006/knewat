// name: relay/missing_refs
// purpose: Which of the given agent/task/fact/artifact ids exist (explains a rejected handoff or decision).
// params: agent_ids:list[str], task_ids:list[str], fact_ids:list[str], artifact_ids:list[str]
// returns: agents, tasks, facts, artifacts (each a list of the ids that exist)
// mode: ro
OPTIONAL MATCH (a:Agent) WHERE a.id IN $agent_ids
WITH collect(a.id) AS agents
OPTIONAL MATCH (t:Task) WHERE t.id IN $task_ids
WITH agents, collect(t.id) AS tasks
OPTIONAL MATCH (f:Fact) WHERE f.id IN $fact_ids
WITH agents, tasks, collect(f.id) AS facts
OPTIONAL MATCH (x:Artifact) WHERE x.id IN $artifact_ids
RETURN agents, tasks, facts, collect(x.id) AS artifacts
