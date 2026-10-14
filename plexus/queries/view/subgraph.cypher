// name: view/subgraph
// purpose: The explorer's subgraph: the newest $limit nodes (optionally of given labels / created_at window) and the edges among them, as one row. Embeddings are never returned.
// params: labels:list[str], since:int, until:int, limit:int
// returns: nodes [{id, label, props}], edges [{source, target, type}] (one row). props holds a fixed whitelist of display keys, long text cut to 200 chars.
// mode: ro
// $labels empty = all labels. Callers pass limit+1 to detect truncation. Edges are only those whose both ends are in the node set.
MATCH (n)
WHERE n.created_at >= $since AND n.created_at <= $until AND (size($labels) = 0 OR labels(n)[0] IN $labels)
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
    trust: x.trust, query: left(x.query, 200), k: x.k, harness: x.harness, task_type: x.task_type, subject_id: x.subject_id
  }}] AS nodes, es AS edges
