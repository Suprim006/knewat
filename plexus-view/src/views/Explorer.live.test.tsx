import { act, screen, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import type { FlowEvent, Subgraph, ViewApi } from '../api';
import { createFixtureApi } from '../fixtures/client';
import { FakeEventSource } from '../test/fakeEventSource';
import { acme, renderApp } from '../test/render';

const nodeCount = () => {
  const t = screen.getByTestId('visible-counts').textContent ?? '';
  const m = /of (\d+) nodes/.exec(t);
  return m ? Number(m[1]) : 0;
};

/** An Explorer wired to a fake SSE stream, with the graph read counted (and optionally scripted). */
function setup(graph: (call: number) => Promise<Subgraph>) {
  const base = createFixtureApi(acme);
  const reads = { n: 0 };
  const api: ViewApi = {
    ...base,
    streamUrl: (t: string) => `http://api/api/${t}/stream`,
    graph: (t, opts) => {
      reads.n += 1;
      return opts?.until === undefined ? graph(reads.n) : base.graph(t, opts);
    },
  };
  renderApp('/', api);
  return { reads };
}

const event = (i: number): FlowEvent => ({
  id: `burst-${i}`,
  tool: 'heartbeat',
  at: acme.flow[acme.flow.length - 1]!.at + 1000 + i,
  agent_id: 'builder',
  query_name: 'relay/heartbeat',
  run_time_ms: 0.4,
  wrote: true,
  step: null,
  step_id: null,
  step_n: null,
  created: [],
  updated: [{ id: acme.ids['t.7']!, label: 'Task' }],
});

const full = (): Subgraph => ({ nodes: acme.nodes, edges: acme.edges, truncated: false, limit: 2000 });

afterEach(() => {
  vi.unstubAllGlobals();
  FakeEventSource.reset();
});
beforeEach(() => vi.stubGlobal('EventSource', FakeEventSource));

describe('Explorer: live ingest over SSE', () => {
  it('coalesces a burst of events into at most two graph reads', async () => {
    const { reads } = setup(async () => full());
    await waitFor(() => expect(nodeCount()).toBeGreaterThan(0));
    await waitFor(() => expect(FakeEventSource.instances.length).toBe(1));
    const afterLoad = reads.n;

    act(() => {
      for (let i = 0; i < 20; i++) FakeEventSource.last!.emit(event(i));
    });
    // one read was in flight when the other 19 events arrived, and they cost exactly one trailing read
    await waitFor(() => expect(reads.n - afterLoad).toBe(2));
    await new Promise((r) => setTimeout(r, 200)); // ...and nothing more follows
    expect(reads.n - afterLoad).toBe(2);
  });

  it('the trailing read picks up what changed while the first read was in flight', async () => {
    const early = acme.nodes.filter((n) => n.label !== 'Decision');
    const ids = new Set(early.map((n) => n.id));
    const initial: Subgraph = {
      nodes: early,
      edges: acme.edges.filter((e) => ids.has(e.source) && ids.has(e.target)),
      truncated: false,
      limit: 2000,
    };
    let release: (() => void) | undefined;
    const { reads } = setup(async (call) => {
      if (call === 1) return initial;
      if (call === 2) await new Promise<void>((r) => (release = r)); // held: later events arrive meanwhile
      return full();
    });
    await waitFor(() => expect(nodeCount()).toBe(early.length));
    await waitFor(() => expect(FakeEventSource.instances.length).toBe(1));
    act(() => {
      for (let i = 0; i < 5; i++) FakeEventSource.last!.emit(event(i));
    });
    await waitFor(() => expect(release).toBeDefined());
    expect(reads.n).toBe(2); // one read in flight, the other four events only mark it dirty
    await act(async () => release!());
    await waitFor(() => expect(nodeCount()).toBe(acme.nodes.length));
    expect(reads.n).toBe(3); // exactly one trailing read
  });

  it('shows a failed live read instead of swallowing it, and recovers on the next event', async () => {
    const { reads } = setup(async (call) => {
      if (call === 2) throw new Error('boom');
      return full();
    });
    await waitFor(() => expect(nodeCount()).toBeGreaterThan(0));
    await waitFor(() => expect(FakeEventSource.instances.length).toBe(1));
    act(() => FakeEventSource.last!.emit(event(1)));
    const alert = await screen.findByRole('alert');
    expect(alert).toHaveTextContent(/live update failed/i);
    expect(alert).toHaveTextContent('boom');

    act(() => FakeEventSource.last!.emit(event(2)));
    await waitFor(() => expect(screen.queryByRole('alert')).not.toBeInTheDocument());
    expect(reads.n).toBe(3);
  });
});
