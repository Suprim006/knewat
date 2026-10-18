# Cypher audit summary: all 111 `.cypher` files in `plexus/queries/` (2,721 lines)

> **STALE (2026-10-18):** the numbers in this document were measured on builds before the current main (7618d18) and are not valid for it until re-run. Build per number: [docs/NUMBERS_STATUS.md](../NUMBERS_STATUS.md).

Branch `feature/neuro-memory-research` (HEAD e126875). This is a read-only review: no query, Python or test file was changed.

Per-bucket reports (one section per file, every file covered):

| Bucket | Files | Reviewer | Report |
|---|---|---|---|
| `engram/` | 26 | Sonnet subagent | `cypher-review/engram.md` |
| `lineage/` | 19 | Sonnet subagent | `cypher-review/lineage.md` |
| `relay/` + `staleness/` | 31 | orchestrator | `cypher-review/relay-staleness.md` |
| `view/` + `activation/` | 22 | orchestrator | `cypher-review/view-activation.md` |
| `schema/` + `audit/` + `crucible/` + `demo/` | 13 | orchestrator | `cypher-review/schema-audit-crucible-demo.md` |

The orchestrator's review of the branch's Python scoring changes is in `BRANCH_REVIEW.md`.

**Deviation from the plan.** The task asked for 5 parallel subagents. The run's delegation cap was 2
(`delegation.oneshot_max_children`), so the two largest directories went to subagents and the orchestrator reviewed the
other three buckets itself, using the same checklist and the same live-check rules.

**Live checks.** Every bucket ran live checks on plexus-db-13 (127.0.0.1:6313), always in throw-away `audit_*` graphs
that were deleted afterwards. A finding marked **CONFIRMED** below has a live reproduction or a PROFILE record count in
its bucket report. A finding marked **SUSPECTED** was found by reading and was not reproduced.

---

## 1. Correctness: wrong answers, confirmed and suspected

Ranked by impact.

| # | File:lines | Status | What is wrong | Impact |
|---|---|---|---|---|
| C1 | `activation/activation.cypher` L27 (**this branch**) | CONFIRMED (live) | `artifacts_ok` counts VERIFIED_BY *paths* over *every* FOR task of the decision. The header and `docs/forgetting.md` say it counts independently verified artifacts of the decision's *done* tasks. Fixture: header semantics give 1, the query returned 3. | **Medium.** Each unit adds weight 1.0 to salience, and salience ≥ 0.5 protects a fact. In the default `mult` mode that protection also applies (see `BRANCH_REVIEW.md` finding 1). So one artifact verified twice is enough to protect a fact from sweeps and lift it to the neutral activation floor. |
| C2 | `engram/recall_hop_facts.cypher` L15-18 | CONFIRMED (live) | On a diamond scope graph (a scope that inherits another both directly and through a third) the same fact is returned twice. The duplicates fill the per-entity slots (`per_entity` = 3), so nearer facts are dropped. Live: `[g1, g1]` where `[g1, p1]` was expected. | **Medium.** This branch now calls the query at hop 0 for the §3.3 candidate union, so the named entity's facts can be under-filled whenever scopes form a diamond. Fixing it with a pattern predicate also makes the query shorter (engram.md). |
| C3 | `engram/assert_fact.cypher` L80-82 | CONFIRMED (live) | The `soft` (DUPLICATES_MAYBE) list is cut to `maybe_cap` in storage order, not nearest-first as the header says. With cap 1 it kept the farthest candidate. | **Low.** It needs 6 or more current facts with the same `dup_key`. Sorting in Python is safer than an in-query sort, which would need the zero-row guard. |
| C4 | `lineage/impact_fact.cypher` L55 (generated) | CONFIRMED (live) | The root fact is appended last, so it is the first one cut when the result is truncated. | **Low.** Fix it in `scripts/gen_impact_queries.py` (`[src] + reach`), not in the generated file. |
| C5 | `lineage/record_step.cypher` L21 | CONFIRMED (live) | On the idempotent and out-of-order paths, `previous_id` is the agent's latest step, not the preceding one. | **Low.** The service does not read the field. |
| S1 | `engram/relates_level.cypher` L13, L21 | **SUSPECTED, NOT CONFIRMED** | `LIMIT $limit` applies to the whole frontier per direction, with no `ORDER BY`. A hub entity could fill the limit and starve the other entities. | Unknown. It is related to the `recall(hops)` ranking defect already in PLEXUS_REPORT §9.3, but it is not the same issue. |

