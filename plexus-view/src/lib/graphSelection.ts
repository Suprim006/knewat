import type { Core, NodeSingular } from 'cytoscape';
import type { Props } from '../api/types';
import { createdAt, nodeName } from './graphData';
import type { Counts, FilterState, NeighborInfo, NodeDescription } from './graphTypes';

/*
 * Read-mostly helpers over a Cytoscape instance: search, selection and path highlighting, event rings,
 * node descriptions and the counts shown in the UI. Pure functions of `cy` (plus the filters where one is
 * needed); the controller owns all the state and calls these.
 */

/** Mark nodes matching `q` (name, label, any string prop) and dim the rest; returns the visible matches by name. */
export function searchNodes(cy: Core, q: string): string[] {
  const needle = q.trim().toLowerCase();
  const matches: NodeSingular[] = [];
  cy.batch(() => {
    cy.elements().removeClass('match dim');
    if (!needle) return;
    cy.nodes().forEach((n) => {
      const props = n.data('props') as Props;
      const hit =
        nodeName(n).toLowerCase().includes(needle) ||
        String(n.data('label')).toLowerCase() === needle ||
        Object.values(props).some((v) => typeof v === 'string' && v.toLowerCase().includes(needle));
      if (hit) {
        n.addClass('match');
        if (!n.hasClass('hide-label')) matches.push(n);
      } else n.addClass('dim');
    });
    cy.edges().addClass('dim');
  });
  return matches.sort((a, b) => nodeName(a).localeCompare(nodeName(b))).map((n) => n.id());
}

/** Highlight `id` and its closed neighbourhood; everything else fades. `null` clears. */
export function selectNode(cy: Core, id: string | null): void {
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
}

/** Ring the nodes one tool call created (green) and updated (amber); the rest of the graph recedes. */
export function markEvent(cy: Core, created: string[], updated: string[]): void {
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
}

/** Emphasise the nodes of `ids` and the edges between consecutive ones; everything else fades. */
export function highlightPath(cy: Core, ids: string[]): void {
  cy.batch(() => {
    cy.elements().removeClass('path').addClass('faded');
    let path = cy.collection();
    for (const id of ids) path = path.union(cy.getElementById(id));
    for (let i = 0; i < ids.length - 1; i++) {
      path = path.union(cy.getElementById(ids[i]!).edgesWith(cy.getElementById(ids[i + 1]!)));
    }
    path.removeClass('faded').addClass('path');
  });
}

/** A node's identity, properties and neighbours (sorted by edge type, then name); null when it is not on the canvas. */
export function describeNode(cy: Core, id: string): NodeDescription | null {
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
      name: nodeName(other),
    };
  });
  neighbors.sort((a, b) => a.type.localeCompare(b.type) || a.name.localeCompare(b.name));
  return {
    id,
    label: String(n.data('label')),
    name: nodeName(n),
    props: n.data('props') as Props,
    neighbors,
  };
}

/**
 * Ids of `start` and everything within `hops` hops, walking only edge types and labels the filters leave visible.
 * The caller checks that `start` exists.
 */
export function neighborhoodIds(start: NodeSingular, hops: number, filters: FilterState): Set<string> {
  const usable = (n: NodeSingular) => !filters.hiddenLabels.has(String(n.data('label')));
  const seen = new Set<string>([start.id()]);
  let frontier = [start];
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
  return seen;
}

/** Visible / total node and edge counts, derived from our own filter classes (not `:visible`) so it is renderer-independent. */
export function countElements(cy: Core): Counts {
  let visibleEdges = 0;
  cy.edges().forEach((e) => {
    if (!e.hasClass('hide-type') && !e.source().hasClass('hide-label') && !e.target().hasClass('hide-label'))
      visibleEdges++;
  });
  return {
    visibleNodes: cy.nodes().not('.hide-label').length,
    totalNodes: cy.nodes().length,
    visibleEdges,
    totalEdges: cy.edges().length,
  };
}

/** Number of elements per value of the data field `field` ('label' for nodes, 'type' for edges). */
function tally(eles: readonly { data(key: string): unknown }[], field: string): Record<string, number> {
  const out: Record<string, number> = {};
  for (const e of eles) {
    const k = String(e.data(field));
    out[k] = (out[k] ?? 0) + 1;
  }
  return out;
}
export const countLabels = (cy: Core): Record<string, number> => tally(cy.nodes().toArray(), 'label');
export const countEdgeTypes = (cy: Core): Record<string, number> => tally(cy.edges().toArray(), 'type');

/** [min, max] of `created_at` over all nodes, or null when none has one. */
export function createdAtBounds(cy: Core): [number, number] | null {
  let lo = Infinity;
  let hi = -Infinity;
  cy.nodes().forEach((n) => {
    const t = createdAt(n);
    if (t === null) return;
    lo = Math.min(lo, t);
    hi = Math.max(hi, t);
  });
  return lo <= hi ? [lo, hi] : null;
}
