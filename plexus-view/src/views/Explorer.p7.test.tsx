import { screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it } from 'vitest';
import { ApiError } from '../api';
import { buildAcme } from '../fixtures/acme';
import { createFixtureApi } from '../fixtures/client';
import { applyP7 } from '../fixtures/p7';
import { renderApp } from '../test/render';

const p7 = applyP7(buildAcme());
const p7Api = () => createFixtureApi(p7);

async function loaded() {
  await waitFor(() => {
    const t = screen.getByTestId('visible-counts').textContent ?? '';
    expect(/of (\d+) nodes/.exec(t)?.[1]).toBeDefined();
    expect(Number(/of (\d+) nodes/.exec(t)![1])).toBeGreaterThan(0);
  });
}

async function openFact(user: ReturnType<typeof userEvent.setup>, query: string, name: RegExp) {
  await user.type(screen.getByRole('searchbox', { name: /search nodes/i }), query);
  await user.click(await screen.findByRole('button', { name }));
  return screen.getByRole('complementary', { name: 'Node details' });
}

describe('Explorer legend for staleness and forgetting', () => {
  it('explains each marker, with counts from the loaded facts', async () => {
    renderApp('/', p7Api());
    await loaded();
    const legend = await screen.findByRole('region', { name: 'Memory markers' });
    const suspect = within(legend).getByTestId('legend-suspect');
    expect(suspect).toHaveTextContent('⚠');
    expect(suspect).toHaveTextContent(/suspect/i);
    expect(Number(within(suspect).getByTestId('legend-count').textContent)).toBeGreaterThanOrEqual(5);
    expect(within(legend).getByTestId('legend-pinned')).toHaveTextContent('📌');
    expect(within(legend).getByTestId('legend-pinned')).toHaveTextContent(/pinned/i);
    expect(within(legend).getByTestId('legend-dormant')).toHaveTextContent(/dashed/i);
    expect(within(legend).getByTestId('legend-dormant')).toHaveTextContent(/dormant/i);
    expect(within(legend).getByTestId('legend-faded')).toHaveTextContent(/opacity|faded/i);
    expect(within(legend).getByTestId('legend-dormant').querySelector('[data-testid=legend-count]')).toHaveTextContent('3');
    expect(within(legend).getByTestId('legend-pinned').querySelector('[data-testid=legend-count]')).toHaveTextContent('2');
  });

  it('shows an empty state for a tenant with no staleness or forgetting data', async () => {
    renderApp('/', createFixtureApi(buildAcme()));
    await loaded();
    const legend = await screen.findByRole('region', { name: 'Memory markers' });
    expect(within(legend).getByText(/no staleness or forgetting data/i)).toBeInTheDocument();
    expect(within(legend).queryByTestId('legend-suspect')).not.toBeInTheDocument();
  });
});

describe('Node panel: memory strength', () => {
  it('shows activation, protection, surprise, events and the verify state of a suspect fact', async () => {
    const user = userEvent.setup();
    renderApp('/', p7Api());
    await loaded();
    const panel = await openFact(user, 'scheme: JWT', /scheme: JWT/);
    const strength = await within(panel).findByRole('region', { name: 'Memory strength' });
    await waitFor(() => expect(within(strength).getByTestId('strength-events')).toBeInTheDocument());
    expect(within(strength).getByTestId('strength-activation')).toHaveTextContent('1.40');
    expect(within(strength).getByTestId('strength-protected')).toHaveTextContent(/protected/i);
    expect(within(strength).getByTestId('strength-protected')).toHaveTextContent(/decision/);
    expect(within(strength).getByTestId('strength-surprise')).toHaveTextContent('0.00');
    expect(within(strength).getByTestId('strength-events')).toHaveTextContent('1 creation, 2 decisions');
    const verify = within(strength).getByTestId('strength-verify');
    expect(verify).toHaveTextContent(/suspect/i);
    expect(verify).toHaveTextContent(/since 2026-10-15/);
    await waitFor(() => expect(verify).toHaveTextContent('a1b2c3d'));
    expect(verify).toHaveTextContent('app/auth/jwt.py');
    const link = within(panel).getByRole('link', { name: /needs verification/i });
    expect(link).toHaveAttribute('href', `/verify?fact=${encodeURIComponent(p7.ids['f.jwt']!)}`);
    // badges in the panel header
    expect(within(panel).getByTestId('badge-suspect')).toHaveTextContent('⚠ suspect');
  });

  it('shows a pinned fact as protected by its pin and offers no verification link', async () => {
    const user = userEvent.setup();
    renderApp('/', p7Api());
    await loaded();
    const panel = await openFact(user, 'language: Python 3.12 with FastAPI', /language: Python 3\.12 with FastAPI/);
    const strength = await within(panel).findByRole('region', { name: 'Memory strength' });
    await waitFor(() => expect(within(strength).getByTestId('strength-protected')).toHaveTextContent(/pinned/));
    expect(within(panel).getByTestId('badge-pinned')).toHaveTextContent('📌 pinned');
    expect(within(strength).getByTestId('strength-verify')).toHaveTextContent(/verified/i);
    expect(within(panel).queryByRole('link', { name: /needs verification/i })).not.toBeInTheDocument();
  });

  it('marks a dormant fact', async () => {
    const user = userEvent.setup();
    renderApp('/', p7Api());
    await loaded();
    const panel = await openFact(user, 'single writer', /sqlite_limit/);
    expect(within(panel).getByTestId('badge-dormant')).toHaveTextContent('dormant');
    expect(await within(panel).findByTestId('strength-activation')).toHaveTextContent('-4.20');
  });

  it('degrades to the activation from the graph when /memory-strength fails', async () => {
    const user = userEvent.setup();
    const base = p7Api();
    renderApp('/', {
      ...base,
      memoryStrength: () => Promise.reject(new ApiError(502, 'x/memory-strength/1')),
    });
    await loaded();
    const panel = await openFact(user, 'scheme: JWT', /scheme: JWT/);
    const strength = await within(panel).findByRole('region', { name: 'Memory strength' });
    expect(await within(strength).findByText(/details unavailable/i)).toBeInTheDocument();
    expect(within(strength).getByTestId('strength-activation')).toHaveTextContent('1.40');
  });

  it('says so, without error, for a fact from a tenant without P7 data; non-facts have no section', async () => {
    const user = userEvent.setup();
    renderApp('/', createFixtureApi(buildAcme()));
    await loaded();
    const panel = await openFact(user, 'scheme: JWT', /scheme: JWT/);
    const strength = await within(panel).findByRole('region', { name: 'Memory strength' });
    expect(within(strength).getByText(/no memory-strength data/i)).toBeInTheDocument();
    expect(within(panel).queryByRole('alert')).not.toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: 'Close details' }));
    await user.clear(screen.getByRole('searchbox', { name: /search nodes/i }));
    const decision = await openFact(user, 'Authenticate with JWT', /Authenticate with JWT bearer tokens/);
    expect(within(decision).queryByRole('region', { name: 'Memory strength' })).not.toBeInTheDocument();
  });
});
