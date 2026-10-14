# CLAUDE.md — Graph Hacks (FalkorDB) · Track 02: Agent Memory and Coordination

Guidance for AI coding assistants (Claude Code / Hermes / subagents) working in this repo.
Read this file fully before any work. The **Hackathon rules** section is binding: breaking
it can get the entry disqualified.

---

## 1. Event facts

| Item | Value |
|---|---|
| Event | Graph Hacks: Context for AI Agents (WeMakeDevs × FalkorDB) |
| Page | https://www.wemakedevs.org/hackathons/falkordb (rules: `/rules`, resources: `/resources`) |
| Window | **Oct 15 2026, 12:01 AM IST → Oct 18 2026, 11:59 PM IST** |
| Window in Nepal time (NPT, UTC+5:45) | **Oct 15 00:16 → Oct 19 00:14 NPT** |
| Our internal deadline | **Oct 18, 20:00 NPT.** Submission must be uploaded by then; the remaining 4h are buffer |
| Primary track | **Track 02: Agent Memory and Coordination** (prize: PS5 + GTA VI) |
| Other tracks (optional, must be named if entered) | 01 Agents That Act on Connected Data · 03 Company Brain |
| Side prizes | Best blog post (AirPods 5) · Top 50 projects (T-shirt) |
| Team | Solo or up to 4; each person can be on only one team |
| Help | FalkorDB Discord: https://discord.com/invite/Y2mMT9VdMy |
| Judging criteria | **Not published.** Optimise for the Track 02 focus list (§3) and the graph doing real work (§2, R3) |

## 2. Hackathon rules (binding)

- **R1 — FalkorDB is the primary graph DB** and must support a central part of the product.
- **R2 — The graph must do real work.** If the product still works with FalkorDB removed, it
  doesn't qualify. *Design test for every feature: "Does this need a graph traversal or graph
  write to work?"* Never put the core memory in SQLite/JSON/a vector store with FalkorDB only as a mirror.
- **R3 — Any deployment works:** Docker, self-hosted, or FalkorDB Cloud. Any language or framework.
- **R4 — Data must be public, synthetic, or ours.** No private, login-protected, paywalled, or
  personal data in the graph. Use **synthetic** users and conversations for demos, and never
  real people's PII.
- **R5 — Timing.** Main coding and design work starts **after** the event opens
  (Oct 15 00:16 NPT). Before that, only notes, ideas, graph-model sketches, and diagrams are
  allowed. **No application code before the start.** Git history must show the build happening
  inside the window.
- **R6 — Reuse is allowed:** frameworks, OSS libraries, public APIs, templates, public datasets.
  Only original work done during the event is judged. The main FalkorDB implementation must be new work.
- **R7 — AI assistants are allowed but must be disclosed.** Keep `docs/AI_USAGE.md` up to date
  (see §7).
- **R8 — The team must understand and be able to explain** the graph model, the queries, the
  architecture, and the technical decisions. Projects generated entirely by AI without real
  contribution or verification "may be rejected". Record every design decision in
  `docs/DECISIONS.md` with the reasoning, so the human owner can defend it.
- **R9 — Conduct:** WeMakeDevs Code of Conduct. No plagiarism and no gaming the judging.
- IP stays with the team.

### Required submission deliverables (all of them)
- [ ] Public source-code repository
- [ ] README with **setup instructions** and the **graph data model** (diagram + label/edge table)
- [ ] **The Cypher queries / graph algorithms the product depends on.** Keep them in `queries/`
      as named `.cypher` files and list them in the README
- [ ] Demo video of the working project (aim for ≤ 3 min)
- [ ] Live deployment (preferred) **or** complete local setup instructions
- [ ] Track(s) named in the submission: **Track 02 — Agent Memory and Coordination**
- [ ] (Optional) Blog post for the side prize
- [ ] `docs/AI_USAGE.md` disclosure

## 3. What Track 02 is judged on

> "Build agents that remember across sessions and share state with each other. Memory should
> persist, update over time, and be available to every agent that needs it."

Each focus area must show up **visibly in the demo**:

