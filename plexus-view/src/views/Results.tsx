import { useCallback, useEffect, useState } from 'react';
import { useLocation } from 'react-router-dom';
import { ApiError } from '../api';
import { useApi } from '../app/context';
import { intervalsOverlap, medianComparison, parseResults, peakPoints, signTest } from '../lib/results';
import type { L2Info, L2Row, L4Sweep, ParsedResults } from '../lib/results';
import { useAsync } from '../lib/useAsync';

const fmt = (n: number): string => (Number.isInteger(n) ? String(n) : n.toFixed(n < 10 ? 2 : 1));
const fmtUsd = (n: number): string => `$${n.toFixed(n < 1 ? 3 : 2)}`;
const fmtMs = (n: number): string => (n >= 1000 ? `${(n / 1000).toFixed(2)} s` : `${fmt(n)} ms`);
const fmtInt = (n: number): string => Math.round(n).toLocaleString('en-US');

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

function costText(x: L2Row): string {
  if (x.costUsd === undefined) return '-';
  return x.costUsd === 0
    ? '$0 (no LLM)'
    : `${fmtUsd(x.costUsd)} (${fmtUsd(x.costPerQuestionUsd ?? 0)} / question)`;
}

const STRATA = ['early', 'middle', 'late'];

function pFmt(p: number): string {
  return p < 0.001 ? '< 0.001' : p.toFixed(3);
}

