import { Link } from 'react-router-dom';
import { ABLATED_EDGES, ABLATION_RESULTS_PATH } from '../lib/ablation';

/** Shown while the ablation switch is on: which Knewat features stop working without the hidden edges. */
export function AblationPanel({ counts }: { counts: Record<string, number> }) {
  return (
    <section
      className="ablation-panel"
      aria-label="What breaks without these edges"
      data-testid="ablation-panel"
    >
      <p className="muted">
        Presentation only: the edges are still in the graph. This is what the product could no longer do if
        they were really gone.
      </p>
      <ul>
        {ABLATED_EDGES.map((e) => (
          <li key={e.type}>
            <div>
              <code>{e.type}</code>{' '}
              <span className="muted">
                · {counts[e.type] ?? 0} edges · {e.meaning}
              </span>
            </div>
            <ul>
              {e.breaks.map((b) => (
                <li key={b.feature}>
                  <b>{b.feature}</b>: {b.effect}
                </li>
              ))}
            </ul>
          </li>
        ))}
      </ul>
      <Link to={ABLATION_RESULTS_PATH}>See the measured ablation results →</Link>
    </section>
  );
}
