import type { StepAgent, StepFact, StepResponse, StepWrote } from '../api/types';

export interface KnowledgeDiff {
  /** Facts the agent knows now that it did not at the earlier step. */
  added: StepFact[];
  /** Facts it knew at the earlier step but no longer does (superseded, expired). */
  removed: StepFact[];
  /** Same entity + predicate, different fact: the value moved (e.g. api_version v1 -> v2). */
  changed: { from: StepFact; to: StepFact }[];
  /** Things written since the earlier step. */
  newWrites: StepWrote[];
}

const slot = (f: StepFact): string => `${f.entity ?? ''}\u0000${f.predicate ?? ''}`;

/** What changed in one agent's knowledge between two steps. `before` is undefined when it had no step yet. */
export function diffAgent(before: StepAgent | undefined, after: StepAgent | undefined): KnowledgeDiff {
  const prevRead = before?.read ?? [];
  const nowRead = after?.read ?? [];
  const prevIds = new Set(prevRead.map((f) => f.id));
  const nowIds = new Set(nowRead.map((f) => f.id));
  let added = nowRead.filter((f) => !prevIds.has(f.id));
  let removed = prevRead.filter((f) => !nowIds.has(f.id));
  const changed: KnowledgeDiff['changed'] = [];
  for (const to of [...added]) {
    const from = removed.find((r) => slot(r) === slot(to));
    if (!from) continue;
    changed.push({ from, to });
    added = added.filter((a) => a !== to);
    removed = removed.filter((r) => r !== from);
  }
  const prevWrote = new Set((before?.wrote ?? []).map((w) => w.id));
  return {
    added,
    removed,
    changed,
    newWrites: (after?.wrote ?? []).filter((w) => !prevWrote.has(w.id)),
  };
}

export const isEmptyDiff = (d: KnowledgeDiff): boolean =>
  d.added.length + d.removed.length + d.changed.length + d.newWrites.length === 0;

/** Agent ids present in either response, sorted. */
export function agentIdsOf(a: StepResponse | undefined, b: StepResponse | undefined): string[] {
  return [...new Set([...(a?.agents ?? []), ...(b?.agents ?? [])].map((x) => x.agent_id))].sort();
}
