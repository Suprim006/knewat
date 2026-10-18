import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';
import { screen, within } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import { createFixtureApi } from '../fixtures/client';
import { intervalsOverlap, medianComparison, parseResults, signTest } from '../lib/results';
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
    expect(r.run?.layers).toEqual(['L1', 'L4', 'ablation', 'L2', 'L2_scale', 'B1h', 'C7x', 'L6']);
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
    expect(by.P!.latencyMedianMs).toBeCloseTo(2.6, 1);
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
    expect(within(l2).getByTestId('l2-latency-P')).toHaveTextContent('2.60 ms');
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

describe('L2_scale in the real combined file', () => {
  const r = parseResults(REAL);
  const by = Object.fromEntries((r.l2Scale ?? []).map((x) => [x.arm, x]));

  it('reads accuracy, Wilson intervals, strata and failure analysis per arm', () => {
    expect(Object.keys(by).sort()).toEqual(['B0', 'B1', 'B2', 'P']);
    expect(['P', 'B1', 'B0', 'B2'].map((a) => by[a]!.correct)).toEqual([36, 32, 30, 23]);
    expect(by.P).toMatchObject({ n: 36, wilson: [90.4, 100], costUsd: 0 });
    expect(by.B0!.wilson).toEqual([68.1, 92.1]);
    expect(by.B0!.byStratum!.early).toEqual({ correct: 11, total: 13, pct: 84.6 });
    expect(by.B1!.failure).toMatchObject({ wrong: 4, wrongWithAllEvidence: 1 });
    expect(r.l2ScaleInfo).toMatchObject({ mode: 'full', asked: 36, total: 40 });
    expect(r.l2ScaleInfo!.history!.overBudget.B0).toBeCloseTo(16.65, 2);
    expect(r.l2ScaleInfo!.honesty.length).toBe(7);
    expect(r.l2ScaleInfo!.plexusChanges.length).toBeGreaterThan(0);
  });

  it('computes the paired sign tests BASELINE.md reports (p = 0.031 for B0, 0.125 for B1)', () => {
    const t0 = signTest(by.P!, by.B0!)!;
    const t1 = signTest(by.P!, by.B1!)!;
    expect([t0.aOnly, t0.bOnly]).toEqual([6, 0]);
    expect(t0.p).toBeCloseTo(0.031, 3);
    expect([t1.aOnly, t1.bOnly]).toEqual([4, 0]);
    expect(t1.p).toBeCloseTo(0.125, 3);
    expect(signTest(by.P!, by.B2!)!.p).toBeLessThan(0.001);
    expect(intervalsOverlap(by.P!.wilson, by.B0!.wilson)).toBe(true);
    expect(intervalsOverlap(by.P!.wilson, by.B2!.wilson)).toBe(false);
  });

  it('the sign test is symmetric and handles no discordant pairs', () => {
    const q = (id: string, correct: boolean) => ({ id, correct });
    const a = { arm: 'a', accuracy: 0, questions: [q('1', true), q('2', true), q('3', false)] };
    const b = { arm: 'b', accuracy: 0, questions: [q('1', true), q('2', true), q('3', false)] };
    expect(signTest(a, b)).toEqual({ aOnly: 0, bOnly: 0, n: 0, p: 1 });
    expect(signTest({ arm: 'x', accuracy: 0 }, b)).toBeUndefined();
  });
});

describe('Results page: L2 at scale section', () => {
  const render = () => renderApp('/results', createFixtureApi(acme, REAL));

  it('is its own section after L2, with accuracy, Wilson intervals, tokens, cost and latency', async () => {
    render();
    const s = await screen.findByTestId('l2scale');
    expect(s).toHaveAttribute('id', 'l2scale');
    expect(within(s).getByTestId('l2scale-acc-P')).toHaveTextContent('100% (36/36)');
    expect(within(s).getByTestId('l2scale-acc-B1')).toHaveTextContent('88.9% (32/36)');
    expect(within(s).getByTestId('l2scale-acc-B0')).toHaveTextContent('83.3% (30/36)');
    expect(within(s).getByTestId('l2scale-acc-B2')).toHaveTextContent('63.9% (23/36)');
    expect(within(s).getByTestId('l2scale-wilson-B0')).toHaveTextContent('68.1% – 92.1%');
    expect(within(s).getByTestId('l2scale-wilson-P')).toHaveTextContent('90.4% – 100%');
    expect(within(s).getByTestId('l2scale-whole-B0')).toHaveTextContent('77.8% (28/36)');
    expect(within(s).getByTestId('l2scale-tokens-B1')).toHaveTextContent('22,010');
    expect(within(s).getByTestId('l2scale-cost-B0')).toHaveTextContent('$2.79');
    expect(within(s).getByTestId('l2scale-cost-P')).toHaveTextContent('$0 (no LLM)');
    expect(within(s).getByTestId('l2scale-history')).toHaveTextContent('16.6');
    // the original L2 section is still there and still says what it said
    expect(screen.getByTestId('l2-acc-B0')).toHaveTextContent('100% (43/43)');
  });

  it('shows the paired sign test and states that it is not a proof', async () => {
    render();
    const sig = await screen.findByTestId('l2scale-significance');
    expect(within(sig).getByTestId('l2scale-sign-B0')).toHaveTextContent('60');
    expect(within(sig).getByTestId('l2scale-sign-B0')).toHaveTextContent('0.031');
    expect(within(sig).getByTestId('l2scale-sign-B1')).toHaveTextContent(
      '0.125 (not distinguishable from noise)',
    );
    expect(within(sig).getByTestId('l2scale-sign-B1')).toHaveTextContent('yes');
    expect(within(sig).getByTestId('l2scale-sign-B2')).toHaveTextContent('< 0.001');
    expect(within(sig).getByTestId('l2scale-sign-B2')).toHaveTextContent('no');
    expect(within(sig).getByTestId('l2scale-caveat')).toHaveTextContent(
      'not distinguishable from sampling noise',
    );
    expect(within(sig).getByTestId('l2scale-caveat')).toHaveTextContent('36 questions, one run each');
  });

  it('prints the run honesty notes verbatim inside the section', async () => {
    render();
    const box = await screen.findByTestId('l2scale-honesty');
    const l2s = (REAL.layers as { L2_scale: { honesty: string[] } }).L2_scale.honesty;
    expect(l2s).toHaveLength(7);
    for (const h of l2s) expect(within(box).getByText(h)).toBeInTheDocument();
    expect(box).toHaveTextContent(
      'Questions that aggregate across sprints (the strongest case for a graph) are NOT in this set.',
    );
    expect(box).toHaveTextContent('sprints here do not interact, which favours retrieval');
    expect(box).toHaveTextContent('that engineering effort is part of what P costs');
    expect(screen.getByTestId('l2scale-notes')).toHaveTextContent('re-used from the on-disk cache');
  });

  it('lists the changes made to the Plexus answerer', async () => {
    render();
    expect(await screen.findByTestId('l2scale-changes')).toHaveTextContent(
      'Nine operations ask about a whole class',
    );
  });
});

