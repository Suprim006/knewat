import cytoscape from 'cytoscape';
import type { NodeSingular } from 'cytoscape';
import fcose from 'cytoscape-fcose';
import { keyEdges } from '../api/types';
import type { Props } from '../api/types';
import { createdAt, toEdgeDef, toNodeDef } from './graphData';
import type { KeyedEdge } from './graphData';
import { LAYOUT_OPTIONS, seedNear } from './graphLayout';
import {
  countEdgeTypes,
  countElements,
  countLabels,
  createdAtBounds,
  describeNode,
  highlightPath,
  markEvent,
  neighborhoodIds,
  searchNodes,
  selectNode,
} from './graphSelection';
import { HAYSTACK_EDGE_THRESHOLD, LABEL_MAX_WIDTH, LIGHT_THEME, buildStyle } from './graphStyle';
import type { ControllerOptions, FilterState, GraphController } from './graphTypes';
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
 *
 * This file holds the controller (state + mutations). The rest lives next to it and is re-exported here, so
 * importers keep using `lib/graphController`:
 *  - graphStyle.ts     themes and the Cytoscape stylesheet
 *  - graphLayout.ts    fcose options, the mini-graph options and the seeding of new nodes
 *  - graphData.ts      API node/edge -> Cytoscape element mapping
 *  - graphSelection.ts search, selection / path highlighting, descriptions and counts
 *  - graphTypes.ts     the controller's interfaces
 */

export { DARK_THEME, LIGHT_THEME } from './graphStyle';
export { MINI_CONTROLLER_OPTIONS } from './graphLayout';
export type {
  ControllerOptions,
  Counts,
  GraphController,
  NeighborInfo,
  NodeDescription,
} from './graphTypes';

let registered = false;
function register() {
  if (registered) return;
  registered = true;
  cytoscape.use(fcose);
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
    const counts: MemoryCounts = { suspect: 0, pinned: 0, dormant: 0, duplicate: 0, faded: 0 };
    cy.batch(() => {
      for (const g of all) {
        const el = cy.getElementById(g.id);
        const d = memoryNodeData(g, displayName(g.label, g.props), { now: t, a0, reasons });
        el.data({
          display: d.display,
          suspect: d.suspect,
          pinned: d.pinned,
          dormant: d.dormant,
          duplicate: d.duplicate,
          tip: d.tip,
        });
        if (d.opacity === undefined) el.removeData('opacity');
        else el.data('opacity', d.opacity);
        if (d.suspect) counts.suspect++;
        if (d.pinned) counts.pinned++;
        if (d.dormant) counts.dormant++;
        if (d.duplicate) counts.duplicate++;
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
      return createdAtBounds(cy);
    },

    focusNeighborhood(id, hops = 2) {
      const start = cy.getElementById(id);
      if (start.empty()) return 0;
      const seen = neighborhoodIds(start as NodeSingular, hops, filters);
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
      return searchNodes(cy, q);
    },

    select(id) {
      selectNode(cy, id);
    },

    focus(id) {
      const n = cy.getElementById(id);
      if (n.empty()) return;
      if (headless) cy.center(n);
      else cy.animate({ center: { eles: n }, zoom: Math.max(cy.zoom(), 1.3) }, { duration: 300 });
    },

    describe(id) {
      return describeNode(cy, id);
    },

    counts() {
      return countElements(cy);
    },

    labelCounts() {
      return countLabels(cy);
    },

    edgeTypeCounts() {
      return countEdgeTypes(cy);
    },

    markEvent(created, updated) {
      markEvent(cy, created, updated);
    },

    highlightPath(ids) {
      highlightPath(cy, ids);
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
