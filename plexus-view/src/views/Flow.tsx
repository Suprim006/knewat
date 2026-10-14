import { useCallback, useEffect, useMemo, useState } from 'react';
import { Link } from 'react-router-dom';
import type { FlowEvent, NodeRef } from '../api';
import { useApi, useTenant } from '../app/context';
import { CypherView } from '../components/CypherView';
import { MiniGraph } from '../components/MiniGraph';
import { eventSubgraph } from '../lib/eventGraph';
import { REPLAY_SPEEDS, agentColor, formatClock, replayDelay } from '../lib/flow';
import { labelColor } from '../lib/labels';
import { useAsync } from '../lib/useAsync';
import { useFlowFeed } from '../lib/useFlowFeed';

interface Replay {
  source: FlowEvent[];
  shown: number;
  playing: boolean;
}

function NodeChips({ refs }: { refs: NodeRef[] }) {
  if (refs.length === 0) return <span className="muted">none</span>;
  return (
    <ul className="chips">
      {refs.map((r) => (
        <li key={r.id} title={r.id}>
          <span className="dot" style={{ background: labelColor(r.label) }} />
          {r.label}
          {(r.label === 'Decision' || r.label === 'Fact') && (
            <>
              {' '}
              <Link to={`/why/${encodeURIComponent(r.id)}`}>Why?</Link>
            </>
          )}
        </li>
      ))}
    </ul>
  );
}

function EventDetail({ ev }: { ev: FlowEvent }) {
  const api = useApi();
  const { tenant } = useTenant();
  const loadQuery = useCallback(
    () => (ev.query_name ? api.queryText(ev.query_name) : Promise.resolve(undefined)),
    [api, ev.query_name],
  );
  const query = useAsync(loadQuery);
  // Re-read the graph for each picked event, so the nodes it just created are present.
  const loadGraph = useCallback(() => api.graph(tenant, { limit: 2000 }), [api, tenant]);
  const graph = useAsync(loadGraph);
  const sub = useMemo(() => (graph.data ? eventSubgraph(graph.data, ev) : null), [graph.data, ev]);

  return (
    <section className="event-detail" aria-label="Event detail" data-testid="event-detail">
      <h2>
        <span className="dot" style={{ background: agentColor(ev.agent_id) }} /> {ev.tool}
        <span className="muted"> · {ev.agent_id}</span>
      </h2>
      <dl className="kv">
        <dt>time</dt>
        <dd className="mono">{formatClock(ev.at)}</dd>
        <dt>server run time</dt>
        <dd>{ev.run_time_ms.toFixed(2)} ms</dd>
        <dt>kind</dt>
        <dd>{ev.wrote ? 'write' : 'read'}</dd>
        <dt>agent step</dt>
        <dd>
          {ev.step_n !== null ? (
            <Link to={`/time?step=${ev.step_n}`}>step {ev.step_n} in the Time Machine</Link>
          ) : (
            <span className="muted">no step</span>
          )}
        </dd>
      </dl>
      <div className="two-col">
        <div>
          <h3>Created ({ev.created.length})</h3>
          <NodeChips refs={ev.created} />
        </div>
        <div>
          <h3>Updated ({ev.updated.length})</h3>
          <NodeChips refs={ev.updated} />
        </div>
      </div>

      <h3>The Cypher behind it</h3>
      {!ev.query_name && <p className="muted">This call ran no named query.</p>}
      {query.error && (
        <p className="banner error" role="alert">
          Could not load the query text for <code>{ev.query_name}</code>: {query.error.message}
        </p>
      )}
      {query.data && (
        <>
          <p className="query-meta">
            <code>{query.data.name}</code> <span className="chip plain">{query.data.mode}</span>{' '}
            {query.data.purpose}
          </p>
          <CypherView text={query.data.text} label={`Cypher for ${query.data.name}`} />
        </>
      )}

      <h3>What it touched</h3>
      {sub ? (
        <MiniGraph nodes={sub.nodes} edges={sub.edges} created={sub.created} updated={sub.updated} />
      ) : (
        <p className="muted">{graph.error ? `Graph unavailable: ${graph.error.message}` : 'Loading…'}</p>
      )}
    </section>
  );
}

