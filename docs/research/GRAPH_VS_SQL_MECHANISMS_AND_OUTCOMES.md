# Graph vs SQL for agent memory: mechanisms and outcomes

Written 2026-10-16/17 (FalkorDB Graph Hacks, Track 02). Status: two completed, pre-registered experimental
rounds, reported here together. Sources: `docs/research/P10_GRAPH_VS_SQL.md` (branch `p10`, head `f708fd6`) and
`docs/research/L8_LONG_HORIZON_OUTCOMES.md` (branch `p11`, head `c83488e`), both unmerged at time of writing.
Every number below is read from a committed `results.json` or `report.md`, not transcribed from memory. Labels:
**[P10]** = mechanism-level round (speed, scale, isolation, atomicity), **[L8]** = outcome-level round (does any
mechanism-level property change what a live agent team does).

## Abstract

Plexus is a FalkorDB-backed memory and coordination layer for AI agent teams. An earlier round (Crucible L6)
found that FalkorDB ties a hand-written SQLite control on correctness for provenance-style questions, with SQL
usually faster. This report covers two follow-on rounds that ask sharper questions. P10 asks where the two
backends' *designs* should differ by construction (query expressiveness, multi-tenant isolation and scaling,
transactional atomicity), holding everything else constant and running at scales from 1 to 2,000 tenants and
10 to 50,000 facts. L8 asks a different kind of question: whether any mechanism-level property changes
*outcomes a real agent team produces* (acting on stale facts, repeating finished work, surfacing contradictions),
measured on live 3-agent Claude Code runs rather than synthetic query batches, scored deterministically against
a known fault schedule. The mechanism-level round confirms one FalkorDB advantage (flat multi-tenant latency)
and identifies a large and unexpected FalkorDB weakness (unbounded traversal, 25x-900x slower than SQL). The
outcome-level round finds that Plexus's current implementation does not reduce stale-fact use or repeated work
relative to SQLite or an unstructured file-based baseline, and traces the failure to retrieval quality
(`recall`) rather than to the graph data model itself.

## 1. Research questions

Both rounds were commissioned to test one working hypothesis, stated before any measurement in both
pre-registrations:

> Graph (FalkorDB) gives query expressiveness, easier multi-tenancy, and easier traversal. SQL (SQLite) gives
> atomic writes.

P10 operationalizes each of the four clauses as a measurable family. L8 asks the question the hypothesis
implicitly assumes but never states: *if any of this is true, does it reduce the failure modes an agent team
actually exhibits* -- specifically the three largest MAST failure categories this project's own problem
statement cites (Cemri et al., arXiv 2503.13657): step repetition (15.7% of traces), reasoning-action mismatch
(13.2%), and missing completion recognition (12.4%), plus a fourth outcome this project's design targets
directly: acting on a fact that a source change has already invalidated ("stale-act rate").

## 2. P10: mechanism-level comparison

### 2.1 Design

Four families, each with a pre-registered falsifiable prediction (including explicit predicted ties), one
seed per family except the concurrency family (10 seeds), same machine, same FalkorDB 6.0.2 image, hand-written
Cypher and hand-written SQL by the same author.

| Family | What it measures | Scale swept |
|---|---|---|
| G -- multi-tenancy | Tenant creation cost, storage footprint, cross-tenant leakage, latency vs. tenant count | N = 1, 10, 100, 200, 2,000 tenants |
| H -- query expressiveness | Motif/pattern queries, multi-relationship traversal, constrained shortest path, cross-cutting aggregation, hand-written in both languages | 2,000 and 50,000 facts |
| I -- atomic writes | A 6-entity "close-out" write under repeated process kills, logical aborts, server kills, concurrent lost-update and write-skew races | 200 kills/arm (I1), 20 server kills/arm (I3), 20-200 concurrent writer threads (I4) |
| J -- concurrent sessions | Realistic mixed-operation session replay at varying concurrent population | 2, 20, 200, 1,000 sessions |

Backends compared: F (FalkorDB, product path and hand-tuned Cypher), S-file (SQLite, one file per tenant), and
S-shared (SQLite, one shared file with a `tenant_id` column and row-level filtering in every statement).

### 2.2 Results

