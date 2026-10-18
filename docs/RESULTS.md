# Results: everyday-workflow trials, ablation and the Crucible benchmark

Moved out of the README so it stays a setup guide. Numbers carry their build in [NUMBERS_STATUS.md](NUMBERS_STATUS.md); methodology and pre-registrations are in [BASELINE.md](BASELINE.md).

> **Partly STALE (2026-10-18).** The $0 deterministic benchmark layers (L1, L4, ablation, L2 and L2 at scale re-scored from the cache, B1h,
> C7 extended, L5a, the surviving L5b arms, the hub world, L6 A-F and L6-C) were re-run on `rerun-current` (the code of main `7cca016`) and are
> CURRENT; where a re-run moved a number, this README states the new value. Still STALE (earlier builds, not re-run): the L3 pilot, the L6 LLM
> pilot, L7, L8, the floor 0.5 / 0.9 forgetting runs and the other removed L5b arms, deployment timings, the Testing counts, the recorded
> runs' cost. Build per number: [docs/NUMBERS_STATUS.md](NUMBERS_STATUS.md). Counts of the tree itself are current: 45 tools,
> 114 query files, the recording's 247 nodes / 708 edges.


## Where it helps: decisions made ahead of the code, across repos

The case for Knewat is the multi-repo team: a rule decided in a planning session in one repo, a bot's deprecation notice, a change
on a branch nobody has merged. Nothing in the next repo shows any of it, and the next agent breaks it. With Knewat the decision, who made it,
from which source and why is one graph every agent on the team reads before it writes code.

![Three everyday workflows, 4 runs per arm: rule violations by plain Claude Code, Claude Code with CLAUDE.md, and Claude Code with Knewat](blog/figures/06_trials.png)

Real Claude Code agents doing ordinary feature work in small repos, in separate sessions that share no conversation.
There are three arms: plain Claude Code, Claude Code told to keep decisions in `CLAUDE.md`, and Claude Code with Knewat.
Scoring runs the code the agents wrote. 4 runs per arm, predictions pre-registered. Full records: [trials/](../trials/FINDINGS.md).

| Workflow | Plain | CLAUDE.md | Knewat |
|---|---|---|---|
| A team rule decided in repo A, later work in repo B (rule violations, of 24) | 24 | 24 | **0** |
| Parallel agents on git worktrees: rule on an unmerged branch + a non-AI ci-bot's deprecation notice (of 12) | 9 | 8 | **0** |
| Retract a void document: rules correctly kept (of 8) / void-only rule removed (of 4) | 8 / 0 | 8 / 4 | 8 / 4 |

Knewat wins where no shared file reaches the next agent: another repo, an unmerged branch, a note from a tool that
isn't an AI. It ties a well-kept `CLAUDE.md` where the file does reach the next agent. Within one repo on one machine,
plain Claude Code's own auto-memory already ties both (trials 3/4).
The trial 8 tie exposed a gap: a fact could name only one source. Facts now take several sources (D-015). On the final
code the re-run linked the double-sourced rule to both documents and retracted the void one through
`quarantine_source` / `forget_source`, both 4/4. Knewat costs $0.01-0.10 more per run. Caveats: small synthetic repos,
n = 4 per arm, designed after trials 1-5; build per trial in [docs/NUMBERS_STATUS.md](NUMBERS_STATUS.md) (section H).

## Why FalkorDB is the core (and the ablation that shows it)

FalkorDB is the only state store. There is no SQLite or JSON copy of the memory. Recall, dependency-aware claims, `why`,
time travel, contradiction detection, forget cascades and tenant isolation are graph queries, and the Flow page is a
traversal of the audit edges.

The test of that claim is an **ablation**: delete four relationship types (`DEPENDS_ON`, `BASED_ON`, `DERIVED_FROM`, `READ`)
and see what stops working.

> *(stale: the Crucible ablation figures below were measured on `84763aa`, 2026-10-15. The live ablation's 6 of 6 / 2 of 2 is asserted by the current test suite (current); the counts quoted from the Sonnet recording's output were measured on the P3 demo build (stale). See [docs/NUMBERS_STATUS.md](NUMBERS_STATUS.md).)*

- **Crucible ablation** ([`docs/BASELINE.md`](BASELINE.md)): **7 of 7** capabilities that use those edges break
  (dependency-aware claims, `blocked_by_failure`, `why` for decisions and for facts, `knew_at`, `who_knew`, cascading forget);
  **5 of 5** controls are unaffected (as-of, recall, contradiction flags, supersession, exclusive claims). Re-running the
  dependency-order test (C4) with the edges stripped gives 149 tasks started before their dependencies finished, and the
  forget test (C8) gives 60 forgotten facts still returned (0 and 0 on the intact graph).
