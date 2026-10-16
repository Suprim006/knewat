# BASELINE.md: how we prove Plexus works (benchmark plan, "Crucible")

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

