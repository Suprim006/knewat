# L8 Round A2: the P arm re-run after the P12 fixes

Branch `p12` (base `main` f96df06). Written in two parts: **Part 1 (plan, pre-registration and the no-LLM recall
measurement) was written and committed before the first paid `claude -p` call of this round**; Part 2 (results) is
appended after the runs and does not edit Part 1. Source documents: `docs/research/L8_LONG_HORIZON_OUTCOMES.md`
(the L8 pre-registration, amendments 1-4 and the Round A results, copied unchanged from branch `p11` at `c2d1217`) and
`docs/research/GRAPH_VS_SQL_MECHANISMS_AND_OUTCOMES.md` §3.

## Part 1. Plan (written before any paid call of this round)

### 1.1 What changed in the product (four commits on `p12`)

| Commit | Fix | What |
|---|---|---|
| `0628671` | 1: recall | default scope `all`; `k` 8 → 20, `budget_chars` 2,000 → 6,000 and a `truncated` / `omitted_by_budget` / `more_available` signal; a candidate pool of `max(3k, 60)` (≤ 150) instead of `2k`; the keyword channel also indexes `Fact.search_text` (entity name + predicate words), keeps short tokens with digits (`v2`, `s7`), logs a failed keyword query instead of swallowing it; relevance = cosine + IDF-weighted query-word coverage; BGE query instruction |
| `b487f05` | 2: task-tool atomicity | `create_tasks`, `claim_next_task`, `complete_task`, `fail_task`, `reopen_task` write their `(Step)-[:WROTE]->(Task)` edge inside their own statement (`FOLDS_WROTE`). Kill test `crucible/l6/crash_tasks.py` (hard `Popen.kill` 0-400 ms into a writer looping the five tools; a Task must carry `version + 1` WROTE edges): re-run by the orchestrator, **old path (`--legacy`) 25 orphaned task writes in 30 kills (489 acknowledged calls), new path 0 in 30 kills (522 calls), 0 lost acknowledged writes in both**; the subagent's run: 41 of 1,287 vs 0 of 1,333 over 50 kills; `tests/crucible/l6/test_crash_fold_tasks.py` asserts 0 |
| `498824c` | 3: `verify_fact` | the `verify_degraded` marker (+ suspect state + provisional decision flags) is written **before** the supersede (option "B" of the brief; the single-statement fold was not attempted, §1.3). Kill test `crucible/l6/verify_crash.py` (writer loops assert → decide → `verify_fact(changed)`; a test-only 60 ms sleep between supersede and backdate widens the kill window, used for both runs): re-run by the orchestrator, **old order 18 of 68 superseded facts silent (no completed verification, no marker) with 18 unflagged decisions on them, new order 0 of 62 (19 left marked unfinished, 5 marked before the supersede), 30 kills each**; `tests/crucible/l6/test_verify_crash.py` asserts 0 |
| `e070824` | (found by the full suite) | `apply_schema` retries FalkorDB's transient "another write is in progress"; the L8 harness's dirty check also ignores this round's output directory |

### 1.2 The recall root causes, checked against the code (pre-fix line numbers, `main` f96df06)

The three reviews' list, verified one by one before anything was changed:

| Claim | Verified at | Verdict |
|---|---|---|
| `k = 8`, `budget_chars = 2000` defaults | `engram/service.py:463,465`; MCP tool `mcp/tools_engram.py:154,162` | true |
| tiny candidate pool: `fetch_k = 2k` with forgetting on, vector fetch `4 * fetch_k` | `engram/service.py:515,547` (plus an adaptive retry up to 512 only while fewer than `k` rows survive the filters) | true |
| keyword channel indexes only `Fact.value`; keyword hits re-ranked by cosine only; words under 3 characters dropped; `ResponseError` swallowed | `queries/schema/fulltext.cypher`, `queries/engram/recall.cypher:38-39,53-54` (`ORDER BY score/rank ... LIMIT $k`), `engram/service.py:92,664` | true, all four |
| no BGE query instruction | `embed/fastembed_embedder.py` (one `embed` for facts and queries) | true |
| flat activation penalty for facts with no activation history | `activation/rank.py:59-63` (`-inf` → the floor 0.9) | true as written, but in L8 every fact has its creation event; old history facts sit near the floor because they are old, not because they have no history |

