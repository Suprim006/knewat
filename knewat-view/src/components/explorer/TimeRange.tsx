import { formatClock } from '../../lib/flow';

/** Two sliders over the `created_at` span; `range` null means the whole span. */
export function TimeRange({
  bounds,
  range,
  onRange,
}: {
  bounds: [number, number];
  range: [number, number] | null;
  onRange: (next: [number, number] | null) => void;
}) {
  return (
    <fieldset className="time-range" data-testid="time-range">
      <legend>Time range (created)</legend>
      <label>
        From
        <input
          type="range"
          aria-label="Time range from"
          min={bounds[0]}
          max={bounds[1]}
          value={range?.[0] ?? bounds[0]}
          onChange={(e) => {
            const hi = range?.[1] ?? bounds[1];
            onRange([Math.min(Number(e.target.value), hi), hi]);
          }}
        />
        <output>{formatClock(range?.[0] ?? bounds[0])}</output>
      </label>
      <label>
        To
        <input
          type="range"
          aria-label="Time range to"
          min={bounds[0]}
          max={bounds[1]}
          value={range?.[1] ?? bounds[1]}
          onChange={(e) => {
            const lo = range?.[0] ?? bounds[0];
            onRange([lo, Math.max(Number(e.target.value), lo)]);
          }}
        />
        <output>{formatClock(range?.[1] ?? bounds[1])}</output>
      </label>
      {range && (
        <button type="button" className="link" onClick={() => onRange(null)}>
          reset
        </button>
      )}
    </fieldset>
  );
}