export function Flow() {
  const api = useApi();
  const { tenant } = useTenant();
  const feed = useFlowFeed(api, tenant);
  const [sel, setSel] = useState<{ tenant: string; id: string } | null>(null);
  const [frozenAt, setFrozenAt] = useState<number | null>(null); // live view paused at this many events
  const [replay, setReplay] = useState<Replay | null>(null);
  const [speed, setSpeed] = useState<number>(1);

  /* replay clock: reveal the next event after the (speed-scaled) gap */
  useEffect(() => {
    if (!replay?.playing || replay.shown >= replay.source.length) return;
    const next = replay.source[replay.shown]!;
    const prev = replay.source[replay.shown - 1];
    const t = setTimeout(
      () => setReplay((r) => (r && r.shown === replay.shown ? { ...r, shown: r.shown + 1 } : r)),
      prev ? replayDelay(prev.at, next.at, speed) : 0,
    );
    return () => clearTimeout(t);
  }, [replay, speed]);

  const shown = useMemo(() => {
    if (replay) return replay.source.slice(0, replay.shown);
    return frozenAt === null ? feed.events : feed.events.slice(0, frozenAt);
  }, [replay, frozenAt, feed.events]);
  const rows = useMemo(() => [...shown].reverse(), [shown]);
  const hidden = replay || frozenAt === null ? 0 : feed.events.length - frozenAt;

  const selectedId = sel && sel.tenant === tenant ? sel.id : null;
  const selected = selectedId ? (feed.events.find((e) => e.id === selectedId) ?? null) : null;

  const startReplay = () => {
    setFrozenAt(null);
    setSel(null);
    setReplay({ source: feed.events, shown: 0, playing: true });
  };

  return (
    <section className="page flow" aria-labelledby="flow-h">
      <header className="page-head">
        <h1 id="flow-h">Flow</h1>
        <p className="muted">
          Every MCP tool call, as the <code>ToolCall</code> node it left in the graph. Click one to see what
          it wrote and the Cypher that ran.
        </p>
        <div className="toolbar" role="toolbar" aria-label="Timeline controls">
          <span className={`badge ${feed.status === 'open' ? 'ok' : ''}`} data-testid="stream-status">
            {feed.status === null ? 'fixtures · no stream' : `stream: ${feed.status}`}
          </span>
          {!replay && (
            <>
              <button
                type="button"
                className="btn small"
                onClick={() => setFrozenAt(frozenAt === null ? feed.events.length : null)}
                aria-pressed={frozenAt !== null}
              >
                {frozenAt === null ? '⏸ Pause live' : `▶ Resume live${hidden > 0 ? ` (${hidden} new)` : ''}`}
              </button>
              <button
                type="button"
                className="btn small"
                onClick={startReplay}
                disabled={feed.events.length === 0}
              >
                ⟲ Replay
              </button>
            </>
          )}
          {replay && (
            <>
              <button
                type="button"
                className="btn small"
                onClick={() => setReplay((r) => (r ? { ...r, playing: !r.playing } : r))}
              >
                {replay.playing ? '⏸ Pause' : '▶ Play'}
              </button>
              <label className="inline">
                Speed
                <select
                  aria-label="Replay speed"
                  value={speed}
                  onChange={(e) => setSpeed(Number(e.target.value))}
                >
                  {REPLAY_SPEEDS.map((s) => (
                    <option key={s} value={s}>
                      {s}×
                    </option>
                  ))}
                </select>
              </label>
              <span className="muted" data-testid="replay-progress">
                {replay.shown}/{replay.source.length}
              </span>
              <button type="button" className="btn small" onClick={() => setReplay(null)}>
                ■ Back to live
              </button>
            </>
          )}
          <span className="muted">{shown.length} events</span>
        </div>
      </header>

      {feed.error && (
        <div className="banner error" role="alert">
          Could not load the flow: {feed.error}
        </div>
      )}
      {feed.loaded && feed.events.length === 0 && !feed.error && (
        <p className="muted">No tool calls yet. Events appear here as agents call the MCP server.</p>
      )}

      <div className="flow-body">
        <ol className="timeline" aria-label="Tool calls, newest first" data-testid="timeline">
          {rows.map((e) => (
            <li key={e.id}>
              <button
                type="button"
                className={`event${e.id === selectedId ? ' selected' : ''}`}
                aria-pressed={e.id === selectedId}
                style={{ borderLeftColor: agentColor(e.agent_id) }}
                onClick={() => setSel({ tenant, id: e.id })}
              >
                <span className="ev-tool mono">{e.tool}</span>
                <span className="ev-agent" style={{ color: agentColor(e.agent_id) }}>
                  {e.agent_id}
                </span>
                <span className="ev-time mono muted">{formatClock(e.at)}</span>
                <span className="ev-stats muted">
                  {e.run_time_ms.toFixed(1)} ms · <b className="created">+{e.created.length}</b>{' '}
                  <b className="updated">~{e.updated.length}</b>
                </span>
              </button>
            </li>
          ))}
        </ol>
        <div className="flow-detail">
          {selected ? (
            <EventDetail key={selected.id} ev={selected} />
          ) : (
            <p className="muted placeholder-note">Select an event to see its Cypher and what it touched.</p>
          )}
        </div>
      </div>
    </section>
  );
}
