import { useCallback, useState } from 'react';
import type { KeyboardEvent } from 'react';
import type { CypherResult, CypherValue } from '../api';
import { useApi, useTenant } from '../app/context';
import { ErrorBanner } from '../components/ErrorBanner';
import { compact, valueKind } from '../lib/cypherValue';

const EXAMPLES: { label: string; query: string }[] = [
  {
    label: 'Nodes per label',
    query: 'MATCH (n) RETURN labels(n)[0] AS label, count(*) AS n ORDER BY n DESC',
  },
  {
    label: 'Facts',
    query: 'MATCH (f:Fact) RETURN f.id, f.predicate, f.value LIMIT 25',
  },
  {
    label: 'Edges per type',
    query: 'MATCH ()-[r]->() RETURN type(r) AS type, count(*) AS n ORDER BY n DESC',
  },
  { label: 'Labels', query: 'CALL db.labels()' },
  {
    label: '2-hop path',
    query: 'MATCH p = (a:Agent)-[*2]->(x) RETURN p LIMIT 10',
  },
];

const STORAGE_KEY = 'knewat-view.cypher.last';

function loadLast(): string {
  try {
    return sessionStorage.getItem(STORAGE_KEY) ?? EXAMPLES[0]!.query;
  } catch {
    return EXAMPLES[0]!.query;
  }
}

function Cell({ value }: { value: CypherValue }) {
  const kind = valueKind(value);
  if (kind === 'null') return <span className="null">null</span>;
  if (kind === 'scalar') return <>{String(value)}</>;
  const json = JSON.stringify(value, null, 2);
  return (
    <details>
      <summary title={json}>{compact(value)}</summary>
      <pre>{json}</pre>
    </details>
  );
}

export function CypherConsole() {
  const api = useApi();
  const { tenant } = useTenant();
  const [query, setQuery] = useState(loadLast);
  const [busy, setBusy] = useState(false);
  const [result, setResult] = useState<CypherResult>();
  const [error, setError] = useState<string>();

  const canRun = !busy && query.trim() !== '' && tenant !== '';

  const run = useCallback(async () => {
    if (!canRun) return;
    setBusy(true);
    setError(undefined);
    try {
      sessionStorage.setItem(STORAGE_KEY, query);
    } catch {
      // storage unavailable: not essential
    }
    try {
      setResult(await api.cypher(tenant, query));
    } catch (e) {
      setResult(undefined);
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }, [api, tenant, query, canRun]);

  const onKeyDown = (e: KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === 'Enter' && (e.ctrlKey || e.metaKey)) {
      e.preventDefault();
      void run();
    }
  };

  return (
    <section className="page cypher-console">
      <h1>
        Cypher <span className="muted">· tenant {tenant || '…'}</span>
      </h1>
      <p className="muted">Read-only: writes are rejected. Ctrl/Cmd+Enter runs the query.</p>
      <div className="cypher-examples" role="group" aria-label="Example queries">
        {EXAMPLES.map((ex) => (
          <button key={ex.label} type="button" className="btn small" onClick={() => setQuery(ex.query)}>
            {ex.label}
          </button>
        ))}
      </div>
      <textarea
        className="cypher-input"
        aria-label="Cypher query"
        spellCheck={false}
        value={query}
        onChange={(e) => setQuery(e.target.value)}
        onKeyDown={onKeyDown}
      />
      <div className="cypher-actions">
        <button type="button" className="btn" onClick={() => void run()} disabled={!canRun}>
          {busy ? 'Running…' : 'Run'}
        </button>
        {result && (
          <span role="status" data-testid="cypher-status">
            {result.row_count} {result.row_count === 1 ? 'row' : 'rows'} · {result.run_time_ms} ms
          </span>
        )}
      </div>
      {error && <ErrorBanner>{error}</ErrorBanner>}
      {result?.truncated && (
        <p className="banner" role="status">
          Result truncated at 500 rows.
        </p>
      )}
      {result && (
        <div className="cypher-table-wrap">
          <table className="cypher-table" aria-label="Query result">
            <thead>
              <tr>
                {result.columns.map((c, i) => (
                  <th key={`${c}-${i}`} scope="col">
                    {c}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {result.rows.map((row, r) => (
                <tr key={r}>
                  {row.map((v, c) => (
                    <td key={c}>
                      <Cell value={v} />
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </section>
  );
}
