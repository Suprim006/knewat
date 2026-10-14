import { useCallback, useEffect, useState } from 'react';
import { useLocation } from 'react-router-dom';
import { ApiError } from '../api';
import { useApi } from '../app/context';
import { parseResults, peakPoints } from '../lib/results';
import type { L4Sweep, ParsedResults } from '../lib/results';
import { useAsync } from '../lib/useAsync';

const fmt = (n: number): string => (Number.isInteger(n) ? String(n) : n.toFixed(n < 10 ? 2 : 1));

function Bars({
  rows,
  unit,
  max,
}: {
  rows: { key: string; label: string; value: number; tone?: string }[];
  unit: string;
  max?: number;
}) {
  const top = max ?? Math.max(1, ...rows.map((r) => r.value));
  return (
    <ul className="bars-chart">
      {rows.map((r) => (
        <li key={r.key} data-testid={`bar-${r.key}`}>
          <span className="bar-label">{r.label}</span>
          <span className="bar-track" aria-hidden="true">
            <span
              className={`bar-fill-h ${r.tone ?? ''}`}
              style={{ width: `${Math.max(1.5, (r.value / top) * 100)}%` }}
            />
          </span>
          <span className="bar-value">
            {fmt(r.value)}
            {unit}
          </span>
        </li>
      ))}
    </ul>
  );
}

