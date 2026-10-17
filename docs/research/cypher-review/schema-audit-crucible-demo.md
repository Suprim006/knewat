# Cypher review: `schema/` + `audit/` + `crucible/` + `demo/` (5 + 1 + 4 + 3 = 13 files, 232 lines)

Read-only audit on `feature/neuro-memory-research` (HEAD e126875), done by the orchestrator (delegation cap = 2
subagents). No live run was needed for this bucket.

## SUMMARY

| Severity | Count | Items |
|---|---|---|
| CONFIRMED / SUSPECTED BUG | 0 | — |
| BOUNDEDNESS RISK | 0 product-path; 2 harness-only notes | `demo/ablation_targets` var-length `*1..5` per Source (documented "demo tenant only"); `crucible/l5_real_facts` label scan before ORDER BY (harness) |
| SIMPLIFICATION | 1 | `audit/record_tool_call` 16 OPTIONAL MATCHes are inherent (label-bound seeks); generate them from `LINKABLE_LABELS` if the list changes again |
| CLARITY | 3 | `schema/indexes` header lists the reasons but `Procedure.name` (a MERGE key in `log_procedure_run`) has no index; `demo/ablation_targets` header says "the reach of forget_source" = `*1..5` but forget_source now defaults to 8 (max 12); `demo/ablation_reset_tasks` resets only the first `$limit` tasks with no ORDER BY |
| CLEAN | 11 files | listed at the end |

Product path vs harness: `schema/*` (applied by `apply_schema`) and `audit/record_tool_call` (every MCP tool call) are
product path. `crucible/*` and `demo/*` run only on throw-away benchmark / ablation tenants (headers say so and callers
confirm: `crucible/l5`, `demo/ablation.py`), so their findings are low severity.

---

## schema/

### fulltext.cypher (9 lines)
CLEAN. Split on `;`, tolerated "already indexed". Fact.value full text backs `recall_keywords`; Entity.name backs
`recall_entities` / `find_entity_fulltext`.

### indexes.cypher (69 lines)
- CLEAN for correctness. Length is inherent: one statement per single-property range index (FalkorDB has no composite
  indexes), split on `;` by the loader.
- Coverage check (grep of every `(:Label {prop: …})` and `WHERE x.prop` in `plexus/queries`): every equality key used in a
  MATCH/MERGE has an index **except** `Procedure.name` (MERGE key in `engram/log_procedure_run` together with the indexed
  `task_type`; the seek on `task_type` then filters `name`, so it is fine at realistic sizes) and `Scope.kind` (filtered
  after the `Scope(name)` seek). No index looked unused: `Fact.subject_id` (6 files), `Fact.valid_to` (20), `Entity.norm_name`
  (7), `Procedure.task_type` (4), `Scope.name` (6) are all referenced.
- CLARITY (low): the header comment explains each block well; it could note `Procedure.name` is deliberately unindexed.
- SIMPLIFICATION: none worth doing; grouping by label would read better but changes nothing.

### list_constraints.cypher (6 lines), list_indexes.cypher (6 lines)
CLEAN. (Constraints themselves are created in `plexus/graph/schema.py` via `GRAPH.CONSTRAINT CREATE`, not in a .cypher file
— consistent with the header of `indexes.cypher`.)

### vector.cypher (10 lines)
CLEAN. 384-d cosine on Entity/Fact/Episode; the distance-not-similarity note matches `activation/novelty` and `engram/recall`
(`ORDER BY … ASC`).

## audit/

### record_tool_call.cypher (41 lines)
- CLEAN for correctness and boundedness. Runs on every MCP tool call: one CREATE, one Step seek, then ≤ 200 links
  (`MAX_LINKS = 200` in `audit/recorder.py`) × 16 label-bound id seeks; the empty-list case is replaced by one inert row,
  so the final `sum` always has a row. The 16 labels match `LINKABLE_LABELS` in `audit/recorder.py` exactly.
- The 16 OPTIONAL MATCHes are not redundant: an unlabeled `MATCH (n {id: l.id})` would be an All Node Scan
  (plan-shape 6b). Per link only the matching label's `WHERE l.label = 'X'` is true, so there is no row multiplication.
- SIMPLIFICATION (optional): generate the 16 lines from `LINKABLE_LABELS` so the two lists cannot drift. Low value.

## crucible/ (harness only)

### l5_add_reads.cypher (12 lines)
CLEAN. MERGE of the Step per row inside one UNWIND (the same step id across rows is merged once on 6.0.2; the L5 harness
relies on it and its results are reproducible).

### l5_real_facts.cypher (12 lines)
CLEAN. Reads every active fact before `ORDER BY … LIMIT` (harness, documented).

### list_tasks.cypher (11 lines)
CLEAN.

### strip_edges.cypher (12 lines)
CLEAN. `WITH r LIMIT $limit DELETE r` is the correct way to bound an eager DELETE.

## demo/ (ablation only)

### ablation_reset_tasks.cypher (10 lines)
CLARITY (low): `MATCH (t:Task) WITH t LIMIT $limit SET …` with no ORDER BY and no `WHERE t.status <> 'open'` resets an
arbitrary `$limit` tasks; with more than `MAX_TASKS = 500` tasks some stay claimed/done. The caller only runs it on demo
copies (hundreds of tasks), so it is harmless; `WHERE t.status <> 'open'` would make repeated calls converge.

### ablation_targets.cypher (25 lines)
- BOUNDEDNESS (documented): L17 `OPTIONAL MATCH (f:Fact)-[:DERIVED_FROM*1..5]->(s)` per Source enumerates paths; the header
  already says "fine for a demo tenant, not meant for a huge one".
- CLARITY: "the reach of forget_source" — forget_source's reach is now `$depth` 1..12 (default 8), not `*1..5`.

### ablation_task_deps.cypher (9 lines)
CLEAN.

## Clean files (11)
schema: fulltext, indexes, list_constraints, list_indexes, vector — audit: record_tool_call — crucible: l5_add_reads,
l5_real_facts, list_tasks, strip_edges — demo: ablation_task_deps. (`ablation_reset_tasks` and `ablation_targets` carry
clarity notes only.)
