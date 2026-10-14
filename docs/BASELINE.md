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
