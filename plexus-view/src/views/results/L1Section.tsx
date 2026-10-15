import type { ParsedResults } from '../../lib/results';

/** L1: correctness under concurrency, one row per test and one column per arm. */
export function L1Section({
  l1,
  armLabel,
}: {
  l1: NonNullable<ParsedResults['l1']>;
  armLabel: (id: string) => string;
}) {
  return (
    <section className="result-block" aria-labelledby="l1-h" data-testid="l1">
      <h2 id="l1-h">L1 · correctness under concurrency</h2>
      <p className="muted">Violation counts are summed over every run: counts, not averages.</p>
      <div className="table-scroll">
        <table className="data">
          <thead>
            <tr>
              <th>Test</th>
              <th>Pass bar</th>
              {l1.arms.map((a) => (
                <th key={a} title={armLabel(a)}>
                  {a}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {l1.rows.map((row) => (
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
  );
}
