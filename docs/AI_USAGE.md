# AI usage disclosure (rule R7)

Plexus is built with AI assistance, and this file says where. The owner (Suprim) reviews the graph model, every
`.cypher` file and the architecture (rule R8), and records design decisions in `docs/DECISIONS.md`. Update this
file as work happens, not at the end.

## Tools

| Tool | Role in the build | Used in the product? |
|---|---|---|
| **Hermes Agent** (orchestrator, Claude Opus) | Plans phases, writes task specs, dispatches and reviews subagents, merges and commits | No. Building only; excluded from published runs and benchmarks (D-003) |
| **Claude Sonnet subagents** | Implementation: code, tests, queries and docs inside the files their spec assigns | No |
| **Claude Code** (`claude -p`, unmodified binary, the owner's own subscription) | The demo agents: planner, researcher, builder, connected to Plexus over MCP | Yes, as a client only. Plexus itself contains no LLM and holds no LLM credentials (D-002) |
| **fastembed** (bge-small, local CPU) | Embedding model for semantic matching | Yes. Not an LLM service; no key, no network call at runtime |

## Phase log

| Phase | What was AI-assisted | What the owner reviewed |
|---|---|---|
| P0 core | Sonnet subagent `P0-core`: `docker-compose.yml` (FalkorDB 6.0.2 with verified `FALKORDB_ARGS`), `plexus/` uv project (graph client with sync and asyncio variants, tenancy, query-library loader, idempotent schema applier), schema `.cypher` files, 55 tests, `scripts/agent_db.sh`, `docs/graph-model.md`, `docs/queries.md`, this file, README stub. Orchestrator: spec, review, commit | _TBD: owner review of graph model v1 and schema files before the freeze_ |
| P1 | Sonnet subagents `P1-A Engram` and `P1-B Relay` (service code, `.cypher` queries, 149 tests incl. 50-thread no-double-claim). An independent Sonnet **reviewer** found 2 blockers, 2 majors and 8 minors, each verified with probes. Sonnet subagent `P1-fix` fixed all 12 test-first (313 tests on main after the merge). Orchestrator: specs, gates, merges, fix decisions | _TBD_ |
| P2 | Sonnet subagents `P2-D Lineage` (provenance, time travel, forget/quarantine), `P2-E` (MCP server stdio+HTTP with tenant pinning, ToolCall audit, read-only View API, Dockerfile/compose) and `P2-int` (Lineage wired into the tool layer). Claude Code headless smoke runs (haiku) as an MCP client | _TBD_ |
| P3 | Sonnet subagents `P3-F` (Acme Notes scenario, scripted agents, the `claude -p` orchestrator, recorder/replay, CLI) and `P3-G` (View: Flow, Time Machine, Why, Explorer upgrades, ablation toggle, Inventory, Results). **Claude Code (sonnet/haiku) as the demo agents:** one pilot plus one full recorded run (`demo_data/recordings/acme-claude-sonnet`, 16 processes, $0.70 notional) | _TBD_ |
| P4 | Sonnet subagents `P4-H` (Crucible backends, L1/L4, ablation) and `P4-I` (L2 questions + runner, L3 pilot). **Claude Code (sonnet) as the baseline answerer** in L2 (129 `claude -p` calls, $5.53 notional, cached in `demo_data/crucible/l2_cache`) and in the L3 pilot ($1.70). Plexus itself answers with deterministic Cypher (no LLM) | _TBD_ |
| P5 | Four read-only Sonnet **reviewer** subagents (queries, concurrency/tenancy, MCP/API surface, view/tests) and three fix subagents, plus an integration subagent. The orchestrator merged them and fixed integration breaks | _TBD_ |
| P6 | _TBD_ | _TBD_ |

## Statement of understanding

The owner can explain the graph model (`docs/graph-model.md`), each query (`docs/queries.md`), the architecture
(`docs/PLAN.md`) and the decisions (`docs/DECISIONS.md`). Anything an AI wrote that the owner has not yet reviewed
is marked _TBD_ in the table above.
