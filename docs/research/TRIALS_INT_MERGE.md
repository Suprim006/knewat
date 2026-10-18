# trials-int: merge of `p12` into main's tip

Branch `trials-int` started at main's tip `1ddeb13` (D-013 pattern separation, the Cypher audit fixes C1-C5, P3 empty-list
fixes, quarantine / forget_source CALL tails). `p12` forked at `f96df06` (20 commits: recall finds long-horizon facts, step
`WROTE` folded into the task statements, `verify_fact` degraded marker, `apply_schema` retry, compact recall hits, compact
tool schemas, toolsets, the L8 harness). `git merge --no-ff p12` gave 13 conflicted files. This note lists what each side
changed in each one and how it was resolved. **The owner reviews every `.cypher` change: they are called out below.**

Nothing was merged into `main`, nothing was pushed.

## 1. Where the two designs overlap

Both sides rebuilt the same path (`Engram.recall`):

| | main (D-013) | p12 |
|---|---|---|
| candidates | `2k` (re-ranking) or `k` nearest + keyword ids + the named entities' own facts | pool `max(3k, 60)` <= 150, every keyword hit survives both `LIMIT`s, scope `all` |
| relevance | `1 - rank` | `fused` = cosine mixed with an IDF-weighted query-word coverage (`fuse_scores`) |
| sibling boost | in Cypher, scaled by the seed entity's **fan** (`damp`) | re-applied in **Python** to siblings of the best seeds only (`_sibling_boost`), because with a big pool nearly every candidate is a seed |
| return | `recall_with_meta` -> `(rows, meta)` | `recall_page` -> `(rows, page)` |
| MCP tool | records `entities` + `separation` in `record_recall` | scope `all`, `detail='compact'`, `truncated` |

Resolution rule: keep every mechanism of both, in the order p12's pool/fusion -> main's separation -> rerank.
Concretely, `recall_with_meta(..., all_scopes=False)` is the one implementation; `recall` returns its rows, `recall_page`
returns `(rows, {truncated, omitted_by_budget, more_available, candidates})` (the same four keys are also in the meta).

**The one place the two could not be dropped in side by side:** p12 moves the sibling boost into Python and overwrites
`rank`, which would have silently thrown main's fan damping away. The Cypher now also returns the entity's damp factor per
row (`damp`, 1.0 when `$damp` is false) and `_sibling_boost` scales the boost by it. Test:
`test_the_python_sibling_boost_keeps_the_fan_damping`.

**Scope `all` and separation.** p12's default scope is now `all` (no scope filter). Main's two fan reads
(`engram/recall_entities`, `engram/recall_predicates`) count facts "in the searched scopes", so they gained `$all`
(same one-line `WHERE $all OR fs.id IN sids`), otherwise the default recall would have counted fans in `global` only.
`_entity_facts` (-> `recall_hop_facts`) passes `all` too.

## 2. Conflicted files

### Cypher (owner review)

* **`queries/engram/recall.cypher`** - main: params `damp`, `smax`; `fan_e` by one pattern comprehension, boost `* damp`.
  p12: params `all`, `lim` (was `k`); keyword rows carry `kw` and are ordered first; both `LIMIT`s are `$lim`; columns `kw`,
  `sib_of`. Merged: both parameter sets; the `ORDER BY kw DESC, score ASC LIMIT $lim` cut comes first, then `fan_e` / `damp`
  are computed on the rows that survive it (so the fan comprehension runs per surviving row, up to `$lim`); `damp` is carried
  in the candidate maps and returned as a column (`max(c.damp)`). Header updated. Plan test `test_p5_plans` (params
  `damp: True, all: True, lim: 60`) passes.
* **`queries/engram/recall_hop_facts.cypher`** - main (audit C2): the scope test is a pattern predicate, because a post-
  `DISTINCT` `MATCH (:Scope)-[:INHERITS*0..3]->(gs)` emitted one row per path on a diamond. p12: `$all`, via an OPTIONAL
  MATCH + `WITH DISTINCT ... WHERE $all OR inscope`. Merged: `WHERE $all OR (:Scope {id: $scope_id})-[:INHERITS*0..3]->(gs)`
  (one boolean per fact, so the C2 fix and `$all` are the same line; the `DISTINCT` is no longer needed). Both
  `test_audit_recall_hop_facts` (diamond) and the p12 `$all` test in `test_p9b_relations` pass.
* **`queries/engram/relates_level.cypher`** - main: only an S1 header note (suspected hub starvation, not changed). p12:
  OPTIONAL MATCH + `$all`. Merged: p12's query, main's S1 note kept.
* **`queries/relay/complete_task.cypher`, `fail_task.cypher`** - main (P3): `UNWIND CASE WHEN size($artifact_ids)=0 ...`
  form so an empty list does not scan the Artifact id index. p12: `OPTIONAL MATCH (stp:Step {id: $step_id})` and a
  `FOREACH ... CREATE (sw)-[:WROTE]->(t)` so the Step edge is in the same statement. Merged: the Step seek goes **before**
  the UNWIND (`stp` is carried in `WITH a, t, stp, count(e)`), the artifact guard keeps main's seek form, the `WROTE`
  `FOREACH` is p12's. Still one bounded statement. `test_p3_empty_list_plans` now passes `step_id: ""`.
