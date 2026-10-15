# Testing Plexus: Definition of Ready for Testing, and the owner's checklist

Everything below was run on the `p5-int` branch (Windows 11, Docker Desktop, FalkorDB 6.0.2). Commands are copy-pasteable
from the repo root unless a `cd` says otherwise. "Evidence" is a command plus what it printed; numbers are from those runs.

## 1. Definition of Ready for Testing (PLAN §5 P5)

| # | DoRT item | Status | Evidence (command → result) |
|---|---|---|---|
| 1 | `docker compose up` from a clean clone works with no manual steps beyond `.env` | **met** | Clone of branch `p5-int` into an empty scratch directory, `.env` = `.env.example` + non-default ports (`FALKORDB_PORT=6367 FALKORDB_BROWSER_PORT=3067 PLEXUS_API_PORT=18067 PLEXUS_MCP_PORT=18767 PLEXUS_VIEW_PORT=15167`), `docker compose -p plexus-fresh up -d --wait` → 4 services `healthy` after **216 s** (3 image builds incl. the embedding model download). `docker compose run --rm plexus-cli demo replay acme-claude-sonnet --tenant demo` → `replayed ... 247 nodes, 708 edges (matches meta.json: True)`. Every View API endpoint answered (below). Screenshots `docs/screenshots/01..13`. The stack is run from the README Setup text, step for step |
| 2 | Suite green (Python + View), lint clean, reviewers' findings fixed or logged | **met**, findings log is the commit history | `cd plexus && ruff check . && ruff format --check . && PLEXUS_TEST_DB_PORT=<port> uv run pytest -q` → `ruff check` clean, `ruff format --check` clean (185 files), **869 passed** in 407 s (includes the main merge: L2, L2-scale, L3 tests). View, in a fresh clone: `npm ci && npm run lint && npm run typecheck && npm test -- --run && npm run build` → lint clean, typecheck clean, **143 passed** (21 files, at the clone's commit `18e4418`) and **150 passed** at the final commit after the L2-scale section, build ok. Reviewer findings (P5 Q1-Q11, C-01..C-11, D1-D7, P5C-01..07) are fixed in commits named after them: `git log --oneline --grep "P5"`; there is no separate open-findings file because none is open |
| 3 | Every MCP tool is callable from Claude Code headless and has a contract test | **met by contract test; real-Claude coverage is partial** | `tests/mcp/test_tool_coverage.py::test_every_registered_tool_is_called_through_mcp_by_some_test` fails if any of the 41 registered tools has no MCP contract test (in-memory MCP client, same JSON-RPC as a real client). Real headless Claude Code: the recorded Sonnet run called 11 distinct tools 83 times with 0 permission denials (`demo_data/recordings/acme-claude-sonnet/calls.json`), and the Haiku smoke in `docs/mcp.md` returned `v1`. The other 30 tools have **not** been driven by a real `claude -p`; the MCP HTTP endpoint of the compose stack answered `initialize` with the tool capability (`curl -X POST http://127.0.0.1:18767/mcp/t/demo ...`). Owner step 9 below drives `recall`/`why` from your own Claude Code |
| 4 | Demo replay and live scripted demo both run; one real Claude Code recording exists | **met** | In the fresh stack: `docker compose run --rm plexus-cli demo live --scripted --tenant live --speed 0` → `scripted run finished: 67 tool calls` with the kill/reclaim, v2 and contradiction events printed; replay as in row 1. Real recording: `plexus demo list` → `acme-claude-sonnet claude 247 nodes 708 edges sonnet` (83 steps, 16 `claude -p` processes, 0 denials, $0.698 notional; `docs/demo.md`) |
| 5 | Crucible L1, L2 and L4 results reproducible from one command | **partly met: two commands, not one** | L1 + L4 + ablation: `docker compose --profile bench run --rm crucible all` (`--quick` for ~2 min; full ≈ 24 min). L2: `python -m plexus.crucible.l2.run run --mode full` (the 129 `claude -p` answers are cached, so a rerun is free and byte-reproducible; a first run costs ≈ $5.5 of subscription), L2-scale: `python -m plexus.crucible.l2.scale_run run --mode full` (cached, first run ≈ $6.5). Then **`python -m plexus.crucible.combine`** writes `results/latest-all.json` from the parts, and `... combine --check` → `latest-all.json: up to date`; `tests/crucible/test_results_file.py` fails if the committed file is not exactly that merge. There is no single wrapper that also pays for the LLM arms, deliberately: an accidental rerun should not spend the owner's subscription |
| 6 | The View shows Explorer, Flow, Time Machine, Why, Inventory and Results against live data | **met** | Fresh stack, tenant `demo` (replay of the real run), View served by nginx on :15167: `docs/screenshots/01-explorer.png` (graph, 247 nodes), `02-flow.png` (83 `ToolCall` events, stream open), `03-time-machine.png`, `04-why.png` (decision → 3 facts, 2 agents, 4 steps, 3 sources, 29 paths), `05-inventory.png` (247 / 708 / 14 labels / 26 edge types), `06..10-results-*.png` (the real combined file: L1, L2, L4, ablation, honesty), `11..13-results-l2-scale*.png` (L2 at scale, from the live API serving `latest-all.json`) |
| 7 | `docs/queries.md` lists every query; `docs/graph-model.md` matches the schema files | **met** | `tests/test_docs_consistency.py`: every one of the 69 named queries (`plexus/queries/**`) has a row in `docs/queries.md` (and the file lists none that does not exist); every label and property indexed in `schema/indexes.cypher` appears in `docs/graph-model.md`. Plan shape of `view/subgraph` after the new `created_at` indexes: `tests/api/test_subgraph_plan.py` |
| 8 | The owner's manual test checklist is handed over | **met** | §3 below |

