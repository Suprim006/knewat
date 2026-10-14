import { buildAcme } from './acme';
import type { AcmeDataset } from './acme';
import { QUERY_TEXTS } from './queries';
import type {
  FlowResponse,
  GraphNode,
  GraphQuery,
  IndexInfo,
  Inventory,
  KnewAt,
  QueryText,
  Results,
  Subgraph,
  TenantList,
  ViewApi,
  WhyPath,
} from '../api/types';

/** Fixture tenant ids. `acme` holds the Acme Notes dataset, `scratch` is an empty graph. */
export const FIXTURE_TENANTS: TenantList = {
  tenants: [
    { id: 'acme', graph: 'plexus_t_acme' },
    { id: 'scratch', graph: 'plexus_t_scratch' },
  ],
};

const EMPTY: AcmeDataset = { nodes: [], edges: [], flow: [], ids: {}, steps: [] };

/** Indexes from docs/graph-model.md ("Indexes and constraints"). */
export function modelIndexes(labels: string[]): IndexInfo[] {
  const idx = (label: string, property: string, kind: IndexInfo['kind']): IndexInfo => ({
    label,
    property,
    kind,
    entity: 'node',
    status: 'OPERATIONAL',
  });
  return [
    ...labels.map((l) => idx(l, 'id', 'range')),
    idx('Fact', 'subject_id', 'range'),
    idx('Fact', 'predicate', 'range'),
    idx('Fact', 'valid_to', 'range'),
    idx('Fact', 'status', 'range'),
    idx('Task', 'status', 'range'),
    idx('Step', 'n', 'range'),
    idx('ToolCall', 'at', 'range'),
    idx('Entity', 'norm_name', 'range'),
    idx('Entity', 'name', 'fulltext'),
    idx('Fact', 'value', 'fulltext'),
    idx('Episode', 'text', 'fulltext'),
    idx('Entity', 'embedding', 'vector'),
    idx('Fact', 'embedding', 'vector'),
    idx('Episode', 'embedding', 'vector'),
    ...['Task', 'Fact', 'Agent', 'Decision', 'Handoff'].map((l) => idx(l, 'id', 'unique')),
  ];
}

const WHY_EDGES = new Set([
  'BASED_ON',
  'DERIVED_FROM',
  'ASSERTED_BY',
  'DECIDED',
  'WROTE',
  'ABOUT',
  'SUPERSEDES',
  'FOR',
  'BY',
]);
const WHY_LEAVES = new Set(['Source', 'Agent', 'Episode', 'Step']);

