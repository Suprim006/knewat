import { describe, expect, it } from 'vitest';
import { createFixtureApi } from './client';
import { buildAcme } from './acme';

const data = buildAcme();
const api = createFixtureApi(data);

describe('fixture ViewApi', () => {
  it('lists tenants', async () => {
    const t = await api.tenants();
    expect(t.tenants.map((x) => x.graph)).toEqual(['knewat_t_acme', 'knewat_t_scratch']);
  });

  it('inventory counts match the dataset', async () => {
    const inv = await api.inventory('acme');
    expect(inv.nodes_total).toBe(data.nodes.length);
    expect(inv.edges_total).toBe(data.edges.length);
    expect(inv.labels.reduce((s, l) => s + l.count, 0)).toBe(data.nodes.length);
    expect(inv.edge_types.reduce((s, e) => s + e.count, 0)).toBe(data.edges.length);
    expect(inv.indexes.find((i) => i.label === 'Fact')?.types.embedding).toEqual(['VECTOR']);
  });

  it('returns an empty graph for the scratch tenant', async () => {
    const g = await api.graph('scratch');
    expect(g.nodes).toHaveLength(0);
    expect((await api.inventory('scratch')).nodes_total).toBe(0);
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
    expect(all.edges.every((e) => ids.has(e.source) && ids.has(e.target))).toBe(true);
  });

  it('serves flow events after a timestamp', async () => {
    const all = await api.flow('acme');
    const mid = all.events[10]!.at;
    const rest = await api.flow('acme', mid);
    expect(rest.events.length).toBe(all.events.filter((e) => e.at > mid).length);
  });

  it('answers what each agent knew at a step (per-agent step numbers)', async () => {
    const early = await api.step('acme', 2);
    const late = await api.step('acme', 100);
    const read = (r: Awaited<typeof early>, agent: string) =>
      r.agents.find((a) => a.agent_id === agent)!.read;
    expect(early.agents.map((a) => a.agent_id)).toEqual(['builder', 'planner', 'researcher']);
    expect(early.agents.every((a) => a.step_n <= 2)).toBe(true);
    expect(read(late, 'planner').length).toBeGreaterThan(read(early, 'planner').length);
    // the superseded v1 is no longer valid at the end, so nobody still "knows" it
    for (const a of late.agents) expect(a.read.map((f) => f.id)).not.toContain(data.ids['f.v1']);
    expect((await api.step('acme', 0)).agents).toHaveLength(0);
  });

  it('traces a decision back to facts, agents, steps and sources in the Why shape', async () => {
    const why = await api.why('acme', data.ids['d.jwt']!);
    const r = why.result;
    expect(r.root).toBe(data.ids['d.jwt']);
    expect(r.kind).toBe('Decision');
    expect(r.facts.map((f) => f.id)).toContain(data.ids['f.jwt']);
    expect(r.sources.length).toBeGreaterThan(0);
    expect(r.agents.length).toBeGreaterThan(0);
    expect(r.paths.length).toBeGreaterThan(0);
    for (const p of r.paths) expect(p[0]!.from).toBe(r.root);
    const ids = new Set(r.nodes.map((n) => n.id));
    for (const e of r.edges) expect(ids.has(e.from) && ids.has(e.to)).toBe(true);
    await expect(api.why('acme', 'nope')).rejects.toMatchObject({ status: 404 });
  });

  it('has no results until the Crucible produces them', async () => {
    await expect(api.results()).rejects.toMatchObject({ status: 404 });
    await expect(createFixtureApi(data, { l1: [] }).results()).resolves.toEqual({ l1: [] });
  });

  it('serves real query text for known query names', async () => {
    const q = await api.queryText('relay/claim_next_task');
    expect(q.text).toContain('MATCH');
    expect(q.mode).toBe('rw');
    expect(q.purpose).toContain('claim');
    expect(q.params.agent).toBe('str');
    expect((await api.queryText('nope/x')).text).toContain('no fixture text');
  });
});
