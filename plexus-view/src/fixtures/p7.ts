/*
 * Staleness and forgetting overlay for the Acme Notes fixture, in the shapes the View API sends
 * (docs/view-api.schema.json). `applyP7` returns a NEW dataset, so `buildAcme()` keeps its counts. The query
 * helpers back the fixture client's `verifyQueue`, `docsToUpdate`, `memoryStrength` and memory counts.
 */
import { OPEN } from '../api/types';
import type { DocRow, GraphEdge, GraphNode, MemoryStrength, Props, VerifyRow } from '../api/types';
import type { AcmeDataset } from './acme';
import { T0, stepTime } from './acme';
import { isSuspectAt, medianActivation, sigmoid } from '../lib/memory';

const REPO = 'acme-notes';
const ROOT = 'C:/acme-notes';
const HOUR = 3_600_000;

/** Floor of the rank multiplier (PLEXUS_ACT_FLOOR); the multiplier is halfway to 1 at A0. */
const FLOOR = 0.5;
const DECAY = 0.5;

/** Activation by fact key: hot facts, long-forgotten ones, and everything else from a deterministic spread. */
const ACTIVATION: Record<string, number> = {
  jwt: 1.4,
  pg: 1.1,
  v2: 0.9,
  lang: 0.8,
  apikey: 0.7,
  goal: 0.6,
  v1: -3.0,
  sqlite: -4.2,
  deadline: -3.8,
  scaffold: -3.5,
  size: -3.1,
  methods: -2.9,
  db_cands: -2.6,
};
const SURPRISE: Record<string, number> = { apikey: 0.9, slowapi: 0.7, v2: 0.5 };
const PINNED = new Set(['lang', 'goal']);
const DORMANT = new Set(['sqlite', 'deadline', 'scaffold']);
/** Suspect because code changed: fact key -> change key. */
const CHANGED: Record<string, 'chg1' | 'chg2'> = { jwt: 'chg1', ttl: 'chg1', mw: 'chg1', pg_tp: 'chg2' };
/** Suspect because a review date passed (not about code): fact key -> verify_after. */
const REVIEW: Record<string, number> = { ci: T0 + HOUR, rate_limit: T0 + 2 * HOUR };

const spread = (i: number): number => -2.2 + (((i * 7919) % 13) / 12) * 2.6;

const anchorLabel = (n: GraphNode): string => {
  const sym = String(n.props.symbol ?? '');
  return sym ? `${n.props.path}#${sym}` : String(n.props.path);
};

export function applyP7(base: AcmeDataset): AcmeDataset {
  const ids = { ...base.ids };
  const keyOf = new Map(Object.entries(base.ids).map(([k, v]) => [v, k]));
  const idOf = (k: string): string => {
    const id = ids[k];
    if (!id) throw new Error(`fixture: unknown node key ${k}`);
    return id;
  };

  /* new nodes: two code changes, three anchors */
  const mk = (label: 'Change' | 'CodeAnchor', key: string, id: string, props: Props): GraphNode => {
    ids[key] = id;
    return { id, label, props };
  };
  const at1 = stepTime(24);
  const at2 = stepTime(26);
  const extra: GraphNode[] = [
    mk('CodeAnchor', 'anc.jwt', 'anc:1a2b3c4d5e6f7a8b', {
      repo: REPO,
      path: `${ROOT}/app/auth/jwt.py`,
      symbol: '',
      hash: '3f9c1d7a',
      kind: 'file',
      updated_at: at1,
      created_at: stepTime(9),
    }),
    mk('CodeAnchor', 'anc.mw', 'anc:2b3c4d5e6f7a8b9c', {
      repo: REPO,
      path: `${ROOT}/app/auth/jwt.py`,
      symbol: 'verify_token',
      hash: '77ab02ce',
      kind: 'function',
      updated_at: at1,
      created_at: stepTime(15),
    }),
    mk('CodeAnchor', 'anc.pool', 'anc:3c4d5e6f7a8b9c0d', {
      repo: REPO,
      path: `${ROOT}/app/db/pool.py`,
      symbol: '',
      hash: 'c04e5519',
      kind: 'file',
      updated_at: at2,
      created_at: stepTime(11),
    }),
    mk('Change', 'chg1', 'chg:aa11bb22cc33dd44', {
      commit: 'a1b2c3d',
      at: at1,
      paths: JSON.stringify([`${ROOT}/app/auth/jwt.py`]),
      agent_id: 'builder',
      created_at: at1,
    }),
    mk('Change', 'chg2', 'chg:ee55ff6600117722', {
      commit: 'e4f5a6b',
      at: at2,
      paths: JSON.stringify([`${ROOT}/app/db/pool.py`]),
      agent_id: 'builder',
      created_at: at2,
    }),
  ];

  const edge = (type: string, s: string, t: string): GraphEdge => ({
    type,
    source: idOf(s),
    target: idOf(t),
  });
  const extraEdges: GraphEdge[] = [
    edge('ANCHORED_TO', 'f.jwt', 'anc.jwt'),
    edge('ANCHORED_TO', 'f.mw', 'anc.mw'),
    edge('ANCHORED_TO', 'f.pg_tp', 'anc.pool'),
    edge('DESCRIBES', 's.rfc', 'anc.jwt'),
    edge('TOUCHED', 'chg1', 'anc.jwt'),
    edge('TOUCHED', 'chg1', 'anc.mw'),
    edge('TOUCHED', 'chg2', 'anc.pool'),
    ...Object.entries(CHANGED).map(([f, c]) => edge('SUSPECTED', c, `f.${f}`)),
  ];

  const edges = [...base.edges, ...extraEdges];

  let i = 0;
  const nodes = base.nodes.map((n): GraphNode => {
    if (n.label !== 'Fact') return n;
    const key = (keyOf.get(n.id) ?? '').replace(/^f\./, '');
    const changed = CHANGED[key];
    const reviewAt = REVIEW[key];
    const protectedFact = protectReasons(edges, n.id, PINNED.has(key)).length > 0;
    const props: Props = {
      ...n.props,
      verify_state: changed ? 'suspect' : 'verified',
      suspect_since: changed ? (changed === 'chg1' ? at1 : at2) : 0,
      verify_after: reviewAt ?? OPEN,
      surprise: SURPRISE[key] ?? 0,
      pinned: PINNED.has(key),
      activation: ACTIVATION[key] ?? Math.round(spread(i) * 100) / 100,
      protected: protectedFact,
    };
    if (DORMANT.has(key)) props.status = 'dormant';
    i++;
    return { ...n, props };
  });

  return { ...base, nodes: [...nodes, ...extra], edges, ids };
}

