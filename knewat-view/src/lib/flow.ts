import type { FlowEvent, ViewApi } from '../api';

/** Fixed colours for the demo's three roles; any other agent id gets a stable hashed colour. */
const KNOWN_AGENTS: Record<string, string> = {
  planner: '#4363d8',
  researcher: '#3cb44b',
  builder: '#f58231',
};
const PALETTE = ['#e6194b', '#911eb4', '#42d4f4', '#f032e6', '#9a6324', '#469990', '#808000', '#dc6bad'];

export function agentColor(agentId: string): string {
  const known = KNOWN_AGENTS[agentId];
  if (known) return known;
  let h = 0;
  for (let i = 0; i < agentId.length; i++) h = (Math.imul(h, 31) + agentId.charCodeAt(i)) >>> 0;
  return PALETTE[h % PALETTE.length]!;
}

/** `HH:MM:SS.mmm` in UTC (stable for screenshots and tests). */
export function formatClock(ms: number): string {
  return new Date(ms).toISOString().slice(11, 23);
}

export const REPLAY_SPEEDS = [0.5, 1, 2, 5, 10] as const;

/**
 * Wait before revealing the next event in a replay: the real gap between the two calls divided by the
 * speed, but never so long that a quiet period stalls the demo (max 1.5 s) nor so short it flickers (min 40 ms).
 */
export function replayDelay(prevAt: number, nextAt: number, speed: number): number {
  const gap = Math.max(0, nextAt - prevAt);
  return Math.round(Math.min(1500, Math.max(40, gap)) / speed);
}

const PAGE = 1000;
const MAX_PAGES = 10;

/**
 * Backfill the timeline from `/flow` (oldest first, at most 1000 per page). Returns the newest `keep`
 * events and the resume point (`last_at`) to hand to the SSE stream.
 */
export async function loadFlowBackfill(
  api: ViewApi,
  tenant: string,
  keep = 500,
): Promise<{ events: FlowEvent[]; lastAt: number }> {
  let after = 0;
  let all: FlowEvent[] = [];
  for (let page = 0; page < MAX_PAGES; page++) {
    const res = await api.flow(tenant, after, PAGE);
    all = all.concat(res.events);
    after = res.last_at;
    if (res.events.length < PAGE) break;
    if (all.length > keep * 4) all = all.slice(-keep);
  }
  return { events: all.slice(-keep), lastAt: after };
}
