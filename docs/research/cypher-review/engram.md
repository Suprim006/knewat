# Cypher review: `plexus/queries/engram/` (26 files, 591 lines)

Read-only review on branch `feature/neuro-memory-research`. No query, Python or other file was changed.
Method: read every file against the three FalkorDB skills (silent-wrong-answers, big-write quirks, plan-shape) and
`FALKORDB_REFERENCE.md` §2 / `CLAUDE.md` §6-7; traced each caller in `plexus/src/plexus/engram/*.py` for params and
caller-side caps; checked `docs/DECISIONS.md` D-013 and `docs/PLEXUS_REPORT.md` §9.3 so documented limits are not
reported as new. Live checks ran on plexus-db-13 in throw-away graphs `audit_engram_*` (all deleted; `GRAPH.LIST` shows none left).
Fixtures were small (4 entities, 4 scopes incl. a diamond), so plan/volume claims are by reading and are labelled so.

## SUMMARY

| Severity | Count | Items |
|---|---|---|
| CONFIRMED BUG | 2 | `recall_hop_facts` duplicate rows over a diamond scope graph; `assert_fact` `soft` list is not nearest-first |
| SUSPECTED BUG | 1 | `relates_level` LIMIT is global per direction, so one hub entity can starve the rest of the frontier (SUSPECTED, NOT CONFIRMED live) |
| BOUNDEDNESS RISK | 7 | `recall_predicates` (graph-wide per predicate), `recall` hub fan-out, `recall_hop_facts` hub fan-out, `recall_entities` hub fan-out, `resolve_entity` full-text hits on the serialised write path, `remember_episode` tail scan, `entities_page` / `entity_duplicate_names` (migration only) |
| SIMPLIFICATION | 5 | `assert_fact` one comprehension instead of two; `recall_hop_facts` pattern predicate + no re-MATCH; `recall` re-MATCHes; `recall_keywords` redundant DISTINCT; `recall_entities`/`recall_predicates` redundant CASE (low priority) |
| CLARITY | 5 | `assert_fact` stale "Lineage tail" note; `recall_predicates` "input order" claim false; `recall_entities` / `recall_predicates` header claims a WHERE-drop that did not reproduce; `recall` `fan_e` is defined differently from `recall_entities` fan; `create_scope` cycle note |
| CLEAN | 20 of 26 files have no correctness finding (some carry CLARITY/low-risk notes) | list at end; files with findings: `assert_fact`, `recall_hop_facts`, `recall_predicates`, `recall_entities`, `recall`, `relates_level` |

Headline: the three files this branch added or changed (`recall`, `recall_entities`, `recall_predicates`) have **no correctness bug** that I could
reproduce. All three recall paths returned the right rows for a single-fact entity, a diamond scope graph, an entity
with only out-of-scope facts, an expired fact and a predicate with no facts. The two confirmed bugs are in older
files. The branch's own risks are boundedness (hub fan-out, graph-wide predicate seek) and two stale header claims.

Traps from the skills that I checked and found **not present**: multiple pattern comprehensions over the same relationship in one projection
(`recall` has three over DERIVED_FROM / ASSERTED_BY / DUPLICATES_MAYBE, `fact_history` three over ASSERTED_BY / SUPERSEDES / CONTRADICTS,
`duplicate_pair` three over DUPLICATES_MAYBE / DUPLICATES / SUPERSEDES; each relationship type is read once, and live runs with
every edge present returned all lists non-empty); MERGE before OPTIONAL MATCH (`log_procedure_run` has a WITH between them, so it is accepted);
zero-row aggregation killing a write (`assert_fact` and `create_scope` are safe, see the sections);
`*1..N` path enumeration used for membership (all `INHERITS*0..3` uses are collected `DISTINCT`, except `recall_hop_facts`, see below).

---

## assert_fact.cypher (122 lines; header 1-49, body 50-122)

