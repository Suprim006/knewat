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
