import cytoscape from 'cytoscape';
import type { Core, ElementDefinition, NodeSingular, StylesheetJson } from 'cytoscape';
import fcose from 'cytoscape-fcose';
import { keyEdges } from '../api/types';
import type { GraphEdge, GraphNode, Props } from '../api/types';
import { displayName, nodeColor } from './labels';
import type { ColorMode } from './labels';
import { EMPTY_MEMORY_COUNTS, medianActivation, memoryNodeData } from './memory';
import type { MemoryCounts } from './memory';

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

/** Ring colour of a suspect Fact (amber, readable on light and dark). */
export const SUSPECT_COLOR = '#d97706';

const NODE_SIZE: Record<string, number> = {
  Change: 16,
  CodeAnchor: 16,
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

/**
 * The Flow page's "What it touched" mini-graph: a handful of nodes in a 320 px box. Quality `default`
 * is cheap at this size and spreads nodes properly; a much stronger repulsion keep
 * each node's label clear of its neighbours (draft layout on the default options put about 10 label/label or
 * label/node overlaps in the busiest events, see miniLayout.test.ts); names are cut sooner and shown in full on hover.
 */
export const MINI_CONTROLLER_OPTIONS = {
  labelMaxWidth: 84,
  layout: {
    quality: 'default',
    idealEdgeLength: 120,
    nodeRepulsion: 200000,
    nodeSeparation: 220,
    gravity: 0.1,
    nodeDimensionsIncludeLabels: true,
  },
} as const satisfies Pick<ControllerOptions, 'layout' | 'labelMaxWidth'>;

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

/** Default node-label width on the canvas (px); longer names are cut with an ellipsis. */
export const LABEL_MAX_WIDTH = 110;

export function buildStyle(
  theme: Theme,
  haystack: boolean,
  labelMaxWidth: number = LABEL_MAX_WIDTH,
): StylesheetJson {
  return [
    {
      selector: 'node',
      style: {
        width: 'data(size)',
        height: 'data(size)',
        'background-color': 'data(color)',
        label: 'data(display)',
        color: theme.text,
        'font-size': 10,
        'text-valign': 'bottom',
        'text-margin-y': 3,
        'text-wrap': 'ellipsis',
        'text-max-width': `${labelMaxWidth}px`,
        'text-outline-color': theme.textOutline,
        'text-outline-width': 2,
        'min-zoomed-font-size': 9,
      },
    },
    // P7: a Fact's opacity follows its activation (data.opacity is set only when the API sent one).
    { selector: 'node[opacity]', style: { opacity: 'data(opacity)' as unknown as number } },
    // P7: dormant = dashed outline; suspect = amber ring (the ⚠ glyph is in the label).
    {
      selector: 'node[?dormant]',
      style: { 'border-style': 'dashed' as const, 'border-width': 2, 'border-color': theme.edgeStrong },
    },
    { selector: 'node[?suspect]', style: { 'border-width': 2, 'border-color': SUSPECT_COLOR } },
    // Anchors keep their label even when zoomed out; everything else labels on zoom-in.
    {
      selector:
        'node[label = "Agent"], node[label = "Task"], node[label = "Decision"], node[label = "Entity"]',
      style: { 'min-zoomed-font-size': 0, 'font-size': 11, 'font-weight': 600 },
    },
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
    // Hovering a node shows its whole name (labels are ellipsised otherwise) above its neighbours.
    {
      selector: 'node.hover',
      style: {
        'text-wrap': 'wrap' as const,
        'text-max-width': '260px',
        'z-index': 999,
        'text-background-color': theme.textOutline,
        'text-background-opacity': 0.9,
        'text-background-padding': '2px',
        'min-zoomed-font-size': 0,
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
    { selector: 'node.ctx, edge.ctx', style: { opacity: 0.45 } },
    { selector: 'node.ev-created', style: { 'border-width': 5, 'border-color': '#22c55e', opacity: 1 } },
    { selector: 'node.ev-updated', style: { 'border-width': 5, 'border-color': '#f59e0b', opacity: 1 } },
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

const createdAt = (n: NodeSingular): number | null => {
  const v = Number((n.data('props') as Props).created_at);
  return Number.isFinite(v) && v > 0 ? v : null;
};

export interface GraphController {
  readonly cy: Core;
  /** Replace all elements and run the one-off fcose layout (draft). */
  load(nodes: GraphNode[], edges: GraphEdge[]): void;
  clear(): void;
  /** Add nodes/edges without relayout; new nodes are seeded next to a neighbour. Returns the ids of nodes actually added. */
  addLive(nodes: GraphNode[], edges: GraphEdge[]): string[];
  /** Refresh the properties (and label text) of nodes already on the canvas. Returns how many changed. */
  updateProps(nodes: GraphNode[]): number;
  /** Remove every node created at or after `ts` (used by the fixture "replay as live" demo). Returns the count. */
  removeCreatedSince(ts: number): number;
  setFilters(f: FilterState): void;
  /** Fade centre for the activation-driven opacity: the API's A0, or null to use the median of the facts. */
  setActivationCenter(a0: number | null): void;
  /** Reasons from the verify queue (fact id -> text) for the suspect tooltips. */
  setSuspectReasons(reasons: ReadonlyMap<string, string>): void;
  /** Counts for the legend: suspect, pinned, dormant and activation-faded facts. */
  memoryCounts(): MemoryCounts;
  /** Colour nodes by their label or by the module that owns the label. */
  setColorMode(mode: ColorMode): void;
  /** Hide nodes whose `created_at` is outside [from, to] (epoch ms); null clears. Nodes without one stay. */
  setTimeRange(range: [number, number] | null): void;
  /** [min, max] of `created_at` over all nodes, or null when none has one. */
  timeBounds(): [number, number] | null;
  /** Show only `id` and everything within `hops` hops (over visible labels/edge types); returns the node count. */
  focusNeighborhood(id: string, hops?: number): number;
  clearFocus(): void;
  focusedOn(): string | null;
  setSearch(q: string): string[];
  select(id: string | null): void;
  focus(id: string): void;
  describe(id: string): NodeDescription | null;
  counts(): Counts;
  labelCounts(): Record<string, number>;
  edgeTypeCounts(): Record<string, number>;
  /** Flow view: ring what one tool call created (green) and updated (amber); the rest recedes. */
  markEvent(created: string[], updated: string[]): void;
  highlightPath(nodeIds: string[]): void;
  clearHighlight(): void;
  relayout(): void;
  fit(): void;
  setTheme(theme: Theme): void;
  destroy(): void;
}

export interface ControllerOptions {
  container?: HTMLElement | null;
  /** Overrides merged into {@link LAYOUT_OPTIONS} (e.g. a roomier layout for a small graph). */
  layout?: Record<string, unknown>;
  /** Node-label width in px before the name is cut with an ellipsis (hover shows the whole name). */
  labelMaxWidth?: number;
  /** No rendering (tests / jsdom). */
  headless?: boolean;
  onSelect?: (id: string | null) => void;
  theme?: Theme;
  /** Clock for the suspect rule (review dates); defaults to Date.now. */
  now?: () => number;
}

interface KeyedEdge {
  id: string;
  edge: GraphEdge;
}

const toNodeDef = (n: GraphNode, mode: ColorMode = 'label'): ElementDefinition => ({
  group: 'nodes',
  data: {
    id: n.id,
    label: n.label,
    name: displayName(n.label, n.props),
    size: NODE_SIZE[n.label] ?? 14,
    color: nodeColor(n.label, mode),
    props: n.props,
    display: displayName(n.label, n.props),
  },
});
const toEdgeDef = ({ id, edge: e }: KeyedEdge): ElementDefinition => ({
  group: 'edges',
  data: { id, source: e.source, target: e.target, type: e.type },
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
  const labelMaxWidth = opts.labelMaxWidth ?? LABEL_MAX_WIDTH;
  const layoutOptions = { ...LAYOUT_OPTIONS, ...opts.layout };
  let filters: FilterState = { hiddenLabels: new Set(), hiddenEdgeTypes: new Set() };
  /** Edges waiting for an endpoint, by key (a Map so "already parked?" is O(1)). */
  const pending = new Map<string, KeyedEdge>();
  let colorMode: ColorMode = 'label';
  let timeRange: [number, number] | null = null;
  let focus: Set<string> | null = null;
  let focusId: string | null = null;
  const timers = new Set<ReturnType<typeof setTimeout>>();
  const now = opts.now ?? Date.now;
  let givenA0: number | null = null;
  let reasons: ReadonlyMap<string, string> = new Map();
  const memoryCount: MemoryCounts = { ...EMPTY_MEMORY_COUNTS };

  const cy = cytoscape({
    container: headless ? undefined : opts.container,
    headless,
    styleEnabled: true,
    minZoom: 0.05,
    maxZoom: 4,
    wheelSensitivity: 0.25,
    style: buildStyle(theme, haystack, labelMaxWidth),
  });

  cy.on('mouseover', 'node', (e) => {
    e.target.addClass('hover');
    // A native tooltip on the canvas host: the suspect reason, pin / dormant notes, activation.
    const tip = String(e.target.data('tip') ?? '');
    if (opts.container) opts.container.title = tip;
  });
  cy.on('mouseout', 'node', (e) => {
    e.target.removeClass('hover');
    if (opts.container) opts.container.title = '';
  });
  cy.on('tap', 'node', (e) => opts.onSelect?.(e.target.id()));
  cy.on('tap', (e) => {
    if (e.target === cy) opts.onSelect?.(null);
  });

  const name = (n: NodeSingular): string => String(n.data('name'));

  /**
   * (Re)compute the P7 display data of every node: glyphs in the label, tooltip, suspect / dormant / pinned
   * flags and the activation opacity. The fade centre is the API's A0 if given, else the median activation of
   * the Facts on the canvas. Cheap (one pass); runs after every change to the node set or their properties.
   */
  function applyMemory(): void {
    const all = cy
      .nodes()
      .map((n) => ({ id: n.id(), label: String(n.data('label')), props: n.data('props') as Props }));
    const a0 = givenA0 ?? medianActivation(all);
    const t = now();
    const counts: MemoryCounts = { suspect: 0, pinned: 0, dormant: 0, faded: 0 };
    cy.batch(() => {
      for (const g of all) {
        const el = cy.getElementById(g.id);
        const d = memoryNodeData(g, displayName(g.label, g.props), { now: t, a0, reasons });
        el.data({ display: d.display, suspect: d.suspect, pinned: d.pinned, dormant: d.dormant, tip: d.tip });
        if (d.opacity === undefined) el.removeData('opacity');
        else el.data('opacity', d.opacity);
        if (d.suspect) counts.suspect++;
        if (d.pinned) counts.pinned++;
        if (d.dormant) counts.dormant++;
        if (d.opacity !== undefined) counts.faded++;
      }
    });
    Object.assign(memoryCount, counts);
  }

  function applyFilters(eles = cy.elements()) {
    cy.batch(() => {
      eles.nodes().forEach((n) => {
        const t = timeRange ? createdAt(n) : null;
        const outOfTime = timeRange !== null && t !== null && (t < timeRange[0] || t > timeRange[1]);
        const outOfFocus = focus !== null && !focus.has(n.id());
        // `hide-label` means "hidden by any node filter" (label, time range, focus).
        n.toggleClass(
          'hide-label',
          filters.hiddenLabels.has(String(n.data('label'))) || outOfTime || outOfFocus,
        );
      });
      eles.edges().forEach((e) => {
        e.toggleClass('hide-type', filters.hiddenEdgeTypes.has(String(e.data('type'))));
      });
    });
  }

  function flushPending(): void {
    if (pending.size === 0) return;
    const ready: KeyedEdge[] = [];
    for (const [id, k] of pending) {
      if (!cy.getElementById(id).empty()) {
        pending.delete(id);
      } else if (cy.getElementById(k.edge.source).nonempty() && cy.getElementById(k.edge.target).nonempty()) {
        pending.delete(id);
        ready.push(k);
      }
    }
    if (ready.length > 0) {
      const added = cy.add(ready.map(toEdgeDef));
      applyFilters(added);
    }
  }

  function updateEdgeMode(): void {
    const next = cy.edges().length > HAYSTACK_EDGE_THRESHOLD;
    if (next !== haystack) {
      haystack = next;
      cy.style(buildStyle(theme, haystack, labelMaxWidth));
    }
  }

  const controller: GraphController = {
    cy,

    load(nodes, edges) {
      cy.elements().remove();
      pending.clear();
      timeRange = null;
      focus = null;
      focusId = null;
      const known = new Set(nodes.map((n) => n.id));
      cy.batch(() => {
        cy.add(nodes.map((n) => toNodeDef(n, colorMode)));
        cy.add(keyEdges(edges.filter((e) => known.has(e.source) && known.has(e.target))).map(toEdgeDef));
      });
      updateEdgeMode();
      applyFilters();
      applyMemory();
      if (nodes.length > 0) {
        // Lay out what is visible (hidden-by-default labels/edge types would only add hairball), then
        // park the hidden nodes next to their neighbours so toggling them on moves nothing.
        const visible = cy.elements().not('.hide-label, .hide-type');
        if (visible.nodes().nonempty()) {
          visible.layout({ ...layoutOptions, animate: false } as cytoscape.LayoutOptions).run();
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
      pending.clear();
    },

    addLive(nodes, edges) {
      const fresh = nodes.filter((n) => cy.getElementById(n.id).empty());
      const freshIds = new Set(fresh.map((n) => n.id));
      const addedIds = fresh.map((n) => n.id);
      if (fresh.length === 0 && edges.length === 0) return [];
      cy.batch(() => {
        const added = cy.add(fresh.map((n) => toNodeDef(n, colorMode)));
        // Edges whose endpoints exist (or arrive in this batch) go in now; the rest wait.
        const newEdges: KeyedEdge[] = [];
        const ok = (id: string) => cy.getElementById(id).nonempty();
        for (const k of keyEdges(edges)) {
          if (!cy.getElementById(k.id).empty() || pending.has(k.id)) continue;
          if (ok(k.edge.source) && ok(k.edge.target)) newEdges.push(k);
          else pending.set(k.id, k);
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
      if (addedIds.length > 0) applyMemory();
      if (addedIds.length > 0) {
        const t = setTimeout(() => {
          timers.delete(t);
          for (const id of addedIds) cy.getElementById(id).removeClass('fresh');
        }, 2500);
        timers.add(t);
      }
      return addedIds;
    },

    updateProps(nodes) {
      let changed = 0;
      cy.batch(() => {
        for (const n of nodes) {
          const el = cy.getElementById(n.id);
          if (el.empty()) continue;
          if (JSON.stringify(el.data('props')) === JSON.stringify(n.props)) continue;
          el.data('props', n.props);
          el.data('name', displayName(n.label, n.props));
          changed++;
        }
      });
      if (changed > 0) applyMemory();
      return changed;
    },

    removeCreatedSince(ts) {
      const doomed = cy.nodes().filter((n) => Number((n.data('props') as Props).created_at) >= ts);
      const n = doomed.length;
      cy.remove(doomed);
      pending.clear();
      return n;
    },

    setFilters(f) {
      filters = f;
      applyFilters();
    },

    setActivationCenter(a0) {
      givenA0 = a0;
      applyMemory();
    },

    setSuspectReasons(next) {
      reasons = next;
      applyMemory();
    },

    memoryCounts() {
      return { ...memoryCount };
    },

    setColorMode(mode) {
      colorMode = mode;
      cy.batch(() => {
        cy.nodes().forEach((n) => {
          n.data('color', nodeColor(String(n.data('label')), mode));
        });
      });
    },

    setTimeRange(range) {
      timeRange = range;
      applyFilters();
    },

    timeBounds() {
      let lo = Infinity;
      let hi = -Infinity;
      cy.nodes().forEach((n) => {
        const t = createdAt(n);
        if (t === null) return;
        lo = Math.min(lo, t);
        hi = Math.max(hi, t);
      });
      return lo <= hi ? [lo, hi] : null;
    },

    focusNeighborhood(id, hops = 2) {
      const start = cy.getElementById(id);
      if (start.empty()) return 0;
      const usable = (n: NodeSingular) => !filters.hiddenLabels.has(String(n.data('label')));
      const seen = new Set<string>([id]);
      let frontier = [start as NodeSingular];
      for (let h = 0; h < hops; h++) {
        const next: NodeSingular[] = [];
        for (const n of frontier) {
          n.connectedEdges()
            .filter((e) => !filters.hiddenEdgeTypes.has(String(e.data('type'))))
            .forEach((e) => {
              const other = e.source().id() === n.id() ? e.target() : e.source();
              if (seen.has(other.id()) || !usable(other)) return;
              seen.add(other.id());
              next.push(other);
            });
        }
        frontier = next;
      }
      focus = seen;
      focusId = id;
      applyFilters();
      cy.fit(cy.nodes().not('.hide-label'), 40);
      return seen.size;
    },

    clearFocus() {
      focus = null;
      focusId = null;
      applyFilters();
    },

    focusedOn() {
      return focusId;
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

    markEvent(created, updated) {
      cy.batch(() => {
        cy.elements().removeClass('ev-created ev-updated ctx');
        const c = cy.collection();
        const hit = (ids: string[], cls: string) => {
          const eles = cy.collection();
          for (const id of ids) eles.merge(cy.getElementById(id));
          eles.addClass(cls);
          return eles;
        };
        const made = hit(created, 'ev-created');
        const changed = hit(updated, 'ev-updated');
        c.merge(made).merge(changed);
        cy.elements().difference(c.union(c.connectedEdges())).addClass('ctx');
      });
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
        ...layoutOptions,
        animate: !headless,
        animationDuration: 600,
      } as cytoscape.LayoutOptions).run();
    },

    fit() {
      cy.fit(undefined, 30);
    },

    setTheme(t) {
      theme = t;
      cy.style(buildStyle(theme, haystack, labelMaxWidth));
    },

    destroy() {
      for (const t of timers) clearTimeout(t);
      timers.clear();
      cy.destroy();
    },
  };
  return controller;
}
