import type { FlowEvent } from '../../api';

/** The sidebar's live feed: stream status, the fixture replay button and the latest events. */
export function LiveFeed({
  feed,
  streamStatus,
  replayable,
  replay,
  onStartReplay,
  onStopReplay,
}: {
  feed: FlowEvent[];
  streamStatus: string;
  /** Fixture mode: offer "replay the last events as live". */
  replayable: boolean;
  replay: { done: number; total: number } | null;
  onStartReplay: () => void;
  onStopReplay: () => void;
}) {
  return (
    <section aria-labelledby="live-h" className="live">
      <h3 id="live-h">Live feed</h3>
      {streamStatus && <div className="muted">stream: {streamStatus}</div>}
      {replayable && (
        <button type="button" className="btn small" onClick={replay ? onStopReplay : onStartReplay}>
          {replay ? `Stop replay (${replay.done}/${replay.total})` : '▶ Replay last events as live'}
        </button>
      )}
      <ul className="feed">
        {feed.map((e) => (
          <li key={e.id}>
            <span className="mono">{e.tool}</span>
            <span className="muted">
              {' '}
              +{e.created.length} ~{e.updated.length}
            </span>
          </li>
        ))}
      </ul>
    </section>
  );
}