- **Live version on the real recording** (`knewat demo ablation`: 6 edge-dependent features and 2 controls on the demo
  tenant, a smaller set than Crucible's):

  ```bash
  docker compose run --rm knewat-cli demo ablation --tenant demo
  ```

  It copies the tenant with `GRAPH.COPY`, strips the four edge types in the copy and runs the same probes on both. Output on
  the Sonnet recording: `why(decision)` goes from "3 supporting facts, 2 agents, 3 sources" to 0 facts and 0 sources;
  `knew_at` from 5 facts to 0; with `DEPENDS_ON` gone, 11 tasks are claimable on a fresh board with unmet dependencies;
  **6 of 6 features break, 2 of 2 controls are unaffected**, and the original tenant is verified untouched. Open the copy
  (`demo_ablated`, kept unless you pass `--drop`) in the View to see the same graph without those edges. Details:
  [`docs/demo.md`](demo.md).

What the ablation does **not** show: that nothing else could store these relations. SQLite (B1) answers some of the same
provenance questions with recursive CTEs, and the benchmark below reports where it ties.

## Benchmark results (Crucible, honest)

Crucible swaps only the backend behind an identical tool API: **B0** files (flock + atomic replace), **B1** SQLite
(transactions), **B2** vector store (same local embedder), **P** Knewat. Everything else is fixed (same agents' prompts,
model, scenario, budgets, seeds). Exact-match scoring, no LLM judge. Full methodology, pre-registration and failure analysis:
[`docs/BASELINE.md`](BASELINE.md); the same numbers are in the View's Results page.

> **Partly STALE (2026-10-18):** re-run on `rerun-current` and CURRENT: L1, L4, ablation (`fb8e02f`), L2 and L2 at scale (re-scored from the cache), B1h, C7 extended, L6 A-F and L6-C (values that moved are stated in the table). Not re-run, still STALE: the L6 LLM pilot (`dc83183`..`5871d30`), L3, L7, L8. Reproduce a number by checking out its build (or tag `pre-cleanup` for the build just before the dead-code cleanup). Per-number table: [docs/NUMBERS_STATUS.md](NUMBERS_STATUS.md).

| Layer | What we found | How to read it |
|---|---|---|
| **L1** correctness under concurrency (C1-C8, 10 seeded runs per case) | **All four arms pass with 0 violations.** Knewat does **not** win on claims, leases, dependency order, as-of, tenant probes or forgetting: a competent file store or SQLite ties it. The one measured difference: C7 near-duplicate paraphrases, where B0/B1 catch 0%, B2 misses 25% (30 of 120 pairs) and Knewat misses 50% (60 of 120 pairs: the stricter P9-c duplicate rule merges fewer paraphrases and merges no different statement; see C7 extended) | The graph is not claimed to be more correct on these |
| **L4** performance | **SQLite is faster than Knewat on the median claim at every worker count** (0.12 vs 4.9 ms at 1 worker; 0.80 vs 720.9 ms at 200) but has worse tail latency at 200 workers (p99 4.76 s vs 1.46 s). Knewat server-side time stays under 4 ms for claims; the rest is queueing, because FalkorDB serialises writes per graph. **Knewat scales across tenant graphs: 112 → 202 → 459 ops/s on 1, 4, 16 graphs (+311%)**; SQLite also rose in the re-run (425 → 889 → 1771; the first run had it fall to 500 at 16 files, so that contrast is not reproduced). `recall` is the slow path now: 2-6 ops/s, 77-110 ms server-side at 300 facts (it was about 10 ms before the ranking terms were added) | Raw claim speed is not Knewat's case. B0/B1/B2 are in-process libraries and the Knewat arms cross a container network |
| **L2** provenance and time questions (43 questions, one Acme project) | **Tie on accuracy:** P 43/43, B0 43/43, B1 43/43, B2 40/43 (93.0%). The whole history fits in the 32k-character context, so the LLM reads everything. Knewat costs 0 tokens (vs 13-16k tokens and $0.05-0.06 per question for B0/B1) and ~2.5 ms vs ~5 s | A tie on accuracy; the difference is cost, latency and determinism. Knewat uses a hand-written Cypher per question family |
| **L2 at scale** (pre-registered; 20 sprints of history, 10.4-16.6× the context cap, 36 questions) | **P 36/36 (100%), B1 32/36 (88.9%), B0 30/36 (83.3%), B2 23/36 (63.9%).** Wilson 95%: P 90.4-100, B1 74.7-95.6, B0 68.1-92.1, B2 47.6-77.5. Paired sign test: P vs B0 6-0, p = 0.031; **P vs B1 4-0, p = 0.125, not distinguishable from noise**; P vs B2 13-0, p < 0.001. B0/B1 failures were join-heavy provenance questions and one transitive dependency, not class-wide questions; accuracy did not decay with how early the sprint was. B0/B1 spent about 20-22k tokens and $0.08-0.09 per question (about 5 s) against 0 tokens and a few milliseconds | A gap, but a small one: the intervals of P and B0/B1 overlap, and the B1 gap is within sampling noise. Not a claim that Knewat is "better at memory" in general |
| **B1h** hand-written SQL control on the same L2 and L2-scale questions | **SQL ties:** B1h 43/43 on L2 and 36/36 on L2-scale, the same as Knewat, at 0 LLM calls | On questions a SQL author can write, a relational schema answers as many as the graph. The advantage over B0/B1/B2 is a structured record, not graph storage as such |
| **C7 extended** (226 labelled pairs; negations, units, number words, near-twins) | **0 false merges in 150 pairs that must stay apart** (every category, both splits; < 2.0% at 95% by the rule of three); the old rule (B2) falsely merged 68 of 150. **Targets missed:** heavy paraphrases are auto-merged 10 of 24 and surfaced for review 19 of 24, against a pre-registered 75% auto or 95% surfaced; light paraphrases 10 of 20 and unit rewordings 11 of 12 against 100% auto | Precision is the claim, recall of heavy rewordings is not. A close-but-different pair becomes a soft `DUPLICATES_MAYBE` link instead of a silent merge |
| **L6** five pre-registered families where a graph could beat SQL (blast radius, why-depth, cross-sprint aggregation, consistent reads, crash-consistency) | **A tie or a SQL win in every family.** A: SQL ties the hand-tuned graph query and the product's `impact` tool did not finish at 5,000 facts (fixed: see below); B: tie when the call passes depth 12 (the MCP tool exposes it now; the tool path itself was not re-run); D: both 24/24, SQL 3.6x faster; E: 0 violations for every single-statement arm, the product's own level-wise traversal tears; F: Knewat lost (94 of 1,240 records without their `WROTE` edge; fixed for `assert_fact`, `record_decision` and `handoff`, see below). LLM pilot (8 questions per family): B1a 24/24, B0g 24/24, B0r 2/24, Knewat MCP tools 10/16, 88 calls, $7.09. **C (run later, D-013 §5.4): multi-hop recall with a fan-weighted rule, hand-written SQL and Cypher both 75/75 with identical lists; SQL 3-6x faster at depth 3; the shipped `recall(hops)` 0/75 in the top 5.** The same phase's L5b SQL arm ties the shipped ranking within one probe (recall@1 85.7 vs 85.0, 85.7 vs 85.7, 85.7 vs 84.3 in three runs, recall@5 100% on both, 92 lines of SQL vs 104 of Cypher; the two top-1 lists no longer agree probe by probe) | The graph is not found to beat a competent SQL schema in any family, including ranking and multi-hop recall; the product defects the run exposed were fixed and re-run, except the `recall(hops)` ranking found by C, which is recorded as the next fix |
| **Ablation** | 7 of 7 edge-dependent capabilities break, 5 of 5 controls unaffected | The graph does real work (above) |

**What the results support.** Knewat makes provenance, dependencies and time first-class edges in FalkorDB, so *why*, *who knew* and *what is
affected* are single deterministic queries (zero tokens, milliseconds). Against flat files and tool-less LLM readers that is a large cost and
latency win, and a measurable accuracy win once histories exceed the context. A well-built relational schema with recursive CTEs matches Knewat on
correctness and is faster on simple claims; we publish that tie (B1h, L6), the benchmark, and the cases where we lose. L6 in one line: no family
shows the graph beating hand-written SQL, and two product defects it exposed (an `impact` query that never finished at 5,000 facts, and a
provenance edge that a crash could lose) were fixed and re-measured.

**Methodology limits** (the Results page and `report.md` print the full list): synthetic data; one scenario family; one model
(`claude-sonnet-5-5`); LLM arms run once per question; 36-43 questions; scripted worker threads on one machine against a
single-node database; the L2 baselines see their own artifacts at an equal 32,000-character cap, selected by BM25 or top-12
cosine; Knewat answers each question family with hand-written Cypher, which favours Knewat, while every L2-scale question
names its sprint, which favours retrieval; L2-scale asks no questions that aggregate across sprints (the strongest case for a
graph), and the procedures family was not measured; L3 (end-to-end LLM teams with injected faults) was only piloted and is not
in the results; Hermes is excluded from all published runs. Do not compare these numbers with vendor-reported LoCoMo or
LongMemEval scores. Raw files: [`knewat/src/knewat/crucible/results/`](../knewat/src/knewat/crucible/results/).

Reproduce: `docker compose --profile bench run --rm crucible all --quick` (about 2 min; the full run takes about 24 min)
writes L1 + L4 + ablation. The L2 and L2-at-scale answers are cached in `knewat/demo_data/crucible/`, so a rerun is free and
byte-reproducible; `python -m knewat.crucible.combine` merges everything into `latest-all.json`, which the Results page serves.

