import cytoscape from 'cytoscape';
import type { Core, ElementDefinition, NodeSingular, StylesheetJson } from 'cytoscape';
import fcose from 'cytoscape-fcose';
import type { GraphEdge, GraphNode, Props } from '../api/types';
import { displayName, labelColor, LABEL_COLORS } from './labels';

/*
 * Thin imperative wrapper around Cytoscape.js (docs/spikes/S3-view-lib.md).
 *
 * Rules from the spike, enforced here:
 *  - fcose runs once, with quality "draft" (default quality freezes the tab for ~26 s at 2k nodes);
 *  - live nodes are seeded next to a neighbour and never trigger a relayout (existing nodes don't move);
 *  - graph elements live in Cytoscape, not in React state; React only holds selection and filters.
 */

let registered = false;
function register() {
  if (registered) return;
  registered = true;
  cytoscape.use(fcose);
}

export interface Theme {
  text: string;
  textOutline: string;
  edge: string;
  edgeStrong: string;
  highlight: string;
}
export const LIGHT_THEME: Theme = {
  text: '#1f2933',
  textOutline: '#ffffff',
  edge: '#b7bfca',
  edgeStrong: '#5b6676',
  highlight: '#111827',
};
export const DARK_THEME: Theme = {
  text: '#e5e9f0',
  textOutline: '#14181f',
  edge: '#4a5465',
  edgeStrong: '#a7b1c2',
  highlight: '#f8fafc',
};

const NODE_SIZE: Record<string, number> = {
  Agent: 34,
  Entity: 22,
  Task: 22,
  Decision: 20,
  Handoff: 18,
  Artifact: 16,
  Scope: 20,
  Source: 18,
  Procedure: 18,
  Step: 11,
  ToolCall: 8,
  Recall: 12,
  Session: 14,
  Run: 14,
  Episode: 13,
  Fact: 14,
};

/** Above this many edges we switch to cheap haystack edges (no arrowheads). */
export const HAYSTACK_EDGE_THRESHOLD = 1500;

/** fcose options. Quality stays "draft" (spike S3): `default` takes ~26 s at 2k nodes. */
export const LAYOUT_OPTIONS = {
  name: 'fcose',
  quality: 'draft',
  randomize: true,
  nodeDimensionsIncludeLabels: false,
  idealEdgeLength: 110,
  nodeRepulsion: 14000,
  nodeSeparation: 110,
  edgeElasticity: 0.4,
  gravity: 0.15,
  packComponents: true,
} as const;

export function buildStyle(theme: Theme, haystack: boolean): StylesheetJson {
  return [
    {
      selector: 'node',
      style: {
        width: 'data(size)',
        height: 'data(size)',
        'background-color': '#999999',
        label: 'data(name)',
        color: theme.text,
        'font-size': 10,
        'text-valign': 'bottom',
        'text-margin-y': 3,
        'text-wrap': 'ellipsis',
        'text-max-width': '110px',
        'text-outline-color': theme.textOutline,
        'text-outline-width': 2,
        'min-zoomed-font-size': 9,
      },
    },
    // Anchors keep their label even when zoomed out; everything else labels on zoom-in.
    {
      selector:
        'node[label = "Agent"], node[label = "Task"], node[label = "Decision"], node[label = "Entity"]',
      style: { 'min-zoomed-font-size': 0, 'font-size': 11, 'font-weight': 600 },
    },
    ...Object.entries(LABEL_COLORS).map(([label, color]) => ({
      selector: `node[label = "${label}"]`,
      style: { 'background-color': color },
    })),
    {
      selector: 'edge',
      style: haystack
        ? { width: 0.7, 'line-color': theme.edge, 'curve-style': 'haystack' as const }
        : {
            width: 1,
            'line-color': theme.edge,
            'target-arrow-color': theme.edge,
            'target-arrow-shape': 'triangle' as const,
            'arrow-scale': 0.7,
            'curve-style': 'bezier' as const,
          },
    },
    { selector: '.hide-label, .hide-type', style: { display: 'none' as const } },
    { selector: 'node.dim, edge.dim', style: { opacity: 0.12 } },
    { selector: 'node.match', style: { 'border-width': 3, 'border-color': theme.highlight } },
    { selector: '.faded', style: { opacity: 0.1 } },
    {
      selector: 'node.nb',
      style: { opacity: 1 },
    },
    {
      selector: 'edge.nb',
      style: {
        opacity: 1,
        width: 2.2,
        'line-color': theme.edgeStrong,
        'target-arrow-color': theme.edgeStrong,
        'curve-style': 'bezier' as const,
        label: 'data(type)',
        'font-size': 8,
        color: theme.text,
        'text-rotation': 'autorotate' as const,
        'text-background-color': theme.textOutline,
        'text-background-opacity': 0.85,
        'text-background-padding': '1px',
      },
    },
    { selector: 'node.sel', style: { 'border-width': 4, 'border-color': theme.highlight, opacity: 1 } },
    {
      selector: 'node.fresh',
      style: { 'border-width': 5, 'border-color': '#22c55e', 'border-opacity': 0.9 },
    },
    { selector: 'node.path', style: { 'border-width': 4, 'border-color': theme.highlight, opacity: 1 } },
    {
      selector: 'edge.path',
      style: {
        width: 4,
        'line-color': theme.highlight,
        'target-arrow-color': theme.highlight,
        'curve-style': 'bezier' as const,
        opacity: 1,
        'z-index': 99,
      },
    },
  ] as StylesheetJson;
}