**One cause the list does not contain, and it is the decisive one for L8.** Recall searches "the given scope plus
the scopes it INHERITS" (`queries/engram/recall.cypher:23`), and the tool's default scope was `global`
(`mcp/tools_engram.py:153`). `global` inherits nothing, so a default recall never sees a `project:*` scope. The
20-sprint history writes the S07 billing cycle into `project:billing-s07` and the S20 release channel into
`project:acme-s20` (`crucible/l2/scale_scenario.py:377-381`); L8 amendment 2 had already noted the first one. Two of
the three long-horizon facts L8 scores were therefore unreachable by any default recall, whatever `k`, pool or
ranking. B1's baseline has the same scope chain (`crucible/backends/sqlite.py:352-357`, `scope_chain`), which is why
B1 also found only the S13 fact (5/15).

### 1.3 Fix 3: which option and why

Option B (marker before the supersede), not the single-statement fold. The supersede is `engram/assert_fact.cypher`,
a ~120-line statement with several documented FalkorDB 6.0.2 planner traps in its header, and it is Engram's write
path for every fact; folding the staleness backdate into it would put staleness logic inside the most-used write of
the product. Option B gives the invariant that matters (a kill can no longer leave a Decision `BASED_ON` a silently
wrong fact: the marker, the suspect state and a provisional decision flag are one statement written first), and
`facts_to_verify` / `suspect_ids` now list marked facts even after they were superseded. What it does **not** give:
the supersede and the backdate are still two statements; a kill between them leaves a marked, unfinished
verification that the next `verify_fact` (same value) completes, not an atomic all-or-nothing change.

### 1.4 The no-LLM recall measurement (before any live run)

`python -m plexus.crucible.l8.recall_bench` builds the exact store an L8 P run starts from (the 20-sprint history
through the P-mcp backend, `hash` embedder as in L8), then talks to an in-process Plexus MCP server (the real tool
layer and its defaults). Two measurements, no LLM anywhere:

* **Replay:** every `add_source` / `assert_fact` / `recall` the Round A P agents issued, in transcript order, with
  their own arguments. For the 36 recalls made while working on `t13` (needs S07 billing cycle, S13 API-key header)
  and `t16` (needs S20 release channel), did the fact the query asked for come back?
* **Canonical:** for each sprint S01-S20 and five history facts (API version, database, API-key header, billing
  cycle, release channel), one query naming the subject and one paraphrase without it, with the tool's defaults:
  200 queries per seed, 1,000 over 5 seeds.

| | before (f96df06 code) | after (all P12 fixes) | after, but scope forced to `global` |
|---|---|---|---|
| Replay: recalls that returned the fact they asked for | **6 / 36** | **27 / 36** | 6 / 36 |
| Replay: S07 billing cycle found by any recall of its task (per seed) | 0 / 5 | 5 / 5 | 0 / 5 |
| Replay: S13 API-key header | 5 / 5 | 5 / 5 | 5 / 5 |
| Replay: S20 release channel (only one Round A P seed reached `t16`) | 0 / 1 | 1 / 1 | 0 / 1 |
| Canonical: target returned (of 1,000) | **600** | **1,000** | 600 |
| Canonical: target ranked first (of 1,000) | 515 | 1,000 | 600 |
| Canonical: billing cycle / release channel facts (of 200 each) | 0 / 0 | 200 / 200 | 0 / 0 |

Files: `plexus/demo_data/crucible/l8_postfix/recall_bench-{before,after,after-scope-global}.json`. Read it as: the
scope default accounts for every miss of a stored long-horizon fact (the forced-`global` column has exactly the
"before" completeness); the ranking changes (pool, keyword channel, fusion) took the in-scope facts from rank 1 in
515 of 600 to 600 of 600 and the agents' real queries from 6 to 27 of 36 found. The 9 remaining replay misses are
vague queries such as "Bolt Billing API" with `k = 10` (20 sprints of equally good matches).

