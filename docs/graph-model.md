# Plexus graph model v1

Source of truth: `docs/PLAN.md` §2. The schema is applied by `plexus/queries/schema/*.cypher` through
`plexus.graph.schema.apply_schema`, and `plexus/tests/test_schema.py` checks the live indexes and constraints
against the lists below. If this file and the schema files disagree, that is a bug.

Every node has `id` (UUID string) and `created_at` (epoch ms). Embeddings are `vecf32`, 384-d, cosine.

## Diagram

```mermaid
erDiagram
    Agent ||--o{ Session : HAD
    Session ||--o{ Episode : HAS_EPISODE
    Episode ||--o| Episode : NEXT
    Fact }o--|| Entity : ABOUT
    Fact }o--o{ Episode : "DERIVED_FROM"
    Fact }o--o{ Source : "DERIVED_FROM"
    Fact }o--o{ Fact : "DERIVED_FROM / SUPERSEDES / DUPLICATES / CONTRADICTS"
    Fact }o--|| Scope : IN_SCOPE
    Scope }o--o| Scope : INHERITS
    Fact }o--|| Agent : ASSERTED_BY
    Procedure ||--o{ Run : USED_IN
    Run }o--|| Agent : BY
    Run }o--|| Task : FOR
    Task }o--o{ Task : DEPENDS_ON
    Agent ||--o{ Task : "CLAIMED {at, lease_until}"
    Handoff }o--|| Agent : FROM
    Handoff }o--|| Agent : TO
    Handoff }o--|| Task : FOR
    Handoff }o--o{ Artifact : CARRIES
    Handoff }o--o{ Fact : CARRIES
    Agent ||--o{ Decision : DECIDED
    Decision }o--o{ Fact : BASED_ON
    Decision }o--|| Task : FOR
    Artifact }o--|| Agent : PRODUCED_BY
    Artifact }o--o{ Agent : VERIFIED_BY
    Step }o--|| Agent : BY
    Step }o--o{ Fact : READ
    Step }o--o{ Fact : "WROTE (also Decision, Handoff, Task)"
    Step ||--o| Step : NEXT
    ToolCall }o--|| Step : IN_STEP
    Recall }o--o{ Fact : RETURNED
    Recall }o--|| Agent : BY
    ToolCall }o--o{ Fact : "CREATED / UPDATED (any node)"
```

The diagram is a summary (ER cardinalities are indicative). The edge table below is exact.

## Node labels

| Label | Key properties | Module |
|---|---|---|
| `Agent` | `id, name, role, harness` | all |
| `Scope` | `id, kind: user\|project\|global, name` | Engram |
| `Session` | `id, agent_id, started_at, ended_at` | Engram |
| `Episode` | `id, role, text, at, step, embedding` | Engram |
| `Entity` | `id, name, norm_name, kind, embedding` | Engram |
| `Fact` | `id, subject_id, predicate, value, valid_from, valid_to (OPEN), recorded_at, status: active\|superseded\|quarantined\|forgotten, confidence, embedding` | Engram |
| `Source` | `id, uri, kind, trust, title, text` | Lineage |
| `Procedure` | `id, name, task_type, steps_json` | Engram |
| `Run` | `id, at, success, notes` | Engram |
| `Task` | `id, title, status: open\|claimed\|done\|failed, priority, lease_until, claimed_by, version, done_at` | Relay |
| `Handoff` | `id, at, note` | Relay |
| `Artifact` | `id, kind, uri, hash, summary` | Relay |
| `Decision` | `id, text, at` | Relay |
| `Step` | `id, n, at, agent_id` | Lineage |
| `ToolCall` | `id, tool, at, agent_id, query_name, run_time_ms, wrote` | audit (feeds the View) |
| `Recall` | `id, at, query, scope_id, agent_id, k` | lineage (record behind `why_recalled`) |

## Edges

