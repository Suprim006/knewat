/*
 * Staleness (P7-J) and forgetting (P7-K) as the viewer shows them. Pure functions over the Fact properties
 * the View API sends (docs/view-api.schema.json, GraphNode.props), so the Explorer canvas, the node panel
 * and the Time Machine agree. Every field is optional: a tenant without P7 data has none of them.
 */
import { OPEN } from '../api/types';
import type { GraphNode, Props } from '../api/types';

export const SUSPECT_GLYPH = '⚠';
export const PIN_GLYPH = '📌';
/** A fact with an open soft-duplicate link (DUPLICATES_MAYBE): the id of the older fact it may repeat. */
export const DUPLICATE_GLYPH = '⧉';
/** Opacity range of a Fact node: 0.35 (long forgotten) .. 1 (hot). */
const MIN_OPACITY = 0.35;

export const sigmoid = (x: number): number => 1 / (1 + Math.exp(-x));

/** opacity = 0.35 + 0.65·σ(activation − A0) */
export const activationOpacity = (activation: number, a0: number): number =>
  MIN_OPACITY + (1 - MIN_OPACITY) * sigmoid(activation - a0);

const num = (v: unknown): number | null => (typeof v === 'number' && Number.isFinite(v) ? v : null);
const when = (ms: number): string =>
  new Date(ms)
    .toISOString()
    .replace('T', ' ')
    .replace(/:\d\d\.\d+Z$/, 'Z');

/** Facts the staleness rule applies to: a superseded or forgotten fact is not worth re-checking. */
const rated = (p: Props): boolean => p.status !== 'superseded' && p.status !== 'forgotten';

/**
 * Contract rule: suspect at time `t` iff verify_state = 'suspect' (and its suspect_since has been reached)
 * OR the review date `verify_after` is <= t. `t` is "now" in the Explorer and the step's time in the
 * Time Machine, which is how the state is time-aware.
 */
export function isSuspectAt(p: Props, t: number): boolean {
  if (!rated(p)) return false;
  if (p.verify_state === 'suspect' && (num(p.suspect_since) ?? 0) <= t) return true;
  const after = num(p.verify_after);
  return after !== null && after < OPEN && after <= t;
}

/** The reason the properties alone can give; the verify queue knows the commit and paths. */
export function suspectReason(p: Props): string {
  if (p.verify_state === 'suspect') {
    const since = num(p.suspect_since);
    return since ? `changed code (suspect since ${when(since)})` : 'changed code';
  }
  const after = num(p.verify_after);
  return after !== null && after < OPEN ? `review date passed (${when(after)})` : 'needs verification';
}

export interface FactMemory {
  suspect: boolean;
  /** Why it is suspect ('' when it is not). */
  reason: string;
  pinned: boolean;
  dormant: boolean;
  /** The older fact this one may duplicate (`props.maybe_duplicate_of`), '' when none. */
  maybeDuplicateOf: string;
  /** null when the API sent no activation (forgetting off, no events, or a tenant without P7). */
  activation: number | null;
  protected: boolean;
  surprise: number;
}

export function factMemory(p: Props, t: number, reason?: string): FactMemory {
  const suspect = isSuspectAt(p, t);
  return {
    suspect,
    reason: suspect ? (reason ?? suspectReason(p)) : '',
    pinned: p.pinned === true,
    dormant: p.status === 'dormant',
    maybeDuplicateOf: typeof p.maybe_duplicate_of === 'string' ? p.maybe_duplicate_of : '',
    activation: num(p.activation),
    protected: p.protected === true,
    surprise: num(p.surprise) ?? 0,
  };
}

/** True when the node carries any P7 field, i.e. the tenant has staleness / forgetting data. */
export const hasMemoryData = (p: Props): boolean =>
  ['activation', 'verify_state', 'pinned', 'surprise'].some((k) => p[k] !== undefined);