**Correctness counts.**
- 6 files have a correctness finding: 5 confirmed (C1-C5) and 1 suspected (S1).
- One of the six is new on this branch: C1.
- C2 is a pre-existing bug that the branch now relies on.

## 2. Performance and boundedness: confirmed bugs, then risks

### 2a. Confirmed

| # | File(s) | Evidence | Fix | Recommend |
|---|---|---|---|---|
| P1 | `lineage/quarantine.cypher` L66-81 | The `fs` and `reads` lists are carried as grouping keys, which makes the query quadratic. Live: 1,200 facts took 1.5 s and 2,500 facts timed out at 10 s. Callers allow up to 5,000 facts. `impact_*` already had this fixed (PLEXUS_REPORT §8.3). | Move the tail into `CALL {}` subqueries. The subagent prototyped this: 5,000 facts in 589 ms, with identical results at 1,500 facts. | **Yes, first.** |
| P2 | `lineage/why_derived_level.cypher`, all 4 branches | `UNWIND $frontier MATCH (:Fact {id})-[:R]->()` traverses every DERIVED_FROM edge per level: 5,004 records for a 1-element frontier. The header claims an index seek. | Bind the node first (plan-shape item 6c). Measured: 5,001 records drop to 1, with identical rows on branches 1-2. | **Yes.** |
| P3 | `lineage/link_step` L10-18, `relay/complete_task` L14, `relay/fail_task` L14, `relay/create_tasks` L16, `relay/handoff` L11+L13, `relay/record_decision` L11 | Cross-cutting pattern: `OPTIONAL MATCH (x:L) WHERE x.id IN $list` with an **empty** list scans the whole `L.id` index. A non-empty list is a seek. Live PROFILE results are listed below this table. | Plan-shape item 4: `UNWIND CASE WHEN size($l)=0 THEN [''] ELSE $l END AS k OPTIONAL MATCH (x:L {id: k})`. Keep the existing grouping keys so the guard row survives. | **Yes.** `link_step` is the hot one. |

P3 live PROFILE results:
- `link_step` with no `wrote_ids`, which is the case on every recall-linked step: it read 20,000 Fact and 2,000 Task index entries. Median server time was 4.8 ms, against 0.23 ms with one id.
- `complete_task` with no artifacts: 3,000 of 3,000 Artifacts read.
- `create_tasks` with no external dependencies: 3,001 of 3,001 Tasks read.

These scans grow linearly with the graph and run inside the per-graph serialised write queue.

**P3 suspected, not profiled.** The same empty-list shape appears in `lineage/record_recall` L16 (if a recall with no rows is recorded), `lineage/link_derived` L9-13 and `engram/create_scope` L6 (empty `$inherits`). The read-only error-path files are low priority: `relay/missing_refs`, `relay/existing_*`, `lineage/existing_ids`, `lineage/node_info`.

### 2b. Boundedness risks: work that grows without a cap

These are by reading unless a measurement is given.

| # | File | Risk |
|---|---|---|
| B1 | `lineage/forget_source` L67-73 | Same list-as-grouping-key problem as P1, milder. Measured 382 ms at 2,500 facts; about 1.5 s at the 5,000 cap is extrapolated, not measured. Apply the same `CALL` fix. |
| B2 | `engram/recall_predicates` (**this branch**) | The `Fact.predicate` seek returns every fact with that predicate in **all scopes, statuses and times**, then filters. Neither D-013 nor §9.3 mentions this. Cost grows with history for a common predicate. |
| B3 | `engram/recall`, `recall_entities`, `recall_hop_facts` | Hub fan-out (the `recall` header acknowledges it). |
| B4 | `engram/resolve_entity` | Runs a full-text OR over all entities that share any token, inside the serialised write. |
| B5 | `lineage/quarantine` `reads`; `lineage/knew_at`, `lineage/record_step` | `quarantine` materialises every (step, fact) pair before cutting to `max_detail`. `knew_at` and `record_step` read the agent's whole step history on every call; `record_step` runs before each write. |
| B6 | `staleness/mark_changed` | Lists are carried as grouping keys, but this was **measured acceptable** at the cap: 148 ms at `MAX_AFFECTED` = 2,000 and 299 ms with 4,000 candidates. Deep 4-5-level cascades with thousands of facts per level were not measured, and the read side has no cap. |
| B7 | Low priority | `engram/remember_episode` tail scan; `engram/entities_page` and `entity_duplicate_names` (migration only); `view/scope_lookup` (Label Scan of all Scopes, live); `view/step_agents`; `staleness/suspect_ids` (an arbitrary 5,000-fact sample is taken before ranking by impact); `staleness/docs_to_update`; `demo/ablation_targets` (documented). |

