// name: view/inventory_nodes
// purpose: Node count per label (the View's data inventory), one O(1) label count per graph-model label; labels with no nodes are omitted.
// params: none
// returns: label, n (sorted by label)
// mode: ro
// FalkorDB answers MATCH (n:L) RETURN count(n) from the label matrix, so this costs O(labels), not O(nodes) (0.3 ms vs 28 ms at 35k nodes). The label list is the graph model's (tests/api/test_inventory_queries.py keeps it in sync); the API falls back to view/inventory_nodes_scan when the graph has a label not listed here.
MATCH (n:Agent) WITH count(n) AS n WHERE n > 0 RETURN 'Agent' AS label, n
UNION ALL
MATCH (n:Artifact) WITH count(n) AS n WHERE n > 0 RETURN 'Artifact' AS label, n
UNION ALL
MATCH (n:Decision) WITH count(n) AS n WHERE n > 0 RETURN 'Decision' AS label, n
UNION ALL
MATCH (n:Entity) WITH count(n) AS n WHERE n > 0 RETURN 'Entity' AS label, n
UNION ALL
MATCH (n:Episode) WITH count(n) AS n WHERE n > 0 RETURN 'Episode' AS label, n
UNION ALL
MATCH (n:Fact) WITH count(n) AS n WHERE n > 0 RETURN 'Fact' AS label, n
UNION ALL
MATCH (n:Handoff) WITH count(n) AS n WHERE n > 0 RETURN 'Handoff' AS label, n
UNION ALL
MATCH (n:Procedure) WITH count(n) AS n WHERE n > 0 RETURN 'Procedure' AS label, n
UNION ALL
MATCH (n:Recall) WITH count(n) AS n WHERE n > 0 RETURN 'Recall' AS label, n
UNION ALL
MATCH (n:Run) WITH count(n) AS n WHERE n > 0 RETURN 'Run' AS label, n
UNION ALL
MATCH (n:Scope) WITH count(n) AS n WHERE n > 0 RETURN 'Scope' AS label, n
UNION ALL
MATCH (n:Session) WITH count(n) AS n WHERE n > 0 RETURN 'Session' AS label, n
UNION ALL
MATCH (n:Source) WITH count(n) AS n WHERE n > 0 RETURN 'Source' AS label, n
UNION ALL
MATCH (n:Step) WITH count(n) AS n WHERE n > 0 RETURN 'Step' AS label, n
UNION ALL
MATCH (n:Task) WITH count(n) AS n WHERE n > 0 RETURN 'Task' AS label, n
UNION ALL
MATCH (n:ToolCall) WITH count(n) AS n WHERE n > 0 RETURN 'ToolCall' AS label, n