/** Median activation of the Facts that report one (the fade centre when the API sends no A0); null if none. */
export function medianActivation(nodes: readonly GraphNode[]): number | null {
  const a = nodes
    .filter((n) => n.label === 'Fact')
    .map((n) => num(n.props.activation))
    .filter((v): v is number => v !== null)
    .sort((x, y) => x - y);
  if (a.length === 0) return null;
  const mid = a.length >> 1;
  return a.length % 2 ? a[mid]! : (a[mid - 1]! + a[mid]!) / 2;
}

export interface MemoryContext {
  now: number;
  /** Fade centre; null/undefined = do not fade. */
  a0?: number | null;
  /** Reasons from the verify queue by fact id. */
  reasons?: ReadonlyMap<string, string>;
}

export interface MemoryNodeData {
  /** Canvas label: glyphs + name. */
  display: string;
  suspect: boolean;
  pinned: boolean;
  dormant: boolean;
  duplicate: boolean;
  /** Hover text ('' for nodes with nothing to say). */
  tip: string;
  /** Set only when the fact has an activation and a fade centre is known. */
  opacity?: number;
}

/** Cytoscape data for one node: badges in the label, a tooltip, and the activation-driven opacity. */
export function memoryNodeData(node: GraphNode, name: string, ctx: MemoryContext): MemoryNodeData {
  if (node.label !== 'Fact')
    return { display: name, suspect: false, pinned: false, dormant: false, duplicate: false, tip: '' };
  const m = factMemory(node.props, ctx.now, ctx.reasons?.get(node.id));
  const dup = m.maybeDuplicateOf !== '';
  const glyphs = [
    m.suspect ? SUSPECT_GLYPH : '',
    m.pinned ? PIN_GLYPH : '',
    dup ? DUPLICATE_GLYPH : '',
  ].filter(Boolean);
  const tip = [
    m.suspect ? `${SUSPECT_GLYPH} suspect: ${m.reason}` : '',
    m.pinned ? `${PIN_GLYPH} pinned: never faded or swept` : '',
    dup
      ? `${DUPLICATE_GLYPH} possible duplicate of ${m.maybeDuplicateOf} (confirm_duplicate / reject_duplicate)`
      : '',
    m.dormant ? 'dormant: swept out of recall, still stored (restore_fact brings it back)' : '',
    m.activation !== null ? `activation ${m.activation.toFixed(2)}${m.protected ? ' (protected)' : ''}` : '',
    m.surprise > 0 ? `surprise ${m.surprise.toFixed(2)}` : '',
  ]
    .filter(Boolean)
    .join('\n');
  const out: MemoryNodeData = {
    display: glyphs.length > 0 ? `${glyphs.join(' ')} ${name}` : name,
    suspect: m.suspect,
    pinned: m.pinned,
    dormant: m.dormant,
    duplicate: dup,
    tip: tip ? `${name}\n${tip}` : '',
  };
  if (m.activation !== null && ctx.a0 !== null && ctx.a0 !== undefined)
    out.opacity = activationOpacity(m.activation, ctx.a0);
  return out;
}

const EVENT_NAMES: [key: string, singular: string][] = [
  ['create', 'creation'],
  ['reassert', 're-assertion'],
  ['decision', 'decision'],
  ['handoff', 'handoff'],
  ['use', 'use'],
  ['recall', 'recall'],
  ['verified', 'verification'],
];

/** "1 creation, 2 decisions, 3 uses": the activation events by kind, zero counts dropped. */
export function strengthCounts(counts: Record<string, number>): string {
  const parts = EVENT_NAMES.filter(([k]) => (counts[k] ?? 0) > 0).map(
    ([k, s]) => `${counts[k]} ${s}${counts[k] === 1 ? '' : 's'}`,
  );
  return parts.length > 0 ? parts.join(', ') : 'no events';
}

/** What the legend counts. */
export interface MemoryCounts {
  suspect: number;
  pinned: number;
  dormant: number;
  /** Facts with an open possible-duplicate link. */
  duplicate: number;
  /** Facts drawn with an activation-driven opacity. */
  faded: number;
}
export const EMPTY_MEMORY_COUNTS: MemoryCounts = {
  suspect: 0,
  pinned: 0,
  dormant: 0,
  duplicate: 0,
  faded: 0,
};
