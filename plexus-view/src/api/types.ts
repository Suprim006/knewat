/**
 * Types for the Plexus View API (docs/PLAN.md §4) and graph model v1 (docs/graph-model.md).
 *
 * These mirror the real API: `plexus/src/plexus/api/models.py` (exported to docs/view-api.schema.json).
 * Field names are final; times are epoch milliseconds. Everything funnels through `src/api/client.ts`.
 */

/** FalkorDB cannot store null, so an open-ended `valid_to` is this sentinel. */
export const OPEN = 9_999_999_999_999;

export const NODE_LABELS = [
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
] as const;
export type NodeLabel = (typeof NODE_LABELS)[number];

export const EDGE_TYPES = [
  'HAS_EPISODE',
  'NEXT',
  'HAD',
  'ABOUT',
  'DERIVED_FROM',
  'IN_SCOPE',
  'INHERITS',
  'SUPERSEDES',
  'DUPLICATES',
  'CONTRADICTS',
  'ASSERTED_BY',
  'USED_IN',
  'BY',
  'FOR',
  'DEPENDS_ON',
  'CLAIMED',
  'FROM',
  'TO',
  'CARRIES',
  'DECIDED',
  'BASED_ON',
  'PRODUCED_BY',
  'VERIFIED_BY',
  'READ',
  'WROTE',
  'IN_STEP',
  'CREATED',
  'UPDATED',
  'RETURNED',
] as const;
export type EdgeType = (typeof EDGE_TYPES)[number];

/** Scalar property values only: FalkorDB has no null or map properties. */
export type PropValue = string | number | boolean | string[] | number[];
export type Props = Record<string, PropValue>;

export interface GraphNode {
  id: string;
  /** Node label; a string so a newer server with an unknown label still renders. */
  label: string;
  props: Props;
}

/** Edges carry no id of their own in the API; see {@link edgeId}. */
export interface GraphEdge {
  source: string;
  target: string;
  type: string;
}

/** Groups parallel edges: same source, type and target. NOT unique, see {@link keyEdges}. */
export const edgeId = (e: GraphEdge): string => `${e.source}|${e.type}|${e.target}`;

/** Client-side key of the `index`-th edge of a (source, type, target) group. */
export const edgeKey = (e: GraphEdge, index: number): string => `${edgeId(e)}|${index}`;

/**
 * The API gives edges no id and may return several parallel edges of one type between the same two
 * nodes (a task claimed twice, a fact re-asserted). Key each by (source, target, type, index within its
 * group, in response order) so none collapses. A re-read yields the same keys for the same edges, plus
 * new ones for any extra parallel edge, which is all `addLive` needs to stay idempotent.
 */
export function keyEdges(edges: readonly GraphEdge[]): { id: string; edge: GraphEdge }[] {
  const seen = new Map<string, number>();
  return edges.map((edge) => {
    const group = edgeId(edge);
    const index = seen.get(group) ?? 0;
    seen.set(group, index + 1);
    return { id: edgeKey(edge, index), edge };
  });
}

/** `GET /api/{t}/graph` */
export interface Subgraph {
  nodes: GraphNode[];
  edges: GraphEdge[];
  /** True if more nodes matched than `limit`. */
  truncated: boolean;
  limit: number;
}

/** `GET /api/tenants` */
export interface TenantInfo {
  /** Short tenant id (the part after `plexus_t_`). */
  tenant: string;
  /** Full graph name, `plexus_t_<id>`. */
  graph: string;
}
export interface TenantList {
  tenants: TenantInfo[];
}

export interface LabelCount {
  label: string;
  count: number;
  /** Property keys seen on a bounded sample of this label's nodes. */
  keys: string[];
}
export interface EdgeTypeCount {
  type: string;
  count: number;
}
export interface IndexInfo {
  label: string;
  properties: string[];
  /** Property -> index kinds (RANGE | FULLTEXT | VECTOR). */
  types: Record<string, string[]>;
  entity_type: string;
  status: string;
}

/** `GET /api/{t}/inventory` */
export interface Inventory {
  tenant: string;
  nodes_total: number;
  edges_total: number;
  labels: LabelCount[];
  edge_types: EdgeTypeCount[];
  indexes: IndexInfo[];
}

