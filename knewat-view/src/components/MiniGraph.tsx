import { useCallback, useEffect, useState } from 'react';
import type { GraphEdge, GraphNode } from '../api';
import { MINI_CONTROLLER_OPTIONS } from '../lib/graphController';
import type { GraphController } from '../lib/graphController';
import { GraphCanvas } from './GraphCanvas';

interface Props {
  nodes: GraphNode[];
  edges: GraphEdge[];
  created: string[];
  updated: string[];
  onSelect?: (id: string | null) => void;
}

/** A small Cytoscape view of one event's nodes: created ringed green, updated ringed amber. */
export function MiniGraph({ nodes, edges, created, updated, onSelect }: Props) {
  const [ctl, setCtl] = useState<GraphController | null>(null);
  const select = useCallback((id: string | null) => onSelect?.(id), [onSelect]);

  useEffect(() => {
    if (!ctl) return;
    ctl.load(nodes, edges);
    ctl.markEvent(created, updated);
  }, [ctl, nodes, edges, created, updated]);

  return (
    <div className="mini-graph" data-testid="mini-graph">
      <GraphCanvas onReady={setCtl} onSelect={select} tuning={MINI_CONTROLLER_OPTIONS} />
      <div className="legend-inline">
        <span>
          <i className="swatch" style={{ borderColor: '#22c55e' }} /> created ({created.length})
        </span>
        <span>
          <i className="swatch" style={{ borderColor: '#f59e0b' }} /> updated ({updated.length})
        </span>
      </div>
    </div>
  );
}
