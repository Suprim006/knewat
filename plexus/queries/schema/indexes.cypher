// name: schema/indexes
// purpose: Range (exact-match / range) indexes from graph model v1: id on every label, plus the hot filter properties.
// params: none
// returns: nothing (one CREATE INDEX per statement; re-running errors with "already indexed", which apply_schema tolerates)
// mode: rw
// split: ;
// Why: id lookups are the entry point of every query and the UNIQUE constraints need these; Fact(subject_id,
// predicate, valid_to, status) serve current-fact and as-of lookups; Task(status) serves ready-task scans;
// Step(n) and ToolCall(at) serve time-travel and the flow feed. Each property is its own single-property index (there are no
// composite indexes). Step(agent_id) serves record_step / knew_at; Source(uri), Scope(name) and Procedure(task_type) serve
// the MERGE keys of create_source / create_scope / log_procedure_run and the best_procedure filter (P5 review Q4).
// P7-J staleness (graph model v1.1): CodeAnchor(id, path) serve the anchor MERGE and the file-level symbol lookup, Change(id, at) the
// change feed (docs_to_update), Fact(verify_state) the suspect scan (facts_to_verify). Range indexes only; apply_schema stays idempotent.
// created_at on all 16 labels serves view/subgraph (the Explorer's label / time-window filter): one index range seek per label
// instead of an All Node Scan of the graph (P5-int Q5).
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
CREATE INDEX FOR (n:Fact) ON (n.verify_state)
