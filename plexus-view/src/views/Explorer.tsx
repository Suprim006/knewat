import { useCallback, useEffect, useRef, useState } from 'react';
import { connectFlowStream } from '../api';
import type { FlowEvent } from '../api';
import { useApi, useTenant } from '../app/context';
import { LiveFeed } from '../components/explorer/LiveFeed';
import { SearchBox } from '../components/explorer/SearchBox';
import { ViewControls } from '../components/explorer/ViewControls';
import { FilterPanel } from '../components/FilterPanel';
import { GraphCanvas } from '../components/GraphCanvas';
import { NodePanel } from '../components/NodePanel';
import { MemoryLegend } from '../components/MemoryLegend';
import { ABLATED_EDGE_TYPES, effectiveHiddenEdges } from '../lib/ablation';
import { errorMessage } from '../lib/errors';
import { DEFAULT_HIDDEN_EDGE_TYPES, DEFAULT_HIDDEN_LABELS } from '../lib/labels';
import type { ColorMode } from '../lib/labels';
import type { Counts, GraphController } from '../lib/graphController';
import { EMPTY_MEMORY_COUNTS } from '../lib/memory';
import type { MemoryCounts } from '../lib/memory';
import { GRAPH_LIMIT, useLiveIngest, useReplay } from '../lib/useLiveGraph';

const EMPTY_COUNTS: Counts = { visibleNodes: 0, totalNodes: 0, visibleEdges: 0, totalEdges: 0 };

interface Stats {
  counts: Counts;
  labels: Record<string, number>;
  edges: Record<string, number>;
  memory: MemoryCounts;
}
const EMPTY_STATS: Stats = { counts: EMPTY_COUNTS, labels: {}, edges: {}, memory: EMPTY_MEMORY_COUNTS };

