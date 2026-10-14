# Spike S3: graph library for `plexus-view`

**Recommendation: Cytoscape.js 3.34 + `cytoscape-fcose` (quality `draft`), with a thin own wrapper.**
Fallback: `react-force-graph-2d`. Not recommended as the primary: `@falkordb/canvas`.

Spike code (throwaway): `C:/Users/ACER/AppData/Local/hermes/cache/scratch/plexus-s3/`.

## 1. Setup

- Vite 8 + React 19 + TypeScript 7 (`tsc` clean for all three entries).
- Synthetic graph: 2,000 nodes, 4,000 edges, 6 labels (colour per label), seeded RNG, connected, with hub nodes.
- Then 50 new nodes (about 73 edges) added in 5 batches of 10, simulating SSE events.
- A BFS-found 5-node path is highlighted, and a node click handler is attached.
- Chrome via CDP on this Windows laptop. Timings are noisy (the same Cytoscape layout took 330–1,700 ms across runs). Treat them as orders of magnitude.

## 2. Comparison

| | **(a) Cytoscape.js + fcose** | **(b) `@falkordb/canvas`** | **(c) `react-force-graph-2d`** |
|---|---|---|---|
| Version / released | cytoscape 3.34.3 (2026-09-07); fcose 2.2.0 (2023-01, stable, rarely changes); react-cytoscapejs 2.0.0 (2022-09, unmaintained but works on React 19) | 0.3.3 (2026-10-12). **0.x with churn:** 0.2.7 → 0.3.3 in 2 months, 6 releases | 1.29.2 (2026-09-29), on `force-graph` 1.52 |
| License | MIT | MIT | MIT |
| Bundle delta over bare React (raw / gzip) | **+562 kB / +170 kB** (cytoscape + fcose) | **+230 kB / +74 kB** for the 2D entry. A lazy 3D chunk (1.3 MB, three.js) exists, but is not fetched for 2D (checked in the server log) | **+186 kB / +60 kB** |
| Total built JS (raw / gzip) | 782 kB / 237 kB (react-cytoscapejs wrapper: 784 kB / 238 kB) | 449 kB / 141 kB (+ unused lazy 3D chunk) | 406 kB / 128 kB |
| Initial layout (2k/4k) | fcose `draft`: **0.3–1.7 s** on the main thread. `default` quality: **26 s** (measured in Node), `proof`: 182 s. Use `draft`. | Synchronous 300-tick warmup: a **single 8.1–8.7 s main-thread block**. `setData()` itself returns in about 20 ms and the block happens afterwards. The page is frozen meanwhile. | No block (max long task 74 ms). Animated, the engine stops after the default 15 s cooldown (15.3 s). Nodes are visible immediately. |
| Incremental add of 50 nodes | `cy.add` of 50 nodes: **6.7 ms**. Seeding new nodes next to a neighbour: 4.8 ms. **0 of the 2,000 existing nodes moved** (>25 px). No relayout needed, so it is fully stable. | `setGraphData()` (the incremental API) keeps positions but **re-runs the full warmup**: 0.85 s (30 ticks) to **9 s** (300 ticks, default) block per batch. Drift: 27% of layout radius at 300 ticks, 17% at 30 ticks. `setData()` is a full replacement. | `graphData` swap: 0.3 ms, but it **reheats the simulation**. Mean shift was 155 on a layout radius of 542 (29%), with all nodes drifting. Needs `fx/fy` pinning of existing nodes to be stable. |
| Layout stays stable? | **Yes** (manual placement). A fcose re-run is not incremental. `draft` + `randomize:false` **throws** (`nodeIndexes` of undefined, `relocateComponent`). `draft` + `randomize:true` reshuffles 98% of nodes. `default` + `fixedNodeConstraint` is stable but takes 6.9 s. | Partly. Same overall shape, but about 12–27% drift per batch and a blocking warmup. | No by default (reheat). Fixable with pinning. |
| Path-highlight API | Classes plus selectors: `cy.elements().addClass('faded')`, `getElementById(id).edgesWith(...)`, `addClass('path')`. Style rules are declarative. The naive filter-based version took 48 ms; the snippet below uses `edgesWith` instead. | Callbacks: `setConfig({isNodeSelected, isLinkSelected})` plus `refresh()`: 2–3 ms. Verified: the selected node is drawn with a thick border. Fixed look, only overridable with custom canvas drawing. | Accessors (`linkColor`, `linkWidth`, `nodeCanvasObject`) plus `refresh()`: about 0 ms. Verified visually (thick black path). |
| Click handler | `cy.on('tap','node', e => ...)` ✔ (tested with a real click) | `eventHandlers.onNodeClick(node)` ✔ (tested) | `onNodeClick(node)` ✔ (tested) |
| Zoom/pan under load (2k nodes, wheel zoom, 2.5 s) | ~51 fps | ~56 fps | ~57 fps (all roughly vsync-limited) |
| TypeScript | cytoscape ships its own `index.d.ts` (do NOT add the deprecated `@types/cytoscape`). `@types/cytoscape-fcose` 2.2.5 is needed. `@types/react-cytoscapejs` 1.2.6. | Bundled types. **The `falkordb-canvas` JSX typing is a global `JSX` augmentation, which does not apply under React 19 types.** It needs a local `declare module 'react'` shim (1 file). Node ids must be numbers. | Bundled types (`ForceGraphMethods`). `any` creeps in via node/link accessors. |
| Fit for Plexus needs | Add and remove elements by id (time-machine step slider). Class/selector styling (why-path, ablation fade). Many layouts available (dagre for the Flow DAG). **Headless mode works in Node** (we ran layouts there), so the layout and highlight logic is unit-testable without a browser. Compound nodes. | Built-in tree/radial layouts, a `visible` flag for filtering, glow on nodes, link labels and arrows. Matches the FalkorDB Browser look. But: blocking warmup, 0.x API, and a relayout per live update. | Smallest and simplest, with smooth physics. Weak selection and styling model. Jitter on every update unless pinned. |

