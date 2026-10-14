import { describe, expect, it } from 'vitest';
import { createFixtureApi } from './client';
import { buildAcme } from './acme';

const data = buildAcme();
const api = createFixtureApi(data);

describe('fixture ViewApi', () => {
  it('lists tenants', async () => {
    const t = await api.tenants();
    expect(t.tenants.map((x) => x.graph)).toEqual(['plexus_t_acme', 'plexus_t_scratch']);
  });

  it('inventory counts match the dataset', async () => {
    const inv = await api.inventory('acme');
    expect(inv.node_total).toBe(data.nodes.length);
    expect(inv.edge_total).toBe(data.edges.length);
    expect(inv.labels.reduce((s, l) => s + l.count, 0)).toBe(data.nodes.length);
    expect(inv.edge_types.reduce((s, e) => s + e.count, 0)).toBe(data.edges.length);
    expect(inv.indexes.some((i) => i.kind === 'vector' && i.label === 'Fact')).toBe(true);
  });

  it('returns an empty graph for the scratch tenant', async () => {
    const g = await api.graph('scratch');
    expect(g.nodes).toHaveLength(0);
    expect((await api.inventory('scratch')).node_total).toBe(0);
  });

  it('filters the graph by label, window and limit', async () => {
    const facts = await api.graph('acme', { labels: ['Fact'] });
    expect(facts.nodes.every((n) => n.label === 'Fact')).toBe(true);
    expect(facts.nodes.length).toBeGreaterThan(30);
    const late = await api.graph('acme', { since: data.flow[data.flow.length - 3]!.at });
    expect(late.nodes.length).toBeGreaterThan(0);
    expect(late.nodes.length).toBeLessThan(10);
    expect((await api.graph('acme', { limit: 5 })).nodes).toHaveLength(5);
    const all = await api.graph('acme');
    const ids = new Set(all.nodes.map((n) => n.id));
    expect(all.edges.every((e) => ids.has(e.src) && ids.has(e.dst))).toBe(true);
  });

  it('serves flow events after a timestamp', async () => {
    const all = await api.flow('acme');
    const mid = all.events[10]!.at;
    const rest = await api.flow('acme', mid);
    expect(rest.events.length).toBe(all.events.filter((e) => e.at > mid).length);
  });

  it('answers what each agent knew at a step', async () => {
    const early = await api.step('acme', 5);
    const late = await api.step('acme', 22);
    const count = (k: Awaited<typeof early>, name: string) =>
      k.agents.find((a) => a.agent_name === name)!.knew.length;
    expect(count(late, 'planner')).toBeGreaterThan(count(early, 'planner'));
    const builder = late.agents.find((a) => a.agent_name === 'builder')!;
    expect(builder.knew).not.toContain(data.ids['f.v2']); // the builder has not read v2 by step 22
  });

  it('traces a decision back to facts, agents and sources', async () => {
    const why = await api.why('acme', data.ids['d.jwt']!);
    expect(why.paths.length).toBeGreaterThan(0);
    const labels = new Map(data.nodes.map((n) => [n.id, n.label]));
    const ends = new Set(why.paths.map((p) => labels.get(p.node_ids[p.node_ids.length - 1]!)));
    expect(ends.has('Source')).toBe(true);
    expect(ends.has('Agent')).toBe(true);
    for (const p of why.paths) expect(p.edge_ids).toHaveLength(p.node_ids.length - 1);
  });

  it('serves real query text for known query names', async () => {
    const q = await api.queryText('relay/claim_next_task');
    expect(q.text).toContain('MATCH');
    expect((await api.queryText('nope/x')).text).toContain('no fixture text');
  });
});
