import { fmt } from '../../lib/format';

/** Horizontal bar chart (CSS bars); `max` pins the scale, otherwise the largest value is 100%. */
export function Bars({
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
