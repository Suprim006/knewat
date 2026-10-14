# Query index

Every Cypher statement the product depends on lives in `plexus/queries/<area>/<name>.cypher` with a header
(`name`, `purpose`, `params`, `returns`, `mode`, optional `split`) and is loaded by
`plexus.graph.queries.QueryLibrary`. The loader rejects a missing or unexpected parameter, a `$param` that the
header does not declare, and a header `name` that differs from the file path. `GraphClient.ro()` refuses
`mode: rw` queries and runs the rest through `GRAPH.RO_QUERY`.

Add one row per query when you add the file. "Why it's a graph query" must be a real reason (a traversal, an
index-backed lookup in the graph, an atomic graph write). Housekeeping queries say so.

| Name | Module | Mode | Purpose | Why it's a graph query |
|---|---|---|---|---|
| `schema/indexes` | schema | rw | Range indexes: `id` on all 15 labels; `Fact(subject_id, predicate, valid_to, status)`, `Task(status)`, `Step(n)`, `ToolCall(at)` | Makes id lookups and the validity-window/ready-task filters index-backed; prerequisite for the UNIQUE constraints. Schema housekeeping, no traversal. |
| `schema/fulltext` | schema | rw | Full-text indexes on `Entity.name`, `Fact.value`, `Episode.text` | Keyword seeds for entity resolution and recall that then expand along edges. Schema housekeeping. |
| `schema/vector` | schema | rw | 384-d cosine vector indexes on `Entity/Fact/Episode.embedding` | Semantic seeds for hybrid recall (vector, then graph expansion, then validity filter). Schema housekeeping. |
| `schema/list_indexes` | schema | ro | `CALL db.indexes()`: list indexes and status | Introspection for tests and the View inventory. |
| `schema/list_constraints` | schema | ro | `CALL db.constraints()`: list constraints and status | Lets `apply_schema` wait until each UNIQUE constraint is `OPERATIONAL`. |
| `engram/start_session` | engram | rw | MERGE Agent, create Session, `(Agent)-[:HAD]->(Session)` | Atomic multi-node/edge graph write. |
| `engram/remember_episode` | engram | rw | Append an Episode: `HAS_EPISODE` + `NEXT` from the session's current last episode, one statement | The chain tail is found by traversal (`NOT (last)-[:NEXT]->()`) and extended atomically, so concurrent appends cannot fork the chain. |
| `engram/find_entity_exact` | engram | ro | Entity by normalised name | Index-backed lookup on `Entity.norm_name`. |
| `engram/find_entity_fulltext` | engram | ro | Entity candidates by name tokens | Full-text index inside the graph (step 2 of entity resolution). |
| `engram/find_entity_vector` | engram | ro | Nearest entities by name embedding | Vector index inside the graph (step 3 of entity resolution). |
| `engram/upsert_entity` | engram | rw | `MERGE (e:Entity {norm_name})` | Atomic MERGE: concurrent creates of one name yield one node. |
| `engram/create_scope` | engram | rw | MERGE Scope on (kind, name) + `INHERITS` edges; no write if a parent is missing | Scope hierarchy is graph structure that recall traverses. |
| `engram/assert_fact` | engram | rw | One statement: find current facts on entity+predicate+scope, classify duplicate / supersede / contradiction, then write Fact with `ABOUT`, `IN_SCOPE`, `ASSERTED_BY`, `DERIVED_FROM`, `SUPERSEDES`, `CONTRADICTS` | Conflict detection and validity-window closing are traversals plus an atomic multi-edge write; per-graph write serialisation makes it race-free. |
| `engram/recall` | engram | ro | Hybrid recall: vector seeds over `Fact.embedding`, scope inheritance (`INHERITS*0..3`), validity/status filter at time `t`, 1-hop `ABOUT` expansion to sibling facts, why-path pieces | Vector index seed, then scope and entity traversals and provenance edges, in one read. |
| `engram/fact_history` | engram | ro | All versions of one entity+predicate in a scope with `SUPERSEDES`/`CONTRADICTS` ids | Version chain is edges between Fact nodes. |
| `engram/log_procedure_run` | engram | rw | MERGE Procedure, create Run with `USED_IN`, `BY`, optional `FOR` Task | Atomic multi-node/edge write. |
| `engram/best_procedure` | engram | ro | Procedures for a task type ranked by success rate then runs | Aggregation over `Procedure-[:USED_IN]->Run`. |

