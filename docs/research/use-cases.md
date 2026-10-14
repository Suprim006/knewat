# FalkorDB use cases for agent memory & coordination (Track 02 research)

Research only, no code. Every project below had its README/page read on 2026-10-14. Relevance = fit to Track 02 (high/med/low). Stars/benchmarks deliberately omitted unless read on the page.

## Projects

1. **Graphiti (Zep)** — [repo](https://github.com/getzep/graphiti). Temporal context-graph framework; FalkorDB is a supported backend (`pip install graphiti-core[falkordb]`) ([README](https://github.com/getzep/graphiti)).
   - Model: Entities (nodes), Facts (edges with validity windows: when true / when superseded), Episodes (raw provenance), custom Pydantic types ([README](https://github.com/getzep/graphiti)).
   - FalkorDB use: graph + hybrid (semantic+keyword+traversal) retrieval store. Python. **High.**
   - Copy: episode-to-fact provenance plus validity windows is the reference temporal schema.

2. **Graphiti MCP server on FalkorDB** — [FalkorDB docs](https://docs.falkordb.com/agentic-memory/graphiti-mcp-server.md). Docker Compose "combined image" bundles FalkorDB + MCP server at `http://localhost:8000/mcp/`.
   - Tools: episode add/get/delete, fact and node search, `group_id` groups, queue-based async ingestion with a `SEMAPHORE_LIMIT` concurrency cap (tuned to avoid LLM 429s). Built-in types include Preferences, Procedures, Events.
   - Copy: queue + semaphore for write concurrency. **High.**

3. **Gralkor / `@gralkor/openclaw`** — [repo](https://github.com/elimydlarz/openclaw_gralkor). OpenClaw memory plugin: Graphiti + FalkorDB (falkordblite embedded), FastAPI sidecar, TypeScript harness.
   - Hooks: `before_prompt_build` (auto-recall), `agent_end` (capture the turn as a role/content list), `session_end` (flush). Tools: `memory_search`, `memory_add`, `memory_build_communities`.
   - Pattern: `group_id` = sanitised `agentId`, a per-agent graph partition; hyphens must become underscores (RediSearch constraint). Each hook derives the group independently, so there is no shared session→group map. **High.**

4. **mem0-falkordb + openclaw-mem0-demo** — [plugin](https://github.com/FalkorDB/mem0-falkordb), [demo](https://github.com/FalkorDB/openclaw-mem0-demo). FalkorDB graph store for Mem0, added via runtime patching with no Mem0 source changes.
   - Pattern: each user gets their own graph (`mem0_alice`, `mem0_bob`). No `user_id` WHERE clauses, and `delete_all` drops the graph. Docs list Neo4j→FalkorDB Cypher translations (`id(n)`, `db.idx.vector.queryNodes`, `vecf32`).
   - Demo adds auto-capture/auto-recall plus 5 memory tools in OpenClaw. Python/TS. **High** (the tenancy template).

5. **Cognee + FalkorDB** — [FalkorDB docs](https://docs.falkordb.com/agentic-memory/cognee.md). Community hybrid adapter; FalkorDB serves as both graph and vector store (`falkor` provider for both configs).
   - Flow: `add()` → `cognify()` (LLM extracts entities/relations) → `search()`. Needs Python 3.11–3.13. **Med.**

6. **Invarail (formerly LocalClaw)** — [repo](https://github.com/PeterGreenAppliedAI/Invarail). Governed local agent for 7–30B models.
   - Memory: FalkorDB graph with native HNSW vectors; typed entities; `SUPERSEDES` edges instead of overwrites; provenance on each fact (`stated|observed|inferred`; only human-reviewed `!save` counts as stated); relevance floor on injection; intake every 8 turns ([README](https://github.com/PeterGreenAppliedAI/Invarail)).
   - Caveat: the graph is one of four memory backends (graph/flat/vault/legacy), so FalkorDB is optional there. TypeScript. **Med-high.**
   - Copy: provenance enum plus "learning may inform execution but never expand authority".

7. **Synapse** — [repo](https://github.com/Ardha-Eco-System/synapse). Hermes memory-provider plugin on Graphiti + FalkorDB, with a "hippocampus" layer.
   - Algorithms: salience scoring, Ebbinghaus forgetting curve, consolidation job (Hebbian co-occurrence, contradiction detection, pruning), reconsolidation, pattern completion (BFS expansion), retrieval-induced forgetting.
   - Hooks: `on_episode_ingested` and `on_recall`. Retrieval is BM25 prefetch with a background cache. `falkor.py` includes a "temporal workaround". Python. **High.**

8. **Dragon Brain** — [repo](https://github.com/iikarus/Dragon-Brain). MCP server (34 tools): FalkorDB graph + Qdrant vectors + BGE-M3 embeddings + Streamlit dashboard. "Librarian" agent clusters memories into concepts; time-travel queries.
   - Trick ("fail loud"): a `SearchError` contract so a crashed backend is never reported as "no memories". Qdrant failure rolls back the FalkorDB write (cross-store compensation). `testcontainers` kills real FalkorDB/Qdrant mid-operation in CI. A fixed Cypher label-injection bug is documented ([README](https://github.com/iikarus/Dragon-Brain)). **High.**

9. **multi-agent-graph-memory (Guild case study)** — [repo](https://github.com/sadbeto/multi-agent-graph-memory). One orchestrator + specialists (router/security/research/planning/build), each with its own named FalkorDB graph behind one Graphiti MCP server.
   - Principles: isolation beats one giant memory; verify retrieval through the same MCP path agents use; a successful write is not a usable memory; reinforce agent identity when graph context mentions other agents. Docs-first, no private data. **High.**

10. **graph-memory-mcp** — [repo](https://github.com/river-ai-lab/graph-memory-mcp). FastMCP service on FalkorDB: facts with embeddings, entity triplets, context-subgraph extraction, fact versioning/soft-delete, auto-`MENTIONS` edges, dedup/archival jobs.
    - Isolation by `owner_id` (alphanumeric plus `-_@`). A `memory_policies_for_LLM.md` is meant to sit in agent context at session start. Read-only Graph Explorer UI. Python. **High.**

11. **Cortadel** — [repo (SDKs/docs only)](https://github.com/cortadel/cortadel). Bi-temporal memory engine over FalkorDB or Memgraph, .NET 10; REST + MCP + dashboard.
    - Five-verb write pipeline (store/invalidate/delete/touch/resolve), reversible entity merging, Louvain communities (including cross-user shared ones), per-user backup/export, **zero LLM calls on read**. The server is a closed container image; only SDKs are open. **High.**

12. **RAGBrain** — [repo](https://github.com/Nagendhra-Madishetti/ragbrain). Bi-temporal graph on FalkorDB/Neo4j via Graphiti.
    - Four timestamps per fact (`valid_at`, `invalid_at`, `created_at`, `expired_at`) plus a `superseded_by` back-link. System-time replay: "what did we believe before the correction?". The "un-knowing" invariant is tested in CI against a live FalkorDB. **Med-high.**

13. **memore** — [repo](https://github.com/bartkamphuis/memore). Write-time deterministic consolidation: `(subject key, freshness ordinal, value equality)` decides supersession, with a test asserting no LLM is in that path. Recall is injected before the model call (200 ms P95 budget). Superseded facts stay visible, marked SUPERSEDED. FalkorDB runs in Compose; local models. Its README says the open problem is extraction naming one subject differently (subject agreement 0.583 across paraphrases). **Med.**

14. **agent-memory-bench** — [repo](https://github.com/zhang-liz/agent-memory-bench) (by FalkorDB's DevRel lead, disclosed). Compares full-context, compaction, memory-tool, vector, SQLite and FalkorDB (read-only Cypher over extracted facts) on lookup / multihop / transitive / "changed" / verbatim questions.
    - Includes a graph-DB test with concurrent writers; FalkorDB uses one graph per user, while Neo4j/Memgraph Community use one DB with a `user_id` index. Its own caveat: SQLite wins simple lookups and concurrent writes, and loses on multi-hop at 1M edges. **High** as an eval template.

15. **MERIDIAN** (Graph Hacks 2026 entry) — [repo](https://github.com/aniruddhaadak80/meridian-graphhacks). Four agents (Scout → Archivist → Guardian → Oracle) share one graph per tenant (`meridian_<tenant>`). Guardian writes Episode + Task nodes back.
    - Tricks: `npm run ablation` severs all relationships and shows 8/8 capabilities collapse (proof that the graph is load-bearing); idempotent MERGE Cypher export; `/api/proof` and a Cypher log for judges; tenant switch = fully isolated graph. Its README also notes an in-memory mirror fallback when FalkorDB is unreachable. **High.**

16. **Board of SuperVision** (Track 1/3 style; Hack for Humanity) — [repo](https://github.com/LabGuy94/boardofsupervision), described in the [FalkorDB blog](https://www.falkordb.com/blog/how-builders-at-hack-for-humanity-used-falkordb-to-solve-real-community-problems/). 66 meetings → 7,553 nodes; votes are `VOTED` edges, which enables "who dissents together" queries.
    - Guard: all reads go through `ro_query` with a 3 s timeout, a regex blocking write keywords, and `LIMIT` capped at 100; the UI shows the Cypher it ran; eval 30/30; every answer carries a video-timestamp citation. **Med** (guard pattern).

17. **Can I park here? / LOCAL GACHA** (same [blog](https://www.falkordb.com/blog/how-builders-at-hack-for-humanity-used-falkordb-to-solve-real-community-problems/)) — Parking: graph named by a hash of its source data plus a ready flag flipped after import, idempotent `UNWIND…MERGE` in batches of 300, and `collect()` returns a JSON string via a raw Redis client. Gacha: the model gets no DB credentials and only sees returned rows, and the "why" (shared area/experience) is returned with each row. **Low-med.**

**Other Graph Hacks 2026 entries seen (competitors; read-only awareness):** [GraphMem](https://github.com/tuoitrevohoc/graphmem) (Fact/Decision/Task/Agent nodes; `supersedes`/`depends_on`; a planner and a coder coordinate only through the graph; its HONESTY notice repeats the rule that FalkorDB code must be written during Oct 14–18), [ZeroCapital Graph Memory](https://github.com/renigat7-cpu/graph-hacks-2026) (episodic/semantic/procedural in one graph, multi-hop trace as audit trail), [Mnemo](https://github.com/Nakul443/Mnemo) (LangGraph, replaced facts kept as history, meant to be shared across agents later; README is thin).

## Reusable patterns for Track 02

- **One graph per tenant/user, not a `user_id` filter**: simpler queries, instant delete by dropping the graph ([mem0-falkordb](https://github.com/FalkorDB/mem0-falkordb), [MERIDIAN](https://github.com/aniruddhaadak80/meridian-graphhacks), [bench](https://github.com/zhang-liz/agent-memory-bench)). Sanitise IDs (no hyphens for RediSearch) ([Gralkor](https://github.com/elimydlarz/openclaw_gralkor)).
- **Per-agent lanes in one instance** plus an orchestrator that routes writes; verify with the same MCP path agents use ([Guild](https://github.com/sadbeto/multi-agent-graph-memory)).
- **Supersede, never overwrite**: `SUPERSEDES`/`superseded_by`, `valid_at`/`invalid_at` ([Invarail](https://github.com/PeterGreenAppliedAI/Invarail), [RAGBrain](https://github.com/Nagendhra-Madishetti/ragbrain), [Cortadel](https://github.com/cortadel/cortadel)). Add a transaction-time axis for "what did we believe then".
- **Deterministic, LLM-free consolidation and reads**; keep the LLM only on the extraction side ([memore](https://github.com/bartkamphuis/memore), [Cortadel](https://github.com/cortadel/cortadel)).
- **Provenance on every fact** (`stated|observed|inferred`, episode links) ([Invarail](https://github.com/PeterGreenAppliedAI/Invarail), [Graphiti](https://github.com/getzep/graphiti)).
- **Fail loud**: never map a backend error to "no memories"; test with killed containers ([Dragon Brain](https://github.com/iikarus/Dragon-Brain)).
- **Ablation test** that severs edges to prove FalkorDB is load-bearing (hackathon rule) ([MERIDIAN](https://github.com/aniruddhaadak80/meridian-graphhacks)).
- **Read-only guard**: `GRAPH.RO_QUERY`, timeout, write-keyword block, LIMIT cap, show the Cypher in the UI ([Board of SuperVision](https://www.falkordb.com/blog/how-builders-at-hack-for-humanity-used-falkordb-to-solve-real-community-problems/)).
- **Async write queue with a concurrency semaphore** and a flush-on-session-end hook ([Graphiti MCP](https://docs.falkordb.com/agentic-memory/graphiti-mcp-server.md), [Gralkor](https://github.com/elimydlarz/openclaw_gralkor)).
- **Idempotent `MERGE` seeding** so re-runs are safe; ready flag before reads ([blog](https://www.falkordb.com/blog/how-builders-at-hack-for-humanity-used-falkordb-to-solve-real-community-problems/), [MERIDIAN](https://github.com/aniruddhaadak80/meridian-graphhacks)).
- **Background consolidation/decay jobs** (salience, forgetting curve, dedup, communities) ([Synapse](https://github.com/Ardha-Eco-System/synapse), [graph-memory-mcp](https://github.com/river-ai-lab/graph-memory-mcp)).
- **Benchmark honestly against SQLite/vector** with multihop, transitive and "changed" questions ([bench](https://github.com/zhang-liz/agent-memory-bench)).

## Gaps / ideas nobody seems to have built (my inference from the repos above, not verified exhaustively)

- **Shared-state handoff protocol as graph primitives**: tasks with claim/lease/handoff edges between agents and conflict detection when two agents write contradictory facts. Most projects isolate lanes; GraphMem plans this but its repo has no code yet.
- **Cross-tenant "shared + private" overlay**: a per-tenant graph that reads through to a read-only org graph (Cortadel mentions shared communities; nobody shows a clean FalkorDB-native pattern).
- **Procedural memory as executable graph** (skills/runbooks with success/failure edges updated from outcomes). Procedures appear as an entity type, but I found no outcome-weighted skill selection.
- **Public concurrency benchmark for many agents** writing/reading the same and different graphs (bench covers concurrent writers but not multi-agent coordination semantics).
- **Memory time-travel UI for debugging agent decisions** ("replay what agent B knew at step N"), combining bi-temporal replay with multi-agent traces.