### View API, every endpoint, fresh stack, tenant `demo` (`python scratch/curl_all.py http://127.0.0.1:18067 demo`)

```text
200  GET /healthz
200  GET /healthz?deep=1
200  GET /api/tenants                                   tenants: demo
200  GET /api/demo/inventory                            247 nodes, 708 edges, 14 labels, 26 edge types
200  GET /api/demo/graph?limit=2000                     247 nodes, 708 edges, truncated=False
200  GET /api/demo/graph?labels=Decision,Fact&limit=100 10 nodes (['Decision', 'Fact']), 9 edges
200  GET /api/demo/graph?since=<median created_at>      124 nodes
200  GET /api/demo/flow?limit=200                       83 events
200  GET /api/demo/step/15                              agents: ['planner', 'researcher']
200  GET /api/demo/step/25                              agents: ['builder', 'planner', 'researcher']
200  GET /api/demo/why/<decision id>                    kind=Decision facts=3 nodes=17 edges=27
200  GET /api/demo/recall/<recall id>                   results=5 nodes=17
200  GET /api/demo/stream                               SSE (first frame read)
200  GET /api/queries/view/subgraph                     query text
200  GET /api/results                                   layers L1, L4, ablation, L2 (L2_scale added later, see §2)
404  GET /api/nosuchtenant/inventory                    unknown tenant
404  GET /api/queries/..%2f..%2fpyproject               path traversal refused
5xx: 0
```

### What changed in this integration pass (P5-int)

