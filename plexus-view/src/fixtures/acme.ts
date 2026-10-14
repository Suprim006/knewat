/**
 * Hand-authored "Acme Notes API" software-team scenario, expressed as graph model v1.
 *
 * Three agents (planner, researcher, builder) build a small notes REST service. The script below is the
 * *only* hand-written part: a list of steps, each with the tool calls an agent made and the nodes/edges
 * each call created or updated. `buildAcme()` expands it into the same shapes the View API returns
 * (nodes, edges, ToolCall flow events) so fixture mode and live mode are interchangeable.
 *
 * Scenario beats (they mirror the fault script of the real demo):
 *  - step 14-17: the builder claims T7 and goes silent; its lease expires and it re-claims after restart;
 *  - step 20:    the researcher supersedes `API version = v1` with `v2`;
 *  - step 21:    the builder asserts `auth = API key`, contradicting the researcher's `auth = JWT`;
 *  - step 22:    the planner resolves the contradiction with a decision;
 *  - step 26:    the researcher fails T9 (rate-limit library incompatible), the planner re-plans.
 *
 * Synthetic data only. Ids are deterministic UUID-shaped strings so tests and screenshots are stable.
 */
import { NODE_LABELS, OPEN } from '../api/types';
import type { FlowEvent, GraphEdge, GraphNode, NodeLabel, Props, PropValue } from '../api/types';

export const T0 = 1_792_060_800_000; // 2026-10-15T00:00:00Z-ish
export const STEP_MS = 45_000;
export const stepTime = (n: number): number => T0 + n * STEP_MS;

/* ---------- script DSL ---------- */

/** Tokens substituted while expanding: the op's timestamp, a 2-minute lease, and the step number. */
export const NOW = -1;
export const LEASE = -2;
export const STEP = -3;

type AgentName = 'planner' | 'researcher' | 'builder';
type NodeSpec = [label: NodeLabel, key: string, props: Props];
type EdgeSpec = [type: string, src: string, dst: string, props?: Props];

interface OpSpec {
  tool: string;
  nodes?: NodeSpec[];
  edges?: EdgeSpec[];
  /** Existing nodes updated by the call: key -> property changes. */
  patch?: Record<string, Props>;
  /** Fact keys read by the call (becomes Step -READ-> Fact). */
  read?: string[];
  recall?: { query: string; facts: string[] };
}
interface StepSpec {
  n: number;
  agent: AgentName;
  ops: OpSpec[];
}

const ENTITIES = {
  api: ['Acme Notes API', 'service'],
  auth: ['Authentication', 'concept'],
  db: ['Database', 'component'],
  ep: ['Notes endpoints', 'component'],
  page: ['Pagination', 'concept'],
  rate: ['Rate limiting', 'concept'],
  dep: ['Deployment', 'concept'],
  test: ['Testing', 'concept'],
} as const;
type EntityName = keyof typeof ENTITIES;

const WRITE_TOOLS = new Set([
  'start_session',
  'remember_episode',
  'assert_fact',
  'log_procedure_run',
  'create_tasks',
  'claim_next_task',
  'heartbeat',
  'complete_task',
  'fail_task',
  'handoff',
  'record_decision',
]);

const QUERY_NAMES: Record<string, string> = {
  start_session: 'engram/start_session',
  remember_episode: 'engram/remember_episode',
  assert_fact: 'engram/assert_fact',
  recall: 'engram/recall',
  log_procedure_run: 'engram/log_procedure_run',
  best_procedure: 'engram/best_procedure',
  create_tasks: 'relay/create_tasks',
  claim_next_task: 'relay/claim_next_task',
  heartbeat: 'relay/heartbeat',
  complete_task: 'relay/complete_task',
  fail_task: 'relay/fail_task',
  handoff: 'relay/handoff',
  record_decision: 'relay/record_decision',
  blocked_by_failure: 'relay/blocked_by_failure',
  why: 'lineage/why',
  why_recalled: 'lineage/why_recalled',
  who_knew: 'lineage/who_knew',
  knew_at: 'lineage/knew_at',
  as_of: 'lineage/as_of',
};

/* ---------- op helpers ---------- */

interface FactOpts {
  src?: string; // Source key
  ep?: string; // Episode key
  from?: string[]; // Fact keys (DERIVED_FROM)
  conf?: number;
  scope?: 'global' | 'project';
  supersedes?: string;
  contradicts?: string;
  duplicates?: string;
}

