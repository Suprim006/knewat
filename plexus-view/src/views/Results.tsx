import { useCallback, useEffect } from 'react';
import { useLocation } from 'react-router-dom';
import { ApiError } from '../api';
import { useApi } from '../app/context';
import { parseResults } from '../lib/results';
import type { ParsedResults } from '../lib/results';
import { useAsync } from '../lib/useAsync';
import { AblationSection } from './results/AblationSection';
import { L1Section } from './results/L1Section';
import { L2Section } from './results/L2Section';
import { L4Section } from './results/L4Section';
import { StringList } from './results/StringList';

function RunMeta({ run }: { run: NonNullable<ParsedResults['run']> }) {
  return (
    <p className="muted" data-testid="run-meta">
      Run <code>{run.id}</code> · {run.startedAt}
      {run.durationS !== undefined && ` · ${Math.round(run.durationS)} s`} ·{' '}
      {run.quick ? <b>quick run (CI sizing), not the published figures</b> : 'full run'} · layers{' '}
      {run.layers.join(', ')}
    </p>
  );
}

function Content({ r }: { r: ParsedResults }) {
  const { hash } = useLocation();
  useEffect(() => {
    if (hash) document.getElementById(hash.slice(1))?.scrollIntoView?.();
  }, [hash]);
  const armLabel = (id: string) => r.arms.find((a) => a.id === id)?.label ?? id;
  return (
    <>
      {r.run && <RunMeta run={r.run} />}
      {r.headline.length > 0 && <StringList items={r.headline} className="headline" ariaLabel="Headline" />}

      {r.l1 && <L1Section l1={r.l1} armLabel={armLabel} />}

      {r.l2 && <L2Section rows={r.l2} info={r.l2Info} armLabel={armLabel} kind="l2" />}
      {r.l2Scale && <L2Section rows={r.l2Scale} info={r.l2ScaleInfo} armLabel={armLabel} kind="l2scale" />}

      <L4Section r={r} />

      {r.ablation && <AblationSection ablation={r.ablation} />}

      {r.honesty.length > 0 && (
        <section className="result-block" aria-labelledby="honesty-h">
          <h2 id="honesty-h">Limits and honesty notes</h2>
          <StringList items={r.honesty} />
        </section>
      )}
      {r.unknown.length > 0 && <p className="muted">Not drawn here: {r.unknown.join(', ')}.</p>}
    </>
  );
}

export function Results() {
  const api = useApi();
  const load = useCallback(() => api.results(), [api]);
  const res = useAsync(load);
  const missing = res.error instanceof ApiError && res.error.status === 404;
  const parsed = res.data ? parseResults(res.data) : null;
  const empty =
    parsed &&
    !parsed.l1 &&
    !parsed.l2 &&
    !parsed.l2Scale &&
    parsed.l4.length === 0 &&
    !parsed.ablation &&
    parsed.headline.length === 0;

  return (
    <section className="page results" aria-labelledby="res-h">
      <h1 id="res-h">Results</h1>
      <p className="muted">
        The Crucible benchmark: Files, SQLite, Vector and Plexus on the same tool interface. Read from{' '}
        <code>/api/results</code>.
      </p>
      {res.loading && <p className="muted">Loading results…</p>}
      {missing && (
        <div className="placeholder" data-testid="results-placeholder">
          <h2>No Crucible results yet</h2>
          <p>
            The results file appears after a benchmark run (<code>uv run crucible all --quick</code>); point
            the API at it with <code>PLEXUS_RESULTS_PATH</code>. Until then this page has nothing to show, and
            nothing here is estimated.
          </p>
        </div>
      )}
      {res.error && !missing && (
        <div className="banner error" role="alert">
          Could not load the results: {res.error.message}
        </div>
      )}
      {empty && <p className="muted">The results file has no layers this page knows how to draw.</p>}
      {parsed && !empty && <Content r={parsed} />}
      {parsed && empty && (
        <details>
          <summary>Raw JSON</summary>
          <pre className="cypher">{JSON.stringify(res.data, null, 2)}</pre>
        </details>
      )}
    </section>
  );
}
