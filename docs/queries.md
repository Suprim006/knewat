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
| `schema/indexes` | schema | rw | Range indexes, every one on a single property (no composite indexes): `id` on all 16 labels (incl. `Recall`); `Entity.norm_name`; `Fact.subject_id`, `Fact.predicate`, `Fact.valid_to`, `Fact.status`; `Task.status`; `Step.n`, `Step.agent_id`; `ToolCall.at`; `created_at` on all 16 labels (backs `view/subgraph`); `Source.uri`, `Scope.name`, `Procedure.task_type` (the last four back the MERGE keys of `create_source` / `create_scope` / `log_procedure_run`, `best_procedure` and the per-agent Step lookups; P5 review Q4) | Makes id lookups and the validity-window/ready-task filters index-backed; prerequisite for the UNIQUE constraints. Schema housekeeping, no traversal. |
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
| `engram/assert_fact` | engram | rw | One statement: find current facts on entity+predicate+scope, classify duplicate / supersede / contradiction, then write Fact with `ABOUT`, `IN_SCOPE`, `ASSERTED_BY {at}`, `DERIVED_FROM`, `SUPERSEDES`, `CONTRADICTS`. The current-fact lookup is anchored at the Entity (`(e)<-[:ABOUT]-(f {predicate, status, valid_to})-[:IN_SCOPE]->(sc)`), so its cost follows the entity's facts, not the facts in the scope (P5 review Q2). A duplicate is equal `norm_value`, or value-embedding distance <= threshold **and** identical numeric/version tokens (`Fact.value_tokens`). A duplicate keeps ONE fact (no `DUPLICATES` edge) and adds a timestamped `ASSERTED_BY`; it also supersedes the asserting agent's own earlier different current facts (`(dup)-[:SUPERSEDES]->(old)`). Window times use `ts = max(now, valid_from of closing facts)`. An unknown scope/episode/source writes nothing (not even the Agent); `Engram.assert_fact` checks those ids before it creates a new subject Entity, so a rejected call leaves no orphan Entity either (P5 review Q8) | Conflict detection and validity-window closing are traversals plus an atomic multi-edge write; per-graph write serialisation makes it race-free. |
| `engram/recall` | engram | ro | Hybrid recall: vector seeds over `Fact.embedding` (+ keyword ids), scope inheritance (`INHERITS*0..3`), validity/status filter at time `t`, 1-hop `ABOUT` expansion to at most 5 nearest sibling facts per seed, why-path pieces. The expansion is entity-first (`(e)<-[:ABOUT]-(g)` with the property filters, then the scope test on the bound `g`) and the keyword seeds are id seeks, so latency follows the entity fan-out rather than the number of facts in the scope (P5 review Q1) | Vector index seed, then scope and entity traversals and provenance edges, in one read. **Limitation:** FalkorDB's vector procedure has no pre-filter, so filters run after the index returns `over` nodes; the wrapper re-runs with `over` x4 (start `4k`, cap 512) until `k` rows survive, and `engram/recall_keywords` backs it up beyond the cap. |
| `engram/recall_keywords` | engram | ro | Ids of in-scope, currently valid facts whose `Fact.value` matches any query word | Full-text index inside the graph; filters before its `LIMIT`, so it cannot be starved by out-of-scope facts. |
| `engram/missing_refs` | engram | ro | Which scope / episode / source id exists (explains a rejected `assert_fact`) | Diagnostic id lookups. |
| `engram/fact_history` | engram | ro | Up to `limit` (default 200, max 10 000) versions of one entity+predicate in a scope, newest kept, listed oldest first, with `SUPERSEDES`/`CONTRADICTS` ids. Anchored at the Entity (P5 review Q2, Q11) | Version chain is edges between Fact nodes. |
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
| `relay/claim_next_task` | rw | Atomically claim the best ready task (open or lease-expired, all `DEPENDS_ON` targets `done`; order: priority desc, `created_at`, then `seq` = input position in `create_tasks`, then id), set lease and `version+1`, create the `CLAIMED` edge (with `reclaimed_from`). `Relay.claim_next_task` rejects `lease_ms` outside 1 ms..24 h so `now + lease_ms` cannot overflow int64 or lock a task for good (P5 review Q7) | Readiness is a traversal over `DEPENDS_ON`; the claim is a single serialised graph write, so two agents never win the same task (50-thread test). |
| `relay/ready_tasks` | ro | Tasks claimable now, best first (same rule as the claim) | Dependency check by traversal. |
| `relay/heartbeat` | rw | Extend a lease (`max(current, now + lease_ms)`, never shortens) only if `claimed_by = agent AND status = 'claimed'`; `lease_ms` is bounded 1 ms..24 h like the claim (P5 review Q7) | Compare-and-set on graph node state. |
| `relay/task_status` | ro | One task with its direct dependencies and their statuses | One-hop `DEPENDS_ON` traversal. |
| `relay/agent_exists` | ro | Explains an empty claim result (unknown agent) | Diagnostic id lookup. |
| `relay/complete_task` | rw | CAS on `claimed_by` + `version`; set `done`, `done_at`, `version+1`; create `Artifact`s with `PRODUCED_BY` and `(Artifact)-[:FOR]->(Task)` (the `task_id` property is kept). `Task.done_at = 0` means "not finished" (FalkorDB stores no null); open-ended `valid_to`/`ended_at` use the `9999999999999` sentinel | Completion unblocks `DEPENDS_ON` successors; artifacts hang off the producing agent as graph evidence. |
| `relay/fail_task` | rw | Same CAS and the same `Artifact` edges, status `failed` and a `fail_reason`; a failed dependency keeps dependents blocked | Failure propagates by traversal (`blocked_by_failure`). |
| `relay/existing_artifacts` | ro | Which artifact ids exist (explains a rejected complete/fail/handoff) | Diagnostic id lookup. |
| `relay/handoff` | rw | Create `Handoff` + `FROM`/`TO`/`FOR` + `CARRIES` to artifacts and facts; matches every referenced node first and compares counts, so a bad id writes nothing | A handoff is a node that links agents, a task and the evidence it carries, so it can be traversed later (`why`). |
| `relay/verify_artifact` | rw | `MERGE (Artifact)-[:VERIFIED_BY {at, independent}]->(Agent)`; `independent` = the verifier did not produce the artifact, and is persisted on the edge | Verification is an edge, not a self-reported field; self-verification stays distinguishable. |
| `relay/record_decision` | rw | Create `Decision` with `DECIDED`, `FOR`, and all-or-nothing `BASED_ON` facts (fact count compared in the same statement) | Decisions link to the exact facts they rest on; `why(decision)` walks `BASED_ON`. |
| `relay/dependents_of` | ro | One BFS level: distinct tasks that directly depend on any task in a frontier list | Transitive dependency traversal done level by level over distinct nodes (<= 10 levels, <= 5000 tasks) by `Relay.blocked_by_failure`; replaces the exponential `*1..10` path enumeration. |
| `relay/reopen_task` | rw | CAS `failed` -> `open`: `version+1`, clears lease/`claimed_by`/`done_at`, records `reopened_by`/`reopened_at` | Retry path for failed work; the version bump fences out the old claim holder. |
| `relay/missing_refs` | ro | Which agent/task/fact/artifact ids exist (explains a rejected handoff or decision) | Diagnostic id lookups. |

