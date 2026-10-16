/**
 * P9 layers of the combined results file, read defensively like lib/results.ts: `layers.B1h` (hand-written SQL on the
 * L2 and L2-scale questions), `layers.C7x` (the extended duplicate corpus) and `layers.L6` (the pre-registered beat-SQL
 * families, with their LLM pilot and the post-fix re-run). Anything missing is skipped.
 */
type Obj = Record<string, unknown>;
const isObj = (v: unknown): v is Obj => typeof v === 'object' && v !== null && !Array.isArray(v);
const num = (v: unknown): number | undefined => (typeof v === 'number' && Number.isFinite(v) ? v : undefined);
const str = (v: unknown): string => (typeof v === 'string' ? v : v == null ? '' : String(v));
const obj = (v: unknown): Obj => (isObj(v) ? v : {});

// ------------------------------------------------------------------------------------------------ B1h
export interface B1hRow {
  layer: 'L2' | 'L2_scale';
  title: string;
  correct: number;
  total: number;
  /** Plexus on the same questions (from layers.L2 / layers.L2_scale), if present. */
  plexusCorrect?: number;
  bothCorrect?: number;
  b1hOnly?: number;
  pOnly?: number;
  bothWrong?: number;
}
export interface B1hInfo {
  rows: B1hRow[];
  answerer: string;
  sqlLines?: number;
  cypherLines?: number;
  llmCalls: number;
  honesty: string[];
}

export function parseB1h(layer: unknown, plexus: Record<string, number | undefined>): B1hInfo | undefined {
  if (!isObj(layer) || !isObj(layer.layers)) return undefined;
  const rows: B1hRow[] = [];
  for (const [key, title] of [
    ['L2', 'L2 · provenance questions'],
    ['L2_scale', 'L2-scale · 200 sprints'],
  ] as const) {
    const l = obj(obj(layer.layers)[key]);
    const acc = obj(obj(l.arm).accuracy);
    const correct = num(acc.correct);
    const total = num(acc.total);
    if (correct === undefined || total === undefined) continue;
    const p = obj(l.paired_with_P);
    rows.push({
      layer: key,
      title,
      correct,
      total,
      plexusCorrect: plexus[key],
      bothCorrect: num(p.both_correct),
      b1hOnly: num(p.b1h_only),
      pOnly: num(p.p_only),
      bothWrong: num(p.both_wrong),
    });
  }
  if (rows.length === 0) return undefined;
  const size = obj(layer.code_size);
  return {
    rows,
    answerer: str(layer.answerer),
    sqlLines: num(size.sql_answerer_lines),
    cypherLines: num(size.cypher_answerer_lines),
    llmCalls: num(obj(layer.run).llm_calls) ?? 0,
    honesty: Array.isArray(layer.honesty) ? layer.honesty.map(str) : [],
  };
}

// ------------------------------------------------------------------------------------------------ C7x
export interface C7xCategory {
  name: string;
  expected: string;
  pairs: number;
  merged: number;
  maybe: number;
  isNew: number;
  falseMerges: number;
  /** rule-of-three upper bound (0..1) when no false merge was seen, else undefined */
  upper?: number;
}
export interface C7xArm {
  arm: string;
  pairs: number;
  notMergePairs: number;
  mergePairs: number;
  falseMerges: number;
  autoMerged: number;
  surfaced: number;
}
export interface C7xInfo {
  arms: C7xArm[];
  categories: C7xCategory[];
  /** category -> {auto %, surfaced %} for the paraphrase categories, with the pre-registered target */
  targets: {
    category: string;
    autoPct: number;
    surfacedPct: number;
    targetAutoPct: number;
    missed: boolean;
  }[];
  falseMergeUpper95?: number;
}

export function parseC7x(layer: unknown): C7xInfo | undefined {
  if (!isObj(layer) || !isObj(layer.arms)) return undefined;
  const arms: C7xArm[] = Object.entries(layer.arms).flatMap(([arm, a]) => {
    const m = obj(obj(a).metrics);
    const pairs = num(m.pairs);
    return pairs === undefined
      ? []
      : [
          {
            arm,
            pairs,
            notMergePairs: num(m.not_merge_pairs) ?? 0,
            mergePairs: num(m.merge_pairs) ?? 0,
            falseMerges: num(m.false_merges) ?? 0,
            autoMerged: num(m.auto_merged) ?? 0,
            surfaced: num(m.surfaced) ?? 0,
          },
        ];
  });
  const categories: C7xCategory[] = Object.entries(obj(layer.by_category)).map(([name, c]) => {
    const o = obj(c);
    return {
      name,
      expected: str(o.expected),
      pairs: num(o.pairs) ?? 0,
      merged: num(o.merged) ?? 0,
      maybe: num(o.maybe) ?? 0,
      isNew: num(o.new) ?? 0,
      falseMerges: num(o.false_merges) ?? 0,
      upper: num(o.false_merge_upper_95),
    };
  });
  if (arms.length === 0 || categories.length === 0) return undefined;
  const t = obj(layer.targets);
  const heavyTarget = num(t.heavy_auto_pct) ?? 75;
  const heavySurfaced = num(t.heavy_surfaced_pct) ?? 95;
  const otherTarget = num(t.other_merge_categories_auto_pct) ?? 100;
  const targets = categories
    .filter((c) => c.expected === 'merge')
    .map((c) => {
      const autoPct = c.pairs ? (100 * c.merged) / c.pairs : 0;
      const surfacedPct = c.pairs ? (100 * (c.merged + c.maybe)) / c.pairs : 0;
      const heavy = c.name === 'heavy';
      const targetAutoPct = heavy ? heavyTarget : otherTarget;
      const missed = heavy ? autoPct < heavyTarget && surfacedPct < heavySurfaced : autoPct < otherTarget;
      return { category: c.name, autoPct, surfacedPct, targetAutoPct, missed };
    });
  return { arms, categories, targets, falseMergeUpper95: num(layer.false_merge_upper_95) };
}

