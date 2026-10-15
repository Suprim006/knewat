import type { Core } from 'cytoscape';
import type { GraphEdge, GraphNode, Props } from '../api/types';
import type { ColorMode } from './labels';
import type { MemoryCounts } from './memory';
import type { Theme } from './graphStyle';

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
