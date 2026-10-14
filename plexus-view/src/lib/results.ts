/**
 * Read the Crucible results JSON (`GET /api/results`) defensively.
 *
 * The documented shape lives in plexus/src/plexus/crucible/results.py (`schema_version` 1): layers L1, L4 and
 * ablation, with L2 (provenance Q&A accuracy per arm) arriving later. Anything missing or oddly shaped is
 * skipped rather than thrown, so a newer or partial file still renders what it can.
 */
type Obj = Record<string, unknown>;
const isObj = (v: unknown): v is Obj => typeof v === 'object' && v !== null && !Array.isArray(v);
const num = (v: unknown): number | undefined => (typeof v === 'number' && Number.isFinite(v) ? v : undefined);
const str = (v: unknown): string => (typeof v === 'string' ? v : v == null ? '' : String(v));
const arr = (v: unknown): unknown[] => (Array.isArray(v) ? v : []);
const strs = (v: unknown): string[] => arr(v).map(str);

export interface ArmInfo {
  id: string;
  label: string;
  represents: string;
}
export type CellState = 'pass' | 'fail' | 'n/a' | 'none';
export interface L1Row {
  id: string;
  title: string;
  bar: string;
  cells: { arm: string; state: CellState; text: string }[];
}
export interface L1Table {
  arms: string[];
  rows: L1Row[];
}
export interface L2Row {
  arm: string;
  /** 0..100 */
  accuracy: number;
  n?: number;
}
export interface Percentiles {
  p50: number;
  p95: number;
  p99: number;
}
export interface L4Point {
  arm: string;
  /** workers (claim / recall sweeps) or tenants (tenant sweep) */
  x: number;
  throughput?: number;
  errors: number;
  ops: Record<string, { client: Percentiles; server?: Percentiles }>;
}
export interface L4Sweep {
  key: string;
  title: string;
  xLabel: string;
  points: L4Point[];
  ops: string[];
}
export interface AblationCapability {
  capability: string;
  needs: string;
  intactPass: boolean;
  ablatedPass: boolean;
  breaks: boolean;
}
export interface AblationView {
  title: string;
  stripped: string[];
  capabilities: AblationCapability[];
  summary: { label: string; value: string }[];
  l1: { test: string; arm: string; violations: string }[];
}
export interface ParsedResults {
  schemaVersion?: number;
  run?: {
    id: string;
    startedAt: string;
    durationS?: number;
    quick: boolean;
    command: string;
    layers: string[];
  };
  headline: string[];
  honesty: string[];
  arms: ArmInfo[];
  l1?: L1Table;
  l2?: L2Row[];
  l4: L4Sweep[];
  ablation?: AblationView;
  /** Top-level keys nobody here knows how to draw (shown as raw JSON). */
  unknown: string[];
}

function parseArms(raw: unknown): ArmInfo[] {
  if (!isObj(raw)) return [];
  return Object.entries(raw).map(([id, v]) => ({
    id,
    label: isObj(v) ? str(v.label) || id : id,
    represents: isObj(v) ? str(v.represents) : '',
  }));
}

function cellOf(r: unknown): { state: CellState; text: string } {
  if (!isObj(r)) return { state: 'none', text: '-' };
  if (r.unsupported === true) return { state: 'n/a', text: 'n/a (unsupported)' };
  const runs = num(r.runs) ?? 0;
  const ok = num(r.runs_passed) ?? 0;
  if (r.passed === true) return { state: 'pass', text: `pass (${ok}/${runs})` };
  const bad = isObj(r.violations_total)
    ? Object.entries(r.violations_total)
        .filter(([, v]) => v)
        .map(([k, v]) => `${k}=${str(v)}`)
        .join(', ')
    : '';
  return { state: 'fail', text: `FAIL ${ok}/${runs}${bad ? ` (${bad})` : ''}` };
}

function parseL1(layer: unknown): L1Table | undefined {
  if (!isObj(layer) || !isObj(layer.tests)) return undefined;
  const armsObj = isObj(layer.arms) ? layer.arms : {};
  const arms = Object.keys(armsObj);
  const rows = Object.entries(layer.tests).map(([id, spec]) => {
    const s = isObj(spec) ? spec : {};
    return {
      id,
      title: str(s.title),
      bar: str(s.bar ?? s.pass_bar),
      cells: arms.map((arm) => {
        const a = armsObj[arm];
        const t = isObj(a) && isObj(a.tests) ? a.tests[id] : undefined;
        return { arm, ...cellOf(t) };
      }),
    };
  });
  return { arms, rows };
}

const ACCURACY_KEYS = ['accuracy', 'overall', 'exact_match', 'em', 'score', 'acc'];
function accuracyOf(v: unknown): { accuracy: number; n?: number } | undefined {
  if (typeof v === 'number') return { accuracy: v };
  if (!isObj(v)) return undefined;
  for (const k of ACCURACY_KEYS) {
    const direct = num(v[k]);
    if (direct !== undefined) return { accuracy: direct, n: num(v.n ?? v.questions ?? v.total) };
  }
  if (isObj(v.summary)) return accuracyOf(v.summary);
  const correct = num(v.correct);
  const total = num(v.total ?? v.n ?? v.questions);
  if (correct !== undefined && total) return { accuracy: correct / total, n: total };
  return undefined;
}