export interface NeighborInfo {
  direction: 'out' | 'in';
  type: string;
  id: string;
  label: string;
  name: string;
}
export interface NodeDescription {
  id: string;
  label: string;
  name: string;
  props: Props;
  neighbors: NeighborInfo[];
}
export interface Counts {
  visibleNodes: number;
  totalNodes: number;
  visibleEdges: number;
  totalEdges: number;
}
export interface FilterState {
  hiddenLabels: ReadonlySet<string>;
  hiddenEdgeTypes: ReadonlySet<string>;
}

export interface GraphController {
  readonly cy: Core;
  /** Replace all elements and run the one-off fcose layout (draft). */
  load(nodes: GraphNode[], edges: GraphEdge[]): void;
  clear(): void;
  /** Add nodes/edges without relayout; new nodes are seeded next to a neighbour. Returns the ids of nodes actually added. */
  addLive(nodes: GraphNode[], edges: GraphEdge[]): string[];
  /** Remove every node created at or after `ts` (used by the fixture "replay as live" demo). Returns the count. */
  removeCreatedSince(ts: number): number;
  setFilters(f: FilterState): void;
  setSearch(q: string): string[];
  select(id: string | null): void;
  focus(id: string): void;
  describe(id: string): NodeDescription | null;
  counts(): Counts;
  labelCounts(): Record<string, number>;
  edgeTypeCounts(): Record<string, number>;
  highlightPath(nodeIds: string[]): void;
  clearHighlight(): void;
  relayout(): void;
  fit(): void;
  setTheme(theme: Theme): void;
  destroy(): void;
}

export interface ControllerOptions {
  container?: HTMLElement | null;
  /** No rendering (tests / jsdom). */
  headless?: boolean;
  onSelect?: (id: string | null) => void;
  theme?: Theme;
}

const toNodeDef = (n: GraphNode): ElementDefinition => ({
  group: 'nodes',
  data: {
    id: n.id,
    label: n.label,
    name: displayName(n.label, n.props),
    size: NODE_SIZE[n.label] ?? 14,
    color: labelColor(n.label),
    props: n.props,
  },
});
const toEdgeDef = (e: GraphEdge): ElementDefinition => ({
  group: 'edges',
  data: { id: e.id, source: e.src, target: e.dst, type: e.type, props: e.props },
});

/**
 * Give each unplaced node a position next to an already-placed neighbour (several passes so chains of
 * new nodes work), falling back to the centre of the placed cluster. Never moves placed nodes.
 */
function seedNear(cy: Core, unplaced: NodeSingular[], placed: Set<string>): void {
  const todo = [...unplaced];
  for (let pass = 0; pass < 4 && todo.length > 0; pass++) {
    for (let i = todo.length - 1; i >= 0; i--) {
      const n = todo[i]!;
      const nb = n
        .neighborhood('node')
        .filter((m) => placed.has(m.id()))
        .first() as NodeSingular;
      if (nb.empty()) continue;
      const p = nb.position();
      n.position({ x: p.x + (Math.random() - 0.5) * 60, y: p.y + (Math.random() - 0.5) * 60 });
      placed.add(n.id());
      todo.splice(i, 1);
    }
  }
  if (todo.length === 0) return;
  const ext = cy.nodes().filter((n) => placed.has(n.id()));
  const box = ext.nonempty() ? ext.boundingBox() : { x1: 0, x2: 0, y1: 0, y2: 0 };
  for (const n of todo) {
    n.position({
      x: (box.x1 + box.x2) / 2 + (Math.random() - 0.5) * 120,
      y: (box.y1 + box.y2) / 2 + (Math.random() - 0.5) * 120,
    });
  }
}

