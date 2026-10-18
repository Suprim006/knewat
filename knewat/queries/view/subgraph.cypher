// name: view/subgraph
// purpose: The explorer's subgraph: the newest $limit nodes (optionally of given labels / created_at window) and the edges among them, as one row. Embeddings are never returned.
// params: labels:list[str], since:int, until:int, limit:int
// returns: nodes [{id, label, props}], edges [{source, target, type}] (one row). props holds a fixed whitelist of display keys, long text cut to 200 chars.
// mode: ro
// $labels empty = all labels. Callers pass limit+1 to detect truncation. Edges are only those whose both ends are in the node set.
// Index use (P5-int, Q5): one branch per label, each an index range seek on that label's created_at index (schema/indexes).
// An unlabeled `MATCH (n) WHERE n.created_at ...` is an All Node Scan of the whole graph whatever the filters are. A branch whose
// label is not wanted is gated by the UNWIND CASE (zero rows, so its index is never read). Each branch keeps its own newest $limit,
// and the outer step keeps the newest $limit of those, so the result equals the old single scan (ties broken by id). The 18 labels
// are the graph model's labels: tests/api/test_subgraph_plan.py fails if a label gets an `id` index but no branch here.
CALL {
  UNWIND CASE WHEN size($labels) = 0 OR 'Agent' IN $labels THEN [1] ELSE [] END AS wAgent
  MATCH (n:Agent) WHERE n.created_at >= $since AND n.created_at <= $until
  WITH n ORDER BY n.created_at DESC, n.id LIMIT $limit
  RETURN n
  UNION ALL
  UNWIND CASE WHEN size($labels) = 0 OR 'Artifact' IN $labels THEN [1] ELSE [] END AS wArtifact
  MATCH (n:Artifact) WHERE n.created_at >= $since AND n.created_at <= $until
  WITH n ORDER BY n.created_at DESC, n.id LIMIT $limit
  RETURN n
  UNION ALL
  UNWIND CASE WHEN size($labels) = 0 OR 'Change' IN $labels THEN [1] ELSE [] END AS wChange
  MATCH (n:Change) WHERE n.created_at >= $since AND n.created_at <= $until
  WITH n ORDER BY n.created_at DESC, n.id LIMIT $limit
  RETURN n
  UNION ALL
  UNWIND CASE WHEN size($labels) = 0 OR 'CodeAnchor' IN $labels THEN [1] ELSE [] END AS wCodeAnchor
  MATCH (n:CodeAnchor) WHERE n.created_at >= $since AND n.created_at <= $until
  WITH n ORDER BY n.created_at DESC, n.id LIMIT $limit
  RETURN n
  UNION ALL
  UNWIND CASE WHEN size($labels) = 0 OR 'Decision' IN $labels THEN [1] ELSE [] END AS wDecision
  MATCH (n:Decision) WHERE n.created_at >= $since AND n.created_at <= $until
  WITH n ORDER BY n.created_at DESC, n.id LIMIT $limit
  RETURN n
  UNION ALL
  UNWIND CASE WHEN size($labels) = 0 OR 'Entity' IN $labels THEN [1] ELSE [] END AS wEntity
  MATCH (n:Entity) WHERE n.created_at >= $since AND n.created_at <= $until
  WITH n ORDER BY n.created_at DESC, n.id LIMIT $limit
  RETURN n
  UNION ALL
  UNWIND CASE WHEN size($labels) = 0 OR 'Episode' IN $labels THEN [1] ELSE [] END AS wEpisode
  MATCH (n:Episode) WHERE n.created_at >= $since AND n.created_at <= $until
  WITH n ORDER BY n.created_at DESC, n.id LIMIT $limit
  RETURN n
  UNION ALL
  UNWIND CASE WHEN size($labels) = 0 OR 'Fact' IN $labels THEN [1] ELSE [] END AS wFact
  MATCH (n:Fact) WHERE n.created_at >= $since AND n.created_at <= $until
  WITH n ORDER BY n.created_at DESC, n.id LIMIT $limit
  RETURN n
  UNION ALL
  UNWIND CASE WHEN size($labels) = 0 OR 'Handoff' IN $labels THEN [1] ELSE [] END AS wHandoff
  MATCH (n:Handoff) WHERE n.created_at >= $since AND n.created_at <= $until
  WITH n ORDER BY n.created_at DESC, n.id LIMIT $limit
  RETURN n
  UNION ALL
  UNWIND CASE WHEN size($labels) = 0 OR 'Procedure' IN $labels THEN [1] ELSE [] END AS wProcedure
  MATCH (n:Procedure) WHERE n.created_at >= $since AND n.created_at <= $until
  WITH n ORDER BY n.created_at DESC, n.id LIMIT $limit
  RETURN n
  UNION ALL
  UNWIND CASE WHEN size($labels) = 0 OR 'Recall' IN $labels THEN [1] ELSE [] END AS wRecall
  MATCH (n:Recall) WHERE n.created_at >= $since AND n.created_at <= $until
  WITH n ORDER BY n.created_at DESC, n.id LIMIT $limit
  RETURN n
  UNION ALL
  UNWIND CASE WHEN size($labels) = 0 OR 'Run' IN $labels THEN [1] ELSE [] END AS wRun
  MATCH (n:Run) WHERE n.created_at >= $since AND n.created_at <= $until
  WITH n ORDER BY n.created_at DESC, n.id LIMIT $limit
  RETURN n
  UNION ALL
  UNWIND CASE WHEN size($labels) = 0 OR 'Scope' IN $labels THEN [1] ELSE [] END AS wScope
  MATCH (n:Scope) WHERE n.created_at >= $since AND n.created_at <= $until
  WITH n ORDER BY n.created_at DESC, n.id LIMIT $limit
  RETURN n
  UNION ALL
  UNWIND CASE WHEN size($labels) = 0 OR 'Session' IN $labels THEN [1] ELSE [] END AS wSession
  MATCH (n:Session) WHERE n.created_at >= $since AND n.created_at <= $until
  WITH n ORDER BY n.created_at DESC, n.id LIMIT $limit
  RETURN n
  UNION ALL
  UNWIND CASE WHEN size($labels) = 0 OR 'Source' IN $labels THEN [1] ELSE [] END AS wSource
  MATCH (n:Source) WHERE n.created_at >= $since AND n.created_at <= $until
  WITH n ORDER BY n.created_at DESC, n.id LIMIT $limit
  RETURN n
  UNION ALL
  UNWIND CASE WHEN size($labels) = 0 OR 'Step' IN $labels THEN [1] ELSE [] END AS wStep
  MATCH (n:Step) WHERE n.created_at >= $since AND n.created_at <= $until
  WITH n ORDER BY n.created_at DESC, n.id LIMIT $limit
  RETURN n
  UNION ALL
  UNWIND CASE WHEN size($labels) = 0 OR 'Task' IN $labels THEN [1] ELSE [] END AS wTask
  MATCH (n:Task) WHERE n.created_at >= $since AND n.created_at <= $until
  WITH n ORDER BY n.created_at DESC, n.id LIMIT $limit
  RETURN n
  UNION ALL
  UNWIND CASE WHEN size($labels) = 0 OR 'ToolCall' IN $labels THEN [1] ELSE [] END AS wToolCall
  MATCH (n:ToolCall) WHERE n.created_at >= $since AND n.created_at <= $until
  WITH n ORDER BY n.created_at DESC, n.id LIMIT $limit
  RETURN n
}
WITH n ORDER BY n.created_at DESC, n.id LIMIT $limit
WITH collect(n) AS ns
UNWIND ns AS a
OPTIONAL MATCH (a)-[r]->(b) WHERE b IN ns
WITH ns, collect(CASE WHEN r IS NULL THEN null ELSE {source: a.id, target: b.id, type: type(r)} END) AS es
RETURN [x IN ns | {
  id: x.id, label: labels(x)[0],
  props: {
    name: x.name, title: x.title, text: left(x.text, 200), role: x.role, kind: x.kind, uri: x.uri,
    predicate: x.predicate, value: left(x.value, 200), status: x.status, tool: x.tool,
    agent_id: x.agent_id, query_name: x.query_name, run_time_ms: x.run_time_ms, wrote: x.wrote,
    at: x.at, created_at: x.created_at, valid_from: x.valid_from, valid_to: x.valid_to,
    priority: x.priority, success: x.success, n: x.n, step: x.step, claimed_by: x.claimed_by,
    version: x.version, summary: left(x.summary, 200), note: left(x.note, 200), confidence: x.confidence,
    trust: x.trust, query: left(x.query, 200), k: x.k, harness: x.harness, task_type: x.task_type, subject_id: x.subject_id,
    verify_state: x.verify_state, suspect_since: x.suspect_since, verify_after: x.verify_after, verified_at: x.verified_at,
    surprise: x.surprise, pinned: x.pinned, path: x.path, symbol: x.symbol, hash: x.hash, commit: x.commit, repo: x.repo,
    paths: left(x.paths, 200)
  }}] AS nodes, es AS edges
