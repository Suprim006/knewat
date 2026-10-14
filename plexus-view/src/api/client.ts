import type {
  FlowResponse,
  GraphQuery,
  Inventory,
  KnewAt,
  QueryText,
  Results,
  Subgraph,
  TenantList,
  ViewApi,
  WhyPath,
} from './types';

export const DEFAULT_API_BASE = 'http://localhost:8080';

export class ApiError extends Error {
  readonly status: number;
  readonly url: string;
  constructor(status: number, url: string, message?: string) {
    super(message ?? `View API ${status} for ${url}`);
    this.name = 'ApiError';
    this.status = status;
    this.url = url;
  }
}

type Params = Record<string, string | number | undefined>;

/** Join base + path and append defined query params in a stable (insertion) order. */
export function buildUrl(base: string, path: string, params: Params = {}): string {
  const root = base.replace(/\/+$/, '');
  const qs = Object.entries(params)
    .filter((entry): entry is [string, string | number] => entry[1] !== undefined && entry[1] !== '')
    .map(([k, v]) => `${encodeURIComponent(k)}=${encodeURIComponent(String(v))}`)
    .join('&');
  return `${root}${path}${qs ? `?${qs}` : ''}`;
}

const seg = encodeURIComponent;

export function graphParams(q: GraphQuery = {}): Params {
  return {
    labels: q.labels && q.labels.length > 0 ? q.labels.join(',') : undefined,
    since: q.since,
    until: q.until,
    limit: q.limit,
  };
}

/** Typed client for the read-only Plexus View API (docs/PLAN.md §4). */
export function createHttpApi(
  base: string = DEFAULT_API_BASE,
  fetchImpl: typeof fetch = (...a) => fetch(...a),
): ViewApi {
  async function get<T>(path: string, params?: Params): Promise<T> {
    const url = buildUrl(base, path, params);
    const res = await fetchImpl(url, { headers: { Accept: 'application/json' } });
    if (!res.ok) throw new ApiError(res.status, url);
    return (await res.json()) as T;
  }
  return {
    tenants: () => get<TenantList>('/api/tenants'),
    inventory: (t) => get<Inventory>(`/api/${seg(t)}/inventory`),
    graph: (t, q) => get<Subgraph>(`/api/${seg(t)}/graph`, graphParams(q)),
    flow: (t, after) => get<FlowResponse>(`/api/${seg(t)}/flow`, { after }),
    step: (t, n) => get<KnewAt>(`/api/${seg(t)}/step/${n}`),
    why: (t, id) => get<WhyPath>(`/api/${seg(t)}/why/${seg(id)}`),
    queryText: (name) => get<QueryText>(`/api/queries/${name.split('/').map(seg).join('/')}`),
    results: () => get<Results>('/api/results'),
    streamUrl: (t) => buildUrl(base, `/api/${seg(t)}/stream`),
  };
}
