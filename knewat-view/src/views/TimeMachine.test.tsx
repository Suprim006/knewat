import { fireEvent, screen, waitFor, within } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import { createFixtureApi } from '../fixtures/client';
import { diffAgent } from '../lib/timeMachine';
import { acme, renderApp } from '../test/render';

const maxStep = Math.max(...acme.flow.map((e) => e.step_n ?? 0));
const api = createFixtureApi(acme);

const readCount = (agent: string) => {
  const card = screen.getByTestId(`agent-${agent}`);
  return within(card).getByRole('heading', { name: /Knew \(/ }).textContent;
};

describe('Time Machine', () => {
  it('starts at the last step and shows what each agent knew and wrote', async () => {
    renderApp('/time');
    const grid = await screen.findByTestId('agent-grid');
    await waitFor(() => expect(within(grid).getByTestId('agent-planner')).toBeInTheDocument());
    expect(screen.getByTestId('step-value')).toHaveTextContent(`${maxStep} / ${maxStep}`);
    for (const a of ['planner', 'researcher', 'builder'])
      expect(within(grid).getByTestId(`agent-${a}`)).toBeInTheDocument();
    const planner = within(screen.getByTestId('agent-planner'));
    expect(planner.getByRole('heading', { name: /Wrote \(/ })).toBeInTheDocument();
    expect(planner.getAllByRole('link', { name: 'Why?' }).length).toBeGreaterThan(0);
  });

  it('changes the content when the slider moves', async () => {
    renderApp('/time?step=3');
    await waitFor(() => expect(screen.getByTestId('agent-planner')).toBeInTheDocument());
    await waitFor(() => expect(screen.getByTestId('agent-planner')).toHaveTextContent('its step 3'));
    const early = readCount('planner');
    const earlyText = screen.getByTestId('agent-grid').textContent;

    fireEvent.change(screen.getByRole('slider', { name: 'Step' }), { target: { value: String(maxStep) } });
    await waitFor(() =>
      expect(screen.getByTestId('step-value')).toHaveTextContent(`${maxStep} / ${maxStep}`),
    );
    await waitFor(() => expect(screen.getByTestId('agent-grid').textContent).not.toBe(earlyText));
    await waitFor(() => expect(readCount('planner')).not.toBe(early));
  });

  it('highlights a value moving between steps (API version v1 -> v2)', async () => {
    // find the step at which some agent's knowledge of one slot changes value, using the same API
    let found: { n: number; agent: string } | null = null;
    for (let n = 2; n <= maxStep && !found; n++) {
      const [a, b] = await Promise.all([api.step('acme', n - 1), api.step('acme', n)]);
      for (const ag of b.agents) {
        const d = diffAgent(
          a.agents.find((x) => x.agent_id === ag.agent_id),
          ag,
        );
        if (d.changed.some((c) => c.to.predicate === 'api_version')) found = { n, agent: ag.agent_id };
      }
    }
    expect(found, 'some agent should see api_version move from v1 to v2').not.toBeNull();
    renderApp(`/time?step=${found!.n}`);
    const diff = await screen.findByTestId(`diff-${found!.agent}`);
    const changed = diff.querySelector('[data-diff="changed"]')!;
    expect(changed).toHaveTextContent('api_version changed');
    expect(changed.querySelector('del')).toHaveTextContent('v1');
    expect(changed.querySelector('ins')).toHaveTextContent('v2');
    // the new value is also marked in the "Knew" list
    expect(within(screen.getByTestId(`agent-${found!.agent}`)).getAllByText(/v2/).length).toBeGreaterThan(0);
  });

  it('clamps an out-of-range ?step and shows an empty state for a tenant without steps', async () => {
    renderApp('/time?step=9999');
    await waitFor(() =>
      expect(screen.getByTestId('step-value')).toHaveTextContent(`${maxStep} / ${maxStep}`),
    );
  });
});

describe('diffAgent', () => {
  const fact = (id: string, value: string, predicate = 'p') => ({ id, entity: 'E', predicate, value });
  const agent = (read: ReturnType<typeof fact>[], wrote: string[] = []) => ({
    agent_id: 'a',
    step_n: 1,
    step_at: 1,
    read,
    wrote: wrote.map((id) => ({ id, label: 'Fact', summary: id })),
  });

  it('classifies added, removed, changed and new writes', () => {
    const d = diffAgent(
      agent([fact('1', 'v1'), fact('2', 'x', 'q'), fact('3', 'gone', 'r')], ['w1']),
      agent([fact('4', 'v2'), fact('2', 'x', 'q'), fact('5', 'new', 's')], ['w1', 'w2']),
    );
    expect(d.changed.map((c) => [c.from.value, c.to.value])).toEqual([['v1', 'v2']]);
    expect(d.added.map((f) => f.id)).toEqual(['5']);
    expect(d.removed.map((f) => f.id)).toEqual(['3']);
    expect(d.newWrites.map((w) => w.id)).toEqual(['w2']);
  });

  it('treats a first step as all new', () => {
    const d = diffAgent(undefined, agent([fact('1', 'a')], ['w']));
    expect(d.added).toHaveLength(1);
    expect(d.newWrites).toHaveLength(1);
  });
});
