-- close-out store for family I (SQLite): one table per entity, join tables for the edges
CREATE TABLE agents (id TEXT PRIMARY KEY);
CREATE TABLE sources (id TEXT PRIMARY KEY);
CREATE TABLE tasks (id TEXT PRIMARY KEY, status TEXT, claimed_by TEXT, version INTEGER NOT NULL, done_at INTEGER, co TEXT);
CREATE TABLE steps (id TEXT PRIMARY KEY, co TEXT, agent_id TEXT, at INTEGER);
CREATE TABLE facts (id TEXT PRIMARY KEY, co TEXT, value TEXT, status TEXT, created_at INTEGER);
CREATE TABLE fact_derived (fact_id TEXT, source_id TEXT);
CREATE TABLE fact_asserted (fact_id TEXT, agent_id TEXT);
CREATE TABLE step_wrote (step_id TEXT, node_id TEXT);
CREATE TABLE decisions (id TEXT PRIMARY KEY, co TEXT, text TEXT, agent_id TEXT, task_id TEXT, created_at INTEGER);
CREATE TABLE decision_based_on (decision_id TEXT, fact_id TEXT);
CREATE TABLE artifacts (id TEXT PRIMARY KEY, co TEXT, summary TEXT, agent_id TEXT, task_id TEXT, created_at INTEGER);
CREATE TABLE handoffs (id TEXT PRIMARY KEY, co TEXT, note TEXT, from_agent TEXT, to_agent TEXT, task_id TEXT, created_at INTEGER);
CREATE TABLE handoff_carries (handoff_id TEXT, fact_id TEXT);
CREATE INDEX ix_wrote_node ON step_wrote(node_id);
CREATE INDEX ix_fd ON fact_derived(fact_id);
CREATE INDEX ix_fa ON fact_asserted(fact_id);
CREATE INDEX ix_dbo ON decision_based_on(decision_id);
CREATE INDEX ix_hc ON handoff_carries(handoff_id);
