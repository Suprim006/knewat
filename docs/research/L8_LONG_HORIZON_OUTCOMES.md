# P11 / Crucible L8: long-horizon memory under live change, scored on outcomes

Status: **plan and pre-registration, not yet approved for execution.** Written on branch `p11` (base `main`
f96df06) before any L8 code exists and before any L8 `claude -p` call. LLM calls made for L8 before this text: **0**.
Nothing in this document has been measured. L7 is taken by the in-flight P10 branch (graph vs SQL by scale,
`docs/research/P10_GRAPH_VS_SQL.md`), so this layer is **L8**.

Every number below marked *prediction* is a guess written before the run. A tie or a Plexus loss is a valid result
and is published as such (`docs/BASELINE.md` §6). If, after the run, the headline sentence in §12 cannot be filled in
with numbers that favour Plexus, the sentence is filled in with the numbers that came out, and that is the finding.
No re-running "until it looks better": every run is recorded, including aborted and discarded ones, with the reason.

Contents: §1 what L8 asks · §2 what exists and is reused · §3 the scenario · §4 the fault timeline · §5 arms · §6
metrics (one subsection per metric: computation, prediction per arm, why it matters) · §7 what shrinks · §8 run
design and statistics · §9 ground truth and the deterministic scorer · §10 budget · §11 execution order and gates
· §12 headline · §13 limits of this plan, stated up front.

---

## 1. What L8 asks

The report's L3 pilot (`docs/PLEXUS_REPORT.md` §6.7) ran one real 3-agent Claude Code team per arm on a 12-task
scenario. All arms finished 12/12, reclaimed the killed builder's task, surfaced the one contradiction, and
Plexus used ~75% more tokens. n = 1, a scenario small enough that every backend completes it, and metrics that
every competent store ties on. §10 item 2 of the report says what to do: ≥ 5 runs per arm, fixed seeds, a history
that exceeds an agent's context, and the MAST metrics.

**The question L8 answers:**

> Can Plexus store long-horizon memory across sessions, and does it reduce the **stale-act rate** and
> **step repetition** of a real agent team versus the baselines; by how much, and at what token premium?

Not "can the store answer `knew_at`" (L2/L6 showed every competent store ties on that). The unit of measurement is
an **agent action** (an artifact written, a decision recorded, a handoff sent, a task completed), and the question
per action is: *was the fact this action relied on already false when the agent acted, and did the store's design
give the agent a way to find out before it acted?*

Three things change versus L3 to make that measurable:

1. **The ground shifts during the run.** A code repository that the facts are about receives seeded commits of the
   eight L5a edit kinds *while the agents are working* (L5a measured the flagging offline; L8 measures whether
   flagged facts change what agents do).
2. **The history is bigger than the context.** The team's store is pre-loaded with the 20-sprint L2-scale history
   (B0 artifact 532,813 chars, 16.6× the 32k reader budget), and four live tasks need a fact from an old sprint.
   Every turn is a fresh `claude -p` process with `--no-session-persistence` (as in L3), so the *only* memory
   between turns and between agents is the store under test.
3. **Scoring is action-level and deterministic.** Every fact value in the scenario is a unique sentinel token; the
   fault script knows at which turn each sentinel became false; the scorer finds sentinels in tool calls and
   artifact files. No LLM judge anywhere in the headline numbers.

Two comparisons are deliberately separated (§5): **design effect** (P vs B0/B1, which have the status-quo tool
surface and no staleness tools) and **backend effect** (P vs B3, a Postgres backend behind the *same* tool
surface including the staleness tools). If P beats B0/B1 but ties B3, the finding is "the design (anchors +
suspect flags + verify) does the work, the graph does not"; that is a legitimate and expected outcome (§6.1).

---

## 2. What exists and is reused (no new mechanics where old ones work)

| Need | Existing machinery | Where | Reuse |
|---|---|---|---|
| Drive real `claude -p` agents, one process per turn, stream-json transcripts, token/cost per turn | `ClaudeDriver`, `build_command`, `ClaudeConfig` | `plexus/demo/orchestrator.py` | as is, plus a `--tools` change (§3.4) |
| Scheduler with a global step counter, lease-based kill/reclaim, time-based faults at turn boundaries | `World`, `FaultScript`, `run_engine`, `reclaimer_for` | `plexus/demo/engine.py`, `demo/scenario.py` | extend `FaultScript` with a commit schedule and extra kills |
| Baselines behind the Plexus tool names (stdio MCP) | `baseline_mcp.py` over `CoordinationBackend` (B0 files, B1 SQLite, B2 vector) | `crucible/l3/baseline_mcp.py`, `crucible/backends/` | as is for B0/B1; new backend class for B3 |
| Per-arm metrics from transcripts (`tool_use`/`tool_result` blocks), run envelope, report | `transcript_metrics`, `arm_metrics`, `render_l3_report` | `crucible/l3/run.py` | the parser; new metric functions in `crucible/l8/score.py` |
| Scripted repo of 12 modules × 5 functions, 8 edit kinds, AST-computed ground truth per commit, assertion that script edits == AST truth | `build_repo`, `KINDS`, `segments`, `Commit.truth` | `crucible/l5/staleness.py` | the generator, parameterised with domain names and sentinel values; commits applied *incrementally* at scheduled turns instead of all up front |
| Code-change hook into the store | `plexus code scan` / `plexus code hook-git` → `mark_changed`; `commit_groups`, `chunk_entries` | `plexus/codescan/`, `docs/staleness.md` | the git `post-commit` hook in the run's repo (P arm only, by design) |
| 20-sprint history, deterministic ids/clock, per-sprint ledger as ground truth | `play_scale`, `Ledger`, `deterministic` | `crucible/l2/scale_scenario.py`, `l2/scenario.py` | preload into every arm's store before the live sprint |
| Crash harness (SIGKILL mid-write; orphan Step/WROTE count) | family F | `crucible/l6/crash.py` | the *inspection* code (orphans per store), applied to the L8 stores after the L8 kills |
| Hand-written SQL control for provenance questions | B1h, `sqlite_h.py`, `l6/sql_mcp.py` | `crucible/backends/sqlite_h.py` | the B1 schema is the starting point of the B3 Postgres schema |
| Exact-match scoring of LLM readers (reply ends with one JSON object), answer cache | L2-scale / L6 scorer | `crucible/l2/`, `l6/score.py`, `l6/llm.py` | for the cross-cutting questions on the file arms (§6.5) |
| Results envelope with `code_commit`, dirty flag, machine facts | L6/L7 helpers | `crucible/l6/run.py`, p10 `l7` helpers once merged | as is |

New code, all under `plexus/src/plexus/crucible/l8/` (estimated 1,200–1,800 lines, written *after* this plan is
approved): `scenario.py` (the S21 task graph and briefs, sentinel table), `repo.py` (L5a generator with domain
names, incremental commits), `faults.py` (seeded schedule), `arms.py` (B0′ driver without MCP, B3 backend),
`score.py` (the deterministic scorer, §9), `run.py`, `audit.py` (end-of-run cross-cutting questions and the
query-authoring probe).

---

## 3. The scenario: "Acme Notes API, sprint 21, with a repo that moves"

### 3.1 Shape

* **Team:** the same three roles (planner, researcher, builder), the same `common.md` conventions (one change,
  §3.4), the same Sonnet model, the same `--max-turns 25` per process.
* **History:** the L2-scale K = 20 sprints (S01–S20) played into the arm's store before turn 1, by the existing
  `play_scale` through the arm's `CoordinationBackend` (P: the Plexus backend; B0/B1: as today; B3: the new
  backend; B0′: rendered as the B0 files *as markdown memory* in the agents' working directory, §5.3). The L2-scale
  ledger is the ground truth for the four history-dependent tasks.
* **Live sprint S21:** 16 tasks (the 12 of `demo_data/acme/tasks.json` with their roles and DAG kept, plus 4 new,
  §3.2), one mid-run extra task (`t12-update-endpoints-for-v2`, as today), two specials (`ingest-v2`,
  `adopt-v2`, as today). Each task produces 1–3 **named artifact files** under `workdir/artifacts/<task>/`
  (`spec.md`, `schema.md`, ...) whose required content is a list of sentinel tokens (§3.3). Tasks that in L3 only
  attached an artifact *summary* now also write the file; `complete_task` still attaches it.
* **Repository:** `workdir/repo/`, generated by the L5a generator with domain names: 12 modules (`auth.py`,
  `api.py`, `db.py`, `ratelimit.py`, `notes.py`, `users.py`, `search.py`, `export.py`, `billing.py`, `audit.py`,
  `config.py`, `release.py`) × 5 functions, each `def name(): return SENTINEL` with a docstring. 60 functions, 60
  facts of the form `(Acme Notes API S21, <module>.<function>, <sentinel>)`. The initial commit is made before turn
  1 with `GIT_AUTHOR_DATE` from the deterministic clock.
* **Length:** 16 + 1 tasks, 2 specials, 3 kill/reclaim cycles → about **24–26 turns** per run (L3: 16),
  about 140–180 MCP calls (L3: 82) plus `Read`/`Write` calls.

### 3.2 The four new tasks

| Task | Role | Depends on | Needs | Why it is there |
|---|---|---|---|---|
| `t13-reuse-billing-cycle` | planner | t02 | the billing cycle decided in sprint **S07** and the API-key header decided in **S13** (from the L2-scale ledger) | long-horizon recall across sessions: the answer is 14 sprints back, not in any prompt |
| `t14-ratelimit-spec` | researcher | t04 | 5 sentinels from `ratelimit.py` + the decision in S03 that chose the rate-limit window | code facts that will be invalidated mid-run (§4) |
| `t15-config-matrix` | builder | t06, t14 | 8 sentinels across `config.py`, `db.py`, `auth.py` | the task with the most exposure to commits; its artifact is where stale acts are expected |
| `t16-release-notes` | researcher | t09, t13, t15 | every sentinel the previous artifacts used, plus the S20 release channel | a late task that inherits staleness through artifacts (does a stale value propagate?) |

