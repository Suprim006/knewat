import { act, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import type { FlowEvent } from '../api';
import { createFixtureApi } from '../fixtures/client';
import { FakeEventSource } from '../test/fakeEventSource';
import { acme, renderApp } from '../test/render';

const rows = () => within(screen.getByTestId('timeline')).getAllByRole('button');

afterEach(() => {
  vi.unstubAllGlobals();
  FakeEventSource.reset();
});

describe('Flow', () => {
  it('renders the tool-call timeline newest first with agent, tool, time, run time and counts', async () => {
    renderApp('/flow');
    await waitFor(() => expect(rows().length).toBe(Math.min(500, acme.flow.length)));
    const newest = acme.flow[acme.flow.length - 1]!;
    const first = rows()[0]!;
    expect(first).toHaveTextContent(newest.tool);
    expect(first).toHaveTextContent(newest.agent_id);
    expect(first).toHaveTextContent(`${newest.run_time_ms.toFixed(1)} ms`);
    expect(first).toHaveTextContent(`+${newest.created.length}`);
    expect(first).toHaveTextContent(/\d\d:\d\d:\d\d\.\d{3}/);
    expect(screen.getByTestId('stream-status')).toHaveTextContent('fixtures');
  });

  it('shows the Cypher behind an event when it is clicked, and what the call created', async () => {
    const user = userEvent.setup();
    renderApp('/flow');
    await waitFor(() => expect(rows().length).toBeGreaterThan(10));
    const assertFact = acme.flow.find(
      (e) => e.tool === 'assert_fact' && e.created.some((c) => c.label === 'Fact'),
    )!;
    const row = rows().find(
      (r) => r.textContent?.includes(assertFact.tool) && r.textContent.includes(formatAt(assertFact)),
    )!;
    await user.click(row);
    const detail = await screen.findByTestId('event-detail');
    await waitFor(() => expect(within(detail).getByTestId('cypher-text')).toHaveTextContent('MATCH'));
    expect(within(detail).getByTestId('cypher-text')).toHaveTextContent('name: engram/assert_fact');
    expect(within(detail).getByText('engram/assert_fact')).toBeInTheDocument();
    expect(within(detail).getByText(/Created \(\d+\)/)).toBeInTheDocument();
    expect(within(detail).getAllByRole('link', { name: 'Why?' }).length).toBeGreaterThan(0);
    await within(detail).findByTestId('mini-graph');
    expect(row).toHaveAttribute('aria-pressed', 'true');
  });

  it('replays the timeline with play/pause and a speed control', async () => {
    const user = userEvent.setup();
    renderApp('/flow');
    await waitFor(() => expect(rows().length).toBeGreaterThan(10));
    await user.click(screen.getByRole('button', { name: /Replay/ }));
    await user.selectOptions(screen.getByLabelText('Replay speed'), '10');
    await waitFor(() =>
      expect(Number(screen.getByTestId('replay-progress').textContent?.split('/')[0])).toBeGreaterThan(1),
    );
    await user.click(screen.getByRole('button', { name: /Pause/ }));
    const frozen = screen.getByTestId('replay-progress').textContent;
    await new Promise((r) => setTimeout(r, 150));
    expect(screen.getByTestId('replay-progress')).toHaveTextContent(frozen!);
    await user.click(screen.getByRole('button', { name: /Play/ }));
    await waitFor(() => expect(screen.getByTestId('replay-progress').textContent).not.toBe(frozen));
    await user.click(screen.getByRole('button', { name: /Back to live/ }));
    expect(rows().length).toBe(Math.min(500, acme.flow.length));
  });
});

const formatAt = (e: FlowEvent) => new Date(e.at).toISOString().slice(11, 23);

describe('Flow (live over SSE)', () => {
  beforeEach(() => {
    vi.stubGlobal('EventSource', FakeEventSource);
  });

  it('backfills from /flow, resumes the stream after it, and adds pushed events', async () => {
    const base = createFixtureApi(acme);
    const api = { ...base, streamUrl: (t: string) => `http://api/api/${t}/stream` };
    renderApp('/flow', api);
    await waitFor(() => expect(FakeEventSource.instances.length).toBe(1));
    const lastAt = acme.flow[acme.flow.length - 1]!.at;
    expect(FakeEventSource.last!.url).toBe(`http://api/api/acme/stream?after=${lastAt}`);
    act(() => FakeEventSource.last!.open());
    expect(screen.getByTestId('stream-status')).toHaveTextContent('stream: open');

    const live: FlowEvent = {
      id: 'live-1',
      tool: 'heartbeat',
      at: lastAt + 5000,
      agent_id: 'builder',
      query_name: 'relay/heartbeat',
      run_time_ms: 0.42,
      wrote: true,
      step: null,
      step_id: null,
      step_n: null,
      created: [],
      updated: [{ id: acme.ids['t.7']!, label: 'Task' }],
    };
    const before = rows().length;
    act(() => FakeEventSource.last!.emit(live));
    await waitFor(() => expect(rows().length).toBe(before + 1));
    expect(rows()[0]).toHaveTextContent('heartbeat');
    expect(rows()[0]).toHaveTextContent('~1');

    // pausing freezes the view while events keep arriving
    const user = userEvent.setup();
    await user.click(screen.getByRole('button', { name: /Pause live/ }));
    act(() => FakeEventSource.last!.emit({ ...live, id: 'live-2', at: live.at + 1000 }));
    expect(rows().length).toBe(before + 1);
    await user.click(screen.getByRole('button', { name: /Resume live \(1 new\)/ }));
    await waitFor(() => expect(rows().length).toBe(before + 2));
  });

  it('reconnects when the stream drops', async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    try {
      const base = createFixtureApi(acme);
      renderApp('/flow', { ...base, streamUrl: (t: string) => `http://api/api/${t}/stream` });
      await waitFor(() => expect(FakeEventSource.instances.length).toBe(1));
      act(() => FakeEventSource.last!.fail());
      await act(async () => {
        await vi.advanceTimersByTimeAsync(600);
      });
      expect(FakeEventSource.instances.length).toBe(2);
      expect(FakeEventSource.instances[0]!.closed).toBe(true);
    } finally {
      vi.useRealTimers();
    }
  });
});
