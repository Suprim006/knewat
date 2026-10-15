import { useCallback, useEffect, useRef, useState } from 'react';
import type { Dispatch, RefObject, SetStateAction } from 'react';
import type { FlowEvent, ViewApi } from '../api';
import { errorMessage } from './errors';
import type { GraphController } from './graphController';

/** Nodes the Explorer reads per request (the API caps the subgraph at this many, newest first). */
export const GRAPH_LIMIT = 2000;
const REPLAY_EVENTS = 24;
const REPLAY_INTERVAL_MS = 700;

interface LiveDeps {
  ctl: GraphController | null;
  api: ViewApi;
  tenant: string;
  /** Re-derive the React-side stats (counts, search results) after the canvas changed. */
  refresh: (c: GraphController) => void;
  /** Newest event/node time seen, for the SSE resume point and the replay reset. */
  lastAtRef: RefObject<number>;
  setFeed: Dispatch<SetStateAction<FlowEvent[]>>;
}

/**
 * A flow event arrived (SSE, or the fixture replay). The API cannot fetch nodes by id, and a
 * `since`/`until` window on created_at would drop the edges that join new nodes to older ones, so we
 * re-read the (bounded) subgraph and let `addLive` add only what is new: no relayout, new nodes seeded
 * next to a neighbour.
 *
 * Live events are coalesced: at most one read is in flight; events that arrive meanwhile only set a
 * `dirty` flag, and one trailing read picks up everything they changed. A burst of N calls therefore
 * costs two reads, not N. A failed read is shown (not swallowed) and the next event retries.
 *
 * The replay passes `until` (caps the read at the event's time so nodes appear one event at a time);
 * those reads are deliberately one per event, in order.
 */
export function useLiveIngest({ ctl, api, tenant, refresh, lastAtRef, setFeed }: LiveDeps) {
  const ingestQueue = useRef<Promise<void>>(Promise.resolve());
  /** Live-read state of the current (controller, tenant); replaced on switch so a stale read cannot touch it. */
  const liveRead = useRef({ running: false, dirty: false });
  const [liveError, setLiveError] = useState<{ tenant: string; message: string } | null>(null);

  /* a new controller or tenant starts a fresh live-read state (an old read finishing must not touch it) */
  useEffect(() => {
    liveRead.current = { running: false, dirty: false };
  }, [ctl, tenant]);

  const ingest = useCallback(
    (ev: FlowEvent, until?: number): Promise<void> => {
      if (!ctl) return Promise.resolve();
      setFeed((f) => [ev, ...f].slice(0, 6));
      lastAtRef.current = Math.max(lastAtRef.current, ev.at);
      const known = (id: string) => ctl.cy.getElementById(id).nonempty();
      const touchesNew = ev.created.some((r) => !known(r.id)) || ev.updated.length > 0;
      if (!touchesNew && until === undefined) return Promise.resolve();

      const state = liveRead.current;
      const read = async (cap?: number) => {
        const g = await api.graph(tenant, { limit: GRAPH_LIMIT, until: cap });
        if (liveRead.current !== state) return; // tenant or controller changed while reading
        ctl.addLive(g.nodes, g.edges);
        ctl.updateProps(g.nodes);
        if (g.a0 !== undefined) ctl.setActivationCenter(g.a0);
        setLiveError(null);
        refresh(ctl);
      };
      if (until !== undefined) {
        const run = () => read(until);
        ingestQueue.current = ingestQueue.current.then(run).catch(() => undefined);
        return ingestQueue.current;
      }
      if (state.running) {
        state.dirty = true;
        return Promise.resolve();
      }
      state.running = true;
      void (async () => {
        try {
          do {
            state.dirty = false;
            await read();
          } while (state.dirty && liveRead.current === state);
        } catch (e) {
          if (liveRead.current === state) setLiveError({ tenant, message: errorMessage(e) });
        } finally {
          state.running = false;
        }
      })();
      return Promise.resolve();
    },
    [ctl, api, tenant, refresh, lastAtRef, setFeed],
  );

  return { ingest, liveError };
}

/**
 * Fixture mode only: replay the last flow events one at a time as if they were live. Resets the canvas to
 * just before the first of them, then feeds each through `ingest` with its own time as the read cap.
 */
export function useReplay(
  { ctl, api, tenant, refresh, lastAtRef, setFeed }: LiveDeps,
  ingest: (ev: FlowEvent, until?: number) => Promise<void>,
) {
  const [replay, setReplay] = useState<{ tenant: string; done: number; total: number } | null>(null);
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null);

  /* stop any running replay when the tenant or controller changes */
  useEffect(
    () => () => {
      if (timer.current) clearTimeout(timer.current);
      timer.current = null;
    },
    [tenant, ctl],
  );

  const start = async () => {
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
      timer.current = setTimeout(() => {
        void ingest(ev, ev.at).then(() => {
          setReplay({ tenant, done: i + 1, total });
          tick(i + 1);
        });
      }, REPLAY_INTERVAL_MS);
    };
    setReplay({ tenant, done: 0, total });
    tick(0);
  };
  const stop = () => {
    if (timer.current) clearTimeout(timer.current);
    timer.current = null;
    setReplay(null);
  };

  return { replay: replay !== null && replay.tenant === tenant ? replay : null, start, stop };
}
