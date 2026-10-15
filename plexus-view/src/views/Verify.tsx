import { useCallback, useEffect, useRef } from 'react';
import { Link, useSearchParams } from 'react-router-dom';
import { ApiError } from '../api';
import type { DocRow, VerifyQueue, VerifyRow } from '../api';
import { useApi, useTenant } from '../app/context';
import { formatProp } from '../lib/labels';
import { SUSPECT_GLYPH } from '../lib/memory';
import { useAsync } from '../lib/useAsync';
import type { AsyncState } from '../lib/useAsync';

const DASH = '—';
const LIMIT = 200;

const isMissing = (e: Error | undefined): boolean => e instanceof ApiError && e.status === 404;

/** "not available on this server" for an API that predates P7; any other failure is an alert. */
function Failure({ what, error }: { what: string; error: Error }) {
  if (isMissing(error))
    return (
      <p className="muted">The {what} is not available on this server (it predates staleness tracking).</p>
    );
  return (
    <div className="banner error" role="alert">
      Could not load the {what}: {error.message}
    </div>
  );
}

function QueueRow({ row, current }: { row: VerifyRow; current: boolean }) {
  const ref = useRef<HTMLTableRowElement>(null);
  useEffect(() => {
    if (current) ref.current?.scrollIntoView?.({ block: 'center' });
  }, [current]);
  const suspect = row.verify_state === 'suspect';
  return (
    <tr
      ref={ref}
      data-testid={`verify-row-${row.fact_id}`}
      className={current ? 'highlight' : undefined}
      aria-current={current ? 'true' : undefined}
    >
      <th scope="row" className="fact-cell">
        <span className="muted">{row.entity || '?'} · </span>
        {row.predicate} = <b>{row.value}</b> <Link to={`/why/${encodeURIComponent(row.fact_id)}`}>Why?</Link>
        {row.anchors.length > 0 && (
          <ul className="anchors" aria-label="Anchors">
            {row.anchors.map((a) => (
              <li key={a}>
                <code>{a}</code>
              </li>
            ))}
          </ul>
        )}
      </th>
      <td data-testid="verify-state">
        {suspect ? `${SUSPECT_GLYPH} suspect` : 'review date'}
        {suspect && row.suspect_since > 0 && (
          <div className="muted">since {formatProp('suspect_since', row.suspect_since)}</div>
        )}
      </td>
      <td data-testid="verify-reason">
        {row.reason}
        {row.change && (
          <div className="muted">
            commit <code>{row.change.commit || 'working tree'}</code> · {formatProp('at', row.change.at)}
          </div>
        )}
      </td>
      <td className="num" data-testid="verify-decisions">
        {row.decisions_count}
      </td>
      <td className="num" data-testid="verify-activation">
        {typeof row.activation === 'number' ? row.activation.toFixed(2) : DASH}
        {row.protected && <span className="muted"> protected</span>}
      </td>
    </tr>
  );
}

function DocCard({ doc }: { doc: DocRow }) {
  return (
    <article className="card wide" data-testid="doc-row">
      <header>
        <strong>{doc.title || doc.uri}</strong>
        <span className="muted">latest change {formatProp('at', doc.latest)}</span>
      </header>
      <div className="mono muted">{doc.uri}</div>
      <ul>
        {doc.changes.map((c) => (
          <li key={`${c.change_id}${c.anchor}`}>
            <code>{c.commit || 'working tree'}</code> changed <code>{c.anchor}</code>
            {c.paths.length > 0 && <span className="muted"> · {c.paths.join(', ')}</span>}
            <span className="muted"> · {formatProp('at', c.at)}</span>
          </li>
        ))}
      </ul>
    </article>
  );
}

function QueueSection({ queue, current }: { queue: AsyncState<VerifyQueue | undefined>; current: string }) {
  return (
    <section aria-labelledby="vq-h" className="panel">
      <h2 id="vq-h">Facts to verify</h2>
      {queue.error && <Failure what="verify queue" error={queue.error} />}
      {queue.loading && <p className="muted">Loading the verify queue…</p>}
      {queue.data && queue.data.rows.length === 0 && (
        <p className="muted">No fact needs verification: nothing is suspect and no review date has passed.</p>
      )}
      {queue.data && queue.data.rows.length > 0 && (
        <table className="verify-table">
          <caption className="sr-only">
            Facts to re-check, most decisions at risk first, then most active
          </caption>
          <thead>
            <tr>
              <th scope="col">Fact</th>
              <th scope="col">State</th>
              <th scope="col">Reason</th>
              <th scope="col" className="num">
                Decisions at risk
              </th>
              <th scope="col" className="num">
                Activation
              </th>
            </tr>
          </thead>
          <tbody>
            {queue.data.rows.map((r) => (
              <QueueRow key={r.fact_id} row={r} current={r.fact_id === current} />
            ))}
          </tbody>
        </table>
      )}
    </section>
  );
}

/**
 * Read-only staleness page: the verify queue (`/verify-queue`) and the docs behind their code
 * (`/docs-to-update`). Re-checking a fact is done by an agent with the `verify_fact` tool, never here.
 */
export function Verify() {
  const api = useApi();
  const { tenant, empty: noTenants } = useTenant();
  const [params] = useSearchParams();
  const current = params.get('fact') ?? '';

  const loadQueue = useCallback(
    () => (tenant ? api.verifyQueue(tenant, { limit: LIMIT }) : Promise.resolve(undefined)),
    [api, tenant],
  );
  const loadDocs = useCallback(
    () => (tenant ? api.docsToUpdate(tenant, { limit: LIMIT }) : Promise.resolve(undefined)),
    [api, tenant],
  );
  const queue = useAsync(loadQueue);
  const docs = useAsync(loadDocs);

  return (
    <section className="page verify">
      <h1>Verify</h1>
      <p className="muted">
        Facts an agent should re-check before relying on them, and docs that describe code which has changed
        since they were written. The viewer never writes: an agent confirms or corrects a fact with the{' '}
        <code>verify_fact</code> tool.
      </p>
      {!tenant && (
        <p className="muted">
          {noTenants ? 'No tenants yet, so there is nothing to verify.' : 'Waiting for tenants…'}
        </p>
      )}
      {tenant && (
        <>
          <QueueSection queue={queue} current={current} />
          <section aria-labelledby="docs-h" className="panel">
            <h2 id="docs-h">Docs to update</h2>
            {docs.error && <Failure what="docs list" error={docs.error} />}
            {docs.loading && <p className="muted">Loading docs…</p>}
            {docs.data && docs.data.docs.length === 0 && (
              <p className="muted">No doc is behind its code: nothing has changed under a described file.</p>
            )}
            {docs.data && docs.data.docs.length > 0 && (
              <div className="cards">
                {docs.data.docs.map((d) => (
                  <DocCard key={d.source_id} doc={d} />
                ))}
              </div>
            )}
          </section>
        </>
      )}
    </section>
  );
}
