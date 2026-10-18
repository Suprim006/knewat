import type { Results } from '../api/types';

/**
 * A results file in the shape knewat/src/knewat/crucible/results.py documents, with made-up numbers.
 * Only for tests; it is never served by the app (the fixture API answers /api/results with 404 so the
 * Results page shows its "no results yet" state, and the live API serves the real file).
 */
const point = (arm: string, workers: number, p50: number, p99: number, srv = true) => ({
  arm,
  workers,
  tasks: 500,
  throughput_ops_s: Math.round(10000 / (p50 + workers / 10)),
  error_count: 0,
  claim: {
    n: 500,
    p50_ms: p50,
    p95_ms: (p50 + p99) / 2,
    p99_ms: p99,
    ...(srv ? { server_p50_ms: p50 / 10, server_p95_ms: p99 / 10, server_p99_ms: p99 / 8 } : {}),
  },
  heartbeat: { n: 500, p50_ms: p50 / 2, p95_ms: p99 / 2, p99_ms: p99 / 1.5 },
  complete: { n: 500, p50_ms: p50, p95_ms: p99 / 1.2, p99_ms: p99 },
});

export const SAMPLE_RESULTS: Results = {
  schema_version: 1,
  kind: 'crucible-results',
  run: {
    id: 'sample-run',
    started_at: '2026-10-17T10:00:00Z',
    finished_at: '2026-10-17T10:20:00Z',
    duration_s: 1200,
    quick: true,
    command: 'crucible all --quick',
    layers: ['L1', 'L2', 'L4', 'ablation'],
  },
  environment: { python: '3.12', in_docker: true },
  config: { seeds: [1, 2, 3] },
  arms: {
    B0: { label: 'Files', represents: 'Markdown memory + JSON task list with locks', isolation: 'directory' },
    B1: { label: 'SQLite', represents: 'Just use a relational database', isolation: 'database file' },
    P: { label: 'Knewat', represents: 'FalkorDB, one graph per tenant', isolation: 'graph per tenant' },
  },
  layers: {
    L1: {
      title: 'L1: correctness',
      tests: {
        C1: { title: 'Race to claim', metric: 'double claims', bar: '0 / 0 / 0' },
        C6: { title: 'As-of queries', metric: 'wrong versions', bar: '0' },
      },
      arms: {
        B0: {
          tests: {
            C1: { runs: 10, runs_passed: 10, passed: true, unsupported: false, violations_total: {} },
            C6: { runs: 10, runs_passed: 0, passed: false, unsupported: true, violations_total: {} },
          },
        },
        B1: {
          tests: {
            C1: { runs: 10, runs_passed: 10, passed: true, unsupported: false, violations_total: {} },
            C6: {
              runs: 10,
              runs_passed: 7,
              passed: false,
              unsupported: false,
              violations_total: { wrong_version: 12 },
            },
          },
        },
        P: {
          tests: {
            C1: { runs: 10, runs_passed: 10, passed: true, unsupported: false, violations_total: {} },
            C6: { runs: 10, runs_passed: 10, passed: true, unsupported: false, violations_total: {} },
          },
        },
      },
    },
    L2: {
      arms: { B0: { accuracy: 0.45, n: 40 }, B1: { accuracy: 0.6, n: 40 }, P: { accuracy: 0.9, n: 40 } },
    },
    L4: {
      title: 'L4: performance',
      claim_sweep: [
        point('B1', 10, 4, 12),
        point('B1', 100, 20, 80),
        point('P', 10, 6, 15),
        point('P', 100, 18, 60),
      ],
      recall_sweep: [
        {
          arm: 'P',
          workers: 50,
          error_count: 0,
          throughput_ops_s: 900,
          recall: { p50_ms: 8, p95_ms: 15, p99_ms: 24 },
        },
      ],
      tenant_sweep: [],
      notes: ['Measured inside Docker.'],
    },
    ablation: {
      title: 'Ablation',
      stripped_relationship_types: ['DEPENDS_ON', 'BASED_ON', 'DERIVED_FROM', 'READ'],
      capabilities: [
        {
          capability: 'why(decision)',
          needs: 'BASED_ON',
          intact: { passed: true },
          ablated: { passed: false },
          breaks_without_edges: true,
        },
        {
          capability: 'as_of',
          needs: '(none: control)',
          intact: { passed: true },
          ablated: { passed: true },
          breaks_without_edges: false,
        },
      ],
      l1_rerun: {
        P: { C4: { violations_total: {} } },
        'P-abl': { C4: { violations_total: { started_before_deps: 31 } } },
      },
      summary: { capabilities_needing_edges: 1, broken_by_ablation: 1, controls: 1, controls_unaffected: 1 },
    },
  },
  summary: {
    headline: ['Knewat: 0 violations across C1-C8.', 'Ablation breaks 1 of 1 edge-dependent capabilities.'],
  },
  honesty: ['SAMPLE data for UI tests, not measured.'],
};
