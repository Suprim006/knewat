# Plexus

**One shared memory for agent teams that work across several repos.** Plexus tracks the decisions a team makes ahead of the
code, and who changed what and why. Claude Code, Hermes and other harnesses remember in text files and coordinate through task lists,
which works until the next agent is not in the folder where the file lives. Plexus gives the team one FalkorDB graph instead: every
memory, task, claim, handoff and decision is a node, every "because" is an edge, and agents connect over MCP. A rule decided in repo A
is recalled in repo B, a dead agent's task is reclaimed with the evidence kept, and *"why did we decide that?"* and *"what did the
builder know at step 17?"* are graph queries, not guesses. In the everyday-workflow trials below, real Claude Code agents followed a
cross-repo rule 24 of 24 times with Plexus and 0 of 24 without it.

**Track: Track 02, Agent Memory and Coordination** · Graph Hacks (WeMakeDevs × FalkorDB).

| | |
|---|---|
| Live demo | `<RENDER_URL>` (one container on Render Free: the View, the read-only API and a read-only Cypher console; no MCP endpoint, see [Live demo](#live-demo)) |
| Demo video (≤ 3 min) | `<VIDEO_URL>` |
| Blog post | `<BLOG_URL>` |
| Run it yourself | `docker compose up -d --wait --build`, see [Setup](#setup) (Docker is the only requirement) |

Plexus itself contains **no LLM and no LLM credentials**. The agents in the demo are the unmodified `claude` binary; every
Plexus tool is a deterministic Cypher query. Only synthetic data is used (a fictional "Acme Notes API" team).

> **Partly STALE (2026-10-18).** The $0 deterministic benchmark layers (L1, L4, ablation, L2 and L2 at scale re-scored from the cache, B1h,
> C7 extended, L5a, the surviving L5b arms, the hub world, L6 A-F and L6-C) were re-run on `rerun-current` (the code of main `7cca016`) and are
> CURRENT; where a re-run moved a number, this README states the new value. Still STALE (earlier builds, not re-run): the L3 pilot, the L6 LLM
> pilot, L7, L8, the floor 0.5 / 0.9 forgetting runs and the other removed L5b arms, deployment timings, the Testing counts, the recorded
> runs' cost. Build per number: [docs/NUMBERS_STATUS.md](docs/NUMBERS_STATUS.md). Counts of the tree itself are current: 45 tools,
> 114 query files, the recording's 247 nodes / 708 edges.

## Where it helps: decisions made ahead of the code, across repos

The case for Plexus is the multi-repo team: a rule decided in a planning session in one repo, a bot's deprecation notice, a change
on a branch nobody has merged. Nothing in the next repo shows any of it, and the next agent breaks it. With Plexus the decision, who made it,
from which source and why is one graph every agent on the team reads before it writes code.

![Three everyday workflows, 4 runs per arm: rule violations by plain Claude Code, Claude Code with CLAUDE.md, and Claude Code with Plexus](docs/blog/figures/06_trials.png)

Real Claude Code agents doing ordinary feature work in small repos, in separate sessions that share no conversation.
There are three arms: plain Claude Code, Claude Code told to keep decisions in `CLAUDE.md`, and Claude Code with Plexus.
Scoring runs the code the agents wrote. 4 runs per arm, predictions pre-registered. Full records: [trials/](trials/FINDINGS.md).

| Workflow | Plain | CLAUDE.md | Plexus |
|---|---|---|---|
| A team rule decided in repo A, later work in repo B (rule violations, of 24) | 24 | 24 | **0** |
| Parallel agents on git worktrees: rule on an unmerged branch + a non-AI ci-bot's deprecation notice (of 12) | 9 | 8 | **0** |
| Retract a void document: rules correctly kept (of 8) / void-only rule removed (of 4) | 8 / 0 | 8 / 4 | 8 / 4 |

Plexus wins where no shared file reaches the next agent: another repo, an unmerged branch, a note from a tool that
isn't an AI. It ties a well-kept `CLAUDE.md` where the file does reach the next agent. Within one repo on one machine,
plain Claude Code's own auto-memory already ties both (trials 3/4).
The trial 8 tie exposed a gap: a fact could name only one source. Facts now take several sources (D-015). On the final
code the re-run linked the double-sourced rule to both documents and retracted the void one through
`quarantine_source` / `forget_source`, both 4/4. Plexus costs $0.01-0.10 more per run. Caveats: small synthetic repos,
n = 4 per arm, designed after trials 1-5; build per trial in [docs/NUMBERS_STATUS.md](docs/NUMBERS_STATUS.md) (section H).

## What it does, by Track 02 focus area

| Focus area | Plexus feature | Where to see it |
|---|---|---|
| Episodic, semantic and procedural memory | `Episode` chains, scoped `Fact`s on `Entity`s with validity windows, `Procedure` → `Run` success rates | MCP: `remember_episode`, `assert_fact`, `recall`, `log_procedure_run`, `best_procedure` · queries `plexus/queries/engram/` · View: Explorer. *Procedures are implemented and tested but are not exercised in the recorded demo and have no View page.* |
| Persistent conversation history | `Agent` → `Session` → `Episode` chains. Every `claude -p` turn is a new process; the recording has 16 sessions and the agents still build on each other's facts | View: Inventory (16 `Session`, 5 `Episode`), Explorer · MCP: `start_session`, `remember_episode` |
| Shared state and handoffs | Dependency-aware atomic claims with leases and heartbeats, dead-agent reclaim, `Handoff` nodes carrying artifacts and facts, `Decision`-`BASED_ON`→`Fact` | View: Flow (live `ToolCall` feed), Why · MCP: `claim_next_task`, `heartbeat`, `handoff`, `record_decision` · queries `plexus/queries/relay/` |
| High-concurrency reads and writes | One statement per operation; writes serialise per graph, so load spreads over tenant graphs. Crucible L1 races 10-200 workers; L4 measures the ceiling | View: Results (L1, L4) · [`docs/BASELINE.md`](docs/BASELINE.md) |
| Separate memory per user or tenant | One FalkorDB graph per tenant (`plexus_t_<tenant>`); the tenant is bound to the connection and is never a tool argument; `Scope` nodes (user, project, global) with `INHERITS`. Crucible C5 probes leak 0 rows | View: tenant selector in the header · [`docs/mcp.md`](docs/mcp.md) · `plexus/queries/engram/create_scope.cypher` |
| Memory updates over time | Validity windows (`valid_from`/`valid_to`), `SUPERSEDES`, `CONTRADICTS` and duplicate detection at write time, "as of T" queries, forget-by-source and quarantine | View: Time Machine, Explorer · MCP: `assert_fact`, `as_of`, `fact_history`, `forget_source`, `quarantine_source` |
| Explainability | `why(decision)` and `why_recalled` return graph paths (decision → facts → agent → step → source); `knew_at(agent, step)`; `who_knew(fact)` | View: Why, Time Machine · MCP: `why`, `why_recalled`, `who_knew`, `knew_at` |

## Memory that notices change

Agent memory goes stale silently: a fact written when `payments.py` used eSewa is still "true" a month after someone
rewrote it. Plexus ties facts to code and tells the agent which ones to re-check, instead of waiting for the agent to be wrong.

- **A code change makes a fact *suspect*, never false.** A fact is `ANCHORED_TO` a `CodeAnchor` (a file, or a Python
  function / class found with `ast`; other languages are file level only). `mark_changed` hashes the code, creates a `Change`
  and marks the active facts of every changed anchor `suspect` in one Cypher statement. A fact that derives from a `Source`
  whose uri is a changed file is suspect too, with no `anchor_fact` call (the zero-effort path). A review date
  (`set_review_date`) does the same for facts no code change can invalidate (a deployed URL).
- **Recall still returns suspect facts**, flagged: `verify_state: suspect`, `suspect_since`, `suspect_reason: "changed in abc123
  (app/services/payments.py)"`. Nothing is hidden or dropped.
- **An agent re-checks and records the outcome.** `facts_to_verify` lists the work (most decisions at risk first, then the most
  used fact, then the oldest suspicion). `verify_fact(still_true, new_value, evidence)` confirms the fact, or supersedes it **at
  the time of the code change** (so `as_of` before / after the change returns the old / new value), and flags the decisions
  that rested on the old value. `docs_to_update` lists the docs that `DESCRIBE` code that changed after the doc was edited.
- **One query answers "why is this decision at risk"**: `why(decision)` includes the `Change`s that `SUSPECTED` the facts it
  rests on and the agents that `VERIFIED_BY` them.

Tools (7): `anchor_fact`, `describe_code`, `mark_changed`, `verify_fact`, `facts_to_verify`, `docs_to_update`,
`set_review_date` ([`docs/mcp.md`](docs/mcp.md), [`docs/staleness.md`](docs/staleness.md)).

Wiring it to a repository (runs on the developer machine; the server never reads your files):

```bash
plexus code baseline --repo ~/work/pv-core-api --tenant physio      # once: record today's hashes
plexus code hook-git --repo ~/work/pv-core-api --tenant physio       # a post-commit hook (never fails a commit)
plexus code hook-claude --tenant physio                              # prints a Claude Code PostToolUse hook for .claude/settings.json
plexus code scan --repo ~/work/pv-core-api --tenant physio --paths app/services/payments.py   # a one-off scan
```

Honest claims. **Measured** (Crucible L5a, 60 facts, 21 commits of a scripted repo, no LLM): symbol-level anchors flag exactly
the facts whose function changed (19 of 19, 0 false flags); file-level anchors miss none but only 15% of their flags are right (the
rest are functions that did not change); without anchors all 19 stale facts come back looking current; stale facts returned
unflagged: 0 for both anchored arms ([`docs/BASELINE.md`](docs/BASELINE.md), "L5 results"). **Demonstrated** (one real Claude Code
run on a scratch copy of a real backend, [`docs/staleness.md`](docs/staleness.md), "Real run"): the agent used only the tools to
find the stale fact, read the code, record the corrected value, and name the doc to update. The run also found a bug (a
corrected clause of a long fact was swallowed as a paraphrase duplicate), now fixed with a test. **Not claimed:** that
agents verify well in general, or that facts nobody anchored are covered; `verify_fact` is two statements and is not atomic
(a failure between them is documented and pinned by a test).

> *(stale: the L5a figures were measured on `75bd122`; the real run was recorded on `p7-int`. See [docs/NUMBERS_STATUS.md](docs/NUMBERS_STATUS.md).)*

## Forgetting

Memory that only grows gets noisy. Plexus ranks facts by how much they are used, and **never deletes anything because of
age**. `A(f) = ln(sum of w * t^-0.5)` over a fact's events (created, re-asserted, a decision rests on it, a handoff carries it,
used `weight 1`, merely recalled `0.3`, verified `2`; the newest 50 events; surprising facts start higher). Recall
multiplies relevance by `floor + (1 - floor) * sigmoid(A - A0)` (default floor 0.9), so a fact nobody uses ranks lower and is
still returned. Facts a decision rests on, a handoff carries, a human pinned, that supersede or contradict another, or that
come from a `trust: high` source are *protected*: they never fade in a sweep. A suspect fact is not strengthened by being
recalled.

Tools (5): `pin_fact`, `unpin_fact`, `memory_strength` (why a fact ranks where it does, read-only), `memory_sweep` (dry run by
default; moves faint unprotected non-suspect facts to `dormant`, hidden from recall unless `include_dormant`), `restore_fact`;
`recall` gains `include_dormant` and `forgetting`. Settings: `PLEXUS_FORGETTING=on|off`, `PLEXUS_ACT_DECAY`, `PLEXUS_ACT_A0`,
`PLEXUS_ACT_FLOOR`, `PLEXUS_ACT_EVENTS` ([`.env.example`](.env.example), [`docs/forgetting.md`](docs/forgetting.md)).

Honest claims. **This is a ranking and a tidy-up, not an accuracy feature, and it has a cost.** Ranking-only forgetting at
`PLEXUS_ACT_FLOOR=0.9` is the default; the sweep is optional, dry-run by default and reversible. Crucible L5b (20 near-identical
sprints, 140 real facts, 300 decaying noise facts, 90 simulated days of reads, no LLM, [`docs/BASELINE.md`](docs/BASELINE.md)): our first
default, floor 0.5, **failed** its pre-registered criterion (recall@5 98.6% -> 73-75%, 7-8 of 80 "read once, 90 days ago, a
decision rests on it" probes outranked by popular near-twins from other sprints), so it was changed to 0.9 and re-tested as a new
pre-registered run. At 0.9: critical probes lost 0, recall@5 96.4% against 98.6% with forgetting off, recall@1 63.6% against 75.7%,
noise share of what recall returns 24.0% -> 15.1%, nothing deleted (fact count equal, 0 of 80 critical facts swept). A real sweep
lowers recall@5 to 88.6% because it hides the cold facts nobody used for 90 days (14 real ones in the run); read the dry run first,
`restore_fact` undoes it. One synthetic scenario, one confirmatory run: a hypothesis for your data, not a promise.

> *(stale: the floor 0.5 runs were measured on `75bd122`, the floor 0.9 confirmatory run on `92c9bd7`. See [docs/NUMBERS_STATUS.md](docs/NUMBERS_STATUS.md).)*

**D-013 (pattern separation, branch `feature/neuro-memory-research`).** A neuroscience survey (working notes, not in this repo)
traced the recall@1 loss to the combination rule, not the decay curve. `recall` now resolves the entities the query names (one
bounded full-text read) and lifts their facts by an ACT-R context term over two cues, the entity and the predicate the query
names (`PLEXUS_RECALL_SEPARATION=on`, `PLEXUS_ACT_W_ENTITY` / `_W_PREDICATE`); the named entity's own facts
always join the candidates; the exact-keyword bypass tests the whole fact text. Pre-registered L5b re-run (same seed, 0 LLM
calls): recall@1 75.7% (78.6% on the current build) -> **85.7%** with forgetting off, recall@5 100%, every cross-entity displacer gone, the pre-registered
0.90 target **not reached** — and a later run showed why: the 20 residual misses are the scenario's 20 contradicting
`auth_method` pairs (same entity, same predicate, both active), so 85.7% is the ceiling for any value-blind scorer; the predicate
cue, pre-registered as the fix, changed no L5b rank (`docs/BASELINE.md` "Predicate cue results"). The additive forgetting mode built alongside it
(Pavlik-Anderson decay, graded salience) **failed** its pre-registered test (70.0%) and has been removed (reproduce at tag
`pre-cleanup`); the shipped default (`mult` + the two-cue separation, weights confirmed in a registered run) measures recall@1 85.7%, recall@5 100%,
noise share 33.3-41.4% on the current build (20.6-20.9% before the retrieval branches were merged; D-013 as first shipped: 85.0% / 100% / 22.1%; D-012 alone: 65.0% / 95.7% / 14.9%).
[`docs/DECISIONS.md`](docs/DECISIONS.md) D-013, [`docs/BASELINE.md`](docs/BASELINE.md) "L5b-D013" and "Predicate cue results".

> *(Partly stale: the `sep` / `sep+mult` runs were re-run on `7f28f60` (2026-10-18): recall@1 85.7%, recall@5 100%, critical loss 0 reproduced, noise share 33.3% (N = 5) / 41.4% (N = 15), so the 20.6-20.9% figure described the pre-merge build. The D-012-alone and D-013-as-first-shipped figures come from removed arms (`on-mult`, `sep+add`) measured on `3017ad7`: reproduce at `pre-cleanup`. See [docs/NUMBERS_STATUS.md](docs/NUMBERS_STATUS.md).)*

## Architecture

```mermaid
flowchart LR
    subgraph agents["Agents: unmodified Claude Code or any MCP client"]
        A1["planner"]
        A2["researcher"]
        A3["builder"]
        A4["your own agent"]
    end
    subgraph plexus["plexus (Python, no LLM)"]
        MCP["MCP server<br/>stdio or streamable HTTP<br/>tenant bound to the connection"]
        TOOLS["tool layer: 45 tools<br/>Engram, Relay, Lineage, staleness, forgetting<br/>one parameterised Cypher statement each"]
        API["View API<br/>read-only"]
    end
    DB[("FalkorDB 6.0.2<br/>one graph per tenant")]
    VIEW["plexus-view<br/>React + Cytoscape"]
    CRU["Crucible<br/>benchmark harness"]
    A1 & A2 & A3 & A4 -->|"MCP"| MCP
    MCP --> TOOLS
    TOOLS -->|"GRAPH.QUERY"| DB
    DB -->|"GRAPH.RO_QUERY"| API
    API --> VIEW
    CRU -->|"same tool API, four backends"| TOOLS
```

- **Engram** (memory), **Relay** (coordination) and **Lineage** (provenance) are three modules over one graph. They are
  Python wrappers around named `.cypher` files in [`plexus/queries/`](plexus/queries/); the loader rejects any parameter a
  header does not declare, and nothing is string-formatted into Cypher.
- **Every tool call is audited in the graph.** The MCP runtime opens a Lineage `Step` per (agent, n) and writes a `ToolCall`
  with `IN_STEP` and `CREATED`/`UPDATED` edges to the nodes it touched. The Flow page and the Time Machine are traversals of
  these edges.
- **The View never writes.** The API holds a read-only client (`GRAPH.RO_QUERY` only); `plexus-view` talks to it and nothing else.
- **No LLM inside Plexus (D-002).** Semantic matching uses a local CPU embedding model (bge-small via fastembed). The agents are
  unmodified Claude Code processes started with `claude -p ... --mcp-config`, signed in with the owner's own subscription;
  Plexus never sees a Claude credential. Hermes is not used in any published run (D-003). The decisions and their reasoning
  are in [`docs/DECISIONS.md`](docs/DECISIONS.md).
- **Crucible** swaps only the backend (files, SQLite, vector store, Plexus) behind an identical tool API; see
  [Benchmark results](#benchmark-results-crucible-honest).

## Graph data model

Full reference with every property, index and convention: [`docs/graph-model.md`](docs/graph-model.md). Every node has a
UUID `id` and `created_at` (epoch ms). There is no `datetime()` on FalkorDB 6.0.2, so time is integer epoch milliseconds, and an
open-ended `valid_to` is `9999999999999`.

```mermaid
erDiagram
    Agent ||--o{ Session : HAD
    Session ||--o{ Episode : HAS_EPISODE
    Episode ||--o| Episode : NEXT
    Fact }o--|| Entity : ABOUT
    Fact }o--o{ Episode : DERIVED_FROM
    Fact }o--o{ Source : DERIVED_FROM
    Fact }o--o{ Fact : "SUPERSEDES, CONTRADICTS, DUPLICATES"
    Fact }o--|| Scope : IN_SCOPE
    Scope }o--o| Scope : INHERITS
    Fact }o--|| Agent : ASSERTED_BY
    Procedure ||--o{ Run : USED_IN
    Run }o--|| Agent : BY
    Run }o--|| Task : FOR
    Task }o--o{ Task : DEPENDS_ON
    Agent ||--o{ Task : CLAIMED
    Handoff }o--|| Agent : "FROM, TO"
    Handoff }o--|| Task : FOR
    Handoff }o--o{ Artifact : CARRIES
    Handoff }o--o{ Fact : CARRIES
    Agent ||--o{ Decision : DECIDED
    Decision }o--o{ Fact : BASED_ON
    Decision }o--|| Task : FOR
    Artifact }o--|| Agent : PRODUCED_BY
    Step }o--|| Agent : BY
    Step }o--o{ Fact : READ
    Step }o--o{ Fact : WROTE
    Step ||--o| Step : NEXT
    ToolCall }o--|| Step : IN_STEP
    Recall }o--o{ Fact : RETURNED
    ToolCall }o--o{ Fact : "CREATED, UPDATED"
```

The diagram is a summary (cardinalities are indicative); the tables are exact.

| Label | Module | Key properties |
|---|---|---|
| `Agent` | all | `name, role, harness` |
| `Scope` | Engram | `kind: user\|project\|global, name` |
| `Session`, `Episode` | Engram | `Session(agent_id, started_at, ended_at)`; `Episode(role, text, at, step, embedding)` |
| `Entity` | Engram | `name, norm_name, kind, embedding` |
| `Fact` | Engram | `subject_id, predicate, value, valid_from, valid_to, status: active\|superseded\|quarantined\|forgotten, embedding` |
| `Source` | Lineage | `uri, kind, trust, title, text` |
| `Procedure`, `Run` | Engram | `Procedure(name, task_type, steps_json)`; `Run(at, success, notes)` |
| `Task` | Relay | `status: open\|claimed\|done\|failed, priority, lease_until, claimed_by, version` |
| `Handoff`, `Artifact`, `Decision` | Relay | `Handoff(at, note)`; `Artifact(kind, uri, hash, summary)`; `Decision(text, at, flagged)` |
| `Step`, `ToolCall`, `Recall` | Lineage, audit | `Step(n, at, agent_id)`; `ToolCall(tool, query_name, run_time_ms, wrote)`; `Recall(query, k)` |

| Module | Relationships |
|---|---|
| Engram | `HAD`, `HAS_EPISODE`, `NEXT` (episodes), `ABOUT`, `DERIVED_FROM` (→ Episode, Source or Fact), `IN_SCOPE`, `INHERITS`, `SUPERSEDES`, `DUPLICATES`, `CONTRADICTS`, `ASSERTED_BY {at}`, `USED_IN`, `BY`, `FOR` |
| Relay | `DEPENDS_ON`, `CLAIMED {at, lease_until, reclaimed_from}`, `FROM`, `TO`, `FOR`, `CARRIES`, `DECIDED`, `BASED_ON`, `PRODUCED_BY`, `VERIFIED_BY {at, independent}` |
| Lineage and audit | `Step -[:BY]-> Agent`, `READ`, `WROTE`, `NEXT` (steps), `IN_STEP`, `CREATED`, `UPDATED`, `RETURNED {rank, score}` |

Indexes: range indexes on `id` and `created_at` for all 16 labels plus the hot filters (`Fact.predicate/valid_to/status`,
`Task.status`, `Step.n`, `ToolCall.at`, `Entity.norm_name`); full-text on `Entity.name`, `Fact.value`, `Episode.text`;
384-d cosine vector indexes on `Entity/Fact/Episode.embedding`; UNIQUE constraints on `Task/Fact/Agent/Decision/Handoff.id`.
The recorded real run holds 247 nodes and 708 edges (14 labels, 26 relationship types).

## The Cypher queries the product depends on

Every statement lives in a named, parameterised file under [`plexus/queries/<area>/<name>.cypher`](plexus/queries/) with a
header (purpose, params, returns, mode) and is loaded by name; 114 files in all. The complete index with a "why it is a graph
query" for each is [`docs/queries.md`](docs/queries.md). The ones the product cannot work without:

| Query | What it does | Why it is a graph query |
|---|---|---|
| [`engram/assert_fact`](plexus/queries/engram/assert_fact.cypher) | Finds the entity's current facts, classifies duplicate / supersede / contradiction, writes the `Fact` with `ABOUT`, `IN_SCOPE`, `ASSERTED_BY`, `DERIVED_FROM`, `SUPERSEDES`, `CONTRADICTS` | Conflict detection and validity-window closing are traversals plus one atomic multi-edge write; per-graph write serialisation makes it race-free |
| [`engram/recall`](plexus/queries/engram/recall.cypher) | Hybrid recall: vector seeds, scope inheritance (`INHERITS*0..3`), validity filter at time `t`, 1-hop sibling expansion | Vector index seed, then scope and entity traversals, in one read |
| [`engram/remember_episode`](plexus/queries/engram/remember_episode.cypher) | Appends an `Episode` to the session's chain | The chain tail is found by traversal and extended atomically, so concurrent appends cannot fork it |
| [`relay/create_tasks`](plexus/queries/relay/create_tasks.cypher) | Creates a task DAG with `DEPENDS_ON` edges, all or nothing | The dependency graph is stored as edges |
| [`relay/claim_next_task`](plexus/queries/relay/claim_next_task.cypher) | Claims the best ready task (all `DEPENDS_ON` targets `done`, free or lease-expired), sets lease, `version+1`, `CLAIMED` edge | Readiness is a traversal; the claim is one serialised graph write, so two agents never win the same task (also covers dead-agent reclaim) |
| [`relay/dependents_closure`](plexus/queries/relay/dependents_closure.cypher) | Every task that transitively depends on a task, nearest first, in one statement | Transitive "what is blocked if T fails" (`blocked_by_failure`) |
| [`relay/handoff`](plexus/queries/relay/handoff.cypher) | `Handoff` + `FROM`/`TO`/`FOR` + `CARRIES` artifacts and facts; a bad id writes nothing | A handoff is a node linking agents, a task and its evidence, traversable later |
| [`relay/record_decision`](plexus/queries/relay/record_decision.cypher) | `Decision` with `DECIDED`, `FOR` and all-or-nothing `BASED_ON` facts | Decisions point at the exact facts they rest on |
| [`lineage/why_edges`](plexus/queries/lineage/why_edges.cypher) | Provenance subgraph of a decision or fact | Variable-length paths from decision to fact to agent, step and source: this is the "why" answer |
| [`lineage/knew_at`](plexus/queries/lineage/knew_at.cypher) | Time machine: facts an agent had read at or before step N that were still valid then, plus what it wrote | Step chain + `READ`/`WROTE` edges + the fact's validity window |
| [`lineage/as_of`](plexus/queries/lineage/as_of.cypher) | The fact valid at time t for (subject, predicate), nearest scope first | Entity → `ABOUT` → Fact with a validity filter and scope traversal |
| [`lineage/who_knew`](plexus/queries/lineage/who_knew.cypher) | Agents whose steps `READ` a fact, and who asserted it | `READ` edges one hop each way |
| [`lineage/forget_source`](plexus/queries/lineage/forget_source.cypher) | Marks every fact reaching a `Source` through up to 12 `DERIVED_FROM` hops (default 8, level by level) as forgotten (unless another `Source` still supports it: then only that link is dropped) and flags the decisions that rest on them | The cascade follows derivation edges, in one atomic write |
| [`lineage/quarantine`](plexus/queries/lineage/quarantine.cypher) | Reversible version of the above (stretch feature); hides a fact only when every one of its sources is quarantined; returns the blast radius (readers, decisions, handoffs) and the facts other sources keep alive | Blast radius is a traversal back out through `READ`, `BASED_ON`, `CARRIES` |
| [`audit/record_tool_call`](plexus/queries/audit/record_tool_call.cypher) | Writes a `ToolCall` with `IN_STEP` and `CREATED`/`UPDATED` edges to what the tool touched | The Flow page draws these edges |
| [`view/flow`](plexus/queries/view/flow.cypher) | Tool calls in order with the nodes each created or updated | A traversal of `ToolCall` → `CREATED`/`UPDATED`; also the SSE feed |
| [`crucible/strip_edges`](plexus/queries/crucible/strip_edges.cypher) | **Ablation only:** deletes `DEPENDS_ON`, `BASED_ON`, `DERIVED_FROM`, `READ` in bounded batches | Measures which features break without the edges |

Three of them in the form the demo uses (run in the FalkorDB Browser on graph `plexus_t_demo`, or see
[`docs/demo.md`](docs/demo.md) for more):

```cypher
// Why did the team move to v2?
MATCH (d:Decision) WHERE d.text STARTS WITH 'Adopt'
MATCH (d)-[:BASED_ON]->(f:Fact)-[:DERIVED_FROM]->(s:Source)
MATCH (f)-[:ASSERTED_BY]->(a:Agent)
OPTIONAL MATCH (f)-[:SUPERSEDES]->(old:Fact)
RETURN d.text, f.value, a.id, s.uri, old.value   // v2, researcher, acme-docs/06_api_style_guide_v2.md, v1

// Who reclaimed what after the builder died?
MATCH (a:Agent)-[c:CLAIMED]->(t:Task) WHERE c.reclaimed_from <> ''
RETURN a.id, t.id, c.reclaimed_from              // researcher, t03-design-endpoints, builder

// Which decisions rest on a fact that is no longer true?
MATCH (d:Decision)-[:BASED_ON]->(f:Fact) WHERE f.status <> 'active' RETURN d.text, f.value, f.status
```

## Why FalkorDB is the core (and the ablation that shows it)

FalkorDB is the only state store. There is no SQLite or JSON copy of the memory. Recall, dependency-aware claims, `why`,
time travel, contradiction detection, forget cascades and tenant isolation are graph queries, and the Flow page is a
traversal of the audit edges.

The test of that claim is an **ablation**: delete four relationship types (`DEPENDS_ON`, `BASED_ON`, `DERIVED_FROM`, `READ`)
and see what stops working.

> *(stale: the Crucible ablation figures below were measured on `84763aa`, 2026-10-15. The live ablation's 6 of 6 / 2 of 2 is asserted by the current test suite (current); the counts quoted from the Sonnet recording's output were measured on the P3 demo build (stale). See [docs/NUMBERS_STATUS.md](docs/NUMBERS_STATUS.md).)*

- **Crucible ablation** ([`docs/BASELINE.md`](docs/BASELINE.md)): **7 of 7** capabilities that use those edges break
  (dependency-aware claims, `blocked_by_failure`, `why` for decisions and for facts, `knew_at`, `who_knew`, cascading forget);
  **5 of 5** controls are unaffected (as-of, recall, contradiction flags, supersession, exclusive claims). Re-running the
  dependency-order test (C4) with the edges stripped gives 149 tasks started before their dependencies finished, and the
  forget test (C8) gives 60 forgotten facts still returned (0 and 0 on the intact graph).
- **Live version on the real recording** (`plexus demo ablation`: 6 edge-dependent features and 2 controls on the demo
  tenant, a smaller set than Crucible's):

  ```bash
  docker compose run --rm plexus-cli demo ablation --tenant demo
  ```

  It copies the tenant with `GRAPH.COPY`, strips the four edge types in the copy and runs the same probes on both. Output on
  the Sonnet recording: `why(decision)` goes from "3 supporting facts, 2 agents, 3 sources" to 0 facts and 0 sources;
  `knew_at` from 5 facts to 0; with `DEPENDS_ON` gone, 11 tasks are claimable on a fresh board with unmet dependencies;
  **6 of 6 features break, 2 of 2 controls are unaffected**, and the original tenant is verified untouched. Open the copy
  (`demo_ablated`, kept unless you pass `--drop`) in the View to see the same graph without those edges. Details:
  [`docs/demo.md`](docs/demo.md).

What the ablation does **not** show: that nothing else could store these relations. SQLite (B1) answers some of the same
provenance questions with recursive CTEs, and the benchmark below reports where it ties.

## Benchmark results (Crucible, honest)

Crucible swaps only the backend behind an identical tool API: **B0** files (flock + atomic replace), **B1** SQLite
(transactions), **B2** vector store (same local embedder), **P** Plexus. Everything else is fixed (same agents' prompts,
model, scenario, budgets, seeds). Exact-match scoring, no LLM judge. Full methodology, pre-registration and failure analysis:
[`docs/BASELINE.md`](docs/BASELINE.md); the same numbers are in the View's Results page.

> **Partly STALE (2026-10-18):** re-run on `rerun-current` and CURRENT: L1, L4, ablation (`fb8e02f`), L2 and L2 at scale (re-scored from the cache), B1h, C7 extended, L6 A-F and L6-C (values that moved are stated in the table). Not re-run, still STALE: the L6 LLM pilot (`dc83183`..`5871d30`), L3, L7, L8. Reproduce a number by checking out its build (or tag `pre-cleanup` for the build just before the dead-code cleanup). Per-number table: [docs/NUMBERS_STATUS.md](docs/NUMBERS_STATUS.md).

| Layer | What we found | How to read it |
|---|---|---|
| **L1** correctness under concurrency (C1-C8, 10 seeded runs per case) | **All four arms pass with 0 violations.** Plexus does **not** win on claims, leases, dependency order, as-of, tenant probes or forgetting: a competent file store or SQLite ties it. The one measured difference: C7 near-duplicate paraphrases, where B0/B1 catch 0%, B2 misses 25% (30 of 120 pairs) and Plexus misses 50% (60 of 120 pairs: the stricter P9-c duplicate rule merges fewer paraphrases and merges no different statement; see C7 extended) | The graph is not claimed to be more correct on these |
| **L4** performance | **SQLite is faster than Plexus on the median claim at every worker count** (0.12 vs 4.9 ms at 1 worker; 0.80 vs 720.9 ms at 200) but has worse tail latency at 200 workers (p99 4.76 s vs 1.46 s). Plexus server-side time stays under 4 ms for claims; the rest is queueing, because FalkorDB serialises writes per graph. **Plexus scales across tenant graphs: 112 → 202 → 459 ops/s on 1, 4, 16 graphs (+311%)**; SQLite also rose in the re-run (425 → 889 → 1771; the first run had it fall to 500 at 16 files, so that contrast is not reproduced). `recall` is the slow path now: 2-6 ops/s, 77-110 ms server-side at 300 facts (it was about 10 ms before the ranking terms were added) | Raw claim speed is not Plexus's case. B0/B1/B2 are in-process libraries and the Plexus arms cross a container network |
| **L2** provenance and time questions (43 questions, one Acme project) | **Tie on accuracy:** P 43/43, B0 43/43, B1 43/43, B2 40/43 (93.0%). The whole history fits in the 32k-character context, so the LLM reads everything. Plexus costs 0 tokens (vs 13-16k tokens and $0.05-0.06 per question for B0/B1) and ~2.5 ms vs ~5 s | A tie on accuracy; the difference is cost, latency and determinism. Plexus uses a hand-written Cypher per question family |
| **L2 at scale** (pre-registered; 20 sprints of history, 10.4-16.6× the context cap, 36 questions) | **P 36/36 (100%), B1 32/36 (88.9%), B0 30/36 (83.3%), B2 23/36 (63.9%).** Wilson 95%: P 90.4-100, B1 74.7-95.6, B0 68.1-92.1, B2 47.6-77.5. Paired sign test: P vs B0 6-0, p = 0.031; **P vs B1 4-0, p = 0.125, not distinguishable from noise**; P vs B2 13-0, p < 0.001. B0/B1 failures were join-heavy provenance questions and one transitive dependency, not class-wide questions; accuracy did not decay with how early the sprint was. B0/B1 spent about 20-22k tokens and $0.08-0.09 per question (about 5 s) against 0 tokens and a few milliseconds | A gap, but a small one: the intervals of P and B0/B1 overlap, and the B1 gap is within sampling noise. Not a claim that Plexus is "better at memory" in general |
| **B1h** hand-written SQL control on the same L2 and L2-scale questions | **SQL ties:** B1h 43/43 on L2 and 36/36 on L2-scale, the same as Plexus, at 0 LLM calls | On questions a SQL author can write, a relational schema answers as many as the graph. The advantage over B0/B1/B2 is a structured record, not graph storage as such |
| **C7 extended** (226 labelled pairs; negations, units, number words, near-twins) | **0 false merges in 150 pairs that must stay apart** (every category, both splits; < 2.0% at 95% by the rule of three); the old rule (B2) falsely merged 68 of 150. **Targets missed:** heavy paraphrases are auto-merged 10 of 24 and surfaced for review 19 of 24, against a pre-registered 75% auto or 95% surfaced; light paraphrases 10 of 20 and unit rewordings 11 of 12 against 100% auto | Precision is the claim, recall of heavy rewordings is not. A close-but-different pair becomes a soft `DUPLICATES_MAYBE` link instead of a silent merge |
| **L6** five pre-registered families where a graph could beat SQL (blast radius, why-depth, cross-sprint aggregation, consistent reads, crash-consistency) | **A tie or a SQL win in every family.** A: SQL ties the hand-tuned graph query and the product's `impact` tool did not finish at 5,000 facts (fixed: see below); B: tie when the call passes depth 12 (the MCP tool exposes it now; the tool path itself was not re-run); D: both 24/24, SQL 3.6x faster; E: 0 violations for every single-statement arm, the product's own level-wise traversal tears; F: Plexus lost (94 of 1,240 records without their `WROTE` edge; fixed for `assert_fact`, `record_decision` and `handoff`, see below). LLM pilot (8 questions per family): B1a 24/24, B0g 24/24, B0r 2/24, Plexus MCP tools 10/16, 88 calls, $7.09. **C (run later, D-013 §5.4): multi-hop recall with a fan-weighted rule, hand-written SQL and Cypher both 75/75 with identical lists; SQL 3-6x faster at depth 3; the shipped `recall(hops)` 0/75 in the top 5.** The same phase's L5b SQL arm ties the shipped ranking within one probe (recall@1 85.7 vs 85.0, 85.7 vs 85.7, 85.7 vs 84.3 in three runs, recall@5 100% on both, 92 lines of SQL vs 104 of Cypher; the two top-1 lists no longer agree probe by probe) | The graph is not found to beat a competent SQL schema in any family, including ranking and multi-hop recall; the product defects the run exposed were fixed and re-run, except the `recall(hops)` ranking found by C, which is recorded as the next fix |
| **Ablation** | 7 of 7 edge-dependent capabilities break, 5 of 5 controls unaffected | The graph does real work (above) |

**What the results support.** Plexus makes provenance, dependencies and time first-class edges in FalkorDB, so *why*, *who knew* and *what is
affected* are single deterministic queries (zero tokens, milliseconds). Against flat files and tool-less LLM readers that is a large cost and
latency win, and a measurable accuracy win once histories exceed the context. A well-built relational schema with recursive CTEs matches Plexus on
correctness and is faster on simple claims; we publish that tie (B1h, L6), the benchmark, and the cases where we lose. L6 in one line: no family
shows the graph beating hand-written SQL, and two product defects it exposed (an `impact` query that never finished at 5,000 facts, and a
provenance edge that a crash could lose) were fixed and re-measured.

**Methodology limits** (the Results page and `report.md` print the full list): synthetic data; one scenario family; one model
(`claude-sonnet-5-5`); LLM arms run once per question; 36-43 questions; scripted worker threads on one machine against a
single-node database; the L2 baselines see their own artifacts at an equal 32,000-character cap, selected by BM25 or top-12
cosine; Plexus answers each question family with hand-written Cypher, which favours Plexus, while every L2-scale question
names its sprint, which favours retrieval; L2-scale asks no questions that aggregate across sprints (the strongest case for a
graph), and the procedures family was not measured; L3 (end-to-end LLM teams with injected faults) was only piloted and is not
in the results; Hermes is excluded from all published runs. Do not compare these numbers with vendor-reported LoCoMo or
LongMemEval scores. Raw files: [`plexus/src/plexus/crucible/results/`](plexus/src/plexus/crucible/results/).

Reproduce: `docker compose --profile bench run --rm crucible all --quick` (about 2 min; the full run takes about 24 min)
writes L1 + L4 + ablation. The L2 and L2-at-scale answers are cached in `plexus/demo_data/crucible/`, so a rerun is free and
byte-reproducible; `python -m plexus.crucible.combine` merges everything into `latest-all.json`, which the Results page serves.

## Live demo

`<RENDER_URL>`: one Docker container on Render Free runs FalkorDB 6.0.2, the read-only View API and the static View. The MCP
server is **not** deployed until it is stable ([D-016](docs/DECISIONS.md)). How to deploy it yourself (the CI gate, the
keep-awake check) and the safety controls: [`docs/deploy.md`](docs/deploy.md).

- **Read-only tenants `demo`** (the real Claude Sonnet recording) **and `demo_scripted`** are restored from the recordings on
  every boot. Browse them in the View: pick the tenant in the header.
- **Run your own Cypher** on the **Cypher** page (`POST /api/{tenant}/cypher`). It is read-only (`GRAPH.RO_QUERY`: the server
  refuses writes), 3 s timeout, at most 500 rows, no `LOAD CSV`, `CALL` limited to read procedures, 20 queries per minute per IP.
- **No LLM runs on the public site.** The only LLM runs are the recorded ones.
- Request bodies to the console are capped at 16 KiB. Nothing visitors do changes the graph; a restart reseeds it.
- Verified locally under `-m 512m --cpus 0.5` (36/36 checks of `deploy/verify.py`): boot in about 4 s, peak 88 MiB (cgroup;
  83 MiB by `docker stats`). The deployment on Render itself has not been verified yet.
- The first request after 15 idle minutes wakes the service (about a minute plus the reseed) unless the `live-smoke` workflow
  or an uptime pinger keeps it awake.

## Setup

You need **Docker with Compose v2** and nothing else (no Python, no Node). The first `up` builds two images (about 4 minutes,
about 1 GB of images including FalkorDB). This exact path was run from a fresh clone (4 services healthy after 216 s, then the
replay; evidence in [`docs/TESTING.md`](docs/TESTING.md); the 216 s is stale, measured on `p5-int`).

```bash
git clone <this repo> plexus && cd plexus
cp .env.example .env                    # optional: the defaults work; edit it only if a host port below is already taken
docker compose up -d --wait --build     # builds and starts FalkorDB 6.0.2, the View API, the MCP server and the View
                                        # (--build matters if an older plexus:dev image exists: compose would reuse it)
docker compose run --rm plexus-cli demo replay acme-claude-sonnet --tenant demo    # load the recorded real Claude Code run
```

| Open | What |
|---|---|
| http://localhost:5180 | **The View.** Pick tenant `demo` in the header: Explorer, Flow, Time Machine, Why, Inventory and **Results** (the Crucible benchmark: L1, L2, L2 at scale, L4, ablation) |
| http://localhost:3000 | FalkorDB Browser (the raw graph: graph `plexus_t_demo`) |
| http://localhost:8080/api/tenants | the read-only View API (`/api/demo/inventory`, `/api/demo/graph`, `/api/results`, ...) |
| http://localhost:8765/mcp/t/demo | the MCP server (streamable HTTP, tenant `demo` pinned by the path). It is an MCP endpoint, not a web page: a plain browser GET answers `Bad Request: Missing session ID`, which is normal. Connect an MCP client (see [Bring your own agent](#bring-your-own-agent)) |

**How you know it worked:** the replay prints `replayed 'acme-claude-sonnet' into tenant 'demo': 247 nodes, 708 edges (matches
meta.json: True)`; Inventory shows 247 nodes, 708 edges, 14 labels, 26 edge types; Flow lists 83 tool calls; Results shows
L1 all-pass and the L2-at-scale section. If the View's tenant list is empty, the replay has not run yet.

The replay restores a recording of three unmodified Claude Code agents (planner, researcher, builder) building the fictional
"Acme Notes API". `docker compose run --rm plexus-cli demo list` shows the other recordings. Ports are `FALKORDB_PORT`,
`FALKORDB_BROWSER_PORT`, `PLEXUS_API_PORT`, `PLEXUS_MCP_PORT` and `PLEXUS_VIEW_PORT` in `.env`; after changing
`PLEXUS_API_PORT` or `PLEXUS_VIEW_PORT` run `docker compose up -d --build` (the View bakes the API address into its bundle).
All compose ports are published on `127.0.0.1` only.

**More to try** (all synthetic data; no LLM and no credentials are involved in any of it):

```bash
# watch the Flow page while scripted agents play the whole scenario (builder killed, task reclaimed, style guide v1 -> v2)
docker compose run --rm plexus-cli demo live --scripted --tenant live --speed 4
# cut DEPENDS_ON / BASED_ON / DERIVED_FROM / READ in a copy of the tenant and see which features break (docs/demo.md)
docker compose run --rm plexus-cli demo ablation --tenant demo
# the benchmark itself (L1 + L4 + ablation; ~20 min full, --quick ~2 min): results land in plexus/src/plexus/crucible/results/
docker compose --profile bench run --rm crucible all --quick
docker compose down -v                  # stop and delete everything
```

The Results page reads `plexus/src/plexus/crucible/results/latest-all.json` (L1 + L4 + ablation from the compose run, merged
with the full L2 and L2-scale runs by `python -m plexus.crucible.combine`), mounted into the API as `PLEXUS_RESULTS_PATH`.

### Bring your own agent

Any MCP client can connect. The server has 45 tools (`start_session`, `assert_fact`, `recall`, `claim_next_task`,
`record_decision`, `why`, `knew_at`, ...; the list is in [`docs/mcp.md`](docs/mcp.md)). Every tool takes an `agent_id`; the
tenant is part of the connection, never an argument.

**Against the public demo:** not available. The MCP endpoint is not deployed until it is stable (D-016); run the local stack
(`docker compose up -d --wait --build`) and connect to `http://127.0.0.1:8765/mcp/t/<tenant>`.

```bash
claude mcp add --transport http plexus http://127.0.0.1:8765/mcp/t/alice
# or in a config file:  { "mcpServers": { "plexus": { "type": "http", "url": "http://127.0.0.1:8765/mcp/t/alice" } } }
claude    # then ask: "Use the plexus tools as agent 'alice': start a session, assert the fact subject=API predicate=version value=v1,
          #            then assert value=v2, recall 'API version', and call why/as_of to show what changed"
```

**Against your local stack** (tenant `byo` is created on first use; leave `demo` alone if you want the recording untouched):

```bash
claude mcp add --transport http plexus http://127.0.0.1:8765/mcp/t/byo         # streamable HTTP, compose service plexus-mcp
# or stdio, generated for this checkout (fastest start-up; needs Python 3.12 + uv, see the contributor block below):
cd plexus && uv sync && FALKORDB_PORT=6379 uv run plexus mcp-config --tenant byo --out ../mcp.local.json
claude --mcp-config ../mcp.local.json
```

To question the recorded run with your own Claude Code, point it at tenant `demo` on the local stack
(`http://127.0.0.1:8765/mcp/t/demo`; your calls add audit nodes to that tenant) and ask: *"Use the plexus tools: recall the
API version, then explain why we chose v2."* Expect `start_session`, `recall` (value `v2`) and `why` on the "Adopt API v2"
decision. For headless `claude -p`, pass `--allowedTools "mcp__plexus__*"` and check `permission_denials` (a blocked tool
still exits 0). Details: [`docs/mcp.md`](docs/mcp.md).

<details><summary>Without Docker for the app (Python 3.12 + <code>uv</code>, Node 22+): contributors and the full test suite</summary>

```bash
docker compose up -d falkordb                       # or scripts/agent_db.sh <slot> for a throw-away test database
cd plexus && uv sync
FALKORDB_PORT=6379 uv run plexus demo replay acme-claude-sonnet --tenant demo
FALKORDB_PORT=6379 uv run plexus-api &             # View API on :8080
cd ../plexus-view && npm ci && npm run dev         # View on http://localhost:5180 (VITE_FIXTURES=1 for the built-in dataset)
cd ../plexus && uv run plexus mcp-config --tenant demo   # an MCP config for Claude Code for this checkout (docs/mcp.md)
```

Quick dev loop (the full gate and the owner's manual checklist are in `docs/TESTING.md`):

```bash
bash scripts/agent_db.sh 10                                   # FalkorDB 6.0.2 on 127.0.0.1:6310
cd plexus && PLEXUS_TEST_DB_PORT=6310 uv run pytest -q        # throwaway graphs, deleted in teardown
bash ../scripts/agent_db.sh rm 10
```

</details>

## Repo layout

```text
plexus/                  the product (Python 3.12, uv)
  queries/<area>/*.cypher  every Cypher statement, named and parameterised (114 files)
  src/plexus/            graph (client, schema, tenancy), engram, relay, lineage, audit, mcp, api, embed, demo, crucible
  demo_data/             the Acme scenario, recordings (acme-claude-sonnet, acme-scripted, pilot-haiku), Crucible questions and caches
  tests/                 pytest against throw-away graphs
plexus-view/             the demonstrator (React + TypeScript + Cytoscape); read-only
deploy/, render.yaml     the one-container public deployment
docs/                    graph-model, queries, DECISIONS, BASELINE, demo, mcp, deploy, TESTING, AI_USAGE, NUMBERS_STATUS, forgetting, staleness
scripts/                 agent_db.sh (throw-away FalkorDB), verify_readme.py (link and number checker)
docker-compose.yml       FalkorDB 6.0.2, plexus-api, plexus-mcp, plexus-view, plexus-cli, crucible (bench profile)
```

## Testing

[`docs/TESTING.md`](docs/TESTING.md) has the Definition of Ready for Testing with evidence and a step-by-step manual
checklist. At the last full run, 1512 Python tests and 229 View tests passed (plus the unit tests for the deploy guard and app), and
`ruff` and the View's lint and typecheck were clean; tests that need a database use their own throw-away graphs. Known gaps
are listed there too: for example, a real Claude Code run has driven only 14 of the 45 tools (11 in the Acme run, 3 more in the P7 physio run; all 45 have an MCP contract
test), and the L1/L4 benchmark and the LLM arms are separate commands. `python scripts/verify_readme.py` checks that every
link in this README, the video script and the blog draft resolves and that the quoted numbers still match the results files.

> *(stale: the 1512 / 229 counts and the 55 guard-test count (now 61 deploy tests, run on this branch) were measured on `p9int` (2026-10-16). The current main passes 1825 Python tests with 2 skipped (full suite on the `integ` tree, identical to `7618d18`); the View and deploy-guard counts have not been re-run. See [docs/NUMBERS_STATUS.md](docs/NUMBERS_STATUS.md).)*

## Docs

- [`docs/graph-model.md`](docs/graph-model.md): graph data model (diagram, labels, edges, indexes)
- [`docs/queries.md`](docs/queries.md): index of every Cypher query
- [`docs/BASELINE.md`](docs/BASELINE.md): benchmark plan, results, pre-registration of L2-scale
- [`docs/demo.md`](docs/demo.md), [`docs/mcp.md`](docs/mcp.md), [`docs/deploy.md`](docs/deploy.md): the demo scenario and ablation, the MCP server, the public deployment
- [`docs/DECISIONS.md`](docs/DECISIONS.md): every design decision with its reasoning
- [`docs/TESTING.md`](docs/TESTING.md), [`docs/NUMBERS_STATUS.md`](docs/NUMBERS_STATUS.md), [`docs/forgetting.md`](docs/forgetting.md), [`docs/staleness.md`](docs/staleness.md)

Plans, research notes, the video script and blog drafts that these documents cite by path are working files and are not in the repository.

## AI disclosure

Plexus was built with AI assistants: a Hermes Agent orchestrator and Claude Sonnet subagents wrote most of the code, tests,
queries and docs from specs, and unmodified Claude Code (the owner's own subscription) plays the demo agents and answers the
benchmark baselines; the product itself contains no LLM. The owner reviews the graph model, the `.cypher` files and the
architecture and records decisions in `docs/DECISIONS.md`; what has and has not been reviewed yet is stated, phase by phase,
in [`docs/AI_USAGE.md`](docs/AI_USAGE.md) (items marked _TBD_ are not yet reviewed).