/** Why a fact is protected from fading (contract: pinned, a live decision, a handoff, SUPERSEDES / CONTRADICTS). */
function protectReasons(edges: readonly GraphEdge[], id: string, pinned: boolean): string[] {
  const first = (pick: (e: GraphEdge) => boolean, label: (e: GraphEdge) => string): string[] =>
    edges.filter(pick).map(label).slice(0, 1);
  return [
    ...(pinned ? ['pinned'] : []),
    ...first(
      (e) => e.type === 'BASED_ON' && e.target === id,
      (e) => `decision:${e.source}`,
    ),
    ...first(
      (e) => e.type === 'CARRIES' && e.target === id,
      (e) => `handoff:${e.source}`,
    ),
    ...first(
      (e) => e.type === 'SUPERSEDES' && e.source === id,
      (e) => `supersedes:${e.target}`,
    ),
    ...first(
      (e) => e.type === 'CONTRADICTS' && (e.source === id || e.target === id),
      (e) => `contradicts:${e.source === id ? e.target : e.source}`,
    ),
  ];
}

/* ------------------------------------------------------------------ queries over a dataset */

const ofLabel = (d: AcmeDataset, label: string): GraphNode[] => d.nodes.filter((n) => n.label === label);
const paths = (c: GraphNode): string[] => {
  try {
    const v: unknown = JSON.parse(String(c.props.paths));
    return Array.isArray(v) ? v.map(String) : [];
  } catch {
    return [];
  }
};
const basename = (s: string): string => s.split('/').filter(Boolean).pop() ?? s;

/** The inventory's memory-health counts (what view/inventory_memory.cypher counts). */
export function memoryCounts(d: AcmeDataset, now: number) {
  const facts = ofLabel(d, 'Fact');
  return {
    suspect_facts: facts.filter((f) => f.props.status === 'active' && isSuspectAt(f.props, now)).length,
    dormant_facts: facts.filter((f) => f.props.status === 'dormant').length,
    pinned_facts: facts.filter((f) => f.props.pinned === true).length,
    changes: ofLabel(d, 'Change').length,
    code_anchors: ofLabel(d, 'CodeAnchor').length,
  };
}

