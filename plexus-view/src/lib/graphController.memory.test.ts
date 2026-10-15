import { afterEach, describe, expect, it } from 'vitest';
import { applyP7 } from '../fixtures/p7';
import { buildAcme } from '../fixtures/acme';
import { createGraphController } from './graphController';
import type { GraphController } from './graphController';
import { activationOpacity, medianActivation } from './memory';

const data = applyP7(buildAcme());
const T_NOW = Date.now();
let ctl: GraphController | undefined;
afterEach(() => ctl?.destroy());

const facts = data.nodes.filter((n) => n.label === 'Fact');
const idOf = (k: string) => data.ids[k]!;
const load = (opts: Parameters<typeof createGraphController>[0] = {}) => {
  ctl = createGraphController({ headless: true, now: () => T_NOW, ...opts });
  ctl.load(data.nodes, data.edges);
  return ctl;
};
const node = (c: GraphController, key: string) => c.cy.getElementById(idOf(key));

describe('graph controller: staleness and forgetting markers', () => {
  it('puts a ⚠ badge and the reason in the tooltip of a suspect fact', () => {
    const c = load();
    const jwt = node(c, 'f.jwt');
    expect(jwt.data('suspect')).toBe(true);
    expect(String(jwt.data('display'))).toMatch(/^⚠ /);
    expect(String(jwt.data('display'))).toContain(String(jwt.data('name')));
    expect(String(jwt.data('tip'))).toMatch(/suspect/);
    // a verified fact has no badge
    expect(node(c, 'f.ttl').data('suspect')).toBe(true);
    expect(node(c, 'f.size').data('suspect')).toBe(false);
    expect(String(node(c, 'f.size').data('display'))).toBe(String(node(c, 'f.size').data('name')));
  });

  it('marks a fact whose review date passed as suspect too', () => {
    const c = load();
    expect(node(c, 'f.ci').data('suspect')).toBe(true);
    expect(String(node(c, 'f.ci').data('tip'))).toMatch(/review date passed/);
  });

  it('is time-aware: before the clock reaches suspect_since there is no badge', () => {
    const since = Number(facts.find((f) => f.id === idOf('f.jwt'))!.props.suspect_since);
    const c = load({ now: () => since - 1 });
    expect(node(c, 'f.jwt').data('suspect')).toBe(false);
  });

  it('adds a pin glyph to a pinned fact and a dashed outline to a dormant one', () => {
    const c = load();
    expect(String(node(c, 'f.lang').data('display'))).toContain('📌');
    expect(node(c, 'f.lang').data('pinned')).toBe(true);
    const sqlite = node(c, 'f.sqlite');
    expect(sqlite.data('dormant')).toBe(true);
    expect(sqlite.style('border-style')).toBe('dashed');
    expect(node(c, 'f.size').style('border-style')).toBe('solid');
  });

  it('sets opacity = 0.35 + 0.65·σ(activation − A0) with A0 the median of the response', () => {
    const c = load();
    const a0 = medianActivation(data.nodes)!;
    const hot = node(c, 'f.jwt');
    const cold = node(c, 'f.sqlite');
    expect(hot.data('opacity')).toBeCloseTo(activationOpacity(1.4, a0), 10);
    expect(cold.data('opacity')).toBeCloseTo(activationOpacity(-4.2, a0), 10);
    expect(Number(hot.data('opacity'))).toBeGreaterThan(Number(cold.data('opacity')));
    expect(Number(cold.style('opacity'))).toBeGreaterThanOrEqual(0.35);
    expect(Number(cold.style('opacity'))).toBeLessThan(0.5);
    expect(Number(hot.style('opacity'))).toBeGreaterThan(0.85);
  });

  it('uses the A0 the API sends in preference to the median', () => {
    const c = load();
    c.setActivationCenter(3);
    expect(node(c, 'f.jwt').data('opacity')).toBeCloseTo(activationOpacity(1.4, 3), 10);
    c.setActivationCenter(null);
    expect(node(c, 'f.jwt').data('opacity')).toBeCloseTo(
      activationOpacity(1.4, medianActivation(data.nodes)!),
      10,
    );
  });

  it('does not touch the opacity of nodes with no activation (old tenants, other labels)', () => {
    const c = load();
    const agent = c.cy.getElementById('planner');
    expect(agent.data('opacity')).toBeUndefined();
    expect(Number(agent.style('opacity'))).toBe(1);
    ctl?.destroy();
    ctl = createGraphController({ headless: true });
    ctl.load(buildAcme().nodes, buildAcme().edges);
    expect(ctl.memoryCounts()).toEqual({ suspect: 0, pinned: 0, dormant: 0, faded: 0 });
    expect(ctl.cy.nodes().filter((n) => n.data('opacity') !== undefined)).toHaveLength(0);
  });

  it('counts the markers for the legend', () => {
    const c = load();
    const m = c.memoryCounts();
    expect(m.suspect).toBeGreaterThanOrEqual(5);
    expect(m.pinned).toBe(facts.filter((f) => f.props.pinned === true).length);
    expect(m.dormant).toBe(facts.filter((f) => f.props.status === 'dormant').length);
    expect(m.faded).toBe(facts.length);
  });

  it('takes better reasons from the verify queue (commit and path)', () => {
    const c = load();
    c.setSuspectReasons(new Map([[idOf('f.jwt'), 'changed in a1b2c3d (C:/acme-notes/app/auth/jwt.py)']]));
    expect(String(node(c, 'f.jwt').data('tip'))).toContain('changed in a1b2c3d');
  });

  it('refreshes the markers when a live read changes a fact (updateProps)', () => {
    const c = load();
    const jwt = data.nodes.find((n) => n.id === idOf('f.jwt'))!;
    const verified = { ...jwt, props: { ...jwt.props, verify_state: 'verified', suspect_since: 0 } };
    expect(c.updateProps([verified])).toBe(1);
    expect(node(c, 'f.jwt').data('suspect')).toBe(false);
    expect(String(node(c, 'f.jwt').data('display'))).not.toContain('⚠');
  });

  it('dims by activation but the selected neighbourhood stays fully opaque', () => {
    const c = load();
    c.select(idOf('f.sqlite'));
    expect(Number(node(c, 'f.sqlite').style('opacity'))).toBe(1);
  });
});
