# plexus-view

Read-only web demonstrator for Plexus: shows what is stored in FalkorDB, how it flows in, and what the demo created.
Vite + React + TypeScript, Cytoscape.js (+ `cytoscape-fcose`) for the graph. It talks to the Plexus View API only and never writes.

| Page         | What it shows                                                                                                                                        |
| ------------ | ---------------------------------------------------------------------------------------------------------------------------------------------------- |
| `/` Explorer | graph, legend, label/edge filters, search, side panel; colour by module, created-at time range, 2-hop focus, "Why?" action, ablation view, live adds |
| `/flow`      | live `ToolCall` timeline (backfill + SSE), replay with play/pause/speed; click an event for the Cypher that ran and a mini-graph of what it touched  |
| `/time`      | Time Machine: per-agent step slider, what each agent knew and wrote, diff highlighting between steps                                                 |
| `/why/:id`   | provenance of a Decision or Fact as a left-to-right layered graph (`/why/latest` = newest decision), path highlight                                  |
| `/inventory` | "what the demo created" summary cards, counts per label and edge type, sample nodes, index list                                                      |
| `/results`   | Crucible results from `/api/results`: L1 table, L2 accuracy bars, L4 latency percentiles, ablation; placeholder until a results file exists          |

## Run

```bash
cd plexus-view
npm ci
VITE_FIXTURES=1 npm run dev        # fixture mode, http://localhost:5180
npm run dev                        # live mode: View API at VITE_PLEXUS_API (default http://localhost:8080)
```

PowerShell: `$env:VITE_FIXTURES=1; npm run dev`.

**The dev and preview servers use port 5180 with `strictPort`** (5171-5173 are taken on the dev machine).
The View API must allow CORS for `http://localhost:5180`.

| Variable          | Meaning                                                                                           |
| ----------------- | ------------------------------------------------------------------------------------------------- |
| `VITE_PLEXUS_API` | View API base URL. Default `http://localhost:8080`.                                               |
| `VITE_FIXTURES`   | `1` serves the built-in "Acme Notes API" dataset from `src/fixtures/` instead of calling the API. |

## Gate

```bash
npm ci && npm run lint && npm run typecheck && npm test -- --run && npm run build
```

`npm run lint` is ESLint + `prettier --check`; `npm run format` fixes formatting.

## Layout

```
src/
  api/        types.ts (mirrors plexus/src/plexus/api/models.py), client.ts (HTTP client), sse.ts (SSE + reconnect), index.ts (createApi)
  fixtures/   acme.ts (scripted Acme Notes scenario), client.ts (fixture ViewApi), queries.ts (real .cypher text), results.ts (test-only results sample)
  lib/        graphController.ts (imperative Cytoscape wrapper), labels.ts, flow.ts, useFlowFeed.ts, eventGraph.ts, timeMachine.ts,
              whyLayout.ts, summary.ts, ablation.ts, results.ts, cypher.ts (highlighter), theme.ts, useAsync.ts
  app/        providers (API + tenant context), Layout (header, nav, tenant selector, theme)
  components/ GraphCanvas, MiniGraph, WhyGraph (SVG), CypherView, AblationPanel, FilterPanel, NodePanel
  views/      Explorer, Flow, TimeMachine, Why, Inventory, Results
scripts/
  seed_live.py   seed a tenant through the real MCP tools (in-process) for a live smoke test
docs/screenshots/   PNGs captured from the browser against the live View API
```

### Graph rendering (docs/spikes/S3-view-lib.md)

- Cytoscape.js behind a thin imperative wrapper (`lib/graphController.ts`), **not** `react-cytoscapejs`. Graph elements live in
  Cytoscape; React state holds selection, filters and counts only.
- fcose runs **once**, with `quality: 'draft'`, on the nodes and edges that are visible at load. Hidden-by-default nodes are parked next to a neighbour.
- Live nodes (`addLive`) are seeded next to an already-placed neighbour with no relayout, so nothing moves. Edges whose endpoint hasn't arrived yet are parked and added when it does.
- Label and edge-type filters toggle a CSS class (`display: none`); they never remove elements, so toggling is instant and positions are kept.
- Hidden by default in the Explorer: labels `ToolCall`, `Step`, `Recall`, `Session`; edges `IN_SCOPE`, `ASSERTED_BY`, `BY`, `WROTE`, `READ`. Toggle them in the left panel.

### Live updates

