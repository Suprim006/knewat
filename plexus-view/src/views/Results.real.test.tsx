import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';
import { screen, within } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import { createFixtureApi } from '../fixtures/client';
import { medianComparison, parseResults } from '../lib/results';
import { acme, renderApp } from '../test/render';

/**
 * Pins the Results page to the REAL combined file (`plexus/src/plexus/crucible/results/latest-all.json`:
 * L1 + L4 + ablation from the first compose run, merged with the full L2 run via
 * `python -m plexus.crucible.l2.run merge`). The copy next to this file is a snapshot of it; a Python test
 * (tests/crucible/test_results_file.py) checks the committed original has the keys read here.
 */
const REAL = JSON.parse(
  readFileSync(resolve(process.cwd(), 'src/fixtures/results.real.json'), 'utf-8'),
) as Record<string, unknown>;

describe('parseResults on the real combined file', () => {
  const r = parseResults(REAL);

  it('finds every layer and nothing it cannot draw', () => {
    expect(r.run?.layers).toEqual(['L1', 'L4', 'ablation', 'L2']);
    expect(r.unknown).toEqual([]);
    expect(r.arms.map((a) => a.id)).toEqual(expect.arrayContaining(['B0', 'B1', 'B2', 'P']));
    expect(r.l1?.rows.map((x) => x.id)).toEqual(['C1', 'C2', 'C3', 'C4', 'C5', 'C6', 'C7', 'C8']);
    expect(r.l1?.arms).toEqual(['B0', 'B1', 'B2', 'P']);
    expect(r.l4.map((s) => s.key)).toEqual(['claim_sweep', 'recall_sweep', 'tenant_sweep']);
    expect(r.ablation?.capabilities).toHaveLength(12);
    expect(r.ablation?.capabilities.filter((c) => c.breaks)).toHaveLength(7);
  });

  it('reads L2 accuracy, the whole-reply variant, tokens, cost and latency per arm', () => {
    const by = Object.fromEntries((r.l2 ?? []).map((x) => [x.arm, x]));
    expect(Object.keys(by).sort()).toEqual(['B0', 'B1', 'B2', 'P']);
    expect(by.P).toMatchObject({ accuracy: 100, correct: 43, n: 43, costUsd: 0, tokensPerQuestion: 0 });
    expect(by.B2).toMatchObject({ correct: 40, n: 43 });
    expect(by.B2!.accuracy).toBeCloseTo(93, 0);
    expect(by.B0).toMatchObject({ wholeReplyCorrect: 36, tokensPerQuestion: 15930, costUsd: 2.6683 });
    expect(by.B0!.wholeReplyPct).toBeCloseTo(83.7, 1);
    expect(by.B0!.latencyMedianMs).toBeCloseTo(5754.6, 1);
    expect(by.P!.latencyMedianMs).toBeCloseTo(2.5, 1);
    expect(by.B0!.replyFormat).toEqual({ jsonOnly: 36, proseThenJson: 7, unparseable: 0, callFailed: 0 });
    expect(r.l2Info).toMatchObject({ mode: 'full', model: 'sonnet', asked: 43, total: 43 });
    expect(r.l2Info!.families).toHaveLength(10);
  });

  it('takes the x axis of the tenant sweep from tenants, not from its fixed worker count', () => {
    const t = r.l4.find((s) => s.key === 'tenant_sweep')!;
    expect(t.xLabel).toBe('tenants');
    expect(new Set(t.points.map((p) => p.x)).size).toBeGreaterThan(1);
    expect(r.l4.find((s) => s.key === 'claim_sweep')!.xLabel).toBe('workers');
  });

  it('keeps the honesty notes and the L4/L2 notes verbatim', () => {
    expect(r.honesty).toEqual(REAL.honesty);
    expect(r.l4Notes.length).toBeGreaterThan(0);
    expect(r.l2Info!.notes.length).toBeGreaterThan(0);
  });

  it('computes who is fastest on the median claim: SQLite (B1) beats Plexus', () => {
    const claim = r.l4.find((s) => s.key === 'claim_sweep')!;
    const cmp = medianComparison(claim, 'claim');
    const top = cmp[cmp.length - 1]!;
    expect(top.fastest.arm).toBe('B1');
    expect(top.plexus!.arm).toBe('P');
    expect(top.ratio!).toBeGreaterThan(1);
    // ... while the tail tells the other half: B1's p99 is worse than its p50 by orders of magnitude
    expect(top.fastest.p99).toBeGreaterThan(top.fastest.p50 * 100);
  });
});

describe('Results page on the real combined file', () => {
  const render = () => renderApp('/results', createFixtureApi(acme, REAL));

  it('shows the L2 table with accuracy, whole-reply accuracy, tokens, cost and latency', async () => {
    render();
    const l2 = await screen.findByTestId('l2');
    expect(within(l2).getByTestId('l2-acc-P')).toHaveTextContent('100% (43/43)');
    expect(within(l2).getByTestId('l2-acc-B2')).toHaveTextContent('93.0% (40/43)');
    expect(within(l2).getByTestId('l2-whole-B0')).toHaveTextContent('83.7% (36/43)');
    expect(within(l2).getByTestId('l2-tokens-B0')).toHaveTextContent('15,930');
    expect(within(l2).getByTestId('l2-cost-B0')).toHaveTextContent('$2.67');
    expect(within(l2).getByTestId('l2-cost-P')).toHaveTextContent('$0 (no LLM)');
    expect(within(l2).getByTestId('l2-latency-B0')).toHaveTextContent('5.75 s');
    expect(within(l2).getByTestId('l2-latency-P')).toHaveTextContent('2.50 ms');
    expect(within(l2).getByTestId('l2-reply-format')).toHaveTextContent('36 JSON-only, 7 prose then JSON');
  });

  it('prints the L2 and honesty notes verbatim, including the methodology change and the tie', async () => {
    render();
    const notes = await screen.findByTestId('l2-notes');
    expect(notes).toHaveTextContent('a methodology fix made with the results in view');
    expect(notes).toHaveTextContent('Both variants are reported.');
    // honesty list: the full sentence, unchanged
    const honesty = (REAL.honesty as string[]).find((h) => h.startsWith('Result in plain words'))!;
    expect(screen.getByText(honesty)).toBeInTheDocument();
    expect(screen.getByText(/Plexus TIES them on accuracy/)).toBeInTheDocument();
  });

  it('shows L4 with SQLite faster on the median claim, not hidden', async () => {
    render();
    const med = await screen.findByTestId('median-claim_sweep');
    const top = within(med).getByTestId('median-claim_sweep-200');
    expect(top).toHaveTextContent('B1');
    expect(top).toHaveTextContent('Plexus P');
    expect(top).toHaveTextContent('× the fastest median');
    expect(screen.getByTestId('l4-notes')).toHaveTextContent('no fairness queue');
  });

  it('shows the L1 matrix and the ablation from the real file', async () => {
    render();
    const l1 = await screen.findByTestId('l1');
    expect(within(l1).getByTestId('l1-C1-P')).toHaveTextContent('pass (40/40)');
    const abl = await screen.findByTestId('ablation');
    expect(within(abl).getByRole('row', { name: /why\(decision\)/ })).toHaveClass('row-broken');
    expect(within(abl).getByRole('row', { name: /recall/ })).not.toHaveClass('row-broken');
  });
});
