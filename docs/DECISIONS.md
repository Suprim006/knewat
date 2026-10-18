# Decisions log

Each entry records the reasoning, so the owner can explain every choice to judges (rule R8).
Format: **ID — title** · date · status (proposed / accepted / superseded).

---

## D-001 — Project: Plexus (memory + coordination + lineage + proof, one graph)
2026-10-14 · **accepted** (owner confirmed the combined scope, the name **Plexus**, and the demo scenario: **generic software team**)

**Context.** Track 02 asks for memory that persists, updates over time and is shared across agents, plus handoffs, concurrency and tenant isolation.
The landscape research (`docs/research/landscape/*`) found gaps in today's products (Claude Code, Hermes, ChatGPT, Letta, Mem0, Graphiti) on both sides:
- **Memory:** stale facts, unscoped memory, size caps, near-duplicates, skills without outcomes.
- **Coordination:** handoffs and decisions can't be queried, there's no consistency model for concurrent writers, and summaries are self-reported.
- **Trust:** no "why recalled", imprecise forgetting, poisoning that spreads between agents.
- **Proof:** no benchmark covers concurrency, handoffs, tenant leaks or invalidation.

Per-tenant graphs and simple supersession are table stakes: competitors MERIDIAN, GraphMem and ZeroCapital have them.
A single-module entry would either be crowded (memory alone, against Graphiti/Mem0/Cognee) or too narrow (coordination or quarantine alone).

**Decision.** Build **Plexus**: one FalkorDB graph model and one MCP server with four modules plus a UI.
1. **Engram (memory):**
   - episodic `Session`/`Episode` chains;
   - semantic `Fact`s with validity windows and `SUPERSEDES`;
   - duplicate and contradiction detection inside the write query;
   - `Scope` nodes plus one graph per tenant;
   - budgeted hybrid recall;
   - procedural `Procedure`→`Run`→`Outcome` success rates.
2. **Relay (coordination):** dependency-aware atomic claims with leases and heartbeats, `Handoff` nodes carrying artifacts and evidence, `Decision`-`BASED_ON`→`Fact`, dead-agent reclaim.
3. **Lineage (provenance and trust):** `why`, `why_recalled`, `who_knew` at step N, `as_of`, forget-by-source cascade, and (stretch) quarantine of a poisoned source's blast radius.
4. **Crucible (proof):** the backend-swap benchmark in `docs/BASELINE.md`.
5. **Time Machine UI:** live graph, step slider, "why" path highlight, ablation switch.

**MVP vs stretch.**
- **MVP:** Engram (minus the procedures UI), Relay, `why` + `who_knew` + `as_of`, Crucible L1/L2/L4, and a minimal UI.
- **Stretch:** quarantine, Crucible L3, procedures UI, HR-ops scenario skin.
- **Cut order:** stretch first, then UI polish; never the MVP.

**Why FalkorDB is the core (R2).** It's the only state store; agents are stateless MCP clients. The graph does the real work in:
1. hybrid recall (vector seed → 1–2 hop expansion → validity and scope filter, in one query);
2. dependency traversal ("next ready task", "what's blocked if T fails");
3. multi-hop "why" paths (decision → facts → agents, steps, sources);
4. contradiction and duplicate detection inside the same atomic write;
5. time travel over `READ` edges and validity windows;
6. forget and quarantine cascades over `DERIVED_FROM`;
7. one graph per tenant with ACL;
8. algorithms as tools (PageRank = load-bearing facts, label propagation = consolidation clusters, WCC = orphans, SPpaths = shortest explanation).

Claims and leases are atomic compare-and-set writes. They're needed, but a relational database could do them, so they are **not** the pitch.
The ablation demo cuts the edges and shows the features break.

**Alternatives.** Each idea alone (see `docs/research/PROJECT_IDEAS.md`). Building on Graphiti or Mem0: rejected, because the main FalkorDB implementation must be new work (rule R6). They serve only as references and baselines.

**Consequences.**
- One schema serves every module. Every MCP tool is one bounded Cypher statement, because writes to a graph run one at a time.
- The scope is large, so the plan must be phased with hard cut lines.
- Pitch order: "why" / time travel / contradictions / scoped memory first, claims last.

## D-002 — Agents are unmodified Claude Code; Plexus has no LLM inside
2026-10-14 · **accepted**

**Context.** The owner has a Claude subscription but no Anthropic API key. Anthropic's [legal & compliance page](https://code.claude.com/docs/en/legal-and-compliance) says:
- subscription OAuth is for "ordinary use of Claude Code and other native Anthropic applications";
- developers building products "should use API key authentication" and may not offer Claude.ai login, route requests through Free/Pro/Max credentials on behalf of users, or "collect, store, or intermediate Claude.ai credentials";
- it explicitly allows "an end user signing in to the unmodified Claude Code binary with their own Claude subscription".