| Focus area | Module and how the demo shows it |
|---|---|
| Episodic, semantic, and procedural memory | **Engram:** `Episode` chains, scoped `Fact`s on `Entity`s, `Procedure`s with `Run` → `Outcome` success rates |
| Persistent conversation history | **Engram:** `Session` → `Episode` chains; kill every agent, restart, and they recall across sessions |
| Shared state and handoffs between agents | **Relay:** atomic claims and leases, `Handoff` nodes carrying artifacts and evidence, decision log |
| High-concurrency reads and writes | **Relay + Crucible:** 100–200 scripted agents; 0 double claims and 0 duplicate facts; p50/p99 measured inside Docker |
| Separate memory per user or tenant | **Engram:** one FalkorDB graph per tenant plus ACL, `Scope` nodes (user, project, global); leak probes report 0 |
| Memory updates over time | **Engram + Lineage:** validity windows, `SUPERSEDES`, `CONTRADICTS` caught at write time, "as of T" queries |
| Explainability (event-wide theme) | **Lineage:** `why(decision)` and `why_recalled(fact)` return graph paths; time machine "what did X know at step N" |

## 4. Project

> **Project: Plexus** (confirmed). It combines the recommended ideas from `docs/research/PROJECT_IDEAS.md`. See `docs/DECISIONS.md` D-001, D-008 and D-009.
> **Build plan: `docs/PLAN.md`** (phases P0–P6, graph model v1, MCP tool surface, View API, Definition of Ready for Testing).

**Pitch:** one shared graph brain for AI agent teams, the memory and coordination layer that Claude Code, Hermes and
other harnesses lack. Agents connect over MCP. Every memory, task, handoff and decision is a node in FalkorDB, so the
team remembers across sessions, works without stepping on each other, and can always answer *"why?"* and *"what did we know then?"*

| Module | Fixes (gap → who has it) | Core capabilities |
|---|---|---|
| **Engram** (memory) | Stale facts, global or unscoped memory, size caps, near-duplicates, skills without outcomes (Hermes, Claude Code, ChatGPT, Graphiti) | Episodic `Session`/`Episode` chains; semantic `Fact`s with validity windows + `SUPERSEDES`; duplicate and contradiction detection at write time; `Scope` (user/project/global) + graph per tenant; budgeted top-k hybrid recall (vector → graph → validity); procedural `Procedure`→`Run`→`Outcome` success rates |
| **Relay** (coordination) | Handoffs and decisions not queryable, no consistency model for concurrent writers, self-reported summaries (Claude agent teams, Hermes subagents/kanban, Letta, Mem0) | Dependency-aware atomic claims + leases + heartbeats; `Handoff` nodes carrying artifacts and evidence; `Decision`-`BASED_ON`→`Fact`; dead-agent reclaim |
| **Lineage** (provenance and trust) | No "why recalled", imprecise forgetting, memory poisoning spreading across agents (ChatGPT, OpenClaw, MAPLE-Guard and Misattribution papers) | `why(decision)` / `why_recalled(fact)` paths; "what did agent X know at step N"; forget-by-source cascade; quarantine of a poisoned source's blast radius (stretch) |
| **Crucible** (proof) | No benchmark covers concurrency, handoffs, tenant leaks or invalidation (LoCoMo, LongMemEval) | Backend-swap benchmark, `docs/BASELINE.md`: Files vs SQLite vs Vector vs Plexus |
| **Time Machine UI** | Memory is invisible | Live graph, per-tenant view, step slider, "why" path highlight, ablation switch |

- **Agents:** unmodified **Claude Code** in headless mode (planner, researcher, builder), connected over MCP (D-002).
  Any MCP client can connect, including a judge's own Claude Code ("bring your own agent").
- **Why FalkorDB is the core (R2):** it is the only state store. Recall, dependencies, "why", time travel, contradictions,
  quarantine and tenant isolation are all graph queries. Claims and leases are plumbing. Ablation demo: cut the edges and the features break.
- **Scope control:** MVP = Engram + Relay + `why` + time travel + Crucible L1/L2/L4. Stretch = quarantine, Crucible L3, procedures UI.
  Cut order: stretch first, then UI polish, never the MVP. Phases go in `docs/PLAN.md`.
- **Demo scenario:** generic software team ("Acme Notes API": planner, researcher, builder). The video script is in `docs/PLAN.md` P6.
- **Two projects (D-008):** `plexus/` = the product (FalkorDB + MCP server of deterministic Cypher + read-only View API).
  `plexus-view/` = the demonstrator (React + Cytoscape), which shows what's stored, how it flows (`ToolCall` nodes) and what the demo created. It never writes.

