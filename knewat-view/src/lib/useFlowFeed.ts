import { useEffect, useRef, useState } from 'react';
import { connectFlowStream } from '../api';
import type { FlowEvent, StreamStatus, ViewApi } from '../api';
import { loadFlowBackfill } from './flow';

export interface FlowFeed {
  /** Oldest first. */
  events: FlowEvent[];
  /** `null` in fixture mode (no stream). */
  status: StreamStatus | null;
  loaded: boolean;
  error?: string;
}

const KEEP = 500;

/**
 * The tenant's ToolCall timeline: a backfill from `/flow`, then live events from the SSE stream
 * (resuming from the backfill's `last_at`, reconnecting with backoff). State is keyed by tenant so a
 * tenant switch never shows the previous tenant's events.
 */
export function useFlowFeed(api: ViewApi, tenant: string): FlowFeed {
  const [state, setState] = useState<{ tenant: string; events: FlowEvent[]; error?: string } | null>(null);
  const [status, setStatus] = useState<StreamStatus | null>(null);
  const seen = useRef(new Set<string>());

  useEffect(() => {
    if (!tenant) return;
    let live = true;
    let closeStream: (() => void) | undefined;
    seen.current = new Set();
    loadFlowBackfill(api, tenant, KEEP).then(
      ({ events, lastAt }) => {
        if (!live) return;
        for (const e of events) seen.current.add(e.id);
        setState({ tenant, events });
        const url = api.streamUrl(tenant);
        if (!url) return;
        closeStream = connectFlowStream({
          url,
          after: lastAt || undefined,
          onStatus: (s) => live && setStatus(s),
          onEvent: (ev) => {
            if (!live || seen.current.has(ev.id)) return;
            seen.current.add(ev.id);
            setState((cur) =>
              cur && cur.tenant === tenant ? { ...cur, events: [...cur.events, ev].slice(-KEEP) } : cur,
            );
          },
        });
      },
      (e: unknown) => {
        if (live) setState({ tenant, events: [], error: e instanceof Error ? e.message : String(e) });
      },
    );
    return () => {
      live = false;
      closeStream?.();
      setStatus(null);
    };
  }, [api, tenant]);

  const current = state && state.tenant === tenant ? state : null;
  return { events: current?.events ?? [], status, loaded: current !== null, error: current?.error };
}
