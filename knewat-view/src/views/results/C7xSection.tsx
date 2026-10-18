import type { C7xInfo } from '../../lib/resultsP9';

const pct = (v: number): string => `${v.toFixed(v % 1 === 0 ? 0 : 1)}%`;

/** C7 extended: 226 labelled pairs; the gate is zero false merges in every category. */
export function C7xSection({ c7x }: { c7x: C7xInfo }) {
  const plexus = c7x.arms.find((a) => a.arm === 'P');
  const missed = c7x.targets.filter((t) => t.missed);
  return (
    <section className="result-block" aria-labelledby="c7x-h" data-testid="c7x">
      <h2 id="c7x-h">C7 extended · does the duplicate rule merge two different statements?</h2>
      {plexus && (
        <p data-testid="c7x-headline">
          <b>
            {plexus.falseMerges} false merges in {plexus.notMergePairs} pairs that must stay apart
          </b>{' '}
          (negation, antonyms, units, number words, near-twins). 95% upper bound by the rule of three:{' '}
          {c7x.falseMergeUpper95 !== undefined
            ? pct(c7x.falseMergeUpper95 * 100)
            : `< ${pct(300 / plexus.notMergePairs)}`}
          ; it says nothing about phrasings the corpus does not contain. Of the {plexus.mergePairs} true
          paraphrases, {plexus.autoMerged} are merged automatically (
          {pct((100 * plexus.autoMerged) / plexus.mergePairs)}) and {plexus.surfaced} are merged or surfaced
          for review ({pct((100 * plexus.surfaced) / plexus.mergePairs)}).
        </p>
      )}
      {missed.length > 0 && (
        <p data-testid="c7x-missed">
          <b>Target missed:</b>{' '}
          {missed
            .map(
              (t) =>
                `${t.category} paraphrases ${pct(t.autoPct)} auto-merged and ${pct(t.surfacedPct)} surfaced against a pre-registered target of ${pct(t.targetAutoPct)} auto${t.category === 'heavy' ? ' or 95% surfaced' : ''}`,
            )
            .join('; ')}
          . Reported as missed, not tuned away (the test half was never used for tuning).
        </p>
      )}
      <div className="table-scroll">
        <table className="data">
          <thead>
            <tr>
              <th>Arm</th>
              <th>Pairs</th>
              <th>Must stay apart</th>
              <th>False merges</th>
              <th>Paraphrases auto-merged</th>
              <th>Merged or surfaced</th>
            </tr>
          </thead>
          <tbody>
            {c7x.arms.map((a) => (
              <tr key={a.arm} data-testid={`c7x-arm-${a.arm}`}>
                <th scope="row">{a.arm}</th>
                <td>{a.pairs}</td>
                <td>{a.notMergePairs}</td>
                <td className={a.falseMerges > 0 ? 'cell-fail' : 'cell-pass'}>{a.falseMerges}</td>
                <td>
                  {a.autoMerged}/{a.mergePairs}
                </td>
                <td>
                  {a.surfaced}/{a.mergePairs}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <details>
        <summary>Per category (Plexus service arm)</summary>
        <div className="table-scroll">
          <table className="data">
            <thead>
              <tr>
                <th>Category</th>
                <th>Expected</th>
                <th>Pairs</th>
                <th>Merged</th>
                <th>Soft link</th>
                <th>Separate</th>
                <th>False merges</th>
              </tr>
            </thead>
            <tbody>
              {c7x.categories.map((c) => (
                <tr key={c.name}>
                  <th scope="row">{c.name}</th>
                  <td>{c.expected}</td>
                  <td>{c.pairs}</td>
                  <td>{c.merged}</td>
                  <td>{c.maybe}</td>
                  <td>{c.isNew}</td>
                  <td>{c.expected === 'merge' ? 'n/a' : c.falseMerges}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </details>
    </section>
  );
}
