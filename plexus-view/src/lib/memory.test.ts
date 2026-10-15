import { describe, expect, it } from 'vitest';
import { OPEN } from '../api/types';
import type { GraphNode } from '../api/types';
import {
  activationOpacity,
  factMemory,
  isSuspectAt,
  medianActivation,
  memoryNodeData,
  sigmoid,
  strengthCounts,
  suspectReason,
} from './memory';

const T = 1_792_100_000_000;
const fact = (props: GraphNode['props']): GraphNode => ({ id: 'f1', label: 'Fact', props });

describe('isSuspectAt', () => {
  it('follows the contract rule: verify_state suspect OR a review date that has passed', () => {
    expect(isSuspectAt({ verify_state: 'suspect', suspect_since: T - 5 }, T)).toBe(true);
    expect(isSuspectAt({ verify_state: 'verified', suspect_since: 0 }, T)).toBe(false);
    expect(isSuspectAt({ verify_after: T - 1 }, T)).toBe(true);
    expect(isSuspectAt({ verify_after: T + 1 }, T)).toBe(false);
    expect(isSuspectAt({ verify_after: OPEN }, T)).toBe(false);
  });
  it('is time-aware: suspect only once the clock has reached suspect_since', () => {
    const p = { verify_state: 'suspect', suspect_since: T };
    expect(isSuspectAt(p, T - 1)).toBe(false);
    expect(isSuspectAt(p, T)).toBe(true);
    expect(isSuspectAt(p, T + 1)).toBe(true);
  });
  it('treats missing fields (a tenant without P7 data) as not suspect', () => {
    expect(isSuspectAt({}, T)).toBe(false);
    expect(isSuspectAt({ status: 'active' }, T)).toBe(false);
  });
  it('does not flag superseded or forgotten facts', () => {
    expect(isSuspectAt({ verify_state: 'suspect', suspect_since: 1, status: 'superseded' }, T)).toBe(false);
    expect(isSuspectAt({ verify_state: 'suspect', suspect_since: 1, status: 'forgotten' }, T)).toBe(false);
    expect(isSuspectAt({ verify_state: 'suspect', suspect_since: 1, status: 'dormant' }, T)).toBe(true);
  });
});

describe('suspectReason', () => {
  it('names the change when the code moved and the date when a review date passed', () => {
    expect(suspectReason({ verify_state: 'suspect', suspect_since: T })).toMatch(/^changed code .*2026/);
    expect(suspectReason({ verify_state: 'verified', verify_after: T })).toMatch(/^review date passed .*2026/);
  });
});

describe('factMemory', () => {
  it('reads the badges from a fact', () => {
    const m = factMemory(
      { verify_state: 'suspect', suspect_since: T - 1, pinned: true, status: 'dormant', activation: -1.5, protected: true, surprise: 0.8 },
      T,
    );
    expect(m).toMatchObject({
      suspect: true,
      pinned: true,
      dormant: true,
      activation: -1.5,
      protected: true,
      surprise: 0.8,
    });
  });
  it('has no badges and no activation for a plain fact', () => {
    expect(factMemory({ status: 'active' }, T)).toMatchObject({
      suspect: false,
      pinned: false,
      dormant: false,
      activation: null,
      protected: false,
    });
  });
  it('prefers a reason from the verify queue over the generic one', () => {
    const m = factMemory({ verify_state: 'suspect', suspect_since: 1 }, T, 'changed in a1b2c3d (app/auth.py)');
    expect(m.reason).toBe('changed in a1b2c3d (app/auth.py)');
  });
});

describe('activationOpacity', () => {
  it('is 0.35 + 0.65·σ(a − a0)', () => {
    expect(activationOpacity(0, 0)).toBeCloseTo(0.35 + 0.65 * 0.5, 10);
    expect(activationOpacity(3, 0)).toBeCloseTo(0.35 + 0.65 * sigmoid(3), 10);
    expect(activationOpacity(-3, 0)).toBeCloseTo(0.35 + 0.65 * sigmoid(-3), 10);
  });
  it('stays within [0.35, 1]', () => {
    expect(activationOpacity(-1e9, 0)).toBeGreaterThanOrEqual(0.35);
    expect(activationOpacity(1e9, 0)).toBeLessThanOrEqual(1);
  });
});

describe('medianActivation', () => {
  it('is the median over facts that report an activation', () => {
    const nodes = [fact({ activation: 1 }), fact({ activation: -3 }), fact({ activation: 5 }), fact({})];
    expect(medianActivation(nodes)).toBe(1);
    expect(medianActivation([...nodes, fact({ activation: 7 })])).toBe(3);
  });
  it('is null when there is no activation to centre on', () => {
    expect(medianActivation([fact({}), { id: 'a', label: 'Agent', props: { activation: 3 } }])).toBeNull();
  });
});

describe('memoryNodeData', () => {
  it('adds glyphs to the label, a tooltip with the reason and an opacity', () => {
    const d = memoryNodeData(
      fact({ verify_state: 'suspect', suspect_since: T - 1, pinned: true, activation: 1 }),
      'api_version: v1',
      { now: T, a0: 0, reasons: new Map([['f1', 'changed in abc1234 (app/x.py)']]) },
    );
    expect(d.display).toBe('⚠ 📌 api_version: v1');
    expect(d.suspect).toBe(true);
    expect(d.pinned).toBe(true);
    expect(d.dormant).toBe(false);
    expect(d.tip).toContain('changed in abc1234 (app/x.py)');
    expect(d.opacity).toBeCloseTo(activationOpacity(1, 0), 10);
  });
  it('leaves non-facts and plain facts untouched (no opacity, no glyph)', () => {
    const plain = memoryNodeData(fact({ status: 'active' }), 'x: y', { now: T, a0: 0 });
    expect(plain).toMatchObject({ display: 'x: y', suspect: false, pinned: false, dormant: false });
    expect(plain.opacity).toBeUndefined();
    const other = memoryNodeData({ id: 'a', label: 'Agent', props: { activation: 3 } }, 'planner', {
      now: T,
      a0: 0,
    });
    expect(other).toMatchObject({ display: 'planner' });
    expect(other.opacity).toBeUndefined();
  });
  it('marks dormant facts and keeps them visible', () => {
    const d = memoryNodeData(fact({ status: 'dormant' }), 'x: y', { now: T, a0: 0 });
    expect(d.dormant).toBe(true);
    expect(d.tip).toMatch(/dormant/);
  });
});

describe('strengthCounts', () => {
  it('summarises the events as "n kind" in the order of the contract and drops zeros', () => {
    expect(strengthCounts({ create: 1, reassert: 0, decision: 2, use: 3, recall: 0, verified: 1, handoff: 0 })).toBe(
      '1 creation, 2 decisions, 3 uses, 1 verification',
    );
    expect(strengthCounts({})).toBe('no events');
  });
});
