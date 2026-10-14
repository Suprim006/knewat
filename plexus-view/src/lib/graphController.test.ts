import type { NodeSingular } from 'cytoscape';
import { afterEach, describe, expect, it } from 'vitest';
import { createGraphController } from './graphController';
import { LABEL_COLORS, MODULE_COLORS } from './labels';
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
      data.edges.filter((e) => ids.has(e.source) && ids.has(e.target)),
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
      data.edges.filter((e) => earlyIds.has(e.source) && earlyIds.has(e.target)),
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
    const edge = { type: 'DEPENDS_ON', source: a.id, target: b.id };
    ctl.addLive([], [edge]);
    expect(ctl.counts().totalEdges).toBe(0);
    ctl.addLive([b], []);
    expect(ctl.counts().totalEdges).toBe(1);
  });

  describe('parallel edges (same source, target and type)', () => {
    const [a, b] = data.nodes.filter((n) => n.label === 'Task') as [
      (typeof data.nodes)[0],
      (typeof data.nodes)[0],
    ];
    const claimed = { type: 'CLAIMED', source: a.id, target: b.id };

    it('draws every one of them, keyed by (source, target, type, index)', () => {
      ctl = createGraphController({ headless: true });
      ctl.load([a, b], [claimed, claimed, claimed, { ...claimed, type: 'DEPENDS_ON' }]);
      expect(ctl.counts().totalEdges).toBe(4);
      expect(ctl.edgeTypeCounts()).toEqual({ CLAIMED: 3, DEPENDS_ON: 1 });
      const ids = ctl.cy.edges().map((e) => e.id());
      expect(new Set(ids).size).toBe(4);
      expect(ids).toContain(`${a.id}|CLAIMED|${b.id}|2`);
      // the default curve style spreads parallel edges apart instead of drawing them on top of each other
      expect(ctl.cy.edges().first().style('curve-style')).toBe('bezier');
    });

    it('a re-read adds only the extra parallel edge and is otherwise idempotent', () => {
      ctl = createGraphController({ headless: true });
      ctl.load([a, b], [claimed, claimed]);
      expect(ctl.addLive([a, b], [claimed, claimed])).toEqual([]);
      expect(ctl.counts().totalEdges).toBe(2);
      ctl.addLive([a, b], [claimed, claimed, claimed]);
      expect(ctl.counts().totalEdges).toBe(3);
      ctl.addLive([a, b], [claimed, claimed, claimed]);
      expect(ctl.counts().totalEdges).toBe(3);
    });

    it('parked parallel edges are all added once their endpoint arrives, and not parked twice', () => {
      ctl = createGraphController({ headless: true });
      ctl.load([a], []);
      ctl.addLive([], [claimed, claimed]);
      ctl.addLive([], [claimed, claimed]); // re-read while still parked
      expect(ctl.counts().totalEdges).toBe(0);
      ctl.addLive([b], []);
      expect(ctl.counts().totalEdges).toBe(2);
    });
  });

  it('updates properties of nodes already on the canvas without moving them', () => {
    ctl = createGraphController({ headless: true });
    const fact = data.nodes.find((n) => n.label === 'Fact')!;
    ctl.load([fact], []);
    const before = { ...ctl.cy.getElementById(fact.id).position() };
    const changed = ctl.updateProps([
      { ...fact, props: { ...fact.props, status: 'superseded', value: 'v9' } },
    ]);
    expect(changed).toBe(1);
    expect(ctl.describe(fact.id)!.props.status).toBe('superseded');
    expect(ctl.describe(fact.id)!.name).toContain('v9');
    expect(ctl.cy.getElementById(fact.id).position()).toEqual(before);
    expect(ctl.updateProps([fact, { ...fact, id: 'unknown' }])).toBe(1); // reverts the one known node
  });

  it('colours by label or by module', () => {
    ctl = createGraphController({ headless: true });
    const task = data.nodes.find((n) => n.label === 'Task')!;
    const fact = data.nodes.find((n) => n.label === 'Fact')!;
    ctl.load([task, fact], []);
    const color = (id: string) => String(ctl!.cy.getElementById(id).data('color'));
    expect(color(task.id)).not.toBe(color(fact.id));
    ctl.setColorMode('module');
    expect(color(task.id)).toBe(MODULE_COLORS.Relay);
    expect(color(fact.id)).toBe(MODULE_COLORS.Engram);
    ctl.addLive([data.nodes.find((n) => n.label === 'Decision')!], []);
    expect(color(data.nodes.find((n) => n.label === 'Decision')!.id)).toBe(MODULE_COLORS.Relay); // new nodes follow the mode
    ctl.setColorMode('label');
    expect(color(task.id)).toBe(LABEL_COLORS.Task);
  });

  it('filters by a created_at range and reports the bounds', () => {
    ctl = createGraphController({ headless: true });
    const facts = data.nodes.filter((n) => n.label === 'Fact');
    ctl.load(facts, []);
    const [lo, hi] = ctl.timeBounds()!;
    expect(lo).toBeLessThan(hi);
    const mid = Math.floor((lo + hi) / 2);
    ctl.setTimeRange([lo, mid]);
    const early = facts.filter((n) => Number(n.props.created_at) <= mid).length;
    expect(ctl.counts().visibleNodes).toBe(early);
    expect(ctl.counts().totalNodes).toBe(facts.length);
    ctl.setTimeRange([mid + 1, hi]);
    expect(ctl.counts().visibleNodes).toBe(facts.length - early);
    ctl.setTimeRange(null);
    expect(ctl.counts().visibleNodes).toBe(facts.length);
    expect(createGraphController({ headless: true }).timeBounds()).toBeNull();
  });

  it('focuses the 2-hop neighbourhood of a node and clears it', () => {
    ctl = createGraphController({ headless: true });
    const keep = data.nodes.filter((n) => n.label !== 'ToolCall' && n.label !== 'Step');
    const ids = new Set(keep.map((n) => n.id));
    ctl.load(
      keep,
      data.edges.filter((e) => ids.has(e.source) && ids.has(e.target)),
    );
    const total = ctl.counts().visibleNodes;
    const decision = data.ids['d.jwt']!;
    const one = ctl.focusNeighborhood(decision, 1);
    const two = ctl.focusNeighborhood(decision, 2);
    expect(ctl.focusedOn()).toBe(decision);
    expect(one).toBeGreaterThan(2);
    expect(two).toBeGreaterThan(one);
    expect(two).toBeLessThan(total);
    expect(ctl.counts().visibleNodes).toBe(two);
    // every focused node is within 2 hops
    const reach = ctl.cy.getElementById(decision).closedNeighborhood().closedNeighborhood().nodes();
    ctl.cy.nodes('.hide-label').forEach((n) => expect(reach.contains(n)).toBe(false));
    ctl.clearFocus();
    expect(ctl.focusedOn()).toBeNull();
    expect(ctl.counts().visibleNodes).toBe(total);
  });

  it('does not walk through hidden edge types when focusing', () => {
    ctl = createGraphController({ headless: true });
    const agentIds = new Set(['planner']);
    const nodes = data.nodes.filter(
      (n) => n.label === 'Decision' || agentIds.has(n.id) || n.label === 'Fact',
    );
    const ids = new Set(nodes.map((n) => n.id));
    ctl.load(
      nodes,
      data.edges.filter((e) => ids.has(e.source) && ids.has(e.target)),
    );
    const d = data.ids['d.jwt']!;
    ctl.setFilters({ hiddenLabels: new Set(), hiddenEdgeTypes: new Set(['BASED_ON']) });
    expect(ctl.focusNeighborhood(d, 2)).toBeLessThan(
      (ctl.clearFocus(),
      ctl.setFilters({ hiddenLabels: new Set(), hiddenEdgeTypes: new Set() }),
      ctl.focusNeighborhood(d, 2)),
    );
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
