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

## 3. Things for the owner to look at

1. **Lexical fusion and the entity/predicate cues now both reward query words in the entity name / predicate.** The
   lexical score (p12) counts them as query-word coverage and the D-013 context term (main) adds `w * (S - ln fan)` for the
   same match. Neither test suite covers the combination beyond `test_defaults_lexical_fusion_and_separation_together`. If
   this is double counting, the knob is `PLEXUS_RECALL_LEXICAL_WEIGHT=0` (restores main's relevance exactly).
2. **Published L5b / L6 numbers were measured on main's candidate pool and relevance.** The merged default path uses p12's
   pool and fused relevance, so those numbers are not re-verified on `trials-int` (not run: they are not part of this
   task). Both new knobs have an off switch (`PLEXUS_RECALL_LEXICAL_WEIGHT=0`; the pool is not switchable).
3. `engram/recall` now computes `fan_e` for up to `$lim` rows (<= 150 + keyword hits) instead of `k`; it is entity-first and
   the plan test passes, but it is a per-row read of an entity's `ABOUT` degree - worth a PROFILE on a tenant with a
   thousand-fact hub entity.
4. `recall` with scope `all` and `as_of` is unchanged from p12 (separation is off for `as_of`).
