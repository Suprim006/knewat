import type { FlowEvent } from './types';

/** Minimal slice of EventSource we depend on (lets tests inject a fake). */
export interface EventSourceLike {
  onopen: ((ev: Event) => void) | null;
  onmessage: ((ev: MessageEvent) => void) | null;
  onerror: ((ev: Event) => void) | null;
  readyState: number;
  close(): void;
}
export type EventSourceFactory = (url: string) => EventSourceLike;

export type StreamStatus = 'connecting' | 'open' | 'reconnecting' | 'closed';

export interface FlowStreamOptions {
  /** Stream URL, e.g. `http://localhost:8080/api/acme/stream`. */
  url: string;
  onEvent: (event: FlowEvent) => void;
  onStatus?: (status: StreamStatus) => void;
  /** Resume point: `at` of the newest event already seen. Sent as `?after=` on (re)connect. */
  after?: number;
  factory?: EventSourceFactory;
  /** First reconnect delay in ms (doubles up to `maxDelayMs`). */
  baseDelayMs?: number;
  maxDelayMs?: number;
  /** Injectable timers for tests. */
  setTimer?: (fn: () => void, ms: number) => unknown;
  clearTimer?: (handle: unknown) => void;
}

export function withAfter(url: string, after?: number): string {
  if (after === undefined) return url;
  return `${url}${url.includes('?') ? '&' : '?'}after=${after}`;
}

/** Exponential backoff: base, 2*base, 4*base ... capped. */
export function backoffDelay(attempt: number, baseMs: number, maxMs: number): number {
  return Math.min(maxMs, baseMs * 2 ** Math.max(0, attempt));
}

/**
 * Subscribe to the flow SSE stream with reconnection. EventSource reconnects by itself for network
 * blips, but gives up (readyState CLOSED) on HTTP errors, so we always reconnect ourselves with
 * backoff and resume from the newest `at` we've seen. Returns a `close()` function.
 */
export function connectFlowStream(opts: FlowStreamOptions): () => void {
  const factory: EventSourceFactory = opts.factory ?? ((u) => new EventSource(u));
  const setTimer = opts.setTimer ?? ((fn, ms) => setTimeout(fn, ms));
  const clearTimer = opts.clearTimer ?? ((h) => clearTimeout(h as ReturnType<typeof setTimeout>));
  const base = opts.baseDelayMs ?? 500;
  const max = opts.maxDelayMs ?? 15_000;

  let lastAt = opts.after;
  let attempt = 0;
  let source: EventSourceLike | null = null;
  let timer: unknown = null;
  let closed = false;

  const status = (s: StreamStatus) => opts.onStatus?.(s);

  function open(first: boolean) {
    status(first ? 'connecting' : 'reconnecting');
    const es = factory(withAfter(opts.url, lastAt));
    source = es;
    es.onopen = () => {
      attempt = 0;
      status('open');
    };
    es.onmessage = (msg) => {
      let ev: FlowEvent;
      try {
        ev = JSON.parse(String(msg.data)) as FlowEvent;
      } catch {
        return; // ignore keep-alives and malformed frames
      }
      if (lastAt !== undefined && ev.at <= lastAt) return; // replay after reconnect
      lastAt = ev.at;
      opts.onEvent(ev);
    };
    es.onerror = () => {
      if (closed) return;
      es.close();
      source = null;
      status('reconnecting');
      timer = setTimer(
        () => {
          timer = null;
          if (!closed) open(false);
        },
        backoffDelay(attempt++, base, max),
      );
    };
  }

  open(true);
  return () => {
    closed = true;
    if (timer !== null) clearTimer(timer);
    source?.close();
    source = null;
    status('closed');
  };
}
