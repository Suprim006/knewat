// name: lineage/node_info
// purpose: Display properties (no embeddings) of the nodes named by id, for the View and for explanations, one row per node.
// params: ids:list[str]
// returns: id, label, props (map of the key properties of that label; Fact props include the P7 verify_state, suspect_since, surprise, pinned with their defaults)
// mode: ro
// Each label branch uses that label's id index, so cost is proportional to the number of ids, not the graph size. Episode text is cut to 200 chars.
MATCH (n:Fact) WHERE n.id IN $ids
RETURN n.id AS id, 'Fact' AS label, {predicate: n.predicate, value: n.value, status: n.status, valid_from: n.valid_from,
  valid_to: n.valid_to, recorded_at: n.recorded_at, confidence: n.confidence, subject_id: n.subject_id,
  verify_state: coalesce(n.verify_state, 'verified'), suspect_since: coalesce(n.suspect_since, 0), surprise: coalesce(n.surprise, 0.0),
  pinned: coalesce(n.pinned, false)} AS props
UNION
MATCH (n:Decision) WHERE n.id IN $ids
RETURN n.id AS id, 'Decision' AS label, {text: n.text, at: n.at, flagged: coalesce(n.flagged, false)} AS props
UNION
MATCH (n:Agent) WHERE n.id IN $ids
RETURN n.id AS id, 'Agent' AS label, {name: n.name, role: n.role, harness: n.harness} AS props
UNION
MATCH (n:Source) WHERE n.id IN $ids
RETURN n.id AS id, 'Source' AS label, {uri: n.uri, kind: n.kind, trust: n.trust} AS props
UNION
MATCH (n:Episode) WHERE n.id IN $ids
RETURN n.id AS id, 'Episode' AS label, {role: n.role, text: substring(n.text, 0, 200), at: n.at} AS props
UNION
MATCH (n:Session) WHERE n.id IN $ids
RETURN n.id AS id, 'Session' AS label, {agent_id: n.agent_id, started_at: n.started_at} AS props
UNION
MATCH (n:Entity) WHERE n.id IN $ids
RETURN n.id AS id, 'Entity' AS label, {name: n.name, kind: n.kind} AS props
UNION
MATCH (n:Scope) WHERE n.id IN $ids
RETURN n.id AS id, 'Scope' AS label, {kind: n.kind, name: n.name} AS props
UNION
MATCH (n:Step) WHERE n.id IN $ids
RETURN n.id AS id, 'Step' AS label, {n: n.n, at: n.at, agent_id: n.agent_id} AS props
UNION
MATCH (n:Task) WHERE n.id IN $ids
RETURN n.id AS id, 'Task' AS label, {title: n.title, status: n.status} AS props
UNION
MATCH (n:Recall) WHERE n.id IN $ids
RETURN n.id AS id, 'Recall' AS label, {query: n.query, at: n.at, k: n.k, agent_id: n.agent_id} AS props
UNION
MATCH (n:Handoff) WHERE n.id IN $ids
RETURN n.id AS id, 'Handoff' AS label, {note: n.note, at: n.at} AS props
UNION
MATCH (n:Artifact) WHERE n.id IN $ids
RETURN n.id AS id, 'Artifact' AS label, {kind: n.kind, uri: n.uri, summary: n.summary} AS props
UNION
MATCH (n:Change) WHERE n.id IN $ids
RETURN n.id AS id, 'Change' AS label, {commit: n.commit, at: n.at, paths: n.paths, agent_id: n.agent_id} AS props
UNION
MATCH (n:CodeAnchor) WHERE n.id IN $ids
RETURN n.id AS id, 'CodeAnchor' AS label, {path: n.path, symbol: n.symbol, kind: n.kind, hash: n.hash} AS props
