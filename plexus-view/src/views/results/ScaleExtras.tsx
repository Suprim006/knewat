import { fmt, fmtInt, pFmt } from '../../lib/format';
import { intervalsOverlap, signTest } from '../../lib/results';
import type { L2Info, L2Row } from '../../lib/results';

const STRATA = ['early', 'middle', 'late'];

type ArmLabel = (id: string) => string;

function History({ h }: { h: NonNullable<L2Info['history']> }) {
  return (
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
  );
}

function Significance({ p, baselines, armLabel }: { p: L2Row; baselines: L2Row[]; armLabel: ArmLabel }) {
  return (
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
        Computed here from the per-question results in the file. The sign test uses only the questions where
        exactly one of the two arms was right, so it is a small sample ({p.n ?? '?'} questions, one run each,
        one model, one synthetic scenario family). {baselines.length} comparisons are shown without any
        correction for that. Overlapping intervals and a p-value above 0.05 mean the gap is not
        distinguishable from sampling noise with this many questions; a gap with a small p-value is
        suggestive, not proof. The honesty notes below say which choices favour the baselines and which favour
        Plexus.
      </p>
    </div>
  );
}

function Strata({ rows, armLabel }: { rows: L2Row[]; armLabel: ArmLabel }) {
  return (
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
  );
}

function Failures({ rows, armLabel }: { rows: L2Row[]; armLabel: ArmLabel }) {
  return (
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
  );
}

/** What only the scale run has: how big the history is, strata, failure analysis, intervals and the paired sign test. */
export function ScaleExtras({ rows, info, armLabel }: { rows: L2Row[]; info: L2Info; armLabel: ArmLabel }) {
  const p = rows.find((x) => x.arm === 'P');
  const baselines = rows.filter((x) => x.arm !== 'P');
  const h = info.history;
  return (
    <>
      {h && <History h={h} />}
      {p && baselines.some((b) => b.questions) && (
        <Significance p={p} baselines={baselines} armLabel={armLabel} />
      )}
      {rows.some((x) => x.byStratum) && <Strata rows={rows} armLabel={armLabel} />}
      {rows.some((x) => x.failure) && <Failures rows={rows} armLabel={armLabel} />}
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
