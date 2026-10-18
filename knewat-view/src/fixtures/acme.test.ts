import { describe, expect, it } from 'vitest';
import { buildAcme } from './acme';
import { EDGE_TYPES, NODE_LABELS, OPEN, edgeId } from '../api/types';

const data = buildAcme();
const byLabel = (l: string) => data.nodes.filter((n) => n.label === l);

describe('Acme Notes fixture follows graph model v1', () => {
  it('is deterministic', () => {
    expect(buildAcme()).toEqual(data);
  });

  it('has the expected population', () => {
    expect(byLabel('Agent').map((a) => a.props.name)).toEqual(['planner', 'researcher', 'builder']);
    expect(byLabel('Task')).toHaveLength(12);
    expect(byLabel('Fact').length).toBeGreaterThanOrEqual(38);
    expect(byLabel('Fact').length).toBeLessThanOrEqual(46);
    expect(byLabel('Step')).toHaveLength(30);
    expect(byLabel('ToolCall').length).toBeGreaterThanOrEqual(60);
    expect(data.flow).toHaveLength(byLabel('ToolCall').length);
    expect(byLabel('Decision').length).toBeGreaterThanOrEqual(5);
    expect(byLabel('Handoff').length).toBeGreaterThanOrEqual(4);
  });

  it('uses only labels and edge types from the model, with unique ids and no dangling edges', () => {
    const ids = new Set(data.nodes.map((n) => n.id));
    expect(ids.size).toBe(data.nodes.length);
    // the API gives edges no id: parallel same-type edges (a re-claimed task) are the only repeats
    const dupes = data.edges.length - new Set(data.edges.map(edgeId)).size;
    expect(dupes).toBeGreaterThanOrEqual(1);
    expect(dupes).toBeLessThanOrEqual(3);
    for (const n of data.nodes) expect(NODE_LABELS as readonly string[]).toContain(n.label);
    for (const e of data.edges) {
      expect(EDGE_TYPES as readonly string[]).toContain(e.type);
      expect(ids.has(e.source)).toBe(true);
      expect(ids.has(e.target)).toBe(true);
    }
  });

  it('gives every node an id and created_at, and no null/map properties', () => {
    for (const n of data.nodes) {
      expect(typeof n.props.created_at).toBe('number');
      for (const v of Object.values(n.props)) {
        expect(v).not.toBeNull();
        expect(v).not.toBeUndefined();
        expect(Array.isArray(v) || typeof v !== 'object').toBe(true);
      }
    }
  });

  it('models the v1 -> v2 supersede', () => {
    const v1 = data.nodes.find((n) => n.id === data.ids['f.v1'])!;
    const v2 = data.nodes.find((n) => n.id === data.ids['f.v2'])!;
    expect(v1.props.status).toBe('superseded');
    expect(v1.props.valid_to).toBe(v2.props.valid_from);
    expect(v2.props.valid_to).toBe(OPEN);
    expect(data.edges).toContainEqual(
      expect.objectContaining({ type: 'SUPERSEDES', source: v2.id, target: v1.id }),
    );
  });

  it('models the JWT vs API key contradiction', () => {
    const jwt = data.ids['f.jwt'];
    const key = data.ids['f.apikey'];
    expect(data.edges).toContainEqual(
      expect.objectContaining({ type: 'CONTRADICTS', source: key, target: jwt }),
    );
    const decision = data.edges.filter((e) => e.type === 'BASED_ON' && e.source === data.ids['d.jwt']);
    expect(decision.map((e) => e.target)).toContain(jwt);
  });

  it('ties every fact to an entity, scope and agent, and every ToolCall to a step', () => {
    for (const f of byLabel('Fact')) {
      for (const t of ['ABOUT', 'IN_SCOPE', 'ASSERTED_BY']) {
        expect(data.edges.filter((e) => e.source === f.id && e.type === t)).toHaveLength(1);
      }
      expect(f.props.subject_id).toBe(
        data.edges.find((e) => e.source === f.id && e.type === 'ABOUT')!.target,
      );
    }
    for (const tc of byLabel('ToolCall')) {
      expect(data.edges.filter((e) => e.source === tc.id && e.type === 'IN_STEP')).toHaveLength(1);
    }
  });

  it('has a task DAG with a failed task and a reclaimed lease', () => {
    const status = (k: string) => data.nodes.find((n) => n.id === data.ids[k])!.props.status;
    expect(status('t.9')).toBe('failed');
    expect(status('t.7')).toBe('done');
    expect(status('t.8')).toBe('claimed');
    expect(data.edges.filter((e) => e.type === 'DEPENDS_ON')).toHaveLength(16);
    expect(data.edges.filter((e) => e.type === 'CLAIMED' && e.target === data.ids['t.7'])).toHaveLength(2);
  });

  it('reports created and updated ids on flow events, ordered by time', () => {
    const ats = data.flow.map((f) => f.at);
    expect([...ats].sort((a, b) => a - b)).toEqual(ats);
    const ids = new Set(data.nodes.map((n) => n.id));
    for (const ev of data.flow)
      for (const r of [...ev.created, ...ev.updated]) expect(ids.has(r.id)).toBe(true);
    expect(data.flow.find((f) => f.tool === 'assert_fact' && f.created.length > 0)).toBeTruthy();
  });

  it('gives flow events the real API fields and per-agent step numbers', () => {
    const byId = new Map(data.nodes.map((n) => [n.id, n]));
    for (const ev of data.flow) {
      expect(typeof ev.wrote).toBe('boolean');
      expect(ev.step).toBeNull();
      const step = byId.get(ev.step_id!)!;
      expect(step.label).toBe('Step');
      expect(step.props.n).toBe(ev.step_n);
      expect(step.props.agent_id).toBe(ev.agent_id);
      for (const r of ev.created) expect(byId.get(r.id)!.label).toBe(r.label);
    }
    // Each agent's steps are numbered 1..k with no gaps.
    for (const agent of ['planner', 'researcher', 'builder']) {
      const ns = data.steps.filter((s) => s.agent_id === agent).map((s) => s.n);
      expect(ns).toEqual(ns.map((_, i) => i + 1));
    }
  });
});
