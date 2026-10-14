import { describe, expect, it, vi } from 'vitest';
import { backoffDelay, connectFlowStream, withAfter } from './sse';
import type { EventSourceLike, StreamStatus } from './sse';
import type { FlowEvent } from './types';

class FakeES implements EventSourceLike {
  onopen: ((ev: Event) => void) | null = null;
  onmessage: ((ev: MessageEvent) => void) | null = null;
  onerror: ((ev: Event) => void) | null = null;
  readyState = 0;
  closed = false;
  constructor(readonly url: string) {}
  close() {
    this.closed = true;
  }
  emit(ev: FlowEvent | string) {
    this.onmessage?.({ data: typeof ev === 'string' ? ev : JSON.stringify(ev) } as MessageEvent);
  }
}

const ev = (at: number): FlowEvent => ({
  id: `e${at}`,
  tool: 'assert_fact',
  at,
  agent_id: 'a',
  query_name: 'engram/assert_fact',
  run_time_ms: 1,
  created: [],
  updated: [],
});

function setup(after?: number) {
  const sources: FakeES[] = [];
  const timers: { fn: () => void; ms: number }[] = [];
  const events: FlowEvent[] = [];
  const statuses: StreamStatus[] = [];
  const close = connectFlowStream({
    url: 'http://api/api/acme/stream',
    after,
    onEvent: (e) => events.push(e),
    onStatus: (s) => statuses.push(s),
    factory: (u) => {
      const s = new FakeES(u);
      sources.push(s);
      return s;
    },
    setTimer: (fn, ms) => {
      timers.push({ fn, ms });
      return timers.length;
    },
    clearTimer: vi.fn(),
    baseDelayMs: 100,
    maxDelayMs: 1000,
  });
  return { sources, timers, events, statuses, close };
}

describe('sse helper', () => {
  it('builds resume urls and backoff', () => {
    expect(withAfter('http://x/s')).toBe('http://x/s');
    expect(withAfter('http://x/s', 5)).toBe('http://x/s?after=5');
    expect(withAfter('http://x/s?a=1', 5)).toBe('http://x/s?a=1&after=5');
    expect([0, 1, 2, 5].map((n) => backoffDelay(n, 100, 1000))).toEqual([100, 200, 400, 1000]);
  });

  it('delivers parsed events and ignores malformed frames', () => {
    const { sources, events, statuses } = setup();
    sources[0]!.onopen?.(new Event('open'));
    sources[0]!.emit(ev(10));
    sources[0]!.emit('not json');
    expect(events.map((e) => e.at)).toEqual([10]);
    expect(statuses).toEqual(['connecting', 'open']);
  });

  it('reconnects with backoff, resuming after the newest event and dropping replays', () => {
    const { sources, timers, events } = setup();
    sources[0]!.emit(ev(10));
    sources[0]!.onerror?.(new Event('error'));
    expect(sources[0]!.closed).toBe(true);
    expect(timers.map((t) => t.ms)).toEqual([100]);
    timers[0]!.fn();
    expect(sources[1]!.url).toBe('http://api/api/acme/stream?after=10');
    sources[1]!.emit(ev(10)); // replayed
    sources[1]!.emit(ev(11));
    expect(events.map((e) => e.at)).toEqual([10, 11]);
    // a second failure doubles the delay; a successful open resets it
    sources[1]!.onerror?.(new Event('error'));
    expect(timers[1]!.ms).toBe(200);
    timers[1]!.fn();
    sources[2]!.onopen?.(new Event('open'));
    sources[2]!.onerror?.(new Event('error'));
    expect(timers[2]!.ms).toBe(100);
  });

  it('starts from a given resume point', () => {
    const { sources } = setup(42);
    expect(sources[0]!.url).toBe('http://api/api/acme/stream?after=42');
  });

  it('stops reconnecting once closed', () => {
    const { sources, timers, close, statuses } = setup();
    sources[0]!.onerror?.(new Event('error'));
    close();
    timers[0]!.fn();
    expect(sources).toHaveLength(1);
    expect(statuses.at(-1)).toBe('closed');
  });
});
