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
