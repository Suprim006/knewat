# Cypher review: `plexus/queries/lineage/` (19 files, 803 lines)

> **STALE (2026-10-18):** the numbers in this document were measured on builds before the current main (7618d18) and are not valid for it until re-run. Build per number: [docs/NUMBERS_STATUS.md](../../NUMBERS_STATUS.md).

Read-only audit against FalkorDB 6.0.2 on branch `feature/neuro-memory-research` (HEAD e126875). Checked against the three
FalkorDB skills, `docs/reference/FALKORDB_REFERENCE.md` §2, `CLAUDE.md` §6-7, `docs/PLEXUS_REPORT.md` §8.3/§9, and the callers in
`plexus/src/plexus/lineage/service.py`. `git diff main -- plexus/queries/lineage` touches only `record_recall` and
`why_recalled` (D-013 `entities` / `separation` / `sep`).

Live checks ran on `plexus-db-13` in throw-away graphs named `audit_lineage_<random>`, all deleted afterwards. Every
"live" number below is a real run. Scratch scripts are outside the repo (`$TMPDIR/audit_lin*.py`). Nothing in the repo was changed except this file.

## SUMMARY

| Severity | Count | Items |
|---|---|---|
| CONFIRMED BUG (performance / boundedness) | 2 | **quarantine** (line 66-81): list-as-grouping-key makes it quadratic, 1,200 facts = 1.5 s, 2,500 facts = timeout, while callers allow 5,000. **why_derived_level** (all branches): `UNWIND $frontier MATCH (:Fact {id})-[:R]->()` scans every DERIVED_FROM edge per level (5,004 records for a 1-element frontier). |
| CONFIRMED BUG (semantic, low) | 2 | `record_step` `previous_id` is wrong on the idempotent / out-of-order paths. `impact_fact` drops the root fact itself when the result is truncated. |
| BOUNDEDNESS RISK | 4 | `forget_source` carries `fs` as a key (382 ms at 2,500 facts, superlinear, same family as the quarantine bug). `quarantine` `reads` collects every (step, fact) pair before cutting. `knew_at` and `record_step` read the agent's whole step history per call. |
| SIMPLIFICATION | 4 | Extend `gen_impact_queries.py` to emit the 12-hop cascade for `forget_source`, `quarantine`, `release_quarantine` (3 hand copies x 48 lines). `why_edges` repeats an 8-line base-fact prelude 9 times. `quarantine` tail to `CALL` subqueries (fix verified). `UNION` to `UNION ALL` in `node_info` / `existing_ids`. |
| CLARITY | 4 | `link_derived` header says `DERIVED_FROM*1..5` (stale). `quarantine` blast radius omits facts already quarantined by another source (design gap, undocumented). `reads_total` counts (step, fact) pairs but `impact_*.steps_total` counts distinct steps. `forget_source` header says it is the twin of `impact_fact`, but they start from different node types. |
| SUSPECTED, NOT CONFIRMED | 0 | Every trap I suspected from reading was tested live. See "Traps checked and NOT reproduced" below. |
| CLEAN | 11 files | `as_of`, `create_source`, `discard_step`, `existing_ids`, `knew_at` (work grows with step history), `link_derived` (stale header only), `link_step`, `node_info`, `record_recall`, `release_quarantine`, `who_knew`, `why_recalled`. `why_edges` is correct but has a large redundancy (see its section). Notes on some are below. |

The two big findings are **not** in the documented-limitations list. `PLEXUS_REPORT.md` §8.3 records that `impact` was
fixed for the 5,000-id grouping-key problem. That fix was never applied to `quarantine` or `forget_source`, which still use the
old shape. `PLEXUS_REPORT.md` line 224 also still says "five fixed one-hop levels". The code now has twelve with `$depth`.

### Traps checked and NOT reproduced (live, fixture where every part fires)
- `as_of`: three pattern comprehensions on `ASSERTED_BY` / `SUPERSEDES` / `CONTRADICTS` in one `RETURN`, plus a `WHERE` after
  `WITH collect(...)`. Result correct: F2 returned `['a1'] / ['F1'] / ['F3']`, and an inherited-scope hit at `t=5` returned `hops=1`.
- `link_step` and `link_derived`: `OPTIONAL MATCH ... WHERE x.id IN $list` after `WITH ..., collect(...)`. Mixed Fact / Decision /
  Handoff / Task writes were linked correctly (`n_read 2, n_wrote 4`; `linked 3`). A bad id returned zero rows and wrote nothing.
