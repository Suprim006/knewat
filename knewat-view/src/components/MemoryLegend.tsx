import type { MemoryCounts } from '../lib/memory';
import { DUPLICATE_GLYPH, PIN_GLYPH, SUSPECT_GLYPH } from '../lib/memory';

function Item({ id, mark, text, count }: { id: string; mark: React.ReactNode; text: string; count: number }) {
  return (
    <li data-testid={`legend-${id}`}>
      <span className="legend-mark" aria-hidden="true">
        {mark}
      </span>
      <span className="check-name">{text}</span>
      <span className="count" data-testid="legend-count">
        {count}
      </span>
    </li>
  );
}

/** Explains the P7 markers on Fact nodes, with how many of each are on the canvas. */
export function MemoryLegend({ counts }: { counts: MemoryCounts }) {
  const any = counts.suspect + counts.pinned + counts.dormant + counts.duplicate + counts.faded > 0;
  return (
    <section aria-labelledby="mem-legend-h" className="memory-legend">
      <h3 id="mem-legend-h">Memory markers</h3>
      {!any ? (
        <p className="muted">No staleness or forgetting data in this tenant yet.</p>
      ) : (
        <ul className="legend-list">
          <Item
            id="suspect"
            mark={<span className="legend-glyph suspect">{SUSPECT_GLYPH}</span>}
            text="suspect: re-check (hover for why)"
            count={counts.suspect}
          />
          <Item
            id="pinned"
            mark={<span className="legend-glyph">{PIN_GLYPH}</span>}
            text="pinned: never fades"
            count={counts.pinned}
          />
          <Item
            id="duplicate"
            mark={<span className="legend-glyph">{DUPLICATE_GLYPH}</span>}
            text="possible duplicate of an older fact (confirm or reject it)"
            count={counts.duplicate}
          />
          <Item
            id="dormant"
            mark={<span className="legend-dashed" />}
            text="dashed outline: dormant"
            count={counts.dormant}
          />
          <Item
            id="faded"
            mark={<span className="legend-fade" />}
            text="opacity follows activation (faded = rarely used)"
            count={counts.faded}
          />
        </ul>
      )}
    </section>
  );
}
