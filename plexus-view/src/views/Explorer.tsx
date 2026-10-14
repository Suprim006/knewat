import { useCallback, useEffect, useRef, useState } from 'react';
import { connectFlowStream } from '../api';
import type { FlowEvent } from '../api';
import { useApi, useTenant } from '../app/context';
import { FilterPanel } from '../components/FilterPanel';
import { GraphCanvas } from '../components/GraphCanvas';
import { NodePanel } from '../components/NodePanel';
import { DEFAULT_HIDDEN_EDGE_TYPES, DEFAULT_HIDDEN_LABELS, labelColor } from '../lib/labels';
import type { Counts, GraphController } from '../lib/graphController';

const GRAPH_LIMIT = 2000;
const REPLAY_EVENTS = 24;
const REPLAY_INTERVAL_MS = 700;
const EMPTY_COUNTS: Counts = { visibleNodes: 0, totalNodes: 0, visibleEdges: 0, totalEdges: 0 };

interface Stats {
  counts: Counts;
  labels: Record<string, number>;
  edges: Record<string, number>;
}
const EMPTY_STATS: Stats = { counts: EMPTY_COUNTS, labels: {}, edges: {} };

export function Explorer() {
  const api = useApi();
  const { tenant } = useTenant();

  const [ctl, setCtl] = useState<GraphController | null>(null);
  const [loaded, setLoaded] = useState<{ tenant: string; error?: string } | null>(null);
  const [stats, setStats] = useState<Stats>(EMPTY_STATS);
  const [rev, setRev] = useState(0);
  const [hiddenLabels, setHiddenLabels] = useState<ReadonlySet<string>>(() => new Set(DEFAULT_HIDDEN_LABELS));
  const [hiddenEdgeTypes, setHiddenEdgeTypes] = useState<ReadonlySet<string>>(
    () => new Set(DEFAULT_HIDDEN_EDGE_TYPES),
  );
  const [query, setQuery] = useState('');
  const [results, setResults] = useState<string[]>([]);
  const [sel, setSel] = useState<{ tenant: string; id: string } | null>(null);
  const [feed, setFeed] = useState<FlowEvent[]>([]);
  const [streamStatus, setStreamStatus] = useState('');
  const [replay, setReplay] = useState<{ tenant: string; done: number; total: number } | null>(null);

  const filtersRef = useRef({ hiddenLabels, hiddenEdgeTypes });
  const queryRef = useRef('');
  const lastAtRef = useRef(0);
  const replayTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const ingestQueue = useRef<Promise<void>>(Promise.resolve());

  const selectedId = sel && sel.tenant === tenant ? sel.id : null;
  const ready = !!ctl && loaded?.tenant === tenant && !loaded.error;
  const loading = !loaded || loaded.tenant !== tenant;
  const fixtureMode = ready && api.streamUrl(tenant) === null;

  const refresh = useCallback((c: GraphController) => {
    setStats({ counts: c.counts(), labels: c.labelCounts(), edges: c.edgeTypeCounts() });
    setResults(c.setSearch(queryRef.current));
    setRev((r) => r + 1);
  }, []);

  /* initial load (and tenant switch) */
  useEffect(() => {
    if (!ctl || !tenant) return;
    let live = true;
    api
      .graph(tenant, { limit: GRAPH_LIMIT })
      .then((g) => {
        if (!live) return;
        ctl.setFilters(filtersRef.current);
        ctl.load(g.nodes, g.edges);
        lastAtRef.current = g.nodes.reduce((m, n) => Math.max(m, Number(n.props.created_at) || 0), 0);
        if (g.truncated) console.warn('Explorer: graph truncated to the newest', g.limit, 'nodes');
        setFeed([]);
        setLoaded({ tenant });
        refresh(ctl);
      })
      .catch((e: unknown) => {
        if (live) setLoaded({ tenant, error: e instanceof Error ? e.message : String(e) });
      });
    return () => {
      live = false;
    };
  }, [api, ctl, tenant, refresh]);

  /* selection highlight lives in Cytoscape */
  useEffect(() => {
    ctl?.select(selectedId);
  }, [ctl, selectedId, rev]);

  /*
   * A flow event arrived (SSE, or the fixture replay). The API cannot fetch nodes by id, and a
   * `since`/`until` window on created_at would drop the edges that join new nodes to older ones, so we
   * re-read the (bounded) subgraph and let `addLive` add only what is new: no relayout, new nodes seeded
   * next to a neighbour. Bursts are coalesced into one read. `until` caps the read at the event's time
   * (used by the replay so nodes appear one event at a time).
   */
  const ingest = useCallback(
    (ev: FlowEvent, until?: number): Promise<void> => {
      if (!ctl) return Promise.resolve();
      setFeed((f) => [ev, ...f].slice(0, 6));
      lastAtRef.current = Math.max(lastAtRef.current, ev.at);
      const known = (id: string) => ctl.cy.getElementById(id).nonempty();
      const touchesNew = ev.created.some((r) => !known(r.id)) || ev.updated.length > 0;
      if (!touchesNew && until === undefined) return ingestQueue.current;
      const run = async () => {
        const g = await api.graph(tenant, { limit: GRAPH_LIMIT, until });
        ctl.addLive(g.nodes, g.edges);
        ctl.updateProps(g.nodes);
        refresh(ctl);
      };
      ingestQueue.current = ingestQueue.current.then(run).catch(() => undefined);
      return ingestQueue.current;
    },
    [ctl, api, tenant, refresh],
  );

  /* live mode: SSE with reconnection */
  useEffect(() => {
    if (!ready) return;
    const url = api.streamUrl(tenant);
    if (!url) return;
    return connectFlowStream({
      url,
      after: lastAtRef.current || undefined,
      onStatus: setStreamStatus,
      onEvent: (ev) => void ingest(ev),
    });
  }, [api, tenant, ready, ingest]);

  /* stop any running replay when the tenant or controller changes */
  useEffect(
    () => () => {
      if (replayTimer.current) clearTimeout(replayTimer.current);
      replayTimer.current = null;
    },
    [tenant, ctl],
  );

  const startReplay = async () => {
    if (!ctl) return;
    const events = (await api.flow(tenant)).events.slice(-REPLAY_EVENTS);
    const first = events[0];
    if (!first) return;
    ctl.removeCreatedSince(first.at);
    lastAtRef.current = first.at - 1;
    setFeed([]);
    refresh(ctl);
    const total = events.length;
    const tick = (i: number) => {
      const ev = events[i];
      if (!ev) {
        setReplay(null);
        return;
      }
      replayTimer.current = setTimeout(() => {
        void ingest(ev, ev.at).then(() => {
          setReplay({ tenant, done: i + 1, total });
          tick(i + 1);
        });
      }, REPLAY_INTERVAL_MS);
    };
    setReplay({ tenant, done: 0, total });
    tick(0);
  };
  const stopReplay = () => {
    if (replayTimer.current) clearTimeout(replayTimer.current);
    replayTimer.current = null;
    setReplay(null);
  };

  const onFilters = (labels: Set<string>, edgeTypes: Set<string>) => {
    filtersRef.current = { hiddenLabels: labels, hiddenEdgeTypes: edgeTypes };
    setHiddenLabels(labels);
    setHiddenEdgeTypes(edgeTypes);
    if (ctl) {
      ctl.setFilters(filtersRef.current);
      refresh(ctl);
    }
  };

  const onQuery = (v: string) => {
    queryRef.current = v;
    setQuery(v);
    if (ctl) setResults(ctl.setSearch(v));
  };

  const selectNode = useCallback((id: string | null) => setSel(id ? { tenant, id } : null), [tenant]);
  const jumpTo = (id: string) => {
    selectNode(id);
    ctl?.focus(id);
  };

  // Cytoscape is the store; every mutation goes through refresh(), which re-renders us.
  const described = ctl && selectedId ? ctl.describe(selectedId) : null;
  const names = results
    .slice(0, 8)
    .map((id) => ctl?.describe(id))
    .filter((d) => d != null);
  const c = stats.counts;
  const replaying = replay !== null && replay.tenant === tenant;

  return (
    <section className="explorer">
      <aside className="panel filters" aria-label="Filters">
        <div className="search">
          <input
            type="search"
            placeholder="Search nodes (name, text, value)…"
            aria-label="Search nodes"
            value={query}
            onChange={(e) => onQuery(e.target.value)}
          />
          {query.trim() && (
            <div className="search-results" aria-live="polite">
              <div className="muted">
                {results.length} match{results.length === 1 ? '' : 'es'}
              </div>
              <ul>
                {names.map((d) => (
                  <li key={d.id}>
                    <button type="button" className="link" onClick={() => jumpTo(d.id)}>
                      <span className="dot" style={{ background: labelColor(d.label) }} />
                      {d.name}
                      <span className="muted"> · {d.label}</span>
                    </button>
                  </li>
                ))}
              </ul>
            </div>
          )}
        </div>
        <FilterPanel
          labelCounts={stats.labels}
          edgeCounts={stats.edges}
          hiddenLabels={hiddenLabels}
          hiddenEdgeTypes={hiddenEdgeTypes}
          onChange={onFilters}
        />
        <section aria-labelledby="live-h" className="live">
          <h3 id="live-h">Live feed</h3>
          {streamStatus && <div className="muted">stream: {streamStatus}</div>}
          {fixtureMode && (
            <button
              type="button"
              className="btn small"
              onClick={replaying ? stopReplay : () => void startReplay()}
            >
              {replaying ? `Stop replay (${replay.done}/${replay.total})` : '▶ Replay last events as live'}
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
      </aside>

      <div className="canvas-wrap">
        <GraphCanvas onReady={setCtl} onSelect={selectNode} />
        <div className="overlay top-left" data-testid="visible-counts">
          Showing <b>{c.visibleNodes}</b> of {c.totalNodes} nodes · <b>{c.visibleEdges}</b> of {c.totalEdges}{' '}
          edges
        </div>
        <div className="overlay top-right">
          <button type="button" className="btn small" onClick={() => ctl?.fit()}>
            Fit
          </button>
          <button
            type="button"
            className="btn small"
            onClick={() => ctl?.relayout()}
            title="Re-run the draft layout (nodes will move)"
          >
            Re-layout
          </button>
        </div>
        {loading && <div className="overlay center">Loading graph…</div>}
        {loaded?.error && loaded.tenant === tenant && (
          <div className="overlay center error" role="alert">
            Could not load the graph: {loaded.error}
          </div>
        )}
        {ready && c.totalNodes === 0 && (
          <div className="overlay center muted">This tenant has no data yet.</div>
        )}
      </div>

      <NodePanel node={described} onSelectNode={jumpTo} onClose={() => selectNode(null)} />
    </section>
  );
}