**Multi-tenancy (G).** Isolation is a tie: zero cross-tenant leaks on the product path for either backend from
N=1 to N=2,000. The raw-channel matrix shows S-shared has *no database-enforced row isolation* -- a raw query
with `ATTACH` or without a view+authorizer leaks 50/50 rows; S-file and F need no special configuration to
refuse the equivalent attack. FalkorDB's per-operation latency ratio from N=1 to N=2,000 is 0.91x-1.09x (flat).
SQLite's degrades 14x-40x over the same range (worse for the shared-file layout), though it remains faster than
FalkorDB in absolute terms at every tenant count measured. Costs run the other way: FalkorDB tenant creation is
9x slower (134.8ms vs. 15.1ms), an empty tenant uses 7x-15x more memory than an empty SQLite file, and 2,000
FalkorDB tenants fit in available memory only with RDB persistence forks disabled (three run attempts were
needed to reach N=2,000 cleanly; amendments 3-4 document two failed attempts: one undercounted by using Redis's
inflated memory-accounting figure as the cap, one was OOM-killed by a persistence fork). At 1,000 concurrent
sessions over 200 tenants (family J), FalkorDB rejected roughly 90% of calls with `Max pending queries
exceeded`; SQLite (S-file) rejected none, though its p99 latency exceeded 5 seconds at that load.

Reading rule (pre-registered): *refine*, not *confirm* -- FalkorDB does not beat both SQL layouts cleanly; it
beats S-shared's isolation story but ties S-file's isolation, and its latency-flatness advantage is real but
comes at a measured resource cost the hypothesis did not originally price in.

**Query expressiveness and traversal (H).** SQL won every traversal cell at both scales, by 25x to 900x at
50,000 facts. The constrained-shortest-path query timed out (10s budget) on 6 of 12 Cypher questions; all three
Cypher variants of the cross-cutting closure aggregate timed out entirely, while the SQL recursive-CTE version
answered in 7.4 seconds. Root cause, confirmed by inspecting `EXPLAIN`/`PROFILE` output: FalkorDB's variable-length
pattern matching enumerates whole paths before applying filters, where a recursive CTE prunes and deduplicates
at each expansion step. Cypher won one of the motif questions, 5.9x faster at the 50,000-fact scale; one motif
question was unscored at that scale because neither language answered within the time budget. Code-complexity
proxy (statement line count, as a concrete stand-in for "expressiveness"): mixed, not a clean win for either
language across the H families.

Reading rule: the pre-registered hypothesis ("graph gives easier traversal") is *refuted* for unbounded,
aggregate and shortest-path-style traversal at these scales; it survives only for the one motif case.

