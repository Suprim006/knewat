# Numbers status: which published numbers are valid for the current build

Written 2026-10-18 on branch `stale-flags`. Nothing was deleted: every number below stays reproducible at the build it was measured on.

**Current build** = `main` @ `7618d18` (git tag `pre-cleanup`). A number is **CURRENT** only if it was measured on `7618d18`, on a tree
byte-identical to it, or is a structural fact of the tree (tool count, query-file count, the immutable recordings). Everything else that was
measured on an earlier build is **STALE**, meaning *not valid for the current build until re-run*, even when a later re-run reproduced it on a
near build (that goes in the last column as 'last reproduced on'). **STALE, build unknown** means no commit is recorded for the measurement.
A stale number is not necessarily wrong; it is unverified for this build. Several were reproduced on later builds (last column), and a few moved
(the L5b noise share, the L6-C `hit_any`): those are called out.

**Tally:** 69 rows: 9 CURRENT, 56 STALE, 4 STALE with unknown build (G9 added with the render-demo merge). Section-level rows are used for the long BASELINE result sections.

Builds are short commit ids, all ancestors of `main`; `git show <id>` and `git checkout <id>` work in this repo. Branch names in parentheses are where
the commit was made. 'Envelope' means the commit recorded in the result's own `results.json` / `run.json`.

## How to reproduce a stale number

1. Check out the build in its own worktree: `git worktree add ../wt-repro <build>` (for the state just before the cleanup of dead code: `git worktree add ../wt-repro pre-cleanup`).
2. Start a private FalkorDB 6.0.2 with `bash scripts/agent_db.sh <slot>`, make a venv (`cd plexus && UV_PROJECT_ENVIRONMENT=.venv-repro uv sync`) and run the layer with the command in the cited BASELINE section.
3. Compare with the cited result file under `plexus/demo_data/crucible/` (ids are random UUIDs, so the second digit of ranking numbers varies; latencies vary about 2x between runs).

**Arms removed in the cleanup (2026-10-18):** the L5b / hub arms `sep+add`, `on-mult`, `sep-entity`, `sep-flat` and the post-hoc X1 (`PLEXUS_KW_BYPASS=value`) behind rows E3, E5, E6 and E8 no longer exist in the tree (their switches `PLEXUS_ACT_MODE=add`, `PLEXUS_ACT_CUES=entity`, `PLEXUS_KW_BYPASS=value` were removed). Arm removed; reproduce at `pre-cleanup`. The `off`, `kw-fix`, `sep` and `sep+mult` arms are unchanged.

| Kind | Layers | Cost | Command (from the repo root; DB port as above) |
|---|---|---|---|
| Deterministic, no LLM | L1, L4, ablation | $0, about 24 min (`--quick` about 2 min) | `docker compose --profile bench run --rm crucible all` |
| Deterministic, no LLM | C7 extended, B1h, L5a / L5b / hub, L6 A B D E F, L6-C, L7, t8 replay, recall bench | $0 | `python -m plexus.crucible.cli l1 --tests C7X ...`, `python -m plexus.crucible.l2.sql_run`, `python -m plexus.crucible.l5 [--only staleness\|forgetting\|hub]`, `python -m plexus.crucible.l6.run det\|conc\|crash\|postfix`, `python -m plexus.crucible.l8.recall_bench`; exact flags in each BASELINE section |
| LLM answers cached | L2, L2-scale | $0 from the cache (byte-reproducible); a cold run is about $5.5 and $6 of subscription | `python -m plexus.crucible.l2.run run --mode full`, `python -m plexus.crucible.l2.scale_run run --mode full` |
| Paid (`claude -p`) | L3 pilot, L6 pilot, L8 rounds, real runs | L3 $1.70, L6 pilot $7.09, L8 round A $21.87, A2 $9.62 | `python -m plexus.crucible.l3.run`, `l6.pilot`, `l8.run`; budgets and caps are in the pre-registrations. Not re-run for this flagging. |

## Summary by layer