| Change | Where | Check |
|---|---|---|
| One combined results file with L1 + L4 + ablation + L2 + L2-scale; the Results page pinned to its real shape (the first version of the parser read nothing from L2 and keyed the tenant sweep on the wrong axis) | `crucible/results/latest-all.json`, `crucible/combine.py`, `plexus-view/src/lib/results.ts`, `plexus-view/src/views/Results.tsx` | `plexus-view/src/views/Results.real.test.tsx` loads a byte copy of the real file; `tests/crucible/test_results_file.py` |
| `created_at` range index on all 16 labels; `view/subgraph` = 16 index range seeks instead of an All Node Scan | `queries/schema/indexes.cypher`, `queries/view/subgraph.cypher` | `tests/api/test_subgraph_plan.py` (fails on the old query: 5 of 16 tests). Measured on 4,209 nodes: label filter 5.6 → 3.2 ms, label + window 3.0 → 1.5 ms, window 2.7 → 2.8 ms, **no filter 3.8 → 5.8 ms (slower)**; the gain is in records read (a window of 5% reads 5%, not 100%), not in the unfiltered default view |
| `plexus demo ablation` | `plexus/src/plexus/demo/ablation.py`, `queries/demo/` | `tests/demo/test_ablation.py` (original tenant untouched, 6 of 6 break, 2 of 2 controls survive) |
| `plexus mcp-config`; `plexus.mcp.json` is a portable template | `cli.py`, `demo/orchestrator.py` | `tests/demo/test_mcp_config.py` |
| Compose: the View (nginx), `plexus-cli` one-off, results mount, per-stack image tags, no fixed `container_name` | `docker-compose.yml`, `plexus-view/Dockerfile` | the fresh-clone run above |

## 2. Benchmark results on the Results page

The page reads `GET /api/results` = `plexus/src/plexus/crucible/results/latest-all.json`: **L1** (correctness under concurrency),
**L2** (43 provenance questions, one scenario), **L2 at scale** (`layers["L2_scale"]`: 20 sprints of history, 10.4-16.6× the 32k context
cap, 36 questions), **L4** (latency and throughput) and the **ablation**. What each number does and does not show is in
`docs/BASELINE.md`; the page prints the run's own notes and honesty text verbatim. What to expect:

| Layer | Result in the file | Read it as |
|---|---|---|
| L1 | 0 violations for every arm, C1-C8 (B0, B1, B2 and P all pass) | the baselines are configured competently: Plexus is **not** claimed to win here |
| L2 (43 q) | P 43/43, B0 43/43, B1 43/43, B2 40/43 (93.0%); whole-reply-JSON: B0 36, B1 38, B2 39, P 43 | at this size B0/B1 fit in the context: a **tie** on accuracy; Plexus costs no tokens ($0 vs $0.05-0.06 per question) and ~2.5 ms vs ~5 s |
| **L2 at scale (36 q)** | **P 36/36, B1 32/36 (88.9%), B0 30/36 (83.3%), B2 23/36 (63.9%)**; Wilson 95%: P 90.4-100, B1 74.7-95.6, B0 68.1-92.1, B2 47.6-77.5 | a gap, but small: P's interval overlaps B0's and B1's. The page computes the **paired sign test** from the per-question rows: P vs B0 6-0, p = 0.031 (suggestive); P vs B1 4-0, **p = 0.125 (not distinguishable from noise)**; P vs B2 13-0, p < 0.001. 36 questions, one run each, one model, synthetic data; every question names one sprint (favours retrieval); Plexus uses hand-written Cypher per question family (favours Plexus). Cost: B0/B1 ≈ 20-22k tokens and $0.08-0.09 per question |
| L4 | **SQLite (B1) is faster than Plexus on the median claim at every load level** (0.10 ms vs 1.75 ms at 1 worker; 0.82 ms vs 570.9 ms at 200). Its tail is worse at 200 workers: p99 2.18 s vs 1.86 s, and the page shows both. Plexus's server-side time stays at 1-4 ms | Plexus's case is not raw claim speed: it is provenance, dependency traversal and time travel, with claims that stay exclusive under 200 workers |
| Ablation | 7 of 7 edge-dependent capabilities break without `DEPENDS_ON`/`BASED_ON`/`DERIVED_FROM`/`READ`; 5 of 5 controls unaffected; C4 gets 181 started-before-dependency violations, C8 60 derived facts still returned | the graph does real work (R2) |

