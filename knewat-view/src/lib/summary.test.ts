import { describe, expect, it } from 'vitest';
import { buildAcme } from '../fixtures/acme';
import { createFixtureApi } from '../fixtures/client';
import { SUMMARY_LABELS, summarize } from './summary';

describe('summarize', () => {
  it('counts what the Acme demo created', async () => {
    const api = createFixtureApi(buildAcme());
    const inv = await api.inventory('acme');
    const sub = await api.graph('acme', { labels: SUMMARY_LABELS, limit: 2000 });
    const s = summarize(inv, sub);
    expect(s.agents).toBe(3);
    expect(s.tasks).toMatchObject({ total: 12, failed: 1 });
    expect(s.tasks.done).toBeGreaterThan(3);
    expect(s.tasks.reclaimed).toBe(1); // T7: claimed twice after the builder went silent
    expect(s.tasks.open + s.tasks.claimed + s.tasks.done + s.tasks.failed).toBe(12);
    expect(s.facts.superseded).toBeGreaterThanOrEqual(1);
    expect(s.facts.active + s.facts.superseded).toBe(s.facts.total);
    expect(s.facts.contradicting).toBeGreaterThanOrEqual(1);
    expect(s.decisions).toBeGreaterThanOrEqual(5);
    expect(s.handoffs).toBeGreaterThanOrEqual(4);
    expect(s.toolCalls).toBe(buildAcme().flow.length);
    expect(s.sampled).toBe(false);
  });

  it('is all zeros for an empty tenant', async () => {
    const api = createFixtureApi(buildAcme());
    const s = summarize(await api.inventory('scratch'), await api.graph('scratch'));
    expect(s.agents + s.decisions + s.handoffs + s.toolCalls + s.tasks.total + s.facts.total).toBe(0);
  });
});
