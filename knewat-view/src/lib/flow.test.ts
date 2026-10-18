import { describe, expect, it, vi } from 'vitest';
import type { FlowEvent, ViewApi } from '../api';
import { buildAcme } from '../fixtures/acme';
import { eventSubgraph } from './eventGraph';
import { agentColor, formatClock, loadFlowBackfill, replayDelay } from './flow';

const data = buildAcme();

describe('flow helpers', () => {
  it('colours the demo roles fixed and other agents stably', () => {
    expect(agentColor('planner')).not.toBe(agentColor('builder'));
    expect(agentColor('agent-x')).toBe(agentColor('agent-x'));
    expect(agentColor('agent-x')).toMatch(/^#[0-9a-f]{6}$/);
  });

  it('formats clock times in UTC', () => {
    expect(formatClock(Date.UTC(2026, 9, 15, 3, 4, 5, 67))).toBe('03:04:05.067');
  });

  it('scales replay gaps by speed, clamped', () => {
    expect(replayDelay(0, 1000, 1)).toBe(1000);
    expect(replayDelay(0, 1000, 10)).toBe(100);
    expect(replayDelay(0, 600_000, 1)).toBe(1500);
    expect(replayDelay(0, 1, 1)).toBe(40);
    expect(replayDelay(500, 100, 2)).toBe(20);
  });

  it('pages /flow with last_at until a short page and keeps the newest events', async () => {
    const mk = (i: number): FlowEvent => ({ ...data.flow[0]!, id: `e${i}`, at: i });
    const flow = vi.fn(async (_t: string, after = 0, limit = 200) => {
      const events = Array.from({ length: 2300 }, (_, i) => mk(i + 1))
        .filter((e) => e.at > after)
        .slice(0, limit);
      return { events, last_at: events.at(-1)?.at ?? after };
    });
    const { events, lastAt } = await loadFlowBackfill({ flow } as unknown as ViewApi, 't', 100);
    expect(flow).toHaveBeenCalledTimes(3);
    expect(events).toHaveLength(100);
    expect(events.at(-1)!.at).toBe(2300);
    expect(lastAt).toBe(2300);
  });
});

describe('eventSubgraph', () => {
  const graph = { nodes: data.nodes, edges: data.edges };

  it('keeps the tool call, the nodes it created and their useful neighbours', () => {
    const ev = data.flow.find((e) => e.tool === 'assert_fact' && e.created.some((c) => c.label === 'Fact'))!;
    const sub = eventSubgraph(graph, ev);
    const ids = new Set(sub.nodes.map((n) => n.id));
    expect(ids.has(ev.id)).toBe(true);
    for (const c of ev.created) expect(ids.has(c.id)).toBe(true);
    expect(sub.created).toEqual(ev.created.map((c) => c.id));
    expect(sub.missing).toEqual([]);
    expect(sub.nodes.some((n) => n.label === 'Entity' || n.label === 'Agent')).toBe(true);
    expect(sub.nodes.some((n) => n.label === 'Step' || n.label === 'Scope')).toBe(false);
    expect(sub.edges.every((e) => ids.has(e.source) && ids.has(e.target))).toBe(true);
  });

  it('reports ids the loaded graph does not have yet', () => {
    const ev = { ...data.flow[0]!, created: [{ id: 'not-loaded', label: 'Fact' }] };
    expect(eventSubgraph(graph, ev).missing).toEqual(['not-loaded']);
  });
});