- `who_knew` and `why_recalled`: multiple comprehensions over different relationship types returned all lists populated.
- `knew_at`: `UNION` with per-branch `ORDER BY ... LIMIT` runs and returns correct rows.
- `why_edges`: the `collect` -> `OPTIONAL MATCH` -> `collect` -> `UNWIND` -> `MATCH` prelude works for a Decision root and a Fact root, and an unknown id returns no rows.
- Zero-input aggregation killing writes: `quarantine` / `forget_source` / `release_quarantine` on a Source with no derived facts
  return one row with empty lists. Verified live for the proposed `quarantine` variant on an empty Source and for `forget_source` on a second (nothing-left) call; `release_quarantine` no-op also returned one empty row. An unknown Source returns zero rows (documented).
- `LIMIT` before eager `SET` in the cascades: the limit is applied at `WITH DISTINCT src, f LIMIT $limit` before the `FOREACH`, so it really bounds the write.

---

## Per-file findings (alphabetical)

### `as_of.cypher` (20 lines)
- **CLEAN**, with two notes.
- L8: `[:INHERITS*0..3]` enumerates paths, but over a scope hierarchy (depth <= 3, `min(length(p))`). It is only a problem with a very diamond-shaped scope graph. BOUNDEDNESS: negligible.
- L11-12: the work is bounded by the number of facts about (subject, predicate), not by `$limit`, and `$limit` applies after the sort. Fine for history sizes that are realistic.
- L11 `WHERE` follows an aggregation (`WITH collect(...) AS scopes`). Trap #1 of the big-write skill did not reproduce (live above). Header and body params match. `Entity.norm_name` and `Step.agent_id` are indexed in `schema/indexes.cypher`.

### `create_source.cypher` (17 lines)
- **CLEAN.** The `s.new` flag, then `WITH ... REMOVE s.new`, is a correct way to return `created`. Trust handling matches the header, including the legacy float case: `1.0 = 'high'` is false, so it becomes `'normal'`.
- Note: `ON MATCH SET s.kind = $kind` overwrites `kind` on every call, even when the caller passes the default. Documented ("refreshes kind").

### `discard_step.cypher` (11 lines)
- **CLEAN.** Verified live: a Step with READ / WROTE edges returns 0 and is kept; an empty Step returns 1 and is deleted; an unknown id returns one row with 0 (the key-less `count` keeps a row). The delete is bounded to one node.

### `existing_ids.cypher` (14 lines)
- **CLEAN.** Five branches, each a `Node By Index Scan` (live PROFILE: 1 record for the matching branch, 0 for the others).
- SIMPLIFICATION (trivial): `UNION` to `UNION ALL`. A row can only repeat if the same id exists under two labels, and the label column differs, so `UNION` never dedups anything here. Behaviour-preserving, ~100%. The path is only used for the error message.

### `forget_source.cypher` (79 lines)
- L15-62 (cascade): level-wise expansion is **correct**. It is a fixed 12-hop chain, each hop bound by `$depth`, driven by DISTINCT facts, and anchored at the Source. `$depth < k` yields `[null]`, which gives an empty level and skips the rest. This is the shape the skills prescribe (6d). Depth is validated 1..12 in `service.py` (`check_between`).
- L64-66: status filter, then `LIMIT $limit` **before** any write. `WITH DISTINCT src, f LIMIT $limit` is correct for the "LIMIT doesn't limit eager ops" rule, and already-forgotten facts are excluded, so a repeated call makes progress. Zero-fact case returns one row via `[null]` (checked live). Idempotent second call returned empty lists (live).
- **BOUNDEDNESS RISK (L67-73, performance):** `fs` (up to 5,000 nodes) stays in the grouping key through `UNWIND y` / `WITH src, fs, collect(...)`. This is exactly the problem `PLEXUS_REPORT` §8.3 documents for `impact` (skill 7b). Live (600 facts + 1 decision each): 1,200 facts 91 ms, 2,500 facts 382 ms (about 4x for 2x, so quadratic); extrapolated 5,000 is about 1.5 s. Not a timeout at the documented cap, so a risk rather than a bug. Same fix as `quarantine` below.
- L74-77: `FOREACH` writes. `valid_to = min(valid_to, now)` handles an open-ended fact. A quarantined-then-forgotten fact keeps a stale `prior_status` property (harmless; `release_quarantine` ignores it because the status is no longer `quarantined`). CLARITY (trivial).
- Header is complete and matches the body. Duplicated block, see SIMPLIFICATION 1.