Regenerating `latest-all.json` after a new run: `cd plexus && uv run python -m plexus.crucible.combine` (then
`cp src/plexus/crucible/results/latest-all.json ../plexus-view/src/fixtures/results.real.json`).

## 3. Owner's manual test checklist

Setup once (any machine with Docker): follow the README Setup. The commands below use the **default** ports
(View 5180, API 8080, MCP 8765, FalkorDB 6379, Browser 3000). If you start a second stack next to another one, give it its own project
and ports (`docker compose -p other ...`, see the header of `docker-compose.yml`) and replace the ports in the URLs.
"Expected" is what the same step produced in the fresh-clone run.

| # | Do | Expected |
|---|---|---|
| 1 | `cp .env.example .env && docker compose up -d --wait --build`, then open http://localhost:5180 and http://localhost:3000 | 4 services `healthy` (≈ 4 min the first time). The View header says `Tenant: unavailable` or an empty tenant list until step 2; the FalkorDB Browser opens |
| 2 | `docker compose run --rm plexus-cli demo replay acme-claude-sonnet --tenant demo`, reload the View, pick tenant `demo`. **Inventory**: counts; **Explorer**: graph | `replayed 'acme-claude-sonnet' into tenant 'demo': 247 nodes, 708 edges (matches meta.json: True)`. Inventory: 247 nodes, 708 edges, 14 labels, 26 edge types (Agent 3, Decision 4, Handoff 4, Task 12, Fact 6, Source 6, Step 83, ToolCall 83, ...). Explorer shows the graph (51 of 247 nodes by default: Step, ToolCall, Session, Recall are hidden; tick them in the left panel) |
| 3 | Open **Flow**, then in another terminal `docker compose run --rm plexus-cli demo live --scripted --tenant live --speed 4`; switch the View's tenant to `live`. Click an event | Flow shows `stream: open` and `ToolCall`s arriving (67 in this run: `claim_next_task`, `assert_fact`, `record_decision`, ...). Clicking one shows the Cypher it ran and a mini-graph of the nodes it created. The terminal prints the fault events: `kill_builder @15`, `reclaim` by the researcher, `publish_v2 @20`, `version_superseded @22`, `auth_contradiction @42` |
| 4 | Kill an agent mid-run: the scripted run does it for you at step 15 (`--kill-at N` moves it). For a real kill use `plexus demo live --claude` (spends your Claude subscription; optional) | The builder's task `t03-design-endpoints` is reclaimed after its lease expires: Flow shows `claim_next_task` by `researcher` right after the gap; in the Explorer the `CLAIMED` edge carries `reclaimed_from = builder`. Query: `MATCH (a:Agent)-[c:CLAIMED]->(t:Task) WHERE c.reclaimed_from <> '' RETURN a.id, t.id` in the FalkorDB Browser (graph `plexus_t_live`) → `researcher, t03-design-endpoints` |
| 5 | **Time Machine** on `demo`: step 17, then step 38, agent `builder` | At step 17 the builder had read `api_version = v1` (shown as superseded today); at step 38 it has read `api_version = v2` (valid). In the scripted run `live` the same switch is between step 15 (v1) and step 29 (v2) |
| 6 | **Why**: choose the decision `Adopt API v2 ...` | A left-to-right graph: the decision → the v2 fact (`BASED_ON`) → the agent that asserted it (researcher) → its step → the source document `06_api_style_guide_v2.md`, with `SUPERSEDES` to the v1 fact. The newest decision (`/why/latest`: `Approve the CRUD spec on API v2 ...`) shows 3 facts, 2 agents, 4 steps, 3 sources |
| 7 | Tenant isolation: switch the tenant selector between `demo` and `live`; then `curl http://localhost:8080/api/live/why/<a demo decision id>` (take one from `/api/demo/graph?labels=Decision`) | Each tenant shows only its own nodes. The `curl` returns `404 {"detail":"no node with id '...'"}` for another tenant's id, and `404 unknown tenant` for a tenant that does not exist |
| 8 | **Results** page (no run needed: the combined file is served) | See §2: L1 all pass; the L2 table with tokens, cost, latency and the whole-reply-JSON column; the **L2 at scale** section (P 36/36, B1 32, B0 30, B2 23, Wilson intervals, sign test p = 0.031 / 0.125 / < 0.001, honesty text); L4 with "Fastest median claim per worker count" naming B1; the ablation table with 7 rows marked broken. To regenerate L1/L4: `docker compose --profile bench run --rm crucible all --quick` (≈ 2 min; writes `plexus/src/plexus/crucible/results/<timestamp>/`), then `combine` as in §2 |
| 9 | Connect your own Claude Code: `claude mcp add --transport http plexus http://127.0.0.1:8765/mcp/t/demo`, or generate a stdio config for this checkout: `cd plexus && uv sync && FALKORDB_PORT=6379 uv run plexus mcp-config --tenant demo --out ../mcp.local.json`, then `claude --mcp-config mcp.local.json`. Ask: "Use the plexus tools: recall the API version, then explain why we chose v2" | The agent calls `start_session`, `recall` (value `v2`), and `why` on the v2 decision. Remember `claude -p` needs `--allowedTools "mcp__plexus__*"`; check `permission_denials` in the stream |
| 10 | Ablation: `docker compose run --rm plexus-cli demo ablation --tenant demo` | A table: `why(decision)`, `knew_at`, `who_knew`, `dependency-aware claim`, `blocked_by_failure`, `forget by source` are `works` on `demo` and `BROKEN` on `demo_ablated`; the two controls (`exclusive claims`, `supersession history`) `works` on both; `6 of 6 edge-dependent features break; 2 of 2 controls are unaffected`; `tenant 'demo' was not modified: verified`. Exit code 0. Open tenant `demo_ablated` in the View to see the graph without the four edge types (`--drop` removes it) |
| 11 | Cleanup: `docker compose down -v` | containers, network and volumes (`plexus_data`, `plexus_fastembed`) removed |

