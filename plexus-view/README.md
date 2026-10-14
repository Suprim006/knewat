# plexus-view

Read-only web demonstrator for Plexus: shows what is stored in FalkorDB, how it flows in, and what the demo created.
Vite + React + TypeScript, Cytoscape.js (+ `cytoscape-fcose`) for the graph. It talks to the Plexus View API only and never writes.

| Page         | State                                                                            |
| ------------ | -------------------------------------------------------------------------------- |
| `/` Explorer | done: graph, legend, label/edge filters, search, node side panel, live additions |
| `/inventory` | done: counts per label and edge type, sample nodes, index list                   |
| `/flow`      | placeholder (P3)                                                                 |
| `/time`      | placeholder (P3)                                                                 |
| `/why/:id`   | placeholder (P3). `GraphController.highlightPath()` is ready for it              |
| `/results`   | placeholder (P4)                                                                 |

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
  api/        types.ts (View API + graph model v1 types), client.ts (HTTP client), sse.ts (SSE + reconnect), index.ts (createApi)
  fixtures/   acme.ts (the scripted Acme Notes API scenario), client.ts (fixture ViewApi), queries.ts (real .cypher text)
  lib/        graphController.ts (imperative Cytoscape wrapper), labels.ts (colours, names), theme.ts, useAsync.ts
  app/        providers (API + tenant context), Layout (header, nav, tenant selector, theme)
  components/ GraphCanvas, FilterPanel, NodePanel
  views/      Explorer, Inventory, Placeholder
```

### Graph rendering (docs/spikes/S3-view-lib.md)

- Cytoscape.js behind a thin imperative wrapper (`lib/graphController.ts`), **not** `react-cytoscapejs`. Graph elements live in
  Cytoscape; React state holds selection, filters and counts only.
- fcose runs **once**, with `quality: 'draft'`, on the nodes and edges that are visible at load. Hidden-by-default nodes are parked next to a neighbour.
- Live nodes (`addLive`) are seeded next to an already-placed neighbour with no relayout, so nothing moves. Edges whose endpoint hasn't arrived yet are parked and added when it does.
- Label and edge-type filters toggle a CSS class (`display: none`); they never remove elements, so toggling is instant and positions are kept.
- Hidden by default in the Explorer: labels `ToolCall`, `Step`, `Recall`, `Session`; edges `IN_SCOPE`, `ASSERTED_BY`, `BY`, `WROTE`, `READ`. Toggle them in the left panel.

### Live updates

In live mode the Explorer opens `GET /api/{t}/stream` (SSE, with exponential-backoff reconnection and `?after=<last event time>` resume).
For each `FlowEvent` it calls `GET /api/{t}/graph?since=<last seen at + 1>&until=<event.at>` and adds the returned nodes and edges.
This assumes new nodes carry `created_at` equal to their `ToolCall.at`, and that `since`/`until` filter on `created_at`.
In fixture mode there is no stream; the **Replay last events as live** button removes the last 24 events' nodes and feeds them through the same code path.

### Assumptions about the View API

PLAN §4 pins the node/edge shapes (`Subgraph`) and the `FlowEvent` fields. The envelopes around them are this app's reading and live
in `src/api/types.ts`: `{ tenants: [{id, graph}] }`, `{ events: FlowEvent[] }`, `Inventory`, `KnewAt`, `WhyPath`, `QueryText`.
If the API returns something different, change `types.ts` and `client.ts` only.

## Fixture data: "Acme Notes API"

`src/fixtures/acme.ts` is a hand-written script of 30 steps in which a planner, a researcher and a builder build a notes service. A small expander turns it
into graph model v1 nodes, edges and `ToolCall` flow events (deterministic ids, synthetic data only). Tenants: `acme` (full dataset) and `scratch` (empty).

It contains: 3 agents, 12 tasks with a dependency DAG (done / claimed / failed / open), 43 facts, 6 decisions with `BASED_ON`, 5 handoffs, 6 artifacts,
5 sources, 4 sessions and 6 episodes, 8 recalls with `RETURNED`, 30 steps and 99 `ToolCall`s. Story beats:

- step 14-17: the builder claims T7 and goes silent; the lease expires and it re-claims (two `CLAIMED` edges);
- step 20: `api_version = v1` is superseded by `v2` (`SUPERSEDES`, `valid_to` closed);
- step 21: the builder asserts `auth = API key`, which `CONTRADICTS` the researcher's `auth = JWT`; the planner resolves it with a decision;
- step 26: T9 (rate limiting) fails and the planner hands it back with a fallback.

`GET /api/queries/{name}` in fixture mode returns the real `.cypher` files from `plexus/queries/{engram,relay}` (snapshot in `queries.ts`).