### `impact_fact.cypher` (86 lines) and `impact_source.cypher` (86 lines)
- **Generated** by `scripts/gen_impact_queries.py`. I rebuilt both with `build('fact')` / `build('source')` and compared them with the files on disk: identical. Review the generator, not the copies. Both files are the 12-hop cascade (L8-54) plus four `CALL` subqueries (L59-82).
- The `CALL` subqueries are the correct shape. Live (2,500 facts, each with a reader and a decision): `impact_source` 146 ms; 600 facts 22 ms. Each `CALL` returns a key-less aggregate, so empty input still gives one row. The root-not-found case returns zero rows through the first `MATCH`.
- **CONFIRMED BUG (low), `impact_fact` L55 (`WITH src, reach + [src] AS reach`):** the root is appended **last**, so when the result is cut by `LIMIT` the root fact itself is the first to disappear. Live: `impact_fact(F1, limit=1)` returned `fact_ids=['F3']`, `truncated=true`, with F1 missing, although the docstring in `service.impact` says "the fact itself is part of facts". Fix: `[src] + reach AS reach` (root first). Confidence ~85% behaviour-preserving for the non-truncated case; for the truncated case, ordering after `DISTINCT` is not formally guaranteed in 6.0.2, so verify with a one-line test. Because the generator owns this line, change it there and regenerate.
- `limit+1` is passed by the caller, so `truncated` (`size(fs) >= $limit`) means "one more exists". That is right.
- Headers are generated, consistent, and match the body (params `id, depth, limit`).

### `knew_at.cypher` (25 lines)
- **CLEAN** for correctness (live: `read` and `wrote` rows correct; `UNION` with per-branch `ORDER BY ... LIMIT` accepted).
- **BOUNDEDNESS RISK (low), L7-10 and L18-20:** the cut Step is found by sorting all of the agent's Steps (`Step(agent_id)` index, then `ORDER BY n DESC LIMIT 1`), and the READ / WROTE branches read the agent's whole history up to the cut before `LIMIT $limit` applies. Cost grows with the agent's step count. Output is bounded; work is not. Acceptable for a time-machine query, but it is not constant-time.
- `$limit` applies per branch, so up to `2 x limit` rows return. Header says "limit:int" only. CLARITY (trivial).

### `link_derived.cypher` (18 lines)
- **CLEAN** (live: mixed Source + Episode + Fact origins linked 3 of 3; an unknown origin id returned zero rows and wrote nothing).
- **CLARITY (stale header), L6:** says "forget_source and quarantine follow these edges (DERIVED_FROM*1..5)". They now follow up to `$depth` (1..12) one hop at a time. Suggested text: "...follow these edges level by level up to $depth (1..12)".
- Note: a derivation **cycle** (A derived from B, B from A) is not rejected here (only self-derivation is checked in Python). The cascades handle it because each is depth-limited and uses DISTINCT, but `why` and the cascades will revisit cycle members at every level up to `$depth`. Bounded, so no action.
- The `size(srcs) = size($from_ids)` guard relies on callers de-duplicating (documented).

### `link_step.cypher` (28 lines)
- **CLEAN** (live: reads `[F1,F2]`, wrote `[F3, Decision, Handoff, Task]` gave `n_read 2, n_wrote 4`; one bad id gave zero rows).
- L22-26: `ON MATCH SET` order is right (`via` is evaluated before `at`; `at` only moves forward). It does not update `rd.suspect`, which `record_recall` maintains. A `'use'` link over an earlier `'recall'` READ keeps the recall-time `suspect`. By the header and the activation rule ("never counts a recall READ with suspect = true") that is intended, since `via` becomes `'use'`. Noted, not a bug.

### `node_info.cypher` (53 lines)
- **CLEAN.** 15 branches, one per label, each a `Node By Index Scan` for the matching label (live PROFILE: 1 record, not graph size). All 15 labels have an id index in `schema/indexes.cypher` (checked each one), so the header's cost claim holds.
- The branch set covers every label emitted by `why_edges` / `why_derived_level` (Agent, Decision, Task, Fact, Step, Entity, Scope, Change, Source, Episode, Session).
- SIMPLIFICATION (trivial): `UNION` to `UNION ALL` (the label column makes every row distinct, so the output is identical). ~100% safe. It saves one Distinct over at most a few hundred rows, so it is low value.

