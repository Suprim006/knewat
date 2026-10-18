import type { LineageEdge, LineageNode, WhyHop, WhyResult } from '../api/types';
import { displayName } from './labels';
import type { Props } from '../api/types';

export const NODE_W = 196;
export const NODE_H = 46;
const COL_GAP = 96;
const ROW_GAP = 14;
const PAD = 16;

export interface PlacedNode {
  id: string;
  label: string;
  title: string;
  depth: number;
  x: number;
  y: number;
  isRoot: boolean;
  props: Record<string, unknown>;
}
export interface PlacedEdge {
  key: string;
  from: string;
  to: string;
  rel: string;
}
export interface WhyLayout {
  nodes: PlacedNode[];
  edges: PlacedEdge[];
  width: number;
  height: number;
  /** Column index -> header text (the labels found at that depth). */
  columns: { depth: number; x: number; heading: string }[];
}

const edgeKey = (from: string, rel: string, to: string): string => `${from}|${rel}|${to}`;

/** The stored edge a hop walked along (a reverse hop walked it backwards). */
const hopEdgeKey = (h: WhyHop): string =>
  h.reverse ? edgeKey(h.to, h.rel, h.from) : edgeKey(h.from, h.rel, h.to);

/** Short text for a lineage node (Step also shows its agent). */
function nodeTitle(n: LineageNode): string {
  const p = n.props as Props;
  if (n.label === 'Step') return `${String(p.agent_id ?? '')} step ${String(p.n ?? '?')}`.trim();
  if (n.label === 'Source') return String(p.title ?? '') || displayName(n.label, p);
  return displayName(n.label, p);
}

const LABEL_ORDER = ['Decision', 'Fact', 'Task', 'Entity', 'Agent', 'Step', 'Source', 'Episode'];
const rank = (label: string): number => {
  const i = LABEL_ORDER.indexOf(label);
  return i < 0 ? LABEL_ORDER.length : i;
};

/**
 * Left-to-right layered layout for a `why` result: a node's column is the number of hops on the
 * shortest path from the root (the decision or fact being explained); rows are sorted by label then title.
 */
export function layoutWhy(result: WhyResult): WhyLayout {
  const depth = new Map<string, number>([[result.root, 0]]);
  for (const path of result.paths) {
    path.forEach((hop, i) => {
      const d = i + 1;
      const cur = depth.get(hop.to);
      if (cur === undefined || d < cur) depth.set(hop.to, d);
    });
  }
  // Nodes the API returned without a path still get a column, right after their deepest known neighbour.
  const known = result.nodes.filter((n) => depth.has(n.id));
  const maxDepth = known.reduce((m, n) => Math.max(m, depth.get(n.id)!), 0);
  for (const n of result.nodes) if (!depth.has(n.id)) depth.set(n.id, maxDepth + 1);

  const byDepth = new Map<number, LineageNode[]>();
  for (const n of result.nodes) {
    const d = depth.get(n.id)!;
    (byDepth.get(d) ?? byDepth.set(d, []).get(d)!).push(n);
  }
  const depths = [...byDepth.keys()].sort((a, b) => a - b);
  const tallest = Math.max(1, ...depths.map((d) => byDepth.get(d)!.length));
  const height = PAD * 2 + 24 + tallest * (NODE_H + ROW_GAP) - ROW_GAP;

  const nodes: PlacedNode[] = [];
  const columns: WhyLayout['columns'] = [];
  depths.forEach((d, col) => {
    const x = PAD + col * (NODE_W + COL_GAP);
    const list = byDepth
      .get(d)!
      .map((n) => ({ n, title: nodeTitle(n) }))
      .sort((a, b) => rank(a.n.label) - rank(b.n.label) || a.title.localeCompare(b.title));
    const colHeight = list.length * (NODE_H + ROW_GAP) - ROW_GAP;
    const top = PAD + 24 + (height - PAD * 2 - 24 - colHeight) / 2;
    list.forEach(({ n, title }, row) => {
      nodes.push({
        id: n.id,
        label: n.label,
        title,
        depth: d,
        x,
        y: top + row * (NODE_H + ROW_GAP),
        isRoot: n.id === result.root,
        props: n.props,
      });
    });
    const labels = [...new Set(list.map((x) => x.n.label))];
    columns.push({
      depth: d,
      x,
      heading: d === 0 ? `Explaining · ${labels.join(', ')}` : labels.join(' · '),
    });
  });

  const ids = new Set(nodes.map((n) => n.id));
  const edges: PlacedEdge[] = result.edges
    .filter((e: LineageEdge) => ids.has(e.from) && ids.has(e.to))
    .map((e) => ({ key: edgeKey(e.from, e.rel, e.to), from: e.from, to: e.to, rel: e.rel }));
  return {
    nodes,
    edges,
    width: PAD * 2 + depths.length * NODE_W + Math.max(0, depths.length - 1) * COL_GAP,
    height,
    columns,
  };
}

/** The edge keys and node ids on the shortest path from the root to `target`. */
export function pathTo(result: WhyResult, target: string): { nodes: Set<string>; edges: Set<string> } {
  const nodes = new Set<string>([result.root]);
  const edges = new Set<string>();
  let best: WhyHop[] | undefined;
  for (const p of result.paths) {
    if (p.length > 0 && p[p.length - 1]!.to === target && (!best || p.length < best.length)) best = p;
  }
  for (const hop of best ?? []) {
    nodes.add(hop.from);
    nodes.add(hop.to);
    edges.add(hopEdgeKey(hop));
  }
  return { nodes, edges };
}
