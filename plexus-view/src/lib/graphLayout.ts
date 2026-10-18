import type { Core, NodeSingular } from 'cytoscape';
import type { ControllerOptions } from './graphTypes';

/**
 * The Flow page's "What it touched" mini-graph: a few nodes in a 320 px box. Quality `default` is cheap at this
 * size and a strong repulsion keeps labels clear of neighbours (see miniLayout.test.ts); names are cut sooner.
 */
export const MINI_CONTROLLER_OPTIONS = {
  labelMaxWidth: 84,
  layout: {
    quality: 'default',
    idealEdgeLength: 120,
    nodeRepulsion: 200000,
    nodeSeparation: 220,
    gravity: 0.1,
    nodeDimensionsIncludeLabels: true,
  },
} as const satisfies Pick<ControllerOptions, 'layout' | 'labelMaxWidth'>;

/** fcose options. Quality stays "draft" (spike S3): `default` takes ~26 s at 2k nodes. */
export const LAYOUT_OPTIONS = {
  name: 'fcose',
  quality: 'draft',
  randomize: true,
  nodeDimensionsIncludeLabels: false,
  idealEdgeLength: 110,
  nodeRepulsion: 14000,
  nodeSeparation: 110,
  edgeElasticity: 0.4,
  gravity: 0.15,
  packComponents: true,
} as const;

/**
 * Give each unplaced node a position next to an already-placed neighbour (several passes so chains of
 * new nodes work), falling back to the centre of the placed cluster. Never moves placed nodes.
 */
export function seedNear(cy: Core, unplaced: NodeSingular[], placed: Set<string>): void {
  const todo = [...unplaced];
  for (let pass = 0; pass < 4 && todo.length > 0; pass++) {
    for (let i = todo.length - 1; i >= 0; i--) {
      const n = todo[i]!;
      const nb = n
        .neighborhood('node')
        .filter((m) => placed.has(m.id()))
        .first() as NodeSingular;
      if (nb.empty()) continue;
      const p = nb.position();
      n.position({ x: p.x + (Math.random() - 0.5) * 60, y: p.y + (Math.random() - 0.5) * 60 });
      placed.add(n.id());
      todo.splice(i, 1);
    }
  }
  if (todo.length === 0) return;
  const ext = cy.nodes().filter((n) => placed.has(n.id()));
  const box = ext.nonempty() ? ext.boundingBox() : { x1: 0, x2: 0, y1: 0, y2: 0 };
  for (const n of todo) {
    n.position({
      x: (box.x1 + box.x2) / 2 + (Math.random() - 0.5) * 120,
      y: (box.y1 + box.y2) / 2 + (Math.random() - 0.5) * 120,
    });
  }
}
