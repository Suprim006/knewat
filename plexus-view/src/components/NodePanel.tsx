import { formatProp, labelColor } from '../lib/labels';
import type { NeighborInfo, NodeDescription } from '../lib/graphController';

interface Props {
  node: NodeDescription | null;
  onSelectNode: (id: string) => void;
  onClose: () => void;
}

export function NodePanel({ node, onSelectNode, onClose }: Props) {
  if (!node) {
    return (
      <aside className="panel side" aria-label="Node details">
        <p className="muted">Click a node to see its properties and neighbours.</p>
      </aside>
    );
  }
  const keys = Object.keys(node.props).filter((k) => k !== 'embedding');
  const groups = new Map<string, NeighborInfo[]>();
  for (const n of node.neighbors) {
    const k = `${n.direction === 'out' ? '→' : '←'} ${n.type}`;
    groups.set(k, [...(groups.get(k) ?? []), n]);
  }
  return (
    <aside className="panel side" aria-label="Node details">
      <div className="side-head">
        <span className="chip" style={{ background: labelColor(node.label) }}>
          {node.label}
        </span>
        <button type="button" className="btn small" onClick={onClose} aria-label="Close details">
          ✕
        </button>
      </div>
      <h2 className="side-title">{node.name}</h2>
      <h3>Properties</h3>
      <dl className="props">
        <dt>id</dt>
        <dd className="mono">{node.id}</dd>
        {keys.map((k) => (
          <div key={k} className="prop-row">
            <dt>{k}</dt>
            <dd>{formatProp(k, node.props[k])}</dd>
          </div>
        ))}
      </dl>
      <h3>Neighbours ({node.neighbors.length})</h3>
      {groups.size === 0 && <p className="muted">No connections.</p>}
      {[...groups].map(([group, items]) => (
        <div key={group} className="nb-group">
          <div className="nb-type">
            {group} <span className="muted">({items.length})</span>
          </div>
          <ul>
            {items.map((n) => (
              <li key={`${group}${n.id}`}>
                <button type="button" className="link" onClick={() => onSelectNode(n.id)}>
                  <span className="dot" style={{ background: labelColor(n.label) }} />
                  {n.name}
                  <span className="muted"> · {n.label}</span>
                </button>
              </li>
            ))}
          </ul>
        </div>
      ))}
    </aside>
  );
}