export function createFixtureApi(dataset: AcmeDataset = buildAcme()): ViewApi {
  const forTenant = (tenant: string): AcmeDataset => (tenant === 'acme' ? dataset : EMPTY);
  const byId = (d: AcmeDataset) => new Map(d.nodes.map((n) => [n.id, n]));

  return {
    async tenants() {
      return FIXTURE_TENANTS;
    },

    async inventory(tenant): Promise<Inventory> {
      const d = forTenant(tenant);
      const labels = new Map<string, { count: number; keys: Set<string> }>();
      for (const n of d.nodes) {
        const e = labels.get(n.label) ?? { count: 0, keys: new Set<string>() };
        e.count++;
        for (const k of Object.keys(n.props)) e.keys.add(k);
        labels.set(n.label, e);
      }
      const types = new Map<string, number>();
      for (const e of d.edges) types.set(e.type, (types.get(e.type) ?? 0) + 1);
      return {
        tenant,
        node_total: d.nodes.length,
        edge_total: d.edges.length,
        labels: [...labels].map(([label, v]) => ({
          label,
          count: v.count,
          property_keys: ['id', ...[...v.keys].filter((k) => k !== 'id')],
        })),
        edge_types: [...types].map(([type, count]) => ({ type, count })),
        indexes: modelIndexes([
          'Agent',
          'Scope',
          'Session',
          'Episode',
          'Entity',
          'Fact',
          'Source',
          'Procedure',
          'Run',
          'Task',
          'Handoff',
          'Artifact',
          'Decision',
          'Step',
          'ToolCall',
          'Recall',
        ]),
      };
    },

    async graph(tenant, q: GraphQuery = {}): Promise<Subgraph> {
      const d = forTenant(tenant);
      const wanted = q.labels && q.labels.length > 0 ? new Set(q.labels) : null;
      const created = (n: GraphNode) => Number(n.props.created_at);
      let nodes = d.nodes.filter(
        (n) =>
          (!wanted || wanted.has(n.label)) &&
          (q.since === undefined || created(n) >= q.since) &&
          (q.until === undefined || created(n) <= q.until),
      );
      if (q.limit !== undefined) nodes = nodes.slice(0, q.limit);
      const ids = new Set(nodes.map((n) => n.id));
      const full = !wanted && q.since === undefined && q.until === undefined;
      // Edges incident to the selection. With a time window the far endpoint may be outside the set;
      // consumers must drop edges whose endpoints they don't have.
      const edges = d.edges.filter((e) =>
        full ? ids.has(e.src) && ids.has(e.dst) : ids.has(e.src) || ids.has(e.dst),
      );
      return { nodes, edges };
    },

    async flow(tenant, after): Promise<FlowResponse> {
      const d = forTenant(tenant);
      return { events: d.flow.filter((e) => after === undefined || e.at > after) };
    },

    async step(tenant, n): Promise<KnewAt> {
      const d = forTenant(tenant);
      const nodes = byId(d);
      const row = d.steps.find((s) => s.n === n);
      const upTo = new Set(d.steps.filter((s) => s.n <= n).map((s) => s.node_id));
      const agents = d.nodes
        .filter((a) => a.label === 'Agent')
        .map((a) => {
          const stepIds = new Set(
            d.nodes
              .filter((s) => s.label === 'Step' && upTo.has(s.id) && s.props.agent_id === a.id)
              .map((s) => s.id),
          );
          const knew = new Set<string>();
          for (const e of d.edges)
            if (
              (e.type === 'READ' || e.type === 'WROTE') &&
              stepIds.has(e.src) &&
              nodes.get(e.dst)?.label === 'Fact'
            )
              knew.add(e.dst);
          const wrote = d.edges
            .filter((e) => e.type === 'WROTE' && e.src === row?.node_id && row.agent_id === a.id)
            .map((e) => e.dst);
          return { agent_id: a.id, agent_name: String(a.props.name), knew: [...knew], wrote };
        });
      return { step: n, at: row?.at ?? 0, agents };
    },

    async why(tenant, id): Promise<WhyPath> {
      const d = forTenant(tenant);
      const nodes = byId(d);
      const out = new Map<string, typeof d.edges>();
      const inc = new Map<string, typeof d.edges>();
      for (const e of d.edges) {
        if (!WHY_EDGES.has(e.type)) continue;
        (out.get(e.src) ?? out.set(e.src, []).get(e.src)!).push(e);
        (inc.get(e.dst) ?? inc.set(e.dst, []).get(e.dst)!).push(e);
      }
      const paths: WhyPath['paths'] = [];
      const walk = (cur: string, nodeIds: string[], edgeIds: string[]) => {
        const node = nodes.get(cur);
        const leaf = nodeIds.length > 1 && node && WHY_LEAVES.has(node.label);
        if (leaf || nodeIds.length >= 6) {
          if (nodeIds.length > 1) paths.push({ node_ids: nodeIds, edge_ids: edgeIds });
          return;
        }
        // follow provenance edges outward; Decision/Fact are also reached via DECIDED/WROTE (incoming)
        const next = [
          ...(out.get(cur) ?? [])
            .filter((e) => e.type !== 'WROTE' && e.type !== 'DECIDED')
            .map((e) => ({ e, to: e.dst })),
          ...(inc.get(cur) ?? [])
            .filter((e) => (e.type === 'WROTE' && nodes.get(e.src)?.label === 'Step') || e.type === 'DECIDED')
            .map((e) => ({ e, to: e.src })),
        ].filter((x) => !nodeIds.includes(x.to) && x.e.type !== 'FOR' && x.e.type !== 'ABOUT');
        if (next.length === 0) {
          if (nodeIds.length > 1) paths.push({ node_ids: nodeIds, edge_ids: edgeIds });
          return;
        }
        for (const { e, to } of next) walk(to, [...nodeIds, to], [...edgeIds, e.id]);
      };
      if (nodes.has(id)) walk(id, [id], []);
      return { subject_id: id, paths: paths.slice(0, 40) };
    },

    async queryText(name): Promise<QueryText> {
      return { name, text: QUERY_TEXTS[name] ?? `// no fixture text for ${name}` };
    },

    async results(): Promise<Results> {
      return { fixture: true, note: 'No Crucible results in fixture mode.' };
    },

    streamUrl() {
      return null;
    },
  };
}