// ------------------------------------------------------------------------------------------------ L6
export interface L6Arm {
  arm: string;
  strict: string;
  p50?: number;
  p99?: number;
  timeouts?: number;
}
export interface L6Conc {
  arm: string;
  v1: number;
  v2: number;
  v3: number;
  reads: number;
  runsWithViolation?: number;
}
export interface L6Crash {
  arm: string;
  orphans: number;
  orphansByKind?: Record<string, number>;
  acked: number;
  lost: number;
  total?: number;
}
export interface L6Pilot {
  arm: string;
  correct: number;
  n: number;
  costPerQuestion?: number;
  cost?: number;
  toolCalls?: number;
}
export interface L6Family {
  id: string;
  title: string;
  det: L6Arm[];
  dag: L6Arm[];
  conc: L6Conc[];
  crash: L6Crash[];
  pilot: L6Pilot[];
  /** D: median over the questions of (Plexus latency / SQL latency); undefined for other families */
  medianSlowdown?: number;
  /** the re-run after the P9-int fixes: A (the impact arms) and F (arm P only) */
  postfixA: (L6Arm & { max?: number })[];
  postfixF: L6Crash[];
}
export interface L6PilotTotal {
  arm: string;
  correct: number;
  n: number;
  cost: number;
}
export interface L6Info {
  families: L6Family[];
  pilotTotals: L6PilotTotal[];
  llmCalls: number;
  costUsd: number;
  budgetCapUsd?: number;
  postfixRun?: string;
}

const FAMILY_TITLES: Record<string, string> = {
  A: 'A · blast radius with diamonds',
  A_dag: 'A-dag · tasks blocked by a failure',
  B: 'B · why-chain depth',
  D: 'D · cross-sprint aggregation',
  E: 'E · consistent reads under concurrent writes',
  F: 'F · provenance crash-consistency',
};
const FAMILY_ORDER = ['A', 'B', 'D', 'E', 'F'];

function detArms(fam: unknown): L6Arm[] {
  const arms = obj(obj(obj(fam).det).arms);
  return Object.entries(arms).flatMap(([arm, a]) => {
    const o = obj(a);
    const c = num(o.strict_correct);
    const n = num(o.n);
    if (c === undefined || n === undefined) return [];
    const lat = obj(o.latency_ms);
    return [{ arm, strict: `${c}/${n}`, p50: num(lat.p50), p99: num(lat.p99), timeouts: num(o.timeouts) }];
  });
}

function medianSlowdown(fam: unknown): number | undefined {
  const arms = obj(obj(obj(fam).det).arms);
  const lat = (arm: string): Map<string, number> =>
    new Map(
      (Array.isArray(obj(arms[arm]).questions) ? (obj(arms[arm]).questions as unknown[]) : []).flatMap(
        (q) => {
          const v = num(obj(q).latency_ms_median);
          return v === undefined ? [] : [[str(obj(q).id), v] as [string, number]];
        },
      ),
    );
  const p = lat('P');
  const sql = lat('B1h');
  const r = [...p].flatMap(([id, v]) => (sql.get(id) ? [v / sql.get(id)!] : [])).sort((a, b) => a - b);
  if (r.length === 0) return undefined;
  const mid = r.length >> 1;
  return r.length % 2 ? r[mid]! : (r[mid - 1]! + r[mid]!) / 2;
}

function crashRows(raw: unknown): L6Crash[] {
  return Object.entries(obj(raw)).flatMap(([arm, c]) => {
    const o = obj(c);
    const orphans = num(o.orphans_total);
    if (orphans === undefined) return [];
    const totals = obj(o.totals);
    return [
      {
        arm,
        orphans,
        orphansByKind: Object.fromEntries(Object.entries(obj(o.orphans)).map(([k, v]) => [k, num(v) ?? 0])),
        acked: num(o.acknowledged_writes) ?? 0,
        lost: num(o.lost_acknowledged_total) ?? 0,
        total: Object.values(totals).reduce<number>((s, v) => s + (num(v) ?? 0), 0) || undefined,
      },
    ];
  });
}