export function Explorer() {
  const api = useApi();
  const { tenant, empty: noTenants } = useTenant();

  const [ctl, setCtl] = useState<GraphController | null>(null);
  const [loaded, setLoaded] = useState<{ tenant: string; error?: string } | null>(null);
  const [stats, setStats] = useState<Stats>(EMPTY_STATS);
  const [rev, setRev] = useState(0);
  const [hiddenLabels, setHiddenLabels] = useState<ReadonlySet<string>>(() => new Set(DEFAULT_HIDDEN_LABELS));
  const [hiddenEdgeTypes, setHiddenEdgeTypes] = useState<ReadonlySet<string>>(
    () => new Set(DEFAULT_HIDDEN_EDGE_TYPES),
  );
  const [colorMode, setColorMode] = useState<ColorMode>('label');
  const [ablation, setAblation] = useState(false);
  const [bounds, setBounds] = useState<[number, number] | null>(null);
  const [range, setRange] = useState<[number, number] | null>(null);
  const [focusId, setFocusId] = useState<string | null>(null);
  const [query, setQuery] = useState('');
  const [results, setResults] = useState<string[]>([]);
  const [sel, setSel] = useState<{ tenant: string; id: string } | null>(null);
  const [feed, setFeed] = useState<FlowEvent[]>([]);
  const [streamStatus, setStreamStatus] = useState('');

  const filtersRef = useRef<{ hiddenLabels: ReadonlySet<string>; hiddenEdgeTypes: ReadonlySet<string> }>({
    hiddenLabels,
    hiddenEdgeTypes,
  });
  const queryRef = useRef('');
  const colorRef = useRef<ColorMode>('label');
  const lastAtRef = useRef(0);

  const selectedId = sel && sel.tenant === tenant ? sel.id : null;
  const ready = !!ctl && loaded?.tenant === tenant && !loaded.error;
  const loading = !loaded || loaded.tenant !== tenant;
  const fixtureMode = ready && api.streamUrl(tenant) === null;

  const refresh = useCallback((c: GraphController) => {
    setStats({
      counts: c.counts(),
      labels: c.labelCounts(),
      edges: c.edgeTypeCounts(),
      memory: c.memoryCounts(),
    });
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
        ctl.setActivationCenter(g.a0 ?? null);
        ctl.setColorMode(colorRef.current);
        setBounds(ctl.timeBounds());
        setRange(null);
        setFocusId(null);
        lastAtRef.current = g.nodes.reduce((m, n) => Math.max(m, Number(n.props.created_at) || 0), 0);
        if (g.truncated) console.warn('Explorer: graph truncated to the newest', g.limit, 'nodes');
        setFeed([]);
        setLoaded({ tenant });
        refresh(ctl);
      })
      .catch((e: unknown) => {
        if (live) setLoaded({ tenant, error: errorMessage(e) });
      });
    return () => {
      live = false;
    };
  }, [api, ctl, tenant, refresh]);

  /* P7: the verify queue's reasons (commit and path) for the suspect tooltips; optional, never blocks the graph */
  useEffect(() => {
    if (!ctl || !tenant || !ready) return;
    let live = true;
    api
      .verifyQueue(tenant, { limit: 200 })
      .then((q) => {
        if (!live) return;
        ctl.setSuspectReasons(new Map(q.rows.map((r) => [r.fact_id, r.reason])));
        refresh(ctl);
      })
      .catch(() => undefined);
    return () => {
      live = false;
    };
  }, [api, ctl, tenant, ready, refresh]);

  /* selection highlight lives in Cytoscape */
  useEffect(() => {
    ctl?.select(selectedId);
  }, [ctl, selectedId, rev]);

  const live = { ctl, api, tenant, refresh, lastAtRef, setFeed };
  const { ingest, liveError } = useLiveIngest(live);
  const replay = useReplay(live, ingest);

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

  const pushFilters = (labels: ReadonlySet<string>, edgeTypes: ReadonlySet<string>, ablate: boolean) => {
    filtersRef.current = { hiddenLabels: labels, hiddenEdgeTypes: effectiveHiddenEdges(edgeTypes, ablate) };
    if (ctl) {
      ctl.setFilters(filtersRef.current);
      refresh(ctl);
    }
  };
  const onFilters = (labels: Set<string>, edgeTypes: Set<string>) => {
    setHiddenLabels(labels);
    setHiddenEdgeTypes(edgeTypes);
    pushFilters(labels, edgeTypes, ablation);
  };
  const onAblation = (on: boolean) => {
    setAblation(on);
    pushFilters(hiddenLabels, hiddenEdgeTypes, on);
  };
  const onColorMode = (mode: ColorMode) => {
    colorRef.current = mode;
    setColorMode(mode);
    ctl?.setColorMode(mode);
  };
  const onRange = (next: [number, number] | null) => {
    setRange(next);
    ctl?.setTimeRange(next);
    if (ctl) refresh(ctl);
  };
  const onFocus = (id: string | null) => {
    if (!ctl) return;
    if (id) ctl.focusNeighborhood(id, 2);
    else ctl.clearFocus();
    setFocusId(id);
    refresh(ctl);
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

  return (
    <section className="explorer">
      <aside className="panel filters" aria-label="Filters">
        <SearchBox
          query={query}
          onQuery={onQuery}
          matchCount={results.length}
          matches={names}
          onJump={jumpTo}
        />
        <ViewControls
          colorMode={colorMode}
          onColorMode={onColorMode}
          bounds={bounds}
          range={range}
          onRange={onRange}
          ablation={ablation}
          onAblation={onAblation}
          edgeCounts={stats.edges}
        />
        <MemoryLegend counts={stats.memory} />
        <FilterPanel
          labelCounts={stats.labels}
          edgeCounts={stats.edges}
          hiddenLabels={hiddenLabels}
          hiddenEdgeTypes={hiddenEdgeTypes}
          forcedEdgeTypes={ablation ? ABLATED_EDGE_TYPES : []}
          onChange={onFilters}
        />
        <LiveFeed
          feed={feed}
          streamStatus={streamStatus}
          replayable={fixtureMode}
          replay={replay.replay}
          onStartReplay={() => void replay.start()}
          onStopReplay={replay.stop}
        />
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
        {focusId && (
          <div className="overlay top-center" data-testid="focus-banner">
            Focused on {ctl?.describe(focusId)?.name ?? focusId} (2 hops){' '}
            <button type="button" className="btn small" onClick={() => onFocus(null)}>
              Show all
            </button>
          </div>
        )}
        {loading && !noTenants && <div className="overlay center">Loading graph…</div>}
        {noTenants && <div className="overlay center muted">No tenant to show yet.</div>}
        {loaded?.error && loaded.tenant === tenant && (
          <div className="overlay center error" role="alert">
            Could not load the graph: {loaded.error}
          </div>
        )}
        {liveError && liveError.tenant === tenant && (
          <div className="overlay bottom-center error" role="alert">
            Live update failed: {liveError.message}. The graph may be behind; the next event retries.
          </div>
        )}
        {ready && c.totalNodes === 0 && (
          <div className="overlay center muted">This tenant has no data yet.</div>
        )}
      </div>

      <NodePanel
        node={described}
        focused={described !== null && focusId === described.id}
        onFocus={onFocus}
        onSelectNode={jumpTo}
        onClose={() => selectNode(null)}
      />
    </section>
  );
}