Constraints are not Cypher: `apply_schema` issues `GRAPH.CONSTRAINT CREATE <graph> UNIQUE NODE <Label>
PROPERTIES 1 id` for `Task`, `Fact`, `Agent`, `Decision` and `Handoff` (see `docs/graph-model.md`).

## Header format

```
// name: engram/assert_fact          must equal the path under queries/ without .cypher
// purpose: one line
// params: subject_id:str, now:int   name:type pairs, or "none"; indented "//   ..." lines continue a value
// returns: columns / shape
// mode: ro|rw
// split: ;                          optional: several statements in one file (schema only)
```

Other `//` comment lines in the header or body are free comments and are ignored.

## Relay queries (`queries/relay/`)

| Name | Mode | Purpose | Why it's a graph query |
|---|---|---|---|
| `relay/register_agent` | rw | MERGE the `Agent` node by id and refresh name/role/harness | Agents are graph nodes that claims, handoffs and decisions attach to. |
| `relay/create_tasks` | rw | Create a task DAG (`UNWIND` tasks, then `DEPENDS_ON` edges) in one statement, guarded so it writes all or nothing | The dependency DAG is stored as `DEPENDS_ON` edges; edges use list indexes because nodes created in the same statement are not `MATCH`able. |
| `relay/existing_tasks` | ro | Which task ids exist (explains a rejected create) | Diagnostic id lookup (index-backed). |
| `relay/claim_next_task` | rw | Atomically claim the best ready task (open or lease-expired, all `DEPENDS_ON` targets `done`), set lease and `version+1`, create the `CLAIMED` edge (with `reclaimed_from`) | Readiness is a traversal over `DEPENDS_ON`; the claim is a single serialised graph write, so two agents never win the same task (50-thread test). |
| `relay/ready_tasks` | ro | Tasks claimable now, best first (same rule as the claim) | Dependency check by traversal. |
| `relay/heartbeat` | rw | Extend a lease only if `claimed_by = agent AND status = 'claimed'` | Compare-and-set on graph node state. |
| `relay/task_status` | ro | One task with its direct dependencies and their statuses | One-hop `DEPENDS_ON` traversal. |
| `relay/agent_exists` | ro | Explains an empty claim result (unknown agent) | Diagnostic id lookup. |
| `relay/complete_task` | rw | CAS on `claimed_by` + `version`; set `done`, `done_at`, `version+1`; create `Artifact`s with `PRODUCED_BY` | Completion unblocks `DEPENDS_ON` successors; artifacts hang off the producing agent as graph evidence. |
| `relay/fail_task` | rw | Same CAS, status `failed` and a `fail_reason`; a failed dependency keeps dependents blocked | Failure propagates by traversal (`blocked_by_failure`). |
| `relay/existing_artifacts` | ro | Which artifact ids exist (explains a rejected complete/fail/handoff) | Diagnostic id lookup. |
| `relay/handoff` | rw | Create `Handoff` + `FROM`/`TO`/`FOR` + `CARRIES` to artifacts and facts; matches every referenced node first and compares counts, so a bad id writes nothing | A handoff is a node that links agents, a task and the evidence it carries, so it can be traversed later (`why`). |
| `relay/verify_artifact` | rw | `MERGE (Artifact)-[:VERIFIED_BY]->(Agent)`; reports whether the verifier is independent of the producer | Verification is an edge, not a self-reported field. |
| `relay/record_decision` | rw | Create `Decision` with `DECIDED`, `FOR`, and all-or-nothing `BASED_ON` facts (fact count compared in the same statement) | Decisions link to the exact facts they rest on; `why(decision)` walks `BASED_ON`. |
| `relay/blocked_by_failure` | ro | Not-done tasks reachable by `(t)<-[:DEPENDS_ON*1..10]-(x)`, with shortest distance | Transitive dependency traversal. |
| `relay/missing_refs` | ro | Which agent/task/fact/artifact ids exist (explains a rejected handoff or decision) | Diagnostic id lookups. |

## Audit queries (`queries/audit/`)

| Name | Mode | Purpose | Why it's a graph query |
|---|---|---|---|
| `audit/record_tool_call` | rw | Create a `ToolCall` (tool, agent, step, query name, server-side `run_time_ms`, `wrote`) with `IN_STEP` and `CREATED`/`UPDATED` edges to the nodes the tool touched (≤ 200, label+id index lookups, unknown ids get no edge) | The flow the View draws is these edges: each tool call points at the exact nodes it created or updated. Runs as the statement right after the tool's own write (deliberate deviation from "same statement": `run_time_ms` is only known after execution). |