export interface NodeRef {
  id: string;
  label: string;
}

/** One `ToolCall` node with the nodes it created/updated (also one SSE `toolcall` frame). */
export interface FlowEvent {
  id: string;
  tool: string;
  /** Epoch ms. */
  at: number;
  agent_id: string;
  /** Named query under `GET /api/queries/{name}`; '' when the call ran none. */
  query_name: string;
  run_time_ms: number;
  wrote: boolean;
  /** The agent's own step counter, if it sent one. */
  step: number | null;
  /** Lineage Step node id. */
  step_id: string | null;
  /** That Step's number in its agent's chain (the step slider's value). */
  step_n: number | null;
  created: NodeRef[];
  updated: NodeRef[];
}

/** `GET /api/{t}/flow?after=` */
export interface FlowResponse {
  events: FlowEvent[];
  /** Largest `at` returned (or `after` when empty); pass it as the next `after`. */
  last_at: number;
}

/** A fact an agent had read by the step and that was still valid then. */
export interface StepFact {
  id: string;
  entity?: string | null;
  predicate?: string | null;
  value?: string | null;
  status?: string | null;
  valid_from?: number | null;
  valid_to?: number | null;
  /** The agent's first step that read it. */
  read_at_step?: number | null;
}
/** A node (Fact, Decision, Handoff or Task) the agent's steps wrote up to the step. */
export interface StepWrote extends NodeRef {
  summary?: string | null;
  step_n?: number | null;
}
export interface StepAgent {
  agent_id: string;
  /** This agent's latest step <= the requested n. */
  step_n: number;
  step_at: number;
  read: StepFact[];
  wrote: StepWrote[];
}
/** `GET /api/{t}/step/{n}` */
export interface StepResponse {
  n: number;
  agents: StepAgent[];
}

export interface LineageNode {
  id: string;
  label: string;
  props: Record<string, unknown>;
}
/** Stored direction `from -[rel]-> to`. */
export interface LineageEdge {
  from: string;
  rel: string;
  to: string;
  props?: Record<string, unknown> | null;
}
export interface WhyHop {
  from: string;
  rel: string;
  to: string;
  /** True when the edge is stored `to -> from`. */
  reverse: boolean;
}
export interface WhyFact {
  id: string;
  props: Record<string, unknown>;
  asserted_by: string[];
  sources: string[];
  episodes: string[];
  derived_from_facts: string[];
  supersedes: string[];
  superseded_by: string[];
  contradicts: string[];
  contradicted_by: string[];
  written_by_steps: string[];
}
export interface WhyResult {
  root: string;
  kind: string;
  facts: WhyFact[];
  agents: string[];
  sources: string[];
  episodes: string[];
  steps: string[];
  paths: WhyHop[][];
  nodes: LineageNode[];
  edges: LineageEdge[];
  truncated: boolean;
}
/** `GET /api/{t}/why/{id}` */
export interface WhyResponse {
  id: string;
  result: WhyResult;
}

/** `GET /api/queries/{name}` */
export interface QueryText {
  name: string;
  mode: string;
  purpose: string;
  params: Record<string, string>;
  returns: string;
  /** The full .cypher file text, header included. */
  text: string;
}

/** `GET /api/results`: Crucible results (shape owned by the Crucible agents; rendered defensively). */
export interface Results {
  [key: string]: unknown;
}

/** Subgraph query parameters (`GET /api/{t}/graph`). */
export interface GraphQuery {
  labels?: string[];
  since?: number;
  until?: number;
  limit?: number;
}

/** Interface implemented by both the HTTP client and the fixture client. */
export interface ViewApi {
  tenants(): Promise<TenantList>;
  inventory(tenant: string): Promise<Inventory>;
  graph(tenant: string, query?: GraphQuery): Promise<Subgraph>;
  flow(tenant: string, after?: number, limit?: number): Promise<FlowResponse>;
  step(tenant: string, n: number): Promise<StepResponse>;
  why(tenant: string, id: string): Promise<WhyResponse>;
  queryText(name: string): Promise<QueryText>;
  /** Rejects with a 404 {@link ApiError} until the Crucible produces results. */
  results(): Promise<Results>;
  /** URL of the SSE stream for a tenant (`null` in fixture mode). */
  streamUrl(tenant: string): string | null;
}
