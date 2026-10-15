import type { ElementDefinition, NodeSingular } from 'cytoscape';
import type { GraphEdge, GraphNode, Props } from '../api/types';
import { displayName, nodeColor } from './labels';
import type { ColorMode } from './labels';

export const NODE_SIZE: Record<string, number> = {
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

export const createdAt = (n: NodeSingular): number | null => {
  const v = Number((n.data('props') as Props).created_at);
  return Number.isFinite(v) && v > 0 ? v : null;
};

/** The display name stored on a canvas node. */
export const nodeName = (n: NodeSingular): string => String(n.data('name'));

export interface KeyedEdge {
  id: string;
  edge: GraphEdge;
}

export const toNodeDef = (n: GraphNode, mode: ColorMode = 'label'): ElementDefinition => ({
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
export const toEdgeDef = ({ id, edge: e }: KeyedEdge): ElementDefinition => ({
  group: 'edges',
  data: { id, source: e.source, target: e.target, type: e.type },
});