| Module | Edge | Properties |
|---|---|---|
| Engram | `(Session)-[:HAS_EPISODE]->(Episode)` | |
| Engram | `(Episode)-[:NEXT]->(Episode)` | |
| Engram | `(Agent)-[:HAD]->(Session)` | |
| Engram | `(Fact)-[:ABOUT]->(Entity)` | |
| Engram | `(Fact)-[:DERIVED_FROM]->(Episode\|Source\|Fact)` | |
| Engram | `(Fact)-[:IN_SCOPE]->(Scope)` | |
| Engram | `(Scope)-[:INHERITS]->(Scope)` | |
| Engram | `(Fact)-[:SUPERSEDES]->(Fact)` | |
| Engram | `(Fact)-[:DUPLICATES\|CONTRADICTS]->(Fact)` | |
| Engram | `(Fact)-[:ASSERTED_BY]->(Agent)` | |
| Engram | `(Procedure)-[:USED_IN]->(Run)` | |
| Engram | `(Run)-[:BY]->(Agent)` | |
| Engram | `(Run)-[:FOR]->(Task)` | |
| Relay | `(Task)-[:DEPENDS_ON]->(Task)` | |
| Relay | `(Agent)-[:CLAIMED]->(Task)` | `at, lease_until` |
| Relay | `(Handoff)-[:FROM]->(Agent)`, `(Handoff)-[:TO]->(Agent)`, `(Handoff)-[:FOR]->(Task)` | |
| Relay | `(Handoff)-[:CARRIES]->(Artifact\|Fact)` | |
| Relay | `(Agent)-[:DECIDED]->(Decision)` | |
| Relay | `(Decision)-[:BASED_ON]->(Fact)` | |
| Relay | `(Decision)-[:FOR]->(Task)` | |
| Relay | `(Artifact)-[:PRODUCED_BY]->(Agent)` | |
| Relay | `(Artifact)-[:VERIFIED_BY]->(Agent)` | |
| Lineage | `(Step)-[:BY]->(Agent)` | |
| Lineage | `(Step)-[:READ]->(Fact)` | |
| Lineage | `(Step)-[:WROTE]->(Fact\|Decision\|Handoff\|Task)` | |
| Lineage | `(Step)-[:NEXT]->(Step)` | |
| audit | `(ToolCall)-[:IN_STEP]->(Step)` | |
| audit | `(ToolCall)-[:CREATED\|UPDATED]->(any)` | |
| lineage | `(Recall)-[:RETURNED {rank, score}]->(Fact)`, `(Recall)-[:BY]->(Agent)`, `(Recall)-[:IN_STEP]->(Step)` | |

## Indexes and constraints

Created by `queries/schema/{indexes,fulltext,vector}.cypher` (idempotent) and `apply_schema`.

| Kind | Label.property | Why |
|---|---|---|
| Range | `id` on **every** label (16, including `Recall`) | entry point of every query; the UNIQUE constraints need it |
| Range | `Fact.subject_id`, `Fact.predicate`, `Fact.valid_to`, `Fact.status` | four separate single-property indexes (FalkorDB range indexes here are not composite): `predicate` / `valid_to` / `status` serve the as-of and active-only filters; the current-fact lookup of `assert_fact` starts at the Entity and uses them as filters |
| Range | `Task.status` | ready-task scans for `claim_next_task` |
| Range | `Step.n`, `Step.agent_id` | time-machine (step N); the agent's latest step and `knew_at` |
| Range | `ToolCall.at` | flow feed ordering |
| Range | `Entity.norm_name` | entity MERGE key |
| Range | `Source.uri`, `Scope.name`, `Procedure.task_type` | MERGE keys of `create_source`, `create_scope` (with `kind`) and `log_procedure_run` (with `name`); `best_procedure` filter |
| Full-text | `Entity.name`, `Fact.value`, `Episode.text` | keyword entity resolution and recall |
| Vector (384-d, cosine) | `Entity.embedding`, `Fact.embedding`, `Episode.embedding` | semantic seeds for recall |
| UNIQUE constraint | `Task.id`, `Fact.id`, `Agent.id`, `Decision.id`, `Handoff.id` | no duplicate ids; `apply_schema` waits until each is `OPERATIONAL` |

