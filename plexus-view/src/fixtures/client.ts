import { buildAcme } from './acme';
import type { AcmeDataset } from './acme';
import { applyP7, docsToUpdate, memoryCounts, memoryStrength, verifyQueue } from './p7';
import { QUERY_TEXTS } from './queries';
import { ApiError } from '../api/client';
import { OPEN } from '../api/types';
import type {
  FlowResponse,
  GraphEdge,
  GraphNode,
  GraphQuery,
  IndexInfo,
  Inventory,
  LineageEdge,
  LineageNode,
  QueryText,
  Results,
  StepAgent,
  StepResponse,
  Subgraph,
  TenantList,
  ViewApi,
  WhyFact,
  WhyHop,
  WhyResponse,
} from '../api/types';

/** Fixture tenant ids. `acme` holds the Acme Notes dataset, `scratch` is an empty graph. */
export const FIXTURE_TENANTS: TenantList = {
  tenants: [
    { tenant: 'acme', graph: 'plexus_t_acme' },
    { tenant: 'scratch', graph: 'plexus_t_scratch' },
  ],
};

const EMPTY: AcmeDataset = { nodes: [], edges: [], flow: [], ids: {}, steps: [] };

/** Indexes from docs/graph-model.md ("Indexes and constraints"), in the API's grouped-by-label shape. */
export function modelIndexes(labels: string[]): IndexInfo[] {
  const entries: [label: string, property: string, kind: string][] = [
    ...labels.map((l): [string, string, string] => [l, 'id', 'RANGE']),
    ['Fact', 'subject_id', 'RANGE'],
    ['Fact', 'predicate', 'RANGE'],
    ['Fact', 'valid_to', 'RANGE'],
    ['Fact', 'status', 'RANGE'],
    ['Fact', 'pinned', 'RANGE'],
    ['CodeAnchor', 'path', 'RANGE'],
    ['Change', 'at', 'RANGE'],
    ['Task', 'status', 'RANGE'],
    ['Step', 'n', 'RANGE'],
    ['ToolCall', 'at', 'RANGE'],
    ['Entity', 'norm_name', 'RANGE'],
    ['Entity', 'name', 'FULLTEXT'],
    ['Fact', 'value', 'FULLTEXT'],
    ['Episode', 'text', 'FULLTEXT'],
    ['Entity', 'embedding', 'VECTOR'],
    ['Fact', 'embedding', 'VECTOR'],
    ['Episode', 'embedding', 'VECTOR'],
  ];
  const byLabel = new Map<string, IndexInfo>();
  for (const [label, property, kind] of entries) {
    const idx = byLabel.get(label) ?? {
      label,
      properties: [],
      types: {},
      entity_type: 'NODE',
      status: 'OPERATIONAL',
    };
    if (!idx.properties.includes(property)) idx.properties.push(property);
    (idx.types[property] ??= []).push(kind);
    byLabel.set(label, idx);
  }
  return [...byLabel.values()];
}

/** Parse the header comments of a `.cypher` file into the API's {mode, purpose, params, returns}. */
export function parseQueryHeader(name: string, text: string): QueryText {
  const lines = text.split('\n');
  const header = (key: string): string => {
    const at = lines.findIndex((l) => l.startsWith(`// ${key}:`));
    if (at < 0) return '';
    const out = [lines[at]!.slice(`// ${key}:`.length).trim()];
    for (let i = at + 1; i < lines.length && /^\/\/ {2,}/.test(lines[i]!); i++)
      out.push(lines[i]!.replace(/^\/\/\s*/, ''));
    return out.join(' ');
  };
  const params: Record<string, string> = {};
  for (const part of header('params').split(',')) {
    const [k, v] = part.split(':').map((x) => x.trim());
    if (k && v) params[k] = v;
  }
  return {
    name,
    mode: header('mode') || 'ro',
    purpose: header('purpose'),
    params,
    returns: header('returns'),
    text,
  };
}

/** Edges that make up a provenance trail, and the labels where a trail ends. */
const WHY_EDGES = new Set([
  'BASED_ON',
  'ASSERTED_BY',
  'DERIVED_FROM',
  'ABOUT',
  'SUPERSEDES',
  'CONTRADICTS',
  'DECIDED',
  'WROTE',
  'FOR',
]);
const WHY_LEAVES = new Set(['Agent', 'Source', 'Episode', 'Step', 'Entity', 'Task']);
const WHY_MAX_HOPS = 3;

interface Adj {
  e: GraphEdge;
  other: string;
  reverse: boolean;
}