## 5. Tech stack (proposed; confirm at kickoff)

- **Language:** Python 3.12, managed with `uv` (`~/AppData/Roaming/Python/Python311/Scripts/uv.exe`)
- **DB client:** official `falkordb` Python client (`FalkorDB(host, port, password)` →
  `select_graph(name)`; use `graph.ro_query()` for reads, `graph.query()` for writes)
- **API:** FastAPI + MCP server · **UI:** minimal web UI or FalkorDB Browser (port 3000) for graph views
- **Optional building blocks** (reuse is allowed, but our own memory/coordination layer must
  stay the judged core): Graphiti, Mem0, Cognee, FalkorDB MCP Server, LangGraph, GraphRAG-SDK
- **Search:** FalkorDB vector index + full-text index, used together with traversal (hybrid recall)

### LLM access and Anthropic account rules (D-002, D-003; binding)
- **Plexus contains no LLM and holds no LLM credentials.** Every Plexus tool is a deterministic Cypher query.
  Semantic matching uses a **local CPU embedding model** (e.g. bge-small via fastembed): no key, no cost, reproducible.
- **Agents are the unmodified Claude Code binary** (`claude` v2.1.296 installed), signed in with the owner's own
  Claude subscription and started by our orchestrator:
  `claude -p "<task>" --mcp-config plexus.mcp.json --allowedTools "mcp__plexus__*" --max-turns N --output-format stream-json`.
  Don't use `--bare` (it needs an API key). Unset `ANTHROPIC_API_KEY`, or usage gets billed to the API instead of the subscription.
- Per Anthropic's [legal & compliance page](https://code.claude.com/docs/en/legal-and-compliance), never:
  1. add a "sign in with Claude" flow to Plexus;
  2. read, store or proxy Claude.ai OAuth tokens;
  3. let anyone other than the owner trigger LLM runs on the owner's subscription.
