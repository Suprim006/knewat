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
| P1 | _TBD_ | _TBD_ |
| P2 | _TBD_ | _TBD_ |
| P3 | _TBD_ | _TBD_ |
| P4 | _TBD_ | _TBD_ |
| P5 | _TBD_ | _TBD_ |
| P6 | _TBD_ | _TBD_ |

## Statement of understanding

The owner can explain the graph model (`docs/graph-model.md`), each query (`docs/queries.md`), the architecture
(`docs/PLAN.md`) and the decisions (`docs/DECISIONS.md`). Anything an AI wrote that the owner has not yet reviewed
is marked _TBD_ in the table above.
