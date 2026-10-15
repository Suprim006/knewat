import type { NodeDescription } from '../../lib/graphController';
import { labelColor } from '../../lib/labels';

/** Node search: the input and, once something is typed, the match count with the first few hits. */
export function SearchBox({
  query,
  onQuery,
  matchCount,
  matches,
  onJump,
}: {
  query: string;
  onQuery: (q: string) => void;
  matchCount: number;
  matches: NodeDescription[];
  onJump: (id: string) => void;
}) {
  return (
    <div className="search">
      <input
        type="search"
        placeholder="Search nodes (name, text, value)…"
        aria-label="Search nodes"
        value={query}
        onChange={(e) => onQuery(e.target.value)}
      />
      {query.trim() && (
        <div className="search-results" aria-live="polite">
          <div className="muted">
            {matchCount} match{matchCount === 1 ? '' : 'es'}
          </div>
          <ul>
            {matches.map((d) => (
              <li key={d.id}>
                <button type="button" className="link" onClick={() => onJump(d.id)}>
                  <span className="dot" style={{ background: labelColor(d.label) }} />
                  {d.name}
                  <span className="muted"> · {d.label}</span>
                </button>
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}