function L4Section({ sweep }: { sweep: L4Sweep }) {
  const [op, setOp] = useState(sweep.ops[0] ?? '');
  const xs = [...new Set(sweep.points.map((p) => p.x))].sort((a, b) => a - b);
  const arms = [...new Set(sweep.points.map((p) => p.arm))];
  const at = (arm: string, x: number) => sweep.points.find((p) => p.arm === arm && p.x === x);
  const peak = peakPoints(sweep);
  const peakX = Math.max(...peak.map((p) => p.x));
  const chartRows = peak
    .filter((p) => p.ops[op])
    .flatMap((p) => [
      { key: `${sweep.key}-${p.arm}-p50`, label: `${p.arm} p50`, value: p.ops[op]!.client.p50, tone: 'p50' },
      { key: `${sweep.key}-${p.arm}-p95`, label: `${p.arm} p95`, value: p.ops[op]!.client.p95, tone: 'p95' },
      { key: `${sweep.key}-${p.arm}-p99`, label: `${p.arm} p99`, value: p.ops[op]!.client.p99, tone: 'p99' },
    ]);
  return (
    <section className="result-block" aria-labelledby={`l4-${sweep.key}`} data-testid={`l4-${sweep.key}`}>
      <h3 id={`l4-${sweep.key}`}>{sweep.title}</h3>
      {sweep.ops.length > 1 && (
        <label className="inline">
          Operation
          <select
            aria-label={`Operation for ${sweep.title}`}
            value={op}
            onChange={(e) => setOp(e.target.value)}
          >
            {sweep.ops.map((o) => (
              <option key={o} value={o}>
                {o}
              </option>
            ))}
          </select>
        </label>
      )}
      <p className="muted">
        Client latency p50 / p95 / p99 in ms (server-side run time below when reported).
      </p>
      <div className="table-scroll">
        <table className="data">
          <thead>
            <tr>
              <th>Arm</th>
              {xs.map((x) => (
                <th key={x}>
                  {x} {sweep.xLabel}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {arms.map((arm) => (
              <tr key={arm}>
                <th scope="row">{arm}</th>
                {xs.map((x) => {
                  const o = at(arm, x)?.ops[op];
                  return (
                    <td key={x} className="mono">
                      {o ? `${fmt(o.client.p50)} / ${fmt(o.client.p95)} / ${fmt(o.client.p99)}` : '-'}
                      {o?.server && (
                        <div className="muted">
                          srv {fmt(o.server.p50)} / {fmt(o.server.p95)} / {fmt(o.server.p99)}
                        </div>
                      )}
                    </td>
                  );
                })}
              </tr>
            ))}
            <tr>
              <th scope="row">ops/s</th>
              {xs.map((x) => (
                <td key={x} className="mono muted">
                  {arms
                    .map((a) => at(a, x))
                    .filter((p) => p?.throughput !== undefined)
                    .map((p) => `${p!.arm} ${fmt(p!.throughput!)}`)
                    .join(' · ') || '-'}
                </td>
              ))}
            </tr>
          </tbody>
        </table>
      </div>
      {chartRows.length > 0 && (
        <>
          <h4>
            {op} latency at {peakX} {sweep.xLabel}
          </h4>
          <Bars rows={chartRows} unit=" ms" />
        </>
      )}
    </section>
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
      {r.run && (
        <p className="muted" data-testid="run-meta">
          Run <code>{r.run.id}</code> · {r.run.startedAt}
          {r.run.durationS !== undefined && ` · ${Math.round(r.run.durationS)} s`} ·{' '}
          {r.run.quick ? <b>quick run (CI sizing), not the published figures</b> : 'full run'} · layers{' '}
          {r.run.layers.join(', ')}
        </p>
      )}
      {r.headline.length > 0 && (
        <ul className="headline" aria-label="Headline">
          {r.headline.map((h) => (
            <li key={h}>{h}</li>
          ))}
        </ul>
      )}

      {r.l1 && (
        <section className="result-block" aria-labelledby="l1-h" data-testid="l1">
          <h2 id="l1-h">L1 · correctness under concurrency</h2>
          <p className="muted">Violation counts are summed over every run: counts, not averages.</p>
          <div className="table-scroll">
            <table className="data">
              <thead>
                <tr>
                  <th>Test</th>
                  <th>Pass bar</th>
                  {r.l1.arms.map((a) => (
                    <th key={a} title={armLabel(a)}>
                      {a}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {r.l1.rows.map((row) => (
                  <tr key={row.id}>
                    <th scope="row">
                      {row.id} · {row.title}
                    </th>
                    <td>{row.bar}</td>
                    {row.cells.map((c) => (
                      <td key={c.arm} className={`cell-${c.state}`} data-testid={`l1-${row.id}-${c.arm}`}>
                        {c.text}
                      </td>
                    ))}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>
      )}

      {r.l2 && (
        <section className="result-block" aria-labelledby="l2-h" data-testid="l2">
          <h2 id="l2-h">L2 · provenance questions, accuracy per arm</h2>
          <Bars
            unit="%"
            max={100}
            rows={r.l2.map((x) => ({
              key: `l2-${x.arm}`,
              label: armLabel(x.arm),
              value: x.accuracy,
              tone: x.arm === 'P' ? 'p99' : 'p50',
            }))}
          />
          <div className="table-scroll">
            <table className="data">
              <thead>
                <tr>
                  <th>Arm</th>
                  <th>Exact-match accuracy</th>
                  <th>Questions</th>
                </tr>
              </thead>
              <tbody>
                {r.l2.map((x) => (
                  <tr key={x.arm}>
                    <th scope="row">{armLabel(x.arm)}</th>
                    <td>{fmt(x.accuracy)}%</td>
                    <td>{x.n ?? '-'}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>
      )}

      {r.l4.length > 0 && (
        <section className="result-block" aria-labelledby="l4-h" data-testid="l4">
          <h2 id="l4-h">L4 · latency percentiles and throughput</h2>
          {r.l4.map((s) => (
            <L4Section key={s.key} sweep={s} />
          ))}
        </section>
      )}

      {r.ablation && (
        <section className="result-block" id="ablation" aria-labelledby="abl-h" data-testid="ablation">
          <h2 id="abl-h">Ablation · what breaks without the edges</h2>
          <p className="muted">
            Edges actually deleted from the graph ({r.ablation.stripped.join(', ')}), then each capability
            re-probed. Controls do not use those edges and should be unaffected.
          </p>
          <ul className="inline-list">
            {r.ablation.summary.map((s) => (
              <li key={s.label}>
                <b>{s.value}</b> {s.label}
              </li>
            ))}
          </ul>
          <div className="table-scroll">
            <table className="data">
              <thead>
                <tr>
                  <th>Capability</th>
                  <th>Needs</th>
                  <th>Intact</th>
                  <th>Edges removed</th>
                </tr>
              </thead>
              <tbody>
                {r.ablation.capabilities.map((c) => (
                  <tr key={c.capability} className={c.breaks ? 'row-broken' : undefined}>
                    <th scope="row">{c.capability}</th>
                    <td>{c.needs}</td>
                    <td className={c.intactPass ? 'cell-pass' : 'cell-fail'}>
                      {c.intactPass ? 'pass' : 'FAIL'}
                    </td>
                    <td className={c.ablatedPass ? 'cell-pass' : 'cell-fail'}>
                      {c.ablatedPass ? 'pass' : 'FAIL'}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          {r.ablation.l1.length > 0 && (
            <table className="data">
              <thead>
                <tr>
                  <th>L1 re-run</th>
                  <th>Arm</th>
                  <th>Violations</th>
                </tr>
              </thead>
              <tbody>
                {r.ablation.l1.map((x) => (
                  <tr key={`${x.arm}-${x.test}`}>
                    <th scope="row">{x.test}</th>
                    <td>{x.arm}</td>
                    <td>{x.violations}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </section>
      )}

      {r.honesty.length > 0 && (
        <section className="result-block" aria-labelledby="honesty-h">
          <h2 id="honesty-h">Limits and honesty notes</h2>
          <ul>
            {r.honesty.map((h) => (
              <li key={h}>{h}</li>
            ))}
          </ul>
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