/** assert_fact: resolve entity, close/link older facts, create the fact with provenance. */
function af(key: string, ent: EntityName, predicate: string, value: string, o: FactOpts = {}): OpSpec {
  const nodes: NodeSpec[] = [
    ['Fact', `f.${key}`, { predicate, value, confidence: o.conf ?? 0.9, status: 'active', subject_id: '' }],
  ];
  const edges: EdgeSpec[] = [
    ['ABOUT', `f.${key}`, `e.${ent}`],
    ['IN_SCOPE', `f.${key}`, o.scope === 'global' ? 'sc.global' : 'sc.project'],
    ['ASSERTED_BY', `f.${key}`, '$agent'],
  ];
  if (o.src) edges.push(['DERIVED_FROM', `f.${key}`, `s.${o.src}`]);
  if (o.ep) edges.push(['DERIVED_FROM', `f.${key}`, `ep.${o.ep}`]);
  for (const f of o.from ?? []) edges.push(['DERIVED_FROM', `f.${key}`, `f.${f}`]);
  const patch: Record<string, Props> = {};
  if (o.supersedes) {
    edges.push(['SUPERSEDES', `f.${key}`, `f.${o.supersedes}`]);
    patch[`f.${o.supersedes}`] = { status: 'superseded', valid_to: NOW };
  }
  if (o.contradicts) edges.push(['CONTRADICTS', `f.${key}`, `f.${o.contradicts}`]);
  if (o.duplicates) edges.push(['DUPLICATES', `f.${key}`, `f.${o.duplicates}`]);
  return { tool: 'assert_fact', nodes, edges, patch };
}

const startSession = (key: string): OpSpec => ({
  tool: 'start_session',
  nodes: [['Session', `ses.${key}`, { agent_id: '@$agent', started_at: NOW, ended_at: OPEN }]],
  edges: [['HAD', '$agent', `ses.${key}`]],
});

const remember = (key: string, session: string, role: string, text: string, prev?: string): OpSpec => ({
  tool: 'remember_episode',
  nodes: [['Episode', `ep.${key}`, { role, text, at: NOW, step: STEP }]],
  edges: [
    ['HAS_EPISODE', `ses.${session}`, `ep.${key}`],
    ...(prev ? ([['NEXT', `ep.${prev}`, `ep.${key}`]] as EdgeSpec[]) : []),
  ],
});

const recall = (query: string, ...facts: string[]): OpSpec => ({ tool: 'recall', recall: { query, facts } });

const claim = (task: string, version: number): OpSpec => ({
  tool: 'claim_next_task',
  patch: {
    [`t.${task}`]: { status: 'claimed', claimed_by: '@$agent', lease_until: LEASE, version },
  },
  edges: [['CLAIMED', '$agent', `t.${task}`, { at: NOW, lease_until: LEASE }]],
});

const complete = (task: string, version: number, extra?: Omit<OpSpec, 'tool' | 'patch'>): OpSpec => ({
  tool: 'complete_task',
  patch: { [`t.${task}`]: { status: 'done', done_at: NOW, lease_until: 0, version } },
  ...extra,
});

const decide = (key: string, task: string, text: string, ...basedOn: string[]): OpSpec => ({
  tool: 'record_decision',
  nodes: [['Decision', `d.${key}`, { text, at: NOW }]],
  edges: [
    ['DECIDED', '$agent', `d.${key}`],
    ['FOR', `d.${key}`, `t.${task}`],
    ...basedOn.map((f): EdgeSpec => ['BASED_ON', `d.${key}`, `f.${f}`]),
  ],
});

const artifact = (key: string, kind: string, uri: string, summary: string): NodeSpec[] => [
  ['Artifact', `ar.${key}`, { kind, uri, hash: fakeHash(key), summary }],
];
const artifactEdges = (key: string, verifiedBy?: AgentName): EdgeSpec[] => [
  ['PRODUCED_BY', `ar.${key}`, '$agent'],
  ...(verifiedBy ? ([['VERIFIED_BY', `ar.${key}`, `a.${verifiedBy}`]] as EdgeSpec[]) : []),
];

const handoff = (
  key: string,
  task: string,
  to: AgentName,
  note: string,
  carries: string[],
  extra?: { nodes?: NodeSpec[]; edges?: EdgeSpec[] },
): OpSpec => ({
  tool: 'handoff',
  nodes: [['Handoff', `h.${key}`, { at: NOW, note }], ...(extra?.nodes ?? [])],
  edges: [
    ['FROM', `h.${key}`, '$agent'],
    ['TO', `h.${key}`, `a.${to}`],
    ['FOR', `h.${key}`, `t.${task}`],
    ...carries.map((c): EdgeSpec => ['CARRIES', `h.${key}`, c]),
    ...(extra?.edges ?? []),
  ],
});