**Atomic writes (I).** The headline test: a 6-entity close-out write, 200 hard process kills. SQLite's `BEGIN
IMMEDIATE` transaction: 0 partial writes, 0 lost acknowledged writes. Plexus's actual product path (the same
write spread across 4 separate tool calls over the MCP transport): 86 partial writes out of 200. Server-kill and
logical-abort variants (I2, I3) show the same pattern: SQLite 0 partial in all configurations; FalkorDB's
`MULTI`/`EXEC` has no client-visible rollback, so a kill mid-sequence leaves 103 of 103 deliberately-staled writes
partial. Lost-update and write-skew races (I4): both backends reach 0 violations under a correct concurrency
primitive (SQLite `BEGIN IMMEDIATE`; FalkorDB `WATCH`+`MULTI`/`EXEC`, which does signal key modification and
works as an optimistic-concurrency primitive), and both show violations when the naive two-statement form is
used without any guard, in either language.

The refining result (I5): when the SAME 6-entity write is expressed as a single Cypher statement (not the
product's 4-tool-call form), it matches SQLite's transaction guarantee exactly across every crash scenario
tested, using 1 round trip instead of 13 and 26 lines of code instead of 39 (roughly 18x slower per call,
server vs. in-process, but zero partial writes).

Reading rule: *confirmed* for the product as currently built, *refined* against the pure hypothesis -- the
atomicity gap is a property of how Plexus's write path is structured (multiple round trips), not an inherent
limit of a single Cypher statement's guarantee.

**Concurrent sessions (J).** Throughput ordering at every population and layout: S-file >= F-service >= F-mcp
(the MCP path pays an audit-write tax, 2x-4x below the raw service path). At P=200 workers, S-file's p99 latency
is *worse* than F-service's p99 despite a better median -- SQLite's busy-handler has no fair queue, so tail
latency inverts under contention even though median throughput favors it. At P=1,000, FalkorDB produces queue-
rejection errors (count > 0); SQLite produces zero lock errors (120-second busy timeout) but exceeds 5-second p99.

### 2.3 Surprises, errors, and limits (as reported, not softened)

- A nondeterministic FalkorDB 6.0.2 crash was reproduced on container restart during log (AOF) replay, 10 of 11
  attempts on a copy of the crashed data, implicating a race between `GRAPH.DELETE` and asynchronous graph
  memory freeing on a background thread. The crashed container was preserved as evidence rather than removed.
  Relevant to Plexus's own tenant-deletion-then-restart path; not yet filed upstream at time of writing.
- Five pre-registered predictions were wrong and reported as such: an empty FalkorDB tenant would stay under
  500KB (it is 744KB); SQLite latency would stay flat with tenant count (it degrades 14x-40x); the AOF-replay
  crash would not reproduce (it did); queue-limit rejections would need only one busy tenant (they needed many);
  the constrained-shortest-path query would need application-side code in both languages (one statement
  sufficed in each).
- No Postgres arm was run (deferred to a later round, see §4).
- One author wrote both the Cypher and the SQL for every family, a conflict of interest acknowledged in the
  original pre-registration and not mitigated here.
- Family H's 50,000-fact timeouts mean two cells (one motif, parts of the closure test) are formally unscored
  rather than scored as losses -- reported as "not run," not folded into either backend's tally.

## 3. L8: outcome-level comparison

### 3.1 Why a second, different kind of benchmark was needed

P10 (and L6 before it) measure whether a backend can answer a class of query, and how fast. Every metric in
P10 is a property of the store, checkable in isolation from any agent. None of it establishes whether a live
agent team, given the chance to misuse or ignore what the store offers, actually behaves better. The project's
own problem statement (`docs/PLEXUS_REPORT.md` §1) cites MAST failure-rate statistics as motivation but, before
this round, had never measured step repetition, missing-completion recognition, or reasoning-action mismatch
on its own runs -- nor measured whether agents act on facts already known to be false. L8 closes that gap.

### 3.2 Scenario and design

Three real `claude -p` Sonnet agents (planner, researcher, builder), one process per turn with no session
persistence, so the memory store under test is the agents' *only* continuity. Scenario: "sprint 21" of the
Acme Notes API story, with 20 prior sprints of history preloaded (far exceeding a single agent's context window)
and a 60-function code repository generated by the existing L5a staleness-edit generator. A fixed, seeded fault
timeline -- 10 code/spec changes, 3 process kills, 3 deliberately planted inter-agent contradictions, and a v1-
to-v2 style-guide change -- lands at identical turns for every backend within a seed, so every arm faces the
same ground truth shifting under it in the same order. Every fact value is a unique sentinel token, which makes
scoring a pure deterministic string-match against the known fault schedule: no LLM judge for any headline
metric. Five seeds (20261017-20261021).

**Arms (Round A, approved scope):** P (Plexus, current MCP tool set, agents not told about the staleness-
specific tools), B1 (SQLite, same tool API), B0' (unmodified Claude Code managing its own `MEMORY.md`/task files
with no MCP tool API at all -- the "what people actually do today" control). B0 (file store with an imposed
tool API) and B3 (Postgres behind the same tool API) were scoped in the pre-registration but deliberately not
run in Round A (cost-gated; see §3.5).

**Metrics, each with a pre-registered computation and an explicit prediction (including predicted ties) before
any run:** stale-act rate, time-to-notice, three MAST signatures (step repetition, missing completion
recognition x3 sub-forms C1-C3, reasoning-action mismatch x3 sub-forms M1-M3), contradiction-detection latency
(X1/X2), three end-of-run cross-cutting audit questions (Q1-Q3), tokens per correct action (raw and billing-
weighted), provenance completeness at kill turns, recovery-repeat rate (R1-R4), and a cold Cypher-vs-SQL query-
authoring probe.

### 3.3 Results, pooled across 5 seeds

| Metric | P | B1 | B0' |
|---|---|---|---|
| Changes never noticed (of 41 total) | 11 | 4 | 2 |
| Step repetition | 0.3% (1 event) | 0% | 0% |
| Missing completion C1-C3 (total) | 4 | 4 | 1 |
| Reasoning-action mismatch M1/M2/M3 | 0/0/3 | 0/3/5 | 0/n.a./n.a. |
| Tokens per correct action, raw | 85,840 | 34,248 | 22,190 |
| Tokens per correct action, billing-weighted | 12,878 | 6,421 | 7,345 |
| Provenance, all writes (of total) | 209/209 | 210/210 | n.a. |
| Provenance at kill turns | 11/11 | 10/10 | n.a. |
| Contradiction X1 caught at write time (of 5) | 5 | 5 | 0 |
| Contradiction X2 caught at write time (of 5) | 4 | 5 | 0 |
| History facts found when needed (of 15) | 3 | 5 | 15 |
| Finished work redone after a kill | 5 of 5 | 9 of 9 | 0 of 9 |
| Audit Q1 / Q2 / Q3 correct (of 5 each) | 5/2/2 | 5/2/1 | 0/1/2 |
| Query-authoring probe (cold, first try, of 9) | Cypher 7/9 | SQL 7/9 | n.a. |

Pooled ordering on the headline composite (worst to best, every post-hoc robustness variant tried preserves this
order): **B0' <= P < B1**.

### 3.4 Interpretation

Write-time contradiction detection is the one place the design worked close to as hypothesized: P and B1 both
caught 4-5 of 5 planted contradictions at write time; B0' caught none, because a flat file has no mechanism to
notice a conflicting write at all. Everywhere else, Plexus's *current implementation* did not separate from, or
fell behind, both baselines:

- **Recall quality is the dominant bottleneck, not the data model.** P found only 3 of 15 needed history facts,
  worse than SQLite's BM25-style retrieval (5 of 15) and far worse than B0's plain `grep` over its own files
  (15 of 15). In 4 of 5 seeds, this directly caused a task (t13, cascading to block t16) to fail: `recall`'s
  embedding-based ranking did not surface the one fact (an Acme billing note) the task needed, among otherwise-
  correct results about an unrelated API.
- **The feature built for this exact problem was never exercised.** Plexus's staleness subsystem
  (`anchor_fact`, `facts_to_verify`, `verify_fact`) exists specifically to catch facts invalidated by a code
  change. Across all 5 seeds, P's agents made zero calls to any of these three tools, because the scenario
  briefs never told them the tools existed. Round A therefore measures what happens when a team *doesn't* use
  Plexus's anti-staleness design, which is a different (and arguably more realistic, but less flattering)
  question than "does the design work when invoked."
- **Agents read less raw code under P and leaned on `recall` instead** (72 file reads vs. 106 for B1, 277 for
  B0'), which plausibly explains both the lower stale-act rate on some axes and the higher miss rate on others:
  `recall` is being trusted in place of ground truth more than either baseline's retrieval method, and when it
  misses, there is no fallback the agent reaches for.
- **Token cost is 2.0x-2.7x the baselines with no correctness payoff in Round A** -- the opposite of the
  defensible trade-off this project's own prior report (`docs/PLEXUS_REPORT.md` §6.7) flagged as acceptable
  ("costs more, but answers right"). Here it costs more and answers worse on several axes.
- Audit questions Q2/Q3 (cross-cutting, multi-sprint) were scored mostly wrong for both tool-using arms (P: 2/5,
  2/5; B1: 2/5, 1/5), despite the query-authoring probe showing the underlying Cypher/SQL statements were
  written correctly -- the gap is in what the stores record about *which facts were read when*, or in how that
  record is matched at audit time, not in query authorship. This was not root-caused further in Round A.

### 3.5 Process notes, deviations, and self-corrections

- Independent review of the scorer, performed after seeds 1-2 but before trusting any headline number, caught
  three bugs: reclaim-turn repeats were not counted as recovery events, provenance was checked against the
  wrong step, and B0''s task-completion detection used the final file state rather than the tracked history.
  All three were fixed (amendments 3-4) and **every seed, including the ones scored before the fix, was
  rescored with the final scorer code** -- no seed's headline number reflects the pre-fix scorer.
- 42 of 45 scheduled process kills were applied; in 3 of the P seeds the run ended at turn 20 (after task t13
  failed and t16 became permanently blocked) before the second kill's scheduled turn, so those kills never had
  a chance to fire.
- One seed's working tree was flagged dirty by the whole-repo dirty-state check (a fix applied after an L7 bug
  where the same check only inspected its own subfolder); the only uncommitted files at that point were
  `score.py`/`test_score.py`, neither of which the runner reads, so the run's validity is unaffected, but the
  flag is reported rather than suppressed.
- B0 and B3 were in-scope in the pre-registration but explicitly deferred per the plan's own cost-gate: the full
  5-arm x 5-seed design was estimated at ~$37 (range $25-55), against a project-to-date LLM spend of ~$15
  notional; Round A (P/B1/B0' only) was approved at an estimated ~$17 and did not exceed that.
- Total spend for Round A, including the query-authoring probe ($0.76) and one $0.19 shake-down run that was
  discarded and recorded as such (`discarded.json`): within the approved range.

## 4. Synthesis across both rounds

| Hypothesis clause | P10 (mechanism) | L8 (outcome) | Net reading |
|---|---|---|---|
| Graph gives query expressiveness | Mixed; SQL wins most traversal cells, Cypher wins one motif | Not directly tested (query-authoring probe is a tie, 7/9 each, Cypher shorter) | Weak support at best; traversal expressiveness claim is largely refuted at scale |
| Graph gives easier multi-tenancy | Refined: flat latency vs. tenant count, but 9x slower creation, 4-15x more memory, worse under extreme concurrency | Not a focus of L8 | Real but costly; not a clean win |
| Graph gives easier traversal | Refuted for unbounded/aggregate traversal (25x-900x slower, frequent timeouts) | n.a. | Refuted at the scales tested |
| SQL gives atomic writes | Confirmed for the product's current multi-call write path; refuted as an inherent graph limit (one Cypher statement matches SQL's guarantee) | n.a. | The real gap is in Plexus's write-path implementation, not the backend |
| (implicit) structured memory reduces stale action and rework | n.a. | Refuted in Round A: Plexus underperformed both SQLite and a bare file-based agent on stale-act rate, recall completeness, and token cost | The most important result: the core value proposition is unproven as currently built |

The single most consequential finding across both rounds is the last row. Every mechanism-level property
Plexus was designed around (contradiction edges, provenance edges, validity windows, a staleness subsystem)
exists in the schema and the query layer. L8 shows that having the mechanism does not, by itself, change what
a live agent team does, when the agents are not told the mechanism exists and when the retrieval layer that
feeds the agent's decisions is weaker than naive alternatives. The project's forward work (§5) follows directly
from this: fixing `recall`'s ranking quality and re-running L8 with the staleness tools explicitly in the
agents' hands is higher-value than any further mechanism-level optimization P10 suggests.

## 5. Limitations (combined)

- One machine, one FalkorDB version (6.0.2), one model (Sonnet) for all L8 agent runs, one seed-generation
  scheme per family.
- One author wrote both the Cypher and the SQL across P10, a direct conflict of interest not otherwise
  mitigated.
- L8 Round A used n=5 seeds per arm; the pre-registration itself notes a permutation test at this sample size
  can only reach significance (p=0.008) at zero overlap, and differences under roughly 10 percentage points
  will read as statistical ties regardless of direction. The ordering reported above is directional and
  consistent across robustness variants, not a significance claim.
- No Postgres arm (B3) has been run in either round; it is the most direct way to separate "SQL" from "a
  relational schema with real multi-statement transactions and MVCC," which SQLite's simpler locking model does
  not fully represent.
- B0 (file store with an imposed tool API) was scoped but not run in L8 Round A.
- L8's staleness-subsystem non-use is itself a scenario-design choice (agents were not told the tools exist);
  it is reported as a finding about Round A's design, not a permanent property of Plexus.
- Total LLM spend across this project to date (~$15 notional before L8, plus L8 Round A's ~$17) remains small
  relative to what repeated-measures statistics at the scenario's scale would need.

## 6. What's next

1. Root-cause `recall`'s retrieval-quality gap (the single highest-leverage fix implied by L8) before any
   further benchmark round; re-running L8 against a fixed `recall` is more informative than adding arms.
2. Re-run L8 Round A (or a variant) with the staleness tools explicitly described in the agent briefs, to
   measure the subsystem L8 Round A did not exercise.
3. Round B of L8 (B0, B3/Postgres) only after (1) and (2), per the plan's own cut order.
4. File the reproduced FalkorDB AOF-replay crash (§2.3) upstream or as a tracked internal issue; it is a
   correctness/availability risk for any tenant-deletion-then-restart path, independent of this benchmark's
   conclusions.
5. Fix the product's write path (close-out and any similarly multi-call write) to use the single-statement form
   I5 showed matches SQLite's atomicity guarantee, closing the gap P10 identified as fixable rather than
   structural.

## Appendix: source files

- `docs/research/P10_GRAPH_VS_SQL.md` (pre-registration, amendments 1-4, full results and verdict), branch
  `p10`, head `f708fd6`. Harness: `plexus/src/plexus/crucible/l7/`. Results:
  `plexus/demo_data/crucible/l7/`.
- `docs/research/L8_LONG_HORIZON_OUTCOMES.md` (pre-registration and Round A results/verdict), branch `p11`,
  head `c83488e`. Harness: `plexus/src/plexus/crucible/l8/`. Results: `plexus/demo_data/crucible/l8/`,
  specifically `latest-roundA.json` and `20261016T155630Z-roundA/report.md`.
- `docs/BLOG_SQL_VS_GRAPH.md` -- public-facing narrative version of this report.