**CONFIRMED BUG (lines 80-82, header lines 7 and 23): `soft` is not "nearest first".**
`[sx IN keyed WHERE ... ][0..$maybe_cap]` slices `keyed` in `cur` (storage) order; nothing sorts by `cos`. Only the *cap* makes it matter:
with more current same-`dup_key` facts than `maybe_cap` (`MAYBE_CAP = 5` in `dedup.py`, so it needs 6+ current facts of one entity, predicate and scope, which the
multi-agent CONTRADICTS path can produce), the kept links are arbitrary, not the nearest.
Live repro (maybe_cos 0.9, cap 1 then cap 2; current facts `far` cos 0.638, `mid` 0.175, `near` ~0.005 created in that order):
```
cap=1 -> maybe: [far(0.638)]            # expected [near]
cap=2 -> maybe: [far(0.638), mid(0.175)] # expected [near, mid]
```
The stored `DUPLICATES_MAYBE` edges and the `maybe` return value both follow this order, so the "soft duplicate" the user is shown may not be the closest.
Fix sketch (behaviour-preserving apart from the order; confidence medium-high; untested): sort before slicing. FalkorDB has no list sort, so do it in the
row domain: after the `keyed` WITH, `UNWIND keyed AS sx WITH ..., sx WHERE dup IS NULL AND (sx.cos <= $maybe_cos OR sx.jac >= $maybe_jac) WITH ..., sx ORDER BY sx.cos ASC LIMIT $maybe_cap WITH ..., collect(sx) AS soft`.
Trap it may trip: this puts a grouping `collect` after UNWIND, so with zero soft candidates the row disappears and the whole write (the new fact) is lost. It needs the `UNWIND CASE WHEN size(l)=0 THEN [null] ELSE l END` null-row trick from skill #5. If the caller can sort instead (the cap is only 5), sort in Python and keep the query as is.

