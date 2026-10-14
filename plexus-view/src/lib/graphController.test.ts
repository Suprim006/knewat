import type { NodeSingular } from 'cytoscape';
import { afterEach, describe, expect, it } from 'vitest';
import { createGraphController } from './graphController';
import type { GraphController } from './graphController';
import { buildAcme } from '../fixtures/acme';

const data = buildAcme();
let ctl: GraphController | undefined;
afterEach(() => ctl?.destroy());

const noToolCalls = (n: { label: string }) => n.label !== 'ToolCall';

describe('graph controller (headless Cytoscape)', () => {
  it('loads a graph and lays it out once', () => {
    ctl = createGraphController({ headless: true });
    const nodes = data.nodes.filter(noToolCalls);
    const ids = new Set(nodes.map((n) => n.id));
    ctl.load(
      nodes,
      data.edges.filter((e) => ids.has(e.src) && ids.has(e.dst)),
    );
    const c = ctl.counts();
    expect(c.totalNodes).toBe(nodes.length);
    expect(c.visibleNodes).toBe(nodes.length);
    // positions are finite and not all identical
    const pos = ctl.cy.nodes().map((n) => n.position());
    expect(pos.every((p) => Number.isFinite(p.x) && Number.isFinite(p.y))).toBe(true);
    expect(new Set(pos.map((p) => `${Math.round(p.x)},${Math.round(p.y)}`)).size).toBeGreaterThan(
      nodes.length / 2,
    );
  });

  it('hides labels and edge types without removing elements', () => {
    ctl = createGraphController({ headless: true });
    ctl.load(data.nodes, data.edges);
    const total = ctl.counts();
    ctl.setFilters({ hiddenLabels: new Set(['ToolCall']), hiddenEdgeTypes: new Set() });
    const noTc = ctl.counts();
    expect(noTc.totalNodes).toBe(total.totalNodes);
    expect(noTc.visibleNodes).toBe(
      total.totalNodes - data.nodes.filter((n) => n.label === 'ToolCall').length,
    );
    expect(noTc.visibleEdges).toBeLessThan(total.visibleEdges);
    ctl.setFilters({
      hiddenLabels: new Set(['ToolCall']),
      hiddenEdgeTypes: new Set(['DERIVED_FROM', 'WROTE']),
    });
    expect(ctl.counts().visibleEdges).toBeLessThan(noTc.visibleEdges);
    ctl.setFilters({ hiddenLabels: new Set(), hiddenEdgeTypes: new Set() });
    expect(ctl.counts()).toEqual(total);
  });

  it('adds live nodes next to a neighbour and moves nothing else', () => {
    ctl = createGraphController({ headless: true });
    const cutoff = data.flow[data.flow.length - 8]!.at;
    const early = data.nodes.filter((n) => Number(n.props.created_at) < cutoff);
    const earlyIds = new Set(early.map((n) => n.id));
    ctl.load(
      early,
      data.edges.filter((e) => earlyIds.has(e.src) && earlyIds.has(e.dst)),
    );
    const before = new Map(ctl.cy.nodes().map((n) => [n.id(), { ...n.position() }]));
    const late = data.nodes.filter((n) => !earlyIds.has(n.id));
    const added = ctl.addLive(late, data.edges);
    expect(added.sort()).toEqual(late.map((n) => n.id).sort());
    for (const [id, p] of before) expect(ctl.cy.getElementById(id).position()).toEqual(p);
    // every new node sits within reach of a neighbour or the cluster, not at the origin by accident
    for (const id of added) {
      const n = ctl.cy.getElementById(id) as NodeSingular;
      const nbs = n.neighborhood('node').nodes();
      expect(nbs.length).toBeGreaterThan(0);
      const near = nbs
        .toArray()
        .some((m) => Math.hypot(m.position().x - n.position().x, m.position().y - n.position().y) < 400);
      expect(near).toBe(true);
    }
    expect(ctl.addLive(late, data.edges)).toEqual([]); // idempotent
  });

  it('parks edges whose endpoint has not arrived yet', () => {
    ctl = createGraphController({ headless: true });
    const [a, b] = data.nodes.filter((n) => n.label === 'Task') as [
      (typeof data.nodes)[0],
      (typeof data.nodes)[0],
    ];
    ctl.load([a], []);
    const edge = { id: 'e1', type: 'DEPENDS_ON', src: a.id, dst: b.id, props: {} };
    ctl.addLive([], [edge]);
    expect(ctl.counts().totalEdges).toBe(0);
    ctl.addLive([b], []);
    expect(ctl.counts().totalEdges).toBe(1);
  });

  it('searches names and property values', () => {
    ctl = createGraphController({ headless: true });
    ctl.load(data.nodes, data.edges);
    const jwt = ctl.setSearch('jwt');
    expect(jwt.length).toBeGreaterThan(3);
    expect(ctl.cy.nodes('.match').length).toBeGreaterThanOrEqual(jwt.length);
    expect(ctl.setSearch('')).toEqual([]);
    expect(ctl.cy.elements('.dim').length).toBe(0);
    expect(ctl.setSearch('zzzz-no-match')).toEqual([]);
  });

  it('describes a node with props and typed neighbours, and selects/fades', () => {
    ctl = createGraphController({ headless: true });
    ctl.load(data.nodes, data.edges);
    const d = ctl.describe(data.ids['d.jwt']!)!;
    expect(d.label).toBe('Decision');
    expect(d.props.text).toBe('Authenticate with JWT bearer tokens');
    expect(d.neighbors.filter((n) => n.type === 'BASED_ON' && n.direction === 'out')).toHaveLength(2);
    expect(
      d.neighbors.some((n) => n.type === 'DECIDED' && n.direction === 'in' && n.name === 'planner'),
    ).toBe(true);
    ctl.select(d.id);
    expect(ctl.cy.nodes('.sel')).toHaveLength(1);
    expect(ctl.cy.elements('.faded').length).toBeGreaterThan(100);
    ctl.select(null);
    expect(ctl.cy.elements('.faded')).toHaveLength(0);
  });

  it('highlights a path and clears it', () => {
    ctl = createGraphController({ headless: true });
    ctl.load(data.nodes, data.edges);
    ctl.highlightPath([data.ids['d.jwt']!, data.ids['f.jwt']!, data.ids['s.rfc']!]);
    expect(ctl.cy.nodes('.path')).toHaveLength(3);
    expect(ctl.cy.edges('.path').length).toBeGreaterThanOrEqual(2);
    ctl.clearHighlight();
    expect(ctl.cy.elements('.path, .faded')).toHaveLength(0);
  });

  it('removes nodes created since a timestamp', () => {
    ctl = createGraphController({ headless: true });
    ctl.load(data.nodes, data.edges);
    const ts = data.flow[data.flow.length - 5]!.at;
    const expected = data.nodes.filter((n) => Number(n.props.created_at) >= ts).length;
    expect(ctl.removeCreatedSince(ts)).toBe(expected);
  });
});