In live mode the Explorer and the Flow page open `GET /api/{t}/stream` (SSE). The API names its frames `event: toolcall`, which
`EventSource.onmessage` never sees, so `connectFlowStream` listens for the named event. It reconnects with exponential backoff, resumes with
`?after=<newest at>`, and de-duplicates by event id (a call that lands late with an older `at` is still delivered once).
The Flow page backfills from `GET /api/{t}/flow` (paged by `last_at`) before connecting.

For each event the Explorer **re-reads the bounded subgraph** (`GET /api/{t}/graph?limit=2000`, coalesced) and lets `addLive` add only what is new,
and `updateProps` refresh nodes the call updated. It does not use `graph?since=&until=`: those filter on `created_at` and the API returns only edges
whose _both_ ends are inside the window, so a new node's edges to older nodes would be lost. (The fixture replay passes `until` so nodes appear one event
at a time.) In fixture mode there is no stream; **Replay last events as live** feeds the last 24 events through the same code path.

### API contract

All types in `src/api/types.ts` mirror `plexus/src/plexus/api/models.py` (also exported to `docs/view-api.schema.json`): `{tenants:[{tenant, graph}]}`,
`GraphEdge = {source, target, type}` (no edge id, so the client keys edges `source|type|target`), `ToolCallEvent` with `step_id`/`step_n`/`created`/`updated`,
`StepResponse.agents[].read/wrote`, `WhyResponse.result.{root, kind, facts, agents, sources, episodes, steps, paths, nodes, edges}`, `QueryText`.
The fixture client returns the same shapes. Step numbers are **per agent** (each agent has its own `Step` chain), so the Time Machine slider value `n` means
"each agent's latest step <= n".

### Results page

`GET /api/results` is read defensively (`lib/results.ts`): it follows the schema documented in `plexus/src/plexus/crucible/results.py`
(`layers.L1`, `layers.L4.{claim,recall,tenant}_sweep`, `layers.ablation`) and accepts L2 (`layers.L2`, accuracy per arm as `{arms:{B0:{accuracy}}}`,
`{B0:{...}}` or `[{arm, accuracy}]`, ratios or percentages) because that layer's shape was not yet fixed. A 404 shows the "no results yet" placeholder;
nothing is estimated. `src/fixtures/results.ts` is a made-up sample used only by tests.

### Ablation view

A presentation-only switch in the Explorer: it hides `DEPENDS_ON`, `BASED_ON`, `DERIVED_FROM` and `READ` edges and lists which tools stop working without them
(`lib/ablation.ts`), linking to `/results#ablation` for the measured result. It never changes data.

### Live smoke test

```bash
docker run -d --name plexus-db-87 -p 127.0.0.1:6387:6379 falkordb/falkordb:6.0.2
FALKORDB_PORT=6387 PLEXUS_API_PORT=18087 plexus/.venv/Scripts/plexus-api.exe &
FALKORDB_PORT=6387 plexus/.venv/Scripts/python.exe plexus-view/scripts/seed_live.py live      # small seed through the MCP tools
# or the scripted demo: FALKORDB_PORT=6387 plexus demo live --scripted --tenant demo --speed 1 --embedder hash
VITE_PLEXUS_API=http://localhost:18087 npm run dev                                              # http://localhost:5180
```

## Fixture data: "Acme Notes API"

`src/fixtures/acme.ts` is a hand-written script of 30 steps in which a planner, a researcher and a builder build a notes service. A small expander turns it
into graph model v1 nodes, edges and `ToolCall` flow events (deterministic ids, synthetic data only). Tenants: `acme` (full dataset) and `scratch` (empty). Agent ids are their names, as in the real tools, and each agent's steps are numbered 1..k.

It contains: 3 agents, 12 tasks with a dependency DAG (done / claimed / failed / open), 43 facts, 6 decisions with `BASED_ON`, 5 handoffs, 6 artifacts,
5 sources, 4 sessions and 6 episodes, 8 recalls with `RETURNED`, 30 steps and 99 `ToolCall`s. Story beats:

- step 14-17: the builder claims T7 and goes silent; the lease expires and it re-claims (two `CLAIMED` edges);
- step 20: `api_version = v1` is superseded by `v2` (`SUPERSEDES`, `valid_to` closed);
- step 21: the builder asserts `auth = API key`, which `CONTRADICTS` the researcher's `auth = JWT`; the planner resolves it with a decision;
- step 26: T9 (rate limiting) fails and the planner hands it back with a fallback.

`GET /api/queries/{name}` in fixture mode returns the real `.cypher` text (with its header parsed into `mode`/`purpose`/`params`/`returns`) from the files from `plexus/queries/{engram,relay}` (snapshot in `queries.ts`).