/** The default dataset is Acme Notes with the P7 staleness / forgetting overlay (`applyP7`). */
export function createFixtureApi(
  dataset: AcmeDataset = applyP7(buildAcme()),
  fixtureResults: Results | null = null,
): ViewApi {
  const forTenant = (tenant: string): AcmeDataset => (tenant === 'acme' ? dataset : EMPTY);
  const byId = (d: AcmeDataset) => new Map(d.nodes.map((n) => [n.id, n]));
  const created = (n: GraphNode) => Number(n.props.created_at);

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
        nodes_total: d.nodes.length,
        edges_total: d.edges.length,
        labels: [...labels].map(([label, v]) => ({
          label,
          count: v.count,
          keys: ['id', ...[...v.keys].filter((k) => k !== 'id')].sort(),
        })),
        edge_types: [...types].map(([type, count]) => ({ type, count })),
        indexes: modelIndexes([...labels.keys()]),
        ...memoryCounts(d, Date.now()),
      };
    },

    async graph(tenant, q: GraphQuery = {}): Promise<Subgraph> {
      const d = forTenant(tenant);
      const wanted = q.labels && q.labels.length > 0 ? new Set(q.labels) : null;
      const limit = q.limit ?? 500;
      // Like view/subgraph: the newest `limit` nodes of the window, and only edges among them.
      const matched = d.nodes
        .filter(
          (n) =>
            (!wanted || wanted.has(n.label)) &&
            (q.since === undefined || created(n) >= q.since) &&
            (q.until === undefined || created(n) <= q.until),
        )
        .sort((a, b) => created(b) - created(a) || a.id.localeCompare(b.id));
      const nodes = matched.slice(0, limit);
      const ids = new Set(nodes.map((n) => n.id));
      const edges = d.edges.filter((e) => ids.has(e.source) && ids.has(e.target));
      return { nodes, edges, truncated: matched.length > limit, limit };
    },

    async flow(tenant, after = 0, limit = 200): Promise<FlowResponse> {
      const events = forTenant(tenant)
        .flow.filter((e) => e.at > after)
        .slice(0, limit);
      return { events, last_at: events.reduce((m, e) => Math.max(m, e.at), after) };
    },

    async step(tenant, n): Promise<StepResponse> {
      const d = forTenant(tenant);
      const nodes = byId(d);
      const agents: StepAgent[] = [];
      const agentIds = [...new Set(d.steps.map((s) => s.agent_id))].sort();
      const entityName = (factId: string): string | null => {
        const ab = d.edges.find((e) => e.type === 'ABOUT' && e.source === factId);
        const ent = ab ? nodes.get(ab.target) : undefined;
        return ent ? String(ent.props.name) : null;
      };
      for (const agentId of agentIds) {
        const mine = d.steps.filter((s) => s.agent_id === agentId && s.n <= n);
        const latest = mine[mine.length - 1];
        if (!latest) continue;
        const stepOf = new Map(mine.map((s) => [s.node_id, s]));
        const read = new Map<string, number>();
        const wrote: StepAgent['wrote'] = [];
        for (const e of d.edges) {
          const st = stepOf.get(e.source);
          const target = nodes.get(e.target);
          if (!st || !target) continue;
          if (e.type === 'READ' && target.label === 'Fact' && !read.has(target.id)) read.set(target.id, st.n);
          if (e.type === 'WROTE' && ['Fact', 'Decision', 'Handoff', 'Task'].includes(target.label))
            wrote.push({
              id: target.id,
              label: target.label,
              summary: String(
                target.props.value ?? target.props.text ?? target.props.note ?? target.props.title ?? '',
              ),
              step_n: st.n,
            });
        }
        agents.push({
          agent_id: agentId,
          step_n: latest.n,
          step_at: latest.at,
          // Like Lineage.knew_at: read by then AND valid at that step's time.
          read: [...read]
            .map(([id, at]) => ({ f: nodes.get(id)!, at }))
            .filter(
              ({ f }) =>
                Number(f.props.valid_from) <= latest.at && latest.at < Number(f.props.valid_to ?? OPEN),
            )
            .map(({ f, at }) => ({
              id: f.id,
              entity: entityName(f.id),
              predicate: String(f.props.predicate),
              value: String(f.props.value),
              status: String(f.props.status),
              valid_from: Number(f.props.valid_from),
              valid_to: Number(f.props.valid_to),
              read_at_step: at,
            })),
          wrote,
        });
      }
      return { n, agents };
    },

    async why(tenant, id): Promise<WhyResponse> {
      const d = forTenant(tenant);
      const nodes = byId(d);
      const root = nodes.get(id);
      if (!root || !['Decision', 'Fact'].includes(root.label))
        throw new ApiError(404, `fixture:/why/${id}`, `no Decision or Fact '${id}'`);
      const adj = new Map<string, Adj[]>();
      const add = (k: string, v: Adj) => (adj.get(k) ?? adj.set(k, []).get(k)!).push(v);
      for (const e of d.edges) {
        if (!WHY_EDGES.has(e.type)) continue;
        add(e.source, { e, other: e.target, reverse: false });
        add(e.target, { e, other: e.source, reverse: true });
      }
      // Breadth-first from the root; every reached node gets the shortest hop list that leads to it.
      const reach = new Map<string, WhyHop[]>([[id, []]]);
      const queue = [id];
      while (queue.length > 0) {
        const cur = queue.shift()!;
        const hops = reach.get(cur)!;
        if (hops.length >= WHY_MAX_HOPS || (cur !== id && WHY_LEAVES.has(nodes.get(cur)!.label))) continue;
        for (const { e, other, reverse } of adj.get(cur) ?? []) {
          const o = nodes.get(other)!;
          if (reach.has(other)) continue;
          // Follow trails towards evidence only.
          if (e.type === 'BASED_ON' && reverse) continue;
          if (e.type === 'WROTE' && !(reverse && o.label === 'Step')) continue;
          if (e.type === 'DECIDED' && !reverse) continue;
          if (e.type === 'FOR' && o.label !== 'Task') continue;
          reach.set(other, [...hops, { from: cur, rel: e.type, to: other, reverse }]);
          queue.push(other);
        }
      }
      const members = new Set(reach.keys());
      const lineageNodes: LineageNode[] = [...members].map((m) => {
        const n = nodes.get(m)!;
        return { id: n.id, label: n.label, props: n.props };
      });
      const lineageEdges: LineageEdge[] = d.edges
        .filter((e) => WHY_EDGES.has(e.type) && members.has(e.source) && members.has(e.target))
        .map((e) => ({ from: e.source, rel: e.type, to: e.target, props: null }));
      const ofLabel = (l: string) => lineageNodes.filter((n) => n.label === l).map((n) => n.id);
      const out = (type: string, from: string) =>
        d.edges.filter((e) => e.type === type && e.source === from).map((e) => e.target);
      const into = (type: string, to: string) =>
        d.edges.filter((e) => e.type === type && e.target === to).map((e) => e.source);
      const labelOf = (x: string) => nodes.get(x)?.label;
      const facts: WhyFact[] = lineageNodes
        .filter((n) => n.label === 'Fact')
        .map((n) => ({
          id: n.id,
          props: n.props,
          asserted_by: out('ASSERTED_BY', n.id),
          sources: out('DERIVED_FROM', n.id).filter((x) => labelOf(x) === 'Source'),
          episodes: out('DERIVED_FROM', n.id).filter((x) => labelOf(x) === 'Episode'),
          derived_from_facts: out('DERIVED_FROM', n.id).filter((x) => labelOf(x) === 'Fact'),
          supersedes: out('SUPERSEDES', n.id),
          superseded_by: into('SUPERSEDES', n.id),
          contradicts: out('CONTRADICTS', n.id),
          contradicted_by: into('CONTRADICTS', n.id),
          written_by_steps: into('WROTE', n.id).filter((x) => labelOf(x) === 'Step'),
        }));
      return {
        id,
        result: {
          root: id,
          kind: root.label,
          facts,
          agents: ofLabel('Agent'),
          sources: ofLabel('Source'),
          episodes: ofLabel('Episode'),
          steps: ofLabel('Step'),
          paths: [...reach.values()].filter((h) => h.length > 0),
          nodes: lineageNodes,
          edges: lineageEdges,
          truncated: false,
        },
      };
    },

    async verifyQueue(tenant, q = {}) {
      return { rows: verifyQueue(forTenant(tenant), Date.now(), q.limit ?? 50) };
    },

    async docsToUpdate(tenant, q = {}) {
      return { docs: docsToUpdate(forTenant(tenant), q.since ?? 0, q.limit ?? 50) };
    },

    async memoryStrength(tenant, factId) {
      const s = memoryStrength(forTenant(tenant), factId);
      if (!s) throw new ApiError(404, `fixture:/memory-strength/${factId}`, `unknown fact id: ${factId}`);
      return s;
    },

    async queryText(name): Promise<QueryText> {
      return parseQueryHeader(name, QUERY_TEXTS[name] ?? `// no fixture text for ${name}`);
    },

    async results(): Promise<Results> {
      if (!fixtureResults) throw new ApiError(404, 'fixture:/api/results', 'no Crucible results available');
      return fixtureResults;
    },

    streamUrl() {
      return null;
    },
  };
}
