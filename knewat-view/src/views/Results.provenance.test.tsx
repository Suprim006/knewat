import { screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import { createFixtureApi } from '../fixtures/client';
import { SAMPLE_RESULTS } from '../fixtures/results';
import { acme, renderApp } from '../test/render';

const withEnv = (env: Record<string, unknown> | undefined) => {
  const { environment: _drop, ...rest } = SAMPLE_RESULTS;
  return env ? { ...rest, environment: env } : rest;
};

describe('Results provenance banner', () => {
  it('shows the build and date read from the results file', async () => {
    renderApp('/results', createFixtureApi(acme, withEnv({ python: '3.12', git_commit: '7618d18' })));
    const b = await screen.findByTestId('provenance');
    expect(b).toHaveTextContent(
      'Measured on build 7618d18 (2026-10-17). Which numbers are current: docs/NUMBERS_STATUS.md',
    );
    expect(b).not.toHaveTextContent('dirty');
  });

  it('shows "build unknown" when the envelope has no commit', async () => {
    renderApp('/results', createFixtureApi(acme, withEnv({ python: '3.12' })));
    expect(await screen.findByTestId('provenance')).toHaveTextContent(
      'Measured on build unknown (2026-10-17).',
    );
  });

  it('shows "build unknown" when there is no environment block at all', async () => {
    renderApp('/results', createFixtureApi(acme, withEnv(undefined)));
    expect(await screen.findByTestId('provenance')).toHaveTextContent('Measured on build unknown');
  });

  it('appends (dirty tree) when the envelope records one', async () => {
    renderApp('/results', createFixtureApi(acme, withEnv({ git_commit: 'abc1234', git_dirty: true })));
    expect(await screen.findByTestId('provenance')).toHaveTextContent(
      'Measured on build abc1234 (dirty tree) (2026-10-17).',
    );
  });

  it('is not shown while there are no results', async () => {
    renderApp('/results');
    await screen.findByTestId('results-placeholder');
    expect(screen.queryByTestId('provenance')).toBeNull();
  });
});