/** L2: accuracy per arm. Accepts `{arms: {B0: {accuracy}}}`, `{B0: {...}}`, or `[{arm, accuracy}]`. */
function parseL2(layer: unknown): L2Row[] | undefined {
  const rows: L2Row[] = [];
  const push = (arm: string, v: unknown) => {
    const a = accuracyOf(v);
    if (!a) return;
    // ratios (0..1) are shown as percentages
    rows.push({ arm, accuracy: a.accuracy <= 1 ? a.accuracy * 100 : a.accuracy, n: a.n });
  };
  if (Array.isArray(layer)) {
    for (const item of layer) if (isObj(item)) push(str(item.arm ?? item.name), item);
  } else if (isObj(layer)) {
    const source = isObj(layer.arms) ? layer.arms : Array.isArray(layer.arms) ? undefined : layer;
    if (source) for (const [arm, v] of Object.entries(source)) push(arm, v);
    else for (const item of arr(layer.arms)) if (isObj(item)) push(str(item.arm ?? item.name), item);
  }
  return rows.length > 0 ? rows : undefined;
}

function percentiles(o: unknown, prefix = ''): Percentiles | undefined {
  if (!isObj(o)) return undefined;
  const p50 = num(o[`${prefix}p50_ms`]);
  const p95 = num(o[`${prefix}p95_ms`]);
  const p99 = num(o[`${prefix}p99_ms`]);
  return p50 !== undefined && p99 !== undefined ? { p50, p95: p95 ?? p99, p99 } : undefined;
}

const SWEEP_TITLES: Record<string, string> = {
  claim_sweep: 'Claim / heartbeat / complete cycles',
  recall_sweep: 'Recall',
  tenant_sweep: 'One graph per tenant',
};

function parseSweep(key: string, raw: unknown): L4Sweep | undefined {
  const pts = arr(raw).filter(isObj);
  if (pts.length === 0) return undefined;
  const xKey = pts.some((p) => num(p.workers) !== undefined) ? 'workers' : 'tenants';
  const ops = new Set<string>();
  const points: L4Point[] = pts.map((p) => {
    const o: L4Point['ops'] = {};
    for (const [k, v] of Object.entries(p)) {
      const client = percentiles(v);
      if (!client) continue;
      o[k] = { client, server: percentiles(v, 'server_') };
      ops.add(k);
    }
    return {
      arm: str(p.arm),
      x: num(p[xKey]) ?? 0,
      throughput: num(p.throughput_ops_s),
      errors: num(p.error_count) ?? 0,
      ops: o,
    };
  });
  return { key, title: SWEEP_TITLES[key] ?? key, xLabel: xKey, points, ops: [...ops] };
}

function parseAblation(raw: unknown): AblationView | undefined {
  if (!isObj(raw)) return undefined;
  const capabilities = arr(raw.capabilities)
    .filter(isObj)
    .map((c) => ({
      capability: str(c.capability),
      needs: str(c.needs),
      intactPass: isObj(c.intact) && c.intact.passed === true,
      ablatedPass: isObj(c.ablated) && c.ablated.passed === true,
      breaks: c.breaks_without_edges === true,
    }));
  const summary = isObj(raw.summary)
    ? Object.entries(raw.summary).map(([label, value]) => ({
        label: label.replace(/_/g, ' '),
        value: str(value),
      }))
    : [];
  const l1: AblationView['l1'] = [];
  if (isObj(raw.l1_rerun))
    for (const [arm, tests] of Object.entries(raw.l1_rerun))
      if (isObj(tests))
        for (const [test, r] of Object.entries(tests)) {
          const v = isObj(r) && isObj(r.violations_total) ? r.violations_total : {};
          const text = Object.entries(v)
            .map(([k, x]) => `${k}=${str(x)}`)
            .join(', ');
          l1.push({ test, arm, violations: text || '0 violations' });
        }
  return {
    title: str(raw.title) || 'Ablation: what breaks when the edges are removed',
    stripped: strs(raw.stripped_relationship_types),
    capabilities,
    summary,
    l1,
  };
}

const KNOWN_TOP = new Set([
  'schema_version',
  'kind',
  'run',
  'environment',
  'config',
  'arms',
  'layers',
  'summary',
  'honesty',
]);

export function parseResults(raw: unknown): ParsedResults {
  const out: ParsedResults = { headline: [], honesty: [], arms: [], l4: [], unknown: [] };
  if (!isObj(raw)) return out;
  out.schemaVersion = num(raw.schema_version);
  if (isObj(raw.run)) {
    const r = raw.run;
    out.run = {
      id: str(r.id),
      startedAt: str(r.started_at),
      durationS: num(r.duration_s),
      quick: r.quick === true,
      command: str(r.command),
      layers: strs(r.layers),
    };
  }
  out.arms = parseArms(raw.arms);
  out.honesty = strs(raw.honesty);
  if (isObj(raw.summary)) out.headline = strs(raw.summary.headline);
  const layers = isObj(raw.layers) ? raw.layers : {};
  out.l1 = parseL1(layers.L1);
  out.l2 = parseL2(layers.L2);
  if (isObj(layers.L4)) {
    for (const key of ['claim_sweep', 'recall_sweep', 'tenant_sweep']) {
      const s = parseSweep(key, layers.L4[key]);
      if (s) out.l4.push(s);
    }
  }
  out.ablation = parseAblation(layers.ablation);
  out.unknown = Object.keys(raw).filter((k) => !KNOWN_TOP.has(k));
  return out;
}

/** The single best point per arm for a bar chart: the largest x (most workers / tenants). */
export function peakPoints(sweep: L4Sweep): L4Point[] {
  const best = new Map<string, L4Point>();
  for (const p of sweep.points) {
    const cur = best.get(p.arm);
    if (!cur || p.x > cur.x) best.set(p.arm, p);
  }
  return [...best.values()];
}