describe('P9 layers on the real combined file', () => {
  const r = parseResults(REAL);

  it('B1h: hand-written SQL ties Plexus on L2 and L2-scale', () => {
    const rows = Object.fromEntries((r.b1h?.rows ?? []).map((x) => [x.layer, x]));
    expect(rows.L2).toMatchObject({ correct: 43, total: 43, plexusCorrect: 43 });
    expect(rows.L2_scale).toMatchObject({ correct: 36, total: 36, plexusCorrect: 36 });
  });

  it('C7 extended: 0 false merges of 150, and the heavy-paraphrase target is reported as missed', () => {
    const p = r.c7x!.arms.find((a) => a.arm === 'P')!;
    expect(p).toMatchObject({ pairs: 226, notMergePairs: 150, falseMerges: 0, autoMerged: 51, surfaced: 70 });
    expect(r.c7x!.arms.find((a) => a.arm === 'B2')!.falseMerges).toBe(68);
    const missed = r.c7x!.targets.filter((t) => t.missed).map((t) => t.category);
    expect([...missed].sort()).toEqual(['heavy', 'light', 'unit_same']); // each below its pre-registered auto target
  });

  it('L6: the pilot totals, the pre-registered families and the post-fix re-run', () => {
    const l6 = r.l6!;
    expect(l6.families.map((f) => f.id)).toEqual(['A', 'B', 'D', 'E', 'F']);
    const pilot = Object.fromEntries(l6.pilotTotals.map((p) => [p.arm, `${p.correct}/${p.n}`]));
    expect(pilot).toEqual({ B1a: '24/24', B0g: '24/24', B0r: '2/24', 'P-mcp': '10/16' });
    expect(l6.llmCalls).toBe(88);
    expect(l6.costUsd).toBeCloseTo(7.0855, 3);
    const a = l6.families.find((f) => f.id === 'A')!;
    expect(a.det.find((x) => x.arm === 'P-product-service')!.strict).toBe('0/24'); // before the fix
    expect(a.postfixA.find((x) => x.arm === 'P-product-service')).toMatchObject({
      strict: '24/24',
      timeouts: 0,
    });
    expect(a.postfixA.find((x) => x.arm === 'P-product-tool')!.strict).toBe('18/24'); // the 2,000-item cap
    const f = l6.families.find((x) => x.id === 'F')!;
    expect(f.crash.find((c) => c.arm === 'P')!.orphans).toBe(94);
    expect(f.postfixF.find((c) => c.arm === 'P')!.orphans).toBe(0);
    expect(l6.families.find((x) => x.id === 'D')!.medianSlowdown!).toBeCloseTo(4.6, 1);
  });
});

describe('Results page: P9 sections on the real combined file', () => {
  it('shows B1h, C7 extended and L6 with the pre-registered expectation next to the result', async () => {
    renderApp('/results', createFixtureApi(acme, REAL));
    const b1h = await screen.findByTestId('b1h');
    expect(within(b1h).getByTestId('b1h-L2')).toHaveTextContent('43/43');
    expect(within(b1h).getByTestId('b1h-L2_scale')).toHaveTextContent('SQL ties');
    const c7x = await screen.findByTestId('c7x');
    expect(within(c7x).getByTestId('c7x-headline')).toHaveTextContent('0 false merges in 150 pairs');
    expect(within(c7x).getByTestId('c7x-missed')).toHaveTextContent('heavy paraphrases');
    const l6 = await screen.findByTestId('l6');
    for (const fam of ['A', 'B', 'D', 'E', 'F']) {
      expect(within(l6).getByTestId(`l6-${fam}-expect`)).toHaveTextContent('Pre-registered');
    }
    expect(within(l6).getByTestId('l6-A-fix-P-product-service')).toHaveTextContent('24/24');
    expect(within(l6).getByTestId('l6-F-crash-P')).toHaveTextContent('94');
    expect(within(l6).getByTestId('l6-F-fix-P')).toHaveTextContent('0 of 2093');
    expect(within(l6).getByTestId('l6-D-speed')).toHaveTextContent('4.6x faster');
    expect(within(l6).getByTestId('l6-pilot-P-mcp')).toHaveTextContent('10/16');
    expect(within(l6).getByTestId('l6-pilot-B0r')).toHaveTextContent('2/24');
  });
});
