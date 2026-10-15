import { useState } from 'react';
import { fmt, fmtMs } from '../../lib/format';
import { medianComparison, peakPoints } from '../../lib/results';
import type { ParsedResults, L4Sweep } from '../../lib/results';
import { Bars } from './Bars';
import { StringList } from './StringList';

/**
 * Who is fastest on the median, computed from the file. Shown for every load level, including the ones where a
 * baseline beats Plexus: the page does not choose which comparison to print.
 */
function MedianCallout({ sweep, op }: { sweep: L4Sweep; op: string }) {
  const rows = medianComparison(sweep, op);
  if (rows.length === 0 || sweep.points.every((p) => p.arm === rows[0]!.fastest.arm)) return null;
  return (
    <div className="median-callout" data-testid={`median-${sweep.key}`}>
      <b>
        Fastest median {op} per {sweep.xLabel.replace(/s$/, '')} count
      </b>
      <ul>
        {rows.map((r) => (
          <li key={r.x} data-testid={`median-${sweep.key}-${r.x}`}>
            <b>{r.x}</b>: {r.fastest.arm} {fmtMs(r.fastest.p50)} (p99 {fmtMs(r.fastest.p99)})
            {r.plexus && r.fastest.arm !== r.plexus.arm && (
              <>
                {' '}
                · Plexus {r.plexus.arm} {fmtMs(r.plexus.p50)} (p99 {fmtMs(r.plexus.p99)})
                {r.ratio !== undefined && ` · ${fmt(r.ratio)}× the fastest median`}
              </>
            )}
            {r.plexus && r.fastest.arm === r.plexus.arm && <> · Plexus is fastest</>}
          </li>
        ))}
      </ul>
    </div>
  );
}

function SweepSection({ sweep }: { sweep: L4Sweep }) {
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
      <MedianCallout sweep={sweep} op={op} />
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

/** L4: one block per sweep, the embedder probe and the notes on how it was measured. */
export function L4Section({ r }: { r: ParsedResults }) {
  if (r.l4.length === 0) return null;
  return (
    <section className="result-block" aria-labelledby="l4-h" data-testid="l4">
      <h2 id="l4-h">L4 · latency percentiles and throughput</h2>
      {r.l4.map((s) => (
        <SweepSection key={s.key} sweep={s} />
      ))}
      {r.embedderProbe.length > 0 && (
        <section className="result-block" data-testid="l4-embedder">
          <h3>Embedding latency (local bge-small, shared by recall)</h3>
          <ul className="inline-list">
            {r.embedderProbe.map((e) => (
              <li key={e.workers}>
                <b>{e.workers}</b> workers: p50 {fmtMs(e.p50)} · p95 {fmtMs(e.p95)} · p99 {fmtMs(e.p99)}
              </li>
            ))}
          </ul>
        </section>
      )}
      {r.l4Notes.length > 0 && (
        <div data-testid="l4-notes">
          <h3>Notes on how L4 was measured</h3>
          <StringList items={r.l4Notes} />
        </div>
      )}
    </section>
  );
}