const task = (key: string, title: string, priority: number): NodeSpec => [
  'Task',
  `t.${key}`,
  { title, status: 'open', priority, lease_until: 0, claimed_by: '', version: 0, done_at: 0 },
];

const TASKS: NodeSpec[] = [
  task('1', 'Define product scope and requirements', 3),
  task('2', 'Research authentication options', 2),
  task('3', 'Research storage options', 2),
  task('4', 'Design the REST API spec', 3),
  task('5', 'Choose the authentication scheme', 3),
  task('6', 'Design the database schema', 2),
  task('7', 'Implement notes CRUD endpoints', 3),
  task('8', 'Implement auth middleware', 3),
  task('9', 'Add pagination and rate limiting', 2),
  task('10', 'Write OpenAPI documentation', 1),
  task('11', 'Write integration tests', 2),
  task('12', 'Load test and release v2', 1),
];
const DEPENDENCIES: [string, string][] = [
  ['2', '1'],
  ['3', '1'],
  ['4', '1'],
  ['5', '2'],
  ['6', '3'],
  ['7', '4'],
  ['7', '6'],
  ['8', '5'],
  ['8', '7'],
  ['9', '7'],
  ['10', '4'],
  ['10', '7'],
  ['11', '8'],
  ['11', '9'],
  ['12', '10'],
  ['12', '11'],
];

/* ---------- the script ---------- */