## 3. Why Cytoscape

1. **Live updates are the core requirement, and only Cytoscape gives a stable, instant, non-blocking incremental add.** 50 nodes added in about 7 ms with zero movement of existing nodes. Both force-based options reshuffle or block on each batch.
2. **Declarative style rules and selectors** map directly to Plexus UI features: path highlight, fading, per-label colour, ablation toggle (hide edge types), time-machine (add/remove by id). They are quick to build and quick to test.
3. **Stable and boring:** a 3.x API, MIT, still released (September 2026). The headless mode lets the P1 agent test layout and highlight code in vitest.
4. This matches the PLAN's default, so there is no replan.

### Costs and rules to follow

- **Always use `quality: 'draft'` for fcose.** `default` freezes the tab for 26 s at this size.
- **Never call fcose again for incremental updates.** Seed new nodes next to a neighbour, as in the snippet. If a relayout is needed (a user "re-layout" button), run `draft` with `randomize:true` (about 0.5–1.5 s) and `animate:true`, or accept a reshuffle.
- Edges use `curve-style: haystack` for speed (2k nodes / 4k edges drew at about 51 fps in the wheel-zoom test). Switch to `bezier` only for highlighted edges.
- Bundle is +170 kB gzip. Acceptable for a demo app. Lazy-load the Explorer view route if wanted.
- Beyond roughly 5k nodes, use a server-side cap (the View API already caps `limit`).
- Don't use the `react-cytoscapejs` wrapper for live updates: it diffs the whole `elements` array on every React render (76 ms for 2k elements) and unmaintained since 2022. Use the thin imperative wrapper below. React state is only for selection, not for graph elements.

### Why not `@falkordb/canvas` (primary)

- 8.5 s frozen tab on first layout. An incremental update re-runs the warmup (0.85–9 s, with 12–27% drift). That defeats live updates and would hurt the demo video.
- 0.x API changing weekly. JSX types are broken on React 19 (needs a shim). It pulls in `three` and `3d-force-graph` as dependencies.
- Pro: the same look as the FalkorDB Browser (shown anyway at :3000), and nice defaults (labels, arrows, glow).
- It could be viable if the warmup moved off the main thread or `setGraphData` did a local warmup. The code has a `runForceWarmup(freeNodeIds)` local-warmup path, but the public API doesn't use it.

### Fallback: `react-force-graph-2d`

Use it only if Cytoscape disappoints. It is the smallest and non-blocking, but needs pinning (`fx/fy`) of existing nodes and a lower `d3AlphaDecay`/`cooldownTime` to avoid jitter.

## 4. Minimal code (typechecked with TS 7 / React 19 / cytoscape 3.34)

```bash
npm i cytoscape cytoscape-fcose
npm i -D @types/cytoscape-fcose   # cytoscape ships its own types
```