## 3. Simplification candidates

Ordered by file length × confidence that the change is safe.

**Recommended:**
1. **Generate the 12-hop cascade** for `forget_source` (79 lines), `quarantine` (81) and `release_quarantine` (66) from `scripts/gen_impact_queries.py`. Today these are three hand copies of the same 48 lines. The generator already emits this prefix for `impact_*`. Confidence about 95%: it is pure text generation, and the result can be diffed against the current files.
2. **`quarantine` tail as `CALL` subqueries** (P1). This is a fix and a simplification at once, measured equivalent.
3. **`why_derived_level` bind-first** (P2).
4. **`engram/recall_hop_facts` pattern predicate** (`WHERE (:Scope {id:$scope_id})-[:INHERITS*0..3]->(gs)`). This fixes C2 and drops the post-DISTINCT var-length MATCH. Verified live by the engram subagent.
5. **Generate `view/subgraph` (121 lines), `view/inventory_edges` (75), `view/inventory_nodes` (41), `view/inventory_keys` (40) and the 16 lines of `audit/record_tool_call`** from one label/type list.
   - Their length is inherent: one index-bound branch per label (plan-shape 6b).
   - Collapsing them by hand would turn them into All Node Scans.
   - Generation removes five hand-synced lists. It is high-confidence but low urgency, because tests already keep the lists in sync.
6. **Small, safe edits:**
   - `view/scope_lookup`: two index-seek branches instead of the `OR` label scan.
   - `staleness/docs_to_update` L10-12: two WITHs become one `WITH … WHERE`.
   - `lineage/node_info` and `existing_ids`: `UNION` → `UNION ALL`.
   - `engram/recall_keywords`: drop the redundant `DISTINCT`.

**Technically shorter, but riskier to touch. Do not do these without a plan test and a full-fixture run:**
- `lineage/why_edges` (109 lines → about 60 via `CALL { … UNION … }`). The subagent's own confidence is about 55%.
- `engram/assert_fact` (122 lines). Using one ASSERTED_BY comprehension for both `closing` and `clashing` (L77-88) was only checked on a 3-fact fixture. This is the most trap-dense write in the repo; fix C3 in Python instead.
- `staleness/mark_changed` (93 lines). The duplicated CodeAnchor MERGE (L70-74 and L85-89) is the required mutually exclusive form of quirk 6, not redundancy. Only the 5-level unroll could be generated, and only together with a decision about cascade depth (see clarity below).
- `engram/recall` / `recall_hop_facts`: drop the final `ABOUT` and `IN_SCOPE` re-MATCHes. It is medium-risk because these are on the hot recall path.
- `relay/complete_task` + `fail_task` merged into one parameterised query. It would save 25 lines, but the query name is recorded in `ToolCall.query_name`. Optional.

## 4. Clarity: stale or incorrect headers and docs

- **One undecided rule, cascade depth.** `staleness/mark_changed` L8 says it expands "as lineage/forget_source does", and `activation/restore` checks taint with `*1..5`. But forget, quarantine and impact now go up to 12 hops (default 8). As a result, a fact 6-8 derivations away from a changed file is not marked suspect, even though forgetting that file would reach it. `PLEXUS_REPORT.md` L224 still says "five fixed one-hop levels". The three depths should be one stated decision.
- Header states something the query doesn't do:
  - `lineage/link_derived` L6 says `DERIVED_FROM*1..5`.
  - `lineage/why_derived_level` claims an index seek (P2).
  - `engram/recall_entities` and `recall_predicates` claim a WHERE row-drop that did not reproduce. `recall_predicates` also claims "input order", which is false, and "no rows for a missing scope", but it returns one row with fan 0.
  - `engram/assert_fact` L48-49 still has a stale "Lineage tail" note.
