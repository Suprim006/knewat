# Plexus: the full report

**One shared graph brain for AI agent teams.** Graph Hacks (WeMakeDevs × FalkorDB), **Track 02: Agent Memory and
Coordination**.

This one document covers:
- the problem;
- the method we used to build and measure Plexus;
- why FalkorDB is the core of it rather than a storage detail;
- what we found;
- what is still weak.

Every number below comes from a file in this repo. The source is named next to each claim, so it can be checked.

---

## Contents

1. [Problem statement](#1-problem-statement)
2. [What Plexus is](#2-what-plexus-is)
3. [How FalkorDB is the core](#3-how-falkordb-is-the-core)
4. [Methodology: how it was built](#4-methodology-how-it-was-built)
5. [Methodology: how it was measured (Crucible)](#5-methodology-how-it-was-measured-crucible)
6. [Findings](#6-findings)
7. [Memory that notices change, and forgetting (P7)](#7-memory-that-notices-change-and-forgetting-p7)
8. [Shortcomings and limits](#8-shortcomings-and-limits)
9. [What we would do next](#9-what-we-would-do-next)
10. [Where to find everything](#10-where-to-find-everything)

---

## 1. Problem statement

### 1.1 The track's brief

> "Build agents that remember across sessions and share state with each other. Memory should persist, update over time,
> and be available to every agent that needs it."

The brief's focus areas:
- episodic, semantic and procedural memory;
- persistent conversation history;
- shared state and handoffs between agents;
- high-concurrency reads and writes;
- separate memory per user or tenant.

### 1.2 How today's agents remember and coordinate

We surveyed coding agents, memory layers and multi-agent frameworks. The cited survey is in
`docs/research/landscape/1-agent-products.md`, `2-memory-layers.md` and `3-coordination.md`. The common pattern:

| Product | How it remembers | Documented limits |
|---|---|---|
| **Claude Code** | `CLAUDE.md` hierarchy plus auto-memory as Markdown files in `~/.claude/projects/<project>/memory/`, machine-local | Index capped at 200 lines / 25 KB; conflicting rules are picked "arbitrarily" (Claude Code memory docs) |
| **Hermes Agent** | `MEMORY.md` (2,200 chars) + `USER.md` (1,375 chars), SQLite FTS5 session search, skills | Hard character caps; global memory with no project or tenant boundary |
| **Mem0, Letta, Graphiti, Zep** | Vector + entity stores, shared memory blocks, temporal knowledge graphs | Concurrent-writer races (Mem0 issue #6515), last-writer-wins shared blocks (Letta), invalidation decided by an LLM and inconsistent (Graphiti issue #1841) |
| **Claude Code agent teams, Hermes subagents, CrewAI, LangGraph** | A task list or kanban plus self-reported summaries from subagents | Handoffs and decisions are free text, not queryable objects |

### 1.3 The eight gaps

These gaps come from `docs/research/PROJECT_IDEAS.md`. Each is cited in the landscape files.

| # | Gap | What goes wrong |
|---|---|---|
| **G1** | **Handoffs, claims and decisions aren't first-class, queryable objects** | Subagents return self-reported summaries. No product or benchmark models `Task`, `Handoff` or `Decision` as data, so "who handed what to whom, based on what?" can't be answered. |
| **G2** | **No consistency story for concurrent writers** | Duplicates are created in races, the last writer wins, and the documented advice is "designate one owner". |
| **G3** | **No temporal validity** | A stale fact stays "current" next to its replacement. When invalidation exists, an LLM decides it inconsistently. |
| **G4** | **Memory isn't scoped** | Memory is global or per repo, with no tenant, project or agent boundary. |
| **G5** | **No conflict detection between agents' facts** | Two agents assert opposite things and nobody notices. A 2026 position paper (arXiv 2603.10062) says memory consistency "has not been formally defined and no framework detects violations". |
| **G6** | **Provenance and "why was this recalled" are partial or missing** | Precise forgetting and containing poisoned memory become impossible. MAPLE-Guard shows one poisoned write promoted into shared memory contaminates agents that never saw the attack; gating cut attack success from 38.2% to 0.9%. |
| **G7** | **Procedural memory doesn't learn from outcomes** | Skills are counted by usage, not by success. |
| **G8** | **No benchmark covers concurrency, handoffs, tenant leaks or invalidation** | LoCoMo, LongMemEval and MemoryAgentBench test recall over dialogue. LoCoMo itself was audited to contain 99 score-corrupting answer-key errors (6.4% of 1,540). |

The MAST failure taxonomy (Cemri et al., arXiv 2503.13657; 1,600+ traces from 7 frameworks) puts numbers on G1, G3 and G5.
The largest failure modes are:

| Failure mode | Share of failures |
|---|---|
| Step repetition (duplicated work) | 15.7% |
| Reasoning–action mismatch | 13.2% |
| Missing completion recognition | 12.4% |

### 1.4 First-hand evidence from building this project

We saw several of these gaps while building Plexus with a multi-agent setup (Hermes orchestrating Claude subagents):

- **G2/G4 in practice:**
  - an exported `DATABASE_URL` leaked between parallel subagents and broke isolation;
  - later, a subagent's runaway write killed the shared FalkorDB container, and about 20 minutes of other agents'
    data was lost (`docs/DECISIONS.md` D-005).
- **G1 in practice:** parallel subagents returned only self-reported summaries. The orchestrator had to re-verify every
  claim, re-run every test gate and read every diff before merging.
- **G3 in practice:** the orchestrator's own memory still said "Docker is broken" after Docker had been fixed. Two
  contradictory notes sat side by side, with nothing to say which was current.
- **G4 in practice:** notes about an unrelated project (an HR payroll backend) were injected into this project's
  context, because the memory was global.

### 1.5 The problem in one sentence

> A team of AI agents has no shared memory that knows **what is true now**, **what changed and when**, **who knew what
> when they acted**, and **why a decision was made**. It also has no way to share work without stepping on itself when
> agents crash or race.

---

## 2. What Plexus is

### 2.1 In one paragraph

Plexus is a service that agents connect to over **MCP** (Model Context Protocol). It exposes **41 tools**. Each tool is
**one deterministic, parameterised Cypher query** (or a short fixed sequence of them) against a **FalkorDB graph per
tenant**:
- every memory, task, claim, handoff and decision is a node;
- every "because" (based on, derived from, depends on, supersedes, read, wrote) is an edge.

Plexus contains **no LLM and holds no LLM credentials**. The agents are unmodified Claude Code processes, and any MCP
client can connect. Semantic matching uses a small local embedding model (`BAAI/bge-small-en-v1.5`, 384 dimensions,
via fastembed, int8 ONNX on CPU), so it needs no API key and has no running cost.

### 2.2 Modules

| Module | Purpose | Gaps it targets | Main tools |
|---|---|---|---|
| **Engram** | Memory: episodic (sessions → episode chains), semantic (scoped facts about entities with validity windows), procedural (procedures → runs with success rates) | G2, G3, G4, G5, G7 | `start_session`, `remember_episode`, `assert_fact`, `recall`, `fact_history`, `log_procedure_run`, `best_procedure` |
| **Relay** | Coordination: dependency-aware atomic claims with leases, heartbeats, complete/fail with version checks, handoffs carrying artifacts and facts, decisions linked to their evidence | G1, G2 | `register_agent`, `create_tasks`, `claim_next_task`, `heartbeat`, `complete_task`, `fail_task`, `reopen_task`, `handoff`, `verify_artifact`, `record_decision`, `ready_tasks`, `task_status`, `blocked_by_failure` |
| **Lineage** | Provenance and time: steps per agent, READ/WROTE edges, recall records, "why", "who knew", "what did X know at step N", "as of T", forgetting by source, quarantine | G6 | `add_source`, `why`, `why_recalled`, `who_knew`, `knew_at`, `as_of`, `forget_source`, `quarantine_source`, `release_quarantine` |
| **Staleness** (P7) | Memory that notices change: facts anchored to files and Python symbols become **suspect** when the code changes (a Claude Code hook or git hook reports hashes); the agent re-verifies and the old fact is closed at the change's time | G3 (code ↔ memory drift) | `anchor_fact`, `describe_code`, `mark_changed`, `verify_fact`, `facts_to_verify`, `docs_to_update`, `set_review_date`; CLI `plexus code scan\|baseline\|hook-claude\|hook-git` |
| **Forgetting** (P7) | Activation-based ranking (ACT-R power-law decay over the use history already in the graph) with write-time surprise; facts fade in rank, never deleted; decision-supporting facts protected | memory hygiene (noise, growth) | `pin_fact`, `unpin_fact`, `memory_strength`, `memory_sweep` (dry-run, reversible), `restore_fact`; `recall(forgetting=…)` |
| **Audit** | Every tool call becomes a `ToolCall` node linked to its step and to every node it created or updated | feeds the viewer; makes the system observable | (automatic) |
| **Crucible** | The benchmark: the same tool API over four backends, then correctness, provenance, end-to-end and performance layers | G8 | `crucible` CLI |
| **plexus-view** | A read-only React + Cytoscape viewer: Explorer, Flow, Time Machine, Why, Inventory, Results | makes the memory visible | (web UI) |

### 2.3 Architecture

```mermaid
flowchart LR
  subgraph Agents
    A1[Claude Code: planner]
    A2[Claude Code: researcher]
    A3[Claude Code: builder]
    A4[any MCP client]
  end
  A1 & A2 & A3 & A4 -->|MCP stdio or HTTP, tenant bound per connection| MCP[Plexus MCP server: 41 tools]
  MCP -->|"parameterised Cypher (one statement per write)"| FDB[(FalkorDB 6.0.2: one graph per tenant)]
  MCP --> EMB[local embedder bge-small, CPU]
  API[View API, FastAPI, read-only] -->|GRAPH.RO_QUERY only| FDB
  VIEW[plexus-view: React + Cytoscape] --> API
  CRU[Crucible benchmark] --> MCP
  CRU --> B[B0 files / B1 SQLite / B2 vector]
```

### 2.4 Tenancy and safety

- **Tenant binding:** the tenant is bound **per connection**: `--tenant` for stdio, or the URL path `/mcp/t/<tenant>`
  for HTTP. It is never a tool argument, so an agent can't address another tenant's graph.
- **Graph names:** `plexus_t_<tenant>` with `^[a-z0-9_]{1,48}$`.
- **HTTP sessions** are pinned to the tenant that created them. A replayed session id under another tenant is
  refused, and pinning fails closed (an unknown session id gets 404).
- **Input limits:** every argument has a size or range limit: ids ≤ 128 chars, values ≤ 20 kB, texts ≤ 100 kB,
  lists ≤ 200, leases ≤ 24 h, steps 1..2³¹-1. Misspelled keys are rejected with the expected keys named.
- **Public deployment:** writes are allowed only on `team_*` tenants. The `demo*` tenants are read-only. There is a
  rate limit (60 requests/min/IP), a 512 KiB body cap, a 50-graph cap and a 24-hour idle sweep (`docs/deploy.md`).

---

## 3. How FalkorDB is the core

Hackathon rule R2: *"If the product still works with FalkorDB removed, it doesn't qualify."* We designed against a
stricter test: **every feature must need a graph traversal or a graph write to work.**

### 3.1 FalkorDB is the only state store

There is no SQLite, no JSON file and no separate vector store behind Plexus. All of these live in the FalkorDB graph:
- memory, tasks, claims, leases and steps;
- recall records, tool-call audit records and embeddings;
- the vector and full-text indexes.

Restart the MCP server and nothing is lost. Point it at an empty graph and the team has no memory.

### 3.2 The graph model

| | Count | Details |
|---|---|---|
| Node labels | 18 | `Agent`, `Scope`, `Session`, `Episode`, `Entity`, `Fact`, `Source`, `Procedure`, `Run`, `Task`, `Handoff`, `Artifact`, `Decision`, `Step`, `ToolCall`, `Recall`, `CodeAnchor`, `Change` (v1.1) |
| Edge types | about 35 | listed below by module |

Full tables are in `docs/graph-model.md`; the edge types by module:

| Module | Edges |
|---|---|
| Engram | `HAD`, `HAS_EPISODE`, `NEXT`, `ABOUT`, `DERIVED_FROM`, `IN_SCOPE`, `INHERITS`, `SUPERSEDES`, `CONTRADICTS`, `DUPLICATES`, `ASSERTED_BY {at}`, `USED_IN`, `BY`, `FOR` |
| Relay | `DEPENDS_ON`, `CLAIMED {at, lease_until, reclaimed_from}`, `FROM`, `TO`, `CARRIES`, `DECIDED`, `BASED_ON`, `PRODUCED_BY`, `VERIFIED_BY {at, independent}`, `(Artifact)-[:FOR]->(Task)` |
| Lineage | `(Step)-[:BY]->(Agent)`, `(Step)-[:READ]->(Fact)`, `(Step)-[:WROTE]->(…)`, `(Step)-[:NEXT]->(Step)`, `(Recall)-[:RETURNED {rank, score}]->(Fact)` |
| Audit | `(ToolCall)-[:IN_STEP]->(Step)`, `(ToolCall)-[:CREATED\|UPDATED]->(any)` |
| Staleness (v1.1) | `(Fact)-[:ANCHORED_TO]->(CodeAnchor)`, `(Source)-[:DESCRIBES]->(CodeAnchor)`, `(Change)-[:TOUCHED]->(CodeAnchor\|Source)`, `(Change)-[:SUSPECTED]->(Fact)`, `(Fact)-[:VERIFIED_BY {at, commit, outcome}]->(Agent)`; `READ` gains `{via: recall\|use, at}` |

**Indexes:**
- range indexes on `id` and `created_at` for all 16 labels;
- range indexes on the hot filters (`Fact.predicate/valid_to/status`, `Task.status`, `Step.n/agent_id`, `ToolCall.at`,
  `Entity.norm_name`, `Source.uri`, `Scope.name`, `Procedure.task_type`);
- full-text indexes on `Entity.name`, `Fact.value`, `Episode.text`;
- 384-dimension cosine **vector indexes** on `Entity`, `Fact` and `Episode` embeddings;
- UNIQUE constraints on the ids of `Task`, `Fact`, `Agent`, `Decision` and `Handoff`.

**Conventions:**
- **Validity:** FalkorDB has no null properties, so a fact that is "valid until further notice" has
  `valid_to = OPEN = 9_999_999_999_999`.
- **Time:** epoch milliseconds (6.0.2 has no `datetime()`).
- **Maps:** stored as JSON strings.

### 3.3 Each feature is a graph operation

| Feature | What the graph does | Query |
|---|---|---|
| **Atomic dependency-aware claim** | One statement: find open tasks or tasks whose lease expired, keep only those whose `DEPENDS_ON` targets are all `done`, order by priority/creation/seq, take one, set the lease, create a `CLAIMED` edge recording who held it before. FalkorDB serialises writes per graph, so two agents can't win the same task. | `queries/relay/claim_next_task.cypher` |
| **Write-time supersede / duplicate / contradiction** | One statement anchored at the `Entity`: find the current fact for (subject, predicate, scope). Then either link the new assertion as a duplicate (same normalised value, or a near-paraphrase with identical numeric/version tokens), close the old fact's validity window and add `SUPERSEDES`, or add `CONTRADICTS` when a different agent holds a different value. | `queries/engram/assert_fact.cypher` |
| **Hybrid recall** | Vector index seeds (cosine) plus a full-text keyword union, expanded through `ABOUT` to sibling facts, filtered by scope inheritance (`INHERITS`) and validity at time T. It over-fetches adaptively because FalkorDB filters after the vector top-k. | `queries/engram/recall.cypher`, `recall_keywords.cypher` |
| **why(decision)** | Traverse `BASED_ON` → facts → `ASSERTED_BY` agents, `DERIVED_FROM*1..3` → episodes and sources, `SUPERSEDES`/`CONTRADICTS` neighbours, and the `Step`s that wrote them. Bounded to 200 elements. | `queries/lineage/why_edges.cypher` |
| **knew_at(agent, step N)** | Follow the agent's `Step` chain up to N, its `READ` edges, and keep facts whose validity window covered that step's time. | `queries/lineage/knew_at.cypher` |
| **who_knew(fact)** | The reverse: `(Step)-[:READ]->(fact)` back to agents and step numbers. | `queries/lineage/who_knew.cypher` |
| **as_of(subject, predicate, T)** | The fact whose `[valid_from, valid_to)` contains T. | `queries/lineage/as_of.cypher` |
| **forget_source / quarantine** | Expand five fixed one-hop levels of `DERIVED_FROM` from the `Source`, mark every derived fact forgotten or quarantined, and flag (not delete) every `Decision` `BASED_ON` them. Quarantine also reports the blast radius: agents that READ them, and handoffs that CARRIES them. Quarantine is reversible. | `queries/lineage/forget_source.cypher`, `quarantine.cypher` |
| **blocked_by_failure(task)** | Breadth-first search over `DEPENDS_ON` (10 levels, 5,000 tasks). | `queries/relay/dependents_of.cypher` |
| **mark_changed** | One bounded statement: compare the hashes of ≤ 200 anchors, create a `Change`, mark the active and dormant facts anchored to the changed code (directly, or through `DERIVED_FROM*1..5` from a `Source` whose uri is the changed file) `suspect`, and return the decisions `BASED_ON` them and the docs that `DESCRIBES` that code. Idempotent on unchanged hashes. | `queries/staleness/mark_changed.cypher` |
| **verify_fact (changed)** | The supersede path, then a backdate: the old fact's `valid_to` becomes the `Change.at` (event time), `recorded_at` stays (record time), dependent decisions are flagged. | `queries/staleness/backdate.cypher` |
| **Activation** | Gather each fact's last 50 use events (creation, re-assert, `BASED_ON`, `CARRIES`, `READ {via}`, `VERIFIED_BY`) and its protection edges in one read; ACT-R `A = ln Σ w·Δt^-0.5` is computed in Python and blended into recall as `relevance × (0.9 + 0.1·σ(A − A₀))`. | `queries/activation/activation.cypher` |
| **Tenant isolation** | One graph per tenant: `plexus_t_<tenant>`. No query can cross graphs. | `plexus/src/plexus/graph/tenancy.py` |
| **Live flow** | `ToolCall` → `CREATED`/`UPDATED` edges, ordered by an indexed `at`. | `queries/view/flow.cypher` |

93 named `.cypher` files are listed in `docs/queries.md`. A test (`tests/test_docs_consistency.py`) fails if a query file
is missing from it.

### 3.4 The proof: cut the edges and the features break (ablation)

Crucible and the `plexus demo ablation` command copy a tenant graph and delete four relationship types from the copy
(`DEPENDS_ON`, `BASED_ON`, `DERIVED_FROM`, `READ`), then run the same feature checks on both.

| Measurement | Result (source) |
|---|---|
| Edge-dependent capabilities that break | **7 of 7**: dependency-aware claims, `blocked_by_failure`, `why` for decisions and for facts, `knew_at`, `who_knew`, cascading forget (`docs/BASELINE.md`) |
| Control capabilities that are unaffected | **5 of 5**: as-of, recall, contradiction flags, supersession, exclusive claims |
| C4 dependency test with edges stripped | **181** tasks started before their dependencies finished (0 when intact) |
| C8 forgetting test with edges stripped | **60** forgotten facts still returned (0 when intact) |
| `plexus demo ablation` on the real recording | 6 of 6 features break, 2 of 2 controls unaffected. Edges deleted: `DEPENDS_ON` ×15, `BASED_ON` ×7, `DERIVED_FROM` ×6, `READ` ×71. The original tenant is verified unchanged. |

The controls matter. Exclusive claims and supersession still work without those edges, so the breakage is caused by
the missing relationships, not by a broken copy.

### 3.5 FalkorDB properties we rely on

- **Per-graph write serialisation:** every query is atomic and writes to one graph run one at a time. That is why
  one-statement writes (claim, assert, decision) can't race. It also limits throughput per graph (see §6.4).
- **Many graphs in one server:** tenants are both the isolation story and the scaling story (writes to different
  graphs run in parallel).
- **Vector, full-text and range indexes in the same engine** as the traversal, so hybrid recall is one query instead of
  a call to a separate vector database.
- **`GRAPH.RO_QUERY`:** the viewer API can only read; a write through it is refused by the server.
- **`GRAPH.COPY` + `DUMP`/`RESTORE`:** this is how real runs are recorded and replayed. Round-trips of nodes, edges,
  vectors and indexes were verified on 6.0.2.

---

## 4. Methodology: how it was built

### 4.1 Process

- **Timeline:** built inside the hackathon window, from the first commit (Oct 15 00:17 NPT) through phases P0–P6,
  with 231+ commits.
- **Pre-window work:** before the window opened, only notes, research and design were written (rule R5).
- **Plan and decisions:** the plan is `docs/PLAN.md`, and 10 decisions with their reasoning are in `docs/DECISIONS.md`.

| Phase | What | Gate |
|---|---|---|
| P0 | Foundations: compose with FalkorDB 6.0.2 pinned, graph client (read-only path refuses writes), query loader that checks every `.cypher` header against its call, idempotent schema. Spikes: S1 (MCP + real Claude Code), S2 (embeddings, vector/full-text/config behaviour on 6.0.2), S3 (graph library for the viewer) | 55 tests |
| P1 | Engram ‖ Relay ‖ viewer shell (parallel) | 149 tests, then an **independent review** |
| P2 | Lineage ‖ MCP server + audit + View API; integration of Lineage into the tool layer | 328 tests; real `docker compose up`; Claude Code smoke |
| P3 | Demo scenario + real Claude Code orchestrator + recording/replay ‖ viewer features | real recorded run; 117 viewer tests |
| P4 | Crucible: backends, L1, L4, ablation ‖ L2 questions, L3 pilot; then the pre-registered L2-at-scale run | results committed with configs and seeds |
| P5 | Four independent read-only reviewers → three fix branches → integration pass | **Ready for testing**: 869 Python + 150 viewer tests, fresh-clone end-to-end |
| P6 | One-container deployment (512 MB checked), README, video script, blog draft | 40/40 deploy checks; 278 README checks |
| P7 | Staleness (J) ‖ activation forgetting (K) ‖ viewer (L) → integration (int) with a pre-registered Crucible L5 and a real Claude run on a copy of the owner's physiotherapy-project graph | 1168 tests; L5 results committed; independent review → 14 findings fixed |
| P8 | Structure and readability pass with zero behaviour change: four disjoint-scope agents (MCP layer, services/API/CLI, Crucible/demo, viewer) | MCP snapshot and API schema byte-identical; HTML of the viewer pages byte-identical; all suites green |

Current size: 22,785 lines of Python in `plexus/src` and 8,770 of TypeScript in `plexus-view/src`; 93 query files; 41 tools; 1229 Python and 223 viewer tests.

### 4.2 Engineering rules we held to

- **One Cypher statement per write.** FalkorDB has no multi-statement transactions, so every memory and coordination
  write that must be atomic is a single statement.
- **Bounded writes.** `LIMIT` doesn't stop eager writes in FalkorDB, so every `UNWIND` and variable-length path has an
  explicit bound. This came from a real incident: a runaway write ignored `TIMEOUT` and crashed the server.
- **Parameters only.** No string-formatted Cypher anywhere. A reviewer probed 17 hostile names; there was no
  injection.
- **Tests first, against a real FalkorDB:** every test gets a throwaway graph (`test_<uuid>`) that is deleted in
  teardown. Each parallel agent has its own database container and git worktree (D-005).
- **Independent review after each major phase,** with findings verified by probes before reporting, then fixed
  test-first.

### 4.3 AI assistance (disclosed in `docs/AI_USAGE.md`)

- **Who wrote it:** most code, tests, queries and docs were written by Claude Sonnet subagents from specs. A Hermes
  (Claude Opus) orchestrator wrote the specs, ran the gates, merged and fixed integration bugs.
- **Demo and baselines:** unmodified Claude Code on the owner's subscription plays the demo agents and answers the
  benchmark baselines.
- **Product:** Plexus itself contains no LLM.
- **Review status:** the owner's review of the graph model, queries and architecture is tracked phase by phase. Items
  not yet reviewed are marked _TBD_ (hackathon rule R8).

---

## 5. Methodology: how it was measured (Crucible)

### 5.1 The principle: change only the backend (D-007)

A claim like "Plexus is better than how Claude Code or Hermes coordinate" is only valid if **everything except the
memory and coordination backend is identical**. Fixed across every arm:
- the agent harness (unmodified `claude -p`);
- the model (Sonnet; the exact model id is recorded);
- prompts and role definitions;
- **the tool API** (same names and signatures);
- scenario, fault injections and seeds;
- budgets.

| Arm | Backend | Represents |
|---|---|---|
| **B0 Files** | Markdown memory + JSON task list **with file locking** (flock + atomic replace) + per-agent logs | How Claude Code and Hermes coordinate today. Built competently, not as a strawman. |
| **B1 SQLite** | Tables + transactions (`BEGIN IMMEDIATE` claims), recursive CTEs | "Just use a relational database" |
| **B2 Vector** | The same local embeddings over facts and logs, top-k retrieval | Mem0-style retrieval memory |
| **P Plexus** | FalkorDB graph per tenant (and **P-mcp**: the same through the MCP layer with Step and ToolCall writes) | Our system |

### 5.2 The four layers

| Layer | Question | Agents | Scoring |
|---|---|---|---|
| **L1** correctness under concurrency | Do claims, leases, dependencies, as-of queries, isolation and forgetting stay correct under 10–200 concurrent workers? | Scripted Python workers (no LLM), 10 seeded runs per case | Exact counts of violations |
| **L2** provenance and time questions | Can each backend answer "why / who / when / what was true then" questions? | Plexus: a fixed Cypher query per question family. Baselines: **the same LLM** (`claude -p` Sonnet, no tools) reading that arm's own data, all with a 32,000-character context budget | **Exact match** against ground truth computed from the scenario script; **no LLM judge** |
| **L3** end-to-end team outcomes | Does a real 3-agent Claude Code team behave differently per backend when faults are injected? | Real `claude -p` agents | Task completion, reclaim, decisions with evidence, contradictions surfaced, tokens, cost |
| **L4** performance and scale | Latency (p50/p99) and throughput as workers grow 1 → 200; one graph vs many tenant graphs | Scripted workers, **run inside the Docker network** (Docker's Windows port forwarding adds about 10 ms per round trip) | Client latency plus server-side `run_time_ms` |

**L1 tests:**

| Test | What it checks |
|---|---|
| C1 | N workers race for tasks: double claims, lost updates, never-claimed tasks |
| C2 | SIGKILL the claimer: is the expired lease reclaimed? |
| C3 | Concurrent same-fact assertions: duplicates, missed contradictions |
| C4 | Dependency DAG: tasks started too early |
| C5 | Tenant isolation probes, including guessed ids and injection strings |
| C6 | As-of queries at random times after supersedes |
| C7 | Concurrent paraphrase duplicates |
| C8 | Forget-by-source, then probe recall |

**L2 question families:** decision provenance, handoffs, time travel, supersession impact, dependencies,
contradictions, recovery, memory currency and scope, cross-session recall, forgetting.

### 5.3 Honesty rules (`docs/BASELINE.md` §6)

1. No LLM-as-judge for headline numbers. The LoCoMo audit found its judge accepted up to 63% of intentionally wrong
   answers.
2. Report ties and losses. B1 SQLite was expected to match Plexus on claims, and we say so.
3. Publish the harness, seeds, raw results, transcripts and the limits.
4. Don't compare with vendor LoCoMo or LongMemEval scores.
5. **Pre-register** any experiment designed after seeing earlier results. The L2-at-scale run was written into
   `docs/BASELINE.md` and committed **before any LLM call**, including its hypothesis, selectors, budget and
   decision rule.

### 5.4 The demo scenario (shared by the demo, L2 and L3)

**Team and task:** a fictional "Acme Notes API" team (planner, researcher, builder) specifies a small notes REST
service. It runs on synthetic data only:
- 7 synthetic source documents;
- a 12-task dependency graph;
- fixed faults at known steps.

**Fault script:**
- the builder is killed once it holds a task (step ≥ 15), and the researcher must reclaim the task;
- style guide v2 is published (step ≥ 20), so "API version v1" must be superseded by v2;
- the planner and the researcher assert conflicting auth methods (JWT vs API key);
- an optional poisoned forum post triggers quarantine.

---

## 6. Findings

### 6.1 The product works end to end with real Claude Code

**Real recorded run** (`plexus/demo_data/recordings/acme-claude-sonnet/meta.json`):
- 16 `claude -p` processes (Sonnet), 95 model turns, **83 Plexus steps**, **0 permission denials**, 0 errors;
- notional cost $0.698;
- all 12 tasks done.

What happened in the graph:
- The builder was killed at step 17, and the researcher reclaimed its task. The `CLAIMED` edge records
  `reclaimed_from = builder`.
- v2 was published at step 24, and the v1 fact was superseded (`SUPERSEDES` edge, validity window closed).
- The auth conflict produced a `CONTRADICTS` edge at write time.
- 4 decisions are linked by `BASED_ON` to the facts they used (7 `BASED_ON` edges).
- The final graph has 247 nodes and 708 edges across 14 labels and 26 edge types.

**What the graph can answer afterwards,** each with one query:
- `knew_at(builder, 17)` → v1;
- `knew_at(builder, 38)` → v2;
- `why("Adopt API v2…")` → the v2 fact, the researcher, its step and the source document `06_api_style_guide_v2.md`;
- the newest decision traces to 3 facts, 2 agents, 4 steps and 3 sources.

**Replay** restores the recording into a fresh tenant and matches the recorded counts exactly.

### 6.2 L1 correctness: a tie, and that's the honest result

**All four arms pass C1–C8 with 0 violations** over 10 seeded runs per case (`docs/BASELINE.md`, Results).

- **Claims:** 200 workers produced 0 double claims and 0 lost updates in every arm, Plexus included. A competently
  built file store (flock + atomic replace) or SQLite (`BEGIN IMMEDIATE`) is just as correct.
- **C2 recovery:** every arm reclaimed every orphaned task, the slowest 1.27–1.52 s after the kill, against a 2.0 s bar.
- **C7 paraphrases:** the only measured difference.
  - B0 and B1 catch **0%** of paraphrase duplicates, because they only deduplicate exact normalised text.
  - B2 and Plexus catch the light rewordings and miss the heavy ones: a **25% miss** (30 of 120 pairs).
  - No arm wrongly merged distinct facts.
- **Capabilities:** B0 and B2 can't answer `why`/`knew_at` at all; L2 asks an LLM instead. B1 implements them with SQL.

**What it means:** Plexus's case isn't "more correct coordination". Exclusive claims and leases are table stakes that a
good SQL or file design also achieves.

### 6.3 Ablation: the graph does the work

7 of 7 edge-dependent capabilities break without the four relationship types; 5 of 5 controls are unaffected (§3.4).

### 6.4 L4 performance: SQLite is faster on simple claims; Plexus scales across tenants

Client p50 / p99 claim latency in ms (throughput in claim + heartbeat + complete ops/s), measured inside Docker:

| Arm | 1 worker | 10 | 50 | 100 | 200 |
|---|---|---|---|---|---|
| B0 files | 1.6 / 4.0 (569/s) | 18 / 30 (534/s) | 267 / 525 (167/s) | 931 / 1294 (102/s) | 2459 / 3885 (73/s) |
| B1 SQLite | 0.1 / 0.2 (17,169/s) | 0.1 / 89 (3,725/s) | 0.3 / 567 (1,656/s) | 0.5 / 1688 (1,480/s) | 0.8 / 2178 (1,456/s) |
| **P Plexus** | 1.8 / 2.8 (668/s) | 5.5 / 16 (1,780/s) | 50 / 140 (1,028/s) | 156 / 356 (679/s) | 571 / 1863 (373/s) |
| P-mcp (with audit + steps) | 8.4 / 11.6 (123/s) | 37 / 48 (258/s) | 239 / 287 (228/s) | 621 / 828 (173/s) | 1622 / 2345 (153/s) |

- **SQLite is faster than Plexus on the median claim at every worker count.** Its tail is worse under contention
  (p99 2.18 s vs 1.86 s at 200 workers), because SQLite's busy handler has no fair queue.
- **Plexus's server-side time** for a claim is 0.5 ms at 1 worker and 3.6 ms at 200. The rest of the client latency is
  queueing, because FalkorDB serialises writes per graph, plus the Python client.
- **Spreading tenants across graphs** (50 workers, claim + complete):

  | Graphs / files | Plexus | SQLite |
  |---|---|---|
  | 1 | 678 ops/s | 1,103 ops/s |
  | 4 | 1,025 ops/s | 1,480 ops/s |
  | 16 | **1,174 ops/s** (+73% over 1 graph) | 500 ops/s |

  SQLite fell at 16 files because 16 files with 50 writers contend on one disk.
- **Recall throughput** is limited by the shared CPU embedding model (about 47 embeddings/s), not by FalkorDB. Server
  time per recall is about 10 ms; the multi-second client latency at 200 workers is queueing.
- **The audit cost:** the MCP layer's Step and ToolCall writes cost 2–3× throughput at 1–50 workers. Every call writes
  provenance.
- **Query tuning during review:** the sibling expansion in recall originally scanned every fact in a scope (80,000
  records, 197 ms at 10k facts). It is now anchored at the entity: the largest step reads 40 records and takes 2.1 ms.
  `assert_fact` and `fact_history` went from 10,000 records to 5–6 (`docs/queries.md`, P5 fix report).

### 6.5 L2 provenance questions (43 questions, one project): a tie on accuracy

Source: `plexus/demo_data/crucible/l2/20261014T215450Z-full/report.md`.

| Arm | Accuracy (exact match) | Tokens / question | Cost / question | Median latency |
|---|---|---|---|---|
| B0 files + Claude | **43/43** | 15,930 | $0.062 | 5.75 s |
| B1 SQLite + Claude | **43/43** | 13,406 | $0.052 | 5.29 s |
| B2 vector + Claude | 40/43 (93%) | 4,092 | $0.015 | 5.76 s |
| **P Plexus (Cypher)** | **43/43** | **0** | **$0** | **2.5 ms** |

- **Why it's a tie:** the whole B0 history is about 25k characters and the B1 dump about 18k, so both fit in the 32k
  budget. Sonnet reads everything and answers everything.
- **Where Plexus wins here:** cost, latency and determinism. It uses zero tokens, takes milliseconds, and gives the
  same answer every time.
- **Disclosed scoring change:** the first run required the reply to be pure JSON. Claude often wrote one sentence
  before correct JSON, which scored B0 36, B1 38, B2 39. The rule was relaxed **after seeing results** (prose allowed;
  the reply must end with one JSON answer). Both variants are published.

### 6.6 L2 at scale (pre-registered): a small, mostly significant gap

**Design:**
- **History:** 20 sprints of the same story. The baseline artifacts are **10.4–16.6× the 32k budget** (B0 532,813
  characters, B1 332,599).
- **Baseline selection:** every baseline gets competent retrieval within the budget: BM25 for B0/B1 (B1 always gets
  the full schema) and vector top-12 for B2.
- **Questions:** 36 (reduced from 40 by the pre-registered budget rule before the full run).

Source: `docs/BASELINE.md`, "L2-scale results".

| Arm | Correct | Wilson 95% interval | Tokens / question | Cost / question | Median latency |
|---|---|---|---|---|---|
| **P Plexus** | **36/36 (100%)** | 90.4–100% | 0 | $0 | 7.5 ms |
| B1 SQLite + Claude | 32/36 (88.9%) | 74.7–95.6% | 22,010 | $0.087 | 4.9 s |
| B0 files + Claude | 30/36 (83.3%) | 68.1–92.1% | 19,646 | $0.077 | 4.7 s |
| B2 vector + Claude | 23/36 (63.9%) | 47.6–77.5% | 4,424 | $0.016 | 5.0 s |

- **Statistics:** a paired sign test on the questions where two arms disagree:

  | Comparison | Disagreements won | p-value | Reading |
  |---|---|---|---|
  | P vs B0 | 6–0 | 0.031 | suggestive |
  | P vs B1 | 4–0 | **0.125** | **not distinguishable from noise** |
  | P vs B2 | 13–0 | < 0.001 | clear |

- **Where the baselines failed:**
  - join-heavy **decision provenance** (B0 and B1 each 1/4): the decision row was retrieved but the second fact or its
    source document wasn't in the 32k context;
  - one **transitive dependency** question: for B1 all six task ids were in the context, and the model still missed
    the chain, so that was a reasoning error, not a retrieval one.
- **What didn't fail:** accuracy did **not** decay for older sprints, because keyword retrieval on the sprint tag works.
- **Hypothesis check:** the pre-registered hypothesis was right on the ordering and ranges, and wrong about *where*
  baselines fail. They answered every class-wide question correctly.
- **Cost of the experiment:** $6.49 for 108 `claude -p` calls, under the $7 cap.

### 6.7 L3 end-to-end pilot: no separation

Source: `plexus/demo_data/crucible/l3/20261014T214900Z-pilot/report.md`. One real 3-agent run per arm (Sonnet,
same faults):

| Metric | P | B0 | B1 |
|---|---|---|---|
| Tasks done | 12/12 | 12/12 | 12/12 |
| Killed builder's task reclaimed and finished | yes | yes | yes |
| Decisions with evidence / handoffs carrying facts | 4 / 4 | 4 / 4 | 4 / 4 |
| Contradictions surfaced at write time | 1 | 1 | 1 |
| Tool calls / errors | 82 / 0 | 81 / 0 | 83 / 0 |
| **Tokens** | **1,723,458** | 981,150 | 993,051 |
| **Cost** | **$0.69** | $0.52 | $0.49 |
| Wall time | 420 s | 316 s | 324 s |

With n=1 this isn't a ranking. The scenario is small enough that every backend completes it. **Plexus agents used
about 75% more tokens:** richer tool results (recall paths, `why` output) cost context. See §7.

### 6.8 Deployment

The one-container image runs FalkorDB, the API, MCP over HTTP and the static viewer. It is 510 MB on disk. Results
under Render-free limits (`-m 512m --cpus 0.5`, `docs/deploy.md`):

| Check | Result |
|---|---|
| Boot to healthy | 5–14 s |
| Peak memory | 332 MiB (cgroup) |
| Automated deploy checks | 40/40 pass |
| Restart | reseeds both demo tenants exactly |

### 6.9 FalkorDB 6.0.2 lessons (22 verified gotchas, `docs/reference/FALKORDB_REFERENCE.md` §2)

The most consequential:
1. **Vector `score` is a cosine distance:** nearest first means `ORDER BY score ASC`. The docs show DESC.
2. **Vector `WHERE` filters run after top-k,** so you must over-fetch, or valid results starve.
3. **Wrong-dimension vectors are silently accepted;** a vector query on a label with no index silently returns
   nothing.
4. **`RESULTSET_SIZE` silently truncates,** and the Docker image defaults (`TIMEOUT 1000`, `MAX_QUEUED_QUERIES 25`)
   bite under load. Set them explicitly.
5. **A runaway cartesian `SET` ignored `TIMEOUT` and crashed the server.** It restarted from a 21-minute-old RDB.
   Bound every write.
6. **No `datetime()`; no null properties;** maps must be JSON strings.
7. **Query-planner bugs:**
   - two CASE-wrapped list comprehensions with nested pattern comprehensions in one `WITH` return wrong results;
   - a node created earlier in the same statement can't be `MATCH`ed;
   - `WHERE NOT (:X)-[:R]->(e)` followed by `MATCH` raises "not defined".
8. **The legacy full-text procedure creates nothing.** Fuzzy `%term%` is edit distance 1, not a substring match.
9. **Redis answers `PING` while still loading the AOF,** so graph queries fail with `BusyLoadingError`. Health checks
   must wait for `loading:0`.
10. **redis-py's default pool raises `MaxConnectionsError` past 100 connections** instead of waiting. This was the root
    cause of the only L1 failure we saw, in the benchmark harness, not in Plexus. The product client now uses a
    blocking pool.

---

## 7. Memory that notices change, and forgetting (P7)

Built after the first version of this report, from two questions the owner asked while testing Plexus on a real
project: *"if code changes but its documentation doesn't, does Plexus notice?"* and *"can memories fade like human
memories, with surprising ones kept?"* The design is in `docs/DECISIONS.md` D-011 and D-012; the research behind it
(109 cited sources) is in `docs/research/forgetting-A-science-and-papers.md` and `forgetting-B-products.md`.

### 7.1 What the research said

- **No evidence that forgetting improves accuracy.** Removing the decay term changed accuracy by 0–1 point in the
  systems that measured it (MemTier, ZenBrain, HeLa-Mem); decay *hurt* when an old fact was needed (ScrubJay on
  MemoryAgentBench). Its real benefits are less noise and bounded growth.
- **Human forgetting follows a power law** (ACT-R base-level activation `B = ln Σ t_k^-d`, `d ≈ 0.5`), not the
  exponential most agent products call "the Ebbinghaus curve". The difference is the fat tail: a 30-day-old use still
  counts 18% of a 1-day-old one under the power law, 3% under Generative Agents' exponential.
- **Surprise raises confidence, not accuracy** (flashbulb memories). A salience boost must never be read as truth.
- **Products mostly re-rank or soft-hide**, and several advertised decay features aren't implemented (Cognee, MemOS).
  The user complaints on record are about *stale memories with no freshness signal*, not about over-forgetting.

### 7.2 What was built

| | Staleness (D-011) | Forgetting (D-012) |
|---|---|---|
| Trigger | A Claude Code `PostToolUse` hook on Edit/Write, or a git `post-commit` hook, runs `plexus code scan`: it hashes changed files and Python functions/classes (via `ast`) and calls `mark_changed` | Nothing is written on read; activation is computed at query time from the use events the graph already records |
| What happens | Facts anchored to the changed code (or derived from a `Source` whose uri is the changed file) become **suspect**: still recalled, flagged with the commit and path. The decisions built on them and the docs that describe that code are listed | Recall multiplies relevance by `0.9 + 0.1·σ(A − A₀)`; surprising facts (a supersede 0.6, a cross-agent contradiction 0.9, novelty up to 0.5) start with extra pseudo-accesses |
| Resolution | The agent reads the code and calls `verify_fact`: confirmed → `VERIFIED_BY` (weight-2 event); changed → supersede with the old fact's `valid_to` = the change's time while `recorded_at` stays (two timelines, as in Graphiti) | Protected facts (`BASED_ON` by a decision, carried by a handoff, in a `SUPERSEDES`/`CONTRADICTS` chain, pinned, or from a high-trust source) never fall below neutral; `as_of`, `why`, `knew_at`, `fact_history` ignore activation |
| Deletion | Never | Never by decay. `memory_sweep` (dry-run by default, reversible with `restore_fact`) moves unprotected faded facts to `dormant` |
| Viewer | ⚠ suspect badge with reason, a **Verify** page (queue + docs to update) | pin glyph, dashed outline for dormant, opacity by activation, a "Memory strength" panel that explains the number |

### 7.3 What was measured (Crucible L5, pre-registered, no LLM)

**L5a staleness** (60 facts, 21 commits, edits of eight kinds):

| Arm | Precision | Recall | Stale facts returned unflagged |
|---|---|---|---|
| Symbol-level anchors | **100%** | **100%** | 0 |
| File-level anchors | 15% | 100% | 0 |
| No anchors (today's tools) | n/a | 0% | 19 of 19 |

Symbol anchoring is exact; file-level is safe but noisy (every edit to a file flags all facts about it); without
anchors every stale fact comes back looking current.

**L5b forgetting** (the L2-scale history plus decaying noise, a simulated 90 days of reads, 80 "critical" probes =
decision-supporting facts read once 90 days ago):

| | recall@5 | critical probes lost | noise share of results | cold-but-true facts in top 5 |
|---|---|---|---|---|
| Forgetting off | 98.6% | — | 24.0% | 100% |
| **On, floor 0.5 (first default)** | **73–75%** | **7–8 of 80** | 10% | 45% |
| On, floor 0.9 (confirmatory, now the default) | 96.4% | **0** | 15.1% | 94% |
| On + sweep, floor 0.9 | 88.6% | 0 (none swept) | 9.9% | 72% |

The first pre-registered run **failed its own criteria**. Among near-identical facts (20 sprints telling the same
story), a popular or protected twin from another sprint was lifted past the relevant fact, because the 0.5–1.0
multiplier moves it more than the tiny relevance gap. Nothing was deleted and no critical fact was swept, but
protection stops sweeping, not outranking. A post-hoc floor sweep pointed at 0.9; a second, pre-registered
confirmatory run at 0.9 passed all criteria (D-012 amendment). Costs that remain, stated in `docs/forgetting.md`:
recall@1 drops 12 points when twins compete; the sweep hides cold-but-true facts and stays optional.

**Real run.** On a copy of the owner's physiotherapy-project graph (42 facts) and a scratch clone of its API repo:
one edit to `normalize_method` in `gateway.py` → the hook flagged 1 fact, 3 dependent decisions and the README →
`claude -p` (Sonnet, 5 turns, 21 s, $0.04) called `facts_to_verify`, read the code, called `verify_fact(changed)` with
the corrected value and named the README and an unregistered `AGENTS.md` as docs to update. The old fact closed at
the change's time, the new one is current, and the first run exposed a bug (`verify_fact` treated the corrected
clause as a paraphrase duplicate), fixed with a regression test. Recording: `demo_data/recordings/physio-stale-sonnet/`.

### 7.4 Review and cleanup (P8)

An independent reviewer found 14 issues (4 major, 0 blockers), mostly the new `dormant` status interacting with
older paths (`mark_changed` and `assert_fact` ignoring dormant facts; `verify_fact`'s two-statement failure state;
a label scan in `facts_to_verify`). All were fixed test-first. Then four agents refactored the code base with a
zero-behaviour-change rule: the MCP snapshot, the View API schema and the rendered viewer HTML were checked
byte-identical before and after.

| Before → after | |
|---|---|
| `mcp/tools.py::register_engram_relay` 521 lines | one `ToolTable` pattern; each tool a flat function; modules ≤ 300 lines |
| `api/view_api.py::create_app` 305 lines | 35 lines + five routers (`routes_core/graph/flow/lineage/staleness`) |
| `crucible/l1.py` cases c2/c5 122/129 lines | 37/24 lines; shared harness; `backends/base.py` for identical checks |
| `graphController.ts` 834, `Results.tsx` 729, `Explorer.tsx` 500 lines | 421 / 104 / 292 lines; style/layout/data/selection modules; per-layer components |
| 8 copies of `OPEN`/`now_ms`/`new_id`/`normalize` | one `plexus/common.py` |

## 8. Shortcomings and limits

### 8.1 About the claims

- **Plexus is not more correct than a well-built SQL or file backend** at claims, leases, dependencies, as-of queries,
  tenant isolation or forgetting (L1 tie).
- **Plexus is slower than SQLite** on the median claim at every load level (L4).
- **On a small history, Plexus ties** a plain-files backend read by Claude on provenance accuracy (L2). Its advantage
  there is cost, latency and determinism, not accuracy.
- **The L2-at-scale gap is small.** 36 questions, one run each and one model: the gap to SQLite (4 questions,
  p = 0.125) is within noise. Only the B2 gap is clearly significant.
- **L3 showed no separation,** and Plexus agents spent more tokens.

### 8.2 About the benchmark design

- **Synthetic data, one scenario family,** repeated in L2-scale as 20 near-identical sprints that don't interact.
- **Favours retrieval:** every L2-scale question names its sprint, and a sprint's records share its tag.
- **Favours Plexus:** Plexus answers each question family with hand-written Cypher, effort the baselines didn't get
  (no hand-written SQL or grep helpers for them). L2-scale also added sprint scoping to the Plexus answerer: Python
  filters plus one new query.
- **Not measured:** questions that aggregate across sprints or projects, which is the case where a graph should help
  most. Procedural memory ("which procedure works best for task type K") was also left out of L2, because the backend
  protocol has no procedure tool.
- **Cross-session recall** was reduced to episodes recorded by agents, since the protocol has no sessions.
- **One model** (Claude Sonnet) and one run per question; L3 had n=1 per arm against a plan of ≥ 5.
- **L4 setup:** one machine, one Docker Desktop run, and absolute numbers swing about 2× between runs. Baselines are
  in-process libraries while Plexus crosses a container network, so cross-arm latency isn't strictly like-for-like.
- **`latest-all.json` mixes runs** from different moments: L1/L4 from the first compose run, L2 and L2-scale from
  later runs. The file records which.

### 8.3 About the product

- **Write throughput per tenant is bounded** by FalkorDB's per-graph write serialisation. Hot tenants need to be spread
  across graphs; one busy team graph has a ceiling (373 claims/s at 200 workers in our run).
- **Provenance isn't atomic with the write.** Step `WROTE`/`READ` links and the `ToolCall` audit record are written in
  statements right after the tool's own write. A crash in between loses a provenance edge, never the memory itself.
  Failures are retried once, then flagged (`lineage_degraded`/`audit_degraded`) rather than hidden.
- **Every tool call writes** (an audit node and a step). Even a read like `recall` is a write. So:
  - the public `demo` tenants refuse every MCP call;
  - the audit layer costs 2–3× throughput at low concurrency;
  - visitors who bring their own agent must use a `team_*` tenant.
- **Duplicate detection is heuristic.** It uses the local embedding plus identical numeric/version tokens, and misses
  about 25% of heavy paraphrases (C7). It never merged distinct facts in our tests, but thresholds were tuned on
  synthetic data.
- **Entity resolution is a separate step before `assert_fact`.** Two different spellings racing can create two
  entities.
- **Recall speed is limited by the CPU embedder** (about 47 embeddings/s shared). Retrieval can still miss a valid
  fact whose embedding is far from the query and which shares no keyword with it, because vector filters run after
  top-k.
- **Explicit step numbers must arrive in order.** A step number behind an agent's latest is renumbered to the next one,
  because the step chain is append-only.
- **Tenant names are routing, not authentication.** There is no auth on the View API or the MCP endpoint. Anything in a
  public `team_*` graph is public.
- **Lineage limits:**
  - forgetting a fact doesn't reinstate the older fact it had superseded;
  - `knew_at` uses a fact's current `valid_to`, which is correct for supersession but, after forgetting, rewrites
    history to the forget time;
  - cascades are bounded (5 hops of `DERIVED_FROM`, 3 hops for `why`).
- **Staleness only covers what is anchored.** Facts nobody linked to code (and languages other than Python, which get
  file-level anchors only) are flagged coarsely or not at all; the hook must be installed per repo.
- **Forgetting is a ranking heuristic with literature defaults.** The floor had to be raised after the first
  pre-registered run failed; recall@1 still drops when near-twin facts compete; the sweep is lossy. It brings less
  noise, not better accuracy.
- **Procedural memory has no viewer page** and isn't exercised in the recorded demo.
- **Explorer limits:**
  - the viewer reads at most the newest 2,000 nodes per request;
  - in dense graphs (> 1,500 edges) parallel edges are drawn on top of each other;
  - the unfiltered Explorer query got slightly slower after indexing (3.8 → 5.8 ms at 4.2k nodes), while filtered
    reads got faster.

### 8.4 About the evidence and the process

- **Real Claude Code coverage:** only 14 of the 41 tools have been driven by real `claude -p` (11 in the Acme runs, 3 more in the physio staleness run). All 41 have MCP
  contract tests, and a guard fails if a new tool lacks one.
- **Reproducing the benchmark** takes separate commands, deliberately (L1/L4 vs the LLM layers), so a re-run can't
  spend the subscription by accident. LLM answers are cached, so re-scoring is free.
- **Render isn't verified.** The deployment is checked locally under Render-like limits only; the live service,
  client-IP forwarding and Render's own memory accounting haven't been tested.
- **Small-sample LLM results:** total LLM spend across demo and benchmarks was about $15 notional on the owner's
  subscription. That is enough for pilots and single runs, not for repeated-measures statistics.
- **AI-written, owner-reviewed:** most code was written by AI subagents. The owner's line-by-line review of the graph
  model and queries is tracked in `docs/AI_USAGE.md` and wasn't complete at the time of writing.
- **L5 used one scenario family and one run per setting** (ids are random, so second digits move); the real staleness
  run is a single demonstration, not a benchmark.
- **One FalkorDB version:** everything was verified on 6.0.2 only. Several documented features behave differently or
  are missing there (§6.9).

---

## 9. What we would do next

1. **Measure the case the graph should win:** cross-project questions such as "which decisions across all sprints
   relied on a fact from source S" or "which agents ever read a fact that was later quarantined". Pre-register them.
2. **Repeat L3 properly:** ≥ 5 runs per arm with fixed seeds, a larger scenario whose history exceeds an agent's
   context, and the MAST metrics.
3. **Slim the tool output:** cap recall paths and `why` detail by default, to close the token gap seen in L3.
4. **Add a no-audit read path,** so public read-only tenants can serve `recall`/`why` to visitors' agents.
5. **Make provenance and `verify_fact` writes atomic:** fold the `link_step` tail and the backdate into the write
   statement where FalkorDB's planner allows.
6. **Batch embeddings or move the embedder to its own service,** to lift the recall ceiling.
7. **Add authentication** (per-tenant tokens) before any non-demo deployment.
8. **Add a procedures view,** and run procedural memory in the demo scenario.
9. **Symbol anchors for TypeScript and Dart** (tree-sitter), so the exact flagging seen for Python covers the
   other repos.
10. **Shard hot tenants:** route a busy team across several graphs (per project), since throughput scaled +73% across
   graphs.

---

## 10. Where to find everything

| Topic | File |
|---|---|
| How to run it, connect Claude Code, ports | `README.md` (Setup, Bring your own agent) |
| Graph data model | `docs/graph-model.md` |
| Every Cypher query, with why it's a graph query | `docs/queries.md`, `plexus/queries/**` |
| MCP tools and behaviour | `docs/mcp.md` |
| Decisions and their reasoning | `docs/DECISIONS.md` (D-001 … D-010) |
| Build plan and phase status | `docs/PLAN.md` |
| Benchmark methodology, pre-registration, results | `docs/BASELINE.md`, `plexus/src/plexus/crucible/results/latest-all.json` |
| Ready-for-testing evidence and the manual test checklist | `docs/TESTING.md` |
| Demo modes, recording, replay, ablation | `docs/demo.md` |
| Staleness and forgetting: design, hooks, limits, the real run | `docs/staleness.md`, `docs/forgetting.md`, D-011/D-012 |
| Forgetting research (cited) | `docs/research/forgetting-A-science-and-papers.md`, `forgetting-B-products.md` |
| Deployment | `docs/deploy.md`, `render.yaml`, `deploy/` |
| FalkorDB 6.0.2 behaviour vs the docs | `docs/reference/FALKORDB_REFERENCE.md` |
| Landscape research (cited) | `docs/research/landscape/*.md`, `docs/research/PROJECT_IDEAS.md` |
| AI disclosure | `docs/AI_USAGE.md` |