## Lineage queries (`queries/lineage/`)

Python entry point: `plexus.lineage.Lineage(client, graph)`; the pure result-shaping helpers are in `plexus/lineage/explain.py`.

**Design decision: how writes and reads attach to Steps.** Lineage uses the *simpler alternative*: a separate
`lineage/link_step` statement (`link_step` / `link_assert_result` in Python) that the tool layer calls right after
an Engram/Relay write, plus `record_recall` which attaches its own `READ` edges. No Engram/Relay query was touched.
- *Trade-off:* the preferred tail fragment would make "write + `WROTE` edge" one atomic statement. It would require
  editing about ten queries owned by other modules (each with different result shapes), which collides with the
  parallel work on the MCP layer. The two-statement version can lose the edge if the process dies between the
  statements (the fact exists, the step does not point at it). That is acceptable here: the loss is one provenance edge,
  never a memory, and `link_step` is idempotent (`MERGE`) so a retry repairs it.
- Nothing is lost in the other direction: `link_step` is all-or-nothing (it writes no edge if any id is unknown).
- `Engram.assert_fact(step=...)` / `log_procedure_run(step=...)` keep their reserved argument unused.

| Name | Mode | Purpose | Why it's a graph query |
|---|---|---|---|
| `lineage/create_source` | rw | `MERGE (Source {uri})`, refresh kind/trust, return its id | Provenance anchor: facts point at it with `DERIVED_FROM`, which forget/quarantine traverse. |
| `lineage/record_step` | rw | One statement: create the agent's next `Step` (`BY`, `NEXT` from its latest step), idempotent per (agent, n), refuses out-of-order n | The chain tail is found by index lookup on `Step(n)`, the `NEXT` edge appended atomically. |
| `lineage/link_step` | rw | `(Step)-[:READ]->(Fact)` and `(Step)-[:WROTE]->(Fact\|Decision\|Handoff\|Task)`; all ids matched first, counts compared, so a bad id writes nothing | The edges are what `who_knew` / `knew_at` / quarantine traverse. |
| `lineage/existing_ids` | ro | Which ids exist as Step/Fact/Decision/Handoff/Task (explains a rejected link or recall record) | Diagnostic id lookup, one index-backed branch per label. |
| `lineage/link_derived` | rw | `(Fact)-[:DERIVED_FROM]->(Source\|Episode\|Fact)`, all-or-nothing | Derivation edges are the paths the cascade follows. |
| `lineage/record_recall` | rw | One statement: `Recall` + `BY` + `IN_STEP` + `RETURNED{rank,score}` per fact + `(Step)-[:READ]->(Fact)`. The Agent is merged only after the all-or-nothing guard, so a rejected call writes nothing (P5 review Q8) | Stores the recall as graph structure so `why_recalled` is a traversal, not a log lookup. |
| `lineage/why_edges` | ro | Provenance subgraph of a Decision or Fact as a flat edge list (UNION of bounded branches): `DECIDED`, `FOR`, `BASED_ON`, `ASSERTED_BY`, `ABOUT`, `IN_SCOPE`, `DERIVED_FROM*1..3`, Session/agent behind an episode, `SUPERSEDES`/`CONTRADICTS`/`DUPLICATES`, writing Steps and their agents | Variable-length path from decision to fact to agent/step/source; this is the "why" answer. |
| `lineage/node_info` | ro | Display properties (no embeddings) for a list of ids, one index-backed branch per label | Property fetch for the nodes `why_edges` found, so the View can label them. |
| `lineage/why_recalled` | ro | A stored `Recall` with every `RETURNED` fact (rank, score) and its entity, asserting agents, one-hop `DERIVED_FROM`, scope | Traverses the edges `record_recall` stored. |
| `lineage/who_knew` | ro | Agents whose Steps `READ` a fact (step n, time, via which recalls), plus asserters and writing steps | `READ` edges from Steps, one hop each way. |
| `lineage/knew_at` | ro | Time machine: facts an agent READ at or before step N that were still valid at that step's time, plus what its Steps WROTE | Step chain + `READ`/`WROTE` edges + validity window on the Fact. |
| `lineage/as_of` | ro | The fact valid at time t for (subject, predicate), nearest scope first (`INHERITS*0..3`) | Entity -> `ABOUT` -> Fact with a validity-window filter and scope traversal. |
| `lineage/forget_source` | rw | One statement: facts reaching a Source through `DERIVED_FROM` chains of 1..5 hops -> `status='forgotten'`, `valid_to=min(valid_to, now)`; `BASED_ON` decisions flagged; `CARRIES` handoffs reported; bounded by `limit` (<= 5000, applied before the SET); the reported `decision_ids` / `handoff_ids` are cut at `max_detail` (default 500) with exact `*_total` counts (P5 review Q11) | The cascade is expanded level by level from the source (five one-hop steps, each driven by the previous level; a `(f:Fact)-[:DERIVED_FROM*1..5]->(src)` pattern is planned from the Fact side and scans every fact, P5 review Q3); it removes the derived facts from recall in one atomic write. |
| `lineage/quarantine` | rw | Stretch. Same traversal, `status='quarantined'` (reversible, `prior_status` kept); returns the blast radius: reading Steps/agents, `BASED_ON` decisions, `CARRIES` handoffs. `reads` / decisions / handoffs are cut at `max_detail` (default 500, totals and the full agent list stay exact; P5 review Q11) | Blast radius = traversal from poisoned facts back out through `READ`, `BASED_ON`, `CARRIES`. |
| `lineage/release_quarantine` | rw | Stretch. Restores `prior_status` of quarantined facts under a Source | Same source-anchored cascade, reversed write. |