| Layer | Measured on | Status | Last reproduced on |
|---|---|---|---|
| Test suite (Python) | `integ` tree = `7618d18` | CURRENT (1825 passed, 2 skipped) | - |
| Tool count 45, query files 114, recording inventory | structural | CURRENT | - |
| t8 replay and P13 PROFILE (new column) | `732016e` / `134c3a0`, product code identical to `7618d18` | CURRENT | - |
| Live ablation 6 of 6 / 2 of 2 | test in the suite on the current tree | CURRENT | - |
| L1, L4, Crucible ablation | `84763aa` | STALE | never re-run |
| L2, L2-scale | `4ac62a8`, `31b15df` | STALE | never re-run (cached answers, $0 re-run possible) |
| L3 pilot | `35109db` (envelope has no commit) | STALE | never |
| B1h, C7 extended | `5c3073a`, `aee7ee8` (envelopes have no commit) | STALE | never |
| L5a staleness | `75bd122` | STALE | never |
| L5b floor 0.5 / 0.9 | `75bd122`, `92c9bd7` | STALE | `3017ad7` (recall@1 65.0%, recall@5 95.7%) |
| L5b D-013, predicate cue, SQL arm, audit-fix re-run | `3017ad7`, `468601e`, `2d0ec96`, `0111b3a`, `df7333f` | STALE | `ae17aee` (recall@1 / @5 / displacers reproduce; noise share moved to 32-42%) |
| L6 A, B, D, E, F | `ae9d208`, `4e92938` (p9a) | STALE | `f966146` (recall-check, same verdicts); `47dd26a` (integ A / B / F) |
| L6 post-fix, p9f-b section | `a58b783`, `740b94e` | STALE | `47dd26a` (integ) |
| L6 pilot (LLM) | `dc83183`..`5871d30` | STALE | never (paid) |
| L6-C multi-hop | `65fbc40` | STALE | `f966146` (strict 0/75 holds; `hit_any` moved 11/6/1 -> 23/9/0) |
| L7 (P10) | `b4a4dcf`..`15b71a5` (p10) | STALE | never |
| L8 round A, A2, token fixes | `3b50242`..`34800ed` (p11); `bbfdea7`, `60903f2` (p12) | STALE | never (paid); recall bench `f966146` |
| Recall-check (BASELINE s1-s8) | `ae17aee`, `f966146` (recall-check) | STALE | latest benchmark measurements of the merged lineage |
| Test counts 1512 / 229 / 55 and earlier | `p9int` and earlier | STALE | Python superseded by 1825; View and guard counts not re-run |
| Deployment, fresh-clone timing | `c9234d8`, `p5-int` | STALE | never |
| Recorded runs: cost, turns | recordings of 2026-10-15 / 16 | STALE | - |

## Every headline number

### A. Test suite, tool and query counts, the recorded runs