Briefs are frozen before the first paid call (prompt version `l8-v1`) and are identical in every arm.

### 3.3 Sentinel tokens (the thing that makes scoring deterministic)

* Every fact value in S21 is a token `AX-<5 digits>` (e.g. `AX-40123`), unique across the repo, the task
  briefs and the 20-sprint history (the history generator's values are checked at build time to contain no
  `AX-` token; the build fails if one collides).
* Each function's initial value and every revision of it are distinct tokens: `(module, function, commit_k) →
  token`, recorded in `sentinels.json` before the run. A revision commit changes the function's return value to the
  next token.
* An **action uses a fact** when the text of the action (an artifact file written with `Write`/`Edit`, the `text`
  of `record_decision`, the `note` of `handoff`, the `summary` of a `complete_task` artifact, or the `value` of an
  `assert_fact`) contains the fact's token. Since tokens are unique, no NLP is involved: string containment.
* **Stale at time t** = the token's function was revised or deleted by a commit that landed before t (§4) and the
  token is not the current one.

Tokens are opaque on purpose: an agent cannot reason its way to the current value, it has to *read* it (from the
code or from the store), which is exactly what the metric is about.

### 3.4 Tools the agents have (identical across arms, one departure from L3)

L3 agents had `--tools ""` (MCP only). L8 agents need to read code and write artifacts, so **every arm** runs
`--tools "Read,Write,Edit,Glob,Grep"`, confined by Claude Code's working-directory rule to `workdir/` (the repo
and the artifacts folder). `Bash`, `WebFetch` and `WebSearch` stay off. `common.md` is edited accordingly:
"You may read the repository under `repo/` and write artifacts under `artifacts/`; the code may change during the
sprint." That sentence is the *only* staleness hint any arm gets and it is the same in every arm. Arms with MCP
add `--allowedTools mcp__plexus__*` as today; B0′ has no MCP server at all.

The step counter (the `step` argument the prompts ask for) exists only in MCP arms. Therefore **all schedules in L8
are keyed to turn boundaries** (one turn = one `claude -p` process), which exist in every arm, not to the MCP step
counter. The MCP step counter is still recorded where it exists.

---

## 4. The fault timeline (seeded; identical across arms for the same seed)

Seed for run r (r = 1..5): `20261016 + r`. `random.Random(seed)` draws the schedule once, before any arm runs;
the schedule is written to `schedule.json` and every arm of run r replays it.

### 4.1 Commits (the L5a edit kinds, landed live)

* **10 change commits per run**: one of each of the 8 kinds (`value`, `sibling`, `docstring`, `add`,
  `module-comment`, `whitespace`, `reorder`, `delete`) plus 2 extra `value` commits (so there are enough
  fact-invalidating changes: `value` 1–3 functions, `sibling` 2, `delete` 1 → **5–11 invalidated facts per run**;
  `docstring` 1 flagged-but-still-true fact; the other four kinds are decoys that flag nothing at symbol level).
* **Function selection** is biased, not uniform: 70% of invalidating edits hit functions listed in the `needs` of
  a task not yet complete at scheduling time (so the stale fact *can* be acted on), 30% hit any live function (so
  not every flag matters). The schedule records which.
* **When:** commits land at turn boundaries drawn without replacement from turns **4..18** (so every commit lands
  after at least one fact-recording task has run and before the last three tasks). The harness commits in
  `workdir/repo/` with the deterministic author date, *between* two `claude -p` processes, never during one.
* **How an arm can notice (this is the design under test):**
  * **P:** the repo has the product's `post-commit` hook (`plexus code hook-git --repo workdir/repo --tenant
    <run tenant>`), so each commit runs `plexus code scan` → `mark_changed` with old/new symbol hashes. Facts the
    agents anchored (`anchor_fact(fact_id, path, symbol)`; the harness runs one baseline `plexus code scan` before
    turn 1 so the CodeAnchor nodes carry hashes) become `suspect`; the next `recall` returns them with
    `verify_state: suspect` and the change reason; `facts_to_verify` lists them. Nothing tells the agent to call
    these; the role prompt is the same as for every other arm. If the hook fails to fire in a run, the harness
    records it and the run is discarded and re-run with the same seed (a harness fault, not a result).
  * **B3:** the same hook payload is delivered to the B3 `mark_changed` (the SQL implementation, §5.5).
  * **B0, B1:** nothing. The agents' only route is to re-read `repo/` or notice a changed value in a document.
    The baseline MCP has no `anchor_fact`/`mark_changed`/`verify_fact`, as today (and that is the honest
    "status quo tool surface").
  * **B0′:** nothing. Native Claude Code: re-read the file or trust memory.
* **What is *not* done:** no `PostToolUse` hook (agents do not edit `repo/`), no prompt line saying "a commit just
  landed". If an agent never re-reads and never recalls, it never notices; whether the store's design makes
  noticing routine or lucky is the question.

### 4.2 Kills (crash points for provenance completeness and recovery)

* **K1**: the builder, as in L3: the first time it holds a task and has made ≥ 1 call on it at or after turn 6
  (lease 3,000 ms → the researcher reclaims). The kill is a `TerminateProcess` of the `claude` process mid-turn.
* **K2**: the researcher during `t14` or `t16` (whichever it holds first at or after a seeded turn in 10..16),
  killed **immediately after its first `Write` of an artifact file** (the harness watches the stream-json for the
  `Write` tool_use and kills on the next event). This is the kill that tests *recovery correctness* (§6.8): one
  unit of work is finished on disk, the task is not.
* **K3**: the planner once, at a seeded turn in 8..20, after its first MCP write of the turn (P/B0/B1/B3) or its
  first `Write` (B0′). Tests provenance completeness (§6.7) on a write-heavy role.
* The reclaim prompt is the existing one ("this task was abandoned by X; write ONE remember_episode; do the task").
  B0′ has no lease; the harness waits the same 3,000 ms and reassigns (§5.3).

### 4.3 Contradictions (scripted pairs)

* **X1** (existing): planner and researcher assert conflicting auth methods in `t05` (JWT vs API key).
* **X2** (new): `t14`'s brief hands the researcher an old sprint document that says the rate-limit window is token
  `AX-3xxxx` (the S03 value); `ratelimit.py` says a different token. Both get asserted by different agents (the
  builder asserts the code value in `t15`). Write-time `CONTRADICTS` should fire on the second assertion in arms
  that implement it.
* **X3** (new, after a commit): a `value` commit changes `auth.token_ttl`; the builder, if it re-reads, asserts the
  new token while the old fact is live. In P this is a supersede-through-verify, not a contradiction; in B0/B1
  it may surface as a contradiction (same subject/predicate, different value). Scored under §6.4 as "two live
  conflicting values".

### 4.4 The v2 style guide (kept)

`publish_v2` at the first boundary at or after turn 12 (L3: step 20), with its `ingest-v2`/`adopt-v2` specials and
`t12`. It is a *document* change, not a code change, so it tests the non-hook path to noticing in every arm.

---

## 5. Arms

| Arm | Backend | Tool surface the agents see | Staleness tools | Status |
|---|---|---|---|---|
| **P** | FalkorDB graph per tenant via `plexus-mcp` (audit mode `full`) | all 45 Plexus tools | yes (product) | required |
| **B0** | Markdown + JSON files, `flock` + atomic replace (`backends/files.py`) via `baseline_mcp` | the 12 scenario tools, same names/args | no | required (first cut candidate, §10) |
| **B0′** (new) | Claude Code's native memory: files it writes itself | `Read,Write,Edit,Glob,Grep` only; **no MCP server** | no | required |
| **B1** | SQLite + transactions (`backends/sqlite.py`) via `baseline_mcp` | the 12 scenario tools | no | required |
| **B3** (new) | **Postgres 16** in a container, same tool API as P (incl. staleness, `why`, `who_knew`, `impact`) | the Plexus tool names the scenario uses + the 7 staleness tools + 3 lineage tools | yes (SQL re-implementation) | required for the backend-effect comparison; runs after P/B1/B0′ (§11) |
| **H** (optional) | Hermes native memory (`MEMORY.md` 2,200 chars) | n/a | no | **not run**; feasibility computed and reported (§5.6) |
| B2 vector | — | — | — | not run (weakest in every prior layer; §9.2 of the report) |

### 5.1 P

The product as of the commit recorded in `results.json`. Tool output size is whatever the product returns at that
commit; if §10 item 3 of the report ("slim the tool output") lands before the run, it is noted, but the run does
**not** wait for it. The P agents are not told about `anchor_fact`; the tool descriptions are the product's own.
Prediction: Sonnet will anchor some facts and not others; the share of facts anchored is reported as a
mediating variable (§6.2).

### 5.2 B0 and B1

Unchanged from L3 (`baseline_mcp.py`): same 12 tool names, write-time contradiction check in the backend (the pilot
showed all three arms surfaced X1 at write time), BM25/grep recall. They have no `anchor_fact`, `verify_fact`,
`why`, `who_knew`. For the end-of-run audit (§6.5) B1 gets hand-written SQL (B1h style); B0 gets the L2-style
32k BM25 reader.

### 5.3 B0′: unmodified Claude Code managing its own memory files

What people actually do today. Operationally:

* **No MCP server, no imposed schema.** The working directory starts with `CLAUDE.md` (the role conventions, same
  content as `common.md` but phrased for files: "shared team memory lives in `memory/`; read it before you act;
  write what the team should remember"), an empty `memory/` directory, the `repo/`, and `history/` = the 20-sprint
  B0 artifact (532k chars of markdown: facts, decisions, handoffs, logs) exactly as the L2-scale B0 arm writes it.
  No `flock`, no atomic replace, no ids handed out by a tool: whatever Claude Code does with `Write`/`Edit` is the
  behaviour.
* **Coordination without a shared tool.** There is no `claim_next_task`. The harness is the "lead" that a Claude
  Code agent-team or a human would be: it assigns each turn's task in the prompt (it knows the DAG, as it does in
  every arm, `scenario.task(tid).depends_on`) and asks the agent to record completion in `memory/tasks.md` in any
  form it likes. **The harness decides a task is done when the required artifact files exist** (§3.3), not by
  parsing the agent's memory file; so B0′'s DAG progression is harness-mediated and does not depend on the agent's
  bookkeeping. Whether the agent's own `tasks.md` agrees with the artifacts is itself a metric (§6.3 C-signatures).
* **Concurrency.** Turns are sequential in every arm (the scheduler runs one `claude -p` at a time; L3 did too),
  so B0′ is not exposed to write races. This is stated as a limit: B0′'s missing `flock` is never exercised here.
  L1's concurrency results (B0 with `flock` vs without) stand separately.
* **Kills and reclaim.** Same kill points; the reclaim prompt says "builder was interrupted while on `t15`; check
  `memory/` and `artifacts/` and finish it". No lease exists, so "lease wait" is a fixed 3,000 ms sleep.
* **If it cannot work** (e.g. the agent overwrites `memory/facts.md` with a fresh file every turn, loses the
  history, or `tasks.md` drifts so far that the agent redoes done work): that is the finding, reported with the
  transcripts, not patched with structure. Pre-registered expectation: it works, badly: completion ≥ 14/17 tasks,
  stale-act rate the highest of all arms, provenance 0 (no concept).

### 5.4 B1 (SQLite) stays; B3 is the "SQL with real transactions" arm

### 5.5 B3: Postgres with the same tool API as Plexus

* **What is realistic:** a `postgres:16-alpine` container (`docker run -p 5433:5432`, ~1 minute to stand up; the
  owner already runs Postgres containers for another project). No pgvector in L8: recall in B3 is BM25 over
  `tsvector`/`ts_rank` (built in), the same class of retrieval B1 has; a pgvector arm is a different question
  (§10 item 1 of the report) and is out of scope.
* **Schema:** the B1 schema (`backends/sqlite.py` + the B1h `claims`/`step_reads` additions) ported to Postgres
  with real `BEGIN ... COMMIT`, `SELECT ... FOR UPDATE SKIP LOCKED` for claims, a `code_anchors` table
  `(fact_id, path, symbol, hash)`, `fact_state` (`active|suspect|superseded|...`), `changes`, and `steps`/`wrote`/
  `read` rows written in the same transaction as the memory write (so provenance completeness is 100% by
  construction, as B1h was in L6-F).
* **Tool surface:** `baseline_mcp.py` gains an arm `B3` registering, in addition to the 12 scenario tools,
  `anchor_fact`, `mark_changed`, `verify_fact`, `facts_to_verify`, `why`, `who_knew`, `impact`, with the Plexus
  argument names (pinned to `tests/mcp/snapshots/tools.json` as the others are). Each is a hand-written SQL
  statement or recursive CTE, written by one author before the first paid call, line counts recorded.
* **What it settles:** whether P's result on stale-act rate (if any) survives when a relational store has the
  *same* design (anchors, suspect state, verify). If P ≈ B3 ≫ B0/B1, the design wins and the graph is not the
  reason; if P > B3 with the same tools, something about the graph path (e.g. `why`/`impact` output the agent
  used) mattered, and the transcripts should show which tool call made the difference. It also removes L4's
  "in-process vs container" asymmetry for one baseline: B3 is across a container network like FalkorDB.
* **Build cost:** about one subagent-day (schema port ≈ 400 lines, 10 new tool handlers ≈ 300 lines, contract
  tests). If the B3 build is not green by the time P/B1/B0′ have run, B3 runs in a later round (§11) and the
  report says so.

### 5.6 H: Hermes native memory (optional; expected structurally impossible; not run)

Hermes memory is one global `MEMORY.md` capped at **2,200 characters** plus `USER.md` at 1,375 (report §1.2),
per profile. For a 3-agent team the only sharing is one profile's file, so three agents would read and rewrite the
same 2,200 characters.

Feasibility, computable before any run:

* The 20-sprint history is 332,599 chars as B1 CSV and 532,813 as B0 markdown: **151–242× the cap**. It cannot be
  stored. The arm would start with no long-horizon memory, which decides `t13`/`t14`/`t16` (history-dependent)
  before the run: 0/3 by construction.
* The live sprint alone: 60 code facts × ~45 chars (`auth.token_ttl=AX-40123`) = 2,700 chars > cap, before any
  task state, decision or handoff. So even S21 alone does not fit.
* Hermes is excluded from published runs by D-003 (credential terms), independent of the cap.

**Decision:** H is **not run**. The report gets one paragraph with the arithmetic above as a finding ("the 2,200-
character design makes a 3-agent, 21-sprint memory structurally impossible: the history is 151–242× the cap and
the live sprint's facts alone exceed it"). An *emulation* arm, B0′ with a 2,200-char cap on `memory/*.md` enforced
by a `PreToolUse` hook rejecting larger writes, is listed as **optional** and runs only if every required arm has
run and ≥ $8 of the cap remains. It would show what an agent does under the cap (prediction: it summarises,
loses the sentinels, stale-act rate ≥ B0′), but it is not Hermes and is labelled "cap emulation under Claude Code".

---

## 6. Metrics

Conventions for every metric: computed by `crucible/l8/score.py` from (a) the per-turn stream-json transcripts,
(b) the final `workdir/` (artifact files, `repo/` git log), (c) a dump of the arm's store, and (d) the pre-run
ground truth (`schedule.json`, `sentinels.json`, `tasks.json`, the L2-scale ledger). Same code for every arm.
Where an arm has no concept for a metric, the cell says `n/a (no <concept>)` and is not scored 0 silently.

Statistics (§8): per arm, pooled action-level rate with a Wilson 95% interval, the five seed-level values (min,
median, max), and for the two headline metrics an exact two-sample permutation test on the five seed-level rates
(P vs each baseline). "Separated" means the seed-level ranges do not overlap **and** the permutation p ≤ 0.05.
Anything else is reported as a tie. With n = 5 per arm the smallest possible two-sided p is 2/252 = 0.0079, so a
real separation can reach significance; a paired sign test on 5 seeds cannot (min p = 0.0625) and is not used.

### 6.1 Stale-act rate (headline)

**Computation.**
* **Scored actions** = tool_use events of `complete_task` (its artifacts' summaries), `record_decision` (`text`),
  `handoff` (`note`), `assert_fact` (`value`), and `Write`/`Edit` whose path is under `artifacts/`, that contain
  **at least one** sentinel of a tracked function. Actions that mention no sentinel are not in the denominator.
  Each action is time-stamped by its turn index and, within a turn, by event order.
* An action is **stale** if any sentinel it contains was invalidated by a commit that landed at a turn boundary
  strictly before the action's turn, and the action does not also contain that function's current sentinel
  (an action that quotes both old and new, e.g. "changed from AX-40123 to AX-41007", is **current**).
* An action is **current** otherwise.
* `stale_act_rate = stale / (stale + current)`; also **dependent-only** rate: restricted to actions of tasks whose
  `needs` list the function (the rate that would matter to a reviewer), and **propagated** rate: actions in `t16`
  (release notes) that copied a stale token from an earlier artifact.
* Also reported: **stale facts live in the store at end of run** (facts in the store whose value is a stale
  sentinel and not superseded/suspect/closed), which is what the next sprint would inherit.

**Prediction per arm (stale / scored actions, pooled over 5 seeds):**

| Arm | Predicted stale-act rate | Reasoning |
|---|---|---|
| P | **5–15%** | suspect flags arrive in `recall` output without being asked for; agents verify some but not all; unanchored facts are never flagged |
| B3 | **5–15%, tie with P** | same design; the backend does not change what the agent sees |
| B1 | 20–40% | no signal; noticing only by re-reading code, which the prompt allows but nothing prompts |
| B0 | 20–40%, **tie with B1** | identical tool surface, identical absence of signal |
| B0′ | 25–50% | same absence, plus memory files that may be rewritten without the new value |

**Decision rule.** The design effect is "shown" if P and B3 are each separated from each of B0 and B1 (both
headline tests pass). The backend effect is "shown" only if P is separated from B3; **I predict it is not** and
that the published sentence will say "the design, not the graph". If P is not separated from B1, the headline
(§12) reports no reduction; the stale facts left in the store at run end become the secondary comparison.

**Why a judge cares.** This is the MAST "proceeding on wrong assumptions" failure, measured as a share of real
actions by an unmodified agent, with a known fault timeline. No prior layer has it.

### 6.2 Time-to-notice

**Computation.** For each invalidating commit c (kinds `value`, `sibling`, `delete`) and each invalidated function
f, two latencies in **turns** (and, in MCP arms, in global steps):
* **Surfaced (level 1):** the first turn ≥ T_c in which any agent (i) receives a tool result containing f's fact
  with `verify_state: suspect` or `change_id` (P, B3), or (ii) `Read`s the file containing f (any arm), or (iii)
  receives a recall/grep result containing the *new* sentinel (any arm).
* **Acted on (level 2):** the first turn ≥ T_c in which any agent writes the new sentinel into the store
  (`verify_fact` with `new_value`, or `assert_fact`, or a memory file write in B0′) **or** into an artifact.
* Right-censored at the last turn; censored cases are reported as a count, and the median is over all cases
  with censored = ∞ (so a median of ∞ is a valid, reportable value).
* **False-alarm cost (P, B3 only):** number of `verify_fact(still_true=true)` calls and `facts_to_verify` calls
  triggered by the `docstring` commit (flagged, still true) and their token cost; the decoy kinds (`add`,
  `module-comment`, `whitespace`, `reorder`) must flag nothing at symbol level (L5a says 100% precision; a flag
  here is a product bug and is reported).

**Prediction.** P and B3: level-1 median **≤ 1 turn** (the next `recall` by anyone), level-2 median 1–3 turns,
censored ≤ 20% (the unanchored facts). B0/B1/B0′: level-1 median ≥ 4 turns with **≥ 50% censored** (agents mostly do
not re-read code they already recorded), level-2 censored ≥ 60%. Tie between B0, B1 and B0′ expected. The
`docstring` false alarm costs P/B3 one verify call per run (≈ 2–5k tokens).

**Why a judge cares.** "Memory that notices change" (report §7) was shown offline; this is the first measurement
of whether an agent *in the loop* notices sooner because of it.

### 6.3 MAST failure rates (operationalised for this scenario)

Each signature is a deterministic transcript/filesystem check. Rates are per scored action (same denominator as
§6.1 for R/M signatures) or per task (C signatures).

**Step repetition** (Cemri et al. 15.7% of failures):
* **R1** `complete_task` called for a task whose earlier `complete_task` succeeded (any agent, any turn). B0′: a
  second "done" entry for the same task in `memory/tasks.md`.
* **R2** `assert_fact` with the same `(subject, predicate, value)` as one already acknowledged in this run (agent-
  side attempts; whether the store deduplicates is recorded separately as "store absorbed").
* **R3** `Write` of an artifact file that already exists with the same required sentinels (a rewrite of finished
  work), excluding the reclaim turn's legitimate re-check (an `Edit` that only appends is not R3).
* **R4** the same `Read` path ≥ 3 times within one turn with no intervening `Edit` (wasted reads; reported, not in
  the headline rate).
* `step_repetition_rate = (R1 + R2 + R3) / scored actions` (headline); R4 per turn alongside.

**Missing completion recognition** (12.4%):
* **C1** work on a task after it is done: any `Write` under `artifacts/<task>/` or `claim`/`heartbeat` on a task
  whose `complete_task` succeeded earlier (not by the reclaimer on a reclaimed task).
* **C2** false completion: `complete_task` acknowledged while a required artifact file is missing or lacks a
  required sentinel (the harness does not block it; the scorer counts it).
* **C3** unrecognised completion: a turn ends with every required artifact of the task present and no
  `complete_task` (B0′: no done entry), so the scheduler re-issues the task next turn.
* `missing_completion_rate = (C1 + C2 + C3) / tasks attempted` (17 per run).

**Reasoning–action mismatch** (13.2%), narrow and deterministic by design:
* **M1** an assistant text block in the turn contains the new sentinel of f (the agent "knows") and a later action
  in the same turn uses f's stale sentinel (the agent acts on the old one).
* **M2** `record_decision` whose `text` contains the sentinel of fact x but whose `based_on_fact_ids` does not
  include x's id (mapped through the store dump); B0′: `n/a (no decision object)`.
* **M3** `handoff` whose `note` contains a sentinel but whose `fact_ids` is empty.
* `mismatch_rate = (M1 + M2 + M3) / scored actions`.
* Honesty: M1–M3 cover a *subset* of what Cemri et al. label reasoning–action mismatch (they used human/LLM
  annotation). The plan does not claim to measure the taxonomy category; it measures three signatures of it that
  can be checked without a judge, and says so in the results.

**Predictions.**

| Signature | P | B3 | B1 | B0 | B0′ |
|---|---|---|---|---|---|
| step repetition (R1–R3) | 2–8% | tie with P | tie with P | tie with P | **10–25%** |
| missing completion (C1–C3) | ≤ 2/17 | tie | tie | tie | 3–6/17 |
| mismatch (M1–M3) | 3–10% | tie | tie | tie | M2/M3 n/a; M1 tie |

I expect **ties among all four tool arms** on all three: the tool surface (claims, versions, `complete_task` with
`expected_version`) imposes the same structure, and the L3 pilot showed identical counts. The only predicted
separation is B0′ vs the rest on repetition and completion, because it has no claim, no version and no
`complete_task`. If P separates from B1 on repetition, I will look for the mechanism in the transcripts (e.g.
`recall` showing the artifact already exists) before claiming it, and say if none is found.

**Why a judge cares.** These are the top three MAST failure modes by share; §1.3 of the report cites the numbers
and no layer measures them yet.

### 6.4 Contradiction detection latency

**Computation.** For X1, X2, X3 (§4.3): the turn (and step) of the second conflicting assertion, and the first
turn at which the conflict is **surfaced**: a tool result with `contradicts` (P, B1, B0, B3: write time), or any
later tool result or memory-file read that returns both values to one agent, or an agent text/decision that
names both sentinels. Latency in turns; `never` if not surfaced by run end. Also: **resolution**: was one of the
two values superseded/closed/removed by run end, and did any post-conflict action use the losing value.

**Prediction.** X1 and X2: **0 turns in P, B0, B1, B3** (write-time check exists in all four; the pilot showed it),
**never or ≥ 3 turns in B0′** (no check; only if an agent reads both lines). X3 (post-commit): in P/B3 it is a
supersede via `verify_fact` and is scored as "resolved at write time"; in B0/B1 a write-time contradiction (0
turns) but **no resolution** (both values stay live) in ≥ 3 of 5 seeds. Tie expected among P/B0/B1/B3 on latency;
the separating number, if any, is *resolution*.

### 6.5 Cross-cutting questions (end-of-run audit)

Asked once per run, after the last turn, against the arm's final store. Three questions, ground truth from the
L2-scale ledger + the run's own scorer output:

* **Q1** "Which decisions, across all 21 sprints, relied (directly or through a handoff-carried fact) on the API
  style guide v1 family of sources?" Answer: set of decision ids (L2-scale: deterministic per sprint; S21: from
  the transcripts' `record_decision` calls whose `based_on` resolve to such facts). Scored as count + 10
  membership probes (5 in, 5 hard negatives from the v2 family) + the 5 earliest, strict as in L6.
* **Q2** "Which agents read a fact that was later invalidated by commit c* (the run's first `value` commit)?"
  Truth: agents whose transcript shows a tool result or file read containing the old sentinel before T_c*.
* **Q3** "Which S21 tasks completed with an artifact that used a fact already stale at completion time?" Truth:
  the scorer's own stale-act list for `complete_task` actions (§6.1).

**How each arm answers (deterministic where the arm allows, $0):** P: `why`/`impact`/`who_knew` plus one Cypher
statement for Q3 (no product tool answers Q3 directly; the statement is written before the run). B1, B3: hand-
written SQL (B1h style, written before the run). B0: the L2-style tool-less reader (`claude -p`, 32k BM25 context,
one JSON answer, cached), **one LLM call per question per seed** = 15 calls. B0′: the same reader over
`memory/` + `history/`. These readers are the arm being scored, not a judge; scoring is exact match.

**Prediction.** P 3/3 and B1/B3 3/3 on all 5 seeds (**tie**, as L6 found). Q2 depends on the store having READ
provenance: P and B3 have it; B1's `step_reads` only if the baseline MCP recorded reads (it does for `recall`), so
B1 ≈ 3/3 too. B0 ≤ 1/3, B0′ ≤ 1/3 (Q2 needs read provenance that files do not keep; Q1 needs 21 sprints in 32k).
What L8 adds over L6 is Q2/Q3 against a *live* run's provenance rather than a generated ledger.

### 6.6 Tokens per correct action (fixes the §6.7 critique)

**Computation.** `tokens_per_correct_action = total tokens of the run / correct actions`, where a **correct action**
is a scored action (§6.1) that is current (not stale), not a repetition (R1–R3), and, for `complete_task`, not C2.
Reported twice: **raw** (all four token classes summed, as L3 did) and **billing-weighted** (cache reads × 0.1,
cache writes × 1.25, as the API prices them; the L3 pilot's tokens were 94% cache reads, so the raw ratio
overstates the cost gap). Also tokens per *scored* action and the cost (`total_cost_usd`) per correct action.

**Prediction.** P raw tokens 1.4–1.9× B1 (L3: 1.75×); per **correct** action **1.1–1.6× B1** if the stale-act
reduction materialises (more correct actions per run), 1.4–1.9× if it does not. B3 ≈ P (same tool output volume).
B0′ lowest per action, highest per correct action if its stale/repetition rates are as predicted. **Success
criterion stated now:** P ≤ 1.5× B1 per correct action is "a premium worth the reduction"; > 2× is published as a
loss on cost regardless of the stale-act result.

### 6.7 Provenance completeness after kills

**Computation.** After the run, for each write the transcripts show as **acknowledged** (a non-error tool_result
for `assert_fact`, `record_decision`, `handoff`, `verify_fact`, `complete_task`; B0′: a `Write`/`Edit` to
`memory/` that returned success), check the store for the provenance record: P: a `Step` with `WROTE` to the
node; B1/B3: the `steps`/`wrote` rows; B0: the per-agent log line with the id; B0′: `n/a (no provenance model)`.
`provenance_completeness = writes with record / acknowledged writes`, overall and in the **kill turns** (the turns
of K1–K3), which is where L6-F found the gap. Lost acknowledged writes (acknowledged, absent from the store) are
listed separately. The L6-F inspection code is reused.

**Prediction.** P: 100% for `assert_fact`/`record_decision`/`handoff` (L6-F fix: 0 of 1,842), **< 100% possible for
`verify_fact` and `complete_task`** in kill turns (report §9.3: their step links are written after the write).
With 3 kills per run × 5 seeds = 15 crash windows the expected count of lost links is 0–2 per arm; the rule-of-three
bound (≤ 3/n) is printed for zeros. B1, B3: 100% (one transaction). B0: ≥ 99% (log line after the write; a kill
between them loses it). B0′: n/a.

### 6.8 Recovery correctness (deterministic, from the task graph + transcript)

**Computation.** For K1 and K2 (a task interrupted after ≥ 1 unit of work): the units of work are the task's
required artifact files; a unit is **finished before the kill** if the file exists with its required sentinels at
the kill. The reclaiming agent **repeats** a finished unit if it `Write`s that file again (replacing content;
an `Edit` that only appends, or a `Read`, is not a repeat) or re-asserts facts the dead agent already asserted
(R2 attributed to the reclaim turn). Per kill: `repeated_units / finished_units`, plus **recovered**: the task's
`complete_task` succeeds by run end with all artifacts present, and the turns from the kill to that.

**Prediction.** All MCP arms recover 15/15 kills (L3 showed it). Repeat rate: P, B3 **≤ 20%** of finished units
(the reclaim result and `recall` show the artifact exists); B1, B0 **tie with P** (the reclaim prompt and
`claim_next_task`'s `reclaimed_from` are the same; the store difference is whether the dead agent's artifact is
findable, and `recall` finds it in all MCP arms); **B0′ ≥ 50%** (no claim record; the agent sees a half-done
folder and tends to restart). Honest expectation: a tie among the tool arms.

### 6.9 Query-authoring cost (Cypher vs SQL, same AI, cold)

**Computation.** For a **new** question family not covered by any existing query file, Q4: "for each S21 task,
list the facts it used that were stale at the time and the commit that invalidated them" (the stale-act query as
a store question), plus Q1 and Q2 as above. One `claude -p` Sonnet process per (language, question, repetition),
fresh directory, given only the schema document (`docs/graph-model.md` for Cypher; the B3 DDL for SQL) and the
question, asked for one statement. **3 repetitions × 3 questions × 2 languages = 18 calls**, the same prompt
template for both. Recorded per statement: non-blank lines, whether it runs (syntax), whether it is exact against
ground truth, and the number of **fix iterations** needed (≤ 3, each a further call with the error message). A
**defect** = a syntax error, a wrong result, or a timeout at 5 s. Statements are run by the harness, not judged.

**Prediction.** Lines: within ±30% of each other (**tie**). Defects: **no direction predicted**; Sonnet has seen far
more SQL than Cypher, so SQL may have fewer first-try syntax errors, while the traversal questions (Q1 with
handoff-carried facts, Q4 with time comparison) may need recursive CTEs that take more iterations. Either
direction is published. This is 18 cheap calls (≈ $1–2) and it is the only place where "easier to write" is
measured rather than asserted.

---

## 7. What shrinks (not deleted, right-sized)

* **L4 latency:** one footnote on the L8 results: "median `claim_next_task` latency in this run: P x ms (container),
  B1 y ms (in-process), B3 z ms (container)". No table. The L4 section of the report stays as is.
* **L1 claims/leases:** a **regression gate** that must pass on the L8 code commit before any paid call
  (`crucible-l1 --quick` C1/C2/C4 on P, B1, B3: 0 double claims, 0 lost updates, 0 early starts). Reported as
  "gate passed at commit X" in one line; a failure blocks the run.
* **Forgetting:** one line in the L8 results: "forgetting on at floor 0.9 (the P7 default) in the P arm; no L8 metric
  depends on it; see `docs/BASELINE.md` L5b." B3 has no activation ranking; the line says so.

---

## 8. Run design and statistics

* **5 seeded runs per arm**, seeds `20261017..20261021`. A seed fixes: the fault schedule (§4), the function
  selection, the kill turns, the history (the L2-scale generator is already deterministic). It does **not** fix the
  model's sampling (`claude -p` has no seed), which is the noise the 5 runs exist to measure.
* **Same everything** across arms: prompts (version `l8-v1`, frozen at the commit in `results.json`), briefs,
  model id, `--max-turns`, tools, schedule. Only the MCP server (or its absence) and the hook differ.
* **Run order:** for each seed, arms in a fixed rotation (seed 1: P, B1, B0′, B0, B3; seed 2: B1, B0′, B0, B3, P;
  ...) so time-of-day/model-version drift is not confounded with arm. The `claude` binary version and the model
  id string are recorded per process; if either changes mid-campaign the report says at which run.
* **Statistics** (§6 preamble): pooled action-level rates with Wilson intervals; five seed-level values shown; exact
  permutation test on seed-level rates for the two headline metrics (stale-act, step repetition) for P vs B1, P vs
  B0′, P vs B3; everything else descriptive. Ties are declared by the pre-stated rule, not by eye.
* **Discarded runs:** a run is discarded only for a harness fault (hook did not fire, scheduler stuck, `claude`
  crashed with a non-model error, permission denial from a misconfigured tool list) and is logged in
  `discarded.json` with its cost; the same seed is re-run. A run where the agents simply did badly is never
  discarded. Discarded runs count against the budget.
* **Caching:** `claude -p` agent turns are not cacheable (state-dependent). The audit readers (§6.5) and the
  query-authoring calls (§6.9) are cached by content hash as in L2/L6.

---

## 9. Ground truth before any run, and the scorer

**Exists before the first paid call, committed with the harness:**

| Artifact | Produced by | Content |
|---|---|---|
| `sentinels.json` | `l8/repo.py` | `(module, function) → [token at commit 0, token at revision 1, ...]`; `delete` marks a terminal revision `null` |
| `schedule.json` per seed | `l8/faults.py` | commit k: turn, kind, edited functions (checked against the AST truth as L5a does, build fails on mismatch); kill turns and conditions; `publish_v2` turn |
| `tasks.json` (S21) | `l8/scenario.py` | 17 tasks: role, DAG, `needs` (functions), required artifacts with required sentinels per artifact |
| `history_ledger.json` | `l2/scale_scenario.play_scale` | the 20-sprint ledger: decisions, sources, facts per sprint (for Q1, t13, t14, t16) |
| `conflicts.json` | `l8/scenario.py` | X1–X3: the two values, the two agents, the tasks in which they are asserted |
| `audit_truth.json` | `l8/audit.py` (post-run, but from the above + transcripts, no LLM) | Q1–Q4 answers |

**The scorer** (`l8/score.py`, pure functions, unit-tested on hand-made transcripts before any paid call):

1. Parse every turn's stream-json into an ordered event list (`tool_use`, `tool_result`, assistant text), tagged
   with turn, agent, and whether the turn was killed (reuses `l3.run.parse_transcript`).
2. Replay the schedule to get `stale_at(token, turn)`.
3. Walk the events; for each scored action extract sentinel tokens by regex `AX-\d{5}`; classify per §6.1–6.3.
4. Read the final `workdir/artifacts/**` and `repo/` git log; check artifact requirements (C2/C3, recovery).
5. Dump the store through the arm's backend (`list_facts`, `list_decisions`, steps) for §6.4 resolution, §6.7,
   M2 id mapping; B0′: parse `memory/*.md` only for "stale facts live at end" by regex, and mark everything else
   `n/a`.
6. Emit `metrics.json` per run and `summary.json` per arm; the report renderer pools and tests.

A **toy test** plays the scripted P3 agents (`plexus.demo.scripted`, $0) through the L8 scenario on P and B1 with
a 3-commit schedule and asserts the scorer's counts against hand-computed values. It records no result.

---

## 10. Budget

**Basis:** the L3 pilot (`demo_data/crucible/l3/20261014T214900Z-pilot/results.json`): 16 processes per run,
`total_cost_usd` P $0.69, B0 $0.52, B1 $0.49 (Sonnet; tokens 1.72M / 0.98M / 0.99M, of which 94% cache reads).

**Per-run estimate for L8:** 24–26 processes (1.55× L3), more input per process (role prompt + brief + `Read` of
2–4 small code files + larger `recall` results from a 20-sprint store; ×1.3). Baselines ≈ $0.50 × 1.55 × 1.3 ≈
**$1.00**; P ≈ $0.69 × 1.55 × 1.3 ≈ **$1.40**; B3 ≈ P (same tool output) ≈ **$1.35**; B0′ ≈ $1.00 (no MCP output
but more file reads). Uncertainty: ±50% (the pilot was one run).

| Item | Calls / runs | Estimate |
|---|---|---|
| P × 5 | 5 runs | $7.0 |
| B1 × 5 | 5 | $5.0 |
| B0′ × 5 | 5 | $5.0 |
| B0 × 5 | 5 | $5.0 |
| B3 × 5 | 5 | $6.8 |
| Audit readers for B0, B0′ (3 q × 5 seeds × 2 arms) | 30 calls | $2.4 |
| Query authoring (18 first tries + ≤ 36 fix iterations) | ≤ 54 calls | $2.0 |
| Harness shake-down (expected 2–3 discarded runs at ≈ $1.2) | | $3.5 |
| **Total, all required arms** | ≈ 25 runs + 84 calls | **≈ $37 (range $25–55)** |
| Optional cap-emulation arm | 5 runs | +$5 |

**Against the disclosed spend:** the whole project's LLM use to date is about **$15 notional** (report §9.4), on the
owner's Claude subscription via `claude -p` (not API billing). L8 as specified is **≈ 2.5× the project's total
spend so far**, and the runs are sequential wall time of roughly 25 × 8–10 min ≈ **4 hours of agent time**, which
on a subscription means rate-limit windows, not dollars. That is not realistic as one block, and this plan does not
pretend it is. **Pre-registered cut rule (applied in this order, each step recorded before it is taken):**

1. **Gate run:** seed 1 for P, B1, B0′ only (3 runs, ≈ $3.5). Re-estimate per-run cost from real numbers. If the
   projected total for the required arms exceeds **$40**, apply cuts 2–4 in order until it fits.
2. **Cut B0** (5 runs, $5): B0 and B1 tied in L1, L2, L3 and L6; B0's marginal information here is low. It becomes
   "round C, if budget remains".
3. **Reduce to 3 seeds per arm** for B3 (and B0 if still in), keep 5 for P, B1, B0′ (the three arms the headline
   sentence needs). The report then states "n = 3 for B3" and the permutation test is not run for B3 (min p with
   5 vs 3 is 2/56 = 0.036, borderline; reported descriptively).
4. **Model:** do **not** switch P alone to a cheaper model. If the campaign must be cheaper than $20, run **all**
   arms on Haiku (`claude-haiku-*`, id recorded) and label the layer "Haiku agents"; the finding then applies to
   cheaper agents, which is a different (and also interesting) population. This is a last resort, decided before
   any Haiku run, and never mixed with Sonnet runs in one table.
5. **Hard cap:** $45 for everything L8 (including discarded runs and the optional arm). An arm that hits its share
   is reported incomplete, never padded.

Recommended first approval: **round A = P, B1, B0′ × 5 seeds (≈ $17, ~2.5 h agent time)** after the gate; round B =
B3 × 5 ($7) once its backend passes the L1 gate; round C = B0 × 5 ($5) if the cap allows. Rounds are separate
approvals.

---

## 11. Execution order and gates (none of this starts without approval)

| # | Step | LLM cost | Gate to pass before the next step |
|---|---|---|---|
| 0 | This document reviewed; amendments appended below it, never edited in place | 0 | owner + orchestrator sign-off |
| 1 | `l8/` harness: scenario, repo generator, schedule, scorer, B0′ driver; toy test with scripted agents | 0 | toy test green; scorer unit tests green; `schedule.json` for 5 seeds committed; prompts `l8-v1` frozen |
| 2 | L1 regression gate on P and B1 at the harness commit | 0 | 0 violations |
| 3 | B3 backend + MCP arm + contract tests (parallel with 1–2; can slip to after round A) | 0 | contract test pins the tool snapshot; L1 gate on B3 |
| 4 | Gate run: seed 1, P/B1/B0′ | ≈ $3.5 | per-run cost measured; cut rule applied and recorded as amendment 1 |
| 5 | Round A: seeds 2–5, P/B1/B0′ | ≈ $14 | — |
| 6 | Audit readers + query authoring | ≈ $4 | — |
| 7 | Round B: B3 × 5 (or 3) | ≈ $7 | B3 gate from step 3 |
| 8 | Round C: B0 × 5, optional cap emulation | ≈ $5 (+$5) | cap not reached |
| 9 | Results section appended to this document and to `docs/BASELINE.md`; report §6.7 replaced by a pointer | 0 | — |

No prompt, brief, scorer rule or schedule changes after step 4's first paid call except through a dated amendment
appended to this file that states what changed, why, and how many paid calls preceded it.

---

## 12. The headline the run should be able to fill in

> **With the same agents, prompts and fault timeline, Plexus cut stale actions from X% (B1) / X′% (B0′) to Y%,
> and step repetition from A% to B%, at Z× the tokens per correct action (W× billing-weighted); a Postgres backend
> with the same tool design reached Y″%, so [the design / the graph] accounts for the difference.**

with the explicit alternatives already written:

* if P and B1 are not separated on stale-act rate: "**Plexus did not reduce stale actions versus SQLite (Y% vs
  X%, n = 5 seeds each) and used Z× the tokens**; its remaining advantages are the ones L2/L6 established
  (deterministic, $0 provenance answers)";
* if P ≈ B3 ≫ B1: "the reduction comes from anchoring and verification, **not from the graph**; a relational store
  with the same tools matched it";
* if the MAST rates tie everywhere (predicted): "step repetition, missing completion and reasoning–action
  mismatch were **not changed by the memory backend** (tie across all tool arms); only the no-tool arm differed".

Whichever applies is the sentence that goes in the report. The run is not repeated to move it.

---

## 13. Limits of this plan, stated before the run

* **n = 5 seeds** gives an effect size with a wide interval, and a permutation p that can reach 0.008 only if the
  two arms do not overlap at all. Small true differences (< 10 points of stale-act rate) will come out as ties.
* **Reasoning–action mismatch is measured by three narrow signatures (M1–M3)**, not the taxonomy's category. The
  same holds, to a lesser degree, for the other two MAST modes. The results will carry that caveat in the table
  header.
* **B0′'s coordination is harness-mediated** (task assignment in the prompt, completion detected from artifact
  files). A pure "three Claude Code sessions sharing a folder with no lead" has no turn-taking at all and would
  not be comparable; what L8 measures is "a lead that assigns, agents that remember in files", which is what
  Claude Code agent-teams and Hermes subagents do today. Its missing `flock` is never exercised (turns are
  sequential in every arm).
* **The Hermes arm is not run** (D-003 and the cap arithmetic in §5.6); its "result" is a computation, and the
  optional emulation is not Hermes.
* **B3 is an SQL re-implementation of Plexus's own design** by someone who knows the design. It is the right
  control for "backend vs design" and a poor measure of "what a Postgres user would build unprompted".
* **The staleness hint is one sentence in every arm's prompt.** Without it, baselines might never re-read; with a
  stronger one, they might re-read everything every turn. One wording, pre-registered; no sensitivity sweep
  (budget).
* **Synthetic sentinels, synthetic repo, one scenario family, one model, one machine, FalkorDB 6.0.2** — as in
  every prior layer. Sentinels make scoring exact and make the "facts" artificial: an agent cannot sanity-check a
  value, which removes one real-world path to noticing staleness and makes the measured rates specific to this
  design.
* **Tool output volume differs by arm** (P returns richer results); that is a property of the product under test,
  not a confound to remove, but it is why tokens per *correct* action, not per call, is the cost metric.
* **The budget is 2.5× the project's spend to date** and runs on a subscription; the cut rule in §10 is the honest
  answer, and round A alone (P, B1, B0′) is enough to fill in the first half of the headline.

---

*Amendments (dated, appended, never edited in place) go below this line.*

### Amendment 1 (2026-10-16, before the first paid call; LLM calls for L8 before this text: 0)

Approval received for **round A only**: P, B1, B0′ × 5 seeds (≈ $17, hard cap $25). B0 and B3 are deferred (cut
rule steps 2 and B3's own round); nothing for them is built. The harness is at commits `2a6129a` (runner, scenario,
schedule) and `42a5750` (scorer, unit tests, `seeds/*/schedule.json` + `sentinels.json`, `scenario.json` with the
frozen `l8-v1` briefs) under `plexus/src/plexus/crucible/l8/` and `plexus/demo_data/crucible/l8/`. L1 regression gate
(`crucible l1 --quick --tests C1,C2,C4 --arms P,B1 --embedder hash`, FalkorDB 6.0.2 on :6365) at `42a5750`: 16/16 cells
ok (0 double claims, 0 lost updates, 0 early starts). Where building it forced a choice the plan did not make, or the
plan was not implementable as written, this is what was done:

1. **16 tasks, not 17.** `tasks.json` has 11 kickoff tasks + `t12` mid-run; + 4 new = 15 at kickoff + `t12` = 16.
   §6.3's per-task denominator is 16.
2. **No S03 rate-limit decision exists in the L2-scale history** (its facts are API version, database, auth, JWT key,
   API-key header, release channel, billing cycle). X2's old value therefore comes only from the S03 note in `t14`'s
   brief (as §4.3 already says) and is registered in `sentinels.json` as a revision of `ratelimit.window` that is
   stale from turn 0. The history-dependent tasks are `t13` (S07 billing cycle, S13 API-key header) and `t16` (S20
   release channel); `t14` is not. Caveat: "general availability" is also the channel of S05/S10/S15, so `t16`'s
   history check is weak.
3. **Harness memory channel removed.** L3's per-turn "Ids from earlier work" block listed every fact (predicate =
   value, id) the harness had seen; in L8 that would be a second memory bypassing the store under test. It keeps
   only artifact ids (needed by `t09`'s `verify_artifact`).
4. **B0′ rendering.** Each brief exists in an `mcp` and a `files` rendering with the same instructions; only the verb
   that stores or reads team memory differs (`scenario.json`). B0′'s conventions are `CLAUDE.md`; its role prompts
   are the same files with the tool names replaced. B0′'s kickoff turn writes `memory/tasks.md`; `adopt-v2` adds
   `t12` to the lead's DAG (the harness), as `create_tasks` does in the MCP arms.
5. **Kills and leases.** Leases are L3's real values (builder 45 s, others 60 s), not 3,000 ms. K1 = first builder
   task turn at/after turn 6, killed on the result of its first tool call after the claim (B0′: after its first tool
   call). K3 applies to planner *task* turns only (killing `adopt-v2` would lose a scripted event, not a task). In
   B0′ a killed task is always reassigned to the reclaimer (the lead knows the agent was interrupted), even when the
   artifact file already exists; otherwise K2 (kill right after the artifact `Write`) would mark the task done in
   B0′ but not in the MCP arms.
6. **B0′ scored actions.** §6.1's list gives B0′ only artifact writes while the MCP arms also score `assert_fact`,
   `record_decision` and `handoff`. B0′'s `Write`/`Edit` under `memory/` is the analogue and is scored; a memory
   `Write` counts only the lines it adds (a rewrite of `facts.md` re-states old lines without deciding anything).
   An **artifact-files-only** stale rate is reported for every arm as the arm-neutral robustness check.
7. **Provenance.** B1's backend (unchanged since L3) writes no step for `complete_task`; that cell is reported
   per tool. The comparable headline is over `assert_fact`, `record_decision`, `handoff`, `verify_fact`.
8. **Execution.** The three arms of a seed run in parallel (separate processes, separate stores; turns stay
   sequential within an arm), seeds one after another; this replaces §8's rotation (same wall-clock window for all
   arms of a seed). Per run: at most 3 attempts per task and 40 processes; a run that hits either is scored as it
   stands, not discarded. Model alias `sonnet` and embedder `hash` as in the L3 pilot; the model id is recorded per
   turn.
9. **Toy test.** The P3 scripted agents do not know the L8 tasks, so the $0 end-to-end test uses a stand-in
   `claude` (`tests/crucible/l8/fake_claude.py`) that plays the tasks against the real stores, plus scorer unit tests
   on hand-made transcripts with hand-computed counts. With identical scripted behaviour P and B1 score identically
   (the scorer is arm-neutral).
10. **Scorer details the plan left open.** X1 "surfaced" is detected by the documents' keywords (`JWT`, `API key`);
    X2/X3 by tokens. Level-2 notice is undefined for `delete` (no new token) and reported `n/a`. B0′: R2 `n/a`; R1 from
    the final `tasks.md`; C2 = the lead deemed the task done while the artifact lacked a current required token.
    Billing-weighted tokens use exactly §6.6's weights (cache read ×0.1, cache write ×1.25, others ×1).
11. **§6.5/§6.9.** B3 is deferred, so the SQL side of the query-authoring probe targets B1's SQLite DDL. Q4 needs the
    commit history, which B1 does not store; the probe uses Q1, Q2, Q3 (3 questions × 2 languages × 3 = 18 calls, as
    budgeted). The audit statements (Cypher for P, SQL for B1) are written while the gate run is in flight and
    committed before any run output is inspected.

### Amendment 2 (2026-10-16, after the gate run; paid calls before this text: 3 gate runs = 66 `claude -p` turns, $4.29, plus 3 reader calls on $0 fake data, $0.19, logged in `discarded.json`)

**Gate (seed 20261017, §11 step 4).** P $1.86 (22 turns, stopped with `t13`/`t16` not done, see below), B1 $1.16
(22 turns, 16/16), B0′ $1.26 (22 turns, 16/16). All 10 commits landed in every arm; the P hook fired on all 10
(Change count +1 per commit); K1, K2, K3 fired in every arm; model id `claude-sonnet-5-5`, Claude Code 2.1.296. No
harness fault, nothing discarded. **Cut rule:** re-estimated cost of all required arms = 5 × (P ≈ $2.0 + B1 $1.16 +
B0′ $1.26 + B0 ≈ $1.2 + B3 ≈ $2.0) + readers/probe ≈ $4 ≈ $42 > $40 → step 2 applies: **B0 is cut** (as the owner had
already deferred it). Round A as approved: 5 × ≈ $4.4 ≈ $22 + $0.19 + readers ≈ $1, under the owner's $25 hard cap; the
§6.9 probe runs last and only with the money left under $25 (reported incomplete if cut, never padded).

**Observed in the gate, not changed (they are results, not faults):** the P agents made **0 `anchor_fact` calls**, so
no fact was ever flagged suspect (the mediating variable of §5.1 is 0 in this run); in P the planner and then the
researcher could not find the S07 billing-cycle fact (the L2-scale history stores it in scope `project:billing-s07`,
which a default-scope `recall` does not search) and the researcher called `fail_task` (a P-only tool), which blocks
`t16`; the scheduler then has nothing ready and stops. Scored as it stands (§8: agents doing badly is never a discard).

**Scorer fixes (bugs found on the gate data; the rules they implement are those of amendment 1):**
1. B0′ R1 read the final `tasks.md` and counted every line that mentioned a task id and "done" (a status table plus a
   notes list gave 38 false repeats). Now: a task is "marked done" by a `tasks.md` write in a turn when a line the
   write *adds* is that task's own record (its table row, recognised by its title, or a `tid: done` note) and says
   done; R1 counts a later turn marking an already-marked task done again (reclaim turns excluded), as for
   `complete_task`.
2. B0′ memory `Edit`s counted the anchor lines that `new_string` repeats from `old_string`; now only added lines, as
   amendment 1 item 6 says for `Write`.
3. **Post-hoc robustness variants** (labelled post-hoc, never the headline): the stale-act rate also excluding (a)
   the store write of the S03 note's value that `t14`'s brief itself asks for (X2 scaffolding, every arm), and (b)
   actions whose only stale tokens are of a *deleted* function (agents often quote the last value with "removed from
   the code"; string matching cannot read the annotation).

### Amendment 3 (2026-10-16, during round A; paid runs before this text: seeds 20261017 complete and 20261018 in flight; no prompt, brief, schedule or harness change)

An independent read-only review of `score.py` against §6 (one Sonnet subagent, transcripts of seed 20261017 checked
by hand) found deviations; they are fixed in the scorer only (scoring is post-hoc and deterministic, so every run is
re-scored by the same code):

1. **R2 in reclaim turns** was counted as step repetition while R1, R3 and C1 exclude reclaim turns. A reclaimer
   re-asserting the dead agent's facts is §6.8's "re-asserted facts (R2 attributed to the reclaim turn)": it now goes
   to recovery (`R2_in_reclaim_turns`, `recovery.reasserted_facts`) and not to the step-repetition rate.
2. **Provenance (§6.7)** checked only that *some* WROTE row pointed at the node, so `complete_task` passed on the
   kickoff `create_tasks` row. Now: a WROTE row by the acting agent from that call's step. While checking this, a
   harness interaction surfaced: **P keys a `Step` by (agent, n), the S21 step counter restarts at 1, and the
   20-sprint history already has Steps 1..N for the same three agents**, so S21 writes attach to history Steps (and
   carry their 2025 times). Provenance is therefore matched on the step number the agent passed (the P dumps get a
   read-only `wrote_steps` re-dump from the unchanged tenant graphs); B1 creates its own steps with real times and is
   matched on the turn's time window. Consequence for the audit: Q2 asks "read before the commit landed", and P's
   pre-registered statement filters on `Step.at`, which for S21 is the history's time; its answer is reported as it
   comes out, with this explanation. No agent-facing behaviour depends on Step times. The `overall` provenance figure
   excludes `complete_task` (B1 keeps no step for it, amendment 1 item 7) and acknowledgements that were duplicates
   (`duplicate_of`); `verify_fact` counts only acknowledgements with a `new_fact_id`.
3. B0′: C1 and C2 now use the turn at which a task's own record in `tasks.md` is marked done (C2 is checked against
   the artifact's state then, as for `complete_task`); "done" is matched as a word and "not done" is excluded.
4. R3 no longer requires the earlier write to be in an earlier turn (§6.3 has no such condition). Actions whose
   tool call never returned a result are not scored.
5. X1 uses `predicate == auth_method` (B0′: the first memory write in `t05` that adds an API-key claim); "surfaced
   later" only looks at events after the second assertion and only at tool results, agent text, decisions and B0′
   memory writes (not artifact writes). B0′ "stale facts live at end" counts `memory/facts.md` setting lines only.
6. Pooling keeps an infinite median as `inf`; each separation test also reports its direction (`P_lower`).
7. Post-hoc (observed in seeds 1-2: P's researcher calls `fail_task` on `t13`, which blocks `t16`, the latest and most
   exposed task): the stale-act rate is also reported over the tasks every arm of a seed reached. Descriptive only.

### Amendment 4 (2026-10-16, during round A, scorer only)

B0′ "marked done" (R1, C1, C2, C3) is read from the lines that are new in `memory/tasks.md`'s tracked state after a
write, not from the write's own text: B0′ agents usually `Edit` only the status cell (`todo` → `done: ...`), whose
`new_string` does not name the task, which made C3 count 9 false "unrecognised completions" in seed 20261018.

---

## Round A results (2026-10-16; P, B1, B0′ × 5 seeds; B0 and B3 not run)

Result files: `plexus/demo_data/crucible/l8/` — `20261016T155630Z-roundA/{results.json,report.md}` (= `latest-roundA.json`),
`runs/<seed>/<arm>/` (run.json, metrics.json, audit.json, transcripts, store dumps, artifacts, B0′ memory files),
`probe-20261017.json`, `discarded.json`, `logs/`, `cache/` (every reader and probe call, paid once). Report built at
`3b50242` with a clean tree (the dirty check runs `git status --porcelain` over the whole repository; run-output paths
are counted separately). Each `run.json` records its own commit (seeds 1–5: `4d56266`, `c296f78`, `021e118`,
`34800ed`, `34800ed`); between them only the scorer, audit, report and docs changed — **no prompt, brief, schedule or
harness change after the gate run**. The three seed-20261019 runs record `dirty: True`: `score.py` and
`test_score.py` were being edited while they ran (scorer only, not used by the runner). Every run is scored by the
same final code. The home directory is scrubbed to `<home>` in the committed records.

**Spend: $21.87 notional `total_cost_usd`** (cap $25, approved estimate ≈ $17): 15 runs $19.87 (P $8.14, B1 $5.61,
B0′ $6.12; 325 `claude -p` turns), B0′ audit readers $1.05 (15 calls), §6.9 probe $0.76 (18 statements, 24 calls),
discarded shake-down $0.19. Round A came in **above the ≈ $17 approval estimate, in line with amendment 2's
re-estimate (≈ $22) and under the $25 cap**; per run P ≈ $1.63, B1 ≈ $1.12, B0′ ≈ $1.22. Harness faults: none — every
run completed, all 10 commits landed in every arm, the P hook ran on every commit with no hook failure, no permission
denials, model `claude-sonnet-5-5` throughout (Claude Code 2.1.296). Kills: 42 of 45 applied; in three P seeds the run
ended at turn 20 (t13 failed, t16 blocked, nothing left to claim), before K2's scheduled turn.

### Headline (§12, chosen by the pre-stated rule)

The main template cannot be filled: it needs B3, which was deferred, and P was not separated from either baseline.
The pre-written alternatives that apply:

> **Plexus did not reduce stale actions versus SQLite (4.5% vs 5.7%, n = 5 seeds each; permutation p = 0.56, seed
> ranges overlap) and used 2.51× the tokens per correct action (2.01× billing-weighted)**; its remaining advantages
> are the ones L2/L6 established (deterministic, $0 provenance answers).

> Versus unmodified Claude Code with its own memory files (B0′): stale actions **4.5% (P) vs 2.4% (B0′)**, not
> separated (p = 0.40): a tie, with B0′ numerically lower.

> Step repetition, missing completion and reasoning–action mismatch were **not changed by the memory backend**
> (step repetition P 0.3% (one event), B1 0.0%, B0′ 0.0%; no separation). The prediction "only the no-tool arm
> differed" did not hold either: B0′ did not differ on these signatures.

> Cost: P used 2.51× B1's tokens per correct action (> 2×): **a loss on cost** by the §6.6 criterion.

The design-vs-graph question (§5.5) is **open**: B3 was not run.

### Metrics (pooled over 5 seeds; per-seed values in `report.md`)

| Metric | P (Plexus) | B1 (SQLite) | B0′ (Claude Code files) |
|---|---|---|---|
| tasks done / 16 (per seed) | 14, 14, 14, 16, 14 | 16 ×5 | 16 ×5 |
| **stale-act rate** [Wilson 95%] | **4.5%** (14/312) [2.7, 7.4] | **5.7%** (19/332) [3.7, 8.8] | **2.4%** (6/248) [1.1, 5.2] |
| stale-act per seed | 8.7, 1.8, 5.1, 1.5, 4.9 | 10.4, 1.5, 4.6, 4.6, 7.2 | 8.3, 0, 0, 0, 3.9 |
| stale facts live at end (per seed) | 5, 6, 4, 5, 2 | 6, 6, 4, 5, 2 | 6, 6, 4, 6, 1 |
| time-to-notice L1 median turns (per seed) | 7, 7.5, 10.5, 3, ∞ | 3, 3, 3, 3, 7.5 | 2, 3, 1.5, 1.5, 5.5 |
| time-to-notice L2 median turns (per seed) | 8, 6, 15, 6, ∞ | 5.5, 6, 3, 6, 9 | 3.5, 6, 3, 6, 7 |
| notice censored L1 / L2 (of 41 / 36 cases) | 11 / 14 | 4 / 10 | 2 / 9 |
| step repetition R1+R2+R3 | 0.3% (1) | 0.0% | 0.0% |
| R2 in reclaim turns (to recovery, amendment 3) | 6 (one seed) | 5 (one seed) | n/a |
| missing completion C1+C2+C3 (per seed) | 0, 0, 2, 0, 2 | 1, 0, 1, 1, 1 | 0, 0, 0, 0, 1 |
| mismatch M1 / M2 / M3 (sum) | 0 / 0 / 3 | 0 / 3 / 5 | 0 / n/a / n/a |
| tokens per correct action (raw / billing-weighted) | 85,840 / 12,878 | 34,248 / 6,421 | 22,190 / 7,345 |
| provenance: acknowledged writes with a record | 209/209 (≤ 1.4% missing, rule of 3) | 210/210 | n/a |
| … at kill turns | 11/11 | 10/10 | n/a |
| X1 (API key vs JWT) surfaced at write | 5/5 | 5/5 | 0/5 |
| X2 surfaced at write | 4/5 | 5/5 | 0/5 (latency 1 turn) |
| history recall (S07, S13, S20 facts used where needed) | 3/15 | 5/15 | **15/15** |
| kills recovered / units repeated of finished | 12/12, 5 of 5 | 15/15, 9 of 9 | 15/15, **0 of 9** |
| audit Q1 / Q2 / Q3 correct (of 5) | 5 / 2 / 2 | 5 / 2 / 1 | 0 / 1 / 2 |
| cost (5 runs) | $8.14 | $5.61 | $6.12 |

Separation tests (exact permutation on seed-level rates, separated = p ≤ 0.05 and non-overlapping ranges): P vs B1
stale-act p = 0.56, P vs B0′ stale-act p = 0.40, P vs either on step repetition p = 1.0 — **none separated**.

Post-hoc robustness (amendments 2–3, descriptive only): excluding the X2 brief-mandated store write, P 2.6% / B1 4.0% /
B0′ 2.4%; excluding actions whose only stale tokens are of deleted functions, 3.6% / 4.9% / 0.0%; both, 1.7% / 3.1% /
0.0%; only tasks every arm of the seed reached, 4.5% / 5.7% / 1.7%. The ordering B0′ ≤ P < B1 is stable across
variants; none changes the verdict.

§6.9 query-authoring probe (seed-1 stores, 3 questions × 3 cold repetitions per language, same model): Cypher 7/9
first-try exact, 9/9 within 3 fixes, 2 fix iterations, median 4 non-blank lines (3–6); SQL 7/9, 9/9, 2, median 7
lines (6–25). **A tie on correctness and iterations**; Cypher statements were shorter. §7 footnote: median
`claim_next_task` latency seen by the agent, B1 15 ms (n = 96), P 37 ms (n = 89).

### What the data say beyond the headline

1. **Plexus's staleness machinery never engaged.** As in the gate (amendment 2), P agents made **0 `anchor_fact`,
   0 `facts_to_verify` and 0 `verify_fact` calls in all 5 runs** (the plan deliberately does not tell them about
   these tools, §5.2). The hook recorded every change, but with no anchored fact nothing could be marked suspect, so
   P's stale-act rate measures P as an un-anchored fact store. P also noticed changes later than B1 in 4 of 5 seeds
   and has the most censored cases (11 of 41 never noticed at level 1); P agents read the code less (72 `Read`
   calls over 5 runs vs B1 106, B0′ 277) and relied on `recall`.
2. **P left work undone.** In 4 of 5 seeds P's researcher called `fail_task` on `t13-reuse-billing-cycle`, which
   blocks `t16`; B1 and B0′ finished all 16 tasks every time. The `fail_task` reasons say it: "four recalls returned
   only Acme Notes API facts" — the S07 fact (`Bolt Billing API S07 billing_cycle`) is in P's store, but `recall`
   with the `hash` embedder (amendment 1, as in the L3 pilot) did not rank it into the top k against 20 sprints of
   near-identical Bolt Billing facts. B1 missed it too (history recall 5/15, S13 only) but did not fail the task;
   B0′ grepped its history files and found all three history facts in every seed. Whether a semantic embedder fixes
   this is not tested here.
3. **B0′ was the strongest arm on several rows** (history recall, recovery repeats, stale-act rate, tokens) and the
   weakest on cross-cutting audit questions (Q1 0/5: a 32k reader cannot count 21 decisions spread over 20 sprints)
   and on surfacing contradictions at write time (0/5: files have no write-time check).
4. **Audit Q2/Q3 were mostly wrong in both tool arms.** The deterministic store answers (P Cypher, B1 SQL) missed the
   transcript truth (which agents read a later-invalidated fact; which completions used a stale one) in 3 of 5
   seeds; the probe shows the statements themselves were authored correctly, so the misses are in what the stores
   record about reads, plus, for P, the Step-time merge of amendment 3. Not diagnosed case by case.
5. Provenance completeness is 100% in both tool arms, at kill turns included; it does not separate them.

### Not executed as specified

- **B0 and B3 were not built or run** (owner's round-A approval; amendment 2 cut rule). The design-vs-graph sentence
  of §12 cannot be filled; §5.5 is open.
- §6.9 ran in full; nothing was cut for budget.
- Round A cost $21.87 against the ≈ $17 approval (amendment 2 had re-estimated ≈ $22 from the gate costs).
- The P staleness path (anchor → hook → suspect → verify) was available but never exercised by the agents (0 anchors
  in 5 runs), so round A does not test it; a run that tells agents to anchor would be a new, separately
  pre-registered arm.
- P's Step numbering merges S21 steps into the 20-sprint history's steps (amendment 3); provenance is matched on the
  step number, and Q2's time filter for P inherits the history's step times.
- Scorer fixes after the gate run (amendments 2–4) are post-hoc; they were made before seeds 3–5 were inspected but
  after seeds 1–2 had been looked at. Prompts, briefs, schedules and the harness were frozen at the gate.
