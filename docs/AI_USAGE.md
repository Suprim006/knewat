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
| P7 | Sonnet subagents `P7-J` (staleness: anchors, `mark_changed`, `verify_fact`, code scan CLI and hooks), `P7-K` (activation forgetting: surprise, activation, recall re-ranking, pin / strength / sweep / restore) and `P7-int` (this integration: View API fields and endpoints, cross-module wiring, the pre-registered Crucible L5, the real run, docs). **Claude Code (sonnet) as the verifying agent** in the real run: 2 `claude -p` calls on a scratch copy of the owner's own project (`demo_data/recordings/physio-stale-sonnet/`). L5 itself made 0 LLM calls | _TBD_ |
| P9 | Sonnet subagents `P9-a` (Crucible B1h hand-written SQL control and the pre-registered L6 beat-SQL families, with an **LLM pilot**: 88 `claude -p` calls (Sonnet) as the answering arms B1a, B0g, B0r and the Plexus MCP tools, $7.09 of a $20 cap, every call cached), `P9-b` (level-wise traversals, `impact`, typed relations), `P9-c` (duplicate precision guards, soft duplicates, the 226-pair C7 extended corpus), `P9-d` (atomic entity resolution, unique constraint, race test) and `P9-e` (audit modes, read-only public tenants), then `P9-int` (fixes for the defects L6 exposed: `impact` on large blasts, `depth` arguments, `WROTE` folded into three write statements, View allow-lists and a possible-duplicate marker; the deterministic L6-A and L6-F re-run; the Results page rows; docs and counts). P9-int made 0 LLM calls | _TBD_ |
| NM (D-013) | Orchestrator research: six cited mechanism notes, survey, implementation plan, and an independent second-pass cross-check (`docs/research/neuro-memory/`). Implementation by the orchestrator on `feature/neuro-memory-research` (`plexus.activation.score`, `activation_spaced`, salience, `engram/recall_entities`, `rank.rerank`, lineage fields, tests); one Sonnet subagent extended the Crucible L5b harness (modes, burst variant, diagnostics, toy test). Benchmarks: 3 pre-registered L5b runs + 1 labelled post-hoc sensitivity, 0 LLM calls. Every `.cypher` change prototyped against a fixture where every rule fires (6.0.2 silent-wrong-answer traps) | No LLM in the product; the scoring is pure Python over graph reads |
| NM §5.4 (SQL arm + L6-C) | Orchestrator: the pre-registration, the L5b SQL arm (`crucible/l5/sql_arm.py`: export, three statements, harness `--sql`, fidelity check), the runs, the debugging of the arm differences and of the product's `recall(hops)` misses, and every doc edit. Sonnet subagent `l6c-build` (spec `.plexus-agents/specs/l6c-build.md`): the L6-C generator, loaders, arms, runner and toy test, built to the committed pre-registration; it reported its four deviations, which the orchestrator recorded as amendment 1 before the registered run, and its B1h fan computation was changed by the orchestrator to a correlated count before any scale-1.0 measurement. 0 LLM calls in the benchmark itself. | The orchestrator read every file the subagent wrote, re-ran the toy test, changed the SQL fan computation, and wrote the results and the walk-back of the §8 verdict ("beats SQL" not earned by any family) itself. |
| P6 | _TBD_ | _TBD_ |

## Statement of understanding

The owner can explain the graph model (`docs/graph-model.md`), each query (`docs/queries.md`), the architecture
(`docs/PLAN.md`) and the decisions (`docs/DECISIONS.md`). Anything an AI wrote that the owner has not yet reviewed
is marked _TBD_ in the table above.

The submission documents (`README.md`, `docs/VIDEO_SCRIPT.md`, `docs/BLOG_DRAFT.md`) were drafted by a Sonnet subagent from the
repo's own docs and result files. `python scripts/verify_readme.py` checks mechanically that their links resolve, their mermaid
parses, and every quoted number and recording id matches its source; it does not check that the wording is fair. The owner must
read those three files before submitting, and the video narration and the blog post are the owner's to edit and publish.
