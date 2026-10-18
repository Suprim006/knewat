import { LABEL_MODULES, MODULE_ORDER, labelColor } from '../lib/labels';

interface Props {
  labelCounts: Record<string, number>;
  edgeCounts: Record<string, number>;
  hiddenLabels: ReadonlySet<string>;
  hiddenEdgeTypes: ReadonlySet<string>;
  /** Edge types hidden by the ablation switch: shown unchecked and locked. */
  forcedEdgeTypes?: readonly string[];
  onChange: (labels: Set<string>, edgeTypes: Set<string>) => void;
}

function toggled(set: ReadonlySet<string>, key: string): Set<string> {
  const next = new Set(set);
  if (next.has(key)) next.delete(key);
  else next.add(key);
  return next;
}

/** Legend + label/edge-type filters. A checked box means "shown". */
export function FilterPanel({
  labelCounts,
  edgeCounts,
  hiddenLabels,
  hiddenEdgeTypes,
  forcedEdgeTypes = [],
  onChange,
}: Props) {
  const labels = Object.keys(labelCounts);
  const modules = MODULE_ORDER.map((m) => ({
    module: m,
    labels: labels.filter((l) => (LABEL_MODULES[l] ?? 'Other') === m).sort(),
  })).filter((g) => g.labels.length > 0);
  const known = new Set(modules.flatMap((g) => g.labels));
  const other = labels.filter((l) => !known.has(l)).sort();
  if (other.length > 0) modules.push({ module: 'Other', labels: other });
  const edgeTypes = Object.entries(edgeCounts).sort((a, b) => b[1] - a[1] || a[0].localeCompare(b[0]));

  return (
    <div className="filters-body">
      <section aria-labelledby="flt-labels">
        <div className="section-head">
          <h3 id="flt-labels">Node labels</h3>
          <span className="actions">
            <button
              type="button"
              className="link"
              onClick={() => onChange(new Set(), new Set(hiddenEdgeTypes))}
            >
              all
            </button>
            <button
              type="button"
              className="link"
              onClick={() => onChange(new Set(labels), new Set(hiddenEdgeTypes))}
            >
              none
            </button>
          </span>
        </div>
        {modules.map((g) => (
          <div key={g.module} className="legend-group">
            <div className="legend-module">{g.module}</div>
            {g.labels.map((l) => (
              <label key={l} className="check">
                <input
                  type="checkbox"
                  checked={!hiddenLabels.has(l)}
                  onChange={() => onChange(toggled(hiddenLabels, l), new Set(hiddenEdgeTypes))}
                />
                <span className="dot" style={{ background: labelColor(l) }} aria-hidden="true" />
                <span className="check-name">{l}</span>
                <span className="count">{labelCounts[l]}</span>
              </label>
            ))}
          </div>
        ))}
      </section>
      <section aria-labelledby="flt-edges">
        <div className="section-head">
          <h3 id="flt-edges">Edge types</h3>
          <span className="actions">
            <button type="button" className="link" onClick={() => onChange(new Set(hiddenLabels), new Set())}>
              all
            </button>
            <button
              type="button"
              className="link"
              onClick={() => onChange(new Set(hiddenLabels), new Set(edgeTypes.map(([t]) => t)))}
            >
              none
            </button>
          </span>
        </div>
        {edgeTypes.map(([t, n]) => (
          <label key={t} className="check">
            <input
              type="checkbox"
              checked={!hiddenEdgeTypes.has(t) && !forcedEdgeTypes.includes(t)}
              disabled={forcedEdgeTypes.includes(t)}
              onChange={() => onChange(new Set(hiddenLabels), toggled(hiddenEdgeTypes, t))}
            />
            <span className="check-name mono">{t}</span>
            <span className="count">{n}</span>
          </label>
        ))}
      </section>
    </div>
  );
}