```tsx
import { useEffect, useRef } from 'react';
import cytoscape, { type Core, type ElementDefinition } from 'cytoscape';
import fcose from 'cytoscape-fcose';

cytoscape.use(fcose); // register once, at module scope

const LABEL_COLORS: Record<string, string> = {
  Agent: '#e6194b', Session: '#3cb44b', Episode: '#4363d8',
  Fact: '#f58231', Entity: '#911eb4', Task: '#42d4f4',
};

export interface GraphNode { id: string; label: string; props?: Record<string, unknown> }
export interface GraphEdge { id: string; source: string; target: string; type: string }

/** Imperative handle the views use; keep it outside React state so SSE events never re-render. */
export interface GraphHandle {
  addElements(nodes: GraphNode[], edges: GraphEdge[]): void;
  highlightPath(nodeIds: string[]): void;
  clearHighlight(): void;
}

export function createGraph(container: HTMLElement, onNodeClick: (id: string) => void): Core & { api: GraphHandle } {
  const cy = cytoscape({
    container,
    minZoom: 0.05, maxZoom: 4,
    style: [
      { selector: 'node', style: { width: 8, height: 8, 'background-color': '#999' } },
      ...Object.entries(LABEL_COLORS).map(([l, c]) => ({
        selector: `node[label = "${l}"]`, style: { 'background-color': c },
      })),
      { selector: 'edge', style: { width: 0.6, 'line-color': '#ccc', 'curve-style': 'haystack' as const } },
      { selector: '.faded', style: { opacity: 0.12 } },
      { selector: 'node.path', style: { width: 18, height: 18, 'border-width': 3, 'border-color': '#000' } },
      { selector: 'edge.path', style: { width: 4, 'line-color': '#000', 'curve-style': 'bezier' as const, 'z-index': 99 } },
    ],
  });

  cy.on('tap', 'node', (e) => onNodeClick(e.target.id()));

  const api: GraphHandle = {
    addElements(nodes, edges) {
      const fresh = nodes.filter((n) => cy.getElementById(n.id).empty());
      const defs: ElementDefinition[] = [
        ...fresh.map((n) => ({ group: 'nodes' as const, data: { id: n.id, label: n.label, ...n.props } })),
        ...edges.filter((e) => cy.getElementById(e.id).empty())
          .map((e) => ({ group: 'edges' as const, data: { ...e } })),
      ];
      cy.batch(() => {
        const added = cy.add(defs);
        // No relayout: seed each new node next to an existing neighbour so the map stays stable.
        added.nodes().forEach((n) => {
          const nb = n.neighborhood('node').filter((m) => !added.contains(m)).first() as cytoscape.NodeSingular;
          const p = nb.empty() ? { x: 0, y: 0 } : nb.position();
          n.position({ x: p.x + (Math.random() - 0.5) * 30, y: p.y + (Math.random() - 0.5) * 30 });
        });
      });
    },
    highlightPath(ids) {
      cy.batch(() => {
        cy.elements().removeClass('path').addClass('faded');
        const nodes = cy.nodes().filter((n) => ids.includes(n.id()));
        let path = nodes;
        for (let i = 0; i < ids.length - 1; i++) {
          path = path.union(cy.getElementById(ids[i]).edgesWith(cy.getElementById(ids[i + 1])));
        }
        path.removeClass('faded').addClass('path');
      });
    },
    clearHighlight() {
      cy.elements().removeClass('faded path');
    },
  };
  return Object.assign(cy, { api });
}

/** Initial load: one call, then run the (draft-quality!) layout once. */
export function loadInitial(cy: Core, nodes: GraphNode[], edges: GraphEdge[]) {
  cy.add([
    ...nodes.map((n) => ({ group: 'nodes' as const, data: { id: n.id, label: n.label } })),
    ...edges.map((e) => ({ group: 'edges' as const, data: { ...e } })),
  ]);
  cy.layout({ name: 'fcose', quality: 'draft', randomize: true, animate: false } as cytoscape.LayoutOptions).run();
  cy.fit(undefined, 20);
}

export function GraphView({ onNodeClick }: { onNodeClick: (id: string) => void }) {
  const ref = useRef<HTMLDivElement>(null);
  useEffect(() => {
    const cy = createGraph(ref.current!, onNodeClick);
    // wire SSE here: new EventSource(...).onmessage = (m) => cy.api.addElements(...)
    return () => cy.destroy();
  }, []); // eslint-disable-line react-hooks/exhaustive-deps
  return <div ref={ref} style={{ width: '100%', height: '100%' }} />;
}
```

## 5. Caveats and what the spike did not cover

- **Not tested:** `highlightPath` as written in the snippet (it uses `edgesWith`) was only typechecked. The spike measured a slower filter-based variant (48 ms) and confirmed that path highlighting works. Likewise `addElements` was not run as written. The measured version placed nodes next to a neighbour in 4.8 ms and nothing moved.
- Timings come from one noisy laptop, in a visible Chrome tab. Don't quote exact milliseconds in the blog post. The orders of magnitude (fcose `draft` ≈ 1 s versus `default` ≈ 26 s; canvas warmup ≈ 8 s) are solid.
- Frame-rate numbers come from a synthetic wheel-zoom loop and are vsync-limited, so they don't separate the libraries.
- Shift percentages compare mean node displacement with mean distance from the centroid, as measured per library.
- Not tested: `react-force-graph-2d` with pinning, and `@falkordb/canvas` with `largeGraph` options or `layoutMode: 'tree'`.
