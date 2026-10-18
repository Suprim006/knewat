# BASELINE.md: how we prove Plexus works (benchmark plan, "Crucible")

> **STALE (2026-10-18):** the numbers in this document were measured on builds before the current main (7618d18) and are not valid for it until re-run. Build per number: [docs/NUMBERS_STATUS.md](NUMBERS_STATUS.md).

Status: plan, written before the event (design notes are allowed under rule R5). Implementation starts after kickoff.
Related decisions: D-002 (Claude Code harness, no LLM in Plexus), D-003 (no Hermes in published runs), D-007 (change only the backend).

## 0. The principle: change only the backend

A claim like "Plexus does better than how Claude Code or Hermes coordinate" is only valid if **everything except the coordination and memory backend is identical**:

| Fixed across arms | Value |
|---|---|
| Agent harness | Unmodified **Claude Code** (`claude -p`, v2.1.296 or pinned), signed in with the owner's own subscription (D-002) |
| Model | One model for all arms. Default: Sonnet (decide at the pilot); record the exact model ID per run |
| Prompts and role definitions | Identical files. Only the tool descriptions in the MCP config differ |
| Tool API | Identical MCP tool names and signatures in every arm. Memory: `remember_episode`, `assert_fact`, `recall`, `forget_source`, `log_procedure_run`, `best_procedure`. Coordination: `claim_next_task`, `heartbeat`, `handoff`, `record_decision`. Lineage: `why`, `why_recalled`, `who_knew`, `as_of` |
| Scenario and seeds | Identical scripted scenario, fault injections and random seeds |
| Budgets | Same `--max-turns`, timeout and token budget per agent |

What changes is **the backend that implements the tool API**:

| Arm | Backend | Represents | Implementation notes |
|---|---|---|---|
| **B0 Files** | Markdown memory file + JSON task list **with file locking** + per-agent transcripts on disk | How Claude Code (CLAUDE.md, auto-memory, agent-team task list) and Hermes (MEMORY.md, kanban, files) coordinate today | Must be competent, not a strawman: atomic claims through a lock file or `os.replace`, append-only logs. "Why" and "as-of" questions are answered by an LLM reading the files |
| **B1 SQLite** | Tables + transactions (tasks, facts, decisions, edges stored as rows) | "Just use a relational database" | The honest rival for claims and leases. Provenance answered with recursive CTEs where feasible |
| **B2 Vector** | Embeddings over facts and logs (Mem0-style), same local embedding model as Plexus | Retrieval-based memory | "Why" and "as-of" answered by top-k retrieval plus an LLM |
| **P Plexus** | FalkorDB 6.0.2 graph per team/tenant | Our system | Deterministic Cypher for every tool |

If B0 or B1 also gets zero double claims, **we report that**. Plexus's claimed advantage must come from what a graph actually does better: provenance, time travel, dependencies, contradictions and isolation.

## 1. Layer 1: correctness under concurrency (deterministic, no LLM)

Agents here are **scripted Python workers** calling the same tool API, so this layer costs no LLM usage.
It runs inside the Docker compose network, with each arm in its own container (D-005).

| ID | Test | Metric | Pass bar |
|---|---|---|---|
| C1 | N workers (10, 50, 100, 200) race to claim M = 500 tasks | double claims, lost updates, tasks never claimed | 0 / 0 / 0 |
| C2 | Kill the claimer mid-task (SIGKILL) | time until the expired lease is reclaimed; orphaned tasks | all reclaimed within lease + 1 heartbeat |
| C3 | Many workers assert facts about the same entity and predicate at once | duplicate facts; contradictions missed | 0 duplicates; 100% of contradictions flagged |
| C4 | Dependency DAG (depth 5, fan-out 3): workers only take tasks that are ready | tasks started before their dependencies finished | 0 |
| C5 | Tenant isolation: tenant-A workers probe with B's IDs, guessed graph names and Cypher-injection strings | rows leaked across tenants | 0 |
| C6 | Supersede facts, then query "as of T" at 20 random T | wrong-version answers | 0 |
| C7 | Near-duplicate facts (paraphrases) written concurrently by different agents | duplicates stored instead of linked as `DUPLICATES` | ≤ the known paraphrase-miss rate, reported |
| C8 | Forget-by-source: delete a source, then probe recall | derived facts still returned | 0 |

Each test runs 10 times per arm with fixed seeds. We report counts, not averages, for any violation.

## 2. Layer 2: provenance and time questions (the headline result)

1. **Record one real multi-agent run per arm** using a scripted scenario with **seeded events** whose ground truth we know:
   - 3 Claude Code agents (planner, researcher, builder) on a small synthetic project (scenario at kickoff: a generic software team or the HR-ops skin);
   - seeded events: 6 decisions, 4 handoffs, 1 fact superseded mid-run, 2 conflicting facts, a dependency chain, and 1 agent killed and its work reclaimed.
2. **Ask about 40 questions** with exact-match ground truth (no LLM judge). Question families, about 6–8 each:

| Family | Example |
|---|---|
| Decision provenance | "Which facts was decision D3 based on, and which agent asserted each?" |
| Handoffs | "What artifacts did the researcher hand to the builder for task T4?" |
| Time travel | "What did the builder believe about the API version at step 12?" |
| Supersession impact | "Which decisions relied on a fact that was later superseded?" |
| Dependencies | "Which tasks are blocked if T7 fails?" |
| Contradictions | "Which current facts conflict, and who asserted each side?" |
| Recovery | "Which tasks were reclaimed after the builder died, and by whom?" |
| Memory currency and scope | "What is the current value of X for project P?" (after a supersede), "Did any fact from project Q appear in P's recall?" (must be no) |
| Cross-session recall | "What did the user ask for in session 1, and was it resolved?" (asked in session 3, after restarting every agent) |
| Procedures | "Which procedure has the best success rate for task type K?" |
| Forgetting | "After forgetting source S, which facts remain that were derived from it?" (must be none) |

3. **How each arm answers:**
   - **P:** one Cypher query per question.
   - **B0 / B1 / B2:** the **same LLM**, given that arm's artifacts (files, SQL with a schema description, or top-k retrieval) with an equal token budget (e.g. 32k context).
4. **Metrics:** exact-match accuracy per family, tokens per question, latency, estimated cost.
5. **The claim this supports** (illustrative numbers, not results): "*File- and transcript-based coordination, as used by Claude Code and Hermes, answered X% of provenance questions at Y tokens each; Plexus answered Z% with deterministic queries.*"

## 3. Layer 3: end-to-end team outcomes (real LLM agents, faults injected)

- **Setup:** the same 3-agent Claude Code team, scenario, model and budgets; only the backend changes (B0 vs B1 vs P; add B2 if budget allows).
- **Faults:**
  1. kill an agent at a random step;
  2. supersede a key fact mid-run;
  3. inject a conflicting fact from another agent.
- **Metrics,** mapped to the MAST failure taxonomy (Cemri et al., arXiv 2503.13657):

