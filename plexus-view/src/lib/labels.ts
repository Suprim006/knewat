import { OPEN } from '../api/types';
import type { Props } from '../api/types';

/** Colour per node label (legend + graph). Chosen to stay readable on both light and dark backgrounds. */
export const LABEL_COLORS: Record<string, string> = {
  Agent: '#e6194b',
  Scope: '#9a6324',
  Session: '#3cb44b',
  Episode: '#4363d8',
  Entity: '#911eb4',
  Fact: '#f58231',
  Source: '#a3a300',
  Procedure: '#469990',
  Run: '#00a3a3',
  Task: '#42d4f4',
  Handoff: '#f032e6',
  Artifact: '#c9a227',
  Decision: '#dc6bad',
  Step: '#7c8798',
  ToolCall: '#b0b6c0',
  Recall: '#2dd4a0',
  Change: '#e0672b',
  CodeAnchor: '#6b8e23',
};
export const FALLBACK_COLOR = '#999999';
export const labelColor = (label: string): string => LABEL_COLORS[label] ?? FALLBACK_COLOR;

/** Which Plexus module owns a label (graph model v1). Used to group the legend. */
export const LABEL_MODULES: Record<string, string> = {
  Agent: 'Shared',
  Scope: 'Engram',
  Session: 'Engram',
  Episode: 'Engram',
  Entity: 'Engram',
  Fact: 'Engram',
  Procedure: 'Engram',
  Run: 'Engram',
  Task: 'Relay',
  Handoff: 'Relay',
  Artifact: 'Relay',
  Decision: 'Relay',
  Source: 'Lineage',
  Step: 'Lineage',
  Recall: 'Lineage',
  ToolCall: 'Audit',
  Change: 'Staleness',
  CodeAnchor: 'Staleness',
};
export const MODULE_ORDER = ['Shared', 'Engram', 'Relay', 'Lineage', 'Staleness', 'Audit'];

/** One colour per module, for the Explorer's "colour by module" mode (Engram, Relay, Lineage, audit). */
export const MODULE_COLORS: Record<string, string> = {
  Shared: '#e6194b',
  Engram: '#4363d8',
  Relay: '#f58231',
  Lineage: '#3cb44b',
  Staleness: '#e0672b',
  Audit: '#9aa3b2',
};
export type ColorMode = 'label' | 'module';
export const moduleOf = (label: string): string => LABEL_MODULES[label] ?? 'Other';
export const moduleColor = (label: string): string => MODULE_COLORS[moduleOf(label)] ?? FALLBACK_COLOR;
export const nodeColor = (label: string, mode: ColorMode): string =>
  mode === 'module' ? moduleColor(label) : labelColor(label);

/**
 * Noise that starts hidden in the Explorer so the memory/coordination structure is readable:
 * audit and lineage bookkeeping nodes, and the edges every fact has (scope, author) or every step has.
 */
export const DEFAULT_HIDDEN_LABELS = ['ToolCall', 'Step', 'Recall', 'Session'];
export const DEFAULT_HIDDEN_EDGE_TYPES = ['IN_SCOPE', 'ASSERTED_BY', 'BY', 'WROTE', 'READ'];

const trunc = (s: string, n = 48): string => (s.length > n ? `${s.slice(0, n - 1)}…` : s);
const str = (v: unknown): string =>
  typeof v === 'string' ? v : v === undefined || v === null ? '' : String(v);
const basename = (uri: string): string => uri.split('/').filter(Boolean).pop() ?? uri;

/** Short human name for a node, shown on the canvas, in lists and in the side panel. */
export function displayName(label: string, p: Props): string {
  switch (label) {
    case 'Agent':
    case 'Scope':
    case 'Entity':
    case 'Procedure':
      return str(p.name) || label;
    case 'Fact':
      return trunc(`${str(p.predicate)}: ${str(p.value)}`);
    case 'Episode':
      return trunc(str(p.text));
    case 'Source':
    case 'Artifact':
      return basename(str(p.uri)) || label;
    case 'Task':
      return trunc(str(p.title));
    case 'Handoff':
      return trunc(str(p.note));
    case 'Decision':
      return trunc(str(p.text));
    case 'Step':
      return `step ${str(p.n)}`;
    case 'ToolCall':
      return str(p.tool) || 'ToolCall';
    case 'Recall':
      return trunc(str(p.query));
    case 'Change':
      return `change ${str(p.commit).slice(0, 7) || 'working tree'}`;
    case 'CodeAnchor':
      return str(p.symbol) ? `${basename(str(p.path))}#${str(p.symbol)}` : basename(str(p.path)) || label;
    case 'Run':
      return trunc(str(p.notes)) || 'run';
    case 'Session':
      return 'session';
    default:
      return label;
  }
}

const TIME_KEYS = new Set([
  'at',
  'created_at',
  'recorded_at',
  'valid_from',
  'valid_to',
  'started_at',
  'ended_at',
  'done_at',
  'lease_until',
  'suspect_since',
  'verified_at',
  'verify_after',
  'updated_at',
]);

/** Format a property for display: epoch-ms fields as ISO timestamps, the OPEN sentinel as "open". */
export function formatProp(key: string, value: unknown): string {
  if (Array.isArray(value)) return value.join(', ');
  if (typeof value === 'number' && TIME_KEYS.has(key)) {
    if (value >= OPEN) return 'open';
    if (value === 0) return '—';
    if (value > 1e11)
      return new Date(value)
        .toISOString()
        .replace('T', ' ')
        .replace(/\.\d+Z$/, 'Z');
  }
  if (typeof value === 'boolean') return value ? 'true' : 'false';
  return str(value);
}