/** `Staleness.facts_to_verify` + activation: decisions at risk DESC, activation DESC, suspect_since ASC. */
export function verifyQueue(d: AcmeDataset, now: number, limit = 50): VerifyRow[] {
  const byId = new Map(d.nodes.map((n) => [n.id, n]));
  const entityOf = (id: string): string => {
    const e = d.edges.find((x) => x.type === 'ABOUT' && x.source === id);
    return String(byId.get(e?.target ?? '')?.props.name ?? '');
  };
  const scopeOf = (id: string): string => {
    const e = d.edges.find((x) => x.type === 'IN_SCOPE' && x.source === id);
    return e?.target ?? '';
  };
  const rows = ofLabel(d, 'Fact')
    .filter((f) => f.props.status === 'active' && isSuspectAt(f.props, now))
    .map((f): VerifyRow => {
      const sus = d.edges.find((e) => e.type === 'SUSPECTED' && e.target === f.id);
      const chg = sus ? byId.get(sus.source) : undefined;
      const anchors = [
        ...d.edges
          .filter((e) => e.type === 'ANCHORED_TO' && e.source === f.id)
          .map((e) => anchorLabel(byId.get(e.target)!)),
        ...d.edges
          .filter(
            (e) => e.type === 'DERIVED_FROM' && e.source === f.id && byId.get(e.target)?.label === 'Source',
          )
          .map((e) => String(byId.get(e.target)!.props.uri)),
      ];
      const changed = f.props.verify_state === 'suspect' && chg;
      return {
        fact_id: f.id,
        entity: entityOf(f.id),
        predicate: String(f.props.predicate),
        value: String(f.props.value),
        scope_id: scopeOf(f.id),
        verify_state: String(f.props.verify_state),
        suspect_since: Number(f.props.suspect_since),
        verify_after: Number(f.props.verify_after),
        reason: changed ? `changed in ${chg.props.commit} (${paths(chg)[0] ?? ''})` : 'review date passed',
        decisions_count: d.edges.filter((e) => e.type === 'BASED_ON' && e.target === f.id).length,
        anchors,
        change: changed
          ? {
              change_id: chg.id,
              commit: String(chg.props.commit),
              at: Number(chg.props.at),
              paths: paths(chg),
            }
          : null,
        activation: typeof f.props.activation === 'number' ? f.props.activation : null,
        protected: typeof f.props.protected === 'boolean' ? f.props.protected : null,
      };
    });
  rows.sort(
    (a, b) =>
      b.decisions_count - a.decisions_count ||
      (b.activation ?? -Infinity) - (a.activation ?? -Infinity) ||
      a.suspect_since - b.suspect_since ||
      a.fact_id.localeCompare(b.fact_id),
  );
  return rows.slice(0, limit);
}

/** `Staleness.docs_to_update`: docs that DESCRIBE code a Change touched after the doc was last edited. */
export function docsToUpdate(d: AcmeDataset, since = 0, limit = 50): DocRow[] {
  const byId = new Map(d.nodes.map((n) => [n.id, n]));
  const docs: DocRow[] = [];
  for (const src of ofLabel(d, 'Source')) {
    const edited = Number(src.props.created_at);
    const changes: DocRow['changes'] = [];
    for (const desc of d.edges.filter((e) => e.type === 'DESCRIBES' && e.source === src.id)) {
      const anchor = byId.get(desc.target);
      if (!anchor) continue;
      for (const t of d.edges.filter((e) => e.type === 'TOUCHED' && e.target === anchor.id)) {
        const chg = byId.get(t.source);
        if (!chg || chg.label !== 'Change') continue;
        const at = Number(chg.props.at);
        if (at <= edited || at < since) continue;
        changes.push({
          change_id: chg.id,
          commit: String(chg.props.commit),
          at,
          paths: paths(chg),
          anchor: anchorLabel(anchor),
        });
      }
    }
    if (changes.length === 0) continue;
    changes.sort((a, b) => b.at - a.at);
    docs.push({
      source_id: src.id,
      uri: String(src.props.uri),
      title: basename(String(src.props.uri)),
      latest: changes[0]!.at,
      changes,
    });
  }
  docs.sort((a, b) => b.latest - a.latest);
  return docs.slice(0, limit);
}

/** `Activation.strength` for a fact in the dataset; undefined for an unknown id. */
export function memoryStrength(d: AcmeDataset, factId: string): MemoryStrength | undefined {
  const f = d.nodes.find((n) => n.id === factId && n.label === 'Fact');
  if (!f) return undefined;
  const count = (type: string, side: 'source' | 'target'): number =>
    d.edges.filter((e) => e.type === type && e[side] === f.id).length;
  const counts = {
    create: 1,
    reassert: 0,
    decision: count('BASED_ON', 'target'),
    handoff: count('CARRIES', 'target'),
    use: count('READ', 'target'),
    recall: count('RETURNED', 'target'),
    verified: count('VERIFIED_BY', 'source'),
  };
  const activation = typeof f.props.activation === 'number' ? f.props.activation : null;
  const a0 = medianActivation(d.nodes) ?? 0;
  const multiplier = FLOOR + (1 - FLOOR) * sigmoid((activation ?? -Infinity) - a0);
  const reasons = protectReasons(d.edges, f.id, f.props.pinned === true);
  const events = Object.values(counts).reduce((s, v) => s + v, 0);
  return {
    fact_id: f.id,
    status: String(f.props.status),
    activation,
    a0,
    multiplier,
    floor: FLOOR,
    decay: DECAY,
    protected: reasons.length > 0,
    protect_reasons: reasons,
    pinned: f.props.pinned === true,
    surprise: Number(f.props.surprise ?? 0),
    created_at: Number(f.props.created_at),
    verify_state: String(f.props.verify_state ?? 'verified'),
    suspect_since: Number(f.props.suspect_since ?? 0),
    counts,
    events_considered: events,
    last_use: null,
    last_recall: null,
    explanation:
      activation === null
        ? 'no usable events: ranks last'
        : `activation ${activation.toFixed(2)} vs neutral ${a0.toFixed(2)}: rank multiplier ${multiplier.toFixed(2)}` +
          (reasons.length > 0 ? `; protected: ${reasons.join(', ')}` : '; not protected'),
    forgetting: true,
  };
}
