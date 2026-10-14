// name: schema/indexes
// purpose: Range (exact-match / range) indexes from graph model v1: id on every label, plus the hot filter properties.
// params: none
// returns: nothing (one CREATE INDEX per statement; re-running errors with "already indexed", which apply_schema tolerates)
// mode: rw
// split: ;
// Why: id lookups are the entry point of every query and the UNIQUE constraints need these; Fact(subject_id,
// predicate, valid_to, status) serve current-fact and as-of lookups; Task(status) serves ready-task scans;
// Step(n) and ToolCall(at) serve time-travel and the flow feed.
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
CREATE INDEX FOR (n:ToolCall) ON (n.at)