- Header leaves something out:
  - `activation/entity_fan` gives zero rows when the entity has no active fact, which the header doesn't say. Its fan is also global, while recall's fan covers only the searched scopes.
  - `view/maybe_duplicates` says "at most 5" per fact. That cap is enforced when the facts are written, not by this query.
  - `relay/create_tasks` doesn't say that `$ext_dep_ids` must be de-duplicated.
  - `relay/handoff` and `record_decision` silently ignore an unknown non-empty `step_id`.
  - `demo/ablation_targets` says "the reach of forget_source", but forget_source's reach is no longer 1..5 hops.
- Semantics worth one line in the header:
  - `lineage/quarantine`'s blast radius leaves out facts already quarantined through another source.
  - `reads_total` counts (step, fact) pairs, while `impact_*.steps_total` counts distinct steps.
  - `staleness/source_by_uri` uses `LIMIT 1` without `ORDER BY`.
  - `relay/task_status` builds two aligned `collect`s.

## 5. Files reviewed and found clean

These files have no correctness, performance or boundedness finding. Some have a clarity or simplification note in their bucket report.

| Bucket | Clean files |
|---|---|
| activation (7) | entity_fan, novelty, pin, restore, scope_facts, suspect_reason, sweep_apply |
| audit (1) | record_tool_call |
| crucible (4) | l5_add_reads, l5_real_facts, list_tasks, strip_edges |
| demo (2) | ablation_reset_tasks, ablation_task_deps |
| engram (15) | assert_relation, backfill_entity_keys, best_procedure, confirm_duplicate, duplicate_pair, fact_history, find_entity_exact, find_entity_fulltext, find_entity_vector, log_procedure_run, missing_refs, recall_keywords, reject_duplicate, split_duplicate, start_session |
| lineage (10) | as_of, create_source, discard_step, existing_ids, impact_source, node_info, release_quarantine, who_knew, why_edges, why_recalled |
| relay (12) | agent_exists, claim_next_task, dependents_of, existing_artifacts, existing_tasks, heartbeat, missing_refs, ready_tasks, register_agent, reopen_task, task_status, verify_artifact |
| schema (5) | fulltext, indexes, list_constraints, list_indexes, vector |
| staleness (11) | anchor_mismatch, backdate, backdate_point, fact_for_verify, facts_to_verify, mark_degraded, set_review_date, source_by_uri, tracked_paths, upsert_anchor, verify_confirm |
| view (12) | flow, indexes, inventory_edges, inventory_edges_scan, inventory_keys, inventory_memory, inventory_nodes, inventory_nodes_scan, labels, maybe_duplicates, relationship_types, subgraph |

**Totals.** 79 files are clean. The other 32 are:
- 6 with a correctness finding (§1);
- 8 with a confirmed performance bug (§2a);
- 3 with the suspected empty-list scan (§2a);
- 15 with a boundedness risk only (§2b).

**Traps checked live and not reproduced:**
- multiple pattern comprehensions in one projection: `recall`, `fact_history`, `duplicate_pair`, `as_of`, `who_knew`, `why_recalled`, `facts_to_verify`, `activation`;
- `WHERE` on an OPTIONAL MATCH after an aggregation: `missing_refs`, `create_tasks`, `handoff`, `link_step`, `link_derived`, `as_of`, `mark_changed` (cover path), `subgraph`;
- a zero-row aggregation dropping the writes: `assert_fact`, `create_scope`, the three cascades;
- a double MERGE of the same TOUCHED edge in `mark_changed`;
- the OPTIONAL MATCH dependency count in `claim_next_task`.

The skills' warnings are real, but this codebase already works around them in nearly every place.

## 6. What I'm not confident about

