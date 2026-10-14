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
