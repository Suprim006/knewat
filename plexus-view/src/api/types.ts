/**
 * Types for the Plexus View API (docs/PLAN.md §4) and graph model v1 (docs/graph-model.md).
 *
 * The View API itself is built by another agent (P2-E). Only the node/edge shapes are pinned by the
 * plan; the envelope shapes below (`{ tenants }`, `{ events }`, ...) are this app's reading of §4 and
 * must be aligned with the real API when it lands. Everything funnels through `src/api/client.ts`.
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

export interface GraphEdge {
  id: string;
  type: string;
  src: string;
  dst: string;
  props: Props;
}

/** `GET /api/{t}/graph` */
export interface Subgraph {
  nodes: GraphNode[];
  edges: GraphEdge[];
}

/** `GET /api/tenants` */
export interface TenantInfo {
  /** Short tenant id (the part after `plexus_t_`). */
  id: string;
  /** Full graph name, `plexus_t_<id>`. */
  graph: string;
}
export interface TenantList {
  tenants: TenantInfo[];
}

export interface LabelCount {
  label: string;
  count: number;
  /** Property keys seen on nodes with this label. */
  property_keys: string[];
}
export interface EdgeTypeCount {
  type: string;
  count: number;
}
export interface IndexInfo {
  label: string;
  property: string;
  kind: 'range' | 'fulltext' | 'vector' | 'unique';
  entity: 'node' | 'edge';
  status?: string;
}

/** `GET /api/{t}/inventory` */
export interface Inventory {
  tenant: string;
  node_total: number;
  edge_total: number;
  labels: LabelCount[];
  edge_types: EdgeTypeCount[];
  indexes: IndexInfo[];
}

/** One `ToolCall` node, with the ids it touched. */
export interface FlowEvent {
  id: string;
  tool: string;
  /** Epoch ms. */
  at: number;
  agent_id: string;
  query_name: string;
  run_time_ms: number;
  created: string[];
  updated: string[];
}

/** `GET /api/{t}/flow?after=` */
export interface FlowResponse {
  events: FlowEvent[];
}

/** One entry of `GET /api/{t}/step/{n}`: what an agent knew and wrote at step n. */
export interface KnewAtAgent {
  agent_id: string;
  agent_name: string;
  knew: string[];
  wrote: string[];
}
/** `GET /api/{t}/step/{n}` */
export interface KnewAt {
  step: number;
  at: number;
  agents: KnewAtAgent[];
}

/** `GET /api/{t}/why/{id}`: ordered paths from the subject back to facts, agents, steps, sources. */
export interface WhyPath {
  subject_id: string;
  paths: { node_ids: string[]; edge_ids: string[] }[];
}

/** `GET /api/queries/{name}` */
export interface QueryText {
  name: string;
  text: string;
}

/** `GET /api/results`: Crucible results (shape owned by the Crucible agents). */
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
  flow(tenant: string, after?: number): Promise<FlowResponse>;
  step(tenant: string, n: number): Promise<KnewAt>;
  why(tenant: string, id: string): Promise<WhyPath>;
  queryText(name: string): Promise<QueryText>;
  results(): Promise<Results>;
  /** URL of the SSE stream for a tenant (`null` in fixture mode). */
  streamUrl(tenant: string): string | null;
}