| ID | Claim | Value | Stated in | Measured on | Status | Last reproduced on |
|---|---|---|---|---|---|---|
| A1 | Full Python suite on the current build | 1825 passed, 2 skipped | commit message of `7618d18` (no document quotes it yet) | `integ` tip `5e34e85`; its tree equals `7618d18` (`git rev-parse integ^{tree} main^{tree}` match) | CURRENT | - |
| A2 | MCP tool count | 45 | README (Architecture, Bring your own agent), docs/mcp.md, REPORT s4 | structural: `len(plexus/tests/mcp/snapshots/tools.json)`, checked by `verify_readme.py` on every run | CURRENT | - |
| A3 | Cypher query files | 114 | README (Cypher queries, Repo layout) | structural: `plexus/queries/**/*.cypher`, checked by `verify_readme.py` on every run | CURRENT | - |
| A4 | Recorded Acme run, counts: nodes, edges, labels, edge types, steps, sessions | 247 / 708 / 14 / 26 / 83 / 16 (5 Episode) | README (What it does, Graph model, Setup), REPORT s6.1, TESTING, demo.md | structural: properties of the immutable recording `acme-claude-sonnet` (`meta.json`, `calls.json`), checked by `verify_readme.py` on every run | CURRENT | - |
| A5 | Tools driven by a real `claude -p` run | 14 of 45 (11 in the Acme run, 3 more in the physio run); REPORT s9.4 says 18 of 45 (also counts the L6 pilot's read-only set) | README (Testing), TESTING s1 and s4, REPORT s9.4 | structural: derived from the recordings' call lists | CURRENT | - |
| A6 | Live ablation on a scripted run: features broken, controls unaffected, tasks claimable without `DEPENDS_ON` | 6 of 6, 2 of 2, 11 of 12 | README (Why FalkorDB), demo.md, TESTING owner step 10 | asserted by `plexus/tests/demo/test_ablation.py` in the 1825-pass suite on the `integ` tree (identical to `7618d18`) | CURRENT | - |
| A7 | t8 replay ($0, scripted): quarantine(memo) hides C2 and C3 and keeps C1 and P1; forget(memo) forgets C2 and C3 and unlinks C1; the single-source control hides C1 | see `results.md` | `plexus/demo_data/crucible/t8replay/results.*`, D-015, PLAN | `732016e` (branch `multisource`, 2026-10-18); `plexus/src` and `plexus/queries` at `732016e` are identical to `7618d18`; the branch tip `0b98c36` has the same tree as `main` | CURRENT | - |
| A8 | t8 replay baseline column (the same script on the pre-P13 tree) | C1 hidden, `source_ids` dropped | `t8replay/before_integ_1f9a8fa.*` | `1f9a8fa` (`integ`, before P13): a comparison control, kept as the pre-registered counterfactual | STALE | n/a (a control by design) |
| A9 | P13 PROFILE records, `lineage/quarantine`, `forget_source`, `release_quarantine`, `impact_source` at N = 1,000 / 5,000 (new column) | e.g. quarantine 26,071 records / 43 ms and 130,071 / 456 ms | `t8replay/profile.txt`, D-015 | `multisource` working tree, committed in `134c3a0`; product code identical to `7618d18` (records are deterministic, milliseconds vary about 2x per the file) | CURRENT | - |
| A10 | Same file, old column (`integ` `1f9a8fa`) | e.g. quarantine 20,064 records / 27 ms | `t8replay/profile.txt` | `1f9a8fa` (`integ`, before P13) | STALE | n/a (comparison column) |
| A11 | Python / View / deploy-guard tests at the last documented gate; ruff file count | 1512 passed (1 skipped), 229 View, 55 guard, ruff clean on 326 files | README (Testing), TESTING s1 row 2, REPORT s4 ('1512 Python and 229 viewer tests'), verify_readme.py pins the 1512 / 229 / 55 strings | branch `p9int` (merged as `efc1c49`), 2026-10-16 | STALE | Python count superseded by A1; the View (229) and guard (55) counts have not been re-run since |
| A12 | Earlier suite counts | 149 (P1), 328 (P2), 1168 (P7-int), 223 View (p8d) | REPORT s4.1 phase table, PLAN, AI_USAGE | the phase gates, 2026-10-15 / 16 | STALE | - |
| A13 | Suite counts on the recall-check line | trials-int `76da7d7`: 1698 passed, 1 skipped; recall-check `f966146`: 1703 passed, 1 skipped; p10 L7 tests: 50 passed, 1 skipped | BASELINE 'Recall-check results' s8, INTEG_MERGE, TRIALS_INT_MERGE | `76da7d7`, `f966146`, `integ` merge of p10 | STALE | superseded by A1 |
| A14 | Recorded Acme run, cost and turns: 16 `claude -p`, 95 turns, 0 permission denials, $0.698 notional, token counts | as listed | REPORT s6.1, TESTING s1 row 4, demo.md | recorded 2026-10-15T02:23+0545 on the P3-F demo build (`03c3a6a` added the recording) | STALE | - |
| A15 | Physio staleness real run: 1 fact flagged, 3 decisions, `claude -p` 5 turns / 21 s / $0.04 (recording: 10 turns, $0.2165) | as listed | README (Memory that notices change), REPORT s7.3, staleness.md 'Real run' | recorded 2026-10-16T02:24+0545, added in `a7b8226` (p7-int) | STALE | - |
| A16 | Total LLM spend across demo and benchmarks | about $15 notional | REPORT s9.4 | an aggregate over many builds; not tied to one commit | STALE, build unknown | - |
| A17 | Size of the code base | ~44,000 lines Python (~30,000 Crucible), ~12,700 TypeScript; 114 query files; 45 tools; 1799 Python + 227 viewer tests | REPORT s4 | counted on main @ 9514a03 (2026-10-18). Not a measurement. | CURRENT | - |

### B. L1, L4 and ablation (one compose run)

| ID | Claim | Value | Stated in | Measured on | Status | Last reproduced on |
|---|---|---|---|---|---|---|
| B1 | L1 correctness C1-C8, 10 seeded runs per case, 4 arms | all four arms 0 violations (200 workers: 0 double claims, 0 lost updates) | README (Benchmark results L1), REPORT s6.2, BASELINE 'Results', TESTING s2 | `84763aa`, run `20261014T204729Z` (compose, 2026-10-14/15) | STALE | - |
| B2 | C7 paraphrases: B0/B1 catch 0%; B2 and P miss 25% (30 of 120 pairs) | 25% miss | README (L1 row), REPORT s6.2, BASELINE 'Results' | `84763aa` | STALE | superseded in kind by C7 extended (D1), not by a re-run of C7 |
| B3 | C2 kill the claimer: slowest reclaim | 1.27-1.52 s against a 2.0 s bar | REPORT s6.2, BASELINE 'Results' | `84763aa` | STALE | - |
| B4 | C5 tenant probes | 0 rows leaked | README (What it does), BASELINE 'Results' | `84763aa` | STALE | - |
| B5 | L4 claim latency, p50 / p99 per arm at 1, 10, 50, 100, 200 workers (table); SQLite faster at every worker count; Plexus server time 0.5 ms (1 worker), 3.6 ms (200) | 0.10 vs 1.75 ms (1 worker), 0.82 vs 570.9 ms (200), p99 2.18 s vs 1.86 s (200) | README (L4 row), REPORT s6.4, BASELINE 'Results', TESTING s2 | `84763aa` (200-worker cells re-run after the connection-pool fix, same commit) | STALE | - |
| B6 | L4 tenant sweep, 50 workers: Plexus 678 / 1025 / 1174 ops/s on 1 / 4 / 16 graphs (+73%); SQLite 1103 / 1480 / 500 | as listed | README (L4 row), REPORT s6.4, BASELINE 'Results', BLOG_DRAFT (not edited here) | `84763aa` | STALE | - |
| B7 | L4 recall throughput: shared embedder ceiling; P recall 36-60 ops/s; B1 BM25 350-525 ops/s; audit cost 2-3x at 1-50 workers | about 47 embeds/s | REPORT s6.4 and s9.3, BASELINE 'Results' | `84763aa` | STALE | - |
| B8 | Query tuning during review: sibling expansion 80,000 records / 197 ms at 10k facts -> 40 records / 2.1 ms; `assert_fact`, `fact_history` 10,000 -> 5-6 records | as listed | REPORT s6.4, queries.md | P5 core-fix branch (merged `d3f3847`, 2026-10-15); exact commit not recorded | STALE, build unknown | - |
| B9 | Unfiltered Explorer query after the `created_at` indexes | 3.8 -> 5.8 ms at 4.2k nodes | TESTING s4, REPORT s9.3 | `p5-int` (2026-10-15) | STALE | - |
| B10 | Crucible ablation: edge-dependent capabilities broken / controls unaffected; C4 started-before-dependency; C8 forgotten facts still returned | 7 of 7 / 5 of 5; 181; 60 (0 and 0 intact) | README (Why FalkorDB, Benchmark table), REPORT s3.4 and s6.3, BASELINE 'Results', TESTING | `84763aa`, run `20261014T204729Z` | STALE | - |
| B11 | Live ablation, quoted output on the Sonnet recording: `why` 3 facts / 2 agents / 3 sources -> 0; `knew_at` 5 -> 0 | as listed | README (Why FalkorDB), demo.md | P3-F demo build (`50bf55e` merge); 6 of 6 / 2 of 2 is A6 | STALE | A6 re-asserts the 6 / 2 verdict on the current tree, not these counts |
| B12 | Combined results file `latest-all.json` (what the View's Results page serves) | mixes the layers above and C-F | README (Benchmark results), TESTING s2 and s4 | `plexus/src/plexus/crucible/results/latest-all.json`: its `environment.git_commit` is `84763aa`; each layer keeps its own build (see the rows of this file) | STALE | - |

### C. L2, L2-scale, L3, B1h

| ID | Claim | Value | Stated in | Measured on | Status | Last reproduced on |
|---|---|---|---|---|---|---|
| C1 | L2 accuracy, 43 questions: P 43, B0 43, B1 43, B2 40 (93.0%); whole-reply-JSON variant B0 36, B1 38, B2 39, P 43 | tie | README (L2 row), REPORT s6.5, TESTING s2, `verify_readme.py` pins the strings | `4ac62a8`, run `20261014T215450Z-full` | STALE | -  (answers are cached in `l2_cache/`, so a re-run is free and byte-reproducible; not re-run on `7618d18`) |
| C2 | L2 tokens, cost, latency per question | B0 15,930 tokens / $0.062 / 5.75 s; B1 13,406 / $0.052 / 5.29 s; B2 4,092 / $0.015 / 5.76 s; P 0 / $0 / 2.5 ms | README (L2 row), REPORT s6.5, TESTING s2 | `4ac62a8` | STALE | - |
| C3 | L2 at scale, 36 questions: correct, Wilson 95%, paired sign test, context ratio | P 36/36, B1 32/36, B0 30/36, B2 23/36; P vs B0 6-0 p = 0.031, P vs B1 4-0 p = 0.125, P vs B2 13-0 p < 0.001; 10.4-16.6x the cap | README (L2 at scale row), REPORT s6.6, BASELINE 'L2-scale results', TESTING s2 | `31b15df`, run `20261014T224309Z-full` (pre-registration `cba0a5a`) | STALE | -  (cached answers, $0 re-run; not re-run on `7618d18`) |
| C4 | L2 at scale, cost and latency | B0/B1 about 20-22k tokens and $0.08-0.09 per question, about 5 s; P 0 tokens, 7.5 ms; experiment $6.49 for 108 calls | README (L2 at scale row), REPORT s6.6 | `31b15df` | STALE | - |
| C5 | L3 end-to-end pilot, n = 1 per arm: tasks, tool calls, tokens, cost, wall time | 12/12 each; tokens 1,723,458 (P) vs 981,150 / 993,051; $0.69 / $0.52 / $0.49; 420 / 316 / 324 s; P about 75% more tokens | REPORT s6.7 and s9, README (Methodology limits) | no commit in the envelope; results added in `35109db` (2026-10-15, P4-I) | STALE | -  (paid, not re-run) |
| C6 | B1h hand-written SQL control: L2 and L2-scale | 43/43 and 36/36, 0 LLM calls, 34 operations | README (B1h row), REPORT s8.1, BASELINE 'B1h', TESTING s2 | no commit in the envelope; results added in `5c3073a` (p9a, 2026-10-16) | STALE | -  ($0; `python -m plexus.crucible.l2.sql_run`, not re-run on `7618d18`) |

### D. C7 extended

| ID | Claim | Value | Stated in | Measured on | Status | Last reproduced on |
|---|---|---|---|---|---|---|
| D1 | C7 extended, 226 pairs: false merges of P and B2 on the 150 pairs that must stay apart; heavy / light / unit auto-merge; auto and surfaced recall of the 76 true paraphrases | 0 and 68; heavy 10 of 24 auto, 19 of 24 surfaced; light 10 of 20; unit 11 of 12; 51/76 = 67.1% auto, 70/76 = 92.1% either | README (C7 extended row), REPORT s8.4 and s9.3, BASELINE 'C7 extended results', TESTING s2 | no commit in the envelope; code at the commit after the pre-registration `262705e`, results added in `aee7ee8` (p9c, 2026-10-16) | STALE | -  ($0; command in the BASELINE section; not re-run on `7618d18`) |

### E. L5 staleness, forgetting, pattern separation (all $0, fastembed)

| ID | Claim | Value | Stated in | Measured on | Status | Last reproduced on |
|---|---|---|---|---|---|---|
| E1 | L5a staleness, 60 facts, 21 commits: S symbol-level 19 TP / 0 FP; F file-level 19 TP / 106 FP (precision 15.2%); N 0% recall, 19 of 19 returned unflagged; stale unflagged 0 for S and F | as listed | README (Memory that notices change), REPORT s7.3, BASELINE 'L5 results', TESTING owner step 14 | `75bd122` (p7-int), run `20261015T202726Z` | STALE | - |
| E2 | L5b first default (floor 0.5): recall@5 98.6% -> 73-75%, 7-8 of 80 critical probes lost (10-12 with sweep) | failed its pre-registered criterion | README (Forgetting), REPORT s7.3, BASELINE 'L5 results', forgetting.md | `75bd122` and `75bd122-dirty` (3 runs, 2026-10-15) | STALE | - |
| E3 | L5b confirmatory, floor 0.9: recall@5 96.4% (off 98.6%), recall@1 63.6% (75.7%), noise share 24.0% -> 15.1%, critical loss 0, real sweep recall@5 88.6% | as listed | README (Forgetting), REPORT s7.3, BASELINE 'L5b confirmatory result', forgetting.md, TESTING owner step 13-14 | `92c9bd7` (clean), run `20261015T205321Z-floor09` | STALE | `3017ad7` (`on-mult`): recall@1 65.0%, recall@5 95.7-96.4%, noise 14.9% (ids differ between plays) |
| E4 | Post-hoc floor sweep 0.8 / 0.9 / 0.95 | labelled post-hoc | BASELINE 'L5 results' | `75bd122-dirty` | STALE | - |
| E5 | D-013 pattern separation (P1) and additive forgetting (P2): `sep` 85.7% recall@1 / 100% recall@5, cross-entity displacers 13 -> 0, ceiling 85.7%; `sep+add` 70.0% (failed); `on-mult` 65.0%; `kw-fix` 77.1%; `sep+mult` 85.0% / 100% / 22.1% | as listed | README (D-013 paragraph), REPORT s7.5, BASELINE 'L5b-D013 results', forgetting.md, DECISIONS D-013 | `3017ad7` (`feature/neuro-memory-research`), runs `20261017T0822*-d013-*` (3 runs) | STALE | recall@1 85.7 / 85.0 / 85.7%, recall@5, critical loss 0 and displacers 0 reproduced on `ae17aee` (recall-check, merged lineage); noise share did not (E8) |
| E6 | Predicate cue, registered run: falsified; single-cue `sep-entity` noise 28.4%, `sep` at 0.6 / 0.4 noise 32.3% (43.6%); hub variant 100% vs relevance-only 97.5% | as listed | README (D-013 paragraph), REPORT s7.5, BASELINE 'Predicate cue results', DECISIONS | `468601e`, runs `20261017T1255*-pc-*` | STALE | - |
| E7 | Predicate cue confirmatory: `sep+mult` at 0.03 / 0.02 (the shipped default then): recall@1 85.7%, recall@5 100%, noise share 20.6% (N = 5) / 20.9% (N = 15), critical loss 0 | as listed | README (D-013 paragraph: 'noise share 20.6-20.9%'), REPORT s7.5, BASELINE 'Predicate cue confirmatory results', forgetting.md | `2d0ec96`, runs `20261017T1306*-pcc-*` | STALE | `df7333f` (audit fixes, noise 22.1 / 19.9 / 21.0%); `1ddeb13` (control on old main, 22.1 / 20.0 / 21.6%). NOT reproduced on the merged lineage (E8) |
| E8 | L5b `sep+mult` on the merged build (trials-int + recall-check): lexical fusion off (now the default) noise share 32.3 / 41.6 / 33.3%; fusion on 42.7 / 60.1 / 41.6% and one critical probe lost; post-hoc attribution X1-X5 (no cause found for +10 to +22 points) | as listed | BASELINE 'Recall-check results' s1 and s5, REPORT s7.5 (merged-build note), DECISIONS D-013 amendment 3 | `ae17aee` (registered), `93c1b45`, `9f50190`, `00ccc82` (post-hoc), `3521a0c` and `1ddeb13` (controls), branch `recall-check` | STALE | this is the closest measurement to the current default; the final default (`f966146`) was checked by the L8 bench, L6 and the tests, not by L5b |
| E9 | L5b with the hand-written SQL arm (B1h-L5): `sep+mult` recall@1 82.9 / 85.7 / 84.3%, recall@5 100% on both arms; 92 lines of SQL vs 104 of Cypher; 17.8 vs 30.6 ms per probe | tie on quality | README (L6 row), REPORT s7.5 and s8.2, BASELINE '5.4 results' part 1 | `0111b3a` (N = 5, N = 15), `65fbc40` (burst), runs `20261017T1029*-sql-*` | STALE | - |
| E10 | Audit-fixes re-run (L5b `sep+mult`): recall@1 85.7%, recall@5 100%, noise 22.1 / 19.9 / 21.0% | as listed | BASELINE 'Audit fixes re-run results' | `df7333f`, runs `20261017T1609*-afx-*` | STALE | reproduces E7 on old main |
| E11 | `fan_e` on a hub entity (GRAPH.PROFILE): records 61,295 -> 1,060 (1,000 facts), 305,295 -> 5,060 (5,000 facts); 289 -> 19.6 ms, 1,478 -> 34.2 ms | as listed | BASELINE 'Recall-check results' s6, DECISIONS D-013 amendment 3 | `76da7d7` before, `bc34bd2` after (branch `recall-check`) | STALE | - |

### F. L6 (beat-SQL families, product defects and fixes)

| ID | Claim | Value | Stated in | Measured on | Status | Last reproduced on |
|---|---|---|---|---|---|---|
| F1 | L6-A blast radius (24 questions, 51,424 facts): B1h 24/24 p50 56.8 ms; product `impact` before the fix 0/24 with 6 timeouts | tie with SQL; SQL faster at 5,000-fact blasts (192 vs 595 ms) | README (L6 row), REPORT s8.2, BASELINE 'L6 results' A | `9aa117c` and `ae9d208` (p9a, 2026-10-16) | STALE | post-fix rows 24/24, 24/24, 24/24, 18/24 reproduced on `a58b783`, `df7333f`, `47dd26a` (integ) and `f966146` |
| F2 | L6-B why-chain depth 2-12 (24 questions): B1h 24/24, P-tuned 24/24, `P-product-tool` 16/24 (depths 8, 12 fail at default depth) | tie once `depth` is passed | README (L6 row), REPORT s8.2, BASELINE 'L6 results' B | `ae9d208` | STALE | `47dd26a` (integ): 16/24, 20/24 with the p9f arm, 24/24 service; `f966146`: identical |
| F3 | L6-D cross-sprint aggregation (24 questions): 24/24 both, SQL 4.6x faster | tie | README (L6 row), REPORT s8.2, BASELINE 'L6 results' D | `ae9d208` | STALE | `f966146`: 24 and 24 |
| F4 | L6-E consistent reads (10 runs x 6 s): 0 violations for every single-statement arm; level-wise traversal tears (e.g. P-levelwise 917 V1 / 1,091 V3 in 4,470 reads) | as listed | README (L6 row), REPORT s8.2, BASELINE 'L6 results' E | `ae9d208` (dirty tree) | STALE | `df7333f`, `f966146`: same verdicts, counts timing-dependent |
| F5 | L6-F crash-consistency, 200 SIGKILLs, arm P: 94 of 1,240 (7.6%) records without Step/WROTE before the fix; 0 of 1,842 after | Plexus lost, then fixed | README (L6 row), REPORT s8.2 and s8.3, BASELINE 'L6 results' F and 'after the fixes', TESTING s2 | `4e92938` (before), `a58b783` (after, p9int) | STALE | 0 orphans on `740b94e` (p9f-b), `df7333f`, `47dd26a` (0 of 1,269), `f966146` (0, 1,975 acknowledged writes) |
| F6 | L6 LLM pilot: 88 `claude -p` calls, $7.09, 8 questions per family | B1a 24/24, B0g 24/24, B0r 2/24, Plexus MCP tools 10/16 | README (L6 row, `verify_readme.py` pins the string), REPORT s8.2, TESTING s2, BASELINE 'L6 results' | `dc83183`, `40fcafe`, `5871d30` (p9a, 2026-10-16, pilot runs) | STALE | -  (paid; the MCP-tool arm ran before the `impact` and depth fixes) |
| F7 | L6 after the P9-int fixes: `impact` 24/24 via the service, p99 626 ms, 0.35 s at 5,000 facts; MCP tool 18/24 (2,000-id cap); `blocked_by_failure` 380 ms -> 2.2 ms | as listed | README (L6 row), REPORT s8.3, BASELINE 'L6 after the fixes', TESTING s2 | `a58b783` (p9int) | STALE | `47dd26a` (integ), `f966146` |
| F8 | L6 post-fix on branch p9f-b: six defects before / after (e.g. 5,000-fact `impact` 446-459 ms, torn reads 79/79 -> 0, F 0 of 2,723) | as listed | BASELINE 'L6 post-fix (P9-f, branch p9f-b)' | `740b94e` (`p9f-b`); the section says itself it describes p9f-b's build | STALE | ported subset re-measured on `47dd26a` (F9) |
| F9 | L6 on integ: A `P-product-tool-p9f` 24/24 (p50 10.4 / p99 689 ms), `P-product-service` 24/24, `P-product-tool` 18/24; B 20/24, 24/24, 16/24; F 0 orphans of 1,269, 0 lost of 1,205, `missing_derived_from` 0 | all registered expectations held | BASELINE 'L6 on integ: results', INTEG_MERGE | `47dd26a` (`integ`, clean), runs `20261017T2111*-postfix`, `T2124*-det` | STALE | this IS a re-run: it is the last time L6 A / B / F were measured on a tree close to current (integ tip `5e34e85` = `7618d18`'s tree came later) |
| F10 | L6-C multi-hop recall (44k facts, 75 questions): B1h and P-tuned 75/75, identical lists; SQL 3.3x faster at depth 3 (12.6 vs 41.3 ms); shipped `recall(hops)` strict 0/75; `hit_any` 11 / 6 / 1 (fastembed re-measure 3 / 1) | as listed | README (L6 row), REPORT s8.2 and s9.3, BASELINE '5.4 results' part 2 | `65fbc40` (dirty), re-run `d76c507`, runs `20261017T1039*-c` | STALE | strict 0/75 and 75/75 reproduced on `1ddeb13`, `ae17aee`, `f966146`; `hit_any` moved to 23 / 9 / 0 on `1ddeb13` and `f966146`, so the published 11 / 6 / 1 is stale on main itself |

### G. L7, L8, recall bench, research documents

| ID | Claim | Value | Stated in | Measured on | Status | Last reproduced on |
|---|---|---|---|---|---|---|
| G1 | L7 (P10) families G, H, I, J: e.g. I SQLite 0 partial close-outs in 200 kills vs product path 86; AOF replay crashed 10 of 11 restarts; H SQL faster in 9 of 11 cells (25-900x on traversals); G tenant create 9x, memory 4-15x; J SQLite 6-17x throughput, FalkorDB rejected about 90% at 1,000 sessions | as listed | BASELINE 'L7 / P10', P10_GRAPH_VS_SQL, GRAPH_VS_SQL_MECHANISMS_AND_OUTCOMES, blog `BLOG_SQL_VS_GRAPH.md` | branch `p10`: `b4a4dcf`, `dc0bda3`, `2ac5fb4`, `15b71a5` (2026-10-16) | STALE | -  ($0; not re-run after the merges) |
| G2 | L8 round A, 5 seeds x 3 arms, $21.87: stale actions P 4.5% vs B1 5.7% (p = 0.56), 2.51x tokens per correct action (2.01x billing-weighted); B0' 2.4% (p = 0.40); P finished 14/16 tasks in 4 of 5 seeds | tie on stale actions, loss on cost | BASELINE 'L8 round A results', L8_LONG_HORIZON_OUTCOMES, GRAPH_VS_SQL_MECHANISMS_AND_OUTCOMES | `3b50242` (envelope); per-seed runs `4d56266`, `c296f78`, `021e118` (dirty), `34800ed` (branch `p11`) | STALE | P arm re-run on p12 (G3); B1 and B0' unchanged |
| G3 | L8 round A2 (P12 post-fix), 5 P runs, $9.62: 89,521 tokens per correct action vs B0' 22,190 (4x); 15/15 history facts found | as listed | L8_ROUND_A2_POSTFIX, L8_TOKEN_COST_P12 | `bbfdea7` (`p12`, dirty), recall before / after `2453a93` (dirty) | STALE | - |
| G4 | L8 token fixes, 3 P seeds, $4.14 (round total $4.58): tokens per correct action 95,092 -> 64,855, 86,237 -> 63,953, 92,943 -> 65,261 | as listed | L8_TOKEN_COST_P12 | `60903f2` (`p12`), `702501f` (recall bench, dirty) | STALE | - |
| G5 | L8 no-LLM recall bench (5 seeds, hash embedder, core toolset): replay calls that found their target; needed fact per task; canonical 1000/1000; mean response chars | 29/36 (`d6d30da`), 28/36 (`f5881c6`), 27/36 (`ae17aee`, `93c1b45`), 28/36 (`f966146`); needed facts 5/5, 5/5, 1/1; 5,333 / 5,766 chars | BASELINE 'Recall-check results' s2, TRIALS_INT_MERGE, L8_TOKEN_COST_P12 | builds as listed (branches `p12`, `trials-int`, `recall-check`) | STALE | `f966146` (28/36, needed facts unchanged); the replay count is documented as not stable (+-1) |
| G6 | Cypher audit: 111 files / 2,721 lines; PROFILE counts (e.g. `quarantine` 1,200 facts 1.5 s, 2,500 facts timeout) | as listed | CYPHER_AUDIT_SUMMARY, cypher-review/*.md | `e126875` (`feature/neuro-memory-research` head) | STALE | findings fixed later; re-measured as F7 / F9 / E11 for some |
| G7 | BEAT_SQL_ANALYSIS micro-probes marked [measured]; PRODUCT_FIXES_ANALYSIS probe timings | as listed | BEAT_SQL_ANALYSIS, PRODUCT_FIXES_ANALYSIS | 2026-10-16, before the P9 merges; no commit recorded | STALE, build unknown | - |
| G8 | Deployment: boot 5-14 s, peak 332 MiB (322 MiB `docker stats`), 40/40 checks, 510 MB image, 55 guard tests, restart 5.2-12.1 s | as listed | README (Live demo), REPORT s6.8, deploy.md | image contents of `c9234d8` (P6-deploy, 2026-10-15) | STALE (describes the MCP-bearing image, no longer deployed; D-016; reproduce at `7cca016`) | - |
| G9 | Render demo image without MCP: boot 3.8 s, peak 88 MiB cgroup (83 MiB `docker stats`), 36/36 `deploy/verify.py` checks, 447 MB image, restart 4.2 s, runaway Cypher query 408 after 3 s | as listed | README (Live demo), deploy.md | image built from the render-demo tree (base `7cca016`) on 2026-10-18 | CURRENT once merged | - |
| G9 | Fresh-clone `docker compose up`: 4 services healthy | 216 s | README (Setup), TESTING s1 row 1 | branch `p5-int` (2026-10-15) | STALE | - |
| G10 | Insert latency grows with the index set: 200 fact inserts 0.05 s on an empty graph, about 2 s at 8,000 facts (one probe) | as listed | REPORT s9.4 | a single probe, build not recorded | STALE, build unknown | - |
| G11 | Forgetting latency: 2,000 / 10,000 facts x 50 reads, server median 11.1 / 10.8 ms | as listed | forgetting.md | P7-K branch (`ad6f85c`, 2026-10-16) | STALE | - |

`README` = README.md, `REPORT` = docs/PLEXUS_REPORT.md (s = section), `BASELINE` = docs/BASELINE.md, `TESTING` = docs/TESTING.md. 'Stated in' lists the main places; docs/research/* repeat the same numbers.

## Documents that carry these numbers

| Document | Flag |
|---|---|
| README.md | banner under the intro, per-section markers |
| docs/BASELINE.md, docs/PLEXUS_REPORT.md | banner at the top |
| docs/TESTING.md, docs/deploy.md, docs/forgetting.md, docs/staleness.md | banner at the top |
| docs/research/: BEAT_SQL_ANALYSIS, CYPHER_AUDIT_SUMMARY, GRAPH_VS_SQL_MECHANISMS_AND_OUTCOMES, INTEG_MERGE, L8_LONG_HORIZON_OUTCOMES, L8_ROUND_A2_POSTFIX, L8_TOKEN_COST_P12, MEMORY_FORGETTING_IMPLEMENTATION_PLAN, P10_GRAPH_VS_SQL, PRODUCT_FIXES_ANALYSIS, TRIALS_INT_MERGE; cypher-review/{lineage,relay-staleness,view-activation}; neuro-memory/00-brief | banner at the top |
| docs/VIDEO_SCRIPT.md | **not edited** (strict beat / word checks), so it still shows these without a flag: beat 8 on-screen text (L1 all four arms 0 violations = B1; L2 at scale P 36/36, B1 32, B0 30, B2 23 and p = 0.125 = C3; L4 fastest median claim SQLite = B5; L5 symbol anchors 100% / 100% = E1; floor 0.5 failed, 0.9 confirmed = E2, E3) and the note on beat 7 (Sonnet, 5 turns, $0.04 = A15). The 247 nodes / 708 edges / 83 steps and the scripted tenant's 199 / 581 are structural (CURRENT). Add a banner or re-record before submission. |
| docs/BLOG_DRAFT.md, docs/blog/, docs/BLOG_SQL_VS_GRAPH.md | not edited (the owner's drafts). They quote B6 (tenant sweep 678 -> 1,174, SQLite 1,103 -> 1,480 -> 500), C3 (36 of 36, 32, 30), G1 (L7) and others: all STALE. |
| plexus-view Results page | serves `latest-all.json` (B12 plus C1-C6, D1, F1-F7) with no banner; code not touched here |
| docs/DECISIONS.md, docs/PLAN.md, docs/AI_USAGE.md | dated decision and phase records that cite the numbers above; not bannered, read them with this file |
| plexus/demo_data/**, plexus/src/plexus/crucible/results/** | published records, unchanged |