BGE query instruction (fix 1e), measured separately with the real `fastembed` embedder (history and queries both
BGE): prefix on 32 / 36 replay, 1,000 / 1,000 canonical; prefix off 32 / 36, 1,000 / 1,000. **No measurable effect on
this benchmark.** It stays on (it is the model's documented query form; `PLEXUS_BGE_QUERY_PREFIX=off` disables it).
The live re-run uses the `hash` embedder as Round A did, so this change cannot affect it.

### 1.5 Re-run design (the "change only the backend" rule, `docs/BASELINE.md` §0)

* **Arms:** P only. B1 and B0′ are not re-run: nothing in their code path changed (they do not use `recall`,
  Engram, the relay task statements or `verify_fact`; B1 is `crucible/backends/sqlite.py` behind
  `crucible/l3/baseline_mcp.py`, B0′ has no MCP server). Their Round A runs are copied byte-identical into
  `plexus/demo_data/crucible/l8_postfix/runs/<seed>/{B1,B0p}` (`caca7ad`), and the scorer at this commit re-scores
  them to exactly the Round A pooled numbers (checked: `score_all(..., arms=('B1','B0p'))` pooled == the
  `latest-roundA.json` pooled, field for field; per-run `metrics.json` byte-identical).
* **Held fixed:** seeds 20261017-20261021 and their frozen schedules (`seeds/*/schedule.json`), prompts and briefs
  `l8-v1` (`scenario.json`), model alias `sonnet`, `--max-turns 25`, tools, embedder `hash`, forgetting default,
  Claude Code 2.1.296 (same binary as Round A), the harness code (`crucible/l8/` copied from `p11`; the only edit is
  the dirty check's output path, `e070824`). The agents are still **not** told about the staleness tools.
* **What changes:** the Plexus code the P arm's MCP server runs (the four commits above).
* **Order and concurrency:** seed 20261017 alone first (the cost gate); then the other four, two at a time (Round A
  ran three processes at a time: one per arm of a seed). FalkorDB container `plexus-db-66` (6366), one tenant per run.
* **Scoring:** the Round A scorer (`crucible/l8/score.py`, `report.py`), unchanged, over `runs/` with the new P runs
  and the copied B1/B0′ runs; audit Q1-Q3 run for the new P runs only (the B1/B0′ audit results are Round A's).
* **Verdict rule (stated now):** the Round A ordering on the headline composite was **B0′ ≤ P < B1** (pooled
  stale-act rate 2.4% ≤ 4.5% < 5.7%). It "changes" if the post-fix P pooled stale-act rate is ≤ B0′'s 2.4% or ≥ B1's
  5.7%; any separation claim uses the pre-registered exact permutation test on seed-level rates (separated = p ≤ 0.05
  and non-overlapping seed ranges). History recall (of 15), tasks done, tokens per correct action, contradiction
  detection and audit Q1-Q3 are reported next to it with the Round A values; nothing is dropped.
* **Not a clean replication, said up front:** Round A P ran in parallel with its seed's B1 and B0′ runs on
  2026-10-16; this round runs later, on a changed product, with sampling noise (`claude -p` has no seed). A difference
  of a few stale actions is within run-to-run noise at n = 5.

### 1.6 Budget (projected before the first call)

Round A P cost $8.14 for 5 runs ($1.49-$1.86; the full 16-task run cost $1.68, 22 turns). Post-fix the P runs should
reach `t16` more often (+0-2 turns) and every recall returns up to 20 facts instead of 8 (~10 KB more tool output
per recall, ~25 recalls per run: roughly +$0.4 per run in cache writes and reads). **Projection: ≈ $2.2 per run,
≈ $11 for 5 (range $9.5-$12.5)**, under the $12 stop line. Rule: after seed 20261017, re-project from its real cost;
if 5 × (its cost) > $12, run only as many further seeds as fit under $12 and report the round as incomplete (never
padded). Spend is the sum of `total_cost_usd` of every `claude -p` process, including any discarded run.

## Part 2. Results (appended after the runs; Part 1 unchanged)

### 2.1 Runs and spend

Five P runs, all `completed`, 22 turns each, one `claude -p` process per turn, no discarded runs. Cost per run
$2.09 (seed 20261017, the cost gate; re-projection 5 × $2.09 = $10.44 < $12, so the other four ran), $1.85, $1.91,
$1.92, $1.85: **total $9.62** (projection was $11). The audit (Q1-Q3) of the P runs reads the graph directly, $0.
B1 and B0′ audits are Round A's (not re-run: B0′'s audit calls an LLM reader). Scored with the Round A scorer at
this commit (`python -m plexus.crucible.l8.report --out plexus/demo_data/crucible/l8_postfix`; the B1/B0′ metrics it
rewrote are byte-identical to Round A's) and `python -m plexus.crucible.l8.compare_a2` →
`plexus/demo_data/crucible/l8_postfix/compare_a2.json`.

### 2.2 Metrics: post-fix P next to the unchanged Round A arms (5 seeds each, pooled unless noted)

| Metric | **P after fixes (A2)** | P Round A | B1 SQLite + MCP (Round A) | B0′ Claude Code, own files (Round A) |
|---|---|---|---|---|
| Stale-act rate (headline) | **4.08%** (13/319) | 4.49% (14/312) | 5.72% (19/332) | **2.42%** (6/248) |
| Wilson 95% | 2.4-6.9% | 2.7-7.4% | 3.7-8.8% | 1.1-5.2% |
| Seed rates (min / median / max) | 1.5 / 4.6 / 7.9% | 1.5 / 4.9 / 8.7% | 1.5 / 4.6 / 10.5% | 0 / 0 / 8.3% |
| Step repetition | 0.0% | 0.3% (1 event) | 0.0% | 0.0% |
| **History recall (long-horizon facts found, of 15)** | **15/15** | 3/15 | 5/15 | 15/15 |
| Tasks done (of 16 per seed) | **16,16,16,16,16** | 14,14,14,16,14 | 16 × 5 | 16 × 5 |
| Tasks failed for "memory has no such fact" (`fail_task` on t13) | **0** | 4 of 5 seeds | n/a (no such tool; 0 of 5 seeds missed t13) | n/a (0) |
| Tokens per correct action (raw) | 89,521 | 85,840 | 34,248 | **22,190** |
| Tokens per correct action (cost-weighted) | 14,348 | 12,878 | 6,421 | 7,345 |
| Cost for 5 runs (notional) | $9.62 | $8.14 | $5.61 | $6.12 |
| Contradiction X1 surfaced at write | 5/5 | 5/5 | 5/5 | 0/5 |
| Contradiction X2 surfaced at write | 5/5 | 4/5 | 5/5 | 0/5 |
| Provenance (acknowledged writes with a record) | 210/210 | 209/209 | 210/210 | n/a |
| Kills recovered / finished units repeated after a kill | 15/15, 7 of 8 | 12/12, 5 of 5 | 15/15, 9 of 9 | 15/15, **0 of 9** |
| Time to notice a change, level 1 median (censored) | 3 turns (4) | 7.5 (11) | 3 (4) | 2 (2) |
| Audit Q1-Q3 (sum over 5 seeds, of 15) | 9 | 9 | 8 | 3 |

Separation tests (pre-registered exact permutation on seed-level stale-act rates, Round A scorer): P(A2) vs B1
p = 0.52, ranges overlap; P(A2) vs B0′ p = 0.44, ranges overlap. **Nothing is separated.**

### 2.3 Verdict on the ordering

**The ordering did not change: B0′ (2.4%) ≤ P (4.1%) < B1 (5.7%), with no pair statistically separated.** By the
Part 1 rule, "changed" needed P ≤ 2.4% or ≥ 5.7%; P moved from 4.5% to 4.1%, one stale action fewer out of ~315, inside
run-to-run noise.

What the fixes did change, and it is large: the history-recall failure is gone. Round A P recalled 3 of 15
long-horizon facts and four of five seeds gave up on `t13` with "team memory has no S07 billing cycle"; post-fix P
recalled 15/15 and finished all 16 tasks on every seed, the same as B0′. That was the defect the synthesis §3 blamed,
and it was real, but it was not what drove the stale-act rate: the stale actions in L8 come from values that changed
mid-run in the repo (the fault schedule), and P's agents still act on a remembered value after the repo changed about
as often as before. The scorer's post-hoc variants say the same (e.g. seed 20261021: P 5 of 63 dependent actions stale,
B0′ 2 of 51, B1 5 of 69).

Where P is now level or better: tasks done (= B0′, > Round A P), history recall (= B0′, > B1), contradiction detection
at write (= B1, ≫ B0′, which detects none), provenance (complete), audit questions (9/15 vs B1 8, B0′ 3), time to notice
(= B1, slightly behind B0′). Where it still loses: stale-act rate (behind B0′, not significantly), tokens per correct
action (4× B0′, 2.6× B1, and slightly worse than before because recall now returns up to 20 facts), and redoing
finished work after a crash (7 of 8 units repeated; B0′ 0 of 9, B1 9 of 9).

### 2.4 Caveats

n = 5 seeds per arm; `claude -p` has no seed; one scenario family, one model (Sonnet), synthetic sentinels; the P runs
ran a day after the baselines and two at a time instead of three. The agents were not told about the staleness tools
(as in Round A), so Fix 3's change is not exercised by this benchmark; Fix 2 shows only as complete provenance (it
already was 209/209 in Round A: the orphan window needs a kill inside a millisecond-wide gap, which the kill tests in
Part 1 measure directly).
