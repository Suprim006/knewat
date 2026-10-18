import { MODULE_COLORS } from '../../lib/labels';
import type { ColorMode } from '../../lib/labels';
import { AblationPanel } from '../AblationPanel';
import { TimeRange } from './TimeRange';

/** The "View" section of the Explorer sidebar: colour mode, time range and the ablation toggle. */
export function ViewControls({
  colorMode,
  onColorMode,
  bounds,
  range,
  onRange,
  ablation,
  onAblation,
  edgeCounts,
}: {
  colorMode: ColorMode;
  onColorMode: (mode: ColorMode) => void;
  bounds: [number, number] | null;
  range: [number, number] | null;
  onRange: (next: [number, number] | null) => void;
  ablation: boolean;
  onAblation: (on: boolean) => void;
  edgeCounts: Record<string, number>;
}) {
  return (
    <section aria-labelledby="view-h" className="view-controls">
      <h3 id="view-h">View</h3>
      <label className="inline">
        Colour by
        <select
          aria-label="Colour by"
          value={colorMode}
          onChange={(e) => onColorMode(e.target.value as ColorMode)}
        >
          <option value="label">node label</option>
          <option value="module">module</option>
        </select>
      </label>
      {colorMode === 'module' && (
        <ul className="module-legend" data-testid="module-legend">
          {Object.entries(MODULE_COLORS).map(([m, c]) => (
            <li key={m}>
              <span className="dot" style={{ background: c }} /> {m}
            </li>
          ))}
        </ul>
      )}
      {bounds && bounds[0] < bounds[1] && <TimeRange bounds={bounds} range={range} onRange={onRange} />}
      <label className="check ablation-toggle">
        <input
          type="checkbox"
          checked={ablation}
          onChange={(e) => onAblation(e.target.checked)}
          aria-label="Ablation: hide DEPENDS_ON, BASED_ON, DERIVED_FROM and READ"
        />
        <span className="check-name">Ablation view</span>
      </label>
      {ablation && <AblationPanel counts={edgeCounts} />}
    </section>
  );
}