Verified FalkorDB 6.0.2 quirks hit while writing these (kept in the query comments where relevant):
- `WITH a, x + collect(y) AS z` (a list expression that mixes a grouping key with an aggregate) returns `null`; put the `collect` in its own `WITH` first.
- After `WITH sc, min(length(p)) AS hops`, a later `MATCH (f)-[:IN_SCOPE]->(sc)` on the aggregated node returned no rows. `as_of` collects `{id, hops}` maps and filters on `fs.id` instead.
- A comment line indented by two or more spaces after the header is read as a continuation of the previous header value (including `mode`), so free comments in `.cypher` files use a single space after `//`.
## Audit queries (`queries/audit/`)

| Name | Mode | Purpose | Why it's a graph query |
|---|---|---|---|
| `audit/record_tool_call` | rw | Create a `ToolCall` (tool, agent, step, query name, server-side `run_time_ms`, `wrote`) with `IN_STEP` and `CREATED`/`UPDATED` edges to the nodes the tool touched (≤ 200, label+id index lookups, unknown ids get no edge) | The flow the View draws is these edges: each tool call points at the exact nodes it created or updated. Runs as the statement right after the tool's own write (deliberate deviation from "same statement": `run_time_ms` is only known after execution). |

## View queries (`queries/view/`, all `ro`, used only by the read-only View API)