function pilotRows(fam: unknown): L6Pilot[] {
  const arms = obj(obj(obj(fam).pilot).arms);
  return Object.entries(arms).flatMap(([arm, a]) => {
    const o = obj(a);
    const correct = num(o.strict_correct);
    const n = num(o.n);
    if (correct === undefined || n === undefined) return [];
    return [
      {
        arm,
        correct,
        n,
        costPerQuestion: num(o.cost_per_question_usd),
        cost: num(o.cost_usd),
        toolCalls: num(o.tool_calls_per_question),
      },
    ];
  });
}

export function parseL6(layer: unknown): L6Info | undefined {
  if (!isObj(layer) || !isObj(layer.families)) return undefined;
  const fams = layer.families;
  const post = obj(obj(layer.postfix).families);
  const out: L6Family[] = [];
  for (const id of FAMILY_ORDER) {
    const f = obj(fams[id]);
    if (Object.keys(f).length === 0) continue;
    const pa = id === 'A' ? obj(obj(post.A).arms) : {};
    out.push({
      id,
      title: FAMILY_TITLES[id] ?? id,
      det: detArms(f),
      dag: id === 'A' ? detArms(fams.A_dag) : [],
      conc: Object.entries(obj(f.conc)).flatMap(([arm, c]) => {
        const t = obj(obj(c).totals);
        return num(t.v1) === undefined
          ? []
          : [
              {
                arm,
                v1: num(t.v1) ?? 0,
                v2: num(t.v2) ?? 0,
                v3: num(t.v3) ?? 0,
                reads: num(t.reads) ?? 0,
                runsWithViolation: num(obj(c).runs_with_violation),
              },
            ];
      }),
      crash: crashRows(f.crash),
      pilot: pilotRows(f),
      medianSlowdown: id === 'D' ? medianSlowdown(f) : undefined,
      postfixA: Object.entries(pa).flatMap(([arm, a]) => {
        const o = obj(a);
        const lat = obj(o.latency_ms);
        const c = num(o.strict_correct);
        const n = num(o.n);
        return c === undefined || n === undefined
          ? []
          : [
              {
                arm,
                strict: `${c}/${n}`,
                p50: num(lat.p50),
                p99: num(lat.p99),
                max: num(lat.max),
                timeouts: num(o.timeouts),
              },
            ];
      }),
      postfixF: id === 'F' ? crashRows(post.F) : [],
    });
  }
  // pilot totals across families A, B and D per arm (the "P" arm there is the product over MCP: P-mcp)
  const byArm = new Map<string, L6PilotTotal>();
  for (const id of ['A', 'B', 'D']) {
    for (const p of pilotRows(fams[id])) {
      const name = p.arm === 'P' ? 'P-mcp' : p.arm;
      const cur = byArm.get(name) ?? { arm: name, correct: 0, n: 0, cost: 0 };
      cur.correct += p.correct;
      cur.n += p.n;
      cur.cost += p.cost ?? 0;
      byArm.set(name, cur);
    }
  }
  const order = ['B1a', 'B0g', 'B0r', 'P-mcp'];
  const pilotTotals = [...byArm.values()].sort((a, b) => order.indexOf(a.arm) - order.indexOf(b.arm));
  const budget = obj(obj(layer.pilot).budget);
  return {
    families: out,
    pilotTotals,
    llmCalls: num(layer.llm_calls_total) ?? 0,
    costUsd: num(layer.cost_usd_total) ?? 0,
    budgetCapUsd: num(budget.total_cap_usd),
    postfixRun: str(obj(layer.postfix).run) || undefined,
  };
}

/** Pre-registered expectations (docs/BASELINE.md "L6 pre-registration", written before any L6 run), one line per family. */
export const L6_EXPECTATION: Record<string, string> = {
  A: 'A tie. P-tuned, B1h and (after the fix) the product answer 24/24; the natural variable-length query (P-naive) times out on large blasts; a 32k reader (B0r) cannot count 5,000 facts (≤ 2/8).',
  B: 'A tie once the depth is exposed. P-tuned = B1h = 24/24; the pre-fix product answers only depths 2-3 (8/24); readers fall behind past depth 3.',
  D: 'A tie on correctness. P = B1h = 24/24; B0r ≤ 1/8. No speed claim; SQL is expected to be at least as fast.',
  E: 'The single-statement arms (P-1stmt, B1h-1stmt, B1h-txn, B0-locked): 0 violations in 10 runs. At least one level-wise or naive arm tears.',
  F: 'P expected to lose. B1h: 0 orphans and 0 lost writes; the service path P: > 0 records without a Step/WROTE link after a kill (documented gap).',
};
