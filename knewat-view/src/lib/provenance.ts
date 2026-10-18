/**
 * Where the numbers on the Results page were measured: read from the results file's own envelope
 * (`GET /api/results`, shape in knewat/src/knewat/crucible/results.py). Nothing is hard-coded, because the
 * file is regenerated on newer builds.
 *
 *  - build: `environment.git_commit` (short commit id). Empty or missing -> 'unknown'.
 *  - date:  `run.finished_at`, else `run.started_at` (ISO 8601; the date part is shown).
 *  - dirty: `environment.git_dirty` or `environment.dirty` is true, or the commit string ends in `-dirty`
 *           (the harness does not record the flag today; the L5/L6 runs tag their ids that way).
 */
type Obj = Record<string, unknown>;
const isObj = (v: unknown): v is Obj => typeof v === 'object' && v !== null && !Array.isArray(v);
const text = (v: unknown): string => (typeof v === 'string' ? v.trim() : '');

export interface Provenance {
  /** Short commit id, or 'unknown'. */
  build: string;
  /** YYYY-MM-DD (or the raw string when it is not ISO), '' when the file has no date. */
  date: string;
  dirty: boolean;
}

export function parseProvenance(raw: unknown): Provenance {
  const root = isObj(raw) ? raw : {};
  const env = isObj(root.environment) ? root.environment : {};
  const run = isObj(root.run) ? root.run : {};
  let commit = text(env.git_commit);
  let dirty = env.git_dirty === true || env.dirty === true;
  if (commit.endsWith('-dirty')) {
    commit = commit.slice(0, -'-dirty'.length);
    dirty = true;
  }
  const when = text(run.finished_at) || text(run.started_at);
  const iso = /^\d{4}-\d{2}-\d{2}/.exec(when);
  return { build: commit || 'unknown', date: iso ? iso[0] : when, dirty };
}