- **Hermes is excluded from published runs.** On this machine it currently uses an OAuth credential taken from Claude Code
  (third-party use of subscription credentials, which those terms don't permit). Hermes may be used for building the project, not as a benchmark or demo agent.
- **Public live demo:** scripted, non-LLM agents for the claim and concurrency scenes, plus **replays** of recorded real Claude Code runs.
  Real LLM runs appear only in the video. Optional "bring your own agent": a judge connects *their own* Claude Code to the public Plexus MCP endpoint, and each team gets its own graph.
- **Usage budget:** Pro/Max limits are shared with Claude chat. Use Sonnet/Haiku for agents, small scenarios, and `--max-turns`.
  Check account usage after a small pilot before full benchmark runs (unverified reports say headless usage draws a separate credit pool).

### Running FalkorDB on this machine (verified 2026-10-14)
- Docker Desktop works now (engine 26.0.0). Dev DB container:
  ```bash
  docker volume create falkordb_dev_data
  docker run -d --name falkordb-dev --restart unless-stopped \
    -p 127.0.0.1:6379:6379 -p 127.0.0.1:3000:3000 \
    -v falkordb_dev_data:/var/lib/falkordb/data falkordb/falkordb:latest
  ```
  Image `falkordb/falkordb:latest` = **FalkorDB 6.0.2** (module ver 60002). Pin this version in compose and deploy files.
  Browser UI: http://localhost:3000. No auth; bound to localhost only. Data survives `docker restart` (verified).
- **Image default module args:** `TIMEOUT 1000` (ms), `MAX_QUEUED_QUERIES 25`, `RESULTSET_SIZE 10000`; `THREAD_COUNT` = 12 here.
  The 1 s timeout and the 25-query queue limit will bite under load tests. Set them explicitly with `FALKORDB_ARGS`.
- **Latency gotcha:** going from Windows through Docker Desktop's port forward costs about 10 ms per round-trip
  (PING ~10 ms, small `ro_query` 25–75 ms) against ~0.3 ms inside the container and ~1 ms server execution time.
  → Run the app and load tests **inside Docker (same compose network)** for any concurrency or latency numbers,
  and report the server-side `run_time_ms` next to client timings.
- Fallback: FalkorDB Cloud free tier (100 MB, no persistence, stopped after 1 idle day and deleted after 7). Not for the judged demo.
- FalkorDB needs **Redis 8.0+**. The FalkorDB module is a Linux `.so`, so it will not load into the portable Windows Redis 8 build.
- Default ports: `6379` (server), `3000` (Browser). Connection settings come from env vars:
  `FALKORDB_HOST`, `FALKORDB_PORT`, `FALKORDB_PASSWORD`, `FALKORDB_USERNAME`.

## 6. FalkorDB gotchas (from docs.falkordb.com)

> **Full reference:** `docs/reference/FALKORDB_REFERENCE.md`. Read its §2 table, "Verified on 6.0.2: where reality differs from the docs", before writing queries.
> The most important items: vector cosine `score` is a distance (sort ASC); `datetime()` doesn't exist (use `localdatetime()` or epoch ms);
> `RESULTSET_SIZE` silently truncates rows; a runaway write ignored `TIMEOUT` and crashed the server, so bound every write.

- It speaks the **Redis protocol**: queries go through `GRAPH.QUERY` / `GRAPH.RO_QUERY`, not Bolt.
  Use the official clients, not Neo4j drivers.
- FalkorDB supports a **subset of OpenCypher** with its own extensions. Don't assume Neo4j-only
  syntax or APOC. Check https://docs.falkordb.com/cypher/known-limitations before using unusual clauses.
- **Concurrency:** reads run in parallel from a snapshot; **writes are serialised per graph**
  (FIFO). Every single query is atomic, but there are no multi-query transactions (only
  Redis `MULTI/EXEC`, which serialises across all graphs). → Make each memory write a single
  Cypher statement. Sharding writes across per-tenant graphs is both the scaling story and the isolation story.
- `LIMIT` does **not** limit eager ops (`CREATE`/`SET`/`MERGE`/`DELETE`).
- Unreferenced relationship aliases in `MATCH` can undercount; reference the alias if counts matter.
- Indexes don't help `<>` filters. Check plans with `GRAPH.EXPLAIN` / `GRAPH.PROFILE`.
- Always use **query parameters** (`$param`), never string-formatted Cypher (injection risk, and it defeats the plan cache).
- Algorithms available as agent tools: shortest path, PageRank, centrality, connected components, community detection.

## 7. Working conventions

- **Planning:** keep the phased plan in `docs/PLAN.md`; record decisions with their reasoning in `docs/DECISIONS.md`.
- **AI disclosure (R7):** `docs/AI_USAGE.md` lists the tools and models used (Claude Code /
  Hermes, subagent models) and which parts were AI-assisted versus written or reviewed by hand. Update it as work happens, not at the end.
- **Human-in-the-loop (R8):** the owner (Suprim) reviews the graph model, every `.cypher`
  file, and the architecture before they are merged. Subagents report their changes; nothing ships unreviewed.
- **Queries:** every Cypher query the product depends on lives in `queries/<area>/<name>.cypher`
  with a header comment (purpose, params, expected result) and is loaded from there by the code.
- **Tests:** pytest against a throw-away graph per test (`test_<uuid>`), which is deleted in teardown.
  Never test against the demo or tenant graphs.
- **Secrets:** `.env` is git-ignored; `.env.example` documents every variable.
- **Commits:** small and frequent, with clear messages. They show judges the work happened during the window.
- **Data:** only synthetic seed data (`scripts/seed.py`) is committed. No real PII.

## 8. Repo layout

Monorepo: `plexus/` (Python product) + `plexus-view/` (web demonstrator) + `docs/` + `docker-compose.yml`. Full tree: `docs/PLAN.md` §0.

## 9. Timeline (NPT; detailed phases in `docs/PLAN.md`)

| When | Goal |
|---|---|
| Before Oct 15 00:16 | Notes, research, decisions, eval plan only (R5) |
| Oct 15 | `git init`, compose, graph model v1, query library, Engram write/recall, MCP server skeleton |
| Oct 16 | Relay (claims, leases, deps, handoffs, decisions) + Lineage `why`/`who_knew`/`as_of`; Claude Code agents wired |
| Oct 17 | Crucible L1/L2/L4 + Time Machine UI + deploy; stretch: quarantine, L3 |
| Oct 18 by 20:00 | README (graph model, queries), demo video, AI_USAGE, blog draft, **submit**, then freeze |

## 10. References

FalkorDB: `docs/reference/FALKORDB_REFERENCE.md`, which links the six parts and the official docs.
Research: `docs/research/` (landscape, use cases, hosting, free-vm, PROJECT_IDEAS).
