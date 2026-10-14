import type { PlacedEdge, PlacedNode, WhyLayout } from '../lib/whyLayout';
import { NODE_H, NODE_W } from '../lib/whyLayout';
import { labelColor } from '../lib/labels';

interface Props {
  layout: WhyLayout;
  selected: string | null;
  /** Node ids / edge keys on the highlighted path (everything else is dimmed). */
  highlight: { nodes: Set<string>; edges: Set<string> } | null;
  onSelect: (id: string) => void;
}

const trunc = (s: string, n: number) => (s.length > n ? `${s.slice(0, n - 1)}…` : s);

function edgePath(a: PlacedNode, b: PlacedNode): string {
  const y1 = a.y + NODE_H / 2;
  const y2 = b.y + NODE_H / 2;
  if (a.x === b.x) {
    // same column: bow out to the right
    const x = a.x + NODE_W;
    return `M ${x} ${y1} C ${x + 44} ${y1}, ${x + 44} ${y2}, ${x} ${y2}`;
  }
  // Leave from the side facing the other node, so edges that point back towards the root still read clearly.
  const forward = b.x > a.x;
  const x1 = forward ? a.x + NODE_W : a.x;
  const x2 = forward ? b.x : b.x + NODE_W;
  const mid = (x1 + x2) / 2;
  return `M ${x1} ${y1} C ${mid} ${y1}, ${mid} ${y2}, ${x2} ${y2}`;
}

/** The provenance graph as SVG: one column per hop distance from the explained node, left to right. */
export function WhyGraph({ layout, selected, highlight, onSelect }: Props) {
  const byId = new Map(layout.nodes.map((n) => [n.id, n]));
  const dim = (on: boolean) => (highlight ? (on ? 1 : 0.18) : 1);
  return (
    <div className="why-scroll">
      <svg
        className="why-graph"
        width={layout.width + 40}
        height={layout.height}
        viewBox={`0 0 ${layout.width + 40} ${layout.height}`}
        role="group"
        aria-label="Provenance graph"
        data-testid="why-graph"
      >
        <defs>
          <marker
            id="why-arrow"
            viewBox="0 0 10 10"
            refX="9"
            refY="5"
            markerUnits="userSpaceOnUse"
            markerWidth="9"
            markerHeight="9"
            orient="auto"
          >
            <path d="M 0 0 L 10 5 L 0 10 z" fill="currentColor" />
          </marker>
        </defs>
        {layout.columns.map((c) => (
          <text key={c.depth} x={c.x} y={18} className="why-col-head">
            {trunc(c.heading, 30)}
          </text>
        ))}
        <g className="why-edges">
          {layout.edges.map((e: PlacedEdge) => {
            const a = byId.get(e.from);
            const b = byId.get(e.to);
            if (!a || !b) return null;
            const on = highlight?.edges.has(e.key) ?? false;
            const mx = a.x === b.x ? a.x + NODE_W + 30 : (a.x + b.x + NODE_W) / 2;
            const my = (a.y + b.y + NODE_H) / 2;
            return (
              <g key={e.key} opacity={dim(on)} data-edge={e.key} data-on={on || undefined}>
                <path
                  d={edgePath(a, b)}
                  className={on ? 'why-edge on' : 'why-edge'}
                  fill="none"
                  markerEnd="url(#why-arrow)"
                />
                <text x={mx} y={my - 3} className="why-edge-label" textAnchor="middle">
                  {e.rel}
                </text>
              </g>
            );
          })}
        </g>
        <g className="why-nodes">
          {layout.nodes.map((n) => {
            const on = highlight?.nodes.has(n.id) ?? false;
            return (
              <g
                key={n.id}
                transform={`translate(${n.x}, ${n.y})`}
                opacity={dim(on)}
                className={`why-node${n.isRoot ? ' root' : ''}${n.id === selected ? ' sel' : ''}`}
                role="button"
                tabIndex={0}
                aria-pressed={n.id === selected}
                aria-label={`${n.label}: ${n.title}`}
                data-testid={`why-node-${n.label}`}
                data-id={n.id}
                data-on={on || undefined}
                onClick={() => onSelect(n.id)}
                onKeyDown={(e) => {
                  if (e.key === 'Enter' || e.key === ' ') {
                    e.preventDefault();
                    onSelect(n.id);
                  }
                }}
              >
                <rect width={NODE_W} height={NODE_H} rx={8} className="why-box" />
                <rect width={6} height={NODE_H} rx={3} fill={labelColor(n.label)} />
                <text x={16} y={19} className="why-label">
                  {n.label}
                </text>
                <text x={16} y={36} className="why-title">
                  {trunc(n.title, 28)}
                </text>
              </g>
            );
          })}
        </g>
      </svg>
    </div>
  );
}