| Name | Mode | Purpose | Why it's a graph query |
|---|---|---|---|
| `view/inventory_nodes` / `view/inventory_edges` | ro | Node count per label / edge count per relationship type: one indexed count per graph-model label/type (O(labels), not O(nodes)) | The data inventory is the shape of the graph itself. |
| `view/inventory_nodes_scan` / `view/inventory_edges_scan` | ro | Full-scan counts, complete for any label/type (O(nodes)/O(edges)) | Fallback used only when the graph holds a label or type the fast counts don't list. |
| `view/labels` / `view/relationship_types` | ro | Labels and relationship types the graph has used (metadata, O(1)) | Decides whether the fast inventory counts are complete. |
| `view/scope_lookup` | ro | An existing `Scope` by id or (kind, name), never created | Read tools (`recall`, `as_of`, `fact_history`) use it, so a typo in `scope` never grows the graph. |
| `view/inventory_keys` | ro | Property keys per label, sampled per label (so every label gets keys) | Shows which properties each label really carries. |
| `view/indexes` | ro | `db.indexes()`: range, full-text and vector indexes with status | Proves the vector/full-text indexes recall depends on are operational. |
| `view/subgraph` | ro | Newest N nodes (label / `created_at` filter) plus the edges among them, one row, display-property whitelist, no embeddings. One `created_at` index range seek per label (16 `UNION ALL` branches, gated by `$labels`); no All Node Scan (plan-shape test `tests/api/test_subgraph_plan.py`) | The explorer draws exactly the stored nodes and edges. |
| `view/flow` | ro | Tool calls in order with the nodes each `CREATED`/`UPDATED` and its `IN_STEP` step | The flow timeline is a traversal of `ToolCall` → `CREATED`/`UPDATED` edges. Also the SSE feed (polled every 500 ms with a 2 s look-back, de-duplicated by id). |
| `view/step_agents` | ro | Agents that have a `Step` numbered ≤ n | `GET /step/{n}` lists these, then asks `Lineage.knew_at` per agent (one definition of "what X knew at step N" for the MCP tool and the API). (The earlier single-query `view/knew_at` was dead code and was removed in P5.) |

## Crucible queries (`queries/crucible/`, benchmark harness only; not used by the product)

| Name | Mode | Purpose | Why it's a graph query |
|---|---|---|---|
| `crucible/list_tasks` | ro | Every task with its state, claimer and version | The L1 harness counts double claims, lost updates and orphans from this. |
| `crucible/strip_edges` | rw | **Ablation only (D-001):** deletes `DEPENDS_ON`, `BASED_ON`, `DERIVED_FROM` and `READ` in bounded batches | Measures which capabilities break without the edges. 7 of 7 break; 5 of 5 controls are unaffected (`docs/BASELINE.md`). |

## Demo queries (`queries/demo/`, `plexus demo ablation` only; not used by the product)

| Name | Mode | Purpose | Why it's a graph query |
|---|---|---|---|
| `demo/ablation_targets` | ro | Picks the probe targets on the intact tenant: the Decision with most `BASED_ON` facts, the agent with most `READ` edges, the Source whose forgetting reaches most decisions/facts (`DERIVED_FROM*1..5` then `BASED_ON`), the root Task with most dependents | The picks *are* edge counts and variable-length traversals; on the stripped copy they would all be empty. |
| `demo/ablation_task_deps` | ro | Every task with the ids it depends on | Ground truth for the dependency-aware-claim probe (`DEPENDS_ON` read on the intact tenant). |
| `demo/ablation_reset_tasks` | rw | Sets every task of a **scratch copy** back to `open` so a finished recording has something to claim | Bounded write (`LIMIT`); never run on a real tenant, only on the throw-away copies the command drops. |

