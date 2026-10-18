// name: schema/indexes
// purpose: Range indexes, each on a single property (no composite indexes): id on every label, created_at on every label (serves view/subgraph: a range seek per label instead of an All Node Scan), plus the hot filter properties.
// params: none
// returns: nothing (one CREATE INDEX per statement; re-running errors with "already indexed", which apply_schema tolerates)
// mode: rw
// split: ;
// Why: id lookups open every query and the UNIQUE constraints need them; Fact(subject_id, predicate, valid_to, status) serve current-fact and as-of lookups; Task(status) ready-task scans; Step(n, agent_id) and ToolCall(at) time travel and the flow feed; Source(uri), Scope(name), Procedure(task_type) the MERGE keys of create_source / create_scope / log_procedure_run.
// Staleness: CodeAnchor(id, path), Change(id, at), Fact(verify_state, verify_after, verify_degraded, pinned) serve the anchor MERGE, the change feed and the suspect scan (staleness/suspect_ids, view/inventory_memory).
CREATE INDEX FOR (n:Agent) ON (n.id);
CREATE INDEX FOR (n:Scope) ON (n.id);
CREATE INDEX FOR (n:Session) ON (n.id);
CREATE INDEX FOR (n:Episode) ON (n.id);
CREATE INDEX FOR (n:Entity) ON (n.id);
CREATE INDEX FOR (n:Fact) ON (n.id);
CREATE INDEX FOR (n:Source) ON (n.id);
CREATE INDEX FOR (n:Procedure) ON (n.id);
CREATE INDEX FOR (n:Run) ON (n.id);
CREATE INDEX FOR (n:Task) ON (n.id);
CREATE INDEX FOR (n:Handoff) ON (n.id);
CREATE INDEX FOR (n:Artifact) ON (n.id);
CREATE INDEX FOR (n:Decision) ON (n.id);
CREATE INDEX FOR (n:Step) ON (n.id);
CREATE INDEX FOR (n:ToolCall) ON (n.id);
CREATE INDEX FOR (n:Recall) ON (n.id);
CREATE INDEX FOR (n:Entity) ON (n.norm_name);
CREATE INDEX FOR (n:Fact) ON (n.subject_id);
CREATE INDEX FOR (n:Fact) ON (n.predicate);
CREATE INDEX FOR (n:Fact) ON (n.valid_to);
CREATE INDEX FOR (n:Fact) ON (n.status);
CREATE INDEX FOR (n:Task) ON (n.status);
CREATE INDEX FOR (n:Step) ON (n.n);
CREATE INDEX FOR (n:ToolCall) ON (n.at);
CREATE INDEX FOR (n:Step) ON (n.agent_id);
CREATE INDEX FOR (n:Source) ON (n.uri);
CREATE INDEX FOR (n:Scope) ON (n.name);
CREATE INDEX FOR (n:Procedure) ON (n.task_type);
CREATE INDEX FOR (n:Agent) ON (n.created_at);
CREATE INDEX FOR (n:Artifact) ON (n.created_at);
CREATE INDEX FOR (n:Decision) ON (n.created_at);
CREATE INDEX FOR (n:Entity) ON (n.created_at);
CREATE INDEX FOR (n:Episode) ON (n.created_at);
CREATE INDEX FOR (n:Fact) ON (n.created_at);
CREATE INDEX FOR (n:Handoff) ON (n.created_at);
CREATE INDEX FOR (n:Procedure) ON (n.created_at);
CREATE INDEX FOR (n:Recall) ON (n.created_at);
CREATE INDEX FOR (n:Run) ON (n.created_at);
CREATE INDEX FOR (n:Scope) ON (n.created_at);
CREATE INDEX FOR (n:Session) ON (n.created_at);
CREATE INDEX FOR (n:Source) ON (n.created_at);
CREATE INDEX FOR (n:Step) ON (n.created_at);
CREATE INDEX FOR (n:Task) ON (n.created_at);
CREATE INDEX FOR (n:ToolCall) ON (n.created_at);
CREATE INDEX FOR (n:CodeAnchor) ON (n.id);
CREATE INDEX FOR (n:CodeAnchor) ON (n.path);
CREATE INDEX FOR (n:Change) ON (n.id);
CREATE INDEX FOR (n:Change) ON (n.at);
CREATE INDEX FOR (n:Fact) ON (n.verify_state);
CREATE INDEX FOR (n:Fact) ON (n.verify_after);
CREATE INDEX FOR (n:Change) ON (n.created_at);
CREATE INDEX FOR (n:CodeAnchor) ON (n.created_at);
CREATE INDEX FOR (n:Fact) ON (n.verify_degraded);
CREATE INDEX FOR (n:Fact) ON (n.pinned)