export function createGraphController(opts: ControllerOptions = {}): GraphController {
  register();
  const headless = opts.headless ?? !opts.container;
  let theme = opts.theme ?? LIGHT_THEME;
  let haystack = false;
  let filters: FilterState = { hiddenLabels: new Set(), hiddenEdgeTypes: new Set() };
  let pending: GraphEdge[] = [];
  const timers = new Set<ReturnType<typeof setTimeout>>();

  const cy = cytoscape({
    container: headless ? undefined : opts.container,
    headless,
    styleEnabled: true,
    minZoom: 0.05,
    maxZoom: 4,
    wheelSensitivity: 0.25,
    style: buildStyle(theme, haystack),
  });

  cy.on('tap', 'node', (e) => opts.onSelect?.(e.target.id()));
  cy.on('tap', (e) => {
    if (e.target === cy) opts.onSelect?.(null);
  });

  const name = (n: NodeSingular): string => String(n.data('name'));

  function applyFilters(eles = cy.elements()) {
    cy.batch(() => {
      eles.nodes().forEach((n) => {
        n.toggleClass('hide-label', filters.hiddenLabels.has(String(n.data('label'))));
      });
      eles.edges().forEach((e) => {
        e.toggleClass('hide-type', filters.hiddenEdgeTypes.has(String(e.data('type'))));
      });
    });
  }

  function flushPending(): void {
    if (pending.length === 0) return;
    const ready: GraphEdge[] = [];
    const rest: GraphEdge[] = [];
    for (const e of pending) {
      if (!cy.getElementById(e.id).empty()) continue;
      if (cy.getElementById(e.src).nonempty() && cy.getElementById(e.dst).nonempty()) ready.push(e);
      else rest.push(e);
    }
    pending = rest;
    if (ready.length > 0) {
      const added = cy.add(ready.map(toEdgeDef));
      applyFilters(added);
    }
  }

  function updateEdgeMode(): void {
    const next = cy.edges().length > HAYSTACK_EDGE_THRESHOLD;
    if (next !== haystack) {
      haystack = next;
      cy.style(buildStyle(theme, haystack));
    }
  }

  const controller: GraphController = {
    cy,

    load(nodes, edges) {
      cy.elements().remove();
      pending = [];
      const known = new Set(nodes.map((n) => n.id));
      cy.batch(() => {
        cy.add(nodes.map(toNodeDef));
        cy.add(edges.filter((e) => known.has(e.src) && known.has(e.dst)).map(toEdgeDef));
      });
      updateEdgeMode();
      applyFilters();
      if (nodes.length > 0) {
        // Lay out what is visible (hidden-by-default labels/edge types would only add hairball), then
        // park the hidden nodes next to their neighbours so toggling them on moves nothing.
        const visible = cy.elements().not('.hide-label, .hide-type');
        if (visible.nodes().nonempty()) {
          visible.layout({ ...LAYOUT_OPTIONS, animate: false } as cytoscape.LayoutOptions).run();
        }
        const hidden = cy.nodes('.hide-label');
        seedNear(
          cy,
          hidden.toArray(),
          new Set(
            cy
              .nodes()
              .not('.hide-label')
              .map((n) => n.id()),
          ),
        );
        cy.fit(undefined, 30);
      }
    },

    clear() {
      cy.elements().remove();
      pending = [];
    },

    addLive(nodes, edges) {
      const fresh = nodes.filter((n) => cy.getElementById(n.id).empty());
      const freshIds = new Set(fresh.map((n) => n.id));
      const addedIds = fresh.map((n) => n.id);
      if (fresh.length === 0 && edges.length === 0) return [];
      cy.batch(() => {
        const added = cy.add(fresh.map(toNodeDef));
        // Edges whose endpoints exist (or arrive in this batch) go in now; the rest wait.
        const newEdges: GraphEdge[] = [];
        for (const e of edges) {
          if (!cy.getElementById(e.id).empty() || pending.some((p) => p.id === e.id)) continue;
          const ok = (id: string) => cy.getElementById(id).nonempty();
          if (ok(e.src) && ok(e.dst)) newEdges.push(e);
          else pending.push(e);
        }
        const addedEdges = cy.add(newEdges.map(toEdgeDef));

        // Seed positions: next to an already-placed neighbour; never relayout.
        const placed = new Set<string>(
          cy
            .nodes()
            .filter((n) => !freshIds.has(n.id()))
            .map((n) => n.id()),
        );
        seedNear(cy, added.nodes().toArray(), placed);
        applyFilters(added.union(addedEdges));
        added.nodes().addClass('fresh');
      });
      flushPending();
      updateEdgeMode();
      if (addedIds.length > 0) {
        const t = setTimeout(() => {
          timers.delete(t);
          for (const id of addedIds) cy.getElementById(id).removeClass('fresh');
        }, 2500);
        timers.add(t);
      }
      return addedIds;
    },

    removeCreatedSince(ts) {
      const doomed = cy.nodes().filter((n) => Number((n.data('props') as Props).created_at) >= ts);
      const n = doomed.length;
      cy.remove(doomed);
      pending = [];
      return n;
    },

    setFilters(f) {
      filters = f;
      applyFilters();
    },

    setSearch(q) {
      const needle = q.trim().toLowerCase();
      const matches: NodeSingular[] = [];
      cy.batch(() => {
        cy.elements().removeClass('match dim');
        if (!needle) return;
        cy.nodes().forEach((n) => {
          const props = n.data('props') as Props;
          const hit =
            name(n).toLowerCase().includes(needle) ||
            String(n.data('label')).toLowerCase() === needle ||
            Object.values(props).some((v) => typeof v === 'string' && v.toLowerCase().includes(needle));
          if (hit) {
            n.addClass('match');
            if (!n.hasClass('hide-label')) matches.push(n);
          } else n.addClass('dim');
        });
        cy.edges().addClass('dim');
      });
      return matches.sort((a, b) => name(a).localeCompare(name(b))).map((n) => n.id());
    },

    select(id) {
      cy.batch(() => {
        cy.elements().removeClass('sel nb faded');
        if (!id) return;
        const n = cy.getElementById(id);
        if (n.empty()) return;
        const closed = n.closedNeighborhood();
        closed.addClass('nb');
        n.addClass('sel');
        cy.elements().difference(closed).addClass('faded');
      });
    },

    focus(id) {
      const n = cy.getElementById(id);
      if (n.empty()) return;
      if (headless) cy.center(n);
      else cy.animate({ center: { eles: n }, zoom: Math.max(cy.zoom(), 1.3) }, { duration: 300 });
    },

    describe(id) {
      const n = cy.getElementById(id);
      if (n.empty()) return null;
      const neighbors: NeighborInfo[] = n.connectedEdges().map((e) => {
        const out = e.source().id() === id;
        const other = out ? e.target() : e.source();
        return {
          direction: out ? 'out' : 'in',
          type: String(e.data('type')),
          id: other.id(),
          label: String(other.data('label')),
          name: name(other),
        };
      });
      neighbors.sort((a, b) => a.type.localeCompare(b.type) || a.name.localeCompare(b.name));
      return {
        id,
        label: String(n.data('label')),
        name: name(n),
        props: n.data('props') as Props,
        neighbors,
      };
    },

    counts() {
      // Derived from our own filter classes (not `:visible`) so it is renderer-independent.
      let visibleEdges = 0;
      cy.edges().forEach((e) => {
        if (
          !e.hasClass('hide-type') &&
          !e.source().hasClass('hide-label') &&
          !e.target().hasClass('hide-label')
        )
          visibleEdges++;
      });
      return {
        visibleNodes: cy.nodes().not('.hide-label').length,
        totalNodes: cy.nodes().length,
        visibleEdges,
        totalEdges: cy.edges().length,
      };
    },

    labelCounts() {
      const out: Record<string, number> = {};
      cy.nodes().forEach((n) => {
        const l = String(n.data('label'));
        out[l] = (out[l] ?? 0) + 1;
      });
      return out;
    },

    edgeTypeCounts() {
      const out: Record<string, number> = {};
      cy.edges().forEach((e) => {
        const t = String(e.data('type'));
        out[t] = (out[t] ?? 0) + 1;
      });
      return out;
    },

    highlightPath(ids) {
      cy.batch(() => {
        cy.elements().removeClass('path').addClass('faded');
        let path = cy.collection();
        for (const id of ids) path = path.union(cy.getElementById(id));
        for (let i = 0; i < ids.length - 1; i++) {
          path = path.union(cy.getElementById(ids[i]!).edgesWith(cy.getElementById(ids[i + 1]!)));
        }
        path.removeClass('faded').addClass('path');
      });
    },

    clearHighlight() {
      cy.elements().removeClass('faded path');
    },

    relayout() {
      cy.layout({
        ...LAYOUT_OPTIONS,
        animate: !headless,
        animationDuration: 600,
      } as cytoscape.LayoutOptions).run();
    },

    fit() {
      cy.fit(undefined, 30);
    },

    setTheme(t) {
      theme = t;
      cy.style(buildStyle(theme, haystack));
    },

    destroy() {
      for (const t of timers) clearTimeout(t);
      timers.clear();
      cy.destroy();
    },
  };
  return controller;
}
