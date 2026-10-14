import { screen, within } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import { createFixtureApi } from '../fixtures/client';
import { SAMPLE_RESULTS } from '../fixtures/results';
import { parseResults, peakPoints } from '../lib/results';
import { acme, renderApp } from '../test/render';

describe('Results page', () => {
  it('shows a placeholder until the Crucible has produced results', async () => {
    renderApp('/results');
    const ph = await screen.findByTestId('results-placeholder');
    expect(ph).toHaveTextContent('No Crucible results yet');
    expect(ph).toHaveTextContent('crucible all');
  });

  it('shows an error for failures other than “no results”', async () => {
    const api = {
      ...createFixtureApi(acme),
      results: () => Promise.reject(new Error('boom')),
    };
    renderApp('/results', api);
    expect(await screen.findByRole('alert')).toHaveTextContent('boom');
  });

  describe('with results', () => {
    const render = () => renderApp('/results', createFixtureApi(acme, SAMPLE_RESULTS));

    it('renders the L1 table per arm with pass/fail cells', async () => {
      render();
      const l1 = await screen.findByTestId('l1');
      expect(within(l1).getByTestId('l1-C1-P')).toHaveTextContent('pass (10/10)');
      expect(within(l1).getByTestId('l1-C6-B1')).toHaveTextContent('FAIL 7/10 (wrong_version=12)');
      expect(within(l1).getByTestId('l1-C6-B0')).toHaveTextContent('n/a (unsupported)');
      expect(within(l1).getByTestId('l1-C6-B1')).toHaveClass('cell-fail');
    });

    it('draws a bar for L2 accuracy per arm', async () => {
      render();
      const l2 = await screen.findByTestId('l2');
      const bar = within(l2).getByTestId('bar-l2-P');
      expect(bar).toHaveTextContent('90%');
      expect(bar.querySelector<HTMLElement>('.bar-fill-h')!.style.width).toBe('90%');
      expect(within(l2).getByTestId('bar-l2-B0')).toHaveTextContent('45%');
    });

    it('lists L4 latency percentiles and charts the peak load', async () => {
      render();
      const claim = await screen.findByTestId('l4-claim_sweep');
      expect(within(claim).getByText('100 workers')).toBeInTheDocument();
      expect(within(claim).getByRole('row', { name: /^P/ })).toHaveTextContent('18 / 39 / 60');
      expect(within(claim).getByTestId('bar-claim_sweep-P-p99')).toHaveTextContent('60 ms');
      expect(within(claim).getAllByText(/srv /).length).toBeGreaterThan(0);
      expect(screen.getByTestId('l4-recall_sweep')).toHaveTextContent('8 / 15 / 24');
    });

    it('shows the ablation results with the capability that breaks', async () => {
      render();
      const abl = await screen.findByTestId('ablation');
      expect(abl).toHaveAttribute('id', 'ablation');
      const broken = within(abl).getByRole('row', { name: /why\(decision\)/ });
      expect(broken).toHaveClass('row-broken');
      expect(broken).toHaveTextContent('BASED_ON');
      expect(within(abl).getByRole('row', { name: /as_of/ })).not.toHaveClass('row-broken');
      expect(abl).toHaveTextContent('started_before_deps=31');
    });

    it('prints the headline and honesty notes, and flags a quick run', async () => {
      render();
      expect(await screen.findByText('Plexus: 0 violations across C1-C8.')).toBeInTheDocument();
      expect(screen.getByTestId('run-meta')).toHaveTextContent('quick run');
      expect(screen.getByText(/SAMPLE data for UI tests/)).toBeInTheDocument();
    });
  });
});

describe('parseResults', () => {
  it('accepts L2 in several shapes and ratios or percentages', () => {
    const a = parseResults({ layers: { L2: { arms: { B0: { accuracy: 0.5 }, P: { overall: 92 } } } } });
    expect(a.l2).toEqual([
      { arm: 'B0', accuracy: 50, n: undefined },
      { arm: 'P', accuracy: 92, n: undefined },
    ]);
    const b = parseResults({ layers: { L2: [{ arm: 'P', correct: 36, total: 40 }] } });
    expect(b.l2).toEqual([{ arm: 'P', accuracy: 90, n: 40 }]);
    const c = parseResults({ layers: { L2: { P: { summary: { accuracy: 0.8 } } } } });
    expect(c.l2?.[0]?.accuracy).toBeCloseTo(80);
  });

  it('survives junk without throwing', () => {
    for (const junk of [
      null,
      5,
      'x',
      [],
      { layers: 3 },
      { layers: { L1: 'no', L4: { claim_sweep: [1, 'a'] } } },
    ])
      expect(() => parseResults(junk)).not.toThrow();
    expect(parseResults({ other: 1 }).unknown).toEqual(['other']);
  });

  it('picks the highest worker count per arm for the chart', () => {
    const l4 = parseResults(SAMPLE_RESULTS).l4.find((s) => s.key === 'claim_sweep')!;
    expect(peakPoints(l4).map((p) => [p.arm, p.x])).toEqual([
      ['B1', 100],
      ['P', 100],
    ]);
  });
});
