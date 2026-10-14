import { useCallback, useMemo, useState } from 'react';
import { Link, useNavigate, useParams } from 'react-router-dom';
import { ApiError } from '../api';
import type { WhyFact } from '../api';
import { useApi, useTenant } from '../app/context';
import { WhyGraph } from '../components/WhyGraph';
import { formatProp, labelColor, displayName } from '../lib/labels';
import { useAsync } from '../lib/useAsync';
import { layoutWhy, pathTo } from '../lib/whyLayout';
import type { Props } from '../api';

const LATEST = 'latest';

function describeError(e: Error): string {
  if (e instanceof ApiError) {
    if (e.status === 404) return 'No Decision or Fact with this id exists in this tenant.';
    if (e.status === 501) return 'Lineage is not installed in this deployment, so “why” is unavailable.';
  }
  return e.message;
}

function factFlags(f: WhyFact): string[] {
  const flags: string[] = [];
  if (f.superseded_by.length > 0) flags.push('superseded');
  if (f.contradicted_by.length > 0) flags.push('contradicted');
  if (f.contradicts.length > 0) flags.push('contradicts another fact');
  if (f.supersedes.length > 0) flags.push('supersedes an older fact');
  return flags;
}

export function Why() {
  const api = useApi();
  const { tenant } = useTenant();
  const { id: routeId = LATEST } = useParams();
  const navigate = useNavigate();
  const [sel, setSel] = useState<{ subject: string; id: string } | null>(null);

  /* candidates for the picker, newest first; also resolves /why/latest */
  const loadCandidates = useCallback(
    () =>
      tenant ? api.graph(tenant, { labels: ['Decision', 'Fact'], limit: 100 }) : Promise.resolve(undefined),
    [api, tenant],
  );
  const candidates = useAsync(loadCandidates);
  const options = useMemo(
    () =>
      (candidates.data?.nodes ?? []).map((n) => ({
        id: n.id,
        label: n.label,
        text: displayName(n.label, n.props),
      })),
    [candidates.data],
  );
  const latest = options.find((o) => o.label === 'Decision') ?? options[0];
  const subject = routeId === LATEST ? (latest?.id ?? null) : routeId;

  const loadWhy = useCallback(
    () => (tenant && subject ? api.why(tenant, subject) : Promise.resolve(undefined)),
    [api, tenant, subject],
  );
  const why = useAsync(loadWhy);
  const result = why.data?.result;
  const layout = useMemo(() => (result ? layoutWhy(result) : null), [result]);

  const selectedId = sel && sel.subject === subject ? sel.id : null;
  const highlight = useMemo(
    () => (result && selectedId ? pathTo(result, selectedId) : null),
    [result, selectedId],
  );
  const selectedNode = result?.nodes.find((n) => n.id === selectedId) ?? null;

  const waiting = !tenant || (routeId === LATEST && candidates.loading);
  const nothing = routeId === LATEST && !candidates.loading && !latest;

  return (
    <section className="page why" aria-labelledby="why-h">
      <h1 id="why-h">Why</h1>
      <p className="muted">
        The provenance behind a decision or fact, read from the graph:{' '}
        <b>decision → facts → agents, steps and sources</b>. Click a node to light up the path that leads to
        it.
      </p>

      <label className="inline why-picker">
        Explain
        <select
          aria-label="Decision or fact to explain"
          value={options.some((o) => o.id === subject) ? (subject ?? '') : ''}
          onChange={(e) => navigate(`/why/${encodeURIComponent(e.target.value)}`)}
        >
          {!options.some((o) => o.id === subject) && <option value="">{subject ? subject : '—'}</option>}
          {options.map((o) => (
            <option key={o.id} value={o.id}>
              {o.label}: {o.text}
            </option>
          ))}
        </select>
      </label>

      {waiting && <p className="muted">Loading…</p>}
      {nothing && (
        <p className="muted">
          No decisions or facts in this tenant yet. Once an agent records one, it shows up here.
        </p>
      )}
      {why.error && (
        <div className="banner error" role="alert">
          {describeError(why.error)}
        </div>
      )}
      {why.loading && subject && !why.error && <p className="muted">Tracing {subject}…</p>}

      {result && layout && (
        <>
          <div className="stat-row why-stats" data-testid="why-summary">
            <div className="stat">
              <div className="stat-n">{result.facts.length}</div>
              <div className="stat-l">facts</div>
            </div>
            <div className="stat">
              <div className="stat-n">{result.agents.length}</div>
              <div className="stat-l">agents</div>
            </div>
            <div className="stat">
              <div className="stat-n">{result.steps.length}</div>
              <div className="stat-l">steps</div>
            </div>
            <div className="stat">
              <div className="stat-n">{result.sources.length}</div>
              <div className="stat-l">sources</div>
            </div>
            <div className="stat">
              <div className="stat-n">{result.paths.length}</div>
              <div className="stat-l">paths</div>
            </div>
          </div>
          {result.truncated && (
            <p className="banner">The trail was cut off at the server’s limit; some evidence is not shown.</p>
          )}
          <WhyGraph
            layout={layout}
            selected={selectedId}
            highlight={highlight}
            onSelect={(id) => setSel({ subject: subject!, id })}
          />

          <div className="two-col why-below">
            <section className="panel" aria-labelledby="why-sel-h">
              <h2 id="why-sel-h">{selectedNode ? 'Selected node' : 'Root'}</h2>
              {(() => {
                const n = selectedNode ?? result.nodes.find((x) => x.id === result.root);
                if (!n) return null;
                return (
                  <>
                    <p>
                      <span className="chip" style={{ background: labelColor(n.label) }}>
                        {n.label}
                      </span>{' '}
                      <code>{n.id}</code>
                    </p>
                    <dl className="kv" data-testid="why-node-props">
                      {Object.entries(n.props).map(([k, v]) => (
                        <div key={k} className="kv-row">
                          <dt>{k}</dt>
                          <dd>{formatProp(k, v as Props[string])}</dd>
                        </div>
                      ))}
                    </dl>
                    {(n.label === 'Fact' || n.label === 'Decision') && n.id !== result.root && (
                      <Link to={`/why/${encodeURIComponent(n.id)}`}>
                        Explain this {n.label.toLowerCase()} →
                      </Link>
                    )}
                  </>
                );
              })()}
            </section>
            <section className="panel" aria-labelledby="why-facts-h">
              <h2 id="why-facts-h">Facts it rests on</h2>
              <ul className="fact-list" data-testid="why-facts">
                {result.facts.map((f) => (
                  <li key={f.id}>
                    <button
                      type="button"
                      className="link"
                      onClick={() => setSel({ subject: subject!, id: f.id })}
                    >
                      {String(f.props.predicate ?? '')}: {String(f.props.value ?? '')}
                    </button>
                    {factFlags(f).map((x) => (
                      <span key={x} className="chip plain">
                        {x}
                      </span>
                    ))}
                    <div className="muted">
                      by {f.asserted_by.join(', ') || '—'} · {f.sources.length} source
                      {f.sources.length === 1 ? '' : 's'}
                    </div>
                  </li>
                ))}
                {result.facts.length === 0 && (
                  <li className="muted">None: this node rests on no recorded facts.</li>
                )}
              </ul>
            </section>
          </div>
        </>
      )}
    </section>
  );
}
