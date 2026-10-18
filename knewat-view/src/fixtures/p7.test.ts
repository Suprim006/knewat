import { describe, expect, it } from 'vitest';
import { buildAcme } from './acme';
import { createFixtureApi } from './client';
import { applyP7 } from './p7';
import { EDGE_TYPES, NODE_LABELS, OPEN } from '../api/types';
import { isSuspectAt } from '../lib/memory';

const base = buildAcme();
const data = applyP7(base);
const facts = data.nodes.filter((n) => n.label === 'Fact');
const api = createFixtureApi(data);
const now = () => Date.now();

describe('Acme + P7 fixture', () => {
  it('is deterministic and does not mutate the base dataset', () => {
    expect(applyP7(buildAcme())).toEqual(data);
    expect(base.nodes.find((n) => n.id === base.ids['f.jwt'])!.props).not.toHaveProperty('verify_state');
    expect(base.nodes.some((n) => n.label === 'Change')).toBe(false);
  });

  it('has suspect (by change and by review date), pinned, dormant and high-surprise facts', () => {
    expect(facts.filter((f) => f.props.verify_state === 'suspect').length).toBeGreaterThanOrEqual(2);
    expect(facts.filter((f) => isSuspectAt(f.props, now())).length).toBeGreaterThanOrEqual(3);
    expect(facts.filter((f) => f.props.pinned === true).length).toBeGreaterThanOrEqual(1);
    expect(facts.filter((f) => f.props.status === 'dormant').length).toBeGreaterThanOrEqual(2);
    expect(facts.filter((f) => Number(f.props.surprise) >= 0.7).length).toBeGreaterThanOrEqual(1);
  });

  it('gives every fact the always-present P7 fields and a spread of activations', () => {
    for (const f of facts) {
      expect(['verified', 'suspect']).toContain(f.props.verify_state);
      expect(typeof f.props.suspect_since).toBe('number');
      expect(typeof f.props.surprise).toBe('number');
      expect(typeof f.props.pinned).toBe('boolean');
      expect(typeof f.props.protected).toBe('boolean');
      expect(typeof f.props.activation).toBe('number');
    }
    const a = facts.map((f) => Number(f.props.activation)).sort((x, y) => x - y);
    expect(a[a.length - 1]! - a[0]!).toBeGreaterThan(3);
  });

  it('adds Change and CodeAnchor nodes that follow the model', () => {
    const ids = new Set(data.nodes.map((n) => n.id));
    expect(ids.size).toBe(data.nodes.length);
    expect(data.nodes.filter((n) => n.label === 'Change').length).toBeGreaterThanOrEqual(1);
    expect(data.nodes.filter((n) => n.label === 'CodeAnchor').length).toBeGreaterThanOrEqual(2);
    for (const n of data.nodes) expect(NODE_LABELS as readonly string[]).toContain(n.label);
    for (const e of data.edges) {
      expect(EDGE_TYPES as readonly string[]).toContain(e.type);
      expect(ids.has(e.source) && ids.has(e.target)).toBe(true);
    }
    expect(data.edges.some((e) => e.type === 'SUSPECTED')).toBe(true);
    expect(data.edges.some((e) => e.type === 'ANCHORED_TO')).toBe(true);
    expect(data.edges.some((e) => e.type === 'DESCRIBES')).toBe(true);
  });
});

describe('fixture ViewApi (P7)', () => {
  it('inventory carries the memory counts of the dataset', async () => {
    const inv = await api.inventory('acme');
    expect(inv.dormant_facts).toBe(facts.filter((f) => f.props.status === 'dormant').length);
    expect(inv.pinned_facts).toBe(facts.filter((f) => f.props.pinned === true).length);
    expect(inv.suspect_facts).toBe(
      facts.filter((f) => f.props.status === 'active' && isSuspectAt(f.props, now())).length,
    );
    expect(inv.changes).toBe(data.nodes.filter((n) => n.label === 'Change').length);
    expect(inv.code_anchors).toBe(data.nodes.filter((n) => n.label === 'CodeAnchor').length);
    expect(inv.nodes_total).toBe(data.nodes.length);
  });

  it('verify-queue lists the suspect facts: most decisions at risk first, then activation', async () => {
    const { rows } = await api.verifyQueue('acme');
    expect(rows.length).toBeGreaterThanOrEqual(3);
    const sorted = [...rows].sort(
      (a, b) =>
        b.decisions_count - a.decisions_count ||
        (b.activation ?? -Infinity) - (a.activation ?? -Infinity) ||
        a.suspect_since - b.suspect_since,
    );
    expect(rows.map((r) => r.fact_id)).toEqual(sorted.map((r) => r.fact_id));
    const jwt = rows.find((r) => r.fact_id === data.ids['f.jwt'])!;
    expect(jwt.decisions_count).toBe(2);
    expect(jwt.verify_state).toBe('suspect');
    expect(jwt.reason).toMatch(/^changed in [0-9a-f]{7} \(/);
    expect(jwt.change?.paths.length).toBeGreaterThan(0);
    expect(jwt.anchors.length).toBeGreaterThan(0);
    expect(rows.some((r) => r.verify_state === 'verified' && r.reason === 'review date passed')).toBe(true);
    expect((await api.verifyQueue('acme', { limit: 1 })).rows).toHaveLength(1);
    expect((await api.verifyQueue('scratch')).rows).toEqual([]);
  });

  it('docs-to-update lists the doc whose code changed after it was edited', async () => {
    const { docs } = await api.docsToUpdate('acme');
    expect(docs).toHaveLength(1);
    expect(docs[0]!.uri).toMatch(/rfc-0042-auth\.md$/);
    expect(docs[0]!.changes[0]!.paths.length).toBeGreaterThan(0);
    expect(docs[0]!.latest).toBe(docs[0]!.changes[0]!.at);
    expect((await api.docsToUpdate('acme', { since: OPEN - 1 })).docs).toEqual([]);
    expect((await api.docsToUpdate('scratch')).docs).toEqual([]);
  });

  it('memory-strength explains a fact and rejects an unknown id with 404', async () => {
    const s = await api.memoryStrength('acme', data.ids['f.lang']!);
    expect(s.pinned).toBe(true);
    expect(s.protected).toBe(true);
    expect(s.protect_reasons).toContain('pinned');
    expect(s.activation).toBe(Number(data.nodes.find((n) => n.id === data.ids['f.lang'])!.props.activation));
    expect(s.explanation.length).toBeGreaterThan(10);
    expect(s.forgetting).toBe(true);
    const suspect = await api.memoryStrength('acme', data.ids['f.jwt']!);
    expect(suspect.verify_state).toBe('suspect');
    expect(suspect.suspect_since).toBeGreaterThan(0);
    expect(suspect.counts.decision).toBe(2);
    await expect(api.memoryStrength('acme', 'nope')).rejects.toMatchObject({ status: 404 });
  });
});