const SCRIPT: StepSpec[] = [
  {
    n: 1,
    agent: 'planner',
    ops: [
      startSession('planner'),
      remember(
        'p1',
        'planner',
        'user',
        'Build a small notes REST API called Acme Notes. Spec and first endpoints due Friday.',
      ),
      {
        tool: 'create_tasks',
        nodes: TASKS,
        edges: DEPENDENCIES.map(([a, b]): EdgeSpec => ['DEPENDS_ON', `t.${a}`, `t.${b}`]),
      },
    ],
  },
  {
    n: 2,
    agent: 'planner',
    ops: [
      claim('1', 1),
      af('goal', 'api', 'goal', 'REST service for creating, reading, updating and deleting notes', {
        src: 'brief',
        ep: 'p1',
      }),
      af('v1', 'api', 'api_version', 'v1', { src: 'brief', ep: 'p1', conf: 0.85 }),
      af('lang', 'api', 'language', 'Python 3.12 with FastAPI', { src: 'brief', scope: 'global' }),
      af('deadline', 'api', 'deadline', 'spec and first endpoints due Friday', { ep: 'p1' }),
    ],
  },
  {
    n: 3,
    agent: 'planner',
    ops: [
      af('roles', 'api', 'team_roles', 'planner decomposes, researcher investigates, builder implements', {
        ep: 'p1',
      }),
      complete('1', 2, {
        nodes: artifact('req', 'doc', 'artifacts/requirements.md', 'Product requirements for Acme Notes API'),
        edges: artifactEdges('req', 'researcher'),
      }),
      handoff('p2r', '1', 'researcher', 'Scope is set. Investigate auth and storage options next.', [
        'ar.req',
        'f.goal',
        'f.deadline',
      ]),
    ],
  },
  {
    n: 4,
    agent: 'researcher',
    ops: [
      startSession('researcher'),
      recall('what is the goal and stack of the project?', 'goal', 'lang', 'deadline'),
      claim('2', 1),
    ],
  },
  {
    n: 5,
    agent: 'researcher',
    ops: [
      remember('r1', 'researcher', 'assistant', 'Reading RFC-0042 on authentication for the notes service.'),
      af('auth_cands', 'auth', 'candidate_schemes', 'JWT bearer, API key, session cookie', {
        src: 'rfc',
        ep: 'r1',
      }),
      af('jwt_prop', 'auth', 'jwt_property', 'stateless; needs signing key rotation', {
        src: 'rfc',
        conf: 0.85,
      }),
      af('key_prop', 'auth', 'apikey_property', 'simple; no expiry unless built; leaks easily', {
        src: 'rfc',
        conf: 0.8,
      }),
    ],
  },
  {
    n: 6,
    agent: 'researcher',
    ops: [
      af('jwt', 'auth', 'scheme', 'JWT', { src: 'rfc', from: ['jwt_prop', 'key_prop'], conf: 0.8 }),
      af('ttl', 'auth', 'token_lifetime', '15 minutes access token, 7 days refresh token', { src: 'rfc' }),
      complete('2', 2, {
        nodes: artifact(
          'authnotes',
          'doc',
          'artifacts/auth-findings.md',
          'Comparison of JWT, API key and cookies',
        ),
        edges: artifactEdges('authnotes'),
      }),
      handoff('r2p', '2', 'planner', 'JWT recommended. Details and lifetimes attached.', [
        'ar.authnotes',
        'f.jwt',
        'f.ttl',
      ]),
    ],
  },
  {
    n: 7,
    agent: 'planner',
    ops: [
      recall('which authentication scheme should we use?', 'jwt', 'ttl', 'auth_cands'),
      claim('5', 1),
      decide('jwt', '5', 'Authenticate with JWT bearer tokens', 'jwt', 'ttl'),
      complete('5', 2),
    ],
  },
  {
    n: 8,
    agent: 'researcher',
    ops: [
      claim('3', 1),
      recall('database options and benchmarks', 'goal', 'lang'),
      af('db_cands', 'db', 'candidate_stores', 'PostgreSQL, SQLite, MongoDB', { src: 'bench' }),
      af('pg_tp', 'db', 'postgres_throughput', 'about 9k note writes per second on the benchmark box', {
        src: 'bench',
        conf: 0.75,
      }),
      af('sqlite', 'db', 'sqlite_limit', 'single writer; fine for local development only', { src: 'bench' }),
    ],
  },
  {
    n: 9,
    agent: 'researcher',
    ops: [
      af('pg', 'db', 'recommendation', 'PostgreSQL 16', {
        src: 'bench',
        from: ['pg_tp', 'sqlite'],
        conf: 0.85,
      }),
      af('size', 'db', 'note_body_limit', 'max note body 64 KB', { src: 'brief' }),
      af('fts', 'db', 'search', 'full-text search via tsvector', { src: 'bench', conf: 0.8 }),
      complete('3', 2, {
        nodes: artifact(
          'storage',
          'doc',
          'artifacts/storage-notes.md',
          'Storage comparison and recommendation',
        ),
        edges: artifactEdges('storage'),
      }),
      handoff('r2b', '3', 'builder', 'Use PostgreSQL 16. Notes are capped at 64 KB.', [
        'ar.storage',
        'f.pg',
        'f.fts',
      ]),
    ],
  },
  {
    n: 10,
    agent: 'planner',
    ops: [
      claim('4', 1),
      af('paths', 'ep', 'paths', '/v1/notes and /v1/notes/{id}', { ep: 'p1', conf: 0.85 }),
      af('methods', 'ep', 'methods', 'GET, POST, PUT, PATCH, DELETE', { ep: 'p1' }),
    ],
  },
  {
    n: 11,
    agent: 'planner',
    ops: [
      af('page_style', 'page', 'style', 'cursor-based', { src: 'guide' }),
      af('page_size', 'page', 'default_page_size', '50', { src: 'guide' }),
      af('rate_limit', 'rate', 'limit', '100 requests per minute per token', { src: 'guide' }),
      decide('page', '4', 'Use cursor pagination with a default page size of 50', 'page_style', 'page_size'),
      complete('4', 2, {
        nodes: artifact(
          'spec1',
          'openapi',
          'artifacts/api-spec.yaml',
          'REST spec for notes endpoints (draft)',
        ),
        edges: artifactEdges('spec1', 'researcher'),
      }),
      handoff('p2b', '4', 'builder', 'Spec drafted. Implement storage and CRUD on top of it.', [
        'ar.spec1',
        'f.paths',
        'f.methods',
        'f.page_style',
      ]),
    ],
  },
  {
    n: 12,
    agent: 'builder',
    ops: [
      startSession('builder1'),
      recall('storage choice and API spec', 'pg', 'paths', 'page_style', 'lang'),
      { tool: 'best_procedure', read: [] },
      claim('6', 1),
    ],
  },
  {
    n: 13,
    agent: 'builder',
    ops: [
      af(
        'schema',
        'db',
        'schema',
        'notes(id uuid, owner text, title text, body text, created_at, updated_at)',
        {
          from: ['pg', 'size'],
          conf: 0.9,
        },
      ),
      decide('pg', '6', 'Use PostgreSQL 16 for notes storage', 'pg', 'pg_tp'),
      complete('6', 2, {
        nodes: artifact(
          'schemasql',
          'sql',
          'artifacts/schema.sql',
          'DDL for the notes table and tsvector index',
        ),
        edges: artifactEdges('schemasql', 'planner'),
      }),
    ],
  },
  {
    n: 14,
    agent: 'builder',
    ops: [
      claim('7', 1),
      remember('b1', 'builder1', 'assistant', 'Scaffolding FastAPI app and wiring PostgreSQL pool.'),
      af('scaffold', 'ep', 'scaffold', 'FastAPI app skeleton and PostgreSQL pool created', { ep: 'b1' }),
    ],
  },
  // step 15: the builder process is killed after its last call; no heartbeat, the T7 lease will expire.
  {
    n: 15,
    agent: 'builder',
    ops: [
      af('wip_post', 'ep', 'status', 'POST /v1/notes half implemented, validation missing', {
        ep: 'b1',
        conf: 0.6,
      }),
    ],
  },
  {
    n: 16,
    agent: 'planner',
    ops: [
      remember(
        'p3',
        'planner',
        'assistant',
        'No heartbeat from the builder for T7. Waiting for the lease to expire.',
        'p1',
      ),
      {
        tool: 'who_knew',
        read: ['wip_post'],
      },
    ],
  },
  {
    n: 17,
    agent: 'builder',
    ops: [
      { ...startSession('builder2'), patch: { 'ses.builder1': { ended_at: NOW } } },
      recall('what was I working on?', 'scaffold', 'wip_post', 'schema', 'pg'),
      claim('7', 2),
    ],
  },
  {
    n: 18,
    agent: 'builder',
    ops: [
      af('post_done', 'ep', 'implemented', 'POST /v1/notes and GET /v1/notes/{id} done with validation', {
        from: ['wip_post'],
      }),
      af('status_codes', 'ep', 'error_format', 'RFC 7807 problem+json for 4xx and 5xx', { src: 'guide' }),
    ],
  },
  {
    n: 19,
    agent: 'builder',
    ops: [
      af(
        'crud_done',
        'ep',
        'implemented_more',
        'PUT, PATCH and DELETE done; list endpoint returns 50 notes',
        {
          from: ['post_done', 'page_size'],
        },
      ),
      complete('7', 3, {
        nodes: artifact('router', 'code', 'src/acme_notes/routers/notes.py', 'Notes CRUD router (v1 paths)'),
        edges: artifactEdges('router', 'researcher'),
      }),
    ],
  },
  {
    n: 20,
    agent: 'researcher',
    ops: [
      remember('r2', 'researcher', 'assistant', 'api-guidelines-v2 says all new services ship under /v2.'),
      af('v2', 'api', 'api_version', 'v2', { src: 'guide', ep: 'r2', supersedes: 'v1', conf: 0.95 }),
      af('v2path', 'api', 'version_path', 'all routes under /v2, /v1 deprecated', {
        src: 'guide',
        conf: 0.95,
      }),
    ],
  },
  {
    n: 21,
    agent: 'builder',
    ops: [
      remember(
        'b2',
        'builder2',
        'assistant',
        'Legacy gateway wiki recommends X-Api-Key headers for internal APIs.',
        undefined,
      ),
      af('apikey', 'auth', 'scheme', 'API key', { src: 'legacy', ep: 'b2', contradicts: 'jwt', conf: 0.55 }),
    ],
  },
  {
    n: 22,
    agent: 'planner',
    ops: [
      recall('which authentication scheme should we use?', 'jwt', 'apikey', 'ttl'),
      { tool: 'why_recalled', read: ['jwt', 'apikey'] },
      af(
        'auth_res',
        'auth',
        'resolution',
        'JWT is the primary scheme; API keys only for service-to-service calls',
        {
          from: ['jwt', 'apikey'],
          conf: 0.9,
        },
      ),
      decide('nokey', '5', 'Reject API keys as the primary auth scheme', 'jwt', 'auth_res'),
    ],
  },
  {
    n: 23,
    agent: 'planner',
    ops: [
      af('paths2', 'ep', 'paths', '/v2/notes and /v2/notes/{id}', {
        from: ['v2path'],
        supersedes: 'paths',
        conf: 0.95,
      }),
      decide('v2', '4', 'Ship the API under the /v2 prefix', 'v2', 'v2path'),
      { tool: 'as_of', read: ['v1', 'v2'] },
    ],
  },
  {
    n: 24,
    agent: 'builder',
    ops: [
      claim('8', 1),
      recall('how should the API authenticate requests?', 'jwt', 'ttl', 'auth_res'),
      af('mw', 'auth', 'middleware', 'verify RS256 signature and reject expired tokens', {
        from: ['jwt', 'ttl'],
      }),
      af('lang2', 'api', 'language', 'Python 3.12 / FastAPI', {
        duplicates: 'lang',
        scope: 'global',
        conf: 0.7,
      }),
    ],
  },
  {
    n: 25,
    agent: 'researcher',
    ops: [
      claim('9', 1),
      recall('rate limiting library for FastAPI', 'rate_limit', 'lang', 'page_size'),
      af('slowapi', 'rate', 'library', 'slowapi 0.1.9', { conf: 0.6 }),
    ],
  },
  {
    n: 26,
    agent: 'researcher',
    ops: [
      af(
        'compat',
        'rate',
        'compatibility',
        'slowapi middleware order breaks the JWT middleware on FastAPI 0.136',
        {
          from: ['slowapi', 'mw'],
          conf: 0.85,
        },
      ),
      af('fallback', 'rate', 'fallback', 'implement an in-process token bucket per token id', {
        from: ['compat'],
      }),
      {
        tool: 'fail_task',
        patch: { 't.9': { status: 'failed', lease_until: 0, version: 2 } },
      },
    ],
  },
  {
    n: 27,
    agent: 'planner',
    ops: [
      { tool: 'blocked_by_failure', read: ['compat'] },
      af('blocked', 'test', 'blocked', 'integration tests wait for pagination and rate limiting (T9)', {
        from: ['compat'],
      }),
      decide('bucket', '9', 'Implement an in-process token bucket instead of slowapi', 'compat', 'fallback'),
      handoff('p2r2', '9', 'researcher', 'Retry T9 with the token bucket fallback.', [
        'f.fallback',
        'f.compat',
      ]),
    ],
  },
  {
    n: 28,
    agent: 'builder',
    ops: [
      { tool: 'knew_at', read: ['jwt', 'apikey'] },
      af('mw_tests', 'test', 'auth_unit_tests', '12 auth middleware unit tests passing', { from: ['mw'] }),
      { tool: 'heartbeat', patch: { 't.8': { lease_until: LEASE } } },
    ],
  },
  {
    n: 29,
    agent: 'builder',
    ops: [
      af('openapi_status', 'api', 'openapi_status', 'draft, waiting for T10', { from: ['crud_done'] }),
      {
        tool: 'log_procedure_run',
        nodes: [
          [
            'Procedure',
            'pr.crud',
            {
              name: 'scaffold-crud-endpoints',
              task_type: 'implement-endpoints',
              steps_json: '["create router","add pydantic models","wire db pool","write handlers"]',
            },
          ],
          ['Run', 'run.crud', { at: NOW, success: true, notes: 'CRUD router done after one restart' }],
        ],
        edges: [
          ['USED_IN', 'pr.crud', 'run.crud'],
          ['BY', 'run.crud', '$agent'],
          ['FOR', 'run.crud', 't.7'],
        ],
      },
    ],
  },
  {
    n: 30,
    agent: 'planner',
    ops: [
      af('status', 'api', 'status', 'v2 mostly implemented; T8 in progress, T9 failed, T11 and T12 waiting', {
        from: ['crud_done', 'compat'],
      }),
      af('target', 'dep', 'target', 'Docker image on a single VM', { src: 'brief' }),
      af('ci', 'dep', 'ci', 'GitHub Actions: lint, test, build', { src: 'brief' }),
    ],
  },
];

