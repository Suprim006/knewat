import { L6_EXPECTATION } from '../../lib/resultsP9';
import type { L6Arm, L6Crash, L6Family, L6Info } from '../../lib/resultsP9';

const ms = (v?: number): string =>
  v === undefined ? '-' : v >= 1000 ? `${(v / 1000).toFixed(1)} s` : `${v} ms`;
const usd = (v: number): string => `$${v.toFixed(v < 1 ? 3 : 2)}`;

function ArmTable({ title, rows, testid }: { title: string; rows: L6Arm[]; testid: string }) {
  if (rows.length === 0) return null;
  return (
    <div className="table-scroll">
      <table className="data" data-testid={testid}>
        <caption>{title}</caption>
        <thead>
          <tr>
            <th>Arm</th>
            <th>Strict correct</th>
            <th>Timeouts (5 s)</th>
            <th>p50</th>
            <th>p99</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((a) => (
            <tr key={a.arm} data-testid={`${testid}-${a.arm}`}>
              <th scope="row">{a.arm}</th>
              <td>{a.strict}</td>
              <td>{a.timeouts ?? '-'}</td>
              <td>{ms(a.p50)}</td>
              <td>{ms(a.p99)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function CrashTable({ rows, title, testid }: { rows: L6Crash[]; title: string; testid: string }) {
  if (rows.length === 0) return null;
  return (
    <div className="table-scroll">
      <table className="data" data-testid={testid}>
        <caption>{title}</caption>
        <thead>
          <tr>
            <th>Arm</th>
            <th>Acknowledged writes</th>
            <th>Records written</th>
            <th>Without Step/WROTE (facts / decisions / handoffs)</th>
            <th>Acknowledged writes lost</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((c) => {
            const k = c.orphansByKind ?? {};
            return (
              <tr key={c.arm} data-testid={`${testid}-${c.arm}`}>
                <th scope="row">{c.arm}</th>
                <td>{c.acked}</td>
                <td>{c.total ?? '-'}</td>
                <td className={c.orphans > 0 ? 'cell-fail' : 'cell-pass'}>
                  <b>{c.orphans}</b>
                  {c.total ? ` of ${c.total} (${((100 * c.orphans) / c.total).toFixed(1)}%)` : ''}
                  {' · '}
                  {k.facts ?? 0} / {k.decisions ?? 0} / {k.handoffs ?? 0}
                </td>
                <td>{c.lost}</td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}

/** A: the product's impact arms before (the pre-registered run) and after the P9-int fix. */
function BeforeAfter({ f }: { f: L6Family }) {
  const pre = f.det.filter((a) => a.arm.startsWith('P-product'));
  const rows = f.postfixA.filter((a) => a.arm.startsWith('P-product'));
  if (rows.length === 0) return null;
  return (
    <div className="table-scroll">
      <table className="data" data-testid="l6-A-fix">
        <caption>
          The product&apos;s impact tool before and after the P9-int fix (same world, same 24 questions)
        </caption>
        <thead>
          <tr>
            <th>Arm</th>
            <th>Before: strict / timeouts / p99</th>
            <th>After: strict / timeouts / p99 / slowest</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((a) => {
            const b = pre.find((x) => x.arm === a.arm);
            return (
              <tr key={a.arm} data-testid={`l6-A-fix-${a.arm}`}>
                <th scope="row">{a.arm}</th>
                <td>{b ? `${b.strict} / ${b.timeouts ?? '-'} / ${ms(b.p99)}` : '-'}</td>
                <td>
                  <b>{a.strict}</b> / {a.timeouts ?? '-'} / {ms(a.p99)} / {ms(a.max)}
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}

function FamilyBlock({ f }: { f: L6Family }) {
  const id = f.id;
  const p = f.det.find((a) => a.arm === 'P');
  const sql = f.det.find((a) => a.arm === 'B1h');
  const speed = id === 'D' && p?.p50 && sql?.p50 ? p.p50 / sql.p50 : undefined;
  return (
    <div className="l6-family" data-testid={`l6-${id}`}>
      <h3>{f.title}</h3>
      <p className="muted" data-testid={`l6-${id}-expect`}>
        <b>Pre-registered:</b> {L6_EXPECTATION[id]}
      </p>
      <ArmTable title="Deterministic arms (24 questions)" rows={f.det} testid={`l6-${id}-det`} />
      {id === 'A' && (
        <ArmTable title="A-dag: tasks blocked by a failure (5 sizes)" rows={f.dag} testid="l6-A-dag" />
      )}
      {id === 'A' && <BeforeAfter f={f} />}
      {speed !== undefined && (
        <p data-testid="l6-D-speed">
          Same questions, same answers: SQL is <b>{speed.toFixed(1)}x faster</b> at the median (in-process
          SQLite against FalkorDB over the container network).
        </p>
      )}
      {f.conc.length > 0 && (
        <div className="table-scroll">
          <table className="data" data-testid="l6-E-conc">
            <caption>10 runs of 6 s: 4 appenders, 1 quarantiner, 8 readers</caption>
            <thead>
              <tr>
                <th>Arm</th>
                <th>Decision without its facts</th>
                <th>Half-quarantined subtree</th>
                <th>Count differs from list</th>
                <th>Reads</th>
              </tr>
            </thead>
            <tbody>
              {f.conc.map((c) => (
                <tr key={c.arm} data-testid={`l6-E-${c.arm}`}>
                  <th scope="row">{c.arm}</th>
                  <td className={c.v1 > 0 ? 'cell-fail' : 'cell-pass'}>{c.v1}</td>
                  <td className={c.v2 > 0 ? 'cell-fail' : 'cell-pass'}>{c.v2}</td>
                  <td className={c.v3 > 0 ? 'cell-fail' : 'cell-pass'}>{c.v3}</td>
                  <td>{c.reads}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      <CrashTable
        rows={f.crash}
        title="200 SIGKILLs per arm, before the fix (the pre-registered run)"
        testid="l6-F-crash"
      />
      <CrashTable
        rows={f.postfixF}
        title="Arm P again after the fix (WROTE written by the same statement; same seed, 200 kills)"
        testid="l6-F-fix"
      />
      {f.pilot.length > 0 && (
        <p className="muted">
          LLM pilot (8 questions, one repetition):{' '}
          {f.pilot.map((x) => `${x.arm === 'P' ? 'P-mcp' : x.arm} ${x.correct}/${x.n}`).join(', ')}.
        </p>
      )}
    </div>
  );
}

/** L6: the pre-registered beat-SQL families. The expectation is shown next to what was measured. */
export function L6Section({ l6 }: { l6: L6Info }) {
  return (
    <section className="result-block" aria-labelledby="l6-h" data-testid="l6">
      <h2 id="l6-h">L6 · where a graph could beat SQL: five pre-registered families</h2>
      <p className="muted">
        Each family has a hand-written SQL control (B1h) and states its prediction before the run. A tie or a
        Plexus loss is a valid outcome and is shown as such. Family C (multi-hop recall) was not run.{' '}
        {l6.postfixRun && (
          <>
            A and F were re-run after the fixes the first run exposed (run <code>{l6.postfixRun}</code>, no
            LLM, same worlds and seeds).
          </>
        )}
      </p>
      {l6.families.map((f) => (
        <FamilyBlock key={f.id} f={f} />
      ))}
      {l6.pilotTotals.length > 0 && (
        <div className="l6-pilot" data-testid="l6-pilot">
          <h3>LLM pilot · families A, B and D, 8 questions each</h3>
          <div className="table-scroll">
            <table className="data">
              <thead>
                <tr>
                  <th>Arm</th>
                  <th>Strict correct</th>
                  <th>Cost</th>
                  <th>Cost per question</th>
                </tr>
              </thead>
              <tbody>
                {l6.pilotTotals.map((p) => (
                  <tr key={p.arm} data-testid={`l6-pilot-${p.arm}`}>
                    <th scope="row">{p.arm}</th>
                    <td>
                      {p.correct}/{p.n}
                    </td>
                    <td>{usd(p.cost)}</td>
                    <td>{usd(p.cost / p.n)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <p className="muted">
            B1a = an agent with one SQL tool; B0g = an agent with files and a shell; B0r = a reader with a 32k
            excerpt and no tools; P-mcp = an agent with the Plexus MCP tools (not asked family D: no tool
            exists for it). {l6.llmCalls} paid calls, {usd(l6.costUsd)} of the{' '}
            {l6.budgetCapUsd !== undefined ? usd(l6.budgetCapUsd) : '$20'} cap. Eight questions and one
            repetition cannot show a gap under three questions.
          </p>
        </div>
      )}
    </section>
  );
}
