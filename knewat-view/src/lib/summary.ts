import type { GraphEdge, GraphNode, Inventory } from '../api/types';

/** Headline numbers for "what the demo created" (Inventory page). */
export interface DemoSummary {
  agents: number;
  tasks: { total: number; open: number; claimed: number; done: number; failed: number; reclaimed: number };
  facts: { total: number; active: number; superseded: number; contradicting: number };
  decisions: number;
  handoffs: number;
  toolCalls: number;
  /** True when the node sample hit its limit, so task/fact splits may undercount. */
  sampled: boolean;
}

/** Labels needed for the task / fact splits (fetched as one filtered `graph` call). */
export const SUMMARY_LABELS = ['Agent', 'Task', 'Fact', 'Decision', 'Handoff'];

const countOf = (inv: Inventory, label: string): number =>
  inv.labels.find((l) => l.label === label)?.count ?? 0;

/**
 * Combine the exact per-label counts from `/inventory` with the splits (status, reclaims,
 * contradictions) read from a subgraph of the Task/Fact nodes and the edges among them.
 */
export function summarize(
  inv: Inventory,
  sub: { nodes: GraphNode[]; edges: GraphEdge[]; truncated?: boolean } | undefined,
): DemoSummary {
  const nodes = sub?.nodes ?? [];
  const status = (label: string, s: string) =>
    nodes.filter((n) => n.label === label && n.props.status === s).length;
  const claimsPerTask = new Map<string, number>();
  let contradicting = 0;
  for (const e of sub?.edges ?? []) {
    if (e.type === 'CLAIMED') claimsPerTask.set(e.target, (claimsPerTask.get(e.target) ?? 0) + 1);
    if (e.type === 'CONTRADICTS') contradicting++;
  }
  return {
    agents: countOf(inv, 'Agent'),
    tasks: {
      total: countOf(inv, 'Task'),
      open: status('Task', 'open'),
      claimed: status('Task', 'claimed'),
      done: status('Task', 'done'),
      failed: status('Task', 'failed'),
      reclaimed: [...claimsPerTask.values()].filter((c) => c > 1).length,
    },
    facts: {
      total: countOf(inv, 'Fact'),
      active: status('Fact', 'active'),
      superseded: status('Fact', 'superseded'),
      contradicting,
    },
    decisions: countOf(inv, 'Decision'),
    handoffs: countOf(inv, 'Handoff'),
    toolCalls: countOf(inv, 'ToolCall'),
    sampled: sub?.truncated ?? false,
  };
}