### `quarantine.cypher` (81 lines)
- L14-61 (cascade): correct, same as `forget_source` (see that file). L62-66: status filter + `LIMIT $limit` before the write, correct. `prior_status` is kept, so a fact already quarantined via another source is not re-snapshotted (live: F3 kept `prior_status='active'` through two quarantines).
- **CONFIRMED BUG (performance, L67-81): quadratic blow-up from list-valued grouping keys.** After `WITH src, collect(f) AS fs`, the query does `UNWIND fs AS x OPTIONAL MATCH (s:Step)-[:READ]->(x)` and then `WITH src, fs, collect(CASE...) AS reads, ...` (L70), then `UNWIND fs AS y ... WITH src, fs, reads, agent_ids, collect(DISTINCT d)` (L74), then once more for handoffs (L77). The `fs` list and the whole `reads` list of maps are hashed once per row. This is trap 7b in `falkordb-plan-shape-tests`, the exact bug `PLEXUS_REPORT` §8.3 says was fixed in `impact`, but the same fix was never applied here.
  - Live repro (each fact has 1 reader step + 1 decision, `depth=8`, `limit=5000`): **600 facts 371 ms; 1,200 facts 1,518 ms; 2,500 facts `Query timed out` (TIMEOUT_MAX 10 s)**. `service.quarantine` allows `limit` up to `MAX_FORGET_FACTS` (5,000). The same graph through `impact_source` took 146 ms, and `release_quarantine` 86 ms.
  - Because the write sits after the slow reads, a timeout aborts before the `FOREACH` (live: nothing was quarantined after the timeout). But the reference §2 #12 warns that the timeout is unreliable for writes. A fact set that is slow to read is also a risk of a half-observed state.
  - **Fix (prototyped and measured), replace L66-81 with the `impact_source` structure.** Keep L1-65, then:
    ```cypher
    WITH src, collect(f) AS fs
    CALL {
      WITH fs
      UNWIND CASE WHEN size(fs) = 0 THEN [null] ELSE fs END AS x
      OPTIONAL MATCH (s:Step)-[:READ]->(x)
      WITH x, s ORDER BY s.at ASC, s.agent_id ASC, x.id ASC
      RETURN collect(CASE WHEN s IS NULL THEN null ELSE {agent_id: s.agent_id, step_id: s.id, n: s.n, at: s.at, fact_id: x.id} END) AS reads,
             collect(DISTINCT s.agent_id) AS agent_ids
    }
    CALL { WITH fs UNWIND CASE WHEN size(fs) = 0 THEN [null] ELSE fs END AS y
           OPTIONAL MATCH (d:Decision)-[:BASED_ON]->(y) RETURN collect(DISTINCT d) AS ds }
    CALL { WITH fs UNWIND CASE WHEN size(fs) = 0 THEN [null] ELSE fs END AS w
           OPTIONAL MATCH (h:Handoff)-[:CARRIES]->(w) RETURN collect(DISTINCT h) AS hs }
    FOREACH (z IN fs | SET z.prior_status = z.status, z.status = 'quarantined', z.quarantined_at = $now)
    RETURN <unchanged RETURN list>
    ```
    Measured on the same shape of graph (5,000 facts, each with reader + decision + handoff): **old 2,222 ms @1,500 facts vs new 101 ms; new @5,000 facts 589 ms (old times out)**. Results compared at 1,500 facts: identical fact set, identical ordered `reads`, equal totals. An empty Source still returns one row with empty lists. Confidence it is behaviour-preserving: ~90%, unverified only for exotic graphs (e.g. a Step that READs the same fact twice, which `MERGE` prevents). Trap it could trip: `ORDER BY` + `collect` inside `CALL` (it worked on 6.0.2 here).