Headless `claude -p` uses the subscription login; `--bare` needs an API key ([headless docs](https://code.claude.com/docs/en/headless)).

**Decision.**
1. **Plexus contains no LLM and no LLM credentials.** All tools are deterministic Cypher. Semantic matching uses a local CPU embedding model (bge-small via fastembed, to confirm at kickoff).
2. **The agents are the unmodified `claude` binary** (v2.1.296), signed in with the owner's own subscription and started by our orchestrator:
   ```
   claude -p "<task>" --mcp-config plexus.mcp.json --allowedTools "mcp__plexus__*" --max-turns N --output-format stream-json
   ```
   `ANTHROPIC_API_KEY` stays unset.
3. The benchmark's baseline arm and Plexus arm both use this same harness, account and model (see `docs/BASELINE.md`).

**Why.**
- It complies with Anthropic's terms.
- No API key or cost is needed.
- Plexus's results are deterministic and reproducible.
- It gives a clean A/B where only the coordination backend changes.
- It also makes Plexus agent-agnostic: any MCP client can use it.

**Alternatives rejected.**
- An Anthropic API key: the owner doesn't have one; it remains an option later.
- Routing Plexus's own LLM calls through the subscription (via the Hermes proxy or a token): prohibited.
- Claude Agent SDK on the subscription: SDK products are told to use API keys.

---

## D-003 — Hermes excluded from published runs; public demo policy
2026-10-14 · **accepted**

**Context.** On this machine Hermes's Anthropic credential is an OAuth token taken from Claude Code (`auth_type: oauth`, `source: claude_code`; checked 2026-10-14). That is third-party use of subscription credentials, which D-002's terms don't permit. Secondary reports say Anthropic has enforced this since early 2026.

**Decision.**
- Hermes may help **build** the project (owner's choice and risk), but it is **not** a benchmark arm or a demo agent. Published runs use Claude Code only.
- The **public live demo never triggers LLM runs on the owner's subscription.** It serves:
  1. scripted, non-LLM agents for the claim, lease and concurrency scenes;
  2. replays of recorded real Claude Code runs for the "why" and time-travel scenes.

  Real LLM runs appear only in the demo video.
- Optional "bring your own agent": a judge connects *their own* Claude Code to the public Plexus MCP endpoint, and each connection gets its own graph or tenant.
- **Owner follow-up (optional):** switch Hermes to an API key or another provider to remove the risk.

---

## D-004 — Dev database: local Docker FalkorDB 6.0.2, pinned
2026-10-14 · **accepted**

- **Decision:** container `falkordb-dev` (`127.0.0.1:6379` and Browser `:3000`, volume `falkordb_dev_data`).
- **Settings:**
  - Pin `6.0.2` in compose and deploy files.
  - Set `FALKORDB_ARGS` explicitly. The image ships with `TIMEOUT 1000`, `MAX_QUEUED_QUERIES 25` and `RESULTSET_SIZE 10000`, and the last one silently truncates results.
  - Use AOF and `noeviction` in deployments.
- **Why:** FalkorDB Cloud Free has no persistence and deletes idle instances. Local Docker was verified to persist data across restarts.
- **Latency:** Windows → Docker adds ~10 ms per round trip, so run all latency and concurrency measurements inside the compose network.

---

## D-005 — Isolation for parallel agents and tests
2026-10-14 · **accepted**

- **Incident:** during the docs research, a subagent's runaway cartesian `SET` ignored `TIMEOUT 50`. The server died, Docker restarted it, and it reloaded an RDB about 21 minutes old, so other agents lost their graphs.
- **Decision:**
  - Parallel agents and test suites each get their **own throwaway FalkorDB container** (or at least their own graphs plus their own container for load tests), never the shared dev instance.
  - Every write is bounded (`UNWIND` sizes, `LIMIT` before writes, `QUERY_MEM_CAPACITY`).
  - Tests use `test_<uuid>` graphs, deleted in teardown.
  - Env vars are passed inline per command. An exported `DATABASE_URL` once leaked between parallel agents in another project.

---

## D-006 — Live-demo hosting
2026-10-14 · **proposed** (decide on Day 3)

- **Primary:** Render Free. One Docker web service runs FalkorDB and the app together and reseeds on boot; an uptime pinger keeps it awake. It's $0 and apparently needs no card. The 512 MB limit is fine, since FalkorDB idles at about 88 MB here.
- **Fallbacks:** the AWS Free plan EC2 (6 months), Azure for Students, or Oracle Always Free. Oracle rejects prepaid and virtual cards, which rules out most Nepali USD cards.
- **Paid fallback:** Railway Hobby at about $5–10/month.
- **Always** ship complete `docker compose` local setup and the demo video.

Details: `docs/research/free-vm.md`, `docs/research/hosting.md`.

---

## D-007 — Evaluation methodology: change only the backend
2026-10-14 · **accepted**

**Decision.** Claims of the form "X does better than Claude Code or Hermes" must come from a benchmark where the agents, model, prompts, tool API and scenario are fixed, and only the coordination and memory backend changes:
- files (how Claude Code and Hermes work today);
- SQLite;
- a vector store;
- Plexus on FalkorDB.

Full plan: `docs/BASELINE.md`. Statements about the real Claude Code or Hermes products are labelled as a qualitative case study, not as benchmark results.

---

## D-008 — Two projects in one repo: `plexus/` (product) and `plexus-view/` (demonstrator)
2026-10-14 · **accepted**

**Context.** The owner wants the product (FalkorDB + an MCP server of deterministic Cypher) kept separate from a view that demonstrates how data is stored, how it flows, and what the demo created.

**Decision.**
- **One monorepo with two projects:**
  - `plexus/`: Python. MCP server, the Engram, Relay and Lineage modules, Crucible, the demo runner, and a **read-only View API** (FastAPI + SSE).
  - `plexus-view/`: Vite + React + TypeScript with Cytoscape.js (or `@falkordb/canvas` if the P0 spike favours it). It talks **only** to the View API and never writes.
- **The data flow is itself graph data:** every MCP tool's Cypher statement also creates a `ToolCall` node with `CREATED`/`UPDATED` edges to what it touched. This happens in the same atomic statement, so there's no extra round trip and nothing outside FalkorDB.

**Why.**
- The judged core stays small and testable.
- The View can't corrupt data.
- "How data flows" is answered by querying the graph, not by app logs.

**Alternatives.**
- The View connecting to FalkorDB directly through its own Node backend: rejected, because it duplicates the queries and adds a second writer risk.
- FalkorDB Browser only: kept as a secondary raw view, but it can't show the flow or time travel.

## D-009 — MCP transports and tenancy binding
2026-10-14 · **accepted** (verify in the P0 spike S1)

**Decision.**
- **stdio** for local Claude Code agents (`plexus.mcp.json`); **streamable HTTP** for the public "bring your own agent" endpoint.
- The tenant is bound **per connection** (a CLI argument or env for stdio, a path or header for HTTP). Tools never accept a graph name, so an agent can't address another tenant's graph.
- Graph names are `plexus_t_<tenant>` with `[a-z0-9_]` only. Test graphs are `test_<uuid>`.

**Why.** Tenant isolation is enforced at the connection layer and backed by one graph per tenant, plus ACL in deployment.

**Verified (S1).** Both transports work with unmodified Claude Code 2.1.296. In stateful HTTP mode the SDK checks the tenant per request, so a session id could be replayed against another tenant path. Plexus therefore pins session id → tenant and returns 403 on a mismatch.

## D-010 — Demo runs: scripted for the public demo, real Claude runs recorded and replayed
2026-10-15 · **accepted**

**Decision.**
- **Scripted runs:** the public demo and the View's live mode use deterministic **scripted agents** that call the same MCP tools in-process, so they leave the same `ToolCall`s and `Step`s as real agents.
- **Real runs:** `claude -p` (sonnet, plus haiku for pilots) runs on the owner's subscription with `--strict-mcp-config`, no built-in tools, `ANTHROPIC_API_KEY` unset, and `permission_denials`/`is_error` checked. Real runs are **recorded** (`GRAPH.COPY` → `DUMP`, plus meta and sanitised transcripts) and **replayed** with `RESTORE`; 6.0.2 round-trips vectors and indexes.
- **Turns are sequential:** real agent turns run one at a time, and the scheduler picks the top ready task for the matching role. `claim_next_task` has no role filter, so concurrent turns would claim other roles' tasks. Concurrency is measured in Crucible instead.

**Why.** It is reproducible and free for the public site (D-003: no LLM on the public site). It is honest about what a real model did, because the recording is the real graph. The first full real run cost about $0.70 (16 processes, 83 steps, 0 denials).

## D-011 — Memory that notices change: suspect → re-verify (staleness)
2026-10-16 · **accepted** by the owner (rank only, nothing deleted; file-level + Python function anchors)

**Context.** Plexus only knows what agents tell it. When Claude Code edits code but not the doc or fact that describes
it, nothing in the graph changes, and recall keeps returning the old fact. Users of today's tools complain about this
most: months-old `MEMORY.md` with no freshness signal, and Graphiti ranking superseded facts equal to current ones
(`docs/research/forgetting-B-products.md`). Graphiti's two timelines (when a fact was true vs when the system learned
it) are the right *record*, but its invalidation only reacts to new *text* and needs an LLM.

**Decision.**
- **Changing code doesn't make a fact false; it makes it suspect.** Facts get `verify_state`: `verified | suspect`. A
  suspect fact stays recallable, carrying `suspect_since` and the change that caused it, so knowledge is never lost
  just because a file was edited.
- **Detection is deterministic and runs on the user's machine.** The Plexus server (in Docker) can't read the user's
  repo. A client CLI (`plexus code-scan` / `plexus hook …`) hashes changed files, and changed functions where a parser
  exists, then calls `mark_changed(changes, commit)`. It is triggered by a Claude Code `PostToolUse` hook on
  Edit/Write and by a git `post-commit` hook.
- **Linking facts to code:**
  - **File level, automatic:** a fact `DERIVED_FROM` a `Source` whose uri is a repo path is anchored to that file, so
    existing facts (for example the physio graph's `CLAUDE.md` facts) are covered with no extra work.
  - **Function level, optional and more precise:** `(Fact)-[:ANCHORED_TO]->(CodeAnchor {path, symbol, hash})`.
  - **Doc to code:** `(Source:doc)-[:DESCRIBES]->(CodeAnchor)`, so a code change lists the doc sections to update.
- **The agent re-verifies; Plexus records the outcome.** `verify_fact(fact_id, still_true, new_value?, evidence?)`:
  - **Confirmed:** the fact returns to `verified`, with a `VERIFIED {at, commit}` edge to the agent.
  - **Changed:** the existing supersede path creates the new fact, and the old fact's `valid_to` is the **change's
    time** (event time), while `recorded_at` stays the time Plexus learned it (Graphiti's two timelines).
- **Check on use, not all at once.** Recall flags suspect facts, and Claude re-checks the ones it is about to rely on.
  `facts_to_verify` orders the rest by impact: decisions that depend on the fact first, then activation (D-012).
- **Facts that aren't about code** (deployed URLs, accounts, client requests) can carry `verify_after`. Once it has
  passed, the fact becomes suspect too.
- **Every suspicion is explainable:** `(Change {commit, at, paths})-[:SUSPECTED]->(Fact)` appears in `why`.

**Why.** It targets the most-reported failure (stale memory with no signal) with a graph traversal Plexus already does
(source → facts derived from it → decisions based on them). It keeps Plexus free of LLMs, and the agent supplies the
judgement. **Rejected alternatives:**
- a fixed TTL for code facts: code doesn't go stale with age;
- auto-closing facts on change: true facts would be lost;
- LLM-judged invalidation inside Plexus: breaks D-002 and is inconsistent (Graphiti #1841).

## D-012 — Activation-based forgetting: rank by use, never delete by decay
2026-10-16 · **accepted** by the owner (rank only, nothing deleted; file-level + Python function anchors)

**Context.** The owner asked for human-like forgetting: unused memories fade, surprising ones stay strong. The research
(`docs/research/forgetting-A-science-and-papers.md`, `forgetting-B-products.md`) found:
- **Decay improves efficiency and noise, not accuracy.** Removing decay terms changed accuracy by about 0–1 point
  (MemTier, ZenBrain, HeLa-Mem). Decay **hurt** when an old fact was needed (ScrubJay on MemoryAgentBench).
  Eviction errors are mostly irreversible.
- **Human recall is better modelled by a power law** (ACT-R base-level activation `B = ln Σ t_k^-d`, `d ≈ 0.5`)
  than by the exponential most agent products use.
- **Surprise raises priority and confidence, not truth** (flashbulb memories).
- **Products mostly re-rank or soft-hide rather than delete.** Several advertised decay features aren't implemented
  (Cognee, MemOS).

**Decision.**
- **Activation is computed at query time from edges Plexus already writes. Nothing is written on read.**
  `A(f) = ln Σ_k w_k · max(now − t_k, 1 min)^(−0.5)` over the fact's most recent K = 50 access events:
  - creation: weight 1;
  - **use**: weight 1, meaning cited in a decision (`BASED_ON`), carried in a handoff, read by `assert_fact`
    (duplicate/supersede), or re-asserted;
  - **surfaced by recall only**: weight 0.3. `READ` edges get `via: 'recall' | 'use'`, because today
    `record_recall` writes `READ` for every returned fact, and surfacing must not keep boosting itself;
  - **verification** (D-011): weight 2, following the testing effect.
- **Surprise is computed once, deterministically, at write time:** `Fact.surprise ∈ [0,1]`, from:
  - superseding a current fact (0.6);
  - contradicting another agent's fact (0.9);
  - novelty, `1 − max cosine` to the nearest existing facts in scope (the dedup lookup already finds them);
  - later, a flagged decision or failed `Run` that traces back to the fact.

  It adds `1 + round(4 · surprise)` pseudo-accesses at creation. It is kept separate from `confidence`, because
  surprise is not truth.
- **Rank, don't filter.** `recall` scores `relevance × (0.5 + 0.5 · σ(A − A₀))`. That leaves a floor of 0.5, so a
  relevant but unused fact can still surface. A strong exact keyword match bypasses the penalty.
- **No forgetting from:** `as_of`, `why`, `knew_at`, `fact_history`, or direct lookups by id.
- **Protected facts never fade below neutral:**
  - facts `BASED_ON` by a current (unflagged) decision;
  - facts carried by an open handoff or relevant to an open task;
  - facts at either end of a `SUPERSEDES`/`CONTRADICTS` chain;
  - pinned facts (`pin_fact`), and facts from sources marked trust `high`.
- **No deletion by decay.**
  - **Optional `memory_sweep(dry_run=true)`:** it moves only low-activation, unprotected facts to `dormant` (a new
    status) and can be undone with `restore`.
  - **Bulky derived records** (`Episode`, `Recall`, `ToolCall`) are the first candidates for archival.
  - **Hard delete** happens only via the existing explicit `forget_source`/purge.
- **Activation and staleness are separate axes.** A suspect fact isn't strengthened by being read. A fact that is both
  faded and suspect still appears in `facts_to_verify` if a decision depends on it.

**Why.** It is grounded in the cognitive model with the best fit (ACT-R power law), and uses the per-access log no
mainstream product keeps. It is deterministic, and decision-supporting facts are protected, which is the failure mode
the research warns about. It is honest about the benefit: **less noise and cost, not better accuracy, unless measured.**
P7 measures it with a pre-registered Crucible layer before any claim is made.

**Amendment 2026-10-16 (after Crucible L5b).** The pre-registered run at the default floor 0.5 **failed** its own
criteria: recall@5 fell from 98.6% to 73–75% and 7–8 of 80 critical probes were outranked (none were swept; nothing
was deleted). Cause: among near-identical facts in one scope, the activation multiplier (0.5–1.0) moves a popular or
protected twin more than the tiny relevance gap, so popularity outranks relevance. A post-hoc sweep showed floor 0.9
keeps every critical probe and 96.4% recall@5 while still cutting noise (23% → 14%). **Decision:** the default floor is
`PLEXUS_ACT_FLOOR=0.9`, confirmed by a second, pre-registered run (`docs/BASELINE.md`, L5b confirmatory). The
`memory_sweep` is lossy for cold-but-true facts in this benchmark (cold@5 ~35–70%) and stays optional, dry-run by
default and reversible. Protection prevents sweeping, not outranking: the docs say so.

## D-013 — Pattern separation at recall; additive forgetting kept opt-in (neuroscience memory upgrade, P1 + P2)
2026-10-17 · **accepted** (P1 on by default; P2 implemented, benchmarked, **not** made the default — its pre-registered test failed)

**Context.** `docs/research/NEUROSCIENCE_MEMORY_SURVEY.md` and `MEMORY_FORGETTING_IMPLEMENTATION_PLAN.md` diagnosed
L5b's 12-point recall@1 loss under D-012: the decay curve is not the defect, the *combination rule* is. Relevance ×
squashed activation can only reorder near-ties, and L5b's near-ties are twins where popularity is the wrong tie-breaker.
The plan's top pick was pattern separation (use the entity the query names), second an additive, bounded activation
term with activation-dependent decay (Pavlik & Anderson 2005) and graded salience, third prediction-error-gated
reliability (P3, not built yet). An independent cross-check (`neuro-memory/CROSS_CHECK.md`) agreed on the diagnosis
and ranking and found one required fix (the sweep threshold under the new decay scale).

**Decision.**
1. **P1 pattern separation, on by default** (`PLEXUS_RECALL_SEPARATION=on`). One extra bounded read per recall
   (`engram/recall_entities`: full-text OR of the query words over `Entity.name`, ≤ 5 entities, each with its fan =
   current facts about it in the searched scopes, entity-first plan). An entity counts as *named* only when every
   word of its name is in the query. Facts about a named entity get `sep = gamma · max(0, 1 − ln fan / S_max)` in
   log-relevance (`gamma = 0.15`, `S_max = ln 50`: a hub entity with ≥ 50 facts gets nothing, the ACT-R fan effect);
   the sibling expansion in `engram/recall` is damped by the same factor; each row reports `lures` (other candidates
   with the same predicate about another entity within 0.02 relevance), `entity_match` and `sep`; `Recall` stores
   `entities` and `separation`, `RETURNED` stores `sep`, so `why_recalled` explains the lift. Nothing is written by a
   recall. The exact-keyword bypass now tests the whole fact text (`PLEXUS_KW_BYPASS=fact`; `value` = the old rule).
2. **P2 additive mode, implemented behind `PLEXUS_ACT_MODE=add`, default stays `mult`.** `plexus.activation.score`:
   `ln rel + beta·tanh((A − A0)/2s) + sep + sal`, Pavlik–Anderson activation-dependent decay
   (`activation_spaced`, `c = 0.217, a = 0.177`, testing-effect weight for a recall after the last use), graded
   salience from the graph (`salience_of`: decisions, verifications, independent artifacts, done tasks, distinct
   using agents, handoffs, trusted source, pin; `Fact.salience` cached by `pin_fact`, recomputed on every read
   otherwise), salience slows decay (`kappa = 0.4`), the band guard replaces `max(A, A0)` for protected facts,
   `memory_sweep`'s default margin is `A0 − 0.72` under the new scale (CROSS_CHECK §3.1), and salience ≥ 0.5 protects
   from sweeps. `mult` mode is byte-for-byte D-012 (plus the bypass fix and separation).
3. **Identity contract:** `PLEXUS_FORGETTING=off` **and** `PLEXUS_RECALL_SEPARATION=off` reproduce the pre-D-012 order
   exactly (`tests/activation/test_recall_off.py`, golden captured on main 4584219). Separation alone changes the
   order only through the damped expansion and when the query names an entity.

**Evidence (pre-registered, `docs/BASELINE.md` "L5b-D013"; results `plexus/demo_data/crucible/l5/20261017T08*-d013-*`).**
L5b, K = 20, seed 20261016, fastembed, 0 LLM calls, N = 5 / N = 15 / N = 5 burst:

| mode | recall@1 (N=5 / 15 / burst) | recall@5 | noise share | rows above target: same entity / other entity (N=5) |
|---|---|---|---|---|
| `off` | 75.7 / 77.1 / 75.0% | 98.6% | 23.7% | 36 / 13 |
| `on-mult` (D-012 as shipped) | 65.0 / 65.7 / 63.6% | 95.7% | 14.9% | 46 / 44 |
| `kw-fix` | 77.1 / 77.1 / 76.4% | 98.6% | 14.9% | 29 / 15 |
| `sep` (P1, forgetting off) | **85.7 / 85.7 / 85.7%** | **100%** | 23.3% | 20 / **0** |
| `sep+add` (P1 + P2, pre-registered constants) | **70.0 / 70.0 / 70.0%** | 100% | 21.9% | 41 / 1 |

Hypotheses (plan §5.1): **1** `sep` ≥ 0.90 — **not reached** (85.7%; above the 0.85 falsification floor, so not
falsified either); recall@5 and critical loss pass. **2** `kw-fix` 77.1% < 0.88: the bypass alone is not the fix, it
only removes `mult`'s own loss. **3** `sep+add` — **FALSIFIED** (15.7 points below `sep`; the rule says "P2 still
costs recall and beta is too large"). **4** critical+hot above target ≤ 5 — **failed** (42). **5** burst — **passed**
(0.0% hot-above-cold under `sep+add`; 3.9% under `on-mult`).

**Reading.** P1 did exactly what it was designed for: every cross-entity displacer is gone (13 → 0) and recall@5 is
100% at both N. The residual 20 displacers are *same-entity* critical facts (another predicate of the same sprint
subject), which an entity cue cannot separate; that is the predicate-cue problem CROSS_CHECK §3.2 predicted, and it
is why 0.90 was not reached. A labelled post-hoc sensitivity (`l5_posthoc/d013/*-sens-n5`, not confirmatory) shows
the `sep+add` loss comes from both P2 terms *jointly* (beta 0.05 → 0.01 alone: 72.9%; delta → 0 alone: 70.7%;
both: 85.0%) and that at the strength where the additive term stops costing recall it also stops reducing noise
(23.9% = `off`). The shipped default (`mult` + separation, `sep+mult`) measures 85.0% / 100% / 22.1%: the 12-point
D-012 loss is gone and recall@5 is perfect, at a smaller noise reduction than D-012 alone (14.9%) because the entity
lift also lifts noise *about the named entity* over real facts about other entities — which is what the query asked for.

**Deviations from the plan text, with reasons.** (a) The bypass keeps `ln rel + sep` rather than relevance only:
"relevance only" would strip the P1 lift from the very rows P1 exists for (every bypassed row names the entity).
(b) Named-entity rule instead of "top 5 by full-text score": the OR query returns every `Acme Notes API Sxx` twin, and
lifting all five would cancel the separation. (c) Salience cache written by `pin_fact` only; the six-statement cache
is deferred because the activation read already has every input (CROSS_CHECK §3.7 "simpler v1") and a partial cache
that drifts from the formula is worse than none. (d) `add` is not the default: the plan made that conditional on
§5.1 passing, and it did not.

**Consequences / follow-ups.** P3 (prediction-error-gated reliability, `why_confidence`) and the hub variant (§5.3)
are not built. *Amendment (§5.4 run, `docs/BASELINE.md` "§5.4 results"):* the SQL-arm extension was built and run;
a hand-written SQL arm given the same columns ties `sep+mult` exactly on recall@1/5 in all three L5b runs with 92
lines of SQL (vs 104 of Cypher) and 3 statements (vs 4), and reproduces the activation of every fact; L6-C ties on
correctness (75/75 both) with SQL 3.3x faster at depth 3. The confidence stated in the table of the plan ("tie by
construction vs a SQL arm") is confirmed; the claim this decision supports is "beats flat retrieval, explains every
rank", not "beats SQL". L6-C also found that the shipped `recall(hops)` never ranks a hop fact into the top 5 and
fills its per-hop cap alphabetically — a product defect recorded for the next decision, not fixed here. The next P1 step is the predicate cue (CROSS_CHECK §3.2 / A.3), which is
what the remaining same-entity displacers need; the next P2 step is a fit of `beta`/`delta` against the recorded
`gap12` distribution (median rank-1/rank-2 gap 0.0167) rather than the declared defaults — as a new pre-registration,
not a tuned re-run of this one.

**Amendment 2026-10-17 (predicate cue, CROSS_CHECK §3.2 + §3.3; `docs/BASELINE.md` "Predicate cue pre-registration" and the
three sections after it).** Built and run as the next P1 step this decision pointed to. What changed: `sep` is now the ACT-R
context term over two cues, `w_entity · max(0, S − ln fan_entity) + w_predicate · max(0, S − ln fan_predicate)`, where the
predicate cue uses the named-entity rule on the words of `Fact.predicate` and its fan comes from one more bounded read
(`engram/recall_predicates`, index seek per named predicate); the named entities' own facts always join the candidates
(`engram/recall_hop_facts` at hop 0, §3.3); each cue is floored at 0 (never a penalty); `PLEXUS_ACT_CUES=entity` restores
point 1 above exactly; the identity contract (point 3) is unchanged. **What the registered run found, against this decision's
own reading:** the 20 residual L5b displacers are *not* "another predicate of the same sprint subject" — they are the
scenario's 20 `CONTRADICTS` pairs (two active `auth_method` facts per subject, same entity, same predicate, both probes), so
85.7% is the L5b recall@1 ceiling for any value-blind scorer and P1 had already reached it; the predicate cue changed no L5b
rank (hard criterion falsified), and at CROSS_CHECK's constants (`0.6 / 0.4 / S = 5`) it raised the noise share by 4–11 points
(the entity cue at ×3.5 relevance lifts the named entity's noise over every other entity's real facts). The hub variant
(plan §5.3) passed (100%) but relevance alone scored 97.5%, so the plan's "flat boost returns an arbitrary hub fact" claim is
false and the variant is weak evidence. A labelled post-hoc sensitivity found the *structure* right and the *magnitude* ~20×
too large; the `1/20` scale (`0.03 / 0.02 / 5`, the entity cue at fan 12 = P1's 0.075) was then pre-registered with an outcome
rule and confirmed (recall@1 at the ceiling in all three runs, noise share below the single-cue form in every run). **Amended
decision:** the shipped default is the two-cue term at `0.03 / 0.02 / 5` (`sep+mult`: 85.7% / 100% / noise 20.6–20.9%); the
registered number of record for CROSS_CHECK's constants stays the falsified one. Follow-ups: the order *inside* a contradicting
pair is undefined by any cue (recency, P3 reliability or `resolve_contradiction` are the candidates — a new pre-registration);
the L5b "same-entity gap" should no longer be cited as a product defect; the §3.3 union's ~5-point noise cost on L5b is the
price of completeness about the named entity and is recorded, not hidden; the SQL arm of §5.4 was not given the predicate
feature (tie claim unchanged).

**Amendment 2026-10-17 (2) — the shipped default matches the text; one additive formula (`docs/research/BRANCH_REVIEW.md`
findings 1–2, `CYPHER_AUDIT_SUMMARY.md` C1).** Point 2 says `mult` is "byte-for-byte D-012 (plus the bypass fix and separation)"
and lists "salience ≥ 0.5 protects from sweeps" among the P2 features, but the code applied the salience rule in both modes: in
`mult` a fact protected by none of D-012's rules became protected (neutral-activation floor in recall, skipped by sweeps) after,
e.g., one confirmed `verify_fact`, three distinct using agents, or — through C1 — one artifact re-verified twice. **Decision:** the
text stands and the code follows it: the salience rule is gated on `add` mode (`activation/service.py`, `st.additive`; the L5b SQL
arm mirrors it with an `:additive` parameter, so the fidelity check stays a like-for-like comparison). Salience is still computed,
cached and reported in both modes (`memory_strength`, `pin_fact`); only the *protection* is add-only. Second, `rank.rerank`'s `add`
branch now calls `score.score()` (the documented formula) instead of re-typing `ln rel + act + sep + sal`; `Ranked.act`/`sal` are
the reported components from the same helpers, so a future P3 `rel_term` wired into `score()` reaches production. (The unwired `rho` / `reliability` arguments of `score()` and `RELIABILITY_PRIOR` were removed in the cleanup (2026-10-18); `rho` defaulted to 0 and nothing passed it, so ranking is unchanged; reproduce at tag `pre-cleanup`.) Third, C1:
`activation/activation` now returns `verified_artifacts` (the ids of the independently verified artifacts FOR the decision's
*done* tasks, one per VERIFIED_BY path) and `salience_of` counts them DISTINCT as `artifacts_ok`; the old `size(...)` counted every
path over every task (one artifact verified twice on an open task scored 2). **Effect on the published numbers:** none expected —
the L5b fixtures carry no VERIFIED_BY / Artifact / multi-agent-use structure and no diamond scopes (pre-registered and re-run,
`docs/BASELINE.md` "Audit fixes re-run"). Also recorded here, from the same audit (B2): `engram/recall_predicates` (the
predicate cue's read) is one index seek per predicate; measured with the production index set, the 6.0.2 seek applies `status` and
`valid_to` together with `predicate`, so the superseded history and the expired facts are *not* read (2,000 + 1,500 of them: 0 index
records; `tests/integration/test_audit_recall_predicates_plan.py` pins it). What it does read is every *current* fact with that
predicate in *every* scope plus one `IN_SCOPE` hop each; the scope is an edge, not an indexed Fact property, so no single-property
index can absorb it and the cost of a common predicate grows with the number of current facts across the tenant's scopes, not with
its history. Documented in the query header; bounded by `RECALL_PREDICATES` (10 predicates per recall).

**Amendment 2026-10-18 (3) — P12's lexical fusion is off by default; recall's per-entity reads run once per entity (`docs/BASELINE.md`
"Recall-check", `docs/research/TRIALS_INT_MERGE.md` §6 items 1-3).** The merge of p12 into main left three open questions; this
records the answers, each measured under a pre-registration written before the first run.

*1. Double counting.* p12's `fuse_scores` (relevance = `(1 - w) · cosine + w · lexical`, `w = 0.5`) and D-013's cues both reward query words that sit
in the entity name or the predicate (the lexical score counts them as coverage, the cue term adds `w · (S - ln fan)` for the same match). The
decision was made by the rule fixed before the runs: nine criteria (L5b `sep+mult` recall@1 / recall@5 / critical loss / other-entity rows / noise
share over N = 5, 15, burst; hub `sep` recall@1; L8 needed facts, canonical, replay >= 28/36); if neither setting passes all nine, the default is the one
failing fewer. Measured on the merged build with FalkorDB 6.0.2: **lexical OFF fails 2** (noise share 32.3 / 41.6 / 33.3 % against the registered <= 24 %;
L8 replay 27/36), **ON fails 3** (the same two, noise 42.7 / 60.1 / 41.6 %, and one critical probe lost of 80 at N = 15, where D-012/D-013 had 0). On the
metrics that were reported but not criteria, OFF is also ahead (L6-C `P-product` `hit_any` at depth 1/2/3: OFF 23/9/0 = main's tip today, ON 13/3/1) or
level (the two clean L8 runs found the same facts in every replay call). The fusion's clear gains are on flat retrieval: the hub world's no-scoring arms (100 % instead
of 96.5 %) and L5b `off` recall@1 (85.0 % instead of 79.3 %); D-013's cues already give the same in the arms that ship (`sep` 100 % / 85.7 % in both settings). **Decision: `PLEXUS_RECALL_LEXICAL_WEIGHT` defaults to 0** (main's
relevance, `1 - rank`); `FUSION_WEIGHT = 0.5` is what the fusion was designed with and is available as an opt-in (`PLEXUS_RECALL_LEXICAL_WEIGHT=0.5`).
The fusion code, its tests and its env switch stayed in the tree then. Removed in the cleanup (2026-10-18); reproduce at tag `pre-cleanup` (`fuse_scores`, `PLEXUS_RECALL_LEXICAL_WEIGHT`, harness `PLEXUS_L5_LEXICAL_WEIGHT`). Honest limits of the decision: it is a count of two failures against three, one of them the replay
number, which moves by +-1 between plays of identical code (27, 28 and 29 were all measured: new ids decide the near-ties of the twenty
`billing_cycle` facts); without that criterion the counts are 1 and 2 and the decision is the same. The L5b / hub harness keeps its pin
(`PLEXUS_L5_LEXICAL_WEIGHT`, default 0) was removed with the switch: it equalled the product default.

*2. Published numbers on the merged build.* Recall@1 (85.7 %, the ceiling), recall@5 (100 %), critical loss (0), cross-entity displacers (0) and the hub
result (100 %) reproduce with the fusion off. **The noise share does not, in either setting, and is reported as a moved number:** `sep+mult` 32.3 % (N = 5),
41.6 % (N = 15), 33.3 % (burst) on the merged build against 22.1 / 20.0 / 21.6 % measured today on main's tip `1ddeb13` through the same harness (published
20.6-22.1 %); `sep+mult` no longer removes noise relative to `sep` (31.7 -> 32.3, where it removed 4-9 points on main). The fusion explains part of it
(ON - OFF: +10.4 / +18.5 / +8.3 points); a remainder of +10.2 / +21.6 / +11.7 points over main is already present on p12's own tip before any D-013 code
(`off` mode: 40.3 / 57.4 % there, with the fusion on) and **no single switch removes it** (bypass text, pool size, value-only keyword ids: post-hoc X1, X3, X4,
X5, all within +-2 points; dropping the keyword channel (X2) cuts the noise to 16.7 / 17.7 % but costs recall@1 (72.9 / 68.6 %), because the keyword bypass is
what shields the cold target facts from the D-012 multiplier). The cause is therefore **not attributed**; the untested differences are the Python sibling boost
(seeds, order), the fused sort, and the `search_text` full-text ranking. The published noise-share figures of `PLEXUS_REPORT` §7.5 describe main's build, not the merged one. L6-C's product arms
(the only L6 family that calls `recall`): `hit_any` is 23 / 9 / 0 against the published 11 / 6 / 1, but main's tip gives the same 23 / 9 / 0 today (the published row predates main's predicate cue and
section 3.3 union), the merged build with the fusion off reproduces it exactly and with the fusion on it is 13 / 3 / 1; strict stays 0/75 in every run, as registered. L6 A/B/D/E/F do not call `recall` and are re-run once for the write-path
changes of the merge (see BASELINE).

*3. `fan_e` on a hub.* Confirmed as a defect, then fixed: `fan_e` and the sibling scan ran per surviving row (up to `$lim` = 120-300 rows after p12), so a
hub contributing 60 rows rescanned its `ABOUT` edges 60 times: 61,295 records in one operator for a 1,000-fact hub (289 ms), 305,295 for 5,000 facts (1,478 ms).
They now run once per distinct entity in a `CALL` subquery (1,060 and 5,060 records, 19.6 and 34.2 ms); rows, ranks, `damp` and `sib_of` are unchanged (576 old-vs-new
parameter sets, 0 differences) and `tests/integration/test_recall_hub_plan.py` pins the record counts at both sizes.

## D-014 — Integration of p9f-b: one statement per answer, and a write's provenance (integ, P9-f)

**Context.** Branch `p9f-b` fixed what Crucible L6 found (impact timeout and truncation, `why` / `blocked_by_failure` read
as several statements that tore under concurrent writes, 7.6% of records without Step/WROTE after a hard kill). `main` had
meanwhile merged `p9int` (impact rewrite, depth args, WROTE folded into the write statements) and the Cypher audit
(quarantine / forget CALL tails, `why_derived_level` bind-first). Both fixed overlapping problems differently; 31 files
conflicted, so each p9f-b commit was decided on its own (`docs/research/INTEG_MERGE.md`).

**Decision.**
1. *Reads that must be one snapshot are one statement:* `lineage/why_edges` (ancestry + display props, replaces
   `why_derived_level` and the `node_info` round trip) and `relay/dependents_closure` (replaces `dependents_of` + the
   Python loop). The audit's bind-first rule is kept and pinned on `why_edges`.
2. *`impact` never hides a cut list:* P9-int's output is kept and extended with `records` (status, valid_from,
   created_at), `order`, `offset` / `next_offset`, `ids_truncated`, `probe_ids`. The 2,000-id cap of P9-int stays (p9f-b
   used 200); paging and probes make a cut harmless at any cap.
3. *A write's provenance:* the Step / WROTE design of P9-int / P12 is kept (the runtime opens the Step first and the
   statement writes WROTE; `FOLDS_WROTE`), not p9f-b's `StepIntent` (the statement creates the Step). Two ways to do the same
   thing in one tree would make every tool answer "which one?"; the kill loop shows 0 orphans with the kept design. Only the
   part with no equivalent moved: `assert_fact(derived_from=...)` writes DERIVED_FROM inside its statement (before it was
   `Lineage.derive_from`, a second statement, and a hard kill between them lost the link for good: 9 of 1,240, 13 after P9-int).

**Not done, on purpose.** READ edges of a write are still linked after it (a lost READ edge is not an orphan: the memory and
its WROTE exist). `StepIntent` is not ported. `quarantine` / `forget_source` keep the audit's CALL tails (p9f-b's
one-pass join is the same idea; their scale test passes unchanged).

## D-015 — Multi-source facts: quarantine and forget respect a fact's other live sources (P13, trial 8)

**Context.** Trial 8 (`trials/FINDINGS.md` section 5): rule C1 was required by two documents (compliance memo and product
spec). `assert_fact` took one `source_id`; all four Plexus runs linked C1 to the memo and wrote "also product P2" into the value
text. In session 3 ("the memo is void") C1 was kept only because the agent read that text; `quarantine_source(memo)` would have
hidden C1 and `forget_source(memo)` would have forgotten it. No run used `quarantine_source` or `why`.

**What was already true.** The model never limited a fact to one source: a `Fact` has one `DERIVED_FROM` edge per Source, `why`,
`recall(detail=full)`, the View API and `activation` already read them as lists, and the duplicate path of `assert_fact` already
MERGEd `source_id` / `derived_ids` onto the existing fact. What was single-source was the **write surface** (one `source_id`) and the
**retraction semantics** (`quarantine` / `forget_source`: "reaches the Source, so it goes"; the `forget_source` header: "forgotten as soon as
ANY of them is forgotten"). So the fix is in four places, not in the model: no new label, edge type or tool.

**Decision.**
1. *Write.* `assert_fact(source_ids=[...])` (max 20, unioned with `source_id`; the MCP argument is a list). Every listed Source gets its
   own `(fact)-[:DERIVED_FROM]->(Source)` edge in the one assert statement. An id that is not a Source rejects the whole call (nothing
   written, not even the Entity): a silently dropped source would be the trial-8 failure again, and a half-linked fact cannot be
   told from a complete one. `source_ids` travel in the existing `derived_ids` parameter (one MERGE per origin; the Python layer
   checks they are Sources first with `engram/existing_origins`), so the statement's shape and plan are unchanged.
2. *Corroboration.* Asserting an existing value again with sources the fact does not have links them to the existing fact (the
   `duplicate_of` path, tier 0 / 1 / 2 alike) and the result says so: `duplicate_of` plus `sources_added: [...]` (`[]` when the call
   added none; absent for a new fact, to keep the response small). `sources_added` is computed in the statement before its writes (one
   pattern comprehension from the bound duplicate). No `link_source` tool: the duplicate path expresses it, and every extra tool is
   resent on every model call.
3. *Quarantine.* `quarantine_source(S)` marks the Source (`Source.quarantined_at`) and hides a reached fact only when it has **no direct
   `DERIVED_FROM` edge to another Source that is not quarantined**. The others stay as they are and come back as
   `corroborated: [{fact_id, other_sources}]` (+ `corroborated_total`), next to `fact_ids` (= the hidden ones). Reads, decisions and
   handoffs describe the hidden facts only. Quarantining the last live Source of a corroborated fact later hides it; the order of
   the two calls does not matter. `release_quarantine(S)` clears the mark and restores every quarantined fact in S's cascade (it has
   S, now live), so a fact hidden by two quarantines is back as soon as one is released. Facts with no source are never reached.
4. *Forget.* `forget_source(S)` forgets a reached fact only if S was its only remaining Source. A fact with another Source keeps its
   status; only its edge to S is deleted (inside a `CALL`, the one write there) and it is listed as `unlinked: [{fact_id,
   other_sources}]` (+ `unlinked_total`). If all its remaining Sources are quarantined it becomes `quarantined` (nothing live supports
   it any more). Forgetting the second Source later forgets it. Idempotent: a second call finds nothing linked. This replaces "any source
   forgets the fact": the old rule was only right while a fact could name one source.
5. *Why / recall.* `why` already lists every source (`facts[].sources`, one `DERIVED_FROM` edge each), and `impact(kind=source)` gains
   `facts.corroborated {total, ids, ids_truncated}` so the preview shows which facts `quarantine` would keep. Compact `recall` hits carry no
   source information (P12 token cut) and still don't; `detail=full` lists every `DERIVED_FROM`.
6. *Tool descriptions.* `assert_fact`: "A fact several documents support: pass all of them in source_ids", with the duplicate case.
   `quarantine_source` / `forget_source`: when to use them (wrong, withdrawn or void source) and that facts another source supports
   stay. The `source_id` argument text was shortened to pay for part of it: the list grows by 418 characters (core 30,182 -> 30,600,
   full 47,843 -> 48,261 by `crucible/l8/manifest_size.py`, a $0 count; `manifest_probe` needs paid `claude -p` calls), guarded by a
   450-character test budget. Empty `corroborated` / `unlinked` are not sent.

**Cost (GRAPH.PROFILE, `demo_data/crucible/t8replay/profile.txt`).** One extra `CALL { WITH src, fs ... }` per query: `UNWIND fs`, one
pattern comprehension of the fact's Source edges (raw values; the filter is a plain list comprehension), one aggregate row out. Records
+30% on 5,000 facts with two sources each (quarantine 100,064 -> 130,071 records, 358 -> 456 ms; forget 80,061 -> 105,075, 359 -> 452 ms;
impact_source 95,065 -> 125,069, 354 -> 430 ms; release unchanged). The brief's ">10 s for 5,000 facts" does not reproduce on integ
(0.36 s: the audit / P9-int `CALL` tails already fixed it). Plan shape pinned: no operation produces more than 3 records per cascade fact
next to 1,500 unrelated facts (`tests/lineage/test_multisource_plans.py`). `lineage/impact_source` is generated: the generator changed.

**Known limits (reported, not hidden).**
- Support is judged on a fact's **direct Source edges**. A derived fact (fact -> fact) is rescued only by a Source of its own, never
  by a corroborated parent: if C1 stays because of the spec, a fact derived only from C1 is still cascaded with the memo (same as before;
  quarantine is reversible, forget is not). Following parents would need a fixpoint over the 12-hop levels inside one statement.
- `activation` still counts a quarantined high-trust Source as protecting a fact (any `trust: high` source in the cascade).
- Unknown tool arguments are silently dropped by the MCP layer (before P13 a client sending `source_ids` got no error and no link);
  this is the framework's behaviour, not changed here.
- The agent still has to name both documents. The tool nudge is the whole defence; whether it changes agent behaviour is measured by a
  paid t8 re-run, which this change does not include (`python -m plexus.crucible.t8_replay` is the $0 check of the engine side).
- The duplicate path already linked `source_id` onto the existing fact before P13 (it just did not say so); the brief's "re-asserting from a
  second source drops it" does not hold on integ 1f9a8fa. The trial-8 runs lost the spec because they wrote C1 once, with the memo only.

**Proof.** `tests/integration/test_multisource_assert.py`, `tests/lineage/test_multisource_lineage.py` (+ `_plans`), `tests/mcp/test_multisource_tools.py`,
`tests/crucible/test_t8_replay.py`; the replay output is `plexus/demo_data/crucible/t8replay/` (`before_integ_1f9a8fa.*` is the same script on the old tree).