/* ---------- expansion ---------- */

function fakeHash(key: string): string {
  let h = 2166136261;
  let out = '';
  for (let round = 0; round < 4; round++) {
    for (let i = 0; i < key.length; i++) h = Math.imul(h ^ (key.charCodeAt(i) + round), 16777619) >>> 0;
    out += h.toString(16).padStart(8, '0');
  }
  return out;
}

function uuid(prefix: number, n: number): string {
  return `${prefix.toString(16).padStart(8, '0')}-0000-4000-8000-${n.toString(16).padStart(12, '0')}`;
}

export interface AcmeDataset {
  nodes: GraphNode[];
  edges: GraphEdge[];
  flow: FlowEvent[];
  /** script keys -> node ids, for tests and the Why fixture. */
  ids: Record<string, string>;
  /** Step number -> agent id and time. */
  steps: { n: number; at: number; agent_id: string; node_id: string }[];
}

export function buildAcme(): AcmeDataset {
  const nodes = new Map<string, GraphNode>();
  const edges: GraphEdge[] = [];
  const created = new Map<string, number>();
  const counters: Record<string, number> = {};
  let edgeSeq = 0;

  const mkNode = (label: NodeLabel, key: string, props: Props, at: number): GraphNode => {
    const c = (counters[label] = (counters[label] ?? 0) + 1);
    const node: GraphNode = {
      id: uuid(NODE_LABELS.indexOf(label) + 1, c),
      label,
      props: { ...props, created_at: at },
    };
    nodes.set(key, node);
    created.set(key, at);
    return node;
  };
  const idOf = (key: string): string => {
    const n = nodes.get(key);
    if (!n) throw new Error(`fixture: unknown node key ${key}`);
    return n.id;
  };
  const mkEdge = (type: string, src: string, dst: string, props: Props = {}): void => {
    edges.push({ id: uuid(0xe, ++edgeSeq), type, src: idOf(src), dst: idOf(dst), props });
  };
  const rand = (() => {
    let s = 20261015;
    return () => (s = (Math.imul(s, 1103515245) + 12345) >>> 0) / 2 ** 32;
  })();

  /** Replace tokens and `@key` references in property values. */
  const resolve = (props: Props, agentKey: string, at: number, step: number): Props => {
    const out: Props = {};
    for (const [k, v] of Object.entries(props)) {
      let r: PropValue = v;
      if (v === NOW) r = at;
      else if (v === LEASE) r = at + 120_000;
      else if (v === STEP) r = step;
      else if (typeof v === 'string' && v.startsWith('@')) r = idOf(v.slice(1).replace('$agent', agentKey));
      out[k] = r;
    }
    return out;
  };
  const sub = (key: string, agentKey: string) => key.replace('$agent', agentKey);

  /* top-level seed: agents, scopes, sources (created before step 1) */
  const seed = T0;
  const agentDefs: [AgentName, string][] = [
    ['planner', 'plans and decomposes work, owns the spec'],
    ['researcher', 'investigates options and records findings'],
    ['builder', 'implements and tests the service'],
  ];
  for (const [name, role] of agentDefs)
    mkNode('Agent', `a.${name}`, { name, role, harness: 'claude-code' }, seed);
  mkNode('Scope', 'sc.global', { kind: 'global', name: 'global' }, seed);
  mkNode('Scope', 'sc.project', { kind: 'project', name: 'acme-notes' }, seed);
  mkEdge('INHERITS', 'sc.project', 'sc.global');
  const sources: [string, string, string, number][] = [
    ['brief', 'docs/acme-notes-brief.md', 'doc', 0.9],
    ['rfc', 'docs/rfc-0042-auth.md', 'rfc', 0.9],
    ['bench', 'docs/postgres-vs-sqlite-bench.md', 'benchmark', 0.8],
    ['guide', 'docs/api-guidelines-v2.md', 'guideline', 0.95],
    ['legacy', 'wiki/legacy-gateway-notes.md', 'wiki', 0.5],
  ];
  for (const [k, uri, kind, trust] of sources) mkNode('Source', `s.${k}`, { uri, kind, trust }, seed);

  const flow: FlowEvent[] = [];
  const stepRows: AcmeDataset['steps'] = [];
  const agentEdgeCache = new Set<string>();
  let prevStepKey: string | undefined;
  const pendingSubjects: [string, string][] = []; // fact key, entity key

  for (const step of SCRIPT) {
    const agentKey = `a.${step.agent}`;
    const stepAt = stepTime(step.n);
    const stepKey = `step.${step.n}`;
    const stepNode = mkNode('Step', stepKey, { n: step.n, at: stepAt, agent_id: idOf(agentKey) }, stepAt);
    mkEdge('BY', stepKey, agentKey);
    if (prevStepKey) mkEdge('NEXT', prevStepKey, stepKey);
    prevStepKey = stepKey;
    stepRows.push({ n: step.n, at: stepAt, agent_id: idOf(agentKey), node_id: stepNode.id });
    const read = new Set<string>();
    const wrote = new Set<string>();

    step.ops.forEach((op, i) => {
      const at = stepAt + i * 2000 + 500;
      const createdIds: string[] = [];
      const updatedIds: string[] = [];

      // entities referenced by an assert_fact are created lazily by the first call that mentions them
      for (const [, , dst] of op.edges ?? []) {
        if (dst.startsWith('e.') && !nodes.has(dst)) {
          const def = ENTITIES[dst.slice(2) as EntityName];
          const norm = def[0].toLowerCase().replace(/\s+/g, ' ');
          createdIds.push(mkNode('Entity', dst, { name: def[0], norm_name: norm, kind: def[1] }, at).id);
        }
      }
      for (const [label, key, props] of op.nodes ?? []) {
        const defaults: Props = label === 'Fact' ? { valid_from: at, valid_to: OPEN, recorded_at: at } : {};
        const n = mkNode(label, key, { ...defaults, ...resolve(props, agentKey, at, step.n) }, at);
        createdIds.push(n.id);
        if (label === 'Fact' || label === 'Decision' || label === 'Handoff' || label === 'Task')
          wrote.add(n.id);
      }
      for (const [type, s, d, p] of op.edges ?? []) {
        mkEdge(type, sub(s, agentKey), sub(d, agentKey), resolve(p ?? {}, agentKey, at, step.n));
        if (type === 'ABOUT') pendingSubjects.push([s, d]);
      }
      for (const [key, change] of Object.entries(op.patch ?? {})) {
        const n = nodes.get(key);
        if (!n) throw new Error(`fixture: patch of unknown node ${key}`);
        n.props = { ...n.props, ...resolve(change, agentKey, at, step.n) };
        updatedIds.push(n.id);
        if (n.label === 'Task' || n.label === 'Fact') wrote.add(n.id);
      }
      for (const f of op.read ?? []) read.add(idOf(`f.${f}`));

      if (op.recall) {
        const rk = `rc.${step.n}.${i}`;
        const rc = mkNode(
          'Recall',
          rk,
          { at, query: op.recall.query, scope_id: idOf('sc.project'), agent_id: idOf(agentKey), k: 5 },
          at,
        );
        createdIds.push(rc.id);
        mkEdge('BY', rk, agentKey);
        mkEdge('IN_STEP', rk, stepKey);
        op.recall.facts.forEach((f, rank) => {
          mkEdge('RETURNED', rk, `f.${f}`, {
            rank: rank + 1,
            score: Math.round((0.08 + rank * 0.07 + rand() * 0.03) * 1000) / 1000,
          });
          read.add(idOf(`f.${f}`));
        });
      }

      const tcKey = `tc.${step.n}.${i}`;
      const tc = mkNode(
        'ToolCall',
        tcKey,
        {
          tool: op.tool,
          at,
          agent_id: idOf(agentKey),
          query_name: QUERY_NAMES[op.tool] ?? `unknown/${op.tool}`,
          run_time_ms: Math.round((1.2 + rand() * 9) * 10) / 10,
          wrote: WRITE_TOOLS.has(op.tool),
        },
        at,
      );
      mkEdge('IN_STEP', tcKey, stepKey);
      for (const id of createdIds)
        edges.push({ id: uuid(0xe, ++edgeSeq), type: 'CREATED', src: tc.id, dst: id, props: {} });
      for (const id of updatedIds)
        edges.push({ id: uuid(0xe, ++edgeSeq), type: 'UPDATED', src: tc.id, dst: id, props: {} });
      flow.push({
        id: tc.id,
        tool: op.tool,
        at,
        agent_id: idOf(agentKey),
        query_name: String(tc.props.query_name),
        run_time_ms: Number(tc.props.run_time_ms),
        created: createdIds,
        updated: updatedIds,
      });
    });

    for (const id of read) {
      const k = `${stepNode.id}>${id}`;
      if (agentEdgeCache.has(k)) continue;
      agentEdgeCache.add(k);
      edges.push({ id: uuid(0xe, ++edgeSeq), type: 'READ', src: stepNode.id, dst: id, props: {} });
    }
    for (const id of wrote)
      edges.push({ id: uuid(0xe, ++edgeSeq), type: 'WROTE', src: stepNode.id, dst: id, props: {} });
  }

  for (const [fk, ek] of pendingSubjects) {
    const f = nodes.get(fk);
    if (f) f.props = { ...f.props, subject_id: idOf(ek) };
  }

  const ids: Record<string, string> = {};
  for (const [k, n] of nodes) ids[k] = n.id;
  return {
    nodes: [...nodes.values()],
    edges,
    flow: flow.sort((a, b) => a.at - b.at),
    ids,
    steps: stepRows,
  };
}