- **BOUNDEDNESS RISK:** even after the fix, `reads` materialises every (step, fact) pair before cutting to `max_detail`. That is the price of an exact `reads_total` and an exact `agent_ids`; the response is bounded (documented in the header, P5 review Q11) but the intermediate list is not. A heavily read fact set could use a lot of memory. Optional: compute `reads_total` with `count(s)` and take the first `max_detail` via `ORDER BY ... LIMIT` in a separate `CALL`.
- **CLARITY / design gap (live-verified):** the blast radius (`reads`, `decision_ids`, `handoff_ids`) covers only facts **changed by this call**. A fact already quarantined through another source (the "S2" case: `F3` reached via two sources) is skipped, so quarantining the second source reports empty readers / decisions for it. If the header's "the blast radius is returned" should mean "everything downstream of the source", this undercounts; if it means "of what this call changed", say so. Suggested header text: "reads / decisions / handoffs describe only the facts this call changed".
- CLARITY: `reads_total = size(reads)` counts (step, fact) pairs, while `impact_*.steps_total` counts distinct steps; the names suggest the same thing.
- Header params (`source_id, now, limit, depth, max_detail`) match the body.

### `record_recall.cypher` (37 lines, **changed on this branch**)
- **CLEAN.** Branch changes are exactly: `entities` / `separation` params added to the header and to `CREATE (r:Recall ...)` (L21-22), and `sep: row.sep` on `RETURNED` (L27). Params in the header match the body and `service.record_recall` (the only caller; it supplies `entities`, `separation`, and `sep` for every row). Live: recall with 2 facts returned `returned 2`; the `RETURNED.sep` was stored; an empty recall with `entities=['e1'], separation=True` round-tripped through `why_recalled` as `['e1'], True`; an unknown step wrote nothing (zero rows).
- L13-18: guard pattern `OPTIONAL MATCH ... WITH st WHERE $step_id = '' OR st IS NOT NULL` then `collect(f)` then `WHERE size(fs) = size($fact_ids)` is correct, and the `MERGE (a:Agent)` comes after the guard, so a rejected call leaves no Agent behind. `OPTIONAL MATCH (f:Fact) WHERE f.id IN $fact_ids` was PROFILE'd on a sibling query (`link_derived`) as an index seek, so cost does not scale with the graph.
- L32-36: `ON MATCH SET rd.suspect = CASE WHEN coalesce(rd.at,0) > $now ...` is placed **before** `rd.at = ...`, which is the correct order (trap 7).
- Boundedness: results are capped by the Python side (`MAX_RECALL_RESULTS`), `O(results x facts)` in the `FOREACH` (<= 200 x 200).
- Minor: if `row.sep` were ever null (only possible for a non-service caller), the property would be silently dropped from `RETURNED`; `why_recalled` coalesces it to 0.0.

### `record_step.cypher` (21 lines)
- Mostly correct; the `MERGE` is followed by a `WITH` before the `OPTIONAL MATCH`, which is the valid form (the rejected order is MERGE directly followed by OPTIONAL MATCH). Atomicity holds since writes are serialised per graph.
- **CONFIRMED BUG (low, semantic), L21 (`last.id AS previous_id`):** the header says `previous_id` is "the id of the preceding Step or null". On the idempotent and out-of-order paths it returns the agent's **latest** Step, which is not the preceding one. Live: steps x1 (n=1), x2 (n=2). Asking again for `n=2` returned `previous_id='x2'` (itself). Asking for `n=1` returned `previous_id='x2'` (a later step). `n=0` (refused) returned `previous_id='x2'`. The service ignores `previous_id`, so there is no functional impact today. Fix: `CASE WHEN can THEN last.id ELSE null END AS previous_id`, or reword the header to "latest existing Step". Confidence 95% for the CASE version; the only caller to check is `service.record_step` (it does not read this column).
- **BOUNDEDNESS RISK (low), L11-12:** `OPTIONAL MATCH (p:Step {agent_id}) WITH a, p ORDER BY p.n DESC LIMIT 1` reads and sorts all of an agent's Steps on every call. The cost grows with the agent's step count. A long-lived agent with 100k steps pays that on every tool call (record_step runs before each write). Possible fix: keep `a.last_n` on the Agent and update it here; that changes the data model, so it is a design decision, not a trivial fix.

### `release_quarantine.cypher` (66 lines)
- **CLEAN** for correctness, with the shared duplication noted. L12-59 cascade identical to `forget_source`; L61 filters to `quarantined`; L63 limit before the write (L65 is the only write). `coalesce(z.prior_status, 'active')` covers a missing snapshot. Zero-fact case returns one row via `[null]`. Live: release after a double quarantine restored `F3` to `active` and removed both helper properties; a no-op release returned an empty list in 24-91 ms.
- No grouping-key problem: after the cascade there is a single `collect(f)` and no list is carried through an `UNWIND`.
- Documented behaviour (header L6): a fact quarantined through another source is also restored if it reaches this one (live-confirmed: releasing S2 restored F3 although SRC was still quarantined). Known and documented, not new.
- Depth must be >= the depth used by `quarantine`, or deeper facts stay quarantined. Documented in the header (`use the depth the quarantine used`).

