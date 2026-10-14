import { afterEach, describe, expect, it } from 'vitest';
import { buildAcme } from '../fixtures/acme';
import { eventSubgraph } from './eventGraph';
import { createGraphController, LAYOUT_OPTIONS, MINI_CONTROLLER_OPTIONS } from './graphController';
import type { GraphController } from './graphController';

const data = buildAcme();
let ctl: GraphController | undefined;
afterEach(() => ctl?.destroy());

interface Box {
  id: string;
  x1: number;
  y1: number;
  x2: number;
  y2: number;
}

/** Each node's circle and its label (drawn under the node, centred, ~5.5 px per char, capped at the max width). */
function boxes(c: GraphController, maxLabelWidth: number): { dots: Box[]; labels: Box[] } {
  const dots: Box[] = [];
  const labels: Box[] = [];
  c.cy.nodes().forEach((n) => {
    const p = n.position();
    const r = Number(n.data('size')) / 2;
    const w = Math.min(maxLabelWidth, String(n.data('name')).length * 5.5);
    dots.push({ id: n.id(), x1: p.x - r, y1: p.y - r, x2: p.x + r, y2: p.y + r });
    labels.push({ id: n.id(), x1: p.x - w / 2, y1: p.y + r + 3, x2: p.x + w / 2, y2: p.y + r + 15 });
  });
  return { dots, labels };
}
const hit = (a: Box, b: Box) => a.x1 < b.x2 && b.x1 < a.x2 && a.y1 < b.y2 && b.y1 < a.y2;

function overlaps(c: GraphController, maxLabelWidth: number): number {
  const { dots, labels } = boxes(c, maxLabelWidth);
  let n = 0;
  for (const l of labels) {
    for (const o of labels) if (l.id < o.id && hit(l, o)) n++;
    for (const d of dots) if (d.id !== l.id && hit(l, d)) n++;
  }
  return n;
}

// The ten busiest events of the demo data (most nodes in their mini-graph).
const busiest = data.flow
  .map((ev) => eventSubgraph({ nodes: data.nodes, edges: data.edges }, ev))
  .sort((a, b) => b.nodes.length - a.nodes.length)
  .slice(0, 10);

describe('Flow mini-graph layout', () => {
  it('uses a roomier layout and shorter labels than the main canvas', () => {
    expect(MINI_CONTROLLER_OPTIONS.labelMaxWidth).toBeLessThan(110);
    expect(MINI_CONTROLLER_OPTIONS.layout?.nodeRepulsion).toBeGreaterThan(LAYOUT_OPTIONS.nodeRepulsion);
    expect(MINI_CONTROLLER_OPTIONS.layout?.nodeDimensionsIncludeLabels).toBe(true);
  });

  it('keeps node and label boxes apart for the busiest events (labels do not pile up)', () => {
    const maxW = MINI_CONTROLLER_OPTIONS.labelMaxWidth!;
    let total = 0;
    for (const sub of busiest) {
      ctl?.destroy();
      ctl = createGraphController({ headless: true, ...MINI_CONTROLLER_OPTIONS });
      ctl.load(sub.nodes, sub.edges);
      total += overlaps(ctl, maxW);
    }
    // The layout is randomised, so allow the odd corner touch; the main-canvas layout scores about 100 here.
    expect(total).toBeLessThanOrEqual(3);
  });

  it('highlights a hovered node so its full label shows', () => {
    ctl = createGraphController({ headless: true, ...MINI_CONTROLLER_OPTIONS });
    const sub = busiest[0]!;
    ctl.load(sub.nodes, sub.edges);
    const id = sub.nodes[0]!.id;
    ctl.cy.getElementById(id).emit('mouseover');
    expect(ctl.cy.getElementById(id).hasClass('hover')).toBe(true);
    ctl.cy.getElementById(id).emit('mouseout');
    expect(ctl.cy.getElementById(id).hasClass('hover')).toBe(false);
  });
});