**Zero-row aggregation (the bucket's main worry): CLEAN.** The only grouping aggregate is `collect(f)` at line 56 and it is fed by the `MATCH (e),(sc)` row, which exists
whenever the entity and scope exist, so a missing reference gives no row by design (header line 7). I tested the dangerous shape: an entity whose history is all `superseded`
(the `WHERE f.status IN [...]` on the OPTIONAL MATCH at line 55 removes every `f`): the assert still returned a row and wrote the fact. Line 57 is a `WITH ... WHERE`, which is the safe form.
Empty `tok_seq` (value with no word characters, `range(0, -1)` at line 71) also ran without error.

**Other checks, all fine:** lines 77-78 and 86-88 hold the two pattern comprehensions over ASSERTED_BY in separate WITHs as the header says; the live closing/clashing result
matched. `DISTINCT` is not needed for `cur` (one IN_SCOPE edge per fact). Dup tier order, wake of a dormant dup (96-98) and the single-statement WROTE edge are consistent with the header.
No FOREACH merges the same node twice. `0.0` division at line 67 is guarded by `size($tok)+xk.nt = 0`.

**BOUNDEDNESS RISK (low, not new):** `cur` is every current fact of one entity+predicate+scope, with no cap in the query or the caller (`service.py` ~355). It is entity-anchored (header 38-41), so it is
O(current facts of that triple), small in practice; contradictions from many agents grow it. Each row costs a cosine distance and an ASSERTED_BY traversal (lines 61-63, 78, 87), inside the per-graph serialised write.

**COMPLEXITY / SIMPLIFICATION.** The statement is 73 lines of body plus 49 of header, and the length is mostly inherent (classify, then write). The redundancy is that the same six-variable carry list
`ag, e, sc, ep, src, stp` is repeated in nine WITHs, and ASSERTED_BY is walked twice (closing at 78, clashing at 87). One concrete change:
```
-- before (77-88): two WITHs, each with its own  [(x)-[:ASSERTED_BY]->(a:Agent) | a.id]
-- after: one pattern comprehension, then filter the maps
WITH ..., [xc IN cur WHERE dup IS NULL OR xc.id <> dup.id
           | {n: xc, mine: all(ac IN [(xc)-[:ASSERTED_BY]->(oc:Agent) | oc.id] WHERE ac = $agent_id)}] AS cm
WITH ..., [x IN cm WHERE $supersede OR x.mine | x.n] AS closing,
          CASE WHEN dup IS NULL THEN [y IN cm WHERE NOT ($supersede OR y.mine) | y.n] ELSE [] END AS clashing
```
Careful: `clashing` must still be computed over all of `cur` when `dup IS NULL` (then the `dup` filter is a no-op, so it is the same set).
I ran the closing/clashing pair in this single-comprehension form against the original on a 3-fact, 2-agent fixture and got identical lists (`closing [t1]`, `clashing [g1,p1]`), but this does not cover the full statement.
Confidence behaviour-preserving: medium-high. Traps it might trip: skill "WITH list-comprehension next to pattern comprehension" (type mismatch `Map vs List`); it removes one of the two same-relationship comprehensions, which is the safer side of the skill's rule. Needs the existing assert_fact suite plus the A/B/A test.

**CLARITY (lines 48-49):** the "Lineage tail ... put `MATCH (st:Step ...)` before the FOREACHes and add `CREATE (st)-[:WROTE]->(nf)`" note is stale: that is already implemented (53, 110, header 36-37). Delete it. The params header matches the body (all 28 `$params` accounted for).

---

## assert_relation.cypher (15 lines)

Clean: one bounded MERGE; the temporary `r.new` flag is set and removed in the same statement, `created` is evaluated before the REMOVE. `$scope_id` is used (the `MATCH (s:Scope)` at line 9 is only the existence guard, matching the header "zero rows = scope missing"). Minor CLARITY: header says "unique per (kind, scope)"; it is unique per (a, b, kind, scope).

## backfill_entity_keys.cypher (9 lines)

Clean: `UNWIND $rows` then an anchored `MATCH (e:Entity {id: row.id})` (single node, so an index seek, not the skill 6c edge-scan trap). Boundedness is by the caller, which sends `BATCH = 200` rows (`migrate.py:33`); the query itself has no guard, which the header states.

## best_procedure.cypher (12 lines)

Clean: the filter on `runs` is a `WITH ... WHERE` after aggregation, the safe form; `LIMIT $limit`. The `MATCH` aggregates every Run of every matching Procedure (grows with runs, inherent to a success rate). Minor CLARITY: a procedure with zero runs is never returned even for `min_runs = 0` (the MATCH requires a Run).

## confirm_duplicate.cypher (29 lines)

Clean: write shape is reads first, one `WITH ... collect(...)`, then FOREACH writes, then the plain SET/CREATE/DELETE. Aggregation keys `n,l,o,sup,reopen` always have input rows, so the writes cannot vanish. Live round trip (a same-agent reword that superseded `w1`): `pair` -> `confirm` returned `reopened: true`, `w1` active/open again and `w2` zero-width; `split_duplicate` restored both. The `OPTIONAL MATCH (o)-[have:ASSERTED_BY]->(ag)` binds `have`, so the unreferenced-alias undercount trap does not apply. Semantic note (not a bug in the code): if the new fact closed several olds, only `o` is reopened (documented by header line 12).

## create_scope.cypher (12 lines)

Clean: `WITH collect(p)` has no grouping key, so over zero rows it still returns one row with `[]`: an empty `inherits` creates the scope (live: returned the row). Duplicate ids in `$inherits` would make `size(parents) = size($inherits)` false and return no row, but the caller dedups with `sorted(set(...))` (`service.py:~276`). `p.id IN $inherits` scans the Scope id index (skill plan-shape #4), harmless at this table size. CLARITY: cycles are not checked (the caller docstring says so); the traversal depth is capped, so only wasted work.

## duplicate_pair.cypher (15 lines)

Clean: three pattern comprehensions, but over three different relationship types with both endpoints bound. Live with a pair that had DUPLICATES_MAYBE, DUPLICATES and SUPERSEDES edges: `linked`, `confirmed` true, `old_reopenable` correctly false. Returns exactly the header columns.

## entities_page.cypher (10 lines)

Clean for correctness. BOUNDEDNESS RISK (migration only, by reading): `WHERE e.id > $after` then `ORDER BY e.id LIMIT` reads the whole indexed id range on every page (skill 6b: no index-ordered scan), so a full migration is O(N^2 / 200) entity reads. Fine for thousands of entities, slow for hundreds of thousands. Also returns the 384-float embedding per row. Not on a request path.

## entity_duplicate_names.cypher (11 lines)

Clean: a deliberate full aggregate over `Entity` (the output is bounded by `LIMIT`, the scan is not). Migration/diagnostic only. The `WHERE n > 1` is after aggregation in a `WITH`, the safe form.

## fact_history.cypher (17 lines)

Clean: entity-anchored, newest `limit` versions kept before the three comprehensions run (header 9-10 is accurate). Live with a fact carrying ASSERTED_BY, SUPERSEDES and CONTRADICTS edges returned all three lists correctly. Final `ORDER BY` on the aliases is valid. The caller supplies `limit`.

## find_entity_exact.cypher (8 lines)

Clean: index seek on `norm_name`, `LIMIT 1`.

## find_entity_fulltext.cypher (9 lines)

Clean: used only by `migrate.py:105` with a `FULLTEXT_CANDIDATES` limit. `queryNodes` returns all matches before `ORDER BY ... LIMIT`; fine for a migration tool. An invalid `q` raises, the same as elsewhere (the recall callers catch `ResponseError`; this caller should confirm it does, not checked).

## find_entity_vector.cypher (8 lines)

Clean: bounded by `$k`; no LIMIT needed. Score is documented as a distance and sorted ASC.

## log_procedure_run.cypher (18 lines)

Clean: the OPTIONAL MATCH on `Task` follows a `WITH ag, p`, so it avoids the MERGE-before-OPTIONAL-MATCH error; `task_id = ''` matches nothing. The MERGE on `(name, task_type)` uses the `task_type` index. Runs accumulate by design (no cap; inherent).

## missing_refs.cypher (11 lines)

Clean: the OPTIONAL MATCH / `count` chain has no WHERE and no grouping list, so it avoids the skill's "chain of OPTIONAL MATCH ... WHERE n = 0" trap. Live over four combinations (all present; episode missing; scope missing and no source; only scope) returned exactly `1/0/1`, `0/1/0`, `1/0/0` as expected.

## recall.cypher (72 lines; header 1-26, body 27-72)  (changed on this branch: +damp/smax, fan_e)

No reproducible correctness bug. Checked live (scopes with a diamond `team -> org, team -> proj -> org`): a single-fact entity returns its seed row with `derived_from`, `asserted_by` and `maybe_dup` all populated (the three RETURN pattern comprehensions work); a `team`-scope recall returns org facts once (no duplicate rows, because `sids` is `collect(DISTINCT ...)` at line 28); keyword-only seeds work; `damp` on and off both run.

**SUSPECTED, NOT CONFIRMED (benign) lines 29-30:** `CALL db.idx.vector.queryNodes ... ` followed by `WITH sids, collect({n: node, s: score}) AS vh`. If the vector index returned zero rows, the grouped `collect` (key `sids`) would produce zero rows and the keyword seeds at 31-33 would be lost. It cannot matter today: the keyword ids are Facts, and any Fact has an embedding, so an empty vector result means there are no Facts. I could not make the vector side empty with a Fact present to test it. Worth a one-line comment, or an `UNWIND CASE ... [null]` guard if Facts without embeddings are ever allowed.

**WHERE after aggregation / MATCH (lines 36-39), the big-write quirk #1:** `WITH ... min(h.s) AS score WHERE f.status ...` followed by `MATCH (f)-[:IN_SCOPE]->(fs) WHERE fs.id IN sids`. That is the shape skill #1 warns about (a WHERE on a MATCH after an aggregation). I did not see it misbehave in the live runs or in the L5 benchmarks; leave it, but it is the first place to look if recall ever loses rows.

**BOUNDEDNESS RISK (known, documented in the header lines 17-20 and tested by `test_p5_plans.py`):** per seed (at most `k`), `fan_e` at line 44 walks every active fact of the entity, and lines 47-53 walk every fact of the entity and compute a cosine distance for each before `[0..$sibs]` caps it. Cost is O(k x entity fan-out), so a hub entity (thousands of facts) makes recall slow. Note the irony: for `damp = true` and fan >= e^smax (50) the boost is 0, yet the query still enumerates the whole hub. Inherent to a vector-less sibling pick; a per-entity cap would need a stored count. The vector side is bounded (`over` <= 512, `MAX_OVER`); the keyword side by `k`; `INHERITS*0..3` is collected once.

**CLARITY (line 44, header 21-24):** `fan_e` counts all `status: 'active'` facts of the entity across **all** scopes and ignores validity/`statuses`, while `recall_entities.fan` counts facts valid at `t`, with `statuses`, in the searched scopes. The header does say "active facts", so it is documented, but the two "fans" feed the same D-013 formula and will disagree for an entity that has facts in other scopes or superseded ones; a reader would assume they are the same.

**SIMPLIFICATION (lines 62-63), confidence medium (behaviour-preserving; untested):** `MATCH (n)-[:ABOUT]->(en)` and `MATCH (n)-[:IN_SCOPE]->(ns)` re-fetch what is already known: every candidate shares the seed's entity `e`, and the scope was bound as `fs` (seeds) or `gs` (siblings). Carry them in the `cands` maps (`ent: e`, `sc: fs`/`gs`) and drop the two MATCHes. Saves two one-hop traversals on at most `k` rows; the risk is the skill #1 quirk when carrying more variables through the aggregation at 59. Low value; skip unless this file is being edited anyway.

**CLARITY (line 66):** `via` is `head(vias)`, i.e. an arbitrary seed when a sibling is reachable from several. Harmless.

## recall_entities.cypher (27 lines)  (new on this branch)

No reproducible correctness bug. Live: entities with in-scope facts get the right fan (`e1` fan 3 in `proj` = proj + inherited org; fan 4 from `team` through the diamond, counted once each); an entity whose only facts are in another scope (`e3`), and an entity whose only fact has expired (`e4`), are both **still returned with fan 0**, as the header promises.

**CLARITY (header 10-13 vs lines 20-26):** the header says "a WHERE on the second OPTIONAL MATCH would drop the entity's row on 6.0.2 when nothing matches, so the scope test yields null inside a CASE". But the code has exactly such a WHERE (line 24: `OPTIONAL MATCH (f)-[:IN_SCOPE]->(fs:Scope) WHERE fs.id IN sids`) *and* the CASE at 25. In my fixtures the WHERE did not drop the row (the e3 and e4 cases above), so either the trap does not apply to this shape or the CASE is dead code that makes the comment misleading. I cannot tell which from small fixtures (I did not test a large graph); the skill ("A WHERE on OPTIONAL MATCH rows also drops the owning row") says it can happen. Keep the CASE (it is harmless and protects against the documented trap), but make the comment match the code, or add a regression test with an out-of-scope-only entity. Same note applies to `recall_predicates`.

**BOUNDEDNESS RISK:** bounded in entities (`LIMIT $limit` at line 19, caller `RECALL_ENTITIES = 5`, applied *before* the fact expansion, which is the right order), but each surviving entity enumerates all its ABOUT edges (lines 20-21), so a hub entity makes every recall that names it O(fan). Same class as `recall`. Documented as fan in the header.

## recall_hop_facts.cypher (31 lines)

**CONFIRMED BUG (lines 15-18): duplicate fact rows when a scope is reachable by two INHERITS paths.**
Line 16 does `WITH DISTINCT e, g0 AS g, gs`, but the `MATCH (:Scope {id:$scope_id})-[:INHERITS*0..3]->(gs)` at line 17 comes *after* the DISTINCT and emits one row per path. A diamond (`team` inherits `org` directly and through `proj`) therefore yields the org facts twice. Live repro (diamond graph, entity `e1` with facts in org/proj/team):
```
per_entity=10 -> [g1, g1, p1, t1]      # g1 (scope org) twice
per_entity=2  -> [g1, g1]              # p1 and t1, the next nearest, are crowded out
```
The same fact is then collected twice into `top` (line 20), so `per_entity` slots are wasted on duplicates. The caller (`relations.py`, `have` set) dedups the output, so no duplicate row reaches the user, but with `HOP_FACTS_PER_ENTITY = 3` an entity with a diamond-scope fact can show 2 distinct facts instead of 3. Diamond scopes are realistic (`create_scope` accepts several parents).
Two fixes, both tested live on the same graph and both returned `[g1, p1, t1]` with the right order: (A) add `WITH DISTINCT e, g` after line 17; or (B), cleaner, replace lines 16-17 with a pattern predicate: `WITH e, g0 AS g, gs WHERE (:Scope {id: $scope_id})-[:INHERITS*0..3]->(gs)` (skill big-write #2 recommends this form; it also stops enumerating paths). Confidence behaviour-preserving apart from removing the duplicates: high for (B) on these fixtures, medium otherwise (the existing hop tests should be re-run).

**SIMPLIFICATION:** line 23 `MATCH (n)-[:IN_SCOPE]->(ns)` re-fetches the scope that `gs` already holds; carry `gs` in the `top` map. The `DISTINCT` on line 16 is then still needed only if (A) is chosen.

**BOUNDEDNESS RISK:** entities are capped by the caller (`HOP_ENTITIES`, <= 20), but per entity the query reads every current fact, runs the scope path test for each one, and computes the cosine distance, then keeps `per_entity` (3) at line 20. Hub entity cost is O(fan). The header says "entity-first", which is correct, but there is no per-entity bound on the read. Documented (header 7-8, recall's header 17-20).

**CLARITY:** the header "returns" omits `maybe_dup` that `recall` has; the Python reader uses `.get("maybe_dup")`, so fine.

## recall_keywords.cypher (19 lines)

Clean for correctness: filters before `LIMIT`, as its header says (lines 14-16 are a plain `WITH ... WHERE` and a `MATCH ... WHERE` on a bound node).
**BOUNDEDNESS RISK (low):** `queryNodes('Fact', $text)` returns every fact that matches any query word (an OR query) before the status/validity/scope filters and the sort; a common word in a large tenant scans all of them. Inherent to the full-text API, no pre-limit is possible.
**SIMPLIFICATION (trivial):** `RETURN DISTINCT` at line 17 is redundant (a fact has one IN_SCOPE edge, so there is one row per node); cosmetic, confidence high.

## recall_predicates.cypher (22 lines)  (new on this branch)

No reproducible correctness bug. Live: `pp` fan 1 (proj) and `color` fan 1, `orgp` 1 (inherited), `qq` (only an expired fact) 0, `nope` (no facts) 0, a non-existent scope returns the predicate with fan 0.
Note on that last result: the header says "No rows when the scope does not exist" (line 4), but the query returned **one row with fan 0** for a missing scope `zzz`, because `sids` is `collect(DISTINCT ...)` of a `MATCH` that has zero rows and `collect` with no grouping key returns `[]` in one row. CLARITY: the header is wrong here (`recall_entities` has the same shape, so by reading it would also return entities with fan 0 for a missing scope, contrary to its header line 4; I did not run that case). The Python wrapper treats it as fan 0 either way.
**CLARITY:** "one row per input predicate, in input order" (line 4) is false: live order was `qq, nope, pp, color, orgp` for the input `pp, qq, color, nope, orgp`. The caller builds a dict so nothing depends on it. There is no ORDER BY; duplicate inputs also collapse to one row. Reword the header.
**CLARITY:** same WHERE-on-OPTIONAL-MATCH comment vs code mismatch as `recall_entities` (lines 17 and 20 carry the WHERE, the CASE is at 21).
**BOUNDEDNESS RISK (the one real concern of the new cue):** `OPTIONAL MATCH (f:Fact {predicate: p})` is an index seek but its result is **every Fact in the graph with that predicate, in all scopes, all statuses and all times**; the status/validity filter is applied afterwards, and then the scope MATCH runs per surviving fact. For a common predicate (`status`, `owner`, `api_version`) in a long-lived tenant graph the cost grows with the whole history, not with the current facts in scope, and it is paid on every recall that names the predicate (up to 10 predicates, `RECALL_PREDICATES`). The header says "one index seek per predicate", which is true of the seek but hides the output size. No cheap fix without a counter; adding `status` to the seek is impossible (single-property indexes). Not mentioned in D-013 or PLEXUS_REPORT §9.3; I would list it there.

## reject_duplicate.cypher (9 lines)

Clean: `RETURN count(l)` after `DELETE l` works; live gave `removed 1` then `0` on a repeat.

## relates_level.cypher (21 lines)

Level-wise, anchored on the frontier (`MATCH (e:Entity {id: fid}) WITH e MATCH (e)-[...]`, skill 6c form) and each branch ends in `RETURN DISTINCT ... LIMIT $limit`, so path duplicates from a diamond scope graph cannot leak (live: a relation visible from `team` through `org` returned once). The two UNION branches are the documented workaround.
**SUSPECTED BUG, NOT CONFIRMED (lines 13 and 21):** `LIMIT $limit` applies to the whole frontier per direction, with no `ORDER BY`. With a frontier of up to 20 entities and a hub among them, the hub can fill the whole limit and the other entities contribute nothing; which rows survive is arbitrary (planner order). This matches what PLEXUS_REPORT §9.3 already reports for `recall(hops)` (cap filled in arbitrary/alphabetical order, answer not surfaced), and the Python sorts after the query, so the arbitrary pre-limit subset is invisible to it. A per-source limit would need a per-entity subquery (`CALL { WITH e MATCH ... LIMIT n }`, which 6.0.2 supports per skill 7b), not tested.
**BOUNDEDNESS:** bounded by `$limit` per direction. The scope test (line 12) runs a BFS per RELATES edge, fine for the stated depth.

## remember_episode.cypher (13 lines)

Clean for correctness: a first episode returned `prev_id null`, the second returned the first (live). The tail lookup `WHERE NOT (last)-[:NEXT]->(:Episode)` (line 9) is on an OPTIONAL MATCH, but a session always has a tail once it has episodes, so the row is never dropped.
**BOUNDEDNESS RISK (low):** finding the tail scans all HAS_EPISODE edges of the session and tests each for NEXT, i.e. O(episodes in the session) per append, O(n^2) over a session. If the chain were ever broken, two tails would give two rows and `CREATE (e ...)` would then create two Episodes with the same id; writes are serialised, so only a corrupted chain can do it. A `Session.last_episode` pointer would make it O(1); not worth it unless sessions get very long.

## resolve_entity.cypher (41 lines)

Clean for correctness. The two lookups are `CALL { ... RETURN collect(...) }`, which always return one row (the header's point), the `ORDER BY j` after `WITH node` is accepted, `coalesce(ex, head(ft), head(vec))` is right, and the `FOREACH ... MERGE` is the only write. Live: new entity -> `how: new`; same-token variant -> `how: fulltext` and the same id; no second Entity created. Division at line 19 cannot be zero: an empty `$tok` uses the `NO_TOKEN` sentinel so the index returns nothing, and entities without `tok` give a null `j` and are filtered out as the header says.
**BOUNDEDNESS RISK (new, on the serialised write path, by reading):** `queryNodes('Entity', $q)` with an OR over up to `MAX_ENTITY_QUERY_TOKENS = 24` tokens returns every entity sharing *any* token before `kind`/`num_key` are tested (line 17) and the Jaccard filter. For a family of twins ("Acme Notes API S01..S99") each new entity's creation scans all of them inside the per-graph write lock. The `num_key` filter prunes the result but not the scan. Not in D-013 or §9.3 (which only note non-transitivity and the migrate prerequisite).
**CLARITY:** the vector side applies `kind`/`num_key` after the top-`k` (k = 5), so near entities of another kind can crowd the right neighbour out. A missed merge, never a wrong one; same family as the documented recall pre-filter limitation. The variable name `vec` (line 28) shadows the `vec.` function namespace; harmless here, but renaming it (`vh`) avoids confusion.

## split_duplicate.cypher (19 lines)

Clean: the roundtrip above restored both facts (`restored: true`, `w1` superseded with `valid_to 400`, `w2` active/open). Guard `(NOT d.reopened OR ...)` handles a missing `reopened` as null-then-OR. FOREACH deletion of the `moved` edges precedes the SET, and the collect keys always have input rows.

## start_session.cypher (11 lines)

Clean: one bounded statement (MERGE agent, SET role/harness, CREATE session, CREATE edge). `role`/`harness` are overwritten on every session by design.

---

## Clean files

`assert_relation`, `backfill_entity_keys`, `best_procedure`, `confirm_duplicate`, `create_scope`, `duplicate_pair`, `fact_history`, `find_entity_exact`, `find_entity_fulltext`, `find_entity_vector`, `log_procedure_run`, `missing_refs`, `reject_duplicate`, `remember_episode`, `resolve_entity`, `split_duplicate`, `start_session`, `entities_page`, `entity_duplicate_names`, `recall_keywords` (some with CLARITY / low-risk BOUNDEDNESS notes above; no correctness finding).

## Already-documented limitations (reported as "known", not new)

- Vector filters run after top-k, so out-of-scope facts can crowd a target out: documented in `recall`'s header and PLEXUS_REPORT §9.3 ("vector filters run after top-k").
- Lexical named-entity / named-predicate rules give nothing to a paraphrase; the shipped cue constants were chosen post hoc: D-013 and §9.3.
- `recall(hops)` ranking, alphabetical cap, hop answers not surfaced: §9.3 (explains the `relates_level` LIMIT behaviour, not a query bug).
- Entity resolution not transitive, needs `plexus migrate entities` for legacy tenants: §9.3.
- Sibling expansion cost depends on the entity's fan-out: `recall` header lines 17-20 (this review adds that the damped hub is still fully enumerated).

## Top simplification candidates

1. `recall_hop_facts` lines 15-18: replace the post-DISTINCT MATCH by a pattern predicate (also fixes the confirmed duplicate bug).
2. `assert_fact` lines 77-88: one ASSERTED_BY comprehension feeding both `closing` and `clashing`.
3. `recall` / `recall_hop_facts`: drop the final `IN_SCOPE` and `ABOUT` re-MATCHes by carrying `gs` and `e`.
4. `recall_keywords` line 17: drop `DISTINCT`.