### `who_knew.cypher` (13 lines)
- **CLEAN** (live: one row per reading Step; `asserted_by`, `written_by`, `recall_ids` are populated correctly). Three pattern comprehensions over three different relationship types gave the right answer. `WITH f, s ORDER BY ... LIMIT $limit` bounds the Step rows. `written_by` and `asserted_by` are unbounded per row but only as large as the fact's own writers. A fact nobody read gives one row with null step, as the header says.

### `why_derived_level.cypher` (22 lines)
- **CONFIRMED BUG (performance, L8-22; all four branches share the shape):** `UNWIND $frontier AS fid MATCH (f:Fact {id: fid})-[:DERIVED_FROM]->(x)` is planned as `Unwind -> Conditional Traverse` over **every** DERIVED_FROM edge, then a filter (skill 6c). The header's claim "anchored at the frontier ids (index seek on Fact.id)" is not true for branches 1 and 2. Live PROFILE with a 1-element frontier on a graph with 5,000 unrelated DERIVED_FROM edges: branch 1 `Conditional Traverse` = **5,004 records**, branch 2 = **5,001 records**. It runs once per level (up to `depth` = 12 queries per `why`), so each `why` costs about `depth x #DERIVED_FROM edges`. Branches 3-4 begin with the same pattern shape (`Conditional Traverse` over a label-less start); my noise graph had no Episode edges, so their cost was not measured and I do not claim it.
  - **Fix (measured):** bind the node first.
    ```cypher
    UNWIND $frontier AS fid
    MATCH (f0:Fact {id: fid})
    WITH f0
    MATCH (f0)-[:DERIVED_FROM]->(x)
    RETURN DISTINCT f0.id AS s, 'Fact' AS sl, 'DERIVED_FROM' AS rel, x.id AS t, labels(x)[0] AS tl, 3 AS prio LIMIT $limit
    ```
    The same `MATCH (f0:Fact {id: fid}) WITH f0 MATCH (f0)-...` shape applied to branches 1 and 2 on the same noise graph: **max records 5,001 -> 1**, identical rows (`[['A','B']]` and `[['B','ag']]`). Apply it to branches 3 and 4 as well (same pattern; unmeasured, expected equal). Confidence 95% behaviour-preserving; trap watched: none triggered. Update the header accordingly.
- Correctness otherwise good: the four branches cover frontier->x, derived fact's asserting agent, Episode's Session, and Session's Agent; `UNION` dedups. The per-branch `LIMIT $limit` truncates silently, but the caller already tracks `max_elements`.

