import type { B1hInfo } from '../../lib/resultsP9';
import { StringList } from './StringList';

const reading = (b: number, p?: number): string => {
  if (p === undefined) return 'no Knewat row to compare';
  if (b === p) return 'SQL ties';
  return b > p ? `SQL is ahead by ${b - p}` : `Knewat is ahead by ${p - b}`;
};

/** B1h: the same L2 / L2-scale questions answered by a competent, hand-written SQL author on SQLite. */
export function B1hSection({ b1h }: { b1h: B1hInfo }) {
  return (
    <section className="result-block" aria-labelledby="b1h-h" data-testid="b1h">
      <h2 id="b1h-h">B1h · the hand-written SQL control</h2>
      <p className="muted">
        The L2 and L2-scale provenance questions again, answered by hand-written SQL on SQLite (no LLM,{' '}
        {b1h.llmCalls} calls). A control, not a rival product: it shows what a competent relational schema
        does on the same questions.
        {b1h.sqlLines !== undefined && b1h.cypherLines !== undefined && (
          <>
            {' '}
            Answerer size: {b1h.sqlLines} lines of SQL against {b1h.cypherLines} lines of Cypher (non-blank,
            non-comment).
          </>
        )}
      </p>
      <div className="table-scroll">
        <table className="data">
          <thead>
            <tr>
              <th>Questions</th>
              <th>B1h (SQL)</th>
              <th>Knewat</th>
              <th title="paired on the same questions">Both right / only SQL / only Knewat / both wrong</th>
              <th>Reading</th>
            </tr>
          </thead>
          <tbody>
            {b1h.rows.map((row) => (
              <tr key={row.layer} data-testid={`b1h-${row.layer}`}>
                <th scope="row">{row.title}</th>
                <td>
                  {row.correct}/{row.total}
                </td>
                <td>{row.knewatCorrect !== undefined ? `${row.knewatCorrect}/${row.total}` : '-'}</td>
                <td>
                  {row.bothCorrect ?? '-'} / {row.b1hOnly ?? '-'} / {row.pOnly ?? '-'} /{' '}
                  {row.bothWrong ?? '-'}
                </td>
                <td>
                  <b>{reading(row.correct, row.knewatCorrect)}</b>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <p>
        On these questions SQL answers as many as Knewat does, so the result shows no advantage of the graph
        over a relational schema. The caveats are in the notes: the same author wrote the SQL and the Cypher,
        and SQLite here runs in-process.
      </p>
      {b1h.honesty.length > 0 && <StringList items={b1h.honesty} />}
    </section>
  );
}
