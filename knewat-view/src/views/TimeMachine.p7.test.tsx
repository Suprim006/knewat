import { screen, waitFor, within } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import { buildAcme } from '../fixtures/acme';
import { createFixtureApi } from '../fixtures/client';
import { applyP7 } from '../fixtures/p7';
import { isSuspectAt } from '../lib/memory';
import { renderApp } from '../test/render';

const p7 = applyP7(buildAcme());
const api = createFixtureApi(p7);
const maxStep = Math.max(...p7.flow.map((e) => e.step_n ?? 0));
const props = new Map(p7.nodes.map((n) => [n.id, n.props]));

/** Fact ids each agent has read at step n, and whether they are suspect at that agent's step time. */
async function expected(n: number) {
  const r = await api.step('acme', n);
  const read = r.agents.flatMap((a) => a.read.map((f) => ({ ...f, at: a.step_at })));
  return {
    suspect: read.filter((f) => isSuspectAt(props.get(f.id)!, f.at)).map((f) => f.id),
    dormant: read.filter((f) => f.status === 'dormant').map((f) => f.id),
    read,
  };
}

describe('Time Machine and P7', () => {
  it('shows a ⚠ badge on known facts that are suspect at the step time, and only from suspect_since on', async () => {
    const want = await expected(maxStep);
    expect(want.suspect.length).toBeGreaterThan(0); // the fixture is meant to exercise this
    renderApp(`/time?step=${maxStep}`, api);
    await waitFor(() => expect(screen.getAllByTestId('tm-suspect').length).toBe(want.suspect.length));
    for (const b of screen.getAllByTestId('tm-suspect')) expect(b).toHaveTextContent('⚠');
  });

  it('shows no suspect badge before the change that made the facts suspect', async () => {
    const early = await expected(3);
    expect(early.suspect).toEqual([]);
    renderApp('/time?step=3', api);
    await waitFor(() => expect(screen.getByTestId('agent-planner')).toHaveTextContent('its step 3'));
    expect(screen.queryAllByTestId('tm-suspect')).toHaveLength(0);
  });

  it('keeps dormant facts visible in as-of mode, marked dormant', async () => {
    const want = await expected(maxStep);
    expect(want.dormant.length).toBeGreaterThan(0);
    renderApp(`/time?step=${maxStep}`, api);
    await waitFor(() => expect(screen.getAllByTestId('tm-dormant').length).toBe(want.dormant.length));
  });

  it('is unchanged for a tenant without P7 data (no badges, no error)', async () => {
    renderApp(`/time?step=${maxStep}`, createFixtureApi(buildAcme()));
    const grid = await screen.findByTestId('agent-grid');
    await waitFor(() => expect(within(grid).getByTestId('agent-planner')).toBeInTheDocument());
    expect(screen.queryAllByTestId('tm-suspect')).toHaveLength(0);
    expect(screen.queryByRole('alert')).not.toBeInTheDocument();
  });
});
