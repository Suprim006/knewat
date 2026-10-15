import { screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it } from 'vitest';
import { ApiError } from '../api';
import type { VerifyRow } from '../api';
import { buildAcme } from '../fixtures/acme';
import { createFixtureApi } from '../fixtures/client';
import { applyP7 } from '../fixtures/p7';
import { renderApp } from '../test/render';

const p7 = applyP7(buildAcme());
const rowOf = (key: string) => `verify-row-${p7.ids[key]}`;

describe('Verify page', () => {
  it('lists the verify queue: fact, reason, decisions at risk, activation', async () => {
    renderApp('/verify', createFixtureApi(p7));
    expect(await screen.findByRole('heading', { level: 1, name: 'Verify' })).toBeInTheDocument();
    const jwt = await screen.findByTestId(rowOf('f.jwt'));
    expect(jwt).toHaveTextContent('Authentication');
    expect(jwt).toHaveTextContent('scheme');
    expect(jwt).toHaveTextContent('JWT');
    expect(within(jwt).getByTestId('verify-reason')).toHaveTextContent('changed in a1b2c3d');
    expect(within(jwt).getByTestId('verify-decisions')).toHaveTextContent('2');
    expect(within(jwt).getByTestId('verify-activation')).toHaveTextContent('1.40');
    expect(within(jwt).getByTestId('verify-state')).toHaveTextContent(/suspect/i);
    expect(within(jwt).getByRole('link', { name: 'Why?' })).toHaveAttribute(
      'href',
      `/why/${encodeURIComponent(p7.ids['f.jwt']!)}`,
    );
    expect(within(jwt).getByText(/app\/auth\/jwt\.py/, { selector: 'code' })).toBeInTheDocument();
    // a review-date fact: verified state, no change
    const ci = screen.getByTestId(rowOf('f.ci'));
    expect(within(ci).getByTestId('verify-reason')).toHaveTextContent('review date passed');
    expect(within(ci).getByTestId('verify-state')).toHaveTextContent(/review/i);
  });

  it('orders rows by decisions at risk, then activation', async () => {
    renderApp('/verify', createFixtureApi(p7));
    await screen.findByTestId(rowOf('f.jwt'));
    const rows = screen.getAllByTestId(/^verify-row-/);
    const decisions = rows.map((r) => Number(within(r).getByTestId('verify-decisions').textContent));
    expect(decisions).toEqual([...decisions].sort((a, b) => b - a));
    expect(rows[0]).toBe(screen.getByTestId(rowOf('f.jwt')));
  });

  it('highlights the fact named in ?fact=', async () => {
    renderApp(`/verify?fact=${p7.ids['f.pg_tp']}`, createFixtureApi(p7));
    const row = await screen.findByTestId(rowOf('f.pg_tp'));
    expect(row).toHaveAttribute('aria-current', 'true');
    expect(screen.getByTestId(rowOf('f.jwt'))).not.toHaveAttribute('aria-current');
  });

  it('lists the docs to update with the change that outdated them', async () => {
    renderApp('/verify', createFixtureApi(p7));
    const docs = await screen.findByRole('region', { name: 'Docs to update' });
    const doc = await within(docs).findByTestId('doc-row');
    expect(doc).toHaveTextContent('rfc-0042-auth.md');
    expect(doc).toHaveTextContent('docs/rfc-0042-auth.md');
    expect(doc).toHaveTextContent('a1b2c3d');
    expect(doc).toHaveTextContent('app/auth/jwt.py');
  });

  it('is read-only: no forms, no buttons that write', async () => {
    const { container } = renderApp('/verify', createFixtureApi(p7));
    await screen.findByTestId(rowOf('f.jwt'));
    const main = container.querySelector('main')!;
    expect(main.querySelector('form')).toBeNull();
    expect(within(main).queryAllByRole('button')).toHaveLength(0);
    expect(within(main).getByText(/viewer never writes/i)).toBeInTheDocument();
  });

  it('shows empty states for a tenant with nothing to verify', async () => {
    const user = userEvent.setup();
    renderApp('/verify', createFixtureApi(p7));
    await screen.findByTestId(rowOf('f.jwt'));
    await user.selectOptions(await screen.findByRole('combobox', { name: 'Tenant' }), 'scratch');
    expect(await screen.findByText(/no fact needs verification/i)).toBeInTheDocument();
    expect(await screen.findByText(/no doc is behind its code/i)).toBeInTheDocument();
    expect(screen.queryByTestId(/^verify-row-/)).not.toBeInTheDocument();
  });

  it('shows a dash for activation when forgetting is off, and keeps the docs when the queue fails', async () => {
    const base = createFixtureApi(p7);
    renderApp('/verify', {
      ...base,
      verifyQueue: async (t, q) => ({
        rows: (await base.verifyQueue(t, q)).rows.map((r): VerifyRow => ({
          ...r,
          activation: null,
          protected: null,
        })),
      }),
    });
    const jwt = await screen.findByTestId(rowOf('f.jwt'));
    expect(within(jwt).getByTestId('verify-activation')).toHaveTextContent('—');
  });

  it('reports a failed queue without hiding the docs list', async () => {
    renderApp('/verify', {
      ...createFixtureApi(p7),
      verifyQueue: () => Promise.reject(new ApiError(503, 'x/verify-queue')),
    });
    expect(await screen.findByRole('alert')).toHaveTextContent(/could not load the verify queue/i);
    await waitFor(() => expect(screen.getByTestId('doc-row')).toBeInTheDocument());
  });

  it('works against a server that predates P7 (404s): both lists say so instead of crashing', async () => {
    renderApp('/verify', {
      ...createFixtureApi(p7),
      verifyQueue: () => Promise.reject(new ApiError(404, 'x/verify-queue')),
      docsToUpdate: () => Promise.reject(new ApiError(404, 'x/docs-to-update')),
    });
    expect(await screen.findAllByText(/not available on this server/i)).toHaveLength(2);
    expect(screen.queryByRole('alert')).not.toBeInTheDocument();
  });
});

describe('navigation', () => {
  it('has a Verify link in the main nav', async () => {
    const user = userEvent.setup();
    renderApp('/', createFixtureApi(p7));
    await user.click(screen.getByRole('link', { name: 'Verify' }));
    expect(await screen.findByRole('heading', { level: 1, name: 'Verify' })).toBeInTheDocument();
  });
});
