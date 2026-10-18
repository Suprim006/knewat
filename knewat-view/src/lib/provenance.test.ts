import { describe, expect, it } from 'vitest';
import { parseProvenance } from './provenance';

describe('parseProvenance', () => {
  it('reads the commit and the run date from the envelope', () => {
    expect(
      parseProvenance({
        run: { started_at: '2026-10-18T09:00:00Z', finished_at: '2026-10-18T09:30:00Z' },
        environment: { git_commit: '7618d18' },
      }),
    ).toEqual({ build: '7618d18', date: '2026-10-18', dirty: false });
  });
  it('falls back to started_at and flags a dirty tree', () => {
    expect(
      parseProvenance({
        run: { started_at: '2026-10-14T20:47:29Z' },
        environment: { git_commit: 'abc1234', git_dirty: true },
      }),
    ).toEqual({ build: 'abc1234', date: '2026-10-14', dirty: true });
    expect(parseProvenance({ environment: { git_commit: 'abc1234-dirty' } })).toMatchObject({
      build: 'abc1234',
      dirty: true,
    });
  });
  it('says unknown for a missing, empty or oddly shaped field', () => {
    expect(parseProvenance({ environment: {}, run: {} })).toEqual({
      build: 'unknown',
      date: '',
      dirty: false,
    });
    expect(parseProvenance({ environment: { git_commit: '' } }).build).toBe('unknown');
    expect(parseProvenance({ environment: { git_commit: 5 } }).build).toBe('unknown');
    expect(parseProvenance(null)).toEqual({ build: 'unknown', date: '', dirty: false });
  });
});