/** What only the scale run has: how big the history is, strata, failure analysis, intervals and the paired sign test. */
function ScaleExtras({
  rows,
  info,
  armLabel,
}: {
  rows: L2Row[];
  info: L2Info;
  armLabel: (id: string) => string;
}) {
  const p = rows.find((x) => x.arm === 'P');
  const baselines = rows.filter((x) => x.arm !== 'P');
  const h = info.history;
  return (
    <>
      {h && (
        <p className="muted" data-testid="l2scale-history">
          History: {h.sprints ?? '?'} sprints of one team (
          {Object.entries(h.scenario)
            .filter(([k]) => ['tasks', 'decisions', 'handoffs', 'facts'].includes(k))
            .map(([k, v]) => `${v} ${k}`)
            .join(', ')}
          ). Whole history as the arm sees it:{' '}
          {Object.entries(h.artifactChars)
            .map(
              ([arm, c]) =>
                `${arm} ${fmtInt(c)} chars${h.overBudget[arm] !== undefined ? ` (${fmt(h.overBudget[arm]!)}× the cap)` : ''}`,
            )
            .join(' · ')}
          . Every question names one sprint; sprints 1-6 are “early”, 7-14 “middle”, 15-20 “late”.
        </p>
      )}
      {p && baselines.some((b) => b.questions) && (
        <div data-testid="l2scale-significance">
          <h3>Is Plexus’s lead real? Intervals and a paired sign test</h3>
          <div className="table-scroll">
            <table className="data">
              <thead>
                <tr>
                  <th>Plexus vs</th>
                  <th>Questions only Plexus got right</th>
                  <th>Questions only the baseline got right</th>
                  <th>Paired sign test p (exact, two-sided)</th>
                  <th>Wilson intervals overlap?</th>
                </tr>
              </thead>
              <tbody>
                {baselines.map((b) => {
                  const t = signTest(p, b);
                  const ov = intervalsOverlap(p.wilson, b.wilson);
                  return (
                    <tr key={b.arm} data-testid={`l2scale-sign-${b.arm}`}>
                      <th scope="row">{armLabel(b.arm)}</th>
                      <td>{t ? t.aOnly : '-'}</td>
                      <td>{t ? t.bOnly : '-'}</td>
                      <td className="mono">
                        {t ? `${pFmt(t.p)}${t.p >= 0.05 ? ' (not distinguishable from noise)' : ''}` : '-'}
                      </td>
                      <td>{ov === undefined ? '-' : ov ? 'yes' : 'no'}</td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
          <p className="muted" data-testid="l2scale-caveat">
            Computed here from the per-question results in the file. The sign test uses only the questions
            where exactly one of the two arms was right, so it is a small sample ({p.n ?? '?'} questions, one
            run each, one model, one synthetic scenario family). {baselines.length} comparisons are shown
            without any correction for that. Overlapping intervals and a p-value above 0.05 mean the gap is
            not distinguishable from sampling noise with this many questions; a gap with a small p-value is
            suggestive, not proof. The honesty notes below say which choices favour the baselines and which
            favour Plexus.
          </p>
        </div>
      )}
      {rows.some((x) => x.byStratum) && (
        <details>
          <summary>Accuracy by position of the asked sprint (early / middle / late)</summary>
          <div className="table-scroll">
            <table className="data" data-testid="l2scale-strata">
              <thead>
                <tr>
                  <th>Arm</th>
                  {STRATA.map((k) => (
                    <th key={k}>{k}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {rows.map((x) => (
                  <tr key={x.arm}>
                    <th scope="row">{armLabel(x.arm)}</th>
                    {STRATA.map((k) => (
                      <td key={k}>
                        {x.byStratum?.[k] ? `${x.byStratum[k]!.correct}/${x.byStratum[k]!.total}` : '-'}
                      </td>
                    ))}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </details>
      )}
      {rows.some((x) => x.failure) && (
        <details>
          <summary>Why the baselines were wrong (counts; the report has each case)</summary>
          <div className="table-scroll">
            <table className="data" data-testid="l2scale-failures">
              <thead>
                <tr>
                  <th>Arm</th>
                  <th>Wrong</th>
                  <th>of which unparseable</th>
                  <th>Wrong, all evidence was in the context</th>
                  <th>Wrong, evidence partly or wholly missing</th>
                  <th>Shown lines from the asked sprint (median)</th>
                </tr>
              </thead>
              <tbody>
                {rows
                  .filter((x) => x.failure)
                  .map((x) => (
                    <tr key={x.arm}>
                      <th scope="row">{armLabel(x.arm)}</th>
                      <td>{x.failure!.wrong}</td>
                      <td>{x.failure!.unparseable}</td>
                      <td>{x.failure!.wrongWithAllEvidence}</td>
                      <td>{x.failure!.wrongWithPartialOrNoEvidence}</td>
                      <td>
                        {x.failure!.medianShareFromAskedSprint !== undefined
                          ? `${Math.round(x.failure!.medianShareFromAskedSprint * 100)}%`
                          : '-'}
                      </td>
                    </tr>
                  ))}
              </tbody>
            </table>
          </div>
        </details>
      )}
      {info.plexusChanges.length > 0 && (
        <details data-testid="l2scale-changes">
          <summary>What was changed in the Plexus answerer for this run</summary>
          <ul>
            {info.plexusChanges.map((c) => (
              <li key={c}>{c}</li>
            ))}
          </ul>
        </details>
      )}
    </>
  );
}

function L2Section({
  rows,
  info,
  armLabel,
  kind,
}: {
  rows: L2Row[];
  info?: L2Info;
  armLabel: (id: string) => string;
  kind: 'l2' | 'l2scale';
}) {
  const scale = kind === 'l2scale';
  const detailed = rows.some((x) => x.tokensPerQuestion !== undefined);
  return (
    <section className="result-block" id={kind} aria-labelledby={`${kind}-h`} data-testid={kind}>
      <h2 id={`${kind}-h`}>
        {scale
          ? 'L2 at scale · the same questions over a history 10-17× the context cap'
          : 'L2 · provenance questions, accuracy per arm'}
      </h2>
      {info && (
        <p className="muted" data-testid={`${kind}-meta`}>
          {info.mode} run · {info.asked ?? '?'} of {info.total ?? '?'} questions · baselines are{' '}
          <code>claude -p</code> {info.model}
          {info.modelIds.length > 0 && ` (${info.modelIds.join(', ')})`}, no tools
          {info.contextBudgetChars !== undefined &&
            `, context capped at ${fmtInt(info.contextBudgetChars)} chars`}
          . Plexus answers with one hand-written Cypher statement per question family and no LLM.
        </p>
      )}
      <Bars
        unit="%"
        max={100}
        rows={rows.map((x) => ({
          key: `${kind}-${x.arm}`,
          label: armLabel(x.arm),
          value: x.accuracy,
          tone: x.arm === 'P' ? 'p99' : 'p50',
        }))}
      />
      <div className="table-scroll">
        <table className="data" data-testid={`${kind}-table`}>
          <thead>
            <tr>
              <th>Arm</th>
              <th>Exact-match accuracy</th>
              {rows.some((x) => x.wilson) && <th title="95% Wilson score interval">95% interval (Wilson)</th>}
              {detailed && (
                <>
                  <th title="Stricter variant: the reply must be nothing but the JSON object">
                    Whole-reply-JSON accuracy
                  </th>
                  <th>Tokens / question</th>
                  <th>LLM cost</th>
                  <th>Latency median / p95</th>
                </>
              )}
              <th>Questions</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((x) => (
              <tr key={x.arm} data-testid={`${kind}-row-${x.arm}`}>
                <th scope="row">
                  {armLabel(x.arm)}
                  {x.completed === false && <span className="muted"> (stopped early by the budget cap)</span>}
                </th>
                <td data-testid={`${kind}-acc-${x.arm}`}>
                  {fmt(x.accuracy)}%{x.correct !== undefined && x.n ? ` (${x.correct}/${x.n})` : ''}
                </td>
                {rows.some((y) => y.wilson) && (
                  <td className="mono" data-testid={`${kind}-wilson-${x.arm}`}>
                    {x.wilson ? `${fmt(x.wilson[0])}% – ${fmt(x.wilson[1])}%` : '-'}
                  </td>
                )}
                {detailed && (
                  <>
                    <td data-testid={`${kind}-whole-${x.arm}`}>
                      {x.wholeReplyPct !== undefined
                        ? `${fmt(x.wholeReplyPct)}%${x.wholeReplyCorrect !== undefined && x.n ? ` (${x.wholeReplyCorrect}/${x.n})` : ''}`
                        : '-'}
                    </td>
                    <td className="mono" data-testid={`${kind}-tokens-${x.arm}`}>
                      {x.tokensPerQuestion !== undefined ? fmtInt(x.tokensPerQuestion) : '-'}
                    </td>
                    <td className="mono" data-testid={`${kind}-cost-${x.arm}`}>
                      {costText(x)}
                    </td>
                    <td className="mono" data-testid={`${kind}-latency-${x.arm}`}>
                      {x.latencyMedianMs !== undefined
                        ? `${fmtMs(x.latencyMedianMs)} / ${x.latencyP95Ms !== undefined ? fmtMs(x.latencyP95Ms) : '-'}`
                        : '-'}
                    </td>
                  </>
                )}
                <td>{x.n ?? '-'}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {rows.some((x) => x.replyFormat) && (
        <p className="muted" data-testid={`${kind}-reply-format`}>
          Reply format (why the two accuracy columns differ):{' '}
          {rows
            .filter((x) => x.replyFormat)
            .map(
              (x) =>
                `${x.arm}: ${x.replyFormat!.jsonOnly} JSON-only, ${x.replyFormat!.proseThenJson} prose then JSON, ${x.replyFormat!.unparseable} unparseable`,
            )
            .join(' · ')}
          .
        </p>
      )}
      {info && info.families.length > 0 && (
        <details>
          <summary>Accuracy by question family</summary>
          <div className="table-scroll">
            <table className="data" data-testid={`${kind}-families`}>
              <thead>
                <tr>
                  <th>Family</th>
                  <th>n</th>
                  {rows.map((x) => (
                    <th key={x.arm}>{x.arm}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {info.families.map((f) => (
                  <tr key={f.family}>
                    <th scope="row">{f.title}</th>
                    <td>{f.n}</td>
                    {rows.map((x) => (
                      <td key={x.arm}>{f.pct[x.arm] !== undefined ? `${fmt(f.pct[x.arm]!)}%` : '-'}</td>
                    ))}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </details>
      )}
      {scale && info && <ScaleExtras rows={rows} info={info} armLabel={armLabel} />}
      {info && info.notes.length > 0 && (
        <div data-testid={`${kind}-notes`}>
          <h3>Notes on how {scale ? 'L2-scale' : 'L2'} was scored</h3>
          <ul>
            {info.notes.map((n) => (
              <li key={n}>{n}</li>
            ))}
          </ul>
        </div>
      )}
      {scale && info && info.honesty.length > 0 && (
        <div data-testid="l2scale-honesty">
          <h3>Honesty notes of this run</h3>
          <ul>
            {info.honesty.map((h) => (
              <li key={h}>{h}</li>
            ))}
          </ul>
        </div>
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

      {r.l2 && <L2Section rows={r.l2} info={r.l2Info} armLabel={armLabel} kind="l2" />}
      {r.l2Scale && <L2Section rows={r.l2Scale} info={r.l2ScaleInfo} armLabel={armLabel} kind="l2scale" />}

      {r.l4.length > 0 && (
        <section className="result-block" aria-labelledby="l4-h" data-testid="l4">
          <h2 id="l4-h">L4 · latency percentiles and throughput</h2>
          {r.l4.map((s) => (
            <L4Section key={s.key} sweep={s} />
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
              <ul>
                {r.l4Notes.map((n) => (
                  <li key={n}>{n}</li>
                ))}
              </ul>
            </div>
          )}
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
