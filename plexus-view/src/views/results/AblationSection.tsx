import type { ParsedResults } from '../../lib/results';

/** Ablation: edges actually deleted from the graph, then each capability re-probed. */
export function AblationSection({ ablation }: { ablation: NonNullable<ParsedResults['ablation']> }) {
  return (
    <section className="result-block" id="ablation" aria-labelledby="abl-h" data-testid="ablation">
      <h2 id="abl-h">Ablation · what breaks without the edges</h2>
      <p className="muted">
        Edges actually deleted from the graph ({ablation.stripped.join(', ')}), then each capability
        re-probed. Controls do not use those edges and should be unaffected.
      </p>
      <ul className="inline-list">
        {ablation.summary.map((s) => (
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
            {ablation.capabilities.map((c) => (
              <tr key={c.capability} className={c.breaks ? 'row-broken' : undefined}>
                <th scope="row">{c.capability}</th>
                <td>{c.needs}</td>
                <td className={c.intactPass ? 'cell-pass' : 'cell-fail'}>{c.intactPass ? 'pass' : 'FAIL'}</td>
                <td className={c.ablatedPass ? 'cell-pass' : 'cell-fail'}>
                  {c.ablatedPass ? 'pass' : 'FAIL'}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {ablation.l1.length > 0 && (
        <table className="data">
          <thead>
            <tr>
              <th>L1 re-run</th>
              <th>Arm</th>
              <th>Violations</th>
            </tr>
          </thead>
          <tbody>
            {ablation.l1.map((x) => (
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
  );
}