### `why_edges.cypher` (109 lines)
- **CORRECTNESS: CLEAN** (live, Decision root: 9 distinct edges covering DECIDED, BASED_ON, WROTE, ABOUT, ASSERTED_BY, IN_SCOPE, SUPERSEDES, CONTRADICTS both ways; Fact root and unknown id also behave: an unknown id returns zero rows). L13-27 are five Decision-edge branches that work from an indexed `Decision {id}`. The empty-list-then-`UNWIND` trap (#2) is the intended behaviour here (no base facts -> no rows).
- `LIMIT $limit` per branch without `ORDER BY` truncates in an unspecified order; the caller (`bound_edges`) re-sorts by `prio`. With 13 branches, up to `13 x limit` rows reach Python. Bounded.
- **BOUNDEDNESS:** the header says "a base fact's neighbourhood is fixed, so the result is bounded". The base set is not fixed for a Decision with many `BASED_ON` facts, but every branch is `LIMIT`ed, so the output is bounded. Only the prelude work scales with the decision size.
- **SIMPLIFICATION (inherent in the UNION shape, but redundant in text):** L29-33, 38-42, 47-51, 56-60, 65-69, 74-78, 83-87, 93-97, 102-106 repeat the same 5-line prelude (`OPTIONAL MATCH BASED_ON`, `collect`, `OPTIONAL MATCH f0`, `collect`, `bfs + f0s`). That is 9 x 5-8 lines, about 60 of the 109 lines. Also it recomputes the base 9 times (all index seeks, cheap).
  - Sketch (before: 9 branches each with the prelude; after: prelude once, branches inside one `CALL` with `UNION`):
    ```cypher
    OPTIONAL MATCH (:Decision {id: $id})-[:BASED_ON]->(bf:Fact)
    WITH collect(bf) AS bfs
    OPTIONAL MATCH (f0:Fact {id: $id})
    WITH bfs, collect(f0) AS f0s
    WITH bfs + f0s AS base
    CALL { WITH base UNWIND base AS f MATCH (f)-[:ASSERTED_BY]->(a:Agent) RETURN ... LIMIT $limit
           UNION WITH base UNWIND base AS f ... }
    RETURN ...
    ```
    plus the five Decision branches as a separate `CALL { ... UNION ... }`. About 109 -> 60 lines. **Confidence ~55%** that it is behaviour-preserving without further debugging: each branch of a `CALL { ... UNION ... }` would need its own `WITH base` import (not checked on 6.0.2 here), and `WITH bfs, collect(f0)` follows the skill 5 warning about mixing an aggregate with another column in one WITH. **Not recommended without a prototype and the existing tests.** A safer and smaller option: keep UNION as is and generate the file from a script (the prelude is the same text), as `gen_impact_queries.py` does for the cascades.
- CLARITY: L109 alone uses `RETURN DISTINCT`; `UNION` dedups anyway. Header correct (params `id, limit`).

### `why_recalled.cypher` (17 lines, **changed on this branch**)
- **CLEAN.** Branch changes are `coalesce(r.entities, []) AS entities`, `coalesce(r.separation, false) AS separation`, and `coalesce(x.sep, 0.0) AS sep`, with the header updated to match. Live: recall with two returned facts returned both rows in rank order with all list columns populated (`entity`, `asserted_by`, `scope`, `step`); `sep` was 0.0 and 0.03; a recall that returned nothing gave one row with `fact_id` null and `entities=['e1'], separation=true`; an unknown recall gives no rows (via the first `MATCH`).
- Five pattern comprehensions over five different relationship types (IN_STEP, ABOUT, ASSERTED_BY, DERIVED_FROM, IN_SCOPE) returned correct values in the live fixture. The trap list warns about two over the **same** relationship pattern, which is not the case here.
- `ORDER BY x.rank ASC LIMIT $limit` (`MAX_RECALL_RESULTS`): bounded.
- Note: `coalesce(r.entities, [])` also keeps old (pre-D-013) Recall nodes readable. Good.

---

## Cross-file items

1. **SIMPLIFICATION 1, the 12-hop cascade is hand-copied three times** (`forget_source` L15-62, `quarantine` L14-61, `release_quarantine` L12-59, 48 lines each, identical after renaming) and is generated for `impact_*`. `gen_impact_queries.py` `build()` already emits the cascade prefix in a loop (`for k in range(2, MAX_DEPTH + 1)`), so a shared function that emits the prefix plus per-file tails removes about 144 hand-maintained lines and the risk of the copies drifting. Confidence ~95% (it is pure text generation; verify by diffing the generated files against the current ones, as I did for `impact_*`). The generator docstring already claims "Both files share the same 12-hop level-wise expansion as `lineage/quarantine` and `forget_source`", but nothing enforces it.
2. **Docs that disagree with the code** (not in this directory): `PLEXUS_REPORT.md` L224 "five fixed one-hop levels"; `link_derived.cypher` L6 header (above).
3. **Known and documented, not new:** `LIMIT` before eager ops (CLAUDE.md §6); the 5,000-id grouping-key problem for `impact` (PLEXUS_REPORT §8.3); `depth` 1..12 replacing the hidden 3-5 hop caps (§8.3); release-through-another-source (header of `release_quarantine`); `forget_source` flags but does not delete Decisions (header).

## Recommended order of work
1. `quarantine.cypher` tail to `CALL` subqueries (verified fix, High: a 5,000-fact quarantine currently fails).
2. `why_derived_level.cypher` bind-then-traverse (verified fix, Medium: cost multiplied by `depth` on every `why`).
3. Same `CALL` treatment for `forget_source.cypher` L67-73 (Low-Medium).
4. Generator for the three cascade prefixes; `impact_fact` root first; `record_step` `previous_id`; stale headers.
