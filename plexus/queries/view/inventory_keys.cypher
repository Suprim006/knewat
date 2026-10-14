// name: view/inventory_keys
// purpose: Property keys seen per label, sampled over at most $sample nodes OF EACH LABEL (so a label created late in a long-lived graph still shows its keys).
// params: sample:int
// returns: label, keys (distinct property names, unordered); labels with no nodes are omitted
// mode: ro
MATCH (n:Agent) WITH n LIMIT $sample UNWIND keys(n) AS k RETURN 'Agent' AS label, collect(DISTINCT k) AS keys
UNION ALL
MATCH (n:Artifact) WITH n LIMIT $sample UNWIND keys(n) AS k RETURN 'Artifact' AS label, collect(DISTINCT k) AS keys
UNION ALL
MATCH (n:Decision) WITH n LIMIT $sample UNWIND keys(n) AS k RETURN 'Decision' AS label, collect(DISTINCT k) AS keys
UNION ALL
MATCH (n:Entity) WITH n LIMIT $sample UNWIND keys(n) AS k RETURN 'Entity' AS label, collect(DISTINCT k) AS keys
UNION ALL
MATCH (n:Episode) WITH n LIMIT $sample UNWIND keys(n) AS k RETURN 'Episode' AS label, collect(DISTINCT k) AS keys
UNION ALL
MATCH (n:Fact) WITH n LIMIT $sample UNWIND keys(n) AS k RETURN 'Fact' AS label, collect(DISTINCT k) AS keys
UNION ALL
MATCH (n:Handoff) WITH n LIMIT $sample UNWIND keys(n) AS k RETURN 'Handoff' AS label, collect(DISTINCT k) AS keys
UNION ALL
MATCH (n:Procedure) WITH n LIMIT $sample UNWIND keys(n) AS k RETURN 'Procedure' AS label, collect(DISTINCT k) AS keys
UNION ALL
MATCH (n:Recall) WITH n LIMIT $sample UNWIND keys(n) AS k RETURN 'Recall' AS label, collect(DISTINCT k) AS keys
UNION ALL
MATCH (n:Run) WITH n LIMIT $sample UNWIND keys(n) AS k RETURN 'Run' AS label, collect(DISTINCT k) AS keys
UNION ALL
MATCH (n:Scope) WITH n LIMIT $sample UNWIND keys(n) AS k RETURN 'Scope' AS label, collect(DISTINCT k) AS keys
UNION ALL
MATCH (n:Session) WITH n LIMIT $sample UNWIND keys(n) AS k RETURN 'Session' AS label, collect(DISTINCT k) AS keys
UNION ALL
MATCH (n:Source) WITH n LIMIT $sample UNWIND keys(n) AS k RETURN 'Source' AS label, collect(DISTINCT k) AS keys
UNION ALL
MATCH (n:Step) WITH n LIMIT $sample UNWIND keys(n) AS k RETURN 'Step' AS label, collect(DISTINCT k) AS keys
UNION ALL
MATCH (n:Task) WITH n LIMIT $sample UNWIND keys(n) AS k RETURN 'Task' AS label, collect(DISTINCT k) AS keys
UNION ALL
MATCH (n:ToolCall) WITH n LIMIT $sample UNWIND keys(n) AS k RETURN 'ToolCall' AS label, collect(DISTINCT k) AS keys