| Metric | MAST mode it reflects |
|---|---|
| Duplicated work (the same task done twice) | step repetition |
| Information lost at handoffs (required facts missing in the receiver's context) | withholding info / ignoring peers |
| Actions taken on stale or conflicting facts | proceeding on wrong assumptions |
| Recovery after the agent was killed (completed? time to recover) | missing completion recognition |
| Task completion and verification pass (scripted acceptance checks) | wrong / no verification |
| Total tokens, wall time | cost |

- **Runs:** at least **5 per arm**, fixed seeds. Report median and spread, because LLM runs are noisy, and keep every transcript.

## 4. Layer 4: performance and scale (scripted, inside Docker)

- Claim, heartbeat and recall latency (p50/p95/p99) and throughput as workers grow 1 → 200.
- **One graph vs many tenant graphs**: writes to a single graph run one at a time, so measure where the ceiling is and how spreading over graphs changes it.
- Report the **server-side `run_time_ms`** next to client-observed latency.
- Compare with B1 SQLite under the identical workload.
- Configure `FALKORDB_ARGS` explicitly (`TIMEOUT_MAX`, `MAX_QUEUED_QUERIES`, `RESULTSET_SIZE`, `QUERY_MEM_CAPACITY`) and record them in the results.

## 5. Real Claude Code / Hermes case study (qualitative, optional)

- Run **actual Claude Code agent teams**, with their native coordination and no Plexus, on the Layer 2 scenario 3–5 times. Then ask them the Layer 2 questions and record the answers.
- Label it **"qualitative case study"**, not a benchmark: product internals change between versions and can't be controlled.
- **Hermes is excluded from published runs** (D-003). We may cite its *documented* behaviour and our first-hand observations from building this project, labelled as such.
- Credit what they do well: human-readable memory, zero infrastructure, Hermes kanban's atomic claims.

## 6. Honesty rules for reporting

1. Publish the harness, scenario seeds, raw results and transcripts, plus `METHODOLOGY.md` with the limits: synthetic data, ~40 questions, one model, one scenario, a single-node database.
2. **No LLM-as-judge for headline numbers.** Use exact-match ground truth from the scripted scenario. The LoCoMo audit found its judge accepted up to 63% of intentionally wrong answers.
3. Report ties and losses. B1 SQLite will likely match Plexus on claims; say so.
4. Phrase product comparisons as "the files approach, configured the way these tools use it", unless a statement comes from the qualitative case study.
5. Don't compare our numbers with vendor-reported LoCoMo or LongMemEval scores; those harnesses aren't comparable.

## 7. Budget and priority (4-day window)

| Priority | Layer | LLM usage | When |
|---|---|---|---|
| Must | L1 correctness + L4 performance | none (scripted) | Day 2–3, alongside product tests |
| Must | L2 provenance questions (~40) | 1 recorded run per arm + ~40 × 3 QA calls | Day 3 |
| Should | L3 end-to-end (3 arms × 5 runs) | heavy: run a 1-run pilot first and check account usage | Day 3–4 |
| Nice | §5 qualitative case study | moderate | Day 4 if usage allows |

Usage notes:
- Pro/Max limits are shared with normal Claude chat.
- Use Sonnet or Haiku for agents and `--max-turns` caps.
- Check account usage after the pilot. Unverified reports say headless use draws a separate credit pool.

## Results (Crucible L1 + L4 + ablation, first full run)

Source of truth: `plexus/src/plexus/crucible/results/20261014T204729Z/{results.json,report.md}` (also `latest.json`).
Run inside the compose network (`docker compose -p plexus-bench --profile bench run --rm crucible all`), FalkorDB 6.0.2 with
`FALKORDB_ARGS` = `TIMEOUT_MAX 10000 TIMEOUT_DEFAULT 5000 MAX_QUEUED_QUERIES 500 RESULTSET_SIZE 100000 QUERY_MEM_CAPACITY 268435456`
(the effective module config is recorded in the results). 10 seeded repetitions per test case; counts are summed over runs.
Synthetic data, scripted workers (threads; C2's victims are processes killed with SIGKILL), one machine, one model of embeddings.
Plexus here means the service layer (`P`) and the same layer through the MCP runtime's Step + ToolCall writes (`P-mcp`).

**L1 correctness: all four arms (B0 files, B1 SQLite, B2 vector, P Plexus) pass C1-C8 with 0 violations.**
Plexus does not beat the baselines on claims, leases, dependency ordering, as-of queries, tenant probes or forgetting;
a competently built file store (flock + atomic replace) or SQLite (BEGIN IMMEDIATE) ties it. The only differences measured:

* **C7 paraphrases** (12 pairs x 10 runs): B0 and B1 store every paraphrase pair as two facts (0% caught, they only dedupe on
  normalised equality); B2 and P catch the punctuation/case and lightly reworded pairs and miss the heavy rewordings
  (25% overall miss, 30 of 120 pairs). Concurrency adds no extra misses in any arm. No arm merged distinct facts.
* **C2 kill the claimer:** every arm reclaimed every orphaned task, slowest 1.27-1.52 s after the kill against a 2.0 s bar.
* **Capabilities** the baselines lack: B0 and B2 raise `Unsupported` for `why` and `knew_at` (L2 asks an LLM instead); B1 implements them
  with SQL (steps/recursive CTE), so provenance questions need L2 to separate the arms.
* **Ablation (D-001):** deleting `DEPENDS_ON`, `BASED_ON`, `DERIVED_FROM` and `READ` breaks 7 of 7 capabilities that use them (dependency-aware
  claims, blocked_by_failure, `why` for decisions and facts, `knew_at`, `who_knew`, cascading forget); 5 of 5 control capabilities
  (as-of, recall, contradiction flags, supersession, exclusive claims) are unaffected. Re-running C4 and C8 with the edges stripped gives
  181 tasks started before their dependencies finished and 60 forgotten facts still returned (0 and 0 intact).

**L4 performance** (client p50 / p99 of `claim`, ms; throughput = claim+heartbeat+complete ops/s):

| Arm | 1 worker | 10 | 50 | 100 | 200 |
|---|---|---|---|---|---|
| B0 files | 1.6 / 4.0 (569/s) | 18 / 30 (534/s) | 267 / 525 (167/s) | 931 / 1294 (102/s) | 2459 / 3885 (73/s) |
| B1 SQLite | 0.1 / 0.2 (17169/s) | 0.1 / 89 (3725/s) | 0.3 / 567 (1656/s) | 0.5 / 1688 (1480/s) | 0.8 / 2178 (1456/s) |
| P Plexus | 1.8 / 2.8 (668/s) | 5.5 / 16 (1780/s) | 50 / 140 (1028/s) | 156 / 356 (679/s) | 571 / 1863 (373/s) |
| P-mcp | 8.4 / 11.6 (123/s) | 37 / 48 (258/s) | 239 / 287 (228/s) | 621 / 828 (173/s) | 1622 / 2345 (153/s) |

* Plexus server-side `run_time_ms` for a claim is 0.5 ms at 1 worker and 3.6 ms at 200 (p50); the rest of the client latency is queueing
  (FalkorDB serialises writes per graph) and the client's GIL. **B1 SQLite is faster than Plexus at every worker count on claims**
  (median), but its p99 under write contention is 0.2-2.2 s because SQLite's busy handler has no fair queue.
* One graph vs several tenants (50 workers, claim+complete): Plexus 678 ops/s on 1 graph, 1025 on 4, 1174 on 16 (+73%); B1 1103 / 1480 / 500
  (16 SQLite files with 50 writers each contend on the disk, so more tenants did not help there).
* Recall (300 facts, embedding included): bounded by the shared embedding model, about 47 embeds/s for any worker count >= 10. P recall
  is 36-60 ops/s, P-mcp 13-28 ops/s; at 200 workers client p50 is about 8 s (P) and 7 s (P-mcp) while server-side time is ~10 ms:
  that is the closed-loop queue (workers / throughput). P-mcp's Step + ToolCall writes cost 2-3x at 1-50 workers; at 100-200 workers both are at the
  embedder ceiling and the audit writes are not the limiter. B1 (BM25, no embeddings) recalls at 350-525 ops/s.
* Numbers are not directly comparable across arms beyond what each row says: B0/B1/B2 are in-process libraries, the Plexus arms cross a container network to FalkorDB.

**Re-run note:** the first pass of `L1:P:C1` (200 workers) and `L4:claim` P / P-mcp at 200 workers hit a harness bug (redis-py's 100-connection
pool shared by 200 threads: `MaxConnectionsError`, 100 failed calls per run, 0 double claims / 0 lost updates). The pool is now 512 and only those
cells were re-run; the original results are kept under `run.reruns[*].superseded` in `results.json` and listed in `report.md`.

Not measured here: L2 (provenance questions), L3 (LLM agents). Limits: see `report.md` "Limits and honesty notes".

## C7 extended (pre-registered, P9-c; written before the first run on the test split)

**Why.** The original C7 (12 paraphrase pairs + 4 controls) measured recall of paraphrases. It never asked the opposite question: does the
duplicate rule merge two *different* statements? With the old rule (cosine distance <= 0.08 and equal digit tokens) the answer was yes for
`enabled` / `not enabled`, `5 minutes` / `5 hours`, `two` / `three` reviewers, `at least` / `at most`, and an automatic merge throws the second
statement away (`docs/research/PRODUCT_FIXES_ANALYSIS.md` B.1). P9-c changed the rule (`plexus/engram/dedup.py`, `queries/engram/assert_fact.cypher`):
a candidate is a duplicate only if its **discriminator key** (numbers, unit-normalised quantities, number words, negation and antonym tokens) equals
the new value's key, the two values are not the same words in another order, and they are not a pure one-word substitution (one content token replaced, or same-length token sequences differing in one position); then tier 1 (cosine
distance <= 0.08) or tier 2 (stemmed stop-word-free token Jaccard >= 0.6 **and** cosine distance <= 0.16). Close pairs that fail only the guards
or the thresholds (cosine <= 0.20 or Jaccard >= 0.5, same key) are stored as two facts joined by `DUPLICATES_MAYBE` ("surfaced").

**Corpus** (`demo_data/crucible/c7_pairs.yaml`, 226 hand-written pairs, one subject each, two agents, sequential): 140 `distinct`, 76 `merge`, 10 `maybe`.
Categories (pairs): punctuation 12, light 20, heavy 24, negation 20, antonym 20, quantifier 14, number_word_same 8, number_word_diff 10, unit_same 12,
unit_diff 14, direction_swap 10 (`maybe`), entity_swap 12, near_numeric 14, sprint_twin 16, long_one_word 12, bare_boolean 8.

**Split.** Inside every category the pairs alternate `train`, `test`, `train`, ... in file order (113 / 113). The test half is **never** used for tuning.
Everything that is a threshold is fixed here, before the test split is run: tier 1 0.08, tier 2 Jaccard 0.6 and cosine 0.16, soft link cosine 0.20 or
Jaccard 0.5, at most 5 soft links per fact. **Disclosure:** the unit and antonym tables, the stop-word list and the stemmer were written from the
B.1 failure list; the train split was run twice while developing. The first run had 3 false merges (`long_one_word`: one word changed in a long
sentence, cosine 0.01-0.05), which led to the *pure one-word substitution* guard (one content token replaced by another). A second run of the
whole corpus with the **hash** embedder (a unit-test diagnostic; it was not run with the real embedder on the test split) merged one *test* pair,
`long_one_word-02` ('server error' / 'client error', where 'client' also occurs elsewhere in the sentence), which extended the guard to
same-length token sequences that differ in one position. So the guard definition has seen one test pair; the real-embedder test split below was
run once, after this section was committed, with no further change.

**Labels and outcomes.** A pair's outcome is `merged` (one active fact after both assertions), `maybe` (two facts and a `possible_duplicates` entry) or
`new` (two facts, no link). A **false merge** is a `distinct` or `maybe` pair that ends `merged`. Recall of the `merge` pairs is reported as
*auto* (`merged`) and *surfaced* (`merged` or `maybe`).

**Gates.** (1) `false_merges == 0` in **every** category, on both splits, on the Plexus arms `P` and `P-mcp` (hard fail, a `C7X` violation). (2) The
rule-of-three bound is reported: 0 false merges in n `distinct`+`maybe` pairs bounds the true false-merge rate below 3/n at 95% (140 + 10 pairs: < 2.0%;
the test half alone, about 75 pairs: < 4%). "Precision 100%" is never written without n. (3) Targets (not gates): heavy paraphrases >= 75% auto or >= 95%
surfaced; every other `merge` category 100% auto. Whatever is missed is reported as missed. Baseline arms (`B0` files, `B1` SQLite, `B2` vector)
run the same corpus and their false merges are *reported*, not gated: they do not claim to have the guards. The concurrent variant stays in the original C7.

**Embedder.** Real `fastembed` (`BAAI/bge-small-en-v1.5`, 384-d); the hash embedder is used only in the unit tests.

## C7 extended results (P9-c; real fastembed embedder, one sequential run per arm, after the pre-registration above)

Raw numbers: `plexus/demo_data/crucible/c7x_results.json` (per-pair outcomes included). Code at the commit that follows the pre-registration commit `262705e`.

**Gate: passed.** Arm `P` (service path) and `P-mcp` (MCP path): **0 false merges in all 16 categories, on both splits** (train 0 of 75 non-`merge` pairs, test 0 of
75, together 0 of 150). The 95% upper bound by the rule of three is **< 4.0%** for each split alone and **< 2.0%** for the 150 pairs together; it says nothing
about antonyms or phrasings the corpus does not contain. For contrast, arm `B2` (the vector baseline, which replicates the *old* Plexus rule: cosine <= 0.08 and
equal digit tokens) **falsely merged 68 of the 150** (unit_diff 12/14, long_one_word 12/12, antonym 10/20, direction_swap 10/10, quantifier 9/14, negation 8/20,
number_word_diff 6/10, sprint_twin 1/16). `B0` (files) and `B1` (SQLite) merge only identical normalised text, so they merge none of the 76 true paraphrases either.

| category | expected | pairs | train: merged / maybe / new | test: merged / maybe / new | false merges (P) | false merges (B2) |
|---|---|---|---|---|---|---|
| punctuation | merge | 12 | 6/0/0 | 6/0/0 | n/a | n/a |
| light | merge | 20 | 5/5/0 | 5/4/1 | n/a | n/a |
| heavy | merge | 24 | 6/4/2 | 4/5/3 | n/a | n/a |
| number_word_same | merge | 8 | 4/0/0 | 4/0/0 | n/a | n/a |
| unit_same | merge | 12 | 5/1/0 | 6/0/0 | n/a | n/a |
| negation | distinct | 20 | 0/0/10 | 0/0/10 | **0** | 8 |
| antonym | distinct | 20 | 0/0/10 | 0/2/8 | **0** | 10 |
| quantifier | distinct | 14 | 0/0/7 | 0/0/7 | **0** | 9 |
| number_word_diff | distinct | 10 | 0/0/5 | 0/0/5 | **0** | 6 |
| unit_diff | distinct | 14 | 0/0/7 | 0/0/7 | **0** | 12 |
| entity_swap | distinct | 12 | 0/3/3 | 0/5/1 | **0** | 0 |
| near_numeric | distinct | 14 | 0/0/7 | 0/0/7 | **0** | 0 |
| sprint_twin | distinct | 16 | 0/0/8 | 0/1/7 | **0** | 1 |
| long_one_word | distinct | 12 | 0/3/3 | 0/3/3 | **0** | 12 |
| bare_boolean | distinct | 8 | 0/0/4 | 0/0/4 | **0** | 0 |
| direction_swap | maybe | 10 | 0/5/0 | 0/5/0 | **0** | 10 |

(`merged` = stored as one fact, `maybe` = two facts joined by `DUPLICATES_MAYBE`, `new` = two facts, no link. For `distinct` rows `maybe` is a harmless soft link:
nothing is lost and a reviewer can reject it; entity_swap and long_one_word pairs get one because they share most words.)

**Recall of the 76 true paraphrases (`merge`).** Auto-merged **51 / 76 = 67.1%** (train 26/38, test 25/38); auto-merged or surfaced as a soft duplicate
**70 / 76 = 92.1%** (train 36/38, test 34/38). Exact numbers per category: punctuation 12/12, number words 8/8, unit changes 11/12 auto (the 12th, `1 GiB` / `1024 MiB`,
is surfaced), light paraphrases 10/20 auto and 19/20 surfaced, **heavy paraphrases 10/24 = 41.7% auto and 19/24 = 79.2% surfaced (train 6/12 and 10/12, test 4/12 and
9/12)**. **The pre-registered heavy-paraphrase target (>= 75% auto or >= 95% surfaced) was missed.** The old rule caught 1 of 4 heavy pairs (25%) on the original
corpus; on this one the new rule auto-merges 42% and surfaces 79%, with 0 false merges. Why: the sequence guard sends every re-ordered rewording (passive / active:
'Builds are triggered on every push' / 'Every push triggers a build') to the soft tier, because the same bag of words can be the opposite statement ('A calls B' / 'B calls A'),
and the 5 heavy pairs that share almost no words (e.g. 'Customer data never leaves the EU region' / 'Data about customers stays inside the EU region') are not
found by any lexical or embedding rule at these thresholds. Raising recall means relaxing a guard, which the 0-false-merge gate does not allow without evidence; it is
left for an agent to confirm through `confirm_duplicate`.

**Regression row.** The original C7 (12 + 4 pairs, concurrent and sequential) is unchanged and still runs as `C7`; `C7X` is selected with `--tests C7X` (not in the default test list).
`B2` and `P` auto-merged the same number of true paraphrases (51), but only 33 of them are the same pairs.

**Reproduce.** `PLEXUS_EMBEDDER=fastembed python -m plexus.crucible.cli l1 --tests C7X --arms P,P-mcp,B0,B1,B2 --reps 1 --port <db port> --out <dir>` (a DB on that port is needed); the
unit tests (`tests/crucible/test_c7x.py`) check the corpus invariants and that the gate fires on a store that merges everything.

## L2-scale (pre-registered)

Written and committed **before any `claude -p` call of this experiment**. LLM calls made before this pre-registration: **0** (pilot calls made before pre-registration: 0; `plexus/demo_data/crucible/l2_scale_cache/` does not exist yet).
Code state this text describes: branch `p4-l2-scale`, commits `9d0bbab`, `c13c1b0`, `977749d`; question file `plexus/demo_data/crucible/questions_scale.yaml` sha256 `177d5a0bbbdfa7620b862c1b999e6c6ed006b0fa07d8a82ec7b22ee609c4394b`.
What was done before this text, without an LLM: built the scenario player, played it on all four arms, checked that the Plexus answerer matches the script ground truth (40/40, a correctness check of the answerer, not a model result), measured artifact sizes, and looked at a few selector outputs for sanity. One selector bug was fixed after that look (compound tokens such as `api_version=v13` are now also indexed as `api_version`, `v13`); the selectors are frozen from here on and will not be tuned after the first paid call.

**Why.** The first L2 run (43 questions, one Acme project) tied: B0 43/43, B1 43/43, B2 40/43, P 43/43, because the whole history fit in the 32k-character context. This run asks whether accuracy diverges when it does not fit.

**History.** K = **20** independent sprints (S01..S20) of the Acme story, played one after another into one tenant per arm, on one deterministic clock. Each sprint has 12 tasks, 6 decisions, 4 handoffs, 1 supersede (api version), 1 auth conflict, 1 killed builder and reclaim, 1 poisoned and forgotten source, 2 project-scoped facts. Ids, uris, subjects, scopes and decision texts carry the sprint tag; values vary per sprint (API versions, database, JWT key, API-key header, poison database, release channel, billing cycle). Totals: 240 tasks, 120 decisions, 80 handoffs, 180 facts, 80 episodes, 160 sources. Artifact sizes (full, uncut), measured before the run, against the 32,000-char cap:

| Arm | Artifact | chars | x cap |
|---|---|---|---|
| B0 files | tasks.json, MEMORY.md, decisions/handoffs jsonl, sources.json, logs | 532,813 | 16.6 |
| B1 SQLite | schema + CSV dump of all tables | 332,599 | 10.4 |
| B2 vector | 860 memory chunks | 147,471 | 4.6 (B2 only ever shows its top-12 chunks) |

**Questions.** 40 exact-match questions, the same 10 families as L2 (decision provenance, handoffs, time travel, supersession, dependencies, contradictions, recovery, memory scope, episodes, forgetting), 4 per family, each about **one named sprint** ("In sprint S07: ..."). Ground truth is derived from the per-sprint script ledger, never typed. Sprint choice is a fixed rule: question i (family order) takes stratum i mod 3 (early S01-S06, middle S07-S14, late S15-S20), sprints dealt round-robin from a shuffle seeded with 20261015 (`scale_questions.assign_sprints`). Pilot (fixed now): Q03, Q14, Q21, Q25, Q37 (five families, all three strata). Not measured: questions that aggregate across sprints (the strongest case for a graph) and the Procedures family.

**Equal context budget.** 32,000 characters for every baseline. Same `claude -p --model sonnet` (no tools, context on stdin, `ANTHROPIC_API_KEY` removed, max-turns 3), same role prompt as L2; the shared conventions get one extra bullet saying the history has many sprints and each question is about the named one (prompt version `l2-scale-v1`).

**Baseline context selection (competent, not truncation).** The question text is the retrieval query for all three arms.
- **B0:** files cut into chunks (one task of `tasks.json`, one entry of `sources.json`, one `MEMORY.md` bullet, one line of each jsonl/log); BM25-ranked; the best chunks that fit the cap are shown grouped by file in file order.
- **B1:** the full schema (all CREATE TABLE) is always shown; every table row is a document (own text plus the text of the rows its id columns point to, one hop); BM25-ranked; the best rows that fit are shown as CSV per table.
- **B2:** unchanged from L2: top-12 chunks by cosine similarity (local bge-small), same cap.
- BM25: Okapi, k1 = 1.5, b = 0.75, idf = ln(1 + (N - n + 0.5)/(n + 0.5)); lower-case alphanumeric tokens; identifiers indexed whole and in parts; short stop list; UUIDs not indexed; ties by document order.

**Scoring.** Exact match after the L2 normalisation, no LLM judge. Final L2 reply rule: the reply may start with prose but must END with exactly one `{"answer": ...}` JSON object with nothing after it. The stricter whole-reply-JSON variant is reported next to it. The rule is fixed now and will not change after results. Replies are cached and re-parsed from the cache.

**Plexus (P).** The same deterministic Cypher answerer, no LLM, unchanged for every question whose arguments already name a unique thing (task id, fact label, decision name, subject, source uri). Changes, all for sprint scoping (the original `plexus_answerer.py` and `queries/l2/*.cypher` are untouched; `scale_plexus.py` subclasses it):
- nine class-wide operations are restricted to the named sprint by a Python filter over the rows of the existing statements (task ids start with the sprint tag, source uris contain it, episode texts start with it): `handoffs_to`, `handoffs_with_superseded_facts`, `decisions_on_superseded`, `decisions_on_forgotten`, `active_conflicts`, `active_conflict_agents`, `reclaimed_tasks`, `completed_by`, `episode_count`;
- `visible_facts` runs one new read-only statement, `queries/l2scale/facts_visible_subject.cypher` (= `l2/facts_visible` plus a subject restriction), because the global scope now holds the facts of all 20 sprints.

**Hypothesis (stated before seeing any result).** Plexus answers 40/40 (deterministic, checked without an LLM). B0 and B1 lose accuracy relative to their 100% on the small history, but not necessarily much: every question names its sprint and a sprint's records share its tag, so keyword retrieval is favourable; I expect them to land roughly 75-95%, with failures on questions that need many scattered rows (class-wide questions such as handoffs_to, completed_by, decisions_on_superseded, and join-heavy provenance). B2 (12 chunks only) is expected to be the lowest. A tie between P and B0 and/or B1 is a live outcome and will be reported as a tie. With 40 questions and one run each, differences of 3 questions or fewer between two arms are within sampling width (Wilson 95% intervals are reported) and will be described as ties, not wins. Whatever comes out is published, including a Plexus loss.

**What is reported.** Accuracy per arm, per family and per stratum (early/middle/late sprint); tokens, cost and latency per arm; for every wrong baseline answer the expected and given answer plus a diagnostic of whether the expected items' words were anywhere in the shown context; reply-format counts; the Plexus changes above; the limits (synthetic data, one scenario family repeated, sprints do not interact, sprint named in every question, hand-written Cypher for P, one model, one run per question). Results shape: `layers["L2_scale"]` in `plexus/demo_data/crucible/l2_scale/<run>/results.json` plus `report.md`, documented in `plexus/src/plexus/crucible/l2/README.md`. Every call is cached in `l2_scale_cache/`; contexts shown are saved per question.

**Budget rule.** Pilot first: 5 questions x B0, B1, B2 (15 calls, cap `--budget-usd 2`). The full run (40 x 3 = 120 calls, the 15 pilot calls are reused from the cache) happens only if pilot `total_cost_usd` x (40/5) <= **$7.00**; otherwise the question count is reduced, and that reduction is recorded here (appended below, with the cost numbers) before the full run. Hard cap for the full run: `--budget-usd 7`; an arm that hits the cap is reported as incomplete.

### L2-scale amendment 1: pilot done, budget rule applied (written before the full run)

Pilot calls made so far: **15** (B0, B1, B2 x Q03, Q14, Q21, Q25, Q37), run after the pre-registration commit `cba0a5a`. Artifacts: `plexus/demo_data/crucible/l2_scale/20261014T223746Z-pilot/`. Pilot cost (`total_cost_usd` summed over the 15 calls): B0 $0.3875, B1 $0.4384, B2 $0.0874, total **$0.9133**. The pilot is not a result; its 15 calls are the same prompts as the full run and are reused from the cache.

Budget rule: $0.9133 x (40 / 5) = **$7.31 > $7.00**, so the question count is reduced (pre-registered above). New size: **36 questions** (projected $6.58). Which four are dropped was fixed by a seeded rule, without looking at any answer: `random.Random(20261016).sample(families, 4)` gave time_travel, episodes, recovery, dependencies; the 4th question of each family is dropped: **Q12, Q36, Q28, Q20** (none is a pilot question). `questions_scale.yaml` keeps all 40; the full run asks the 36 others (`scale_run.FULL_DROPPED_IDS`). Families keep 3-4 questions each (time_travel, episodes, recovery, dependencies 3; the other six 4). Full run cap: new spend is limited to `--budget-usd 6.0` (total of pilot + full stays under $7). Nothing else in the pre-registration changes: same selectors, scoring, hypothesis.

### L2-scale amendment 2: diagnostic fix (after the full run, no LLM call)

The `evidence_in_context` diagnostic (do all words of each expected answer item occur anywhere in the shown context) first treated `predicate=value` as a single word and so under-counted. It was corrected and recomputed from the saved contexts with `scale_run refresh`; answers, scores and costs are untouched. The "Honesty" text of the results was also changed from "40 questions" to "40 generated, 36 asked". Nothing else was edited after the run.

## L2-scale results (full run, 36 questions)

Source of truth: `plexus/demo_data/crucible/l2_scale/20261014T224309Z-full/{results.json,report.md,contexts/}`; every call is in `plexus/demo_data/crucible/l2_scale_cache/`. Model `sonnet` = claude-sonnet-5-5, `claude -p` 2.1.296, no tools, 20 sprints, 32,000-char cap (B0 history 532,813 chars = 16.6x, B1 332,599 = 10.4x, B2 store 147,471 = 4.6x). Asked 36 of the 40 generated questions (amendment 1). Pre-registered scoring rule (prose allowed, reply ends with one JSON object).

| Family | n | B0 | B1 | B2 | P |
|---|---|---|---|---|---|
| Decision provenance | 4 | 1 | 1 | 2 | 4 |
| Handoffs | 4 | 3 | 4 | 2 | 4 |
| Time travel | 3 | 3 | 3 | 3 | 3 |
| Supersession impact | 4 | 4 | 4 | 2 | 4 |
| Dependencies | 3 | 2 | 2 | 1 | 3 |
| Contradictions | 4 | 3 | 4 | 1 | 4 |
| Recovery | 3 | 3 | 3 | 3 | 3 |
| Memory currency and scope | 4 | 4 | 4 | 3 | 4 |
| Cross-session recall | 3 | 3 | 3 | 2 | 3 |
| Forgetting | 4 | 4 | 4 | 4 | 4 |
| **All** | 36 | **30 (83.3%)** | **32 (88.9%)** | **23 (63.9%)** | **36 (100%)** |

Wilson 95% intervals: B0 68.1-92.1%, B1 74.7-95.6%, B2 47.6-77.5%, P 90.4-100%. Whole-reply-JSON-only variant: B0 28/36, B1 26/36, B2 23/36, P 36/36. By sprint position (early S01-S06 / middle S07-S14 / late S15-S20): B0 11/13, 10/12, 9/11; B1 11/13, 11/12, 10/11; B2 8/13, 8/12, 7/11; P 13/13, 12/12, 11/11.

| Arm | tokens / question | cost / question | total | median latency |
|---|---|---|---|---|
| B0 | 19,646 | $0.077 | $2.785 | 4.7 s |
| B1 | 22,010 | $0.087 | $3.117 | 4.9 s |
| B2 | 4,424 | $0.016 | $0.585 | 5.0 s |
| P | 0 | $0 | $0 | 7.5 ms (server-side Cypher) |

Money spent on this experiment: pilot $0.9133 + full run $5.5739 = **$6.4872** over 108 `claude -p` calls (108 = 36 x 3; 15 of them were the pilot calls), under the $7 cap; no call failed, none used a tool.

What it says, in plain words:
- Plexus answered 36/36. This is the same hand-written Cypher answerer as in L2 plus sprint scoping, checked against the script ground truth without an LLM before the run (40/40).
- With a history 10-17x the context budget and competent BM25 selection, B1 got 32/36 and B0 30/36. They lost 4 and 6 questions to Plexus. By the pre-registered rule (more than 3 questions apart) that is a gap, but it is small: the Wilson intervals of P and B0/B1 overlap, and a paired sign test on the discordant questions gives p = 0.031 (P ahead on 6, B0 ahead on 0) for B0 and p = 0.125 (4 vs 0) for B1. The B0 gap is suggestive, the B1 gap is not distinguishable from sampling noise with 36 questions, one run each.
- B2 (vector top-12, as before) got 23/36; its interval does not overlap with P's. It shows 12 chunks (about 2.4k chars), so it misses the second side of anything two-sided (conflicts, provenance with several facts) and anything that lists more than a few records.
- The accuracy of B0/B1 did not decay with the position of the asked sprint (early/middle/late look the same): retrieval by the sprint tag works. The cost is what moved: B0 and B1 spent about 20-22k tokens and $0.08-0.09 per question and about 5 s, against no tokens and a few milliseconds for Plexus; this is the same cost gap as in L2, now with accuracy that no longer ties.
- My hypothesis was right on the arm ordering and on the ranges (B0 83%, B1 89%, B2 64%, P 100%), and wrong on where B0/B1 fail: all their class-wide questions that were asked (handoffs_to, completed_by, decisions_on_superseded, reclaimed_tasks, ...) were answered correctly. They failed on join-heavy provenance (decision provenance: B0 1/4, B1 1/4) and one transitive dependency question.

Failure analysis (from `report.md`, the saved contexts and the cached replies):
- Decision provenance (Q01, Q03, Q04): the decision's `decision_facts` / handoff rows were retrieved, but the fact on the other side (the API-key fact and its source document) was not in the 32k shown, so the model gave one of two items (B0 Q03, Q04, B1 Q01, Q04), refused to name an unseen fact id (B0 Q01, B1 Q03: both replies ended with commentary after the JSON object and were unparseable under the rule; their JSON was incomplete anyway) or answered with raw ids (B0 Q06, Q23: UUIDs, because the fact rows were not in the context). The wrong answers where evidence was missing from the context are retrieval misses; the model never invented a fact.
- Dependencies Q17 (blocked if `s11-t03-design-endpoints` fails): B0 and B1 listed 3 of 6 downstream tasks (missed the transitive chain t09 -> t10 -> t11); for B1 all six task ids were in the context, so this one is a model reasoning error, not a retrieval miss. B2 returned an empty list.
- B2: 13 wrong, 11 of them with words of an expected item missing from the 12 retrieved chunks (empty lists, one side of a conflict, a count of 1 instead of 2), 1 with the evidence present (Q03 answered `@unknown` agents); the 13th is the count question Q35, which has no checkable evidence.
- Limits that may flatter the baselines: every question names its sprint and a sprint's records share its tag; sprints do not interact; no question aggregates across sprints. Limits that may flatter Plexus: hand-written Cypher per question family, scoped by sprint with the changes listed above. One model, one run per question, 36 questions, synthetic data.


## L5 pre-registration (staleness and forgetting; written before the first L5 run)

Written and committed **before any L5 measurement is run**. LLM calls in L5: **0** by design (every number below comes from deterministic code; the one real Claude Code run of P7-int is a separate demonstration, not an L5 result). Code that this text describes: `plexus/src/plexus/crucible/l5.py` (committed after this text; the tiny test `plexus/tests/crucible/test_l5.py` may run before the full run, because it only checks that the harness works at a toy size and records no result). Branch `p7-int`.

### L5a: staleness (`mark_changed`)

**Question.** When code changes, does Plexus flag exactly the facts whose code changed, and does recall then return no stale fact unflagged? How much does the anchor granularity matter?

**Repo (scripted, temporary git repo, seed 20261016).** 12 Python modules `mod00.py`..`mod11.py`, 5 functions each (`f0`..`f4`), so 60 functions; each function has a one-line docstring and returns a literal (`return 30`). **One initial commit and 20 change commits** (21 commits). Each change commit applies one of these edit kinds; every kind appears at least once and the order is drawn with `random.Random(20261016)`:

| Kind | Edit | Ground truth |
|---|---|---|
| value | change the returned literal of 1-3 functions | those functions changed |
| sibling | change one function and, in the same file, a second one | both changed |
| docstring | edit the docstring of one function | that function changed (its text changed) |
| add | add a new function to a file (nothing anchors to it) | none changed |
| module-comment | edit a comment outside every function | none changed |
| whitespace | add trailing whitespace to lines inside a function | none changed (the symbol hash normalises it; the file hash does not) |
| reorder | swap the position of two functions in a file | none changed |
| delete | delete one function | that function changed (gone) |

**Ground truth.** Computed independently of `plexus.codescan`: for every commit, the set of the 60 functions whose source segment (`ast.get_source_segment`, de-indented, trailing whitespace stripped, CRLF normalised) differs between the parent and the commit, or that exist in only one of them. The script's own edit log is checked against it (a mismatch fails the run).

**Facts.** 60 facts, one per function: subject `modNN.fK`, predicate `returns`, value = the literal at the initial commit. Global scope, asserted through `Engram.assert_fact`. The fact value is not updated when the code changes (the measurement is about flagging, not about agents re-writing facts).

**Arms** (each in its own tenant graph, same repo, same commits):

| Arm | Anchors | Entries sent to `mark_changed` per commit |
|---|---|---|
| S symbol | `anchor_fact(file, symbol)` for each fact | every file entry and every symbol entry of the changed files (the real client behaviour, `workflow.commit_groups`) |
| F file | `anchor_fact(file)` | file-level entries only (a client that does not parse symbols) |
| N none | no anchors, no sources | the same entries as S (nothing to hit) |

A baseline hash is established first (the initial commit is sent as a baseline), then each commit is sent with its commit time as `at`. After each commit, the facts that arm flagged are re-confirmed with `verify_fact(still_true=True)` so every commit is measured on its own.

**Measured per arm.** Over the 20 commits: true positives (flagged and in the ground truth), false positives (flagged, not in it), false negatives (in the ground truth, not flagged); **precision** = TP/(TP+FP) and **recall** = TP/(TP+FN) (`n/a` when the denominator is 0); and **stale facts returned unflagged**: for each fact in a commit's ground truth, `Engram.recall("modNN.fK returns", k=3)` after that commit counts it when the fact is returned with `verify_state != 'suspect'`. The number of ground-truth facts over the 20 commits is reported so the counts can be read.

**Hypothesis (stated before seeing any result).** S: precision 1.00, recall 1.00, unflagged 0. F: recall 1.00 (a changed function always changes its file), precision well below 1 because any edit flags the other four facts of the file, and the `add`, `module-comment`, `whitespace` and `reorder` commits flag five facts each for nothing; I expect precision between 0.15 and 0.45 and unflagged 0. N: recall 0, unflagged = every ground-truth fact. **Pass criterion: unflagged = 0 for S and F** (hard). If S shows any false positive or negative, that is a bug or a normalisation difference to be explained, not hidden.

**Limits (repeated in the results).** Synthetic code where every fact is exactly about one function and the fact value is the literal; real facts are looser (a fact "payments time out after 30 s" depends on code its author may not have anchored). The measurement says the mechanism flags what changed; it does not say what fraction of real stale knowledge Plexus covers (that depends on facts being anchored, by `anchor_fact` or implicitly through a Source's file uri). No LLM is involved, so nothing here says an agent will act on the flags (that is the real run).

### L5b: forgetting (activation ranking), forgetting on vs off

**Question.** With many plausible but unused facts around, does activation ranking keep the right facts reachable, reduce the share of noise in what recall returns, and keep rarely used but critical facts? Forgetting lowers rank only; "does not delete" is tested by the fact count being equal before and after.

**History.** The L2-scale history of `plexus.crucible.l2.scale_scenario.play_scale`, **K = 20 sprints**, into one tenant of the Plexus arm (embedder: the local fastembed model, as the other Crucible runs). Real facts are those the script asserted.

**Noise.** For every distinct subject that has a real fact, **N noise facts** in the same scope, asserted by the agent `noise-agent` through `Engram.assert_fact` (no supersede), with predicates drawn from `review_note, todo, meeting_comment, tmp_setting, old_estimate, retro_item, ticket_ref, cleanup_hint` and values from templates that mention the subject and the real predicate word (for example "api_version mentioned in standup, check again after the release"). **N = 5 is the primary run; N = 15 is the stress run** (only if time allows; whichever is run is reported). Created at times drawn uniformly over the history window. "Decaying": 30% of the noise facts get 1-3 reads, all inside the first 30 days of the 90-day window and none afterwards; 70% are never read.

**Simulated 90 days.** Virtual now `V = (real clock at the start of the run) + 90 days`; the engine's clock is replaced by `V` for recall and for the sweep (nothing is waited for). Reads are `(Step)-[:READ {via, at}]->(Fact)` edges placed at chosen times in `[V - 90 d, V]`:
- **hot set H**: a seeded 15% of the real active facts that are not critical; on each of the 90 days 3-8 of them are read, `via='use'` with probability 0.5, else `'recall'`;
- **critical set C**: the real facts that a Decision is `BASED_ON` (not flagged); each is read **exactly once, at `V - 90 d`** (`via='use'`), never again;
- all other real facts (cold): never read.
Random seed 20261016 for all draws.

**Probes.** One per real active fact: query `"<subject> <predicate>"`, in the fact's scope, ground truth = that fact's id. Classes: critical, hot, cold. `k = 5` is primary (`k = 1, 3` reported), `budget_chars = 20000` (no truncation).

**Modes.** `off` (`forgetting=False`), `on` (`forgetting=True`, nothing swept), `on+sweep` (a real `memory_sweep(dry_run=False)` of every sprint scope first, then recall with `forgetting=True`).

**Measured per mode.** recall@k of the ground-truth fact per class and overall; **noise share** = noise rows / rows returned; **chars per recall** = summed `len(text)` of returned rows (the unit of tokens; no tokenizer involved); **critical-probe loss** = critical probes found at k=5 in `off` and missed in the mode; facts moved to dormant by the sweep, by class (critical / hot / cold real, noise); the dry-run candidate list's overlap with critical facts; and the number of Fact nodes before and after (must be equal).

**Pass criteria (fixed now).**
1. **Critical-probe loss = 0** in `on` and `on+sweep`, and no critical fact moved to dormant (hard).
2. **Fact count unchanged** by the sweep (hard).
3. **Non-inferiority:** overall recall@5 of `on` is not more than 0.02 below `off`. If it is, that is reported as harm, not as a pass.
4. **Noise reduced:** the noise share of `on` or `on+sweep` is lower than `off`. If not, it is reported as "no reduction".
Accuracy unchanged is a valid outcome and is reported as such.

**Hypothesis (stated before seeing any result).** recall@5 within ±0.01 between `off` and `on` (the ranking multiplier is bounded to [0.5, 1]; the relevance gap between the target and noise is usually larger); noise share of `on` lower than `off` by a small relative amount (5-25%); `on+sweep` lower again (dormant noise is not returned at all) at a recall within 0.02 of `off`; chars per recall nearly equal for `off` and `on` (k rows are returned either way; only which rows changes); critical loss 0 because every critical fact is protected by its Decision. A possible failure that would count as a finding: cold, non-critical real facts (never read in 90 days) lose rank against noise that was read early, which would lower cold-class recall@5 in `on` and `on+sweep`; the per-class numbers are reported so this is visible.

**Limits (repeated in the results).** One synthetic scenario repeated 20 times; noise is generated from templates, so it is more regular than real clutter; the read schedule is simulated, not observed; the probes are fact lookups (the part of the L2-scale question set that is about stored facts), not the full 36 questions, which are answered by hand-written Cypher and do not call `recall`. No LLM is involved, so this says nothing about the answer quality of an agent.


## L5 results (staleness and forgetting; run after the pre-registration above)

Source of truth: `plexus/demo_data/crucible/l5/` (`results.json` + `report.md` per run), produced by `python -m plexus.crucible.l5`; no LLM call (0). Code state: `p7-int` at `75bd122` for run 1 (then a diagnostic table was added to the harness; runs 2 and 3 are that code, uncommitted at the time of the run, `-dirty` in `results.json`). Embedder: fastembed `bge-small`. Runs on one private FalkorDB 6.0.2 container. Plexus ids are random UUIDs, so repeated runs differ in small ways (which facts are "hot", which noise gets read); the three N=5 numbers below show how much.

### L5a: staleness, 60 facts, 21 commits (run `20261015T202726Z`)

| Arm | TP | FP | FN | precision | recall | stale returned unflagged | stale not in the top 3 |
|---|---|---|---|---|---|---|---|
| S symbol-level anchors | 19 | 0 | 0 | 100% | 100% | **0** | 0 |
| F file-level anchors | 19 | 106 | 0 | 15.2% | 100% | **0** | 0 |
| N no anchors (baseline) | 0 | 0 | 19 | n/a | 0% | 19 | 0 |

19 (commit, fact) pairs changed over the 20 change commits. Facts flagged by edit kind: S flagged only the changed functions (`value` 9, `docstring` 4, `sibling` 4, `delete` 2) and nothing for `add`, `module-comment`, `whitespace` and `reorder`; F flagged all 5 facts of a file for every edit of that file, so the four kinds that change no function cost it 40 flags in 8 commits (`add` 10, `module-comment` 15, `whitespace` 5, `reorder` 10). All pre-registered hypotheses held: S exact, F recall 1.0 with precision 15.2% (I had predicted 15-45%, the low edge), N misses all 19, and the hard criterion (unflagged = 0 for S and F) passed. Why: a stale fact is returned by `recall` with `verify_state = 'suspect'` as soon as `mark_changed` has seen the commit; the baseline arm shows what happens without anchors: every one of the 19 stale facts comes back looking current.

Reading. The mechanism does what it claims on code where every fact is about one function; the file-level fallback is safe (recall 100%) but noisy (15% precision: 85% of what it flags is not stale). That noise is the price of not parsing symbols (other languages are file level only) and is the argument for `anchor_fact` with a symbol. It says nothing about facts nobody anchored.

### L5b: forgetting on vs off (the pre-registered design, K = 20 sprints, 140 real facts: critical 80, hot 9, cold 51)

| Run | Mode | recall@1 | recall@3 | recall@5 | critical@5 | cold@5 | noise share | chars / recall | critical loss |
|---|---|---|---|---|---|---|---|---|---|
| N=5, run 1 (`...202726Z`) | off | 75.7% | 97.1% | 98.6% | 97.5% | 100% | 23.0% | 322 | n/a |
| | on | 22.1% | 45.0% | 72.9% | 87.5% | 45.1% | 10.0% | 256 | **8** |
| | on+sweep | 12.9% | 42.9% | 67.9% | 85.0% | 35.3% | 4.7% | 245 | **10** |
| N=5, run 2 (`...203329Z`) | off | 75.0% | 97.1% | 98.6% | 97.5% | 100% | 27.1% | 330 | n/a |
| | on | 19.3% | 45.0% | 75.0% | 87.5% | 51.0% | 9.9% | 258 | **8** |
| | on+sweep | 15.0% | 41.4% | 65.7% | 82.5% | 33.3% | 6.0% | 250 | **12** |
| N=15 stress (`...203417Z`) | off | 76.4% | 97.1% | 97.9% | 96.2% | 100% | 31.0% | 339 | n/a |
| | on | 22.9% | 53.6% | 79.3% | 87.5% | 62.7% | 14.0% | 273 | **7** |
| | on+sweep | 17.1% | 42.9% | 67.9% | 82.5% | 39.2% | 9.6% | 260 | **11** |

The sweep (real, `dry_run=false`) moved 187-188 facts to dormant at N=5 (572 of 587 at N=15): **0 critical, 0 hot**, 15-16 cold real, the rest noise; the number of `Fact` nodes was identical before and after (480/480, 1080/1080); no dry-run candidate was a critical fact.

Pass criteria (fixed beforehand), run 1 / run 2 / N=15:

| Criterion | Result |
|---|---|
| Critical-probe loss = 0 (hard) | **FAIL** (8 and 10 / 8 and 12 / 7 and 11 lost) |
| No critical fact moved to dormant (hard) | PASS (0) |
| Fact count unchanged by the sweep (hard) | PASS |
| recall@5 of `on` within 0.02 of `off` | **FAIL** (72.9% / 75.0% / 79.3% against 98.6% / 98.6% / 97.9%) |
| Noise share reduced | PASS (23.0% -> 10.0% on, 4.7% on+sweep; 27.1% -> 9.9% / 6.0%) |

**The pre-registered hypothesis was wrong, and the result is a negative one for the default settings.** I predicted recall@5 within +-0.01 and critical loss 0; activation ranking with the default floor 0.5 cost 19-26 points of recall@5 and lost 7-8 of the 80 critical probes (and the sweep made it worse by hiding 15-16 cold real facts: cold@5 fell from 100% to 33-39%). Noise share did fall by more than half, as hoped, but "chars per recall" (322 -> 256) is not a saving: k rows are returned either way, the drop is the composition (shorter facts rank higher), and the answer was wrong more often.

Post-hoc diagnostic (added to the harness after run 1; not pre-registered): the class of the rows ranked above the target. Run 2, mode `on`: noise 1, hot 12, **critical 367**, cold 0. So the noise is not what displaces the target; **protected (critical) and hot facts of the other sprints do**. The 20 sprints repeat the same story with near-identical texts ("Acme Notes API S07 ..." against "... S08 ..."), the relevance gap between a sprint's fact and its twin in another sprint is tiny, and the multiplier `floor + (1 - floor) * sigmoid(A - A0)` moves a protected fact (`max(A, A0)`, multiplier 0.75) or a hot one (about 1.0) far more than that gap, against a cold or unprotected target (about 0.52). In other words activation ranking, as tuned, over-weights popularity against relevance when many facts are nearly the same text. Real memory has less of this (versions are `SUPERSEDES`d and leave `active`, scopes separate projects) but the failure is real for near-duplicate facts in one scope, and it is exactly the pre-registered "possible failure".

Post-hoc sensitivity (exploratory; the design was chosen after seeing the failure, so it is a hypothesis for a new pre-registered run, not a result): the same run with `PLEXUS_ACT_FLOOR` raised (`demo_data/crucible/l5_posthoc/floor*/`; one run each; N=5):

| Floor | recall@5 `on` (off 98.6%) | critical loss `on` / `on+sweep` | noise share `off` -> `on` | recall@5 `on+sweep` |
|---|---|---|---|---|
| 0.5 (default) | 72.9-75.0% | 7-8 / 10-12 | 23-27% -> 10% | 65.7-67.9% |
| 0.8 | 87.1% | 1 / 1 | 26.3% -> 11.9% | 87.1% |
| 0.9 | 96.4% | 0 / 0 | 22.7% -> 14.1% | 87.1% |
| 0.95 | 98.6% | 0 / 0 | 23.3% -> 18.4% | 87.9% |

A floor of 0.9-0.95 keeps the critical probes and (0.95) all of recall@5, at the cost of removing less noise (18.4% against 23.3% at 0.95). The `on+sweep` column does not recover: a sweep hides the cold real facts (cold@5 68.6-70.6%) whatever the floor, because a cold unprotected fact that nobody read for 90 days is by definition what a sweep selects; the sweep is the lossy part and is optional, dry-run by default, and reversible (`restore_fact`).

Reading, in plain words.
- **What holds:** nothing is deleted (fact counts equal); protected facts are never swept (0 of 80 critical, 0 of 9 hot); noise share falls substantially with ranking alone; staleness flagging behaves as designed.
- **What does not hold at the default floor 0.5:** "forgetting does not hurt retrieval" and "critical facts are safe in recall". Protection stops a fact from being swept, not from being outranked in recall by a more popular near-twin. In this benchmark the default made retrieval worse.
- **Recommendation for the owner (not applied here):** do not claim an accuracy benefit; ship `PLEXUS_FORGETTING=off` as the default, or raise the default floor to about 0.9 and pre-register a fresh run (new seed, N=5 and 15) before keeping it on. The harness and the three environment variables (`PLEXUS_FORGETTING`, `PLEXUS_ACT_FLOOR`) are in place to do that in minutes.
- **Limits:** one synthetic scenario repeated 20 times (near-identical sprints are the worst case for popularity-weighted ranking); template noise; simulated reads; fact-lookup probes only, not the 36 questions; three N=5 repeats that differ in the second digit because ids are random; the floor sweep is one run per value.


## L5b confirmatory pre-registration (floor 0.9)

Written and committed **before the confirmatory run**. Reason: the pre-registered L5b run (section "L5 results") failed its hard criterion at the default `PLEXUS_ACT_FLOOR=0.5`; a post-hoc sensitivity sweep over the floor (one run per value, chosen after seeing the failure) suggested 0.9. The orchestrator decided to make 0.9 the default, and this run tests that decision once, as a new pre-registered experiment. LLM calls: 0. Code under test: the harness `plexus.crucible.l5` unchanged, `plexus/src/plexus/activation/settings.py` with `floor = 0.9` as the default (so the run is made with no environment override). Branch `p7-int`.

**Design.** Exactly the L5b design of the first pre-registration (K = 20 sprints, N = 5 noise facts per subject, 90 simulated days, seed 20261016, fastembed, probes, modes `off` / `on` / `on+sweep`, same metrics), run **once** with the new default. Plexus ids are random, so the numbers differ slightly from run to run (the three N=5 runs at floor 0.5 differed in the second digit); a single confirmatory run is therefore read with that spread in mind, and I do not repeat it until it passes.

**Hypothesis (stated before the run).**
1. Critical-probe loss = 0 in `on` and `on+sweep` (hard); no critical fact swept (hard); fact count unchanged (hard).
2. recall@5 of `on` within **0.03** of `off` (the margin is widened from 0.02 because the post-hoc run at 0.9 showed 0.021 below; the widening is declared here, before the run).
3. Noise share of `on` lower than `off`.
4. `on+sweep` is allowed to lose recall (the sweep hides cold real facts by design); this is reported, not a criterion.

**What would count as failure:** criterion 1 not met (then 0.9 is not a safe default and the owner is told so), or criterion 2 not met (then it is reported as a cost, and the default is still the owner's call). Either outcome is written below the result without changing these criteria.


### L5b confirmatory result (floor 0.9, one run)

Source: `plexus/demo_data/crucible/l5/20261015T205321Z-floor09/` (`results.json`, `report.md`); code `92c9bd7` (clean tree); default settings, no environment override; K = 20, N = 5, seed 20261016, fastembed, 0 LLM calls.

| Mode | recall@1 | recall@3 | recall@5 | critical@5 | cold@5 | noise share | chars / recall | critical loss |
|---|---|---|---|---|---|---|---|---|
| off | 75.7% | 97.1% | 98.6% | 97.5% | 100% | 24.0% | 325 | n/a |
| on (floor 0.9) | 63.6% | 93.6% | 96.4% | 97.5% | 94.1% | 15.1% | 285 | **0** |
| on+sweep | 63.6% | 87.9% | 88.6% | 97.5% | 72.5% | 9.9% | 272 | **0** |

The sweep moved 174 facts to dormant: 0 critical, 0 hot, 14 cold real, 160 noise; `Fact` nodes 480 before and after; no critical fact among the dry-run candidates.

| Criterion (pre-registered) | Result |
|---|---|
| Critical-probe loss = 0 in `on` and `on+sweep` (hard) | **PASS** (0, 0) |
| No critical fact swept (hard) | **PASS** (0) |
| Fact count unchanged (hard) | **PASS** (480/480) |
| recall@5 of `on` within 0.03 of `off` | **PASS** (96.4% against 98.6%: 2.2 points below) |
| Noise share of `on` lower than `off` | **PASS** (24.0% -> 15.1%; 9.9% after a sweep) |

All four hypotheses held. Reading, without softening:
- The default floor of 0.9 is confirmed on the pre-registered criteria, in one run. The floor-0.9 post-hoc run before it gave the same recall@5 (96.4%) and critical loss (0): the two agree, and the confirmatory run is not a lucky draw on the headline numbers. (One run; ids are random, so the second digit can move.)
- **It is not free.** recall@1 falls from 75.7% to 63.6% (12 points): when two near-identical facts compete, the more used one is now first more often than the relevant one. recall@5 falls 2.2 points (cold@5 100% -> 94.1%: 3 of 51 cold facts leave the top 5). The noise share of what is returned falls by a third (24.0% -> 15.1%), not by the more than half seen at floor 0.5, because the gentler floor removes less. An agent that reads only the first row is worse off; one that reads five is nearly unaffected.
- **The sweep stays lossy.** `on+sweep` recall@5 is 88.6% (cold@5 72.5%): a sweep hides exactly the unprotected facts nobody has used for 90 days, which includes 14 real cold facts and 160 noise facts. It never touched a critical or hot fact and is reversible (`restore_fact`), but it is not an accuracy-neutral tidy-up, and it stays optional and dry-run by default.
- The post-hoc diagnostic still shows protected (critical) and hot twins as the main displacers (`on`: critical 82, hot 7, noise 0); the floor limits how far they can lift themselves, it does not remove the effect.
- Limits as before: one synthetic scenario of near-identical sprints, template noise, simulated reads, fact-lookup probes only, one run.


## B1h: a hand-written-SQL control for L2 and L2-scale (P9-a, $0)

Source of truth: `plexus/demo_data/crucible/b1h/20261016T035419Z-b1h/{results.json,report.md}` (also `latest.json`); code `plexus/src/plexus/crucible/l2/sql_answerer.py` (the 34 operations), `l2/sql_run.py` (the runner), `backends/sqlite_h.py` (one added table), tests `tests/crucible/l2/test_sql_answerer.py`. **No LLM call, no FalkorDB, cost $0.**

**Why.** In L2 and L2-scale the SQLite arm (B1) is a one-shot LLM reader of a CSV dump (`l2/contexts.py`), while Plexus (P) runs a developer-written query per question. The comparison is therefore *query against reader*, and says nothing on *graph against SQL*. `docs/research/BEAT_SQL_ANALYSIS.md` §1 predicted that the same 34 question operations written in SQL on the existing SQLite store would tie P; this is that run.

**What B1h is.** The existing B1 store (same schema, same transactions, same indexes) played with the same scripts, plus one table, `claims(task_id, agent_id, reclaimed_from, at, lease_until)`, written inside the claim's own `BEGIN IMMEDIATE` transaction. B1 keeps only a task's final claimer, so the Recovery questions are not answerable from its tables; Plexus keeps a `CLAIMED {reclaimed_from}` edge, and a competent SQL schema keeps the same fact. B1's LLM-facing dump (`contexts.B1_TABLES`) is untouched, so the B0/B1/B2 cache and results are unchanged. Each operation is one parameterised read-only statement (a `WITH RECURSIVE ... UNION` for the dependency and forgetting closures, joins elsewhere); the decision name (first four words) is computed in Python over the rows exactly as the Cypher arm does. Scoring is the same `score` over the committed `questions.yaml` / `questions_scale.yaml` (answers derived from the script ledger, never typed); the replay's ledger must equal the reference ledger (it does); L2-scale asks the same 36 questions as the paid run.

| Set | B1h (hand-written SQL) | P (hand-written Cypher) | B1 (reader) | B0 (reader) | B2 (reader) |
|---|---|---|---|---|---|
| L2, 43 q | **43/43** | 43/43 | 43/43 | 43/43 | 40/43 |
| L2-scale, 36 q | **36/36** | 36/36 | 32/36 | 30/36 | 23/36 |

Paired with the committed P rows: 43 both right and 36 both right, 0 questions where they differ. Median per-question latency: B1h 0.1 ms (L2) and 0.2 ms (L2-scale), in-process; P 2.5 ms and 7.5 ms client-side (0.2 / 0.6 ms server-side), across a container network. Author effort, counted as non-blank non-comment lines: the Cypher answerer 174 lines + 82 lines of `.cypher` statements (the scale variant is in a further file, not counted); the SQL answerer 379 lines, which include the scale variant. So the SQL needed no more effort than the Cypher, and it was not shorter either.

**The sentence for the submission (BEAT_SQL §6.3).** On L2 and L2-scale a hand-written-SQL arm on the same SQLite store ties Plexus on correctness (43/43 and 36/36) and is faster per call in process: the accuracy gap between Plexus and the B1/B0 readers (36/36 against 32/36 and 30/36) is *reader against query*, not *graph against SQL*. Plexus's measured edge on these two layers is over tool-less LLM readers (zero tokens, milliseconds, deterministic), not over a relational schema with recursive CTEs.

Limits. The SQL was written by the same author who wrote the Cypher, who knew the questions and the scenario (this is what a control means, but it is not a blind arm). B1h needed one schema addition. In-process SQLite and networked FalkorDB are not a like-for-like speed comparison. Both question sets are shallow (≤ 2 joins, dependency depth ≤ 4); L6 below is where depth and size are varied.


## L6 pre-registration (beat-SQL families A, B, D, E, F; written before any L6 run)

Written and committed **before any L6 measurement and before any L6 `claude -p` call**. Branch `p9a`, base `main` 5191976 plus the B1h commits above. LLM calls made for L6 before this text: **0**. Code state this text describes: the L6 generators, loaders and runners (`plexus/src/plexus/crucible/l6/`) do not exist yet; they are committed after this text and may run at toy size in tests (a toy test records no result). The L6 code and the prompts of the three LLM arms are frozen at the commit recorded in each `results.json` (`code_commit`); no prompt or parser is changed after the first paid call. Design source: `docs/research/BEAT_SQL_ANALYSIS.md` §4.0-4.2. Everything below is a prediction, and a tie or a Plexus loss is a valid outcome that will be published as such.

### What L6 is for

L1/L2 tie because of what the arms are (BEAT_SQL §1), not because a graph is or is not better. L6 asks two separate questions: **(i) structured, provenance-bearing memory against the status quo** (a tool-less reader, or an agent with files) and **(ii) a graph (Plexus) against a competent relational schema** (hand-written SQL on SQLite). Every family therefore carries a hand-written-SQL control (B1h). The headline we expect: large gaps against readers, ties against B1h, and a Plexus loss on crash-consistency (F). Not run: family C (multi-hop associative recall; needs the typed-relation change P2, which is outside this branch's scope; marked "not run" unless the orchestrator says P2 landed) and the optional L6-H (tenant fan-out).

### Arms

| Arm | What | LLM |
|---|---|---|
| **P** | The product, called through its service/tool API: `impact` (A), `why` (B). Only after the traversal fix (P9-b) is merged; until then "pending". For D the arm is hand-written Cypher over the same graph (no product tool exists); for E the single read statement; for F the service path that writes Step and WROTE after the memory write. Where a product call is used the results record the git commit of the code. | no |
| **P-pre** | Family B only: the product `why` as of `main` 5191976 (before the fix), to show the depth cap. | no |
| **P-tuned** | Hand-written Cypher in `crucible/l6` that expands level by level over distinct nodes (anchored on the Source/Fact id), checked with `GRAPH.PROFILE`; no product code. Same tuning budget as B1h. | no |
| **P-naive** | The natural variable-length query `(:Source {id})<-[:DERIVED_FROM*1..12]-(f:Fact)` (and `[:DEPENDS_ON*1..L]` for tasks) with `DISTINCT`, one statement per count. Reported, not hidden. | no |
| **B1h** | SQLite (the B1 schema + `claims`), hand-written recursive CTEs (`UNION`, join order hinted, `step_reads(fact_id)` index added and `ANALYZE` run: the tuning that BEAT_SQL §2.2 showed matters). Line counts of the queries are reported. | no |
| **B1h-untuned** | The same SQL without the extra index, hint or `ANALYZE` (sensitivity row, as BEAT_SQL §4.0.4 asks). | no |
| **B1a** | `claude -p` (Sonnet) with one read-only MCP tool `sql(query)` on the same SQLite file (schema given), no other tool. | yes |
| **B0g** | `claude -p` (Sonnet) in a directory holding B0-style files (`facts.jsonl`, `sources.json`, `decisions.jsonl`, `handoffs.jsonl`, `tasks.json`, `logs/<agent>.jsonl`) with `Bash`, `Read`, `Grep`, `Glob` (`Write`/`Edit`/web tools denied). | yes |
| **B0r** | The existing one-shot reader: `claude -p`, no tools, 32,000 characters of the files chosen by BM25 over the question text (the L2-scale selector idea; chunk = one record per line). | yes |

Not run: B2 (vector top-12) and B3h (Postgres + pgvector). Both are named in BEAT_SQL; neither fits the deadline, and the vector reader is already the weakest arm in L2-scale.

### Common design

* **Ground truth is generated, not typed, and independent of every backend.** A seeded generator (`random.Random(20261016)`) emits one event stream per family; the truth is computed with plain Python BFS/sets over the generator's own ledger. Each arm is loaded from the same stream; before any question the loader asserts, per arm, the node count and the edge count against the ledger. Plexus ids are the generator's ids (labels such as `f00123`), so truth is by label.
* **Answer-size control.** No arm is asked to emit thousands of ids. A question asks for counts, 10 yes/no membership probes (5 inside the answer set, 5 hard negatives: same level or same source family, not in the set) and the 5 earliest members by `at` (all `at` are distinct). A question is **correct** only if every component is exact (strict); per-component accuracy is reported too.
* **Timeouts.** 5,000 ms per statement for every database arm (FalkorDB started with `TIMEOUT_MAX 10000 TIMEOUT_DEFAULT 5000` as in the L1 run plus a per-call `timeout_ms`; SQLite via a progress handler). A timeout counts as a wrong answer and is listed as `timeout`; its latency is 5,000 ms.
* **Latency.** Client wall time per question (p50, p99) and, for Cypher, the server-side `run_time_ms`. B1h is in-process, FalkorDB is across a container network: "embedded" / "server" is printed with the numbers, and neither is called "faster" without that.
* **Statistics.** Exact two-sided paired sign test on discordant questions. n = 24 per deterministic family; the LLM pilot has n = 8 per family and one repetition, so a difference of fewer than 3 questions is called a tie; 6-0 gives p = 0.031 and 5-0 gives 0.0625 (not significant). With 8 questions the pilot cannot establish a small gap and will not be described as doing so.
* **Scoring of LLM replies (fixed now).** As in L2-scale: the reply may begin with prose but must END with exactly one `{"answer": ...}` JSON object with nothing after it; the stricter whole-reply-only variant is reported next to it; replies are cached and re-parsed from the cache. A reply whose tool use was denied, or that used a tool the arm does not have, fails the question.
* **Sizes.** `full` = the sizes below; `toy` = about 1/100 of them, used by the tests only.

### Families and generators

**A: blast radius with diamonds** (BEAT_SQL L6-A). One graph, 100 agents. 24 poisoned sources `s_i` (i = 0..23); blast size `B_i = [10, 100, 1000, 5000][i mod 4]` facts and depth `d_i = min([2, 4, 8, 12][(i div 4) mod 4], B_i)`. The facts of source `i` are spread over `d_i` levels (about `B_i/d_i` per level, at least 1); a level-1 fact derives from the source; a level-k fact (k ≥ 2) derives from 1, 2 or 3 distinct facts of level k-1 (probabilities 0.4/0.4/0.2), so path count far exceeds node count. Background: for every source a further tree of 40% of its size that is NOT poisoned (hard negatives for the probes), plus 100 isolated facts. Every fact is asserted by one agent. Each fact is READ by 0-3 steps (mean 1.5; a step of an agent reads 1-4 facts); about 3% of facts have a Decision `BASED_ON` them, 2% a Handoff that `CARRIES` them. About 55,000 facts, 80,000 reads, 25,000 steps. Question i: "Source `s_i` is poisoned. Facts derived from it directly or through other facts (any depth) are affected; an agent is affected if it read an affected fact, a decision if it is based on one, a handoff if it carries one." Answer = {facts, agents, decisions, handoffs, probes[10], earliest5[5]}. **A-dag** (5 extra questions, deterministic arms only): the Probe-A layered task DAG of BEAT_SQL §2.1 with L in {8, 12, 16, 20, 24} layers of 6 tasks, each depending on 2 tasks of the layer below; "which tasks are blocked if the root fails" (count + probes + the 5 smallest ids); arms P-naive (`*1..L+1`), P (`Relay.blocked_by_failure`, the product), P-tuned, B1h (`UNION`), and B1h with `UNION ALL` plus a depth bound (shown as a trap). **LLM pilot ids for A:** i in {0, 3, 5, 6, 9, 10, 12, 15} (blast 10/5000/100/1000/100/1000/10/5000; depth 2/2/4/4/8/8/10/12).

**B: why-chain depth sweep** (L6-B). For depth d in {2, 3, 4, 6, 8, 12}, 4 chains each (24 questions; chain `c` = 0..23, `d = depths[c div 4]`). A chain is a decision `D` based on exactly one fact `f_0`; `f_i` derives from `f_{i+1}` (i < d-1) plus 3 distractor facts, each of which derives directly from its own other source; `f_{d-1}` derives from the root source `R`. The root is reachable only through the chain, so the chain is unique. Every chain has a **near-twin**: the same fact texts, different ids, its own decision, sources and agents (lexical retrieval cannot tell them apart without the ids). Background: 20,000 noise facts derived from 500 sources (depth ≤ 3). About 21,000 facts. Question: "Decision D is based on one fact. Following derived-from links, that fact reaches source R through a chain of facts. Give the chain as an ordered list of fact ids from the decision's fact down to the fact derived directly from R, and the agent that asserted that last fact." Answer = {chain, agent}; strict = both; the ordered chain alone is reported too. **Pilot ids:** c in {0, 4, 8, 9, 12, 13, 16, 20} (depths 2, 3, 4, 4, 6, 6, 8, 12).

**D: cross-sprint aggregation** (L6-D). The Acme story is not replayed: a purpose-built generator for 200 sprints, each a `Scope` node (projects as Scopes in one graph, so the isolation boundary here is the team, not the project). Per sprint: 18 facts (agents from a pool of 12; each derived from one of the sprint's 3 own sources or one of 30 shared sources), 15% of them later superseded by another fact of the same sprint, 8% later forgotten, 8 decisions based on 1-3 facts, 5 handoffs carrying 1-2 facts. About 3,600 facts, 1,600 decisions, 1,000 handoffs; a few MB as files (far beyond a 32k reader). 6 templates x 4 parameter variants = 24 questions, `i = 4t + v`: T0 number of decisions based on a fact later superseded; T1 the agent that asserted the most later-forgotten facts, with its count; T2 the shared sources cited by decisions in more than k sprints (k fixed per variant so that the answer has 3-15 members); T3 number of handoffs that carry a superseded fact; T4 the 3 sprints with the most forgotten facts, in order (ties by sprint tag); T5 number of facts superseded by a fact asserted by a different agent. The variants v = 0..3 restrict to all sprints / S001-S100 / S101-S200 / S041-S160. Ties for T1 and T4 are excluded by construction (the generator redraws until the maximum is unique). **Pilot ids:** i in {0, 4, 8, 12, 16, 20, 1, 9}.

**E: consistent reads under concurrent writes** (L6-E). A store holding 20 pre-populated quarantine-target sources `Q` (lineage tree of 60 facts, depth ≤ 5, 6 decisions each, never appended to) and 8 append-target sources `A` (tree of 100 facts), about 3,000 facts in all (BEAT_SQL's 100k-edge store is scaled down: the race window is set by the statements, not by the store size). 10 seeded runs of 6 s each (seed `20261016 + run`): 4 appender threads (each loop: one new fact derived from 1-3 existing facts of a random `A` source AND one new decision based on 1-3 facts including the new one, written atomically in ONE statement/transaction/locked append), 1 quarantiner (every 250 ms it quarantines the next `Q` source: ONE statement sets every fact of its tree to `quarantined`), 8 readers (each loop: pick a random source of `A` or `Q`, read its blast radius). Invariants checked on every read, no LLM: **V1** every decision in the answer has all its based-on facts in the answer; **V2** for a `Q` source the answer shows all facts quarantined or none (no half-quarantined subtree); **V3** the reported count equals the number of listed facts and, per (reader, source), never decreases. Arms: **P-1stmt** (one read statement), **P-levelwise** (one statement per hop, as the product's level-wise expansion does), **B1h-1stmt** (one recursive CTE), **B1h-txn** (several SELECTs inside one deferred read transaction on WAL), **B1h-levelwise** (several SELECTs in autocommit: a naive client), **B0-naive** (files: `status.json`, `facts.jsonl`, `decisions.jsonl` read one after the other without a lock), **B0-locked** (the same under a shared `flock`). The B0 writers hold an exclusive `flock` around their appends and replace `status.json` atomically.

**F: provenance crash-consistency** (L6-F, "P expected to lose"). A writer process loops `assert_fact` (with a source and a derived-from link), `record_decision` and `handoff` through the arm's backend (the Crucible backend protocol: `P` = the Plexus service layer, which writes the memory and then Step/READ/WROTE in separate statements; `B1h` = SQLite where the fact, its step and its WROTE row share one transaction; `B0` = the file arm: memory/decision files, then the per-agent log). The parent waits for the writer's "ready", sleeps a random 0-400 ms and SIGKILLs it (`TerminateProcess` on this Windows host); 200 kills per arm, a new process each time, same tenant. Afterwards, per arm: facts, decisions and handoffs **without** their Step/WROTE link (files: without their log line), acknowledged writes that are missing, and the totals. The rule-of-three upper bound (3/n at 95%) is printed for a zero count.

### Hypotheses and decision rules (stated before any result)

* **A.** P-tuned, B1h and (after the fix) P answer 24/24 strict, and the 5 A-dag questions correctly. P-naive is wrong (timeout) on the larger blasts: I predict 8-20 of 24 correct (blast ≤ 100 passes, blast 5000 at depth 8-12 times out) and a timeout for every A-dag size from L = 16 on. P-tuned and B1h medians are within a factor of 3 of each other on at least 70% of the questions, sign not predicted. B1h-untuned is at least 5x slower than B1h on the 5000-fact blasts. LLM pilot (8 q): B0r strict ≤ 2/8 (a 32k reader cannot count 5,000 facts); B1a 4-8/8; B0g 3-8/8; B1a and B0g use more tokens per question than B0r. **Reading rule:** if P-tuned/B1h are 24/24 and P-naive is lower, the finding is "the natural Cypher is the weak side" (as in BEAT_SQL §2.1), not a Plexus win; if P-naive is 24/24 as well, the traversal fear is not borne out at these sizes and that is reported.
* **B.** P-tuned = B1h = 24/24. P-pre answers only chains with d ≤ 3 (8/24: depths 2 and 3), the depth-cap finding. After the fix P answers all 24 if the call passes the depth. B0r ≤ 2/8 beyond depth 3 on the pilot; B1a and B0g 5-8/8, B0g declining with depth. Gap vs readers: large; vs B1h: zero.
* **D.** P = B1h = 24/24. B0r ≤ 1/8; B1a 6-8/8; B0g 5-8/8.
* **E.** P-1stmt, B1h-1stmt, B1h-txn and B0-locked: **0 violations in 10 runs** (hard). At least one of P-levelwise, B1h-levelwise, B0-naive shows ≥ 1 violation; I expect B0-naive to show V1 tears and the two level-wise arms V2 tears. If none of the three shows a violation, the result is "the race did not materialise at this load" and no claim about snapshot reads is made. Counts per arm are reported with the number of reads.
* **F.** B1h: 0 orphans and 0 lost acknowledged writes. P: > 0 orphan facts/decisions/handoffs in 200 kills (documented gap, report §8.3). B0 > 0. If P shows 0, the report says so and gives the rule-of-three bound. Showing the loss is the point; there is no fix in this branch, and the table is labelled "P expected to lose".
* **Pilot reading rule (A, B, D).** Per family and arm: strict correct out of 8, tokens, tool calls, cost, latency. Differences under 3 questions are ties. The pilot is not a full run: the 24-question LLM run is not done, and the text says so.

### LLM pilot budget (hard cap $20 for all L6 `claude -p` calls)

Model `sonnet` (claude-sonnet-5-5), `env -u ANTHROPIC_API_KEY claude -p`, never `--bare`, `--no-session-persistence`, run from an empty temporary directory (so no project `CLAUDE.md` is loaded), stream-json output. B1a: `--tools "" --strict-mcp-config --mcp-config <sql server> --allowedTools mcp__sql__query --max-turns 20`; B0g: `--tools "Bash,Read,Grep,Glob" --max-turns 20`, working directory = a copy of the arm's files; B0r: `--tools "" --max-turns 3`, context on stdin. A per-call `--max-budget-usd 0.80` guard. One repetition per question. Every call is cached by sha256(model, prompt version, arm role prompt, tool config, data hash, question). Families A, B, D only (E and F have no LLM arm: they are concurrency and crash tests). 8 questions x 3 arms x 3 families = **72 calls**. **Order and gate:** (1) 2 calls per arm on family B (6 calls) to measure the cost per call; (2) the rest only if the projected cost of all 72 calls (measured mean cost per arm x calls) is ≤ $16; otherwise the question count per family is reduced by the seeded rule `random.Random(20261016).sample(pilot_ids, k)` and the reduction is recorded here before the run; (3) arm budget split: B0r ≤ $3, B1a ≤ $7, B0g ≤ $8, the rest ($2) a reserve; an arm that reaches its cap is reported incomplete, never padded. Any unexpected permission, tool or harness failure is reported as such with the number of calls it cost.

### What is reported

Per family and arm: strict and per-component accuracy, p50/p99 latency, server time (Cypher), timeouts, statements per answer, tokens/cost/tool calls (LLM arms), and for each wrong answer the expected and given value. Plans (`EXPLAIN`/`PROFILE` text) for the P-tuned and B1h queries of A. Limits stated with the numbers: synthetic data from one generator, one seed per family (E: 10 seeds), one model, one machine, FalkorDB in a container against in-process SQLite, hand-written queries by one author who knew the questions, no Postgres arm, no vector arm, no family C, and the pilot sizes.


### L6 pre-registration, amendment 1 (written after dev runs at toy and full size, before any recorded result)

Development runs of the deterministic arms were made on the registered worlds before this amendment. They are not results (no file is kept), and what they showed is stated here so that the reader can judge which choices were made with a number in view:

1. **P-naive times out on every family-A question, including a 10-fact blast.** The single-pattern form `(:Source {id})<-[:DERIVED_FROM*1..12]-(f:Fact)` is planned from the Fact side (a label scan of 51,000 facts), the quirk the product's own `forget_source.cypher` documents. This is a planner effect, not path explosion, so a second Cypher arm is **added**, **P-anchored**: `MATCH (s:Source {id}) MATCH (s)<-[:DERIVED_FROM*1..12]-(f:Fact) WITH DISTINCT f ...` (the form BEAT_SQL §2.2 found fast on trees). It is still a variable-length pattern and so still enumerates paths on diamonds. P-naive is kept as registered.
2. **P-tuned, first version, was slow for a different reason** (not the one registered): `UNWIND $frontier AS fid MATCH (:Fact {id: fid})...` plans as a scan of all Facts per row (756 ms for 5 ids on 51k facts, `EXPLAIN`: Unwind, Conditional Traverse, Filter). The final P-tuned uses `MATCH (p:Fact) WHERE p.id IN $frontier` (Node By Index Scan, 0.2 ms). The same finding applies to `relay/dependents_of.cypher` (it uses the UNWIND form; at 145 tasks it does not matter) and is passed to P9-b.
3. **B1h-untuned** was about 1.2-2x slower than B1h in the dev run, not the 5x predicted for the 5000-fact blasts; the hypothesis stays as registered and will be reported as wrong if the recorded run agrees.
4. **Repetitions.** Each deterministic question is run 3 times; the answer scored is that of the first run; latency p50/p99 are over all runs (the first run included, no warm-up discard).
5. **P (the product) for family A** is the `impact` tool of P9-b (pending until the traversal fix is merged); for A-dag the product arm is `Relay.blocked_by_failure` as it is on `main`: a level-wise BFS capped at 10 levels. The dev run showed it returns 60 tasks (10 levels x 6) for L >= 12 instead of all of them, so on this DAG it is wrong from L = 12 on; that is a finding about the cap, and P9-b may change it.
6. **E.** The B0 arms run in one process, so the lock file that B0's writers hold is a `threading.Lock`; on Windows a reader can hit `PermissionError` while `status.json` is replaced: such reads are counted as `errors`, not as violations. V3's count and list come from two separate statements in the split arms (a client that asks "how many?" and then lists them).
7. **F.** `hash` embedder (no model download), every fact has its own subject (so the duplicate detector cannot merge two writes), one tenant per arm. B1h is the B1 SQLite backend (`SqliteHistoryBackend`). The writers do very different numbers of operations per kill (SQLite about 190, Plexus about 5), so rates are given per acknowledged operation as well as in total. A fact the writer asked to derive from an earlier fact but that has no such link is counted separately (`missing_derived_from`).
8. **A-dag, family D, E and F sizes** are as registered. The D generator redraws its world (seeded) until every question has a unique answer; the number of redraws is recorded in the results (`world_meta.attempt`).

### L6 pre-registration, amendment 2 (written after merging the P9-b traversal fix, before the P-product arms were run)

`main` b0318b2 (P9-b: level-wise bounded traversals with depth parameters, index-seek frontier in `relay/dependents_of`, read-only `impact`) was merged into this branch (merge commit 3d08bb0). The deterministic run `20261016T042534Z-det` ran on the pre-merge code (commit 9aa117c); it contains no P-product arm for A, and its `P-product(blocked_by_failure)` and `P-pre(why)` rows are the pre-fix product. They are kept as the "before" rows. The P-product arms below are run on the merged code and are the "after" rows. Fixed before they run:

1. **A, P-product-tool**: `Lineage.impact('source', s, depth=12, max_detail=200)`: the largest list the `impact` MCP tool lets an agent ask for (`max_items` <= 200). `facts / agents / decisions / handoffs` come from the exact totals. A probe is "affected" if its id is in the returned fact list; a probe whose answer would need the part of the list beyond 200 ids is therefore answered "not affected" (this is the tool's cap, and it makes some probes wrong on blasts above 200). `earliest5` is not something the tool returns (no timestamps): the arm leaves it empty, so P-product-tool cannot be strictly correct on A; the per-component table says which components it gets right.
2. **A, P-product-service**: the same with `max_detail=5000` (the service allows it, the MCP tool does not). Exact lists, so probes are exact; `earliest5` still empty.
3. **A, strict-without-earliest5** is reported as an extra column for every arm, so that the comparison is not decided only by a field the product cannot give. It is a presentation of the same results, not a re-scoring choice made after seeing them: all five components are reported anyway.
4. **A-dag, P-product** is `Relay.blocked_by_failure('root')` with its default depth (now 50, up to 5,000 tasks) on the merged code.
5. **B, P-product-tool** is `Lineage.why(decision)` with the defaults the MCP `why` tool uses (depth 6, 200 elements: the tool exposes neither); **P-product-service** is `why(decision, depth=12, max_elements=5000)`. The chain is rebuilt from the returned edges as before; if the root is not among them the answer is empty (wrong).
6. **LLM pilot, Plexus MCP arm.** The pilot of three arms is kept as registered. The Plexus MCP arm (`claude -p` with the real MCP server and the `impact`, `why` tools) is a fourth pilot arm, **P-mcp**, added now that the tools exist; its cost counts against the same $20 cap and its per-arm cap is set in the pilot script before any paid call.

### L6 pre-registration, amendment 3 (written before any paid call; the L6 pilot is not yet run)

LLM calls made so far for L6: **0**. This amendment fixes the P-mcp arm and the budget split before the first paid call.

* **P-mcp** (arm id `P` in the pilot files): `claude -p` with `--tools "" --strict-mcp-config --mcp-config <real plexus-mcp stdio server bound to a tenant holding the family's graph> --allowedTools mcp__plexus__{impact,why,blocked_by_failure,task_status,who_knew,fact_history}`, `--max-turns 20`, the same `--max-budget-usd 0.80` per-call guard, embedder `hash`. Only read tools are allowed (`quarantine_source` and `forget_source` would write to the graph being queried). A call that uses any other tool is an error row (wrong answer), not a retry.
* **P-mcp is asked families A and B only** (16 calls). Family D has no product tool (P8 is not built), so a P-mcp row for D would measure the absence of a tool, which is already stated in the deterministic table.
* **Budget split** (total hard cap stays $20): B0r $3, B1a $7, B0g $8, **P-mcp $2**, nothing left in reserve. The gate is unchanged ($16 projected, from the two B-family measurement calls per arm: measured mean cost x calls per arm, 24 for B0r/B1a/B0g and 16 for P-mcp); if it fails, the question count per family is reduced by the seeded rule `random.Random(20261016).sample(pilot_ids, k)` and the reduction is recorded here before the run.
* The prompts (`PROMPT_VERSION = "l6-v1"`, the role strings of the four arms, the question text and format strings of the generators) are frozen at the commit that contains this amendment; the `code_commit` in the pilot `results.json` is that commit or a descendant that changes no prompt.

### L6 pre-registration, amendment 4 (written after the 8 measurement calls, before any further paid call)

The measurement stage (2 calls per arm on family B, 8 calls, **$0.456**, run `latest-pilot-measure.json`) was made at commit `dc83183`. It exposed a defect in the harness, not in any arm: **all 8 replies were scored "unparseable"** although each ended with a correct-looking object, because the question's format string says `a JSON object {"chain": [...], "agent": ...}` and the models wrote that object directly, while the L2 parser requires `{"answer": <that object>}`. The role prompts say "END with {\"answer\": ...}", but the format string was read as more specific; all four arms did the same, so the defect is symmetric.

Because the rule "no prompt or parser is changed after the first paid call" was written to prevent tuning toward results, the fix is the smallest one that touches no prompt and cannot favour an arm: the parser (`l6.llm.parse_reply`) keeps the L2 rule and adds one form-only leniency: **a reply that ends with a valid JSON object with no `answer` key has that object as its answer** (the object must run to the end of the reply; a closing code fence is allowed; any text after it still fails). Prompts, `PROMPT_VERSION`, role strings and the question texts are unchanged, so the 8 cached replies stay valid and are re-scored under the new parser at $0 (cache entries are re-parsed on load). The 8 calls are counted in every cost figure. Scoring is otherwise unchanged (exact match of every component). The gate (projected total = $4.68 from these 8 calls, limit $16) passed; the remaining 64 calls are run at the commit that contains this amendment; the `code_commit` of the pilot results is that commit or a descendant that changes neither a prompt nor the parser.

### L6 pre-registration, amendment 5 (written after the first 71 live pilot calls, before any further paid call)

State: 79 calls so far (8 measurement + 71 in the `rest` stage; 6 cached repeats), **$5.455** of the $20 cap (B0r $1.875, B0g $0.652, B1a $0.561, P-mcp $2.367). B0r, B1a and B0g finished all 24 of their questions. **P-mcp stopped after 5 of its 16 questions**: it reached its $2.00 arm cap during family A (the last call overshot the cap, $2.367 spent), so none of its family-B questions was asked. P-mcp cost $0.43 per family-A question (22 tool calls, 332k tokens per question, against $0.03 for B1a): the 200-id lists of `impact` made it page through the blast, and one call (A10) hit the $0.80 per-call guard and is recorded as a wrong answer with that error. The $2 cap was set from the two family-B measurement calls ($0.10 per call), which was a poor basis for family A; that is a weakness of the pre-registered gate and is stated here.

Decision, taken without looking at any further answer: the P-mcp arm cap is raised from $2 to **$6** so that its remaining 11 questions (A11, A13, A16 and the 8 family-B questions; A10 is not re-asked) run. The total hard cap stays **$20**; the other three arms are complete, so their unspent caps ($1.1 + $6.4 + $7.3) are what funds the raise. If P-mcp reaches $6 it is reported incomplete again. Nothing else changes: same prompts, same parser (amendment 4), same commit lineage.

## L6 results (P9-a): deterministic arms, concurrency, crash-consistency, LLM pilot

All runs are on this machine (Windows 11, 12 cores, FalkorDB 6.0.2 in Docker/WSL2 with `TIMEOUT_MAX 10000`, `TIMEOUT_DEFAULT 5000`, SQLite in-process), one seed per family (E: 10 seeds), hand-written queries by one author who knew the questions. Result files: `plexus/demo_data/crucible/l6/` (`20261016T042534Z-det` pre-merge, `20261016T045029Z-det` post-merge, `20261016T050338Z-conc`, `20261016T051146Z-crash`, `20261016T054105Z-pilot` / `T054343Z` (measurement and its re-score), `T055334Z` (first 71 calls), `T060222Z-pilot` = `latest-pilot.json` (final, all 88)), every call cached in `l6_cache/`. The pre-registration and its five amendments are above; **every result file is later than the commit of the section that predicts it** (pre-registration `docs(baseline): L6 pre-registration ...`, amendments 1-5 each committed before the runs they precede). LLM calls: **88, each paid once** (8 measurement + 80; the re-runs were cache hits), **$7.0855 of the $20 cap** (B0r $1.875, B1a $0.561, B0g $0.652, P-mcp $3.998). The pilot is 8 questions per family and one repetition: it cannot show a difference of fewer than 3 questions, and it is not described as doing so. Family C: **not run** (it needs P2, typed relations + `recall(hops)`, which is on branch `p9b` and not on this branch).

### A: blast radius with diamonds (24 questions, 51,424 facts, 80,851 derived-from edges)

| Arm | strict | timeouts (5 s) | p50 ms | p99 ms | statements | by blast 10/100/1000/5000, median ms |
|---|---|---|---|---|---|---|
| **B1h** (recursive CTE, tuned) | 24/24 | 0 | 56.8 | 260 | 1 | 25 / 36 / 65 / 192 |
| B1h-untuned (no indexes added) | 24/24 | 0 | 76.5 | 326 | 1 | 39 / 52 / 103 / 276 |
| **P-tuned** (level-wise Cypher, `id IN` frontier) | 24/24 | 0 | 69.3 | 749 | 10 | 24 / 31 / 121 / 595 |
| P-anchored (two-`MATCH` var-length) | 24/24 | 0 | 32.3 | 3,351 | 6 | 16 / 21 / 60 / 223 (max 3,321) |
| **P-naive** (one var-length pattern) | 10/24 | 14 | 5,000 | 6,110 | 1 | 4,952 / 4,979 / 5,000 / 5,000 |
| P-product-tool (`impact`, 200-id lists) | 0/24 (12/24 without `earliest5`) | 6 (socket, 5 s) | 31.7 | 5,098 | 1 | 7 / 11 / 262 / 5,012 |
| P-product-service (`max_detail` 5000) | 0/24 (18/24 without `earliest5`) | 6 (socket, 5 s) | 27.6 | 5,060 | 1 | 8 / 15 / 417 / 5,015 |

* **Correctness: SQL ties the hand-tuned graph query, and the natural graph query is the weak one.** B1h = P-tuned = P-anchored = 24/24; P-tuned is within a factor of 3 of B1h on 21 of 24 questions (87.5%, predicted ≥70%) and is slower, not faster, at the top blast (595 vs 192 ms at 5,000 facts). The B1h-untuned/B1h ratio at 5,000 facts is **1.4x, not the ≥5x predicted**: the prediction was wrong; SQLite's recursive CTE needs no hand tuning here. Lines of query code (non-blank, non-comment): B1h 47, P-tuned 72, P-naive 41, P-anchored 24.
* **P-naive**: 0/24 in the first recorded det run (`...T042534Z`, before the merge) and 10/24 in the second (`...T045029Z`); the predicted range was 8-20. Only the questions that finish in <5 s pass, which is a property of the 5 s budget against a plan (`Conditional Variable Length Traverse` from every Fact into a `Node By Index Scan` of the source) that is near the threshold on this machine; the two runs differ by ten questions. Read it as "the single-pattern form is not reliably usable at 51k facts", not as a stable 10/24.
* **The product's `impact` tool (after the P9-b fix) does not give a P win and is wrong on this family in three ways**, all reproducible: (1) it returns no timestamps, so `earliest5` cannot be answered (strict 0/24 by construction; the table gives the other five components); (2) with the MCP tool's 200-id cap, probes beyond the first 200 ids of a 1,000+ blast are answered "not affected" (probes right on 12 of 24 questions); (3) **on every 5,000-fact blast (6 questions) the statement does not finish**: the client's 5 s socket timeout fires, and the same statement run with a 60 s socket timeout against `TIMEOUT_MAX 10000` is cancelled by the server after 10 s. Bisecting `lineage/impact_source.cypher` on the A world: expanding the 5,000 facts takes 0.46 s, and each of the reader / decision / handoff joins alone takes about 0.5 s, but chained as written (`UNWIND fs ... WITH ..., fs, ... UNWIND fs ...`, the 5,000-element list carried through three successive unwinds) the statement exceeds 10 s. This is a defect in the merged P9-b query, reported to the orchestrator; `python -m plexus.crucible.l6.run det --families A` re-measures it. The `timeouts` column counts these as the 5 s budget (`l6.run.is_timeout`, added after the run; the stored file counts the six as `other_errors`).
* **A-dag (the Relay diamond DAG, L = 8, 12, 16, 20, 24 layers; tasks to block grow with L):** B1h `UNION` recursive CTE 5/5 at 0.3-0.5 ms; B1h with `UNION ALL` (the path-enumerating SQL, the SQL twin of the old Cypher) 3/5 (timeouts from L = 20; 727 ms at L = 16); P-naive 4/5 (126 ms at L = 16, 2,038 ms at L = 20, timeout at L = 24); P-tuned 5/5 (33-68 ms); **P-product `Relay.blocked_by_failure` after the fix 5/5 (36-94 ms)**. Before the fix (run `...T042534Z`) the product answered 1/5 (it returned 60 tasks for L ≥ 12). My prediction that P-naive would time out for every size from L = 16 was wrong (it timed out only at L = 24). The `UNION ALL` row is the SQL version of the diamond trap: a SQL author who writes `UNION ALL` meets the same wall as Cypher's path semantics, which is an argument about queries, not about graph vs SQL.
* **LLM pilot (8 questions: A01, A04, A06, A07, A10, A11, A13, A16):** B0r 0/8 (as predicted: a 32k-character excerpt cannot count thousands of facts; replies gave counts of 0-4); **B1a 8/8; B0g 8/8**; P-mcp 2/8 (A01, A13: 10-fact blasts; completed all 8). P-mcp per question: 18.4 tool calls, 324k tokens, $0.41, 79 s median (A10 hit the $0.80 per-call guard and is recorded wrong); the model could not get timestamps from the tools, paged through 200-id lists, and on A16 reported 3,328 facts for a 5,000-fact blast. Cost per question: B1a $0.028 (11.2k tokens, 1.25 SQL calls), B0g $0.030 (22.5k tokens, 1.6 tool calls), B0r $0.079 (19.1k tokens, no tools), P-mcp $0.414. The prediction "B1a and B0g use more tokens than B0r" was right for B0g only (B1a used fewer).

### B: why-chain depth (24 questions, 21,000 facts, chain depths 2, 3, 4, 6, 8, 12 x 4)

| Arm | strict | by depth 2/3/4/6/8/12 (of 4 each) | p50 ms | p99 ms |
|---|---|---|---|---|
| B1h (path CTE) | 24/24 | 4/4/4/4/4/4 | 0.09 | 3.1 |
| P-tuned | 24/24 | all 4 | 22.8 | 58.6 |
| P-naive | 24/24 | all 4 | 8.2 | 23.1 |
| P-product-tool (`Lineage.why` defaults: depth 6, 200 elements, as the MCP `why` tool calls it) | **16/24** | 4/4/4/4/**0/0** | 631 | 1,089 |
| P-product-service (`depth=12, max_elements=5000`) | 24/24 | all 4 | 869 | 2,453 |
| P before the fix (`P-pre`, run `...T042534Z`) | 8/24 | 4/4/0/0/0/0 | 350 | 486 |

* The prediction for the pre-fix product (answers only depths 2 and 3, 8/24) was exact. **After the fix the product answers all 24 only if the caller passes `depth=12` and a larger `max_elements`, which the MCP `why` tool does not expose**: through the tool as agents call it, chains deeper than 6 are still unanswerable (depths 8 and 12: 0/8). That is a finding for P9-b (expose `depth`/`max_elements` on the tool). Where it answers, it is 3-4 orders of magnitude slower than B1h (a single-statement `why` plus node-info lookups); the SQL and the hand-written Cypher are 24/24 with 2 and 7 statements.
* **LLM pilot (B01, B05, B09, B10, B13, B14, B17, B21; depths 2-12):** B0r 1/8 (only the depth-2 chain; at depth ≥ 3 it returned the first and last hop); **B1a 8/8; B0g 8/8; P-mcp 8/8** (1-5 tool calls, $0.086, 83k tokens per question). On B the product MCP tool, the SQL tool and the file agent all solve the pilot, and the reader does not: a tie among the three tool-using arms (n = 8), and no case here for the graph over SQL. P-mcp's cost per question ($0.086) is 3-4x B1a ($0.022) and B0g ($0.028): the `why` result is large.

### D: cross-sprint aggregation (24 questions, 200 sprints as Scopes in one graph, ~3,600 facts)

B1h 24/24 (p50 1.6 ms, 1 statement); P (hand-written Cypher, no product tool: P8 of BEAT_SQL §5 is not built) 24/24 (p50 7.2 ms, 1 statement; median 4.6x slower than B1h on the same question). A tie on correctness; SQL faster. Pilot (D01, D05, D09, D13, D17, D21, D02, D10): B0r 1/8, **B1a 8/8, B0g 8/8** (B1a $0.020/q, 12.7 s; B0g $0.024/q, 20 s). P-mcp was not asked family D (no tool exists for it; amendment 3). The generator redrew its world three times until every question had a unique answer (`world_meta.attempt` = 3).

### E: consistent reads under concurrent writes (10 runs x 6 s, 4 appenders, 1 quarantiner, 8 readers)

| Arm | V1 (decision without its facts) | V2 (half-quarantined subtree) | V3 (count ≠ list / decreasing) | reads | appends | runs with a violation |
|---|---|---|---|---|---|---|
| P-1stmt (one read statement) | **0** | **0** | **0** | 14,377 | 8,323 | 0/10 |
| P-levelwise (one statement per hop) | 917 | 27 | 1,091 | 4,470 | 17,555 | 10/10 |
| B1h-1stmt (one recursive CTE) | **0** | **0** | **0** | 4,116 | 25,108 | 0/10 |
| B1h-txn (SELECTs in one WAL read transaction) | **0** | **0** | **0** | 1,522 | 25,556 | 0/10 |
| B1h-levelwise (autocommit SELECTs) | 345 | 0 | 349 | 1,496 | 23,160 | 10/10 |
| B0-naive (files, no lock) | 43 | 0 | 0 | 2,922 (81 read errors) | 1,446 | 10/10 |
| B0-locked (files under a shared lock) | **0** | **0** | **0** | 1,798 | 1,019 | 0/10 |

* The hard prediction holds (all four consistent arms: 0 violations in 10 runs). **A single read statement on the graph is consistent, and so is the SQL equivalent, and so is the locked file reader; this is a tie, not a Plexus win.** What distinguishes Plexus is not consistency but that the product's *own* level-wise traversal (`Lineage.why` and `Relay.blocked_by_failure` issue one statement per hop from Python) is the P-levelwise arm, which tears: 917 V1 and 1,091 V3 violations in 4,470 reads, and 27 V2 (a half-quarantined subtree). P-1stmt read throughput is 3.5x B1h-1stmt (14,377 vs 4,116) but its append rate is a third of SQLite's (8,323 vs 25,108). The prediction that both level-wise arms show V2 tears was half wrong: B1h-levelwise showed none (its quarantine is a single `UPDATE`, which an autocommit `SELECT` sees whole), only V1/V3 tears. The B0 arms run in one process, so the lock-file is a `threading.Lock` (see amendment 1); the 81 `errors` of B0-naive are `PermissionError` on `status.json` and are not violations.

### F: provenance crash-consistency (200 SIGKILLs per arm; "P expected to lose")

| Arm | acknowledged writes | store totals (facts / decisions / handoffs) | orphans: no Step/WROTE (facts / decisions / handoffs) | derived-from link missing | acknowledged writes lost |
|---|---|---|---|---|---|
| B1h (SQLite, one transaction) | 26,483 | 13,395 / 6,609 / 6,573 | **0 / 0 / 0** | 0 | 0 |
| **P (Plexus service path)** | 1,112 | 704 / 280 / 256 | **60 / 18 / 16 = 94 (7.6% of 1,240)** | 9 | 0 |
| B0 (files; no log line) | 1,534 | 886 / 339 / 321 | 6 / 0 / 1 = 7 (0.45% of 1,546) | 0 | 0 |

* Plexus loses, as pre-registered: 94 of 1,240 records written by the service path have no Step/WROTE link after a kill (the memory write and the step/WROTE write are separate statements), and 9 facts that were written as derived from an earlier fact lack the link. No acknowledged write was lost in any arm. SQLite shows none in 26,577 records (rule-of-three upper bound 0.01% at 95%). The files arm sits between (a log line is appended after the memory line). Writer rates differ by ~25x (about 132 acknowledged operations per kill for SQLite, 5.6 for Plexus: a service round trip per operation against in-process SQLite), so the counts per arm are not comparable as rates of time, only as the share of records without their provenance link. There is no fix in this branch; the documented gap (report §8.3) is real and measured.

### Reading

* **What the evidence supports:** on questions that a competent SQL author can express (L2, L2-scale, A, B, D, E's single statement) Plexus **ties** SQL on correctness, and SQL (SQLite, in-process, hand-indexed) is as fast or faster, from about 1x (A, small blasts) to about 250x (B: 0.09 ms vs 22.8 ms for the same chain) on latency; the graph's advantage is not found in any family here. A graph query written naturally (`P-naive`, `UNION ALL`-equivalent) is the weak side; the same holds for the natural SQL (`UNION ALL`). LLMs with a SQL tool (B1a) or a files-plus-shell tool (B0g) answered 8/8 on each of A, B and D at 3-4x lower cost per question than the 32k-excerpt reader, which answered 0-1 of 8; the Plexus MCP tools answered B 8/8 and A 2/8, at 3-15x B1a's cost per question.
* **What it does not support:** a claim that provenance graph storage beats SQL; the pilot is 8 questions per cell; a 5-point or smaller gap is not detectable. Where Plexus's product is *behind* the generic tools here is itself the finding: `impact` cannot return the earliest affected facts and times out at 5,000 facts; `why` through the MCP tool cannot see past depth 6; crash-consistency is worse than a single SQLite transaction by construction.
* **Limits:** synthetic data from one generator and one seed (E: 10 seeds); one model (Sonnet) and one repetition per LLM question; one machine, SQLite in-process against Dockerised FalkorDB (a network hop per statement in P's latency; `server_ms` is in the result files); no Postgres arm and no vector arm; the author of the SQL also wrote the Cypher and knew the questions; the A and B product arms use the service layer directly, not an MCP round trip (the pilot uses the real MCP server).

## L6 after the fixes (P9-int): A impact and F re-run, deterministic, $0

The pre-registered L6 run above exposed product defects. They were fixed on branch `p9int` (commit messages `fix(impact)`, `feat(mcp): depth arg`, `fix(crash-consistency)`), and the two affected families were re-run on the same worlds, seeds and questions with `python -m plexus.crucible.l6.run postfix --port <db> --kills 200`: result `plexus/demo_data/crucible/l6/20261016T072750Z-postfix/results.json` (code commit `a58b783`, clean tree; 0 LLM calls). **Pre-registered expectation for the re-run (written in the task before it ran):** A impact 24/24 and under 2 s; F orphans 0 for the three folded tools. The original result files are unchanged.

| What | Before (`...T045029Z-det`, `...T051146Z-crash`) | After (`...T072750Z-postfix`) |
|---|---|---|
| A: `impact`, service path (5,000-item lists) | 0/24 strict; 6 timeouts (every 5,000-fact blast); p99 5,060 ms | **24/24 strict, 0 timeouts**; p50 13.2 ms, p99 626 ms, slowest 626 ms |
| A: `impact`, MCP-tool path (list cap 200 before, 2,000 now) | 0/24 strict (12/24 without `earliest5`); 6 timeouts; p99 5,098 ms | **18/24 strict, 0 timeouts**; p50 13.1 ms, p99 669 ms. The six misses are all probes on 5,000-fact blasts: the list is capped at 2,000 ids, so a probe beyond it reads "not affected". Counts, agents, decisions, handoffs and `earliest5` are 24/24 |
| A: B1h (SQL) and P-tuned in the same run | 24/24; B1h p50 56.8 / p99 260 ms; P-tuned p50 69.3 / p99 749 ms | 24/24; B1h p50 33.0 / p99 182 ms; P-tuned p50 50.8 / p99 521 ms (machine load differs between the runs) |
| F: records of arm P without `Step`/`WROTE` after 200 SIGKILLs | **94 of 1,240 (7.6%)**: 60 facts, 18 decisions, 16 handoffs; 1,112 acknowledged writes; 0 lost | **0 of 1,842**: 0 facts (of 1,005), 0 decisions (of 431), 0 handoffs (of 406); 1,776 acknowledged writes; 0 lost. Rule of three: below 0.16% at 95% (3/1,842) |
| F: facts written "derived from an earlier fact" without that link | 9 | 13 (the benchmark arm links them with a second statement; the MCP `assert_fact` has no such argument, so this is the arm's composite, not a product tool) |

* **A impact.** The statement carried the 5,000-element fact list as a grouping key through three successive `UNWIND`s, so FalkorDB hashed the list once per row (quadratic). The joins to readers, decisions, handoffs and tasks are now four `CALL` subqueries that each read the collected list once (`PROFILE`: the busiest operator produces the blast's own `READ` edges; a test pins that unrelated edges are not walked). On a 10,000-fact world with 15,000 reads a 5,000-fact blast takes about 0.35 s of server time (regression test: under 2 s). It also returns `earliest_at` / `latest_at` per category and the five earliest facts, which is what `earliest5` needed; `truncated` now means a further fact exists. **The expectation (24/24, under 2 s) holds for the service path; it does not hold for the MCP-tool path, where the 2,000-id cap makes 6 probes unanswerable** (a membership argument would fix it; not built).
* **F.** `assert_fact`, `record_decision` and `handoff` create `(Step)-[:WROTE]->(node)` in their own write statement; the runtime opens the Step first and removes it again if the call is rejected. A crash can now leave an empty `Step` (not counted above) but no record without its edge. Kill test in the suite: 50 kills, 0 orphans. The pre-registered "P expected to lose" is therefore only true of the pre-fix code; the other tools (`complete_task`, `fail_task`, `create_tasks`, ...) are still linked by a second statement.
* **Not re-run:** B (the MCP `why` tool now accepts `depth`, up to 12; the 16/24 tool-path figure above is the old one and the service path with `depth=12` was already 24/24), D, E, the LLM pilot (88 calls, $7.0855, unchanged). Nothing above changes the reading of L6: no family shows the graph beating hand-written SQL.


## L5b-D013 pre-registration: pattern separation (P1) and forgetting that cannot cost recall (P2); written before any run

Spec: `docs/research/MEMORY_FORGETTING_IMPLEMENTATION_PLAN.md` §5.1 (and `neuro-memory/CROSS_CHECK.md`). Branch `feature/neuro-memory-research`, worktree `wt-neuro-memory`, FalkorDB `plexus-db-13` (6.0.2). Code under test: commits up to the one that adds this section (P1 + P2 implemented; P3 not built). LLM calls: 0 (fastembed, deterministic scripts).

**Design.** The L5b design above unchanged (K = 20 sprints, 90 simulated days, seed 20261016, fastembed, fact-lookup probes `"<subject> <predicate>"`, same metrics), run at N = 5 and N = 15 noise facts per subject, once each, with the harness `plexus.crucible.l5 --only forgetting --modes off,on-mult,kw-fix,sep,sep+add`. One more run, N = 5 with `--burst` (every hot fact is read 90 times inside one hour at day 45 instead of daily). Modes, each isolating one change:

| mode | what is on |
|---|---|
| `off` | flat order: forgetting off, separation off (control; must equal the committed `20261015T205321Z-floor09` `off` numbers within id noise) |
| `on-mult` | D-012 default as shipped: `PLEXUS_ACT_MODE=mult`, floor 0.9, keyword bypass over `Fact.value` only, separation off (control) |
| `kw-fix` | `on-mult` with the keyword bypass tested over the whole fact text `entity predicate: value` |
| `sep` | P1: entity resolution (`engram/recall_entities`, named-entity rule: every word of the entity name in the query), fan-damped lift `gamma · max(0, 1 − ln fan / ln 50)` with `gamma = 0.15`, fan-damped sibling expansion, lures; forgetting **off** |
| `sep+add` | P1 + P2: `PLEXUS_ACT_MODE=add` (`beta = 0.05`, `s = 1`, Pavlik–Anderson `c = 0.217, a = 0.177`, salience `kappa = 0.4`, band `eps = 0.02`, `delta = 0.03`), forgetting on, separation on, bypass over the fact text |

New standard columns (every mode): the class of the rows ranked above the target split into same-entity / other-entity; `hot_above_cold` (share of cold probes with a hot row above the target); `gap12` (distribution of the relevance gap between rank 1 and rank 2; sets `beta` for a later fit); client-side ms of the entity read.

**Hypotheses and decision rules (plan §5.1, copied; thresholds are for N = 5, the N = 15 run is reported with the same rules as a stress case):**
1. `sep` recall@1 ≥ 0.90 and recall@5 ≥ `off` − 0.005; critical loss 0. **Falsified** if recall@1 < 0.85.
2. `kw-fix` alone: report its recall@1; if it already reaches ≥ 0.88, say so and treat the fan/entity term as the hub-entity mechanism only (§5.3), not as the L5b fix.
3. `sep+add` recall@1 ≥ `sep` − 0.01; recall@5 ≥ `sep` − 0.005; noise share ≤ 15.5%. **Falsified** if recall@1 drops more than 1 point below `sep`: then P2 still costs recall and `beta` is too large.
4. Rows above the target of class `critical` or `hot` under `sep+add`: ≤ 5 (today 82 + 7).
5. Burst variant: under `sep+add` a burst twin outranks a cold target in ≤ 1% of cold probes; under `on-mult` it does whenever the relevance gap < 0.06 (reported as `hot_above_cold` for both).

**What I expect, stated plainly before the run.** Confident: hypothesis 3 (P2 is bounded by construction: ±0.05 in log-relevance) and 5 (massed reads self-limit under activation-dependent decay). Unsure: hypothesis 1. The L5b misses in `off` are "critical 42, cold 4, hot 1, noise 2" rows above the target; if most of those rows are about the **same** entity as the target (another predicate of the same sprint subject), the entity lift cannot separate them and `sep` will not reach 0.90 — the same-entity / other-entity split is in the output precisely to show which it was. In that case the honest reading is "P1 fixes cross-entity twins (the mechanism the hub test and L6-C need) and L5b's residual is a predicate-cue problem (CROSS_CHECK §3.2)", not a tuned pass. The harness's recorded pass/fail per criterion is what gets reported, whichever way it goes.

**Implementation choices that deviate from the plan text (documented in `docs/DECISIONS.md` D-013):** the exact-keyword bypass keeps the entity lift (`ln rel + sep`) instead of relevance only, otherwise the bypass would strip P1 from the very rows P1 is for; entities count as named only when every word of their name is in the query (the plan's "top 5 by full-text score" would lift every `Acme Notes API Sxx` twin); the salience cache is written by `pin_fact` only — the activation read recomputes salience from the graph on every call (CROSS_CHECK §3.7 "simpler v1"), so the six-statement cache is deferred.

## L5b-D013 results (run after the pre-registration above; three runs, 0 LLM calls)

Source: `plexus/demo_data/crucible/l5/20261017T082244Z-d013-n5/`, `…T082341Z-d013-n15/`, `…T082449Z-d013-n5-burst/` (`results.json`, `report.md`); code `3017ad7` (the pre-registration commit); FalkorDB 6.0.2 on `plexus-db-13`; K = 20, 140 real active facts (critical 80, hot 9, cold 51), 300 / 900 noise facts, seed 20261016, fastembed. Each run ~40 s.

| Mode | recall@1 N=5 | N=15 | burst | recall@5 (all three) | noise share N=5 / 15 | critical loss | above target N=5: same entity / other entity | hot above cold (burst) |
|---|---|---|---|---|---|---|---|---|
| `off` | 75.7% | 77.1% | 75.0% | 98.6% | 23.7% / 28.7% | n/a | 36 / 13 | 0.0% |
| `on-mult` | 65.0% | 65.7% | 63.6% | 95.7% / 96.4% / 95.0% | 14.9% / 17.4% | 0 | 46 / 44 | 3.9% |
| `kw-fix` | 77.1% | 77.1% | 76.4% | 98.6% | 14.9% / 17.4% | 0 | 29 / 15 | 0.0% |
| `sep` | **85.7%** | **85.7%** | **85.7%** | **100%** | 23.3% / 23.7% | 0 | 20 / **0** | 0.0% |
| `sep+add` | **70.0%** | **70.0%** | **70.0%** | 100% | 21.9% / 20.1% | 0 | 41 / 1 | **0.0%** |

Rank-1/rank-2 relevance gap in `off` (cosine distance, 140 probes): p10 0.0019, p25 0.0044, **p50 0.0167**, p75 0.0488, p90 0.0732 (the same at N = 15). The entity read costs 2.3–2.6 ms client-side per recall.

| Hypothesis (pre-registered) | Result |
|---|---|
| 1. `sep` recall@1 ≥ 0.90; recall@5 ≥ `off` − 0.005; critical loss 0; falsified if < 0.85 | recall@1 **85.7% at every N: target not reached, falsification floor cleared** (neither pass nor falsified). recall@5 100% ≥ 98.1% **PASS**. Critical loss 0 **PASS** |
| 2. `kw-fix` alone ≥ 0.88 → the fan term is only the hub mechanism | **77.1%**: the bypass fix only removes `mult`'s own loss (65.0 → 77.1); the entity term is the L5b lift (77.1 → 85.7) |
| 3. `sep+add` recall@1 ≥ `sep` − 0.01; recall@5 ≥ `sep` − 0.005; noise ≤ 15.5%; falsified if > 1 point below `sep` | **FALSIFIED**: 70.0% is 15.7 points below `sep`. recall@5 100% PASS. Noise 21.9% **FAIL** |
| 4. critical + hot rows above the target under `sep+add` ≤ 5 | **FAIL**: 42 (N=5), 46 (N=15) |
| 5. burst: hot above cold ≤ 1% under `sep+add`; `on-mult` fails whenever the gap < 0.06 | **PASS**: 0.0% under `sep+add` (also 0.0% under `sep` and `off`, so the activation-dependent decay is not what prevented it here); `on-mult` 3.9% (2 of 51 cold probes) |

**Reading, without softening.**
- P1 does what it was built for and no more: every cross-entity displacer is gone (13 → 0 at N = 5, 12 → 0 at N = 15), recall@5 is perfect, no critical probe lost. The 20 rows still above a target are all *same-entity* critical facts (another predicate of the same sprint subject, which an entity cue cannot separate); the damped expansion also removed 16 of the 36 same-entity displacers `off` had (the flat sibling boost lifted siblings over the target). The 0.90 target assumed the twins were mostly cross-entity; they were not, and the split column shows it. The remaining defect is a predicate-cue problem (`CROSS_CHECK.md` §3.2).
- P2 at its declared constants costs recall, as its own falsification clause anticipated. The loss is not `beta` alone: a labelled **post-hoc** sensitivity run (`plexus/demo_data/crucible/l5_posthoc/d013/20261017T0*-sens-n5/`, N = 5, not confirmatory, chosen after seeing the result) gives `sep+add[delta=0]` 70.7%, `sep+add[beta=0.01]` 72.9%, `sep+add[beta=0.01;delta=0]` **85.0%**, `sep+add[beta=0.02;delta=0]` 80.7%: the activation term and the in-band salience lift each move a critical twin by ~0.02 in log-relevance, and the median twin gap is 0.017. At `beta = 0.01, delta = 0` the additive mode no longer costs recall (85.0 vs 85.7) **and no longer reduces noise** (23.9% = `off`): on this benchmark a bounded additive activation term is either harmful or inert. The decision stays as pre-registered: `add` is not the default.
- The shipped default after D-013 (`mult` + separation, measured in the same post-hoc run as `sep+mult`): recall@1 **85.0%**, recall@5 100%, noise 22.1%, critical loss 0, cross-entity displacers 0. Against D-012 as shipped (65.0% / 95.7% / 14.9%) the recall@1 loss is gone and recall@5 is perfect; the noise share is higher than D-012's because the entity lift also lifts noise *about the named entity* above real facts about other entities — the noise-share metric counts that as worse, the query arguably asked for it. Both readings are in the report.
- Limits as before, plus: one seed; the entity rule is lexical (a paraphrased entity name gets no lift); `gamma`, `beta`, `delta` are declared, not fitted (the `gap12` column exists to fit them in a later pre-registration); the hub variant (§5.3), P3 (§5.2) and the SQL-arm extension (§5.4) did not run.

## §5.4 pre-registration: the SQL arm for L5b (B1h-L5) and L6-C multi-hop recall; written before any run

Spec: `docs/research/MEMORY_FORGETTING_IMPLEMENTATION_PLAN.md` §5.4 (and §0, §7 for what may be claimed). Branch `feature/neuro-memory-research`, worktree `wt-neuro-memory`, FalkorDB 6.0.2 on `plexus-db-13`, SQLite 3.53.1 (Python 3.12 stdlib) with the `sqlite-vec` 0.1.9 extension for the KNN seeds and FTS5 for the text lookups. Code under test: the commit that adds this section plus the arm code committed after it (P1 shipped as `sep+mult`; P2 opt-in; P3 not built). LLM calls: 0. Everything below is a prediction; a tie or a Plexus loss is a valid outcome and is published as such.

### Part 1: L5b with a hand-written-SQL arm, shipped default (`sep+mult`)

**What the SQL arm is.** The L5b harness plays the history into FalkorDB as before (K = 20, seed 20261016, fastembed, N = 5 / 15, burst variant). After the noise and the 90-day read schedule are written, the whole tenant graph is exported once into a SQLite file with a conventional relational schema that holds the same columns the Cypher reads use: `scopes`, `scope_inherits`, `entities` (+ FTS5 on `name`), `facts` (id, entity_id, scope_id, predicate, value, status, valid_from, valid_to, created_at, surprise, pinned, verify_state, suspect_since, verify_after; + FTS5 on `value`; + a `vec0` table of the same 384-d fastembed vectors), `fact_events` (fact_id, kind in use/recall/reassert/verified/handoff, t, agent_id, suspect), `fact_decisions` (decision_id, fact_id, t, flagged, tasks_done, artifacts_ok), `fact_links` (src, dst, kind in derived_from/supersedes/contradicts), `sources` (id, trust). Same fact ids, same vectors, same events: the arm is handed the columns, as plan §0 requires. The arm answers a probe with **three parameterised statements**: (1) entities named by the query words (FTS5 OR) with each one's fan by `GROUP BY entity_id` over active, valid, in-scope facts (the same rows `engram/recall_entities` returns); (2) the candidates: KNN seeds (`vec0`, top `over`, retried x4 up to 512 like the Cypher wrapper) unioned with the FTS5 keyword hits, scope/status/validity filters, the fan-damped sibling expansion (5 per seed, boost 0.05 x damp), best `k` by rank (the rows `engram/recall` returns, incl. a `kw` flag); (3) activation inputs: `A(f)` and `protected` per candidate, computed **in SQL** (window function for the newest 50 events, `power()`/`ln()`, the D-012 weights, the contract's suspect-recall rule, protection = pinned / unflagged decision / handoff / supersedes / contradicts / trusted source within 3 `derived_from` hops / salience >= 0.5 with the D-013 salience weights). The two lexical rules both arms apply in Python stay in Python for both (every word of an entity's name in the query; the exact-keyword bypass over the fact text), and the final `mult` formula is the shared pure function `plexus.activation.rank.rerank` (`rel x (0.9 + 0.1 sigmoid(A - A0)) x exp(sep)`) over the columns each arm returned: the test is whether SQL *reads* can feed the same scoring, not whether a formula can be typed twice. Plexus's side is the product as shipped: `engram/recall_entities` (14 non-comment lines), `engram/recall_keywords` (10), `engram/recall` (46), `activation/activation` (31), `engram/find_entity_exact` (3) = **104 lines of Cypher** and 4 reads per probe (5 when nothing is named and the exact-name fallback runs).

**Runs.** N = 5, N = 15, N = 5 burst, modes `off` (retrieval parity control: no scoring at all) and `sep+mult` (the shipped default), both arms measured in the same process on the same graph/export in one session (`--sql`); the Plexus numbers of `docs/BASELINE.md` L5b-D013 are NOT reused because a fresh play gives new ids and the comparison must be paired per probe. Per arm and mode: recall@1/3/5 overall and per class, noise share, paired per-probe agreement (probes where exactly one arm has the target at rank 1 / in the top 5), the share of probes whose top-5 lists are identical, client-side ms per probe (median; Plexus across the Docker network hop, SQLite in process), Plexus server `run_time_ms` summed over the probe's statements vs SQLite's in-process statement time, statements per probe, and the activation fidelity check (`A(f)` and `protected` from SQL vs from `Activation.compute` for every fact of the graph).

**Hypotheses and decision rules.**
1. **Tie on quality (plan §5.4's pre-registered expectation).** `sep+mult`: |recall@1(P) − recall@1(B1h)| <= 1 probe of 140 (0.7 points) and recall@5 equal, at N = 5, N = 15 and burst; the same in `off`. Read as **not a tie** if the gap is >= 3 probes (2.1 points) in any run; 2 probes is reported as "within id noise, direction stated". Where the arms differ the differing probes are listed with the cause (HNSW approximate seeds vs exact KNN; RediSearch vs FTS5 tokenisation on the keyword / entity hits are the expected causes).
2. **Activation fidelity.** SQL `A(f)` equals the Python model's `A(f)` within 1e-6 and `protected` agrees for every fact (480 / 1,040 facts). A disagreement is a bug in the SQL arm to fix before the run counts, and is reported.
3. **Latency.** B1h-L5 median client-side ms per probe < Plexus's (sign predicted: SQL faster, in process vs a network hop per statement). Plexus server-side ms (sum of `run_time_ms`) vs SQLite statement time: sign **not** predicted; both reported.
4. **Code.** Lines of SQL written for the arm (non-blank, non-comment lines of the SQL string literals, counted by the harness) and `loc()` of the arm class (the L6 convention, `plexus.crucible.l6.run.loc`) are reported precisely next to the 104 Cypher lines + `loc()` of the Python the Cypher side runs for the same work. Prediction: the SQL is **not shorter** than the Cypher (the vector-and-expand read and the activation gather are each about as long either way); if it is shorter by >= 20%, that is reported as a finding against the "graph is less code" framing.

**What may be claimed afterwards (plan §0, §5.4).** If 1 holds: "SQL given the same features ties; Plexus beats flat retrieval (`off`) by the D-013 margins; Plexus explains every rank" and nothing more. The phrase "beats SQL on retrieval quality" is reserved for L6-C and only with the SQL arm's code budget stated.

### Part 2: L6-C, multi-hop recall through `RELATES` with the separation lift propagated per hop

**World (generator `plexus.crucible.l6.world_c`, seed 20261016, `hash` embedder, no LLM).** One scope. 4,000 entities with two-word names from two word lists (unique, lexically resolvable: every word of the name in the query), of which 40 are **hubs**. Every ordinary entity carries 10 active facts with distinct predicates drawn from a pool of 60 (`value = "<predicate> of <name> is <token>"`); a hub carries 120. Typed `RELATES {kind, scope_id}` edges: every ordinary entity has 2-5 (kinds from a pool of 8, random partners), every hub is connected to about 100 entities; both directions are walked, as the product does. About 40,000 + 4,800 facts, about 16,000 relations.
**Scoring rule (the plan's "−ln(fan) per hop").** From the anchor entity E1 (named in the question), an entity e reachable within d hops has `cost(e) = min over paths of Σ ln(fan(v))` over the entities v entered along the path (anchor excluded, e included), fan = active facts about v. A candidate answer is a fact with the asked predicate on an entity with cost defined; candidates are ordered by (cost asc, hops asc, entity id, fact id). A path through a hub costs ln(120) ≈ 4.8 per hop; through a fan-10 entity ln(10) ≈ 2.3.
**Questions (75):** 25 at depth d = 1, 25 at d = 2, 25 at d = 3 (stress row; the product's `recall(hops)` is capped at 2, so d = 3 is for the hand-written arms only). For each: anchor E1 and predicate P such that no entity within distance < d from E1 has a fact with P, and >= 2 entities at distance exactly d have one; the expected answer is the unique best candidate under the rule (redrawn when two candidates tie on cost); the generator records, per question, whether the best-by-cost answer differs from the best-by-hops-then-id candidate (`cost_matters`; the family is only informative if this is true for >= 30% of the questions, which is reported). Question text for the product arm: `"<E1 name> <P>"`.
**Arms.** `B1h`: SQLite, one `WITH RECURSIVE` statement per question (walk `relates` both ways to depth d accumulating `cost`, `GROUP BY` entity for the min cost, join `facts` on predicate, order by the rule, top 5), indexes on `relates(src)`, `relates(dst)`, `facts(entity_id, predicate)` and `ANALYZE`; `B1h-untuned`: the same without the three indexes (sensitivity row, as in L6-A). `P-tuned`: hand-written Cypher, level-wise over distinct entities (one bounded statement per hop anchored at the frontier ids, as `engram/relates_level` is, carrying the min cost per entity in Python) plus one statement for the facts; `P-product`: `Engram.recall("<E1> <P>", scope, k=5, hops=d)` exactly as shipped (hash embedder, its own 0.25-per-hop distance penalty and caps of 20 entities / 20 facts per hop, 3 facts per entity); `P-flat`: `Engram.recall(..., hops=0)`, the flat-retrieval baseline. Budget 5,000 ms per statement; a timeout counts as wrong at 5,000 ms (the L6 rule).
**Metrics (the L6 convention).** Per arm and depth: strict (rank-1 fact = expected), recall@5, p50/p99 latency, server ms (Cypher), statements per answer, timeouts; `loc()` per arm class and the non-comment lines of the SQL / Cypher literals; P-tuned vs B1h: share of questions with identical top-5 lists.
**Predictions.** (a) **Correctness tie**: B1h = P-tuned = 25/25 strict at every depth (both implement the rule; a disagreement is a bug in one arm, and which one is reported). (b) P-product strict <= 15/25 at d = 2 and 0/25 at d = 3 (not answerable); P-flat <= 3/25 at d >= 1 (the answer shares only the predicate token with the question, as do ~700 distractor facts). (c) **Latency**: B1h faster than P-tuned at d = 1 and d = 2 (in process; a few hundred rows); at d = 3 the recursive CTE enumerates paths through hubs (two hubs on a path = ~10,000 paths) while the Cypher walks distinct entities per level: I predict the gap narrows or flips at d = 3, sign not predicted; the L6-A reference (SQL 192 vs 595 ms at a 5,000-fact blast) is a reason to doubt a Cypher win. (d) **Code**: the SQL statement is **shorter** than the Cypher arm (one recursive CTE against a level-wise walk + a fact statement); both counts are reported. **Reading rule (plan §5.4):** "beats SQL on retrieval quality" may be written only if P-tuned's strict count exceeds B1h's at any depth with B1h's line count stated; a correctness tie with a latency or code gap in either direction is reported as that, and the `P-product`/`P-flat` rows measure the product against flat retrieval, not against SQL.

**Amendment 1 to Part 2 (written after the toy build, before the registered run; nothing measured at scale 1.0 yet).** Building the generator against the registered rules showed four things that the text above did not foresee; the code is committed with these changes and the run uses them.
1. *Fan variance.* Ordinary entities carry `randint(6, 14)` facts (mean 10) instead of exactly 10: with a constant fan every target reached over an all-ordinary path at depth d costs exactly `d ln 10`, so the "redrawn when two candidates tie on cost" rule can never be met at d >= 2 (`generate(fan_range=(10, 10))` keeps the registered world for reference). Resulting world at scale 1.0: 4,000 entities (40 hubs), 44,294 facts, 17,956 relations (registered: about 44,800 facts and 16,000 relations; the hub degree is jittered 90-110%).
2. *Question stages.* Hubs carry every predicate and sit within two hops of nearly every anchor, so the registered rule ("no entity within distance < d has P", stage `S0`) cannot produce 25 questions at d = 3. Stage `S1` exempts hubs from the closer-entity test and requires the best-by-rule candidate to be at hop distance exactly d. Each question records its stage and the result file holds the per-depth counts; at scale 1.0 and seed 20261016 the generator gives d = 1: 25 `S0`; d = 2: 25 `S0`; d = 3: 2 `S0` + 23 `S1`. `cost_matters` (best-by-rule differs from best-by-hops-then-id) is 0.44 / 0.92 / 1.00 at d = 1 / 2 / 3, above the 30% floor.
3. *P-product's `top5`.* The product ranks every hop fact behind every direct hit, and a question's anchor entity always has >= 5 direct facts, so `rows[:5]` of `recall(k=5, hops=d)` can never contain a hop fact: prediction (b) "P-product strict <= 15/25 at d = 2" is true by construction and uninformative. It stays as registered and is reported with an added labelled column, `hit_any` (the answer appears anywhere in the returned rows, which hold the k direct hits plus up to 20 hop facts per hop). The product arm is measured as the product behaves; this is a finding about the shipped `recall(hops)` ranking, not a tuning.
4. *B1h fan.* The SQL statement counts an entered entity's fan with a correlated `count(*)` over `facts(entity_id)` (the index the tuned file has) rather than a materialised `GROUP BY` over every fact per question; chosen on engineering grounds before any scale-1.0 measurement. `B1h-untuned` drops the three indexes and `ANALYZE` as registered. Latency is the median of 3 repetitions per question (the `REPS` convention of the other L6 families); the first answer is the one scored.

## §5.4 results (run after the pre-registration and amendment 1 above; 0 LLM calls)

Code: `0111b3a` (SQL arm), `65fbc40` (L6-C + amendment 1), results committed in `d76c507`. FalkorDB 6.0.2 on `plexus-db-13`, SQLite 3.53.1 + sqlite-vec 0.1.9, one machine (Windows 11, FalkorDB in Docker/WSL2, SQLite in process).

### Part 1: L5b with the SQL arm (B1h-L5) — a tie on quality, and what the two sides cost

Source: `plexus/demo_data/crucible/l5/20261017T102955Z-sql-n5/`, `…T103041Z-sql-n15/`, `…T103148Z-sql-n5-burst/` (`results.json`, `report.md`; harness `plexus.crucible.l5 --only forgetting --modes off,sep+mult --sql`, fastembed, seed 20261016, K = 20, 140 probes). Both arms measured in the same process on the same graph / export, paired per probe. The Plexus `sep+mult` numbers differ from the D-013 post-hoc run (85.0%) by id noise between plays, as the D-013 section warned.

| Run | Mode | Arm | recall@1 | recall@3 | recall@5 | noise share | probe ms p50 (client, incl. embedding) | server / statement ms p50 | statements per probe | paired: only Plexus @1 / only SQL @1 / same top-1 / identical top-5 |
|---|---|---|---|---|---|---|---|---|---|---|
| N = 5 | `off` | Plexus | 75.0% | 96.4% | 98.6% | 27.4% | 13.9 | 2.0 | 2 | 0 / 1 / 139 / 136 |
| N = 5 | `off` | B1h-L5 | 75.7% | 96.4% | 98.6% | 27.0% | 13.3 | 6.8 | 1 | |
| N = 5 | `sep+mult` | Plexus | **82.9%** | 100% | **100%** | 20.9% | 30.6 | 6.6 | 4 | 3 / 3 / 134 / 127 |
| N = 5 | `sep+mult` | B1h-L5 | **82.9%** | 100% | **100%** | 20.4% | 17.8 | 10.8 | 3 | |
| N = 15 | `off` | Plexus | 75.7% | 97.1% | 97.9% | 31.7% | 15.1 | 2.7 | 2 | 0 / 0 / 140 / 139 |
| N = 15 | `off` | B1h-L5 | 75.7% | 97.1% | 97.9% | 31.6% | 20.5 | 14.0 | 1 | |
| N = 15 | `sep+mult` | Plexus | **85.7%** | 100% | **100%** | 19.1% | 29.7 | 7.1 | 4 | 3 / 3 / 134 / 124 |
| N = 15 | `sep+mult` | B1h-L5 | **85.7%** | 100% | **100%** | 19.1% | 26.5 | 19.5 | 3 | |
| burst | `off` | Plexus | 75.7% | 96.4% | 98.6% | 22.9% | 14.1 | 2.0 | 2 | 0 / 0 / 140 / 139 |
| burst | `off` | B1h-L5 | 75.7% | 96.4% | 98.6% | 22.7% | 13.3 | 6.9 | 1 | |
| burst | `sep+mult` | Plexus | **84.3%** | 100% | **100%** | 21.6% | 30.6 | 6.6 | 4 | 3 / 3 / 134 / 131 |
| burst | `sep+mult` | B1h-L5 | **84.3%** | 100% | **100%** | 21.4% | 17.7 | 10.8 | 3 | |

Per-class recall@1 is identical between the arms in every `sep+mult` run (critical 0.70 / 0.75 / 0.725, hot 1.0, cold 1.0). "server / statement ms" is FalkorDB's `run_time_ms` summed over the probe's statements for Plexus and the in-process execution time of the statements for SQLite; "probe ms" includes the fastembed query embedding (~8 ms) for both arms.

| Hypothesis (pre-registered) | Result |
|---|---|
| 1. Tie: gap <= 1 probe on recall@1, recall@5 equal, every run; also in `off` | **PASS, a tie.** `sep+mult`: recall@1 and recall@5 identical in all three runs (gap 0 probes); `off`: identical at N = 15 and burst, 1 probe at N = 5 (SQL right, Plexus not). Beneath the identical aggregates **6 probes per run (3 each way) have a different rank-1 fact**. Cause, verified on a K = 3 debug graph where the candidate rows were identical: the exact-keyword bypass is granted only to facts inside the full-text top-`2k` (10) keyword hits, and RediSearch's and FTS5's relevance scores pick different 10 facts out of the 15-25 that match the query words; the bypass then lifts a different same-entity twin to rank 1. The 1-probe `off` difference is the approximate (HNSW) seed set vs sqlite-vec's exact scan. |
| 2. Activation fidelity: SQL `A(f)`, salience and `protected` equal the graph side for every fact | **PASS: 0 disagreements of 480 / 1,080 / 480 facts, worst gap 0.0** (the SQL statement reproduces the D-012 model, the newest-50 window, the suspect-recall rule and the D-013 salience / protection rules exactly). |
| 3. Latency: SQL faster client-side (predicted); server-side sign not predicted | **Mixed.** Client-side p50: SQL faster in `sep+mult` at N = 5 (17.8 vs 30.6 ms) and burst (17.7 vs 30.6), about equal at N = 15 (26.5 vs 29.7); in `off` about equal at N = 5 / burst (13.3 vs 13.9 / 14.1) and **Plexus faster at N = 15 (15.1 vs 20.5)**. Server / statement time: **Plexus faster in every cell** (2.0-7.1 ms vs 6.8-19.5 ms), and SQLite's time grows with the fact count (6.8 ms at 480 facts, 14.0 at 1,080: sqlite-vec's `vec0` is an exact scan, FalkorDB's index is HNSW). Plexus's client-side cost is the network hop per statement (4 statements, ~6 ms each round trip on Docker Desktop), SQLite's is the statement itself. |
| 4. Code: SQL not shorter than the Cypher (predicted); a >= 20% shorter SQL is reported against the "graph is less code" framing | **The SQL is 12% shorter: 92 lines of SQL (3 statements: entities 12, candidates 38, activation 42) against 104 lines of Cypher (5 files).** Below the 20% threshold, so the prediction's direction was wrong but the finding is "about the same". Python around the statements: SQL arm `loc(SqlRecall)` 143 + export 85 + helpers 12 = 240; the Plexus side's recall / entity / candidate / keyword / activation / salience Python = 369 (it also shapes the `why_recalled` output, which the SQL arm does not). Schema: 22 lines of DDL for the SQL arm (incl. one line to configure FTS5 like RediSearch: a stemmer and `_` as a token character; with FTS5's defaults the keyword hits differ, as `billing_cycle` is then two words). |

**Reading.** On L5b the shipped default (`sep+mult`) **ties** a hand-written-SQL arm given the same columns, exactly as the plan pre-registered ("tie by construction"): same recall@1 and recall@5 in every run, the same activation for every fact, 3 statements against 4, 92 lines of SQL against 104 of Cypher, SQLite faster end-to-end in process when the graph is small and the activation read is in play, FalkorDB faster per statement and flat in the fact count. The tie is not a disappointment: the plan's §0 said every scoring rule is a function of columns a relational arm can hold, and this is the measurement. What the comparison also showed about the product: (i) the exact-keyword bypass depends on which 10 facts the full-text engine ranks highest, which is why the two arms disagree on 6 probes while agreeing on the aggregate — a fragile rule worth replacing by "any in-scope exact match"; (ii) the recall path costs 4 round trips (5 with the exact-name fallback), and the client-side latency is round trips, not server time. Limits: one seed, one machine, in-process SQLite against a containerised FalkorDB, the SQL written by the author of the Cypher who knew the probes, no Postgres arm, hash-free (fastembed) vectors shared by export rather than re-embedded.

### Part 2: L6-C multi-hop recall — correctness tie, SQL faster at depth, SQL arm less code; the product never surfaces the multi-hop answer

Source: `plexus/demo_data/crucible/l6/20261017T103929Z-c/results.json` (= `latest-c.json`; the post-hoc product re-run is `…T105100Z-c-fastembed-posthoc/`), `python -m plexus.crucible.l6.run_c --scale 1.0`, seed 20261016, hash embedder, 3 repetitions per question (median latency; first answer scored). World: 4,000 entities (40 hubs), 44,294 facts, 17,956 `RELATES`; 75 questions (25 per depth; stages d1 25 `S0`, d2 25 `S0`, d3 2 `S0` + 23 `S1`; `cost_matters` 0.44 / 0.92 / 1.00). Loads: SQLite 0.5 s, FalkorDB 58 s (44k facts with vectors, then full-text + vector indexes built in the background — a first attempt failed because a schema statement queued behind the index build past the client's 5 s socket timeout; the loader now waits and retries).

| Arm | d = 1 strict / 25 | d = 2 | d = 3 | p50 latency ms d = 1 / 2 / 3 | p99 ms d = 1 / 2 / 3 | server ms p50 (Cypher) d = 1 / 2 / 3 | statements per answer | timeouts | code |
|---|---|---|---|---|---|---|---|---|---|
| **B1h** (SQLite, one recursive CTE, indexed) | **25** | **25** | **25** | 7.5 / 8.2 / **12.6** | 9.9 / 11.0 / 19.0 | — | 1 | 0 | SQL 21 lines; `loc` 32 |
| B1h-untuned (no indexes, no ANALYZE) | 25 | 25 | 21 | 71.9 / 304.7 / 3,197 | 99 / 561 / 5,000 | — | 1 | 4 (d = 3) | same SQL |
| **P-tuned** (level-wise Cypher + Python walk) | **25** | **25** | **25** | **4.7** / 10.7 / 41.3 | 6.2 / 14.7 / 75.5 | 0.7 / 3.5 / 23.2 | 2 / 3 / 4 | 0 | Cypher 18 lines + Python; `loc` 43 |
| P-product (`recall(k=5, hops=min(d, 2))` as shipped) | 0 (`hit_any` 11) | 0 (`hit_any` 6) | 0 (not answerable; `hit_any` 1) | 32.1 / 41.3 / 51.1 | 39 / 59 / 57 | 10.8 / 12.1 / 13.4 | 6 / 7 / 7 | 0 | product |
| P-flat (`recall(hops=0)`) | 0 | 0 | 0 | 20.7 / 20.3 / 21.0 | 23 / 22 / 24 | 8.4 / 7.7 / 8.3 | 4 | 0 | product |

P-tuned and B1h returned **identical top-5 lists on 75 / 75 questions**, both equal to the generator's truth.

| Prediction (pre-registered) | Result |
|---|---|
| (a) Correctness tie B1h = P-tuned = 25/25 at every depth | **PASS: 75/75 each, identical lists.** |
| (b) P-product strict <= 15/25 at d = 2, 0/25 at d = 3; P-flat <= 3/25 | **PASS as written, but by construction** (amendment 1 §3): the product ranks hop facts behind every direct hit, so `rows[:5]` never holds one; P-flat 0/75. The labelled `hit_any` column (the answer anywhere in the returned rows) is 11 / 6 / 1 of 25 under the hash embedder. A labelled **post-hoc** re-run of the two product arms with fastembed (`…T105100Z-c-fastembed-posthoc/`, load 355 s) is *worse*: `hit_any` 3 / 1 / 0, strict 0 / 75 both arms, P-product p50 41 / 63 / 58 ms. **Causes, found after the run on a scale-0.3 copy** (`$TMPDIR/l6c_dbg.py`): (i) the hop walk starts from the entities of the *direct* hits, and the direct hits are mostly not the anchor's facts — with either embedder, facts of entities sharing one name word (`bupor kinel` for the anchor `bupor zekel`) are as near to the query as the anchor's own facts, although `recall_entities` has already resolved the anchor by name; (ii) the 20-entities-per-hop cap is filled **alphabetically by entity name** (`relations.expand_hops`: `sorted(found, key=(to_name, to_id))[:20]`), so with five seed entities' neighbourhoods competing, an answer entity whose name sorts late is dropped before its facts are ever read; (iii) hop facts carry a flat +0.25 distance penalty per hop and are appended behind every direct hit, whatever the direct hits' relevance. Under the hash embedder a fourth effect adds noise: 384-d token hashing of ~140 words collides, so dozens of facts tie with the anchor's at distance 0.4037 and the index returns an arbitrary 40. |
| (c) Latency: B1h faster at d = 1 and 2; gap narrows or flips at d = 3 (sign not predicted) | **Wrong on both ends.** At d = 1 the level-wise Cypher is *faster* (4.7 vs 7.5 ms, with the network hop); at d = 2 SQL is faster (8.2 vs 10.7); at d = 3 **SQL widens its lead to 3.3x (12.6 vs 41.3 ms)**: the Cypher's third hop touches thousands of entities (the hubs' neighbourhoods) and counts each one's fan in a pattern comprehension (server 23 ms), while the indexed recursive CTE, although it enumerates paths, finishes in 12.6 ms. The L6-A reference (SQL faster on the big blast) held here too. **B1h-untuned is 10x / 37x / 250x slower** than B1h at d = 1 / 2 / 3 and times out on 4 of 25 at d = 3: the opposite of L6-A's 1.4x; here the two `relates` indexes are what make the CTE fast. |
| (d) Code: SQL statement shorter than the Cypher arm | **The SQL statement is 21 lines; the Cypher is 18 lines of Cypher plus the Python level-wise driver (`loc` 43 against 32 for the whole SQL arm).** Whole arm: SQL is 26% less code; statement literals alone: the Cypher is 3 lines shorter but cannot run without the driver. |

**Reading (plan §5.4's rule).** L6-C does **not** earn "beats SQL on retrieval quality": with the same traversal rule hand-written on both sides the arms tie on every question; the SQL arm is faster at depth 2 and 3 (3.3x at d = 3), needs one statement against 2-4, and is less code overall; the graph side is faster only at depth 1 and in server time per statement. The product's own `recall(hops)` (the thing an agent can call) never puts the multi-hop answer in its top 5 — by its ranking rule, independent of the embedder — and finds it anywhere in the result for 11 / 25 at d = 1 and 6 / 25 at d = 2 with the hash embedder, 3 / 25 and 1 / 25 with fastembed. That is a product finding (three defects: the walk starts from the direct hits' entities rather than the entity the query names, although `recall_entities` already resolves it; the per-hop entity cap is filled alphabetically; hop facts are ranked behind all direct hits however relevant), not a graph-vs-SQL finding, and it is the next product fix, as a new pre-registration. Limits: one seed; oracle-quality relations from one generator; the depth-3 questions needed the `S1` relaxation (23 of 25 exempt hubs from the "no closer entity" rule); SQLite in process against a containerised FalkorDB; both hand-written arms by the author who wrote the generator.

## Predicate cue pre-registration (CROSS_CHECK §3.2 + §3.3): the L5b same-entity residual and the plan's §5.3 hub variant; written before any run

Spec: `docs/research/neuro-memory/CROSS_CHECK.md` §3.2 (the predicate as a second ACT-R cue), §3.3 (the named entity's facts join the candidates) and appendix A.2–A.3; `docs/research/MEMORY_FORGETTING_IMPLEMENTATION_PLAN.md` §5.3 (the hub variant, deferred by the L5b-D013 and §5.4 runs). Branch `feature/neuro-memory-research`, worktree `wt-neuro-memory`, FalkorDB 6.0.2 on `plexus-db-13`. Code under test: the commit that adds this section (the implementation is in it; nothing has been run against a graph except the unit / integration tests). LLM calls: 0. P2 stays opt-in and untouched; P3 is not built; the §5.4 SQL arm is **not** re-run (see "what is not claimed" below).

**What changed in the product (shipped default, `PLEXUS_ACT_CUES=entity+predicate`).** The separation term of D-013 was one cue: `sep = gamma · max(0, 1 − ln fan / S_max)` for facts about the entity the query names (`gamma = 0.15`, `S_max = ln 50`). It is now the ACT-R context term over two cues, `sep = w_entity · max(0, S − ln fan_entity) + w_predicate · max(0, S − ln fan_predicate)` with `w_entity = 0.6`, `w_predicate = 0.4`, `S = 5` (CROSS_CHECK §3.2, the constants as recommended there), where a fact matches the entity cue when the query names its entity (unchanged rule: every word of the entity name in the query) and the predicate cue when the query names its predicate (the same rule applied to the words of `Fact.predicate`, which is stored normalised: `api_version` is the words `api` and `version`); `fan_predicate` = current facts with that predicate in the searched scopes, read by the new `engram/recall_predicates` (one `Fact.predicate` index seek per named predicate; the candidates' predicates are the ones tested, since only a candidate can be lifted). Two implementation choices that deviate from the appendix text, fixed before the run: (i) **each cue is floored at 0** (`max(0, S − ln fan)`), so a hub cue with fan > e^5 ≈ 148 adds nothing rather than subtracting — the appendix's bare `S − ln fan` would push a 200-fact hub's own facts *below* unrelated facts; (ii) the RELATES-neighbour half-weight of A.3 is not implemented (no relation is walked at hop 0). §3.3: the named entities' own current facts join the candidate set before scoring (one bounded read in the `engram/recall_hop_facts` shape at hop 0, the `2k` facts nearest to the query per named entity; a fact the vector / keyword fetch already returned keeps its row). `PLEXUS_ACT_CUES=entity` restores the single-cue term exactly (the L5b harness mode `sep-entity`); `PLEXUS_RECALL_SEPARATION=off` is unchanged and the identity test (`tests/activation/test_recall_off.py`) is the guard. Cost: two more bounded reads per recall that names an entity.

**Why these constants are a prediction, not a fit.** On the L5b probe (A.2) the named fact gets `0.6·(5 − ln 12) + 0.4·(5 − ln 20) ≈ 2.06` nats, its same-entity sibling `≈ 1.26`, its other-entity twin `≈ 0.80`; the median rank-1/rank-2 cosine gap measured in L5b-D013 is 0.017 in relevance (≈ 0.02 nats). So any fact that is a candidate and matches both cues outranks every candidate that matches one — the cue structure, not the weights, decides; `w_entity > w_predicate` only orders the two one-cue classes (sibling above twin). The constants will not be tuned after the run; if the run says they are wrong, the number of record is the pre-registered one and a labelled sensitivity run may follow.

### Part 1: L5b-D013 `sep` re-run with the two-cue term (the 20 same-entity rows)

**Design.** Exactly the L5b-D013 design (K = 20, 90 simulated days, seed 20261016, fastembed, probes `"<subject> <predicate>"`, 140 real facts: critical 80, hot 9, cold 51), three runs: N = 5, N = 15, N = 5 `--burst`; `python -m plexus.crucible.l5 --only forgetting --modes off,sep-entity,sep,sep+mult --tag pc-n5|pc-n15|pc-n5-burst`. Modes: `off` (control), `sep-entity` (the single-cue term P1 first shipped, forgetting off: the in-run control that should reproduce the committed 85.7% within id noise — a fresh play gives new ids, as the §5.4 section warned), `sep` (the two-cue term, forgetting off: the registered number), `sep+mult` (the shipped default: two cues + the D-012 multiplier). Same columns as L5b-D013; the same-entity / other-entity split of the rows above the target is the column this run exists for.

**Hypotheses and decision rules (N = 5 is the registered run; N = 15 and burst are reported with the same rules as stress cases).**
1. `sep` recall@1 ≥ **0.95** (the 20 same-entity rows were 20 of 140 probes; the prediction is that the predicate cue clears all but a handful). **Falsified** if `sep` recall@1 ≤ `sep-entity` recall@1 + 0.02 (no gain beyond id noise): then a candidate's predicate is not what the query word matches on this data, and the fix is elsewhere.
2. Same-entity rows above the target under `sep` ≤ 5 (20 under the committed `sep`); other-entity rows stay 0.
3. `sep` recall@5 ≥ `sep-entity` recall@5 (100% in L5b-D013); critical loss 0.
4. Noise share under `sep` ≤ `sep-entity` + 0.01: the predicate cue lifts the asked fact only (noise predicates are unique, `review_note_123`, and their words are not in the query), so it cannot raise the noise share; a *drop* is expected because the asked fact now displaces the entity's noise facts from the top 5 more often.
5. `sep+mult` recall@1 within 1 probe (0.72 points) of `sep`: the multiplier cannot reorder what a 1-nat cue gap orders.
6. Reported, not a criterion: the `gap12` distribution (unchanged by construction: measured in `off`), the entity read ms, statements per probe (expected 5 for `sep`, 6 for `sep+mult`, against 4 / 5 before), probe ms p50.

**What I expect, stated plainly.** Confident on 1–3 if the asked fact is a candidate — and the §3.3 union makes it one whenever the entity is resolved. The residual I can see in advance: probes whose predicate word is also a word of *another* predicate of the same entity (`api_version` vs `version_policy` share `version`, but the rule needs every word of the predicate, so only a predicate that is a strict sub-multiset of the query's words is a false cue); and entities the lexical rule does not resolve (none in L5b: every subject is named verbatim). On the noise share I am less sure of the direction than of the bound.

### Part 2: the plan's §5.3 hub variant (one entity, 200 facts of distinct predicates)

**World (`plexus.crucible.l5.hub`, seed 20261016, fastembed, no reads simulated, forgetting off in every arm).** One scope. The hub `Atlas Core Platform` with 200 active facts whose predicates are distinct two-word names `w1_w2` (20 × 10 word pairs); 40 ordinary entities (two-word names from disjoint word lists) with 5 facts each whose predicates are drawn from the same pool, so a predicate's fan is ≈ 2 (CROSS_CHECK §3.2 says "1 in the hub variant"; the ordinary entities exist so that the hub's facts compete with other entities' facts under the *same* predicate, the harder case). Values are short phrases that never contain a predicate or entity word, so the full-text keyword path returns nothing and the exact-keyword bypass never fires: the vector seeds, the §3.3 union and the cues alone decide. 200 probes, one per hub fact: `"Atlas Core Platform <predicate>"`. Arms, all `mult`: `off` (separation off: relevance only), `sep-entity` (the single damped cue, `S_max = ln 50`: zero lift at fan 200 — the committed P1), `sep-flat` (the plan's "flat entity boost without the fan term": `cues=entity` with `S_max = 20`, the settings cap, so all 200 hub facts get the same `0.15 · (1 − ln 200 / 20) ≈ 0.11` lift), `sep` (the two-cue term, shipped default). Metrics per arm: recall@1, recall@5, the share of probes with another hub fact **above the target** (the sharp reading of the plan's "an arbitrary fact of the hub"), the share with another hub fact **anywhere in the top 5** (the plan's wording as written), the mean number of candidates the §3.3 union added, probe ms p50, statements per probe.

**Hypotheses and decision rules.**
1. `sep` recall@1 ≥ **0.90** (plan §5.3). **Falsified** if < 0.80.
2. `sep-flat`: another hub fact *above the target* for ≥ 30% of probes, and another hub fact *in the top 5* for ≥ 30% (plan §5.3's claim, both readings).
3. `sep` recall@1 − `sep-entity` recall@1 ≥ 0.10: the predicate cue, not the §3.3 union or the damped expansion, is what the hub variant needs. (`sep-entity` already includes §3.3, so this isolates the cue.)
4. `sep-entity` recall@1 within 2 probes (0.01) of `off`: the committed P1 term gives a 200-fact hub nothing, as its own test (`test_a_hub_entity_gets_no_lift`) documented.
5. Under `sep`, another hub fact above the target ≤ 10%.
6. Stated in advance so it cannot be read as a result: "another hub fact in the top 5" will be high (likely > 90%) under **every** arm including `sep`, because the hub's 200 facts are 50% of the graph and the entity cue (where it applies) lifts all of them equally; the plan's metric does not discriminate between the forms and is reported as written next to the sharper "above the target" one.

**What I expect, stated plainly.** `off` and `sep-entity` close to each other and well below 0.9 (relevance alone among 200 near-identical fact texts, fastembed); `sep-flat` equal to `sep-entity` on recall@1 (a flat lift reorders nothing within the hub); `sep` ≥ 0.9 if the asked fact is among the candidates — the §3.3 union adds the 10 nearest hub facts to the query, which should contain it, but "should" is the thing under test. If `sep` fails while `entity_facts_added` is 0 for the missed probes, the defect is candidate starvation (§3.3's bound), not the cue; both are reported.

**What is not claimed, whatever the result.** The §5.4 SQL arm (B1h-L5) implements the single-cue term and is not re-run here: a gap between Plexus and that arm after this change would be the arm lacking a feature, not a graph advantage (plan §0: every scoring rule here is a function of columns a relational arm can hold, and the predicate fan is a `GROUP BY predicate` count). The "tie on L5b" and "no family beats SQL on quality" readings of §5.4 and `PLEXUS_REPORT.md` stand; only the *flat-retrieval* margins of the product change.

## Predicate cue results (registered runs; 0 LLM calls) and a labelled post-hoc sensitivity

Source: `plexus/demo_data/crucible/l5/20261017T125546Z-pc-n5/`, `…T125634Z-pc-n15/`, `…T125738Z-pc-n5-burst/`, `…T125826Z-pc-hub/` (`results.json`, `report.md`); code `468601e` (the pre-registration commit); FalkorDB 6.0.2 on `plexus-db-13`, fastembed, seed 20261016. Each L5b run ~45 s, the hub run ~2 min.

### Part 1: L5b — falsified; the 20 rows were never a predicate-cue problem

| Run | Mode | recall@1 | recall@5 | noise share | critical loss | above target: same entity / other entity | statements / probe | probe ms p50 (server) |
|---|---|---|---|---|---|---|---|---|
| N = 5 | `off` | 75.7% | 98.6% | 22.9% | n/a | 38 / 13 | 2 | 14.2 (2.1) |
| N = 5 | `sep-entity` (single cue, P1 as shipped + §3.3) | 85.7% | 100% | 28.4% | 0 | 20 / 0 | 5 | 26.0 (5.0) |
| N = 5 | **`sep` (two cues, 0.6 / 0.4 / S = 5)** | **85.7%** | **100%** | **32.3%** | 0 | **20 / 0** | 5 | 25.6 (5.0) |
| N = 5 | `sep+mult` (two cues + multiplier) | 85.7% | 100% | 28.1% | 0 | 20 / 0 | 6 | 40.5 (9.2) |
| N = 15 | `off` | 76.4% | 98.6% | 31.0% | n/a | 40 / 11 | 2 | 15.0 (2.7) |
| N = 15 | `sep-entity` | 85.7% | 100% | 32.9% | 0 | 20 / 0 | 5 | 26.7 (6.2) |
| N = 15 | **`sep`** | **85.7%** | **100%** | **43.6%** | 0 | **20 / 0** | 5 | 26.8 (6.1) |
| N = 15 | `sep+mult` | 85.7% | 100% | 31.6% | 0 | 20 / 0 | 6 | 40.3 (10.0) |
| burst | `off` | 75.0% | 98.6% | 24.9% | n/a | 40 / 12 | 2 | 13.9 (2.0) |
| burst | `sep-entity` | 85.7% | 100% | 29.6% | 0 | 20 / 0 | 5 | 26.3 (5.3) |
| burst | **`sep`** | **85.7%** | **100%** | **33.1%** | 0 | **20 / 0** | 5 | 25.6 (5.1) |
| burst | `sep+mult` | 85.7% | 100% | 26.9% | 0 | 20 / 0 | 6 | 42.0 (9.8) |

| Hypothesis (pre-registered) | Result |
|---|---|
| 1. `sep` recall@1 ≥ 0.95; **falsified** if ≤ `sep-entity` + 0.02 | **FALSIFIED** at every N: `sep` = `sep-entity` = 85.7%, the same 20 probes miss, the same 20 rows sit above them. |
| 2. Same-entity rows above the target ≤ 5; other-entity 0 | **FAIL** (20) / PASS (0). |
| 3. recall@5 ≥ `sep-entity`'s; critical loss 0 | PASS (100%, 0). |
| 4. Noise share ≤ `sep-entity` + 0.01 | **FAIL** at every N: +3.9 / +10.7 / +3.5 points (N = 5 / 15 / burst). |
| 5. `sep+mult` within 1 probe of `sep` | PASS (identical). |

**Why, found after the run on a kept graph (`$TMPDIR/pc/diag_misses.py`, same seed).** Every one of the 20 misses is the scenario's designed **auth conflict**: `scale_scenario.py` asserts, for each of the 20 sprint subjects, `auth_method = JWT bearer tokens (…)` and then `auth_method = API key in X-…-Key header` as a `CONTRADICTS` pair, and both stay *active* in the same scope. Both are real facts, both are probes (`"<subject> auth_method"`), and for either probe the other is a candidate that matches **both cues identically** (entity fan 10, predicate fan 40, `sep` 2.14 nats each): the only thing that separates them is the value, which the probe does not name. One of each pair must therefore lose rank 1, so **85.7% (120 / 140) is the recall@1 ceiling of L5b for any scorer that does not read the value** — and P1 had already reached it in L5b-D013. Two earlier readings were wrong and are corrected here: the L5b-D013 results section called the residual "another predicate of the same sprint subject" (it is the *same* predicate, a contradicting pair), and CROSS_CHECK §3.2's claim that the L5b residual is a predicate-cue problem was built on that reading. The plan's 0.90 target was unreachable by construction. The ordering inside a contradicting pair is a different question (recency? the P3 reliability term? `resolve_contradiction`), not a cue question, and it is not decided here.

**Where the noise went.** Two separate effects, both costs of this change on L5b, where neither mechanism had anything to fix:
- `sep-entity` (28.4%) sits above the committed `sep` of L5b-D013 (23.3%) although it is the same scoring term; the only code difference is the **§3.3 union** (the named entity's `2k` nearest facts always join the candidates — on L5b that is the subject's 5 noise facts, whose values mention the predicate word, which the 4·k vector over-fetch had often missed). The union makes recall *complete* about the named entity; the noise-share metric counts that completeness as worse. (Attribution by elimination, not by a switch: the union has no off switch.)
- `sep` above `sep-entity` (+3.9 / +10.7 / +3.5 points) is the **magnitude of the entity cue** under CROSS_CHECK's constants: `0.6 · (5 − ln 12) ≈ 1.26` nats (×3.5 in relevance) against P1's `0.075` (×1.08). At ×3.5 every fact about the named entity, noise included, outranks every real fact about any other entity; at ×1.08 only near-ties flip. The predicate cue itself cannot raise the noise share (noise predicates are unique and never named), and the post-hoc rows below confirm the dependence is on the weights.
Rank-1/rank-2 gap p50: `off` 0.0167, `sep-entity` 0.0262, `sep` 0.0309 (the cues widen the margin at rank 1 — but on the 20 pairs it is 0 by construction). Statements per probe 5 (`sep`) / 6 (`sep+mult`), against 4 / 5 before: the entity-facts read and the predicate-fan read; `sep+mult` probe ms p50 40.5 against the §5.4 run's 30.6 for the same mode (two more round trips at ~5 ms each on Docker Desktop).

### Part 2: the hub variant — passes, but relevance alone nearly passes it too

Source: `…T125826Z-pc-hub/`. World as registered: hub fan 200 (resolved by name), 40 × 5 ordinary facts, 400 facts, predicate fan mean 2.00 (max 6), 200 probes; the keyword path returned nothing (values carry no query word), `entity_facts_added` 0.0 for every arm (the 10 vector seeds already held the hub's nearest facts).

| Arm | recall@1 | recall@5 | other hub fact above the target | other hub fact in the top 5 | probe ms p50 | statements / probe |
|---|---|---|---|---|---|---|
| `off` | 97.5% | 100% | 2.5% | 100% | 15.5 | 2 |
| `sep-entity` (single cue, zero at fan 200) | 97.5% | 100% | 2.5% | 100% | 29.5 | 5 |
| `sep-flat` (flat entity boost, `S_max = 20`) | 97.5% | 100% | 2.5% | 100% | 29.2 | 5 |
| **`sep` (two cues)** | **100%** | 100% | **0.0%** | 100% | 29.8 | 5 |

| Hypothesis (pre-registered) | Result |
|---|---|
| 1. `sep` recall@1 ≥ 0.90; falsified if < 0.80 | **PASS** (100%). |
| 2. Flat boost: another hub fact above the target ≥ 30%; in the top 5 ≥ 30% | **FAIL** (2.5%) / PASS (100%, as predicted in rule 6: uninformative). |
| 3. `sep` − `sep-entity` ≥ 0.10 | **FAIL** (+2.5 points: 5 probes). |
| 4. `sep-entity` within 0.01 of `off` | PASS (equal). |
| 5. `sep`: another hub fact above the target ≤ 10% | PASS (0%). |

**Reading.** The plan's §5.3 world, as specified (200 distinct predicates, one entity), is solved by cosine relevance alone with fastembed: 195 of 200 probes put the asked fact first with no cue at all, so the plan's prediction that a flat entity boost "returns an arbitrary fact of the hub in the top 5 for ≥ 30%" is false in its sharp reading (2.5% above the target) and vacuous in its literal one (100% under every arm, since the hub is half the graph). The predicate cue fixed the remaining 5 (97.5 → 100%, 0 hub facts above the target) — real, small, and the only measured benefit of this change. My pre-run expectation ("`off` well below 0.9") was wrong; the variant is weak evidence either way. What would make it informative is a hub whose facts share words across predicates or a weaker embedder; not run.

### Labelled post-hoc sensitivity (weights chosen after the registered run; not confirmatory)

`plexus/demo_data/crucible/l5_posthoc/pc/20261017T130229Z-sens-n5/` (L5b, N = 5) and `…T130406Z-sens-hub/` (the hub world), same seed and code, the two-cue term with the weights scaled down 10× and 20× (the 0.6 : 0.4 ratio and `S = 5` kept):

| Term | L5b recall@1 | L5b recall@5 | L5b noise share | same / other entity | hub recall@1 | hub: other hub fact above target |
|---|---|---|---|---|---|---|
| `off` | 75.7% | 98.6% | 23.6% | 36 / 13 | 97.5% | 2.5% |
| `sep-entity` (single cue) | 85.7% | 100% | 29.4% | 20 / 0 | 97.5% | 2.5% |
| `sep` 0.6 / 0.4 (registered) | 85.7% | 100% | 33.6% | 20 / 0 | 100% | 0% |
| `sep` 0.06 / 0.04 | 85.7% | 100% | 31.9% | 20 / 0 | 100% | 0% |
| `sep` **0.03 / 0.02** | 85.7% | 100% | **27.9%** | 20 / 0 | 100% | 0% |

The noise share is monotone in the entity-cue weight and at `w_entity = 0.03` — the scale at which the entity cue at fan 12 (`0.03 · (5 − ln 12) = 0.075`) equals the P1 lift that cleared every cross-entity twin — the two-cue term is below the single-cue form on noise (27.9 vs 29.4%) at the same recall, and still 100% on the hub. In other words CROSS_CHECK §3.2's *structure* (two cues, `S − ln fan`, no zero at fan 50) holds up; its *magnitude* (per-nat weights 0.6 / 0.4) is ~20× too large for a term that is added to ln-cosine, where the twin gaps are 0.02–0.07 nats. The number of record for this task stays the registered one (85.7% recall@1, noise 32.3% at N = 5); what to ship is decided by the confirmatory run below, not by this table.

## Predicate cue confirmatory pre-registration (post-hoc weights, D-012-floor precedent); written before the run

Candidate default: `PLEXUS_ACT_W_ENTITY = 0.03`, `PLEXUS_ACT_W_PREDICATE = 0.02`, `PLEXUS_ACT_CUE_S = 5`, `PLEXUS_ACT_CUES = entity+predicate` (the structure of CROSS_CHECK §3.2 at P1's magnitude). Runs: L5b N = 5, N = 15, N = 5 burst, `--modes off,sep-entity,sep[w_entity=0.03;w_predicate=0.02],sep+mult[w_entity=0.03;w_predicate=0.02] --tag pcc-*` (fresh plays: new ids; the N = 5 sensitivity row above is *not* reused). The hub world is deterministic in the seed and was measured at these weights in the sensitivity run (100%); it is not re-run.

Decision rules (all three runs; a failure in any one is a failure):
1. `sep[0.03/0.02]` recall@1 = `sep-entity` recall@1 (the ceiling, 85.7%); **falsified** if lower by ≥ 1 probe.
2. `sep[0.03/0.02]` noise share ≤ `sep-entity` noise share + 0.005 in every run (**falsified** otherwise: then the sensitivity row was id noise).
3. recall@5 100%, critical loss 0, other-entity rows 0 (unchanged from P1).
4. `sep+mult[0.03/0.02]` recall@1 within 1 probe of `sep[0.03/0.02]`.

Outcome rule, stated now: if 1–4 pass, the shipped default becomes the two-cue term at 0.03 / 0.02 / 5 (recorded in D-013 as a post-hoc-then-confirmed constant, like the 0.9 floor); if any fails, the shipped default reverts to `PLEXUS_ACT_CUES=entity` (P1 exactly as it was) and the two-cue term stays opt-in. Either way the §3.3 union stays on (it is a completeness fix for the named entity's own facts and its cost on L5b is recorded above), and `PLEXUS_RECALL_SEPARATION=off` is unchanged.

## Predicate cue confirmatory results (run after the confirmatory pre-registration above; 0 LLM calls)

Source: `plexus/demo_data/crucible/l5/20261017T130612Z-pcc-n5/`, `…T130659Z-pcc-n15/`, `…T130804Z-pcc-n5-burst/`; code `2d0ec96` (the confirmatory pre-registration commit; same scoring code as `468601e`, weights passed as mode overrides); FalkorDB 6.0.2 on `plexus-db-13`, fastembed, seed 20261016, fresh plays.

| Run | Mode | recall@1 | recall@5 | noise share | critical loss | above target: same / other entity |
|---|---|---|---|---|---|---|
| N = 5 | `off` | 75.7% | 98.6% | 24.3% | n/a | 36 / 13 |
| N = 5 | `sep-entity` | 85.7% | 100% | 29.7% | 0 | 20 / 0 |
| N = 5 | **`sep[0.03/0.02]`** | **85.7%** | 100% | **28.0%** | 0 | 20 / 0 |
| N = 5 | **`sep+mult[0.03/0.02]`** (the shipped default) | **85.7%** | **100%** | **20.6%** | 0 | 20 / 0 |
| N = 15 | `off` | 77.1% | 97.9% | 33.1% | n/a | 37 / 12 |
| N = 15 | `sep-entity` | 85.7% | 100% | 31.9% | 0 | 21 / 0 |
| N = 15 | **`sep[0.03/0.02]`** | **85.7%** | 100% | **30.7%** | 0 | 20 / 0 |
| N = 15 | **`sep+mult[0.03/0.02]`** | **85.7%** | **100%** | **20.9%** | 0 | 20 / 0 |
| burst | `off` | 75.7% | 98.6% | 23.4% | n/a | 36 / 13 |
| burst | `sep-entity` | 85.7% | 100% | 29.0% | 0 | 20 / 0 |
| burst | **`sep[0.03/0.02]`** | **85.7%** | 100% | **25.6%** | 0 | 20 / 0 |
| burst | **`sep+mult[0.03/0.02]`** | **85.7%** | **100%** | **20.7%** | 0 | 20 / 0 |

| Rule (pre-registered) | Result |
|---|---|
| 1. `sep[0.03/0.02]` recall@1 = `sep-entity`'s (85.7%); falsified if lower by ≥ 1 probe | **PASS** in all three runs (equal). |
| 2. noise share ≤ `sep-entity` + 0.005 in every run | **PASS**: −1.7 / −1.2 / −3.4 points. |
| 3. recall@5 100%, critical loss 0, other-entity rows 0 | **PASS** in all three. |
| 4. `sep+mult[0.03/0.02]` within 1 probe of `sep[0.03/0.02]` | **PASS** (equal). |

**Outcome (by the rule stated before the run).** The shipped default is the two-cue context term at `w_entity = 0.03`, `w_predicate = 0.02`, `S = 5` (`PLEXUS_ACT_CUES=entity+predicate`), set as the code defaults in the commit after this section. The shipped default (`sep+mult`) now measures recall@1 **85.7%** (the L5b ceiling), recall@5 **100%**, noise share **20.6–20.9%**, critical loss 0, cross-entity displacers 0 — against D-013 as first shipped (85.0% / 100% / 22.1%, post-hoc run) and the §5.4 paired run (82.9–85.7% / 100% / 19.1–21.6%). Honest reading of the gain: recall@1 is unchanged in substance (the ceiling was already reached; the +0.7 is id noise between plays), the noise share is ~1 point lower than D-013's shipped default and the hub edge case is fixed; the cost is two bounded reads (5 → 6 statements with forgetting on, ~+10 ms per probe on Docker Desktop). The §5.4 SQL arm was not re-run (see "what is not claimed" in the first pre-registration): the tie claim stands, the SQL arm lacks the predicate feature by omission, not by inability.

## Audit fixes re-run pre-registration (`docs/research/CYPHER_AUDIT_SUMMARY.md` C1–C5, P1–P3, B1–B2, `BRANCH_REVIEW.md` 1–2); written before any run

The fixes sit on three paths the published numbers came from: the L5b ranking path (C1 `artifacts_ok`, C2 `recall_hop_facts`
diamond duplicates, finding 1 salience protection gated on `add`, finding 2 `rerank` → `score.score()`), the L6 blast-radius path
(C4 `impact_fact` root-first, P1 `quarantine` tail, B1 `forget_source` tail) and the write path every arm uses (P3 empty-list seeks in
`link_step` / `record_decision` / `handoff` / `complete_task` / `create_tasks` / `record_recall` / `create_scope`, C3 `assert_fact`
nearest-first `soft` cut). Runs, same seeds and worlds as the published ones, 0 LLM calls, on `plexus-db-13`:
L5b `--only forgetting --modes off,sep+mult[w_entity=0.03;w_predicate=0.02]` at N = 5, N = 15 and N = 5 burst (seed 20261016,
fastembed, `--tag afx-*`); L6 `postfix` (A `impact` arms + F, 200 kills) and L6 `conc` (E: the quarantiner uses `lineage/quarantine`).

**Expectation, grounded in the fixtures (checked in the code before the run):**
1. **C1 and finding 1 change no L5b number.** The L5b world never calls `verify_artifact` or `verify_fact` (no `VERIFIED_BY` edge on
   any Artifact or Fact: `crucible/l2/scenario.py` has no such call), the simulated reads are all by one agent (`l5-reader`,
   `crucible/l5_add_reads`), so `use_agents` is 0 from the schedule, and every remaining salience input (decision, handoff, pin, trusted
   source) coincides with a D-012 boolean rule that protects in both modes. The only path left is a fact used (`via = 'use'`) by ≥ 3
   distinct scenario agents through their own Steps with no decision or handoff on it; not expected, and if any `sep+mult` number
   moves this is the first place to look.
2. **C2 changes no L5b number.** L5b scopes are `global` plus `project:` / `user:` scopes that inherit `global` (`mcp/tenant.py`): a
   tree, no diamond, so every fact is reached over exactly one `INHERITS` path.
3. **Finding 2 is an identity rewrite** (`score()` and the inline formula agreed; `tests/activation/test_rank_d013.py` pins it), and
   `mult` mode never goes through it: no L5b number moves.
4. **C3 / P3 change no L5b number**: the L5b world has at most one same-`dup_key` candidate per assertion (the cap never bites), and
   the P3 rewrite changes plan shape, not rows.
5. **L6:** A `impact` stays 24/24 strict (service) / 18/24 (tool, list cap) with the same counts; C4 moves the root fact to the front
   of `fact_ids` (`impact_fact` only; the A arm reads `impact('source')`, unchanged). F stays 0 orphans. E stays 0 violations for
   `P-1stmt` with a *higher* quarantine count per run expected (P1: the quarantiner's statement is faster) — a timing-dependent
   count, not a quality number. Wall times are reported but are not a hypothesis (Docker Desktop noise, 2× swings).

**Decision rule:** a changed recall@1 / recall@5 / noise share / critical loss in any L5b run, or a changed L6 A/E/F correctness
count, is reported as a change and explained from the fixes above (or reported as unexplained); `PLEXUS_REPORT.md` is updated only if
a published number moves. The pre-fix result directories are kept.

## Audit fixes re-run results (run after the pre-registration above; 0 LLM calls)

Source: `plexus/demo_data/crucible/l5/20261017T160947Z-afx-n5/`, `…T161106Z-afx-n15/`, `…T161259Z-afx-n5-burst/`,
`plexus/demo_data/crucible/l6/20261017T163122Z-postfix/`, `…T164411Z-conc/`; code = the commit after this section (all audit
fixes applied); FalkorDB 6.0.2 on `plexus-db-13`, fastembed, seed 20261016, fresh plays. The pre-fix directories are unchanged.

| Run | Mode | recall@1 | recall@5 | noise share | critical loss | above target: same / other | published (`pcc-*`) |
|---|---|---|---|---|---|---|---|
| N = 5 | `sep+mult[0.03/0.02]` | **85.7%** | **100%** | 22.1% | 0 | 20 / 0 | 85.7% / 100% / 20.6% / 0 / 20 / 0 |
| N = 15 | `sep+mult[0.03/0.02]` | **85.7%** | **100%** | 19.9% | 0 | 20 / 0 | 85.7% / 100% / 20.9% / 0 / 20 / 0 |
| burst | `sep+mult[0.03/0.02]` | **85.7%** | **100%** | 21.0% | 0 | 20 / 0 | 85.7% / 100% / 20.7% / 0 / 20 / 0 |
| N = 5 | `off` (control: no fixed code on its path) | 75.0% | 98.6% | 24.6% | n/a | 38 / 13 | 75.7% / 98.6% / 24.3% / 36 / 13 |
| N = 15 | `off` | 77.1% | 98.6% | 29.1% | n/a | 35 / 12 | 77.1% / 97.9% / 33.1% / 37 / 12 |
| burst | `off` | 75.7% | 98.6% | 23.3% | n/a | 39 / 13 | 75.7% / 98.6% / 23.4% / 36 / 13 |

**Reading, by the decision rule.** Every quality number of the shipped default is unchanged: recall@1 85.7% (the ceiling),
recall@5 100%, critical loss 0, cross-entity displacers 0, same-entity rows 20, in all three runs — as pre-registered for C1, C2,
finding 1, finding 2, C3 and P3. The noise share moved by +1.5 / −1.0 / +0.3 points. That is play-to-play id noise, not the fixes:
the `off` control arm, whose path contains none of the changed code, moved by as much or more in the same plays (−4.0 points at
N = 15; recall@1 −0.7 at N = 5; recall@5 +0.7 at N = 15), and the published text already records the same band between plays
(`sep+mult` 19.1–22.1% across the D-013, §5.4 and pcc plays). No published number is updated.

**L6.** A `impact`: B1h 24/24, P-tuned 24/24, P-product-service **24/24 strict, 0 timeouts** (p50 9.4 ms, p99 638 ms; published
13.2 / 626), P-product-tool 18/24 (the 2,000-id list cap, as published; p50 11.2, p99 643). F: **0 orphans** of 1,458 records (814
facts, 336 decisions, 308 handoffs), 0 lost of 1,383 acknowledged writes, `missing_derived_from` 13 (published: 0 of 1,842, 13).
E: `P-1stmt` **0 / 0 / 0** violations in 10/10 runs (reads 15,127, appends 8,925, quarantines 200; published 14,377 / 8,323 /
200); the other six arms as published (`P-levelwise`, `B1h-levelwise`, `B0-naive` tear in 10/10; the other three 0). The
pre-registered "higher quarantine count" expectation for E was wrong in form: the count is the number of `Q` sources (20 per run),
so it cannot rise; it stayed 200. The quarantiner's statement is the P1 rewrite, and it ran 200 times with 0 errors.

## L7 / P10: graph vs SQL strengths and weaknesses by scale (pre-registered)

Pre-registration, design and (later) results: [`docs/research/P10_GRAPH_VS_SQL.md`](research/P10_GRAPH_VS_SQL.md).
Four deterministic families (no LLM call): **G** multi-tenancy at 1-2,000 tenants, **H** query expressiveness and
traversal (motifs, multi-relationship traversal, constrained shortest path), **I** atomic multi-entity writes under
crashes and conflicting writers, **J** concurrent session populations of 2-1,000 replaying the recorded tool-call mix.
Arms: FalkorDB (graph per tenant), SQLite file per tenant, SQLite shared file with `tenant_id`.

**L7 results in one paragraph** (details, tables and the verdict in the P10 doc; result files
`plexus/demo_data/crucible/l7/`). Correctness gates held: 0 cross-tenant leaks on the product path at 1-2,000
tenants in every arm. **I:** a SQLite transaction left 0 partial close-outs in 200 kills; the Plexus product path
(four tool calls) left 86; `MULTI`/`EXEC` survives a client kill but has no rollback; one Cypher statement matched the
SQL transaction everywhere with 1 round trip instead of 13; FalkorDB 6.0.2's AOF replay crashed on restart in 10 of
11 attempts on preserved data. **H:** Cypher was about half as long on pattern questions, but SQL expressed every
question in one statement and was faster on 9 of 11 cells (25-900x on traversals; Cypher timed out on unbounded
closures, SQL did not); the natural Cypher for one motif got a silently wrong answer from the FalkorDB planner.
**G:** FalkorDB latency is flat from 1 to 2,000 tenants (SQLite degrades 14-40x but stays faster); FalkorDB tenants
cost 9x more to create and 4-15x more memory than SQLite files take disk, and 2,000 of them fit this machine only
with persistence forks off. **J:** embedded SQLite had 6-17x the throughput with 0 errors at every population;
FalkorDB had the fairer tail under one hot tenant and rejected ~90% of calls at 1,000 sessions over 200 tenants.

## L8 plan (P11): long-horizon memory under live change, scored on outcomes (pre-registration, not yet approved)

Written on branch `p11` (base `main` f96df06) before any L8 code or `claude -p` call. L7 is the in-flight P10 layer (graph vs SQL by scale), so this is L8. It operationalises report §10 item 2: ≥ 5 seeded runs per arm, a 20-sprint history that exceeds the agent's context, the L5a eight-kind code edits landed *live* during a 3-agent run, and the MAST failure modes as deterministic transcript signatures. Headline metrics: stale-act rate and step repetition per agent action, tokens per *correct* action (fixing the §6.7 n=1, tokens-per-run critique). Arms: P, B0, B0′ (native Claude Code memory files, no tool API), B1, B3 (Postgres behind the same tool API incl. staleness tools); Hermes native memory is computed to be structurally impossible (2,200-char cap vs a 332k–532k-char history) and not run. Every prediction, including the expected ties among the tool arms on the MAST rates and between P and B3 on stale-act rate, the budget (≈ $37, 2.5× the project's spend to date) and the pre-registered cut rule are in **`docs/research/L8_LONG_HORIZON_OUTCOMES.md`**. No run happens until that plan is approved; results will be appended here and there.

## L8 round A results (P11): P, B1, B0′ × 5 seeds, $21.87

Round A only (owner-approved; B0 and B3 not run, so the design-vs-graph question stays open). Full results, metrics table, amendments 1–4 and what could not be executed: **`docs/research/L8_LONG_HORIZON_OUTCOMES.md` § Round A results**; files `plexus/demo_data/crucible/l8/` (`latest-roundA.json`, `20261016T155630Z-roundA/report.md`). Headline, by the pre-stated rule: **Plexus did not reduce stale actions versus SQLite (4.5% vs 5.7%, n = 5 seeds each, p = 0.56) and used 2.51× the tokens per correct action (2.01× billing-weighted)** — a tie on stale actions and a loss on cost. Versus Claude Code with memory files (B0′, 2.4%): a tie (p = 0.40), B0′ numerically lower. Step repetition, missing completion and mismatch: not changed by the backend (all ≈ 0). Losses and ties published as such: P finished 14/16 tasks in 4 of 5 seeds (its `recall` on the `hash` embedder missed an S07 history fact and the agent failed the task; B0′ found all history facts by grep, 15/15), noticed code changes later than B1, and its agents made 0 `anchor_fact` calls, so the staleness feature was never exercised. P and B1 tie on provenance (100% at kill turns too) and on the cold Cypher-vs-SQL probe (7/9 first-try each); P and B1 beat B0′ on write-time contradiction surfacing (5/5 vs 0/5) and audit Q1 (5/5 vs 0/5).

## L6 on integ (P9-f ported onto P9-int + the Cypher audit): $0 deterministic re-run, pre-registered before the run

Branch `integ` = `trials-int` + p10 + p11 + the ported parts of `p9f-b` (`docs/research/INTEG_MERGE.md`). The p9f-b section of this file
(below, "L6 post-fix (P9-f)") measured p9f-b's own build; this re-run measures the merged one. Commands (port 6374, no LLM call):
`python -m plexus.crucible.l6.run postfix --arms P-product-tool,P-product-service,P-product-tool-p9f --kills 200` (A arms + F for arm P) and
`python -m plexus.crucible.l6.run det --families B`. Result files: `plexus/demo_data/crucible/l6-integ/`.

**Expected, written before the run:** (1) A `P-product-tool-p9f` (200-id page, `order='valid_from'`, `probe_ids`) **24/24 strict**, probes
24/24, 0 timeouts; `P-product-service` 24/24; `P-product-tool` (2,000-id cap, no probes) unchanged from the audit re-run. (2) B
`P-product-tool-p9f` (`why(depth=12)`, 200 elements) **20/24**, `P-product-service` (5,000 elements) **24/24**, both 0 errors. (3) F arm P:
**0 orphans, 0 lost acknowledged writes, `missing_derived_from` 0** (the audit re-run on `trials-int` had 0 orphans and 13 missing
DERIVED_FROM, because the benchmark arm linked origins in a second statement). **A result off these is reported as such.**

## L6 on integ: results (run after the pre-registration above; 0 LLM calls)

Files: `plexus/demo_data/crucible/l6-integ/20261017T211111Z-postfix` (A arms + F arm P, 200 kills) and `20261017T212449Z-det` (family B). Same machine
and DB image as the earlier L6 runs; port 6374.

| Registered expectation | Result |
|---|---|
| A `P-product-tool-p9f` 24/24 strict, probes 24/24, 0 timeouts | **24/24 strict**, probes 24/24, 0 timeouts, p50 10.4 / p99 689 ms |
| A `P-product-service` 24/24 | **24/24**, p50 27.6 / p99 735 ms |
| A `P-product-tool` unchanged from the audit re-run | **18/24** (the 2,000-id list cap: probes 18/24), 0 timeouts, p50 34.5 / p99 1,108 ms |
| B `P-product-tool-p9f` 20/24; `P-product-service` 24/24 | **20/24** (depth 12 cut at 200 elements: 0/4), **24/24**; `P-product-tool` (default depth 6) 16/24 as published; 0 timeouts |
| F arm P: 0 orphans, 0 lost, `missing_derived_from` 0 | **0 orphans of 1,269 records** (715 facts, 292 decisions, 262 handoffs), **0 lost** of 1,205 acknowledged writes, **`missing_derived_from` 0** (audit re-run on `trials-int`: 13); rule-of-three upper bound 0.24% |

All expectations held. The `missing_derived_from` change is the one real product difference against `trials-int`: the benchmark arm now
passes the origins to `assert_fact` (one statement) instead of linking them in a second one. The Step/WROTE part of defect 6 was already
folded on `trials-int` (0 orphans there too: this run confirms it with the ported tree). `P-product-service` now answers B with one statement
(`statements_per_answer_median` 1; it was up to 14 before the one-statement `why`).

### Measurements of the p9f-b branch itself (carried over from `p9f-b`, ee6a4ea)

The section below is p9f-b's own, unchanged, and describes **p9f-b's build** (result files `plexus/demo_data/crucible/l6-p9f/`). On `integ`
three things differ: defect 6 is the P9-int / P12 design plus `assert_fact(derived_from=...)` (D-014; the test names `test_p9f_atomic_provenance`
and `StepIntent` below do not exist here: see `tests/integration/test_p9f_derived_from.py`), the MCP `impact` list cap is 2,000 (P9-int; p9f-b used
200) and the decision it calls D-013 is D-014 here. The integ numbers are in the section above.

## L6 post-fix (P9-f, branch `p9f-b`, 2026-10-16)

The six product defects that L6 found, fixed one commit each with a test that fails on the old code and passes on the new one. Re-run on the same machine and DB image with `python -m plexus.crucible.l6.run det --families A,dag,B`, `conc` and `crash --kills 200` (result files: `plexus/demo_data/crucible/l6-p9f/` `20261016T081226Z-det`, `20261016T081747Z-conc`, `20261016T082545Z-crash`; the original files are untouched). The frozen L6 arms are unchanged. Two **post-hoc** product arms were added after the run and are labelled `-p9f`: A `P-product-tool-p9f` (the fixed tool's `order='valid_from'` and `probe_ids`, 200-id page) and B `P-product-tool-p9f` (`why(depth=12)`, tool-default `max_elements` 200). They were not pre-registered. Absolute latencies vary between runs (B1h's 5,000-fact median went from 192 to 110 ms between the two runs), so compare arms within a run.

| # | Defect (L6 finding) | Before | After | Test |
|---|---|---|---|---|
| 1 | `impact` returned no timestamps: "5 earliest affected facts" unanswerable | A P-product-tool / -service: strict **0/24** by construction | every listed fact carries `status`, `valid_from`, `created_at`; `order='valid_from'\|'created_at'`. A `P-product-tool-p9f`: **24/24 strict** | `tests/lineage/test_p9f_impact_detail.py` |
| 2 | MCP `impact` cut its id lists at 200 with no signal; probes beyond them read as "not affected" | probes right on **12/24** (tool) | every list carries `ids_truncated`; `offset` / `next_offset` paging; `probe_ids` answered against the whole blast (`facts.probes`). A `P-product-tool-p9f`: probes **24/24** | `tests/mcp/test_impact_tool.py::test_impact_never_hides_a_cut_list`, `test_p9f_impact_detail.py` |
| 3 | `impact` on a 5,000-fact blast exceeded the 10 s `TIMEOUT_MAX` (three joins grouped by the whole fact list) | 6/24 questions timed out; 5,000-fact median **5,012 ms** (socket timeout) | one-pass joins keyed by the source only: 5,000-fact median **446-459 ms**, 0 timeouts, p99 603 ms (B1h 110 ms, P-tuned 325 ms in the same run). The same defect in `quarantine` / `forget_source` was fixed too | `tests/lineage/test_p9f_impact_scale.py` (5,000 facts, < 5 s), `test_p9f_cascade_scale.py` |
| 4 | MCP `why` hard-coded depth 6 and 200 elements | B P-product-tool **16/24** (depths 8, 12: 0/8) | `depth` (1..12, default 6) and `max_elements` (2..5000, default 200) on the tool, defaults unchanged. B `P-product-tool-p9f` (depth 12, 200 elements): **20/24**; with `max_elements` 5000 (P-product-service): **24/24** | `tests/mcp/test_p9f_why_tool.py` |
| 5 | `why` and `blocked_by_failure` ran one statement per hop (L6-E P-levelwise: 917 V1 / 1,091 V3 tears in 4,470 reads) | product `why` torn in **79/79** racing reads (writer adds a decision + its 2-level ancestry in one statement); `blocked_by_failure` torn in **288/288** | both are one read statement (`lineage/why_edges` with unrolled DISTINCT levels, `relay/dependents_closure`): **0** torn reads. B P-product-service p50 **869 → 18 ms** (the old why issued up to 14 statements); `blocked_by_failure` on a 5,000-task 50-level DAG 0.19 → 0.12 s | `tests/lineage/test_p9f_snapshot_reads.py`, `tests/relay/test_p9f_blocked_snapshot.py` |
| 6 | fact / decision / handoff and their Step/WROTE were separate statements | F arm P: **94 / 1,240 = 7.6%** orphans, 9 missing DERIVED_FROM, 1,112 acknowledged writes | Step + BY/NEXT + WROTE/READ (and `assert_fact`'s DERIVED_FROM) in the memory write statement (D-013). F arm P: **0 / 2,723** orphans, 0 missing DERIVED_FROM, 0 lost; rule-of-three upper bound **0.11%**; 2,653 acknowledged writes (2.4x, fewer statements per write) | `tests/crucible/l6/test_p9f_crash_atomic.py` (25 kills: 15 orphans + 2 missing DERIVED_FROM in 271 records before, 0 after), `tests/integration/test_p9f_atomic_provenance.py` |

Other numbers from the re-run, for the record: A-dag `P-product(blocked_by_failure)` 5/5 (10-14 ms; B1h 0.2-0.5 ms). E reproduces the original (the E arms are hand-written Cypher, not product code): P-1stmt 0 violations in 19,667 reads; P-levelwise 1,313 V1 / 18 V2 / 1,546 V3 in 6,429 reads; B1h-1stmt and B1h-txn 0. F: B1h 0 orphans in 64,683 records; B0 6 in 2,213.

**Not fixed, or still worse than SQLite:**

* **SQLite is still faster on every deterministic family.** A at 5,000 facts: B1h 110 ms vs product `impact` ~450 ms. B: B1h p50 0.06 ms vs product `why` 18 ms. A-dag: 0.2-0.5 ms vs 10-14 ms. F write throughput: B1h acknowledged 64,587 writes against Plexus's 2,653 in the same 200 kills. The fixes made the product correct and usable at these sizes, not faster than SQL.
* **`why` through the tool at depth 12 still needs a larger `max_elements`.** With the default 200 the four depth-12 chains are cut (20/24). `max_elements` keeps the nearest levels first, so the deepest origin is the part that drops. The tool now takes up to 5000 elements and answers 24/24 with them. The default was left at 200 on purpose (a larger default means bigger answers for every caller).
* **`quarantine` of a 5,000-fact blast in one statement still exceeds 10 s.** The join defect is fixed (1,000 facts: ~2 s, was > 5 s), but bulk `SET` on a label with a UNIQUE constraint grows ~N^2.6 on FalkorDB 6.0.2 (bare graph: 500 nodes 0.11 s, 1,000 0.60 s, 2,000 3.98 s; range and vector indexes do not cause it). Fixing it means batching the SET over several statements, which gives up the one-statement atomicity that E relies on (V2). Not done; needs a decision.
* **Defect 6 covers the memory writes, not every write tool.** `create_tasks`, `remember_episode`, `assert_relation`, staleness and dedup tools still open their Step and link it in a second statement, so a kill can still orphan those records. L6-F measures facts, decisions and handoffs only.
* **The E harness does not run product code.** The product-level evidence for defect 5 is the two race tests above, not the E table, and they run one writer against one reader shape each.
## Recall-check pre-registration (trials-int review items 1-3: lexical fusion vs the D-013 cues, published numbers on the merged build, `fan_e` on a hub); written before any run

Branch `recall-check` from `trials-int` (`76da7d7`: p12 merged into main's D-013 + audit fixes). Spec: `docs/research/TRIALS_INT_MERGE.md` §6. LLM calls: 0.
FalkorDB 6.0.2 on `plexus-db-75`. **Build under test:** the commit that adds this section plus one harness-only change made
before the first run (L5b / hub harness: the lexical weight the harness pins is read from `PLEXUS_L5_LEXICAL_WEIGHT`, default `0`
= the pin of `af8f70d`; the product code is untouched). The two settings under test are the product's own switch,
`PLEXUS_RECALL_LEXICAL_WEIGHT`: **ON** = the shipped default `0.5` (p12's `fuse_scores`), **OFF** = `0` (main's relevance `1 - rank`
exactly). The candidate pool (60-150 instead of 2k), p12's keyword channel and scope `all` have no switch and are in both settings:
OFF on this build is "main's relevance on p12's pool", so a published number that OFF fails to reproduce is moved by the pool,
not by the fusion, and that is how it will be attributed.

### What each layer reads, and what is not run twice
* **L5b** (`python -m plexus.crucible.l5 --only forgetting --modes off,sep-entity,sep,sep+mult`, N = 5, N = 15, N = 5 `--burst`, seed 20261016,
  fastembed, K = 20, 140 probes) and the **hub world** (`--only hub`, 200 probes): ON and OFF, one fresh play each (new ids; the
  noise-share band between plays is 19.1-22.1% for `sep+mult`, 2-4 points for the other modes). Published reference: the `afx-*`
  re-run (the last one): `sep+mult` 85.7% / 100% / noise 22.1, 19.9, 21.0% / critical loss 0 / same-entity 20, other-entity 0; `off` 75.0-77.1% /
  98.6% (97.9-98.6%) / 23-33%; hub `sep` 100%, `off` 97.5%.
* **No-LLM recall bench** (`recall_bench --label recallcheck-on|off`, `PLEXUS_TOOLSET=core`, hash embedder, the 5 seeds, as
  `l8_trialsint/recall_bench-trialsint-core.json`): published (trials-int, ON): S07 5/5, S13 5/5, S20 1/1, canonical 1000/1000,
  replay 28/36 (p12: 29/36), mean response 5,340 / 5,776 chars.
* **L6-C** (`run_c --scale 1.0`, hash embedder, seed 20261016, all five arms, ON and OFF): the only L6 family that calls
  `Engram.recall` (grep: `arms_c.py` is the only user in `crucible/l6`). P-product / P-flat are "as shipped" on `trials-int`, so
  they run with the fusion on until this run says otherwise. B1h, B1h-untuned and P-tuned do not touch recall: they are the control and are
  expected to reproduce the published rows exactly (75/75 each) in both settings.
* **L6 A, B, D, E, F** (`l6 det`, `l6 postfix`, `l6 conc`) never call `recall` and do not read the lexical weight, so ON/OFF is not
  a variable there; they are run **once** because the merge changed the write path they use (p12's `WROTE` folded into the task
  statements, main's P3 empty-list forms). Expected: unchanged published correctness counts (A `impact` 24/24 strict service,
  18/24 tool; F 0 orphans; E `P-1stmt` 0 violations and the three tearing arms tearing; B, D as in `latest-det.json`). Latencies are
  reported, not a hypothesis.

### Expectations (stated before the run)
1. **OFF reproduces every published L5b number** (it is main's relevance on p12's pool, and the pool only widens a candidate list that
   the entity/predicate unions already filled): `sep+mult` recall@1 within 2 probes of 85.7% (>= 84.3%), recall@5 >= 99.3% (139/140),
   critical loss 0, other-entity rows above the target 0, noise share <= 24.0% (published band + 2 points), in all three runs;
   hub `sep` >= 99%. Confidence: high for critical loss and other-entity, medium for noise share (the keyword channel now also
   pulls entity-name matches into the pool).
2. **ON also reproduces recall@1, recall@5 and critical loss, but not the noise share.** The scenario's noise facts sit on the
   probed subject and their values mention the predicate word, so their lexical coverage of the query is as high as the target's: I expect the
   `sep+mult` noise share to be >= OFF + 2 points. Recall@1 cannot exceed 85.7% for a scorer that does not read the value, but
   the lexical score does read the value, so a move of up to +-2 probes either way is not excluded. I do not expect a gain.
   ON in mode `off` (no scoring: fused order only) may differ from OFF in `off` by several points; that row is descriptive.
3. **L8 bench: ON = the published 28/36 replay, 1000/1000 canonical, needed facts 5/5 5/5 1/1.** OFF: I expect it to keep the
   canonical and needed-fact counts (the p12 completeness came from the pool, keyword channel and scope `all`) and to lose
   some replay calls (>= 3 of the 36 fewer than ON, since the fusion was added by p12 for the 'billing cycle decided in sprint S07'
   query among twenty near-identical facts). Medium confidence; this is the layer where a difference between the settings is most likely.
4. **L6-C:** strict stays 0/75 in P-product and P-flat in both settings (hop facts are ranked behind every direct hit and direct hits are
   never the multi-hop answer; this is structural, not lexical). `hit_any` (published, hash: P-product 11 / 6 / 1 at d = 1 / 2 / 3, P-flat 0 / 0 / 1)
   will move because of the new pool and the keyword channel; I predict it moves up or stays (a wider pool returns more rows), by
   <= 5 questions per depth, and the same in both settings within 3 questions. Low confidence; reported and explained, not a decision input
   unless the two settings differ by >= 3 questions at one depth.
5. **`fan_e` on a hub (review item 3).** In `engram/recall` the `fan_e` comprehension `size([(e)<-[:ABOUT]-(:Fact {status:'active'}) | 1])` and the
   sibling `OPTIONAL MATCH (e)<-[:ABOUT]-(g0:Fact)` that follows it both run once per surviving row (up to `$lim` <= 150 + keyword hits), and every
   row of one hub entity repeats the same scan of the hub's `ABOUT` edges. I expect the records produced by those two operators to scale as
   `rows_from_the_hub x fan`: on a hub with 1,000 current facts and a recall returning >= 60 hub rows, >= 60,000 records in the `ABOUT` traversal
   (fan_e) and the same order in the sibling expansion; at 5,000 current facts >= 300,000 (>= 150 rows would make it 750,000). That is "scans
   beyond the bounded rows". Fix (if the numbers confirm): the per-entity work (fan, sibling list) is done **once per distinct entity** in the same
   single read (group the rows by entity before the comprehension), so the records scale with `fan x distinct entities`, independent of how many rows
   one entity contributes; acceptance: the `ABOUT`-side records <= 3 x fan per distinct entity at both hub sizes, the rows and ranks identical to the old query on a
   fixture where every rule fires (hub plus siblings in several scopes, a diamond scope graph, an `$all` read), and one statement. If the numbers do
   not confirm (the planner already shares the scan), the finding is "not a defect" and a plan-shape test pins the record count.
   Timings (median `run_time_ms`) are reported next to the records and are not a criterion (Docker Desktop, 2x swings).

### Decision rule for the double-counting question (stated now)
A setting is **admissible** when, on the merged build, it satisfies all of: (L5b) `sep+mult` recall@1 >= 84.3%, recall@5 >= 99.3%, critical loss 0,
other-entity rows 0 and noise share <= 24.0% in all three runs, and hub `sep` recall@1 >= 99%; (L8) needed facts 5/5, 5/5, 1/1, canonical 1000/1000
and replay >= 28/36. L6-C and L6 A/B/D/E/F are reported but are not admissibility criteria (see 4: not lexical, and both settings share the pool).
* both settings admissible: the shipped default becomes **OFF (`0`)**: the fusion is then an extra mechanism that no registered benchmark
  needs, it overlaps the D-013 cues (a query word in the entity name or predicate is rewarded by both), and `0` is main's relevance, which carries the
  published L5b numbers. The fusion stays available (`PLEXUS_RECALL_LEXICAL_WEIGHT`). Exception: if ON's replay count exceeds OFF's by >= 3
  calls (the one measure on which the fusion was designed to help), the tie is not a tie and the default stays ON;
* only ON admissible: the default stays **ON (`0.5`)**; D-013 records that the two mechanisms overlap, that the L5b / hub harness pins the
  fusion off for the SQL-arm comparison, and which published numbers were measured with it off;
* only OFF admissible: the default becomes OFF;
* neither admissible: no default is argued from a tie; the criteria each setting fails are reported as moved published numbers with the cause
  (the pool, the fusion, or both, by the OFF/ON difference), and the default is the setting that fails fewer criteria (a tie keeps ON,
  the merged status quo). A third weight (e.g. 0.1 or 0.25) is only tried then, and is labelled **post-hoc**.
Whatever is chosen, the L5b / hub harness keeps its default pin `PLEXUS_L5_LEXICAL_WEIGHT=0` (the SQL arm mirrors the cosine relevance), and every
number reported for it names the weight used.

### Recall-check addendum 1 (written after the registered L5b / hub / L8 runs, before any post-hoc run): POST-HOC attribution of the moved noise share

What the registered L5b runs showed (numbers in the results section): on the merged build **both** settings leave the published L5b noise share
(`sep+mult` 19.9-22.1%) far behind (OFF 32.3 / 41.6 / 33.3%, ON 42.7 / 60.1 / 41.6%), while recall@1, recall@5 and other-entity rows reproduce; the same code
path at main's tip (`1ddeb13`, control run today through the same harness, FalkorDB 6.0.2 on slot 75) reproduces the published numbers (22.1 / 20.0 / 21.6%),
so the move is the merge, not the machine or the day. A second observation: on main `sep+mult` removes 6-9 points of noise share from `sep` (27.4 -> 22.1,
28.6 -> 20.0); on the merged build it removes none (OFF 31.7 -> 32.3, 36.9 -> 41.6). The activation multiplier is what pushes decayed noise below real facts, so it is not
reaching the noise rows any more.

**Hypothesis (post-hoc: formed after seeing the numbers).** p12's keyword channel searches `Fact.value` **and** `Fact.search_text` (entity name + predicate words) and
returns up to `pool` (60) hits instead of main's `k` value hits; a keyword hit whose text contains every query word is exempt from the use-history term (the exact-keyword
bypass, `PLEXUS_KW_BYPASS=fact` tests entity + predicate + value). In L5b every noise fact sits on the probed subject, so with the entity name and predicate in the tested text a noise
fact now qualifies for the bypass and is shielded from the multiplier. The pool size (60 against 2k) is the competing explanation.

**Post-hoc runs (merged build, labelled post-hoc, NOT decision inputs and not part of the admissibility rule):** L5b `--only forgetting --modes off,sep,sep+mult`, N = 5 and N = 15, fastembed, seed 20261016, a wrapper that sets the
module constant or env var, results in `plexus/demo_data/crucible/l5_posthoc/recallcheck/`:
* X1 `PLEXUS_KW_BYPASS=value` (bypass tests the value only, main's earlier rule; keyword channel unchanged), lexical OFF and ON;
* X2 `MAX_KEYWORDS=0` (no keyword channel at all: no row can be bypassed), lexical OFF;
* X3 `MIN_POOL=0, POOL_FACTOR=2` (pool = 2k as on main), lexical OFF.
Predictions, stated now: **X2** restores the multiplier's effect (`sep+mult` noise <= `sep` - 5 points) and brings `sep+mult` noise to <= 26% at N = 5; **X1** moves the same way but less
(>= 4 points lower than the registered OFF run, possibly still above 24%); **X3** changes the noise share by <= 3 points (the pool is not the cause); with X1 the ON setting stays
>= 5 points above OFF (the lexical term has its own noise cost, because noise values contain the query words). If X1 and X2 both fail their prediction, the hypothesis is falsified and the cause stays unknown
(reported as such). L8: X1 with lexical OFF is also run through `recall_bench` (`PLEXUS_KW_BYPASS=value`) to see whether narrowing the bypass costs the long-horizon facts; expected
1000/1000, needed facts 5/5 5/5 1/1, replay 27-28/36. Whatever X1 shows, the shipped bypass default is not changed by this check: that would be a ranking change that needs its own pre-registered confirmatory run.

### Recall-check addendum 2 (written after post-hoc X1-X3, before X4/X5; also post-hoc)

What X1-X3 showed (numbers in the results section): **X1 (`PLEXUS_KW_BYPASS=value`) did not move the noise share** (OFF `sep+mult` 31.6% / 41.1% against the registered 32.3% / 41.6%), so my first
hypothesis (the breadth of the bypass *text*) is **falsified**. **X2 (no keyword channel)** does remove the noise (`sep+mult` 16.7% / 17.7%, below the published 20-22%) but breaks the ranking it
was meant to leave alone (recall@1 72.9% / 68.6%, 29 / 27 other-entity rows above the target): with no keyword hit nothing is bypassed, and the multiplier demotes the cold target facts, the
D-012 loss that the bypass was added to prevent. So the keyword channel is both what shields the targets and (apparently) what shields the noise. **X3 (pool = 2k)** at N = 5 left the noise
share at 30.3% (the pool is not the cause; N = 15 pending when this is written).

**New hypothesis (post-hoc).** Main's keyword channel matched `Fact.value` only. P12 added `Fact.search_text` (entity name + predicate words) to the full-text index and `engram/recall_keywords`
searches both: for a probe `"<subject> <predicate>"` every fact of the subject (the 5 real and the N noise facts) is now a keyword hit through its entity name, and a keyword hit whose text
contains every query word is exempt from the multiplier. On main only the facts whose value mentions a query word were hits.

**Runs.** X4 = lexical OFF, keyword ids restricted to the facts whose `value` contains a query word (main's semantics; a wrapper filters `Engram._keyword_ids`, product code untouched), pool as
merged; X5 = X4 with pool = 2k (`MIN_POOL=0, POOL_FACTOR=2`), i.e. the closest the merged build can be put to main's candidate rules. L5b `--modes off,sep,sep+mult`, N = 5 and N = 15.
**Predictions, stated now:** X4 brings `sep+mult` noise to <= 26% at N = 5 and <= 24% at N = 15 with recall@1 >= 84.3% and 0 other-entity rows (falsified otherwise); X5 is within 2 points of X4.
If X4 fails, the cause of the move stays unattributed in this report (stated as such), and the remaining differences between the two builds (the Python sibling boost, the fused sort, the named-entity merge
order) are listed as not tested. Nothing here changes a shipped default.

### Recall-check addendum 3 (post-hoc, written before the run): bisect by commit, `off` mode on p12's tip

X3 (pool = 2k) and X4 (value-only keyword ids) did not move the noise share either at N = 5 (30.3% and 30.9% against 32.3%), so none of the single switches I can set on the merged build
explains it. The remaining way to attribute the move is by commit: the same harness, `--modes off` (retrieval only: no cue, no multiplier, so no D-012 / D-013 code is on the path) at N = 5 and N = 15, on three trees: main's tip
`1ddeb13` (control, already run: `off` 24.4% / 28.9% / 27.0% burst), the merged build (`ae17aee`, run: 28.3% / 41.6% / 30.9%) and **p12's tip `3521a0c`** (new, `.venv-ctl2`, no D-013 on it). **Prediction:** p12's `off` noise
share is at the merged build's level (>= 27% at N = 5 and >= 38% at N = 15), i.e. the move comes from p12's retrieval changes (keyword channel over `search_text`, bigger pool, fused sort) and not from the interplay with D-013; if it
is at main's level (<= 30% at N = 15), the interplay with D-013 (named-entity union, separation, bypass) is the cause. Post-hoc; no shipped default depends on it.

## Recall-check results (run after the pre-registration and addenda above; 0 LLM calls)

**Summary.** (1) *Default:* neither lexical setting reproduces every published number; by the pre-stated rule (fewer failed criteria) the shipped default is now lexical fusion **off** (`PLEXUS_RECALL_LEXICAL_WEIGHT=0`; OFF fails 2 of 9 criteria, ON 3). (2) *Moved published numbers, not hidden:* the L5b `sep+mult` noise share on the merged build is 32.3 / 41.6 / 33.3% (published 20-22%, main's tip re-measured today 22.1 / 20.0 / 21.6%) in either setting, with the fusion on 42.7 / 60.1 / 41.6% and one critical probe lost at N = 15;
the fusion explains +8 to +19 points of it, the rest is **not attributed** (five single-switch tests failed to reproduce it). L6-C product-arm `hit_any` moved from 11 / 6 / 1 to 23 / 9 / 0 on main's own tip (before the merge). Recall@1 / recall@5 / critical loss / hub / L8 needed facts and canonical / L6 A, B, D, E, F reproduce. (3) *`fan_e` on a hub:* unbounded per row
(61,295 records at a 1,000-fact hub, 305,295 at 5,000; 289 / 1,478 ms), fixed in one statement (1,060 / 5,060 records; 19.6 / 34.2 ms), rows unchanged, plan-shape test added. Expectations falsified are listed per section.

Code: pre-registered runs on `ae17aee` (trials-int `76da7d7` + the harness switch); the fix commits (`fan_e` once per entity, lexical default 0) came after all registered runs and were
checked by the L8 bench and the tests below. FalkorDB 6.0.2 on `plexus-db-75`, fastembed for L5b / hub, hash embedder for L8 and L6-C, seed 20261016 (L5b), one play per cell (new ids each play).
Result directories (originals untouched; the L6 `latest-*.json` envelopes were restored after the runs): `plexus/demo_data/crucible/l5/*recallcheck-{off,on}-{n5,n15,n5-burst,hub}`, `…recallcheck-ctl-main-*`
(main's tip `1ddeb13`, same harness, today), `…recallcheck-ctl-p12-*` (p12's tip `3521a0c`), `l5_posthoc/recallcheck/` (X1-X5, scripts, PROFILE output), `l8_recallcheck/`, `l6/*-c-recallcheck-{off,on}`.

### 1. L5b and the hub world: both settings, next to the control and the published numbers

`sep+mult` is the shipped default mode; published = the `afx-*` re-run (85.7% / 100% / noise 22.1, 19.9, 21.0% / critical loss 0 / 20 / 0). The control is the published code run again today through the same harness: it reproduces the published numbers
(`sep+mult` 22.1 / 20.0 / 21.6% noise), so differences below are the merge, not the machine.

| Run | Build / setting | Mode | recall@1 | recall@5 | critical loss | noise share | above target: same / other |
|---|---|---|---|---|---|---|---|
| N = 5 | main tip `1ddeb13` (control, today) | `off` | 75.7% | 98.6% | n/a | 24.4% | 36 / 13 |
| N = 5 | main tip `1ddeb13` (control, today) | `sep-entity` | 85.7% | 100.0% | 0 | 28.9% | 20 / 0 |
| N = 5 | main tip `1ddeb13` (control, today) | `sep` | 85.7% | 100.0% | 0 | 27.4% | 20 / 0 |
| N = 5 | main tip `1ddeb13` (control, today) | `sep+mult` | 85.7% | 100.0% | 0 | 22.1% | 20 / 0 |
| N = 5 | trials-int + recall-check, lexical OFF (0) | `off` | 79.3% | 99.3% | n/a | 28.3% | 31 / 8 |
| N = 5 | trials-int + recall-check, lexical OFF (0) | `sep-entity` | 84.3% | 100.0% | 0 | 33.4% | 22 / 0 |
| N = 5 | trials-int + recall-check, lexical OFF (0) | `sep` | 85.7% | 100.0% | 0 | 31.7% | 20 / 0 |
| N = 5 | trials-int + recall-check, lexical OFF (0) | `sep+mult` | 85.7% | 100.0% | 0 | 32.3% | 21 / 0 |
| N = 5 | trials-int + recall-check, lexical ON (0.5) | `off` | 85.0% | 100.0% | n/a | 41.7% | 21 / 0 |
| N = 5 | trials-int + recall-check, lexical ON (0.5) | `sep-entity` | 85.7% | 100.0% | 0 | 43.9% | 20 / 0 |
| N = 5 | trials-int + recall-check, lexical ON (0.5) | `sep` | 85.7% | 100.0% | 0 | 43.9% | 20 / 0 |
| N = 5 | trials-int + recall-check, lexical ON (0.5) | `sep+mult` | 85.7% | 100.0% | 0 | 42.7% | 34 / 0 |
| N = 15 | main tip `1ddeb13` (control, today) | `off` | 77.1% | 98.6% | n/a | 28.9% | 35 / 12 |
| N = 15 | main tip `1ddeb13` (control, today) | `sep-entity` | 85.7% | 100.0% | 0 | 29.1% | 20 / 0 |
| N = 15 | main tip `1ddeb13` (control, today) | `sep` | 85.7% | 100.0% | 0 | 28.6% | 20 / 0 |
| N = 15 | main tip `1ddeb13` (control, today) | `sep+mult` | 85.7% | 100.0% | 0 | 20.0% | 20 / 0 |
| N = 15 | trials-int + recall-check, lexical OFF (0) | `off` | 78.6% | 99.3% | n/a | 41.6% | 33 / 7 |
| N = 15 | trials-int + recall-check, lexical OFF (0) | `sep-entity` | 84.3% | 100.0% | 0 | 39.6% | 22 / 0 |
| N = 15 | trials-int + recall-check, lexical OFF (0) | `sep` | 85.7% | 100.0% | 0 | 36.9% | 20 / 0 |
| N = 15 | trials-int + recall-check, lexical OFF (0) | `sep+mult` | 85.0% | 100.0% | 0 | 41.6% | 23 / 0 |
| N = 15 | trials-int + recall-check, lexical ON (0.5) | `off` | 85.0% | 100.0% | n/a | 56.6% | 25 / 0 |
| N = 15 | trials-int + recall-check, lexical ON (0.5) | `sep-entity` | 85.0% | 100.0% | 0 | 61.3% | 25 / 0 |
| N = 15 | trials-int + recall-check, lexical ON (0.5) | `sep` | 85.7% | 100.0% | 0 | 61.3% | 20 / 0 |
| N = 15 | trials-int + recall-check, lexical ON (0.5) | `sep+mult` | 85.7% | 99.3% | 1 | 60.1% | 44 / 0 |
| burst | main tip `1ddeb13` (control, today) | `off` | 75.0% | 98.6% | n/a | 27.0% | 39 / 12 |
| burst | main tip `1ddeb13` (control, today) | `sep-entity` | 85.7% | 100.0% | 0 | 28.4% | 20 / 0 |
| burst | main tip `1ddeb13` (control, today) | `sep` | 85.7% | 100.0% | 0 | 25.6% | 20 / 0 |
| burst | main tip `1ddeb13` (control, today) | `sep+mult` | 85.7% | 100.0% | 0 | 21.6% | 20 / 0 |
| burst | trials-int + recall-check, lexical OFF (0) | `off` | 79.3% | 99.3% | n/a | 30.9% | 33 / 6 |
| burst | trials-int + recall-check, lexical OFF (0) | `sep-entity` | 84.3% | 100.0% | 0 | 34.0% | 22 / 0 |
| burst | trials-int + recall-check, lexical OFF (0) | `sep` | 85.7% | 100.0% | 0 | 32.7% | 20 / 0 |
| burst | trials-int + recall-check, lexical OFF (0) | `sep+mult` | 85.7% | 100.0% | 0 | 33.3% | 23 / 0 |
| burst | trials-int + recall-check, lexical ON (0.5) | `off` | 85.0% | 100.0% | n/a | 40.9% | 21 / 0 |
| burst | trials-int + recall-check, lexical ON (0.5) | `sep-entity` | 85.7% | 100.0% | 0 | 42.4% | 20 / 0 |
| burst | trials-int + recall-check, lexical ON (0.5) | `sep` | 85.7% | 100.0% | 0 | 42.4% | 20 / 0 |
| burst | trials-int + recall-check, lexical ON (0.5) | `sep+mult` | 85.7% | 100.0% | 0 | 41.6% | 30 / 0 |

| Pre-registered criterion (L5b, `sep+mult`, three runs) | OFF | ON |
|---|---|---|
| recall@1 >= 84.3% | **PASS** 85.7 / 85.0 / 85.7 | **PASS** 85.7 / 85.7 / 85.7 |
| recall@5 >= 99.3% (139/140) | **PASS** 100 / 100 / 100 | **PASS** 100 / 99.3 / 100 |
| critical loss 0 | **PASS** 0 / 0 / 0 | **FAIL** 0 / **1** / 0 (N = 15: 1 of 80 critical probes lost; also 44 same-entity rows above the target against 23) |
| other-entity rows above the target 0 | **PASS** | **PASS** |
| noise share <= 24.0% | **FAIL** 32.3 / 41.6 / 33.3% | **FAIL** 42.7 / 60.1 / 41.6% |
| hub `sep` recall@1 >= 99% | **PASS** 100% | **PASS** 100% |

Hub world (200 probes, fastembed; the table of arms is in the section above):

| Arm | main tip (control) | lexical OFF | lexical ON |
|---|---|---|---|
| `off` | 97.5% / 100% (hub fact above target 2.5%) | 96.5% / 100% (hub fact above target 3.5%) | 100.0% / 100% (hub fact above target 0.0%) |
| `sep-entity` | 97.5% / 100% (hub fact above target 2.5%) | 96.5% / 100% (hub fact above target 3.5%) | 100.0% / 100% (hub fact above target 0.0%) |
| `sep-flat` | 97.5% / 100% (hub fact above target 2.5%) | 96.5% / 100% (hub fact above target 3.5%) | 100.0% / 100% (hub fact above target 0.0%) |
| `sep` | 100.0% / 100% (hub fact above target 0.0%) | 100.0% / 100% (hub fact above target 0.0%) | 100.0% / 100% (hub fact above target 0.0%) |

Expectations 1 and 2 against the result. **1 (OFF reproduces every published L5b number): half falsified.** Recall@1 (85.7 / 85.0 / 85.7%), recall@5, critical loss 0, cross-entity displacers 0 and the hub result reproduce;
the noise share does not (+10.2 / +21.6 / +11.7 points over today's control). **2 (ON reproduces recall and critical loss, not the noise share): half falsified.** The noise share is what I expected to differ
(ON - OFF = +10.4 / +18.5 / +8.3 points), recall@1 does not exceed the ceiling, but ON also lost a critical probe at N = 15 and its `sep+mult` puts 44 same-entity rows above the target (OFF 23): I did not diagnose why the fused score does that.
ON in the `off` (no-scoring) mode gains recall@1 (85.0 against 79.3 / 78.6 / 79.3%), which is the fusion's one benefit measured here.

### 2. The no-LLM recall bench (L8, 5 seeds, hash embedder, `PLEXUS_TOOLSET=core`)

| Run | Code | replay calls that found their target | needed fact found per task S07 / S13 / S20 | canonical (1,000 recalls) | mean response chars replay / canonical |
|---|---|---|---|---|---|
| p12 tip, fusion on (published) | `d6d30da` | 29/36 | 5/5 · 5/5 · 1/1 | 1000/1000 | 5,344 / 5,772 |
| trials-int, fusion on (published) | `f5881c6` | 28/36 | 5/5 · 5/5 · 1/1 | 1000/1000 | 5,340 / 5,776 |
| recall-check ON (0.5), clean re-run | `93c1b45` | 27/36 | 5/5 · 5/5 · 1/1 | 1000/1000 | 5,342 / 5,776 |
| recall-check OFF (0) | `ae17aee` | 27/36 | 5/5 · 5/5 · 1/1 | 1000/1000 | 5,331 / 5,766 |
| post-hoc X1 (OFF + `PLEXUS_KW_BYPASS=value`) | `00ccc82` | 27/36 | 5/5 · 5/5 · 1/1 | 1000/1000 | 5,331 / 5,766 |
| **final build, shipped default (0), no env** | `f966146` | **28/36** | 5/5 · 5/5 · 1/1 | 1000/1000 | 5,333 / 5,766 |

A first ON run (28/36) overlapped a temporary edit of `engram/recall.cypher` in this worktree (a draft of the `fan_e` fix, reverted after about a minute), so it is not used; its file was deleted and the re-run above replaces it.
The replay count is **not a stable measure**: OFF (27) and the final build with the same setting (28) differ by one call, and the single call that changes between runs is always `"Bolt Billing API billing cycle"` of seed 20261019,
which names no sprint, so the twenty `billing_cycle` facts tie and new ids decide which fifteen come back. Needed facts and canonical completeness (the numbers p12 reported as acceptance numbers) are identical in every run.
**Expectation 3 falsified in both halves:** ON does not reproduce 28/36 on a clean re-run (27), and OFF does not lose >= 3 replay calls (it loses none against ON). The replay >= 28 criterion therefore fails for both settings in the registered runs.

### 3. The decision, by the rule stated before the runs

Neither setting is admissible. Failed criteria of nine: **OFF 2** (L5b noise share; L8 replay 27 < 28), **ON 3** (critical loss; noise share; L8 replay 27 < 28). Without the replay criterion (it does not separate the settings, see 2) the counts are 1 and 2.
**The default becomes OFF: `PLEXUS_RECALL_LEXICAL_WEIGHT = 0`** (`f966146`); `FUSION_WEIGHT = 0.5` stays as the opt-in. Why this is the rule's outcome and not a taste: the rule picks the setting that fails fewer criteria and the
count is lower for OFF however the replay criterion is counted. The pre-registration was ambiguous in one place that I resolved before looking at the result, not after: expectation 4 made L6-C a decision input
"if the two settings differ by >= 3 questions at one depth", without a direction; they do differ (below), OFF is ahead on the metric (`hit_any`), and using it would not change the outcome. The "tie keeps ON" clause never applied (no tie).
Recorded in `docs/DECISIONS.md` D-013, amendment 3.

### 4. L6-C, the only L6 family that calls `recall` (hash embedder, seed 20261016, 75 questions, 3 repetitions)

An **unregistered control** was added after the first two runs: the same runner on main's tip `1ddeb13` (`T223224Z-c-recallcheck-ctl-main`), because the published row (`T103929Z-c`, 10:39 on 17 Oct) was taken before main's own predicate cue
(12:55) and the section 3.3 union (named entity's facts join the candidates) landed, so it may not describe main's tip either.

| Run | Arm | strict d1 / d2 / d3 | hit@5 | `hit_any` (answer anywhere in the result) | p50 ms d1 / d2 / d3 | statements per answer |
|---|---|---|---|---|---|---|
| published (`T103929Z-c`, main as of 10:39) | P-product | 0 / 0 / 0 | 0 / 0 / 1 | 11 / 6 / 1 | 32.1 / 41.3 / 51.1 | 6.67 |
| | P-flat | 0 / 0 / 0 | 0 / 0 / 1 | 0 / 0 / 1 | 20.7 / 20.3 / 21.0 | 4.0 |
| **control: main's tip `1ddeb13`, today** | P-product | 0 / 0 / 0 | 0 / 0 / 0 | **23 / 9 / 0** | 46.1 / 55.9 / 54.2 | 8.6 |
| | P-flat | 0 / 0 / 0 | 0 / 0 / 0 | 0 / 0 / 0 | 35.4 / 33.9 / 35.3 | 5.93 |
| recall-check OFF (`T212418Z-c-recallcheck-off`) | P-product | 0 / 0 / 0 | 0 / 0 / 0 | **23 / 9 / 0** | 129.0 / 140.8 / 139.4 | 8.67 |
| | P-flat | 0 / 0 / 0 | 0 / 0 / 0 | 0 / 0 / 0 | 103.9 / 104.7 / 100.0 | 6.0 |
| recall-check ON (`T213223Z-c-recallcheck-on`) | P-product | 0 / 0 / 0 | 0 / 0 / 1 | 13 / 3 / 1 | 132.4 / 164.5 / 155.4 | 8.67 |
| | P-flat | 0 / 0 / 0 | 0 / 0 / 1 | 0 / 0 / 1 | 124.7 / 122.8 / 121.4 | 6.0 |
| **final build `f966146`: shipped default (0) + `fan_e` fix** (`T225138Z-c-recallcheck-final-default`) | P-product | 0 / 0 / 0 | 0 / 0 / 0 | **23 / 9 / 0** | 102.2 / 112.9 / 109.3 | 8.67 |
| | P-flat | 0 / 0 / 0 | 0 / 0 / 0 | 0 / 0 / 0 | 89.0 / 88.5 / 89.2 | 6.0 |

The control arms are as published: B1h 75/75 and P-tuned 75/75 in every run. B1h-untuned (no indexes) timed out more often than published (7-9 of 25 at d = 3 against 4; strict at d = 3 16-18 against 21) in all three runs, control included, because the DB was shared with other
recall-check jobs: it is a timing-dependent control, not a hypothesis. **Reading.** (1) **The published `hit_any` (11 / 6 / 1) is stale on main itself**: main's tip today gives 23 / 9 / 0, so that move is main's own post-publication changes, not the merge (strict 0/75 holds in every run,
as registered; this is the only L6-C expectation that held). (2) **The merged build with the fusion off reproduces main's tip exactly** (23 / 9 / 0, P-flat 0): p12's pool and keyword channel change no L6-C answer. (3) The fusion (ON) lowers `hit_any` (13 / 3 / 1): fewer multi-hop answers are in the result at
depth 1-2, one more at depth 3. (4) The product arms' latency is 2.5-3x main's on the merged build (129 against 46 ms at d = 1) with the same number of statements; the DB was shared during those three runs, so I report it and do not claim it. The final build (shipped default plus the `fan_e` fix, DB otherwise idle) gives 102 / 113 / 109 ms, 20% below the pre-fix OFF run and still about 2.2x main's tip: the remaining gap is **not investigated** (the 44k-fact world has 40 hubs of 120 facts; the pool is now 120 rows through the Python fuse / boost / re-rank).
**Expectation 4 falsified except strict 0/75:** `hit_any` neither stayed within 5 of the published numbers nor matched between the settings (they differ by 10 / 6 / 1 questions). Nothing here makes the product arms answer a multi-hop question at rank 1 (the pre-registered defects of §5.4 are unchanged).

### 5. Post-hoc attribution of the noise-share move (addenda 1-3; not decision inputs)

Prediction scoreboard: X1 (bypass over the value only) predicted >= 4 points lower than the registered OFF run: **falsified** (31.6 / 41.1 against 32.3 / 41.6%). X2 (no keyword channel) predicted `sep+mult` noise <= `sep` - 5 points and <= 26% at N = 5: **half
confirmed** (16.7% against `sep` 20.3%, a 3.6-point reduction; <= 26% yes) with an unpredicted cost: recall@1 72.9 / 68.6% and 29 / 27 other-entity rows above the target, because with no keyword hit nothing is bypassed and the multiplier demotes the cold targets, the D-012 loss the bypass was added to prevent.
X3 (pool = 2k) predicted <= 3 points: **confirmed** (30.3 / 40.7%: the pool is not the cause). X1 with the fusion on predicted >= 5 above OFF: **confirmed** (+10.5 at N = 5) and it made N = 15 worse (critical loss 2, recall@1 78.6%, 67 same-entity rows).
X4 (keyword ids restricted to those whose value contains a query word) predicted <= 26% / <= 24% with recall >= 84.3%: **falsified** (30.9 / 44.3%). X5 (X4 + pool 2k) predicted within 2 points of X4: 1.5 at N = 5 (confirmed), 4.0 at N = 15 (not).
The bisect by commit (addendum 3) predicted p12's own tip at or above the merged level: **confirmed** (`off` mode 40.3% at N = 5 and 57.4% at N = 15 with its fusion on, against 24.4 / 28.9% on main's tip), so the move comes from p12's retrieval, not from its interplay with D-013; with the
fusion off, the merged build's `off` mode is still +3.9 / +12.7 points above main's. **What is attributed:** the lexical fusion (ON - OFF, +10.4 / +18.5 / +8.3 points). **What is not:** the remaining +10.2 / +21.6 / +11.7 points (OFF against main's tip, `sep+mult`), which none of X1-X5 reproduces on its own. Untested: the
Python sibling boost (seeds, order), the fused sort and tie order, the `search_text` term in the full-text ranking.

Post-hoc runs (lexical weight and switches as in the first column; `sep` and `sep+mult` only; the registered OFF / ON rows are in the first table):

| Variant | N | Mode | recall@1 | recall@5 | critical loss | noise share | same / other |
|---|---|---|---|---|---|---|---|
| X1 value-only bypass, OFF | 5 | `sep` | 85.7% | 100.0% | 0 | 31.6% | 20 / 0 |
| X1 value-only bypass, OFF | 5 | `sep+mult` | 85.7% | 100.0% | 0 | 31.6% | 23 / 0 |
| X1 value-only bypass, OFF | 15 | `sep` | 85.7% | 100.0% | 0 | 37.4% | 20 / 0 |
| X1 value-only bypass, OFF | 15 | `sep+mult` | 85.7% | 100.0% | 0 | 41.1% | 24 / 0 |
| X1 value-only bypass, ON | 5 | `sep` | 85.7% | 100.0% | 0 | 42.7% | 20 / 0 |
| X1 value-only bypass, ON | 5 | `sep+mult` | 85.7% | 100.0% | 0 | 42.1% | 33 / 0 |
| X1 value-only bypass, ON | 15 | `sep` | 85.7% | 100.0% | 0 | 61.3% | 20 / 0 |
| X1 value-only bypass, ON | 15 | `sep+mult` | 78.6% | 98.6% | 2 | 61.4% | 67 / 0 |
| X2 no keyword channel, OFF | 5 | `sep` | 84.3% | 100.0% | 0 | 20.3% | 20 / 2 |
| X2 no keyword channel, OFF | 5 | `sep+mult` | 72.9% | 100.0% | 0 | 16.7% | 26 / 29 |
| X2 no keyword channel, OFF | 15 | `sep` | 82.9% | 100.0% | 0 | 24.3% | 20 / 4 |
| X2 no keyword channel, OFF | 15 | `sep+mult` | 68.6% | 100.0% | 0 | 17.7% | 27 / 27 |
| X3 pool = 2k, OFF | 5 | `sep` | 85.7% | 100.0% | 0 | 31.0% | 20 / 0 |
| X3 pool = 2k, OFF | 5 | `sep+mult` | 85.0% | 100.0% | 0 | 30.3% | 24 / 0 |
| X3 pool = 2k, OFF | 15 | `sep` | 85.7% | 100.0% | 0 | 39.7% | 20 / 0 |
| X3 pool = 2k, OFF | 15 | `sep+mult` | 85.0% | 100.0% | 0 | 40.7% | 26 / 0 |
| X4 value-only keyword ids, OFF | 5 | `sep` | 85.7% | 100.0% | 0 | 32.0% | 20 / 0 |
| X4 value-only keyword ids, OFF | 5 | `sep+mult` | 85.7% | 100.0% | 0 | 30.9% | 23 / 0 |
| X4 value-only keyword ids, OFF | 15 | `sep` | 85.7% | 100.0% | 0 | 38.6% | 20 / 0 |
| X4 value-only keyword ids, OFF | 15 | `sep+mult` | 84.3% | 100.0% | 0 | 44.3% | 27 / 0 |
| X5 = X4 + pool 2k, OFF | 5 | `sep` | 85.7% | 100.0% | 0 | 31.7% | 20 / 0 |
| X5 = X4 + pool 2k, OFF | 5 | `sep+mult` | 85.7% | 100.0% | 0 | 32.4% | 21 / 0 |
| X5 = X4 + pool 2k, OFF | 15 | `sep` | 85.7% | 100.0% | 0 | 37.1% | 20 / 0 |
| X5 = X4 + pool 2k, OFF | 15 | `sep+mult` | 85.7% | 100.0% | 0 | 40.3% | 23 / 0 |

p12's tip through the same harness (`--modes` default, fusion on, D-012 era; `ctl-p12-*`): `off` recall@1 84.3 / 84.3%, noise 40.3 / 57.4%; `on` (D-012 multiplier) 77.1 / 73.6% with critical loss 0 / 3; `on+sweep` 85.7 / 85.0%, noise 20.3 / 34.4%.

### 6. `fan_e` on a hub entity (GRAPH.PROFILE, throw-away graph; item 3)

Setup: entity `Mega Hub` with 1,000 (5,000) active facts plus 30 superseded and 30 facts in a scope the query does not inherit, 40 small entities of 5 facts, `recall(k = 20)`: the Python layer's own parameters (`lim` = 120 = pool 60 + 60 keyword ids, `over` = 240, `sibs` = 5, `damp` on);
the result holds 120 rows, at least 60 from the hub. Median `run_time_ms` of 5 on a quiet DB (the `before-*` / `after-*` files in `l5_posthoc/recallcheck/profile/` were taken while other jobs ran; `qbefore-*` / `qafter-*` are the quiet ones).

| Hub facts | Query | `fan_e` comprehension records | sibling scan (`ABOUT` + `IN_SCOPE` traverse, Sort) records | max records, any operator | `run_time_ms` |
|---|---|---|---|---|---|
| 1,000 | before (`76da7d7`) | 61,295 | 61,295 / 61,175 | 61,295 | 289 |
| 1,000 | after (`bc34bd2`) | 1,060 | 1,060 | 1,060 | 19.6 |
| 5,000 | before | 305,295 | 305,295 / 305,175 | 305,295 | 1,478 |
| 5,000 | after | 5,060 | 5,060 | 5,060 | 34.2 |

**Expectation 5 confirmed** (">= 60,000 and >= 300,000 records, scaling as rows from the hub x fan"): the plan scanned the hub once per surviving row. The fix is the single read described in D-013 amendment 3 / the query header; acceptance as registered: `ABOUT`-side records <= 3 x fan
(1,060 and 5,060 are exactly the hub's `ABOUT` degree: 1,000 / 5,000 current facts + 30 superseded + 30 in the other scope, i.e. one scan per entity), rows identical (576 parameter sets old vs new, 0 differences; `$all`, damp on/off, diamond scopes, superseded history, `lim` 5-120, `sibs` 1-5), one statement.
Test `tests/integration/test_recall_hub_plan.py`: RED on the old query (303,600 records at 5,000), GREEN now; asserts records < 2 x hub size at both sizes with >= 60 hub rows in the result, and pins damp / siblings / ranks against a Python reference for `$all` on and off.

### 7. L6 A, B, D, E, F: not recall-dependent, run once on the final build (`f966146`)

These families never call `Engram.recall`, so the lexical weight is not a variable; they were run once because the merge changed the write path they use (p12's `WROTE` folded into the task statements, main's empty-list forms). Result
directories `l6/20261017T222943Z-det`, `…T223508Z-postfix`, `…T224327Z-conc`; compared with the committed runs (`latest-det.json` = the first det run, `latest-postfix.json`, `latest-conc.json`).

| Family | Published | Recall-check run | Same? |
|---|---|---|---|
| A `impact` (24 questions, 51,424 facts), postfix arms | B1h 24/24, P-tuned 24/24, P-product-service 24/24, P-product-tool 18/24 (list cap) | 24/24, 24/24, 24/24, 18/24, 0 timeouts | **yes** |
| A (det arms, first det run) | B1h, B1h-untuned, P-tuned, P-anchored 24/24 each; P-naive 10/24 (14 timeouts); P-product-* 0/24 (6 errors each, before the P9 fixes) | 24/24 each; P-naive 24/24 (0 timeouts); P-product-tool 18/24, P-product-service 24/24 | arms with fixes = the published post-fix rows; P-naive is the deliberately path-enumerating query, timing-dependent |
| A_dag (5 questions) | B1h 5, UNION-ALL 3 (2 timeouts), P-naive 4 (1), P-tuned 5, `blocked_by_failure` 5 | identical | **yes** |
| B why-chain depth (24 questions) | B1h 24, P-tuned 24, P-naive 24, P-product-tool 16 (8 errors), P-product-service 24 | identical | **yes** |
| D cross-sprint aggregation (24 questions) | B1h 24, P 24 | 24, 24 | **yes** |
| E consistent reads under concurrent writes (10 runs x 6 s) | `P-1stmt` 0 violations in 10/10 runs; `P-levelwise`, `B1h-levelwise`, `B0-naive` tear in 10/10; `B1h-1stmt`, `B1h-txn`, `B0-locked` 0 | `P-1stmt` 0 / 0 / 0 (reads 18,165, appends 10,755, quarantines 200); `P-levelwise` 1,241 / 30 / 1,478 violations in 10/10; `B1h-levelwise` 329 / 0 / 335 in 10/10; `B0-naive` 113 / 0 / 0 in 10/10 (113 errors); the other three 0 | **yes** (counts are timing-dependent) |
| F provenance crash-consistency (arm P, 200 SIGKILLs) | 0 orphans, 0 lost of 1,776 acknowledged writes, `missing_derived_from` 13 | 0 orphans, 0 lost of 1,975 acknowledged writes, `missing_derived_from` 11 | **yes** (the 11-13 depends on the kill points) |

Expectation: unchanged correctness counts. **Confirmed**; nothing was tuned.

### 8. Gate (branch `recall-check`, final tree)

`ruff check .` and `ruff format --check .` clean; `scripts/verify_readme.py` 313 checks passed, 0 failed; full suite on FalkorDB 6.0.2 (slot 75): **1703 passed, 1 skipped** (trials-int: 1698 passed, 1 skipped; +4 `test_recall_hub_plan.py`, +1 harness switch test). No tool surface changed
(snapshot untouched), one `.cypher` file changed (`engram/recall`). Open items left by this check: the unattributed part of the L5b noise-share move (+10 to +22 points over main's tip, present on p12's tip before any D-013 code), and the L6-C product-arm latency, still about 2.2x main's tip after the fix (not profiled).

## Re-verification on main (2026-10-18): the $0 deterministic layers, pre-registered before any run

Written and committed **before any layer is run**. Purpose: `docs/NUMBERS_STATUS.md` lists 56 numbers as STALE (measured on builds before the cleanup of
dead code, `pre-cleanup` -> `main` 7cca016). This section re-runs every layer that is deterministic and costs $0, one at a time on an otherwise idle
machine (timings must not compete), and turns each STALE number back into CURRENT where it reproduces. **LLM calls: 0.** Paid layers (L3 pilot, L6 LLM pilot,
L8 rounds, everyday trials) are not run and stay STALE.

**Build under test.** Branch `rerun-current` (worktree `wt-rerun-current`), cut from `main` 7cca016. The code under `plexus/src` and `plexus/queries` is `main`'s,
plus one harness-only commit `b9f01b8` (+ format fix `ca9dbb8`): L7 families G and I accept any agent-DB slot (their container name is derived from the port instead
of being pinned to `plexus-db-65` / `plexus-db-68`, which belong to other sessions) and G gets a `full-n200` scale (the registered full run's reachable levels:
N = 1, 2, 20, 200; N = 2,000 was registered as not reachable and is not attempted). No product code, query or scoring string is touched. Every run's `git` /
`environment` block must show a clean tree; a dirty-tree run is invalid and is redone. DB: FalkorDB 6.0.2 via `scripts/agent_db.sh 86` (port 6386), the
same `FALKORDB_ARGS` as the compose file. Venv `plexus/.venv-rerun`. Embedders as in each original run (L1/L4/L5/B1h/C7x fastembed; L6 and the recall bench `hash`).

**Verdict rule (stated now).** *Reproduced* = every deterministic count / correctness figure of the row equals the published one (ranking percentages and
id-noise figures may differ by the documented +-1 fact; such a figure is called reproduced when it is within the original's own documented noise, and the report says so);
for a timing row, the same ordering and conclusion, with the value re-measured on this machine (absolute ms are not expected to match: the machine and the
Docker Desktop state differ, and the original varied about 2x between plays). *Moved* = anything else: the new value is reported with the old one, and the row becomes
CURRENT at the new value ("moved from X"), with the reason if known. A row stays STALE only when its layer was skipped or its arm no longer exists.

**Known moved numbers, expected to stay at their moved values** (not expected to reproduce the original publication): the L5b `sep+mult` noise share (published
20.6-22.1% before the merge; 32.3 / 41.6 / 33.3% on the merged build `ae17aee` with lexical fusion off, which is main's behaviour; fusion no longer exists), and the L6-C
`hit_any` (published 11 / 6 / 1; 23 / 9 / 0 already on main's tip `1ddeb13` and on `f966146`).

| Layer (in run order) | Command | Published (rows of NUMBERS_STATUS) | Expected on this build |
|---|---|---|---|
| **L1 + L4 + ablation** (B1-B7, B10) | `crucible all` in a container sharing the DB's network namespace (`docker run --network container:plexus-db-86`, image built from this tree), fastembed, 10 reps | all four arms 0 violations C1-C8 (200 workers: 0 double claims, 0 lost updates); C7: B0/B1 0% caught, B2 and P miss 30 of 120 (25%); C2 slowest reclaim 1.27-1.52 s (bar 2.0 s); C5 0 leaked; ablation 7 of 7 broken, 5 of 5 unaffected, C4 181 started early, C8 60 returned (0 / 0 intact); L4: SQLite has the faster median claim at every worker count (0.10 vs 1.75 ms at 1 worker, 0.82 vs 570.9 ms at 200), Plexus server time 0.5 ms (1) to 3.6 ms (200), tenant sweep P 678 / 1025 / 1174 ops/s on 1 / 4 / 16 graphs vs SQLite 1103 / 1480 / 500, recall bounded by the embedder (about 47 embeds/s) | All violation counts, C7 miss counts and ablation counts (7/7, 5/5, 181, 60) **reproduce exactly**; C2 reclaim under the 2.0 s bar. L4 timings re-measured: same ordering (SQLite median faster at every worker count; P tenant sweep rises from 1 to 16 graphs while SQLite's does not; recall limited by the embedder); values not expected to match |
| **L5a** staleness (E1) | `python -m plexus.crucible.l5 --only staleness` | S symbol-level 19 TP / 0 FP; F file-level 19 TP / 106 FP (precision 15.2%); N 0% recall, 19 of 19 returned unflagged; stale unflagged 0 for S and F | reproduces exactly (deterministic) |
| **L5b** existing arms (E5, E7, E9, E10) | `--only forgetting --modes off,kw-fix,sep,sep+mult` at `--noise 5`, `--noise 15`, `--noise 5 --burst`; then `--modes off,sep+mult --sql` at the same three settings; seed 20261016, K = 20, 140 probes, fastembed | `sep` recall@1 85.7%, recall@5 100%, ceiling 85.7%, cross-entity displacers 13 -> 0; `sep+mult` recall@1 85.7 / 85.0 / 85.7%, recall@5 100%, critical loss 0; `kw-fix` recall@1 77.1%; the SQL arm ties (identical recall@1 / @5 and activation), 92 SQL vs 104 Cypher lines | recall@1 / recall@5 / critical loss / displacers / SQL tie / line counts reproduce (recall@1 within +-1 probe of id noise); **noise share expected at the moved values** (32-42%), not at 20.6-22.1% |
| L5b removed arms (E2-E4, E6, E8 and the `on-mult`, `sep+add`, `sep-entity`, `sep-flat` parts of E3, E5, E6, E8) | not run | - | stay STALE: "arm removed; reproduce at `pre-cleanup`" |
| **Hub world** (E6 hub half) | `--only hub` (200 probes; arms `off`, `sep`) | `sep` 100% recall@1; relevance-only 97.5% (96.5% in the recall-check play) | `sep` 100%, `off` 96.5-97.5%. `sep-entity` / `sep-flat` removed, not run |
| **B1h** (C6) | `python -m plexus.crucible.l2.sql_run run --which both` | 43/43 and 36/36, 0 LLM calls, 34 operations | reproduces exactly |
| **C7 extended** (D1) | `PLEXUS_EMBEDDER=fastembed ... crucible l1 --tests C7X --arms P,P-mcp,B0,B1,B2 --reps 1` | P and P-mcp 0 false merges in 150 distinct+maybe pairs; B2 68 of 150; auto 51/76 = 67.1%, surfaced 70/76 = 92.1%; heavy 10/24 auto, 19/24 surfaced; light 10/20; unit 11/12 | reproduces exactly (the real embedder is deterministic; the rule has no random input) |
| **L2 and L2-scale** (C1-C4) | re-score from the cache only: `l2.run run --mode full --budget-usd 0` and `l2.scale_run run --mode full --budget-usd 0` | L2: P 43, B0 43, B1 43, B2 40; L2-scale: P 36, B1 32, B0 30, B2 23 | **Only if every call is served from the cache.** With a cap of 0 the runner raises `BudgetExceeded` before any `claude -p` process when a key misses (`ClaudeRunner.ask`); the arm is then incomplete, nothing is written to `latest-*`, the rows stay STALE and the reason is recorded. Tokens / cost / latency columns are the original calls' (the cache keeps them), so C2 / C4 are reproduced by re-scoring, not re-measured |
| **L6 A, A-dag, B, D** (F1-F3, F7, F9) | `l6.run det` (A, dag, B, D), `l6.run postfix` (A product arms + F arm P, 200 kills) | A: B1h 24/24, P-tuned 24/24; post-fix `P-product-tool-p9f` 24/24, `P-product-service` 24/24, `P-product-tool` 18/24; B: B1h 24/24, P-tuned 24/24, `P-product-tool` 16/24, `P-product-tool-p9f` 20/24, `P-product-service` 24/24; D 24/24 both | all strict counts reproduce exactly; timings keep their ordering (SQL faster; A at 5,000 facts SQL 110-192 ms vs product 450-595 ms), values re-measured |
| **L6 E** (F4) | `l6.run conc --runs 10 --seconds 6` | 0 violations for every single-statement arm; level-wise traversal tears (P-levelwise V1 / V3 counts) | verdicts reproduce; the tear counts are timing-dependent and expected to differ |
| **L6 F** (F5) | `l6.run postfix` (arm P, 200 kills) and `l6.run crash --kills 200` (arms B1h, P, B0) | arm P after the fixes: 0 orphans, 0 lost acknowledged writes, `missing_derived_from` 0; B1h 0 orphans; B0 a few | P 0 / 0 / 0; B1h 0; record counts differ (kills are timed). `crash` runs the arm P of today's tree, so its orphan count is expected 0, unlike the pre-fix 94 of 1,240 |
| **L6-C** (F10) | `l6.run_c --scale 1.0` (hash embedder, seed 20261016, 75 questions) | B1h and P-tuned 75/75 with identical lists; SQL 3.3x faster at depth 3; shipped `recall(hops)` strict 0/75; `hit_any` 11 / 6 / 1 published, moved to 23 / 9 / 0 on main's tip | 75/75 identical lists, strict 0/75, `hit_any` 23 / 9 / 0; SQL faster at depth 3 |
| **L8 recall bench** (G5) | `l8.recall_bench --label rerun-current --port 6386` (5 seeds, hash, `PLEXUS_TOOLSET=core`) | replay calls that found their target 28/36 (+-1 id noise: 27-29); needed facts 5/5, 5/5, 1/1; canonical 1000/1000; mean response 5,333 / 5,766 chars | needed facts and canonical exact; replay 27-29/36; response sizes within a few percent |
| **L7 H** (G1) | `l7.h run --scale full` | SQL faster in 9 of 11 cells (25-900x on traversals); Cypher about half as long; Cypher timeouts on unbounded closures; one silently wrong planner answer | verdicts and the cell count reproduce; ratios re-measured |
| **L7 G** (G1) | `l7.g run --scale full-n200` | N = 1-200 measured; 0 cross-tenant leaks in every arm; FalkorDB latency flat from 1 to 200 tenants, SQLite per-tenant files degrade; tenant creation about 9x slower for FalkorDB; memory 4-15x | scope as registered (N = 2,000 is not attempted: registered as not reachable); verdicts reproduce |
| **L7 I** (G1) | `l7.i run --scale full` (parts I1-I5; the AOF repro container `plexus-db-71-aofrepro` on 6371 is removed afterwards) | SQLite transaction 0 partial close-outs in 200 kills; product path (four tool calls) 86; `MULTI`/`EXEC` survives a client kill but has no rollback; one Cypher statement matches the SQL transaction with 1 round trip vs 13; AOF replay crash 10 of 11 | SQLite 0, one-statement arm 0, product path > 0 (the exact count depends on kill timing); the AOF crash expected again on the preserved data (an upstream bug of FalkorDB 6.0.2) |
| **L7 J** (G1) | `l7.j run --scale dev` (the registered smaller tier: the full grid is 144 cells, about 163 min by the harness's own plan, over the 90-minute allowance) | SQLite 6-17x the throughput with 0 errors at every population; FalkorDB rejected about 90% of calls at 1,000 sessions over 200 tenants | direction and error behaviour reproduce at populations 2 / 20 / 200 and the P = 1,000 feasibility probe; the ratio range is not expected to match (1 rep, 10 s cells) |

**Not run, stay STALE:** L3 pilot (C5), L6 LLM pilot (F6), L8 rounds A / A2 / token fixes (G2-G4), everyday trials, E2-E4, the removed arms of E3 / E5 / E6 / E8, E11 (`fan_e` PROFILE),
B8-B9 (query-tuning probes), B11 (live-ablation counts), G6-G11 (audits, deployment, probes), A8-A16 (comparison controls, recordings, earlier suite counts).

**What can go wrong, and how it is reported.** An L5b row whose ranking numbers move is reported at its new value with "moved from"; a falsified expectation is reported as
falsified, not tuned away. If a layer fails to run (a crash, a timeout, the DB hanging after the I3 kills) it is retried once on a fresh slot; if it still fails the row stays STALE
with the reason. The `latest-*.json` pointers move to a new run only where the layer reproduced or the new value is the honest current one; every old run directory stays.