### If a step does not match

- **`exec: "plexus": executable file not found`** (or old behaviour from the API/MCP): an older `plexus:dev` image was reused. Run `docker compose build plexus-api && docker compose up -d --wait --force-recreate` (or always start with `up -d --wait --build`).
- **`Bad Request: Missing session ID` at `:8765/mcp/t/<tenant>` in a browser**: normal. That URL is an MCP endpoint, not a page; connect an MCP client (owner step 9).
- **Tenant list empty / "unavailable"**: the replay has not run yet, or the View was built for another API port (change `PLEXUS_API_PORT` → `docker compose up -d --build`).
- **Ports in use**: set the five ports in `.env`; on the dev machine 6379 and 3000 belong to `falkordb-dev`.
- **A first `docker compose run` after `up` recreates containers**: it happens when a variable such as `PLEXUS_API_PORT` is set in your shell with another value than `.env` (the shell wins). `env | grep -E "PLEXUS|FALKORDB"`.
- **Python tests**: `bash scripts/agent_db.sh <slot>` starts a private FalkorDB; pass `PLEXUS_TEST_DB_PORT=63<slot>` inline.

## 4. Known gaps (honest list)

- DoRT 3: 30 of the 41 tools were never called by a real `claude -p`; they are covered by the in-memory MCP contract tests only.
- DoRT 5: L1/L4 and L2 need separate commands (above); L2 needs the owner's Claude subscription for a cold run.
- The unfiltered Explorer query (`view/subgraph` without a label or window) is a little slower after the index change (3.8 → 5.8 ms at 4.2k nodes); filtered and windowed reads are faster.
- L4 was measured once on Docker Desktop; absolute numbers swing about 2× between runs (`docs/BASELINE.md`).
- `latest-all.json` mixes runs from different moments (L1/L4 from the first compose run, L2 and L2-scale from later runs); `run.reruns` and the layers' own `run` data say which.
- The Render deployment (P6) is not part of this pass.
