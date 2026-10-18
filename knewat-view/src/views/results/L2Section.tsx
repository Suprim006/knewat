import { costText, fmt, fmtInt, fmtMs } from '../../lib/format';
import type { L2Info, L2Row } from '../../lib/results';
import { Bars } from './Bars';
import { ScaleExtras } from './ScaleExtras';
import { StringList } from './StringList';

/** L2: provenance-question accuracy per arm; `l2scale` is the same questions over a much longer history. */
export function L2Section({
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
          <StringList items={info.notes} />
        </div>
      )}
      {scale && info && info.honesty.length > 0 && (
        <div data-testid="l2scale-honesty">
          <h3>Honesty notes of this run</h3>
          <StringList items={info.honesty} />
        </div>
      )}
    </section>
  );
}
