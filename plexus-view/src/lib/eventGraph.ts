import type { FlowEvent, GraphEdge, GraphNode } from '../api';

export interface EventGraph {
  nodes: GraphNode[];
  edges: GraphEdge[];
  created: string[];
  updated: string[];
  /** Created/updated ids the loaded graph does not contain yet (it may need a refresh). */
  missing: string[];
}

/** Labels that would only add noise around an event's nodes in the mini-graph. */
const CONTEXT_SKIP = new Set(['ToolCall', 'Step', 'Recall', 'Scope']);

/**
 * The part of the graph one tool call touched: the ToolCall itself, the nodes it created/updated, and
 * their direct neighbours for context (bookkeeping labels left out).
 */
export function eventSubgraph(graph: { nodes: GraphNode[]; edges: GraphEdge[] }, ev: FlowEvent): EventGraph {
  const byId = new Map(graph.nodes.map((n) => [n.id, n]));
  const created = ev.created.map((r) => r.id).filter((id) => byId.has(id));
  const updated = ev.updated.map((r) => r.id).filter((id) => byId.has(id));
  const missing = [...ev.created, ...ev.updated].map((r) => r.id).filter((id) => !byId.has(id));
  const core = new Set([ev.id, ...created, ...updated].filter((id) => byId.has(id)));
  const keep = new Set(core);
  for (const e of graph.edges) {
    const a = core.has(e.source);
    const b = core.has(e.target);
    if (a === b) continue;
    const other = byId.get(a ? e.target : e.source);
    if (other && !CONTEXT_SKIP.has(other.label)) keep.add(other.id);
  }
  return {
    nodes: [...keep].map((id) => byId.get(id)!),
    edges: graph.edges.filter((e) => keep.has(e.source) && keep.has(e.target)),
    created,
    updated,
    missing,
  };
}