- **S1 (`relates_level`) is suspected only.** Nobody reproduced the hub-starvation case. It could be harmless if the caller's frontier is small, or real on hub-heavy graphs.
- **P3's six confirmed files were profiled on synthetic graphs** with 3,000-20,000 nodes. I measured record counts, which are deterministic, and one latency, `link_step`. I did not measure the production-size latency, and I did not check how often each caller actually passes an empty list. That frequency is inferred from the callers: `link_step` from a recall, `complete_task` without artifacts.
- **The three suspected empty-list sites** (`record_recall`, `link_derived`, `create_scope`) were not profiled.
- **Several proposed fixes are untested.** The C1 rewrite of `artifacts_ok` (a pattern predicate inside a comprehension), the C3 sort and the P3 UNWIND rewrite were not run. The only fixes run live are the P1 `CALL` rewrite, the P2 bind-first rewrite and the C2 pattern predicate, all by the subagents.
- **C1 has two possible fixes.** Restricting to done tasks and counting distinct artifacts is my reading of the header. The code's broader count may be what was meant, and then only the header and docs are wrong. Either way the multi-path counting (one artifact counted twice) looks unintended.
- **I don't know how C1 interacts with the L5b numbers.** I did not check whether the L5b fixtures contain verified artifacts or VERIFIED_BY edges at all. They probably don't, so C1 and `BRANCH_REVIEW.md` finding 1 likely leave the published numbers unchanged, but that is not verified.
- **The subagents' "clean" verdicts rest on small fixtures.** The engram subagent, for example, used 4 entities and 4 scopes. A clean verdict means no trap reproduced and nothing suspicious was found by reading. It does not mean the file was proven correct at scale.

---

## 7. Fixes applied (branch `feature/neuro-memory-research`, after HEAD `edf9a91`)

Every CONFIRMED finding above and the two BRANCH_REVIEW findings were fixed, each behind a regression test written first
(RED on the old query, then GREEN). The §3 simplifications (cascade / view generation, `why_edges`, `mark_changed`,
complete/fail merge) were left alone; S1 got a header note only. Full suite after the fixes: 1,627 passed, 1 skipped;
`scripts/verify_readme.py` 313 checks passed; the MCP tool surface did not change (no snapshot update). Benchmarks re-run
with a pre-registration (`docs/BASELINE.md` "Audit fixes re-run"): **no published quality number moved**; details there.