## Conventions

- **OPEN sentinel.** FalkorDB cannot store null properties, so an open-ended `valid_to` is
  `OPEN = 9_999_999_999_999`. "Currently valid" means `valid_to = OPEN` (or `valid_to > now`).
- **Time is epoch milliseconds (integers).** There is no `datetime()` on 6.0.2. Use `timestamp()` or pass
  `now` as a parameter (preferred, so tests are deterministic).
- **Ids are UUID strings we generate** (`randomUUID()` in Cypher or Python `uuid4`). FalkorDB's internal
  `id()` is not stable and is never stored or exposed.
- **Maps are JSON strings.** Map and null-containing array properties are rejected, so maps go through
  `toJSON()` (for example `Procedure.steps_json`).
- **Vector scores are distances.** Cosine `score` is lower-is-nearer: `ORDER BY score ASC`.
- **Graph naming.** One graph per tenant: `plexus_t_<tenant>` with `^[a-z0-9_]{1,48}$`
  (`plexus.graph.tenancy.graph_name`). Tests use `test_<uuid hex>` and delete the graph in teardown.
  Agents never pass a graph name; the tenant is bound per connection.
- **Statuses** are lowercase strings: `Fact.status` ∈ `active|superseded|quarantined|forgotten`,
  `Task.status` ∈ `open|claimed|done|failed`.
- **Bounded writes.** One statement per operation, `UNWIND` sizes bounded by the caller. `LIMIT` does not stop
  eager writes (`CREATE/SET/MERGE/DELETE`).

## Properties added during P1 (orchestrator-approved; graph model v1.1)

| Where | Property | Why |
|---|---|---|
| `Fact` | `norm_value` | normalised value used for exact duplicate detection |
| `Fact` | `value_embedding` (vecf32 384, no index) | value-only embedding for the paraphrase check. The full-sentence `embedding` put different values within 0.08 (e.g. PostgreSQL 16 vs MySQL 8 at 0.082); value-only separates them (0.064 same vs 0.165 different) |
| `Session` | `ended_at = OPEN` at creation | no null properties |
| `Episode` | `step = -1` when no step is given | no null properties |
| `Task` | `fail_reason`; `version` also bumped by complete/fail | CAS and diagnostics |
| `Artifact` | `task_id` | direct lookup without traversal |
| `Handoff`, `Decision` | `created_at` | ordering |
| `CLAIMED` edge | `reclaimed_from` (`''` when not a reclaim) | dead-agent recovery evidence |
| `VERIFIED_BY` edge | `at` | audit |

## Additions during P1-fix and P2 (graph model v1.2)

| Where | Addition | Why |
|---|---|---|
| `Fact` | `value_tokens` | numeric/version tokens. A paraphrase counts as a duplicate only when they are identical (v1 ≠ v2, 8080 ≠ 8081) |
| `Fact` | `forgotten_at`, `quarantined_at`, `prior_status` | Lineage forgetting and reversible quarantine |
| `Source` | `title`, `text` | optional human-readable name and excerpt, written by `lineage/create_source` (empty string when absent) |
| `Decision` | `flagged`, `flag_reason` | flagged (not deleted) when a fact it is `BASED_ON` is forgotten |
| `Task` | `seq` | FIFO tie-break for claims, by `create_tasks` input order |
| `Task` | `reopened_by`, `reopened_at` | `reopen_task` for failed tasks |
| `ToolCall` | `step` (-1 when none) | step number without a traversal |
| `ASSERTED_BY` edge | `at` | when each agent asserted (also for duplicates) |
| `VERIFIED_BY` edge | `independent` | self-verification is allowed but marked |
| `(Artifact)-[:FOR]->(Task)` | new edge (the `task_id` property is kept) | the artifact links to its task in the graph |
| Step attachment | a separate `link_step` statement right after the write | Lineage decision: atomicity of a provenance edge vs. editing every Engram/Relay query (see `docs/queries.md`) |