* **`queries/relay/create_tasks.cypher`** - main: `ext_dep_ids` de-duplicated and read with the UNWIND form; p12: `step_id`
  and a `FOREACH ... WROTE` per created task. The bodies merged cleanly; only the `// params:` line conflicted (both added).
* **Non-conflicting but changed for the merge:** `engram/recall_entities.cypher`, `engram/recall_predicates.cypher`
  (`$all`, see above).

### Python

* **`src/plexus/engram/service.py`** - constants (`MAX_KEYWORDS` 12 from p12 + main's `RECALL_ENTITIES/PREDICATES`),
  `recall` / `recall_page` / `recall_with_meta`, `_resolve_entities`, `_entity_facts`, `_resolve_predicates`,
  `_fetch_candidates`, `_sibling_boost` (damp). Defaults are p12's (`k` 20, 6,000 chars). Order inside
  `recall_with_meta`: resolve entities -> keyword ids (pool) -> named entities' facts -> `engram/recall` (pool + `damp`)
  -> `_sibling_boost` -> merge the named entities' facts (they keep rank = own distance, as in main) -> `fuse_scores` ->
  predicates -> `rerank` (or fused sort when both switches are off) -> hops -> budget -> page keys.
* **`src/plexus/activation/rank.py`** - main: additive score, separation, lures, `_bypass_text` (`PLEXUS_KW_BYPASS`, default
  `fact`). p12: relevance = `fused` when the row has it; bypass over entity + predicate + value. Merged: main's `rerank`,
  with `rels` taken from `fused` when present (so bands, lures and the additive score all see the fused relevance). p12's
  bypass text is main's `kw_bypass = fact` default, so nothing was added for it.
* **`src/plexus/mcp/tools_engram.py`** - merged: p12's scope `all` / `detail` / `truncated`, main's `recall_with_meta` +
  `record_recall(entities=, separation=)`; `compact_hit` drops the D-013 ranking inputs (`entity_match`, `predicate_match`,
  `sep`, `salience`) and an empty `lures` (a non-empty `lures` stays: it is a look-alike warning), otherwise the compact hit
  would have grown by five fields. `detail='full'` keeps them.

### Docs / tests

* **`docs/queries.md`** - rows from both sides kept (p12's two search_text rows and `$all` notes, main's entities /
  predicates rows, the C2 wording); `engram/recall` row gets the `damp` sentence. README query-file count 111 -> 114
  (`verify_readme.py` checks it: 108 base + 3 main + 3 p12).
* **`tests/activation/test_recall_off.py`** - main: pass `separation=False`, env `PLEXUS_RECALL_SEPARATION=off`. p12:
  `lexical_weight = 0`, `_cut_ties`, a golden edit. Merged: all of it (both switches off **and** lexical 0 = the old order).
* **`tests/integration/test_engram_recall_scale.py`** - merged: `separation=False` plus p12's pool assertion.
* **`tests/unit/test_engram_util.py`** - both new ro query names.
* Test adjustments forced by the merge (no assertion weakened): direct query calls gained the new params (`all`, `step_id`,
  `search_text`) in `test_audit_recall_hop_facts`, `test_audit_recall_predicates_plan`, `test_audit_assert_fact_soft`,
  `test_p3_empty_list_plans`, `test_recall_separation`; `test_recall_separation` pins D-013 terms against an exact cosine
  relevance, so its autouse fixture sets `lexical_weight = 0` and the "vector fetch misses the named entity" test shrinks the
  pool (`MIN_POOL=2`) and turns the keyword channel off (p12's keyword channel now also matches entity names, so the
  premise "only the vector side can miss it" no longer holds with the default pool of 60). New tests:
  `test_the_python_sibling_boost_keeps_the_fan_damping`, `test_defaults_lexical_fusion_and_separation_together`,
  `test_all_scopes_counts_the_fans_over_every_scope`.
* `tests/mcp/snapshots/tools.json` regenerated (only the `detail` description differs from p12's snapshot: "the ranking
  terms").

## 3. Found after the merge commit (separate commits on `trials-int`)

* **`f5881c6` compact hits hid the D-013 inputs but not `lures`.** The first bench run returned 18k chars per recall
  instead of p12's 5.3k: with separation on, each hit carried `lures` (the ids of other candidates with the same predicate
  about another entity at nearly the same relevance), and the 20 sprint facts of L8 are exactly that - about 20 ids a hit.
  `lures` is now full-only like the other ranking inputs (`why_recalled` still has it); the compact key set is pinned by a
  test. Re-run: 5,340 / 5,776 chars (p12: 5,344 / 5,772).
* **`af8f70d` L5b / hub harness pin the lexical fusion off.** `test_forgetting_sql_arm_toy` (main) failed in the first full
  suite: Plexus' retrieval-only mode and the SQL arm agreed on the top-1 for 12 of 14 probes, because the SQL arm mirrors
  the cosine relevance and Plexus now mixes in p12's lexical score. The harness sets `eng.lexical_weight = 0.0` so it
  measures what `BASELINE.md` registered (D-013 against SQL). The L6-C `P-product` / `P-flat` arms ("`Engram.recall` as
  shipped") were left as shipped, i.e. with the lexical fusion and the pool of p12.

## 4. No-LLM recall bench (`l8_trialsint/recall_bench-trialsint-core.json`)

`PLEXUS_TOOLSET=core python -m plexus.crucible.l8.recall_bench --port 6372 --label trialsint-core --out
demo_data/crucible/l8_trialsint` (5 seeds, hash embedder, the real tool layer through an in-process server scoped to
`core`; replays the recorded Round A queries; no `claude -p`, no network, $0; 0 tool errors).

| | p12 (`l8_p12ts/recall_bench-p12ts-core.json`, `d6d30da`) | trials-int (`f5881c6`) |
|---|---|---|
| needed history fact found per task: S07 billing cycle | 5/5 | 5/5 |
| S13 API-key header | 5/5 | 5/5 |
| S20 release channel | 1/1 | 1/1 |
| canonical (S01-S20 x 5 facts x named + paraphrase) | 1000/1000 | 1000/1000 |
| replay, recalls that found their target | 29/36 | 28/36 |
| mean response chars (replay / canonical) | 5,344 / 5,772 | 5,340 / 5,776 |

The one replay call that differs is seed 20261020, `"Bolt Billing API billing_cycle"` with `k=15`: the S07 fact was
inside the 15 returned on p12 and outside on trials-int. The query names no sprint, so the 20 `billing_cycle` facts
(S01-S20) should look alike to it and which 15 come back is decided by near-ties (p12's own round 1 had 28/36 for the same
reason). It is not a regression in the needed-fact metrics, which are the ones p12 reported as its acceptance numbers.

## 5. Gate (`trials-int`, FalkorDB 6.0.2 on slot 72)

* `ruff check .` and `ruff format --check .`: clean. `scripts/verify_readme.py`: 313 checks passed, 0 failed (query-file
  count 114, 45 tools). Contract snapshot regenerated and committed before the suite.
* Full suite after the last code commit (`af8f70d`): **1698 passed, 1 skipped** (p12 reported 1580 + 1 skipped). The first
  full run (before `af8f70d`) was 1697 passed, 1 failed (`test_forgetting_sql_arm_toy`, see 3).
* `plexus-view` was not run: `docs/view-api.schema.json` is unchanged by this merge.

## 6. Things for the owner to look at

1. **Lexical fusion and the entity/predicate cues now both reward query words in the entity name / predicate.** The
   lexical score (p12) counts them as query-word coverage and the D-013 context term (main) adds `w * (S - ln fan)` for the
   same match. Neither test suite covers the combination beyond `test_defaults_lexical_fusion_and_separation_together`. If
   this is double counting, the knob is `PLEXUS_RECALL_LEXICAL_WEIGHT=0` (restores main's relevance exactly).
2. **Published L5b / L6 numbers were measured on main's candidate pool and relevance.** The merged default path uses p12's
   pool and fused relevance. The L5b / hub harness now pins the lexical fusion off (see 3), but the candidate pool (60-150
   instead of `2k`) is not switchable, so the L5b numbers are not re-verified on `trials-int` (not run: not part of this
   task); the L6-C product arms run as shipped.
3. `engram/recall` now computes `fan_e` for up to `$lim` rows (<= 150 + keyword hits) instead of `k`; it is entity-first and
   the plan test passes, but it is a per-row read of an entity's `ABOUT` degree - worth a PROFILE on a tenant with a
   thousand-fact hub entity.
4. `recall` with scope `all` and `as_of` is unchanged from p12 (separation is off for `as_of`).

### Status after the recall-check (branch `recall-check`, from `trials-int` `76da7d7`; `docs/BASELINE.md` "Recall-check")

1. **Double counting:** measured; the default is now `PLEXUS_RECALL_LEXICAL_WEIGHT=0` (D-013 amendment 3). With the fusion on, L5b lost a critical probe (N = 15) and the noise share rose 8-19 points over fusion off.
2. **Published numbers on the merged build:** recall@1 / recall@5 / critical loss / hub reproduce; the L5b noise share moved (32.3 / 41.6 / 33.3% against 20-22% on main, same harness, same day), partly the fusion, the rest not attributed to a single switch; L6-C product-arm `hit_any` is 23/9/0 with the fusion off (= main's tip today; the published 11/6/1 predates main's predicate cue), 13/3/1 with it on. Neither was hidden or tuned.
3. **`fan_e` on a hub:** confirmed unbounded per row (61,295 records at 1,000 facts, 305,295 at 5,000), fixed (1,060 / 5,060), test added.
