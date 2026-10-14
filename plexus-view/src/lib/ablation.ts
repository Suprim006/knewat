/**
 * Ablation toggle (presentation only): hide the relationship types the Plexus features lean on and say
 * which tools stop working without them. The real ablation (edges actually removed, features measured)
 * is a Crucible result; this view only simulates the *picture*, never touches data.
 */
export interface AblatedEdge {
  type: string;
  /** What the edge is for, in one line. */
  meaning: string;
  /** The tools / features that break without it, and how. */
  breaks: { feature: string; effect: string }[];
}

export const ABLATED_EDGES: AblatedEdge[] = [
  {
    type: 'DEPENDS_ON',
    meaning: 'Task → Task it waits for',
    breaks: [
      {
        feature: 'claim_next_task / ready_tasks',
        effect: 'cannot tell which tasks are ready: dependent tasks get claimed before their inputs exist',
      },
      { feature: 'blocked_by_failure', effect: 'cannot walk from a failed task to everything it blocks' },
    ],
  },
  {
    type: 'BASED_ON',
    meaning: 'Decision → the Facts it rests on',
    breaks: [
      { feature: 'why(decision)', effect: 'the path from a decision to its evidence disappears' },
      { feature: 'record_decision evidence', effect: 'decisions become free text with no checkable basis' },
    ],
  },
  {
    type: 'DERIVED_FROM',
    meaning: 'Fact → the Source / Episode / Fact it came from',
    breaks: [
      {
        feature: 'forget_source / quarantine_source',
        effect: 'cannot find the facts to forget or the blast radius of a bad source',
      },
      { feature: 'why / why_recalled', effect: 'facts lose their sources; trust cannot be traced' },
    ],
  },
  {
    type: 'READ',
    meaning: 'Step → the Facts an agent read',
    breaks: [
      { feature: 'knew_at / who_knew', effect: '“what did agent X know at step N” has no answer' },
      { feature: 'Time Machine', effect: 'the per-agent “knew” column is empty' },
    ],
  },
];

export const ABLATED_EDGE_TYPES: readonly string[] = ABLATED_EDGES.map((e) => e.type);

/** Where the measured ablation results live. */
export const ABLATION_RESULTS_PATH = '/results#ablation';

/** Hidden edge types given the user's choices and whether the ablation switch is on. */
export function effectiveHiddenEdges(manual: ReadonlySet<string>, ablation: boolean): Set<string> {
  const out = new Set(manual);
  if (ablation) for (const t of ABLATED_EDGE_TYPES) out.add(t);
  return out;
}