| # | Fixed | How | Test (RED → GREEN) | Before → after |
|---|---|---|---|---|
| C1 | yes | `activation/activation` returns `verified_artifacts` (ids of the independently verified artifacts FOR the decision's *done* tasks, one per VERIFIED_BY path); `salience_of` counts them DISTINCT as `artifacts_ok`; the L5b SQL-arm export mirrors it | `tests/activation/test_salience.py::test_artifacts_ok_counts_distinct_verified_artifacts_of_done_tasks_only` | audit fixture (x1 on a done task verified twice + x2 on an open task): 3 → 1 |
| C2 | yes | `engram/recall_hop_facts`: the scope test is the pattern predicate `WHERE (:Scope {id:$scope_id})-[:INHERITS*0..3]->(gs)` (the reviewer's fix B) | `tests/integration/test_audit_recall_hop_facts.py` (3 tests) | diamond team→org, team→proj→org, `per_entity` 2: `[g1, g1]` → `[g1, p1]`; 10: `[g1, g1, p1, t1]` → `[g1, p1, t1]` |
| C3 | yes, **not in Python** | the cap and the `DUPLICATES_MAYBE` writes are inside the one statement, so the caller cannot sort first and passing a larger cap would break `MAYBE_CAP`; smallest in-query change instead: one `WITH … ORDER BY cosine` on the candidate rows before `collect(f)`, so `cur` → `keyed` → `soft` are nearest-first and `[0..$maybe_cap]` keeps the nearest (row count unchanged, no zero-row guard needed) | `tests/integration/test_audit_assert_fact_soft.py` (3 tests) | far/mid/near, cap 1: `[far]` → `[near]`; cap 2: `[far, mid]` → `[near, mid]`; edges match |
| C4 | yes | `scripts/gen_impact_queries.py` `[src] + reach`; `impact_fact.cypher` regenerated | `tests/lineage/test_audit_impact_fact_root.py` (2) | `impact_fact(F1, limit=1)`: `['F2']`/`['F3']` (root dropped) → `['F1']`, truncated |
| C5 | yes | `record_step`: `CASE WHEN can THEN last.id ELSE null END AS previous_id` | `tests/lineage/test_audit_record_step_previous.py` | repeat n=2: `'x2'` → null; refused n=0: `'x2'` → null; fresh n=3: `'x2'` |
| BR-1 | yes | `activation/service.py`: salience protection gated on `st.additive`; SQL arm `:additive` param; D-013 amendment 2; `forgetting.md` | `test_salience.py::test_mult_mode_with_salience_inputs_is_exactly_d012` + the pinned test flipped | mult: salience 0.86 fact `protected` → not protected (add: still protected) |
| BR-2 | yes | `rank.rerank` add branch calls `score.score()`; `Ranked` fields unchanged | `test_rank_d013.py::test_add_mode_score_is_score_dot_score_on_the_production_path` (spy: 1 call per row, score equal) | identity (the two formulas agreed) |
| P1 | yes | `quarantine` tail = three `CALL {}` subqueries (as prototyped; results byte-equal to the old query on the fixtures) | `tests/lineage/test_audit_quarantine_tail.py` (5) | reader+decision+handoff per fact, depth 8, medians of 3: old 600 facts 415 ms, 1,200 facts 2,573 ms, **2,500 facts: timeout (>10 s)**; new 1,500 facts 80 ms, **2,500: 154 ms, 5,000: 461 ms** |
| B1 | yes | `forget_source` tail = two `CALL {}` subqueries | `tests/lineage/test_audit_forget_tail.py` (5) | 1,200: 131 → 68 ms; 2,500: 482 → 170 ms; **5,000: 2,025 → 476 ms** |
| P2 | yes | `why_derived_level`: Fact bound first in all four branches; header fixed | `tests/lineage/test_audit_why_level_plan.py` (3) | 1-element frontier over 5,000 unrelated DERIVED_FROM edges + 2,000 Episode chains: **max records 7,002 → 5** (branches 3–4 scanned too: 2,001 each); 11.1 → 3.2 ms |
| P3 | yes, 9 files | `UNWIND CASE WHEN size($l)=0 THEN [''] ELSE $l END AS k OPTIONAL MATCH (x:L {id: k})`, grouping keys kept: `link_step`, `complete_task`, `fail_task`, `create_tasks` (`$ext_dep_ids` only; `$ids` is never empty), `handoff`, `record_decision`; the three suspected sites **all reproduced** under PROFILE and were fixed: `record_recall` (3,000), `link_derived` (3 × 3,000), `create_scope` (3,000; the root-scope case) | `tests/integration/test_p3_empty_list_plans.py` (32: 9 empty-list PROFILE, 9 non-empty seek, 14 behaviour) | index-scan records **~3,000 → 0** per label (3,000-node fixtures); `link_step` with empty `wrote_ids` on 20,000 Fact / 2,000 Task: median 7.2 → 0.38 ms |
| B2 | documented, not rewritten | measured with the production index set: the 6.0.2 seek applies `status` and `valid_to` together with `predicate`, so the history is **not** read (2,000 superseded + 1,500 expired: 0 index records; 700 = the current facts with that predicate across scopes; 1.4 ms). The residual is cross-scope current facts + one `IN_SCOPE` hop each; the scope is an edge, so no single-property index can absorb it. Header rewritten (also: no "input order", a missing scope gives fan-0 rows, the WHERE-drop claim softened); D-013 amendment 2 | `tests/integration/test_audit_recall_predicates_plan.py` (2) pins "history not read" | — |
| S1 | note only | `relates_level` header | — | — |

Headers fixed while there (§4): `link_derived` (`*1..5` → level-wise up to `$depth`), `why_derived_level` (index-seek claim),
`create_tasks` (`$ext_dep_ids` de-duplicated), `handoff` / `record_decision` (unknown non-empty `step_id` is best-effort),
`quarantine` (blast radius = facts changed by this call; `reads_total` counts pairs), `forget_source` (same), `assert_fact`
(stale "Lineage tail" note replaced by the nearest-first note), `recall_predicates` (above), `activation` (returns),
`recall_hop_facts` (pattern predicate), `PLEXUS_REPORT.md` §8 row ("five fixed one-hop levels" → twelve depth-gated).
`docs/queries.md` rows updated for every changed description.

Timings are medians of ≥ 3 runs on Docker Desktop (noisy, 2× swings); record counts are PROFILE `records_produced` and are
deterministic. P1/B1 record counts were not captured (the tests assert completion time and result equality, and a plan-text
guard that the fact list is no longer a grouping key).
