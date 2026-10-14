import { screen, waitFor, within } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import { createFixtureApi } from '../fixtures/client';
import { acme, renderApp } from '../test/render';

const noTenants = () => ({ ...createFixtureApi(acme), tenants: async () => ({ tenants: [] }) });

describe('no tenants yet (empty list, not an error)', () => {
  it('leaves the loading state: the selector says so and a status explains it', async () => {
    renderApp('/', noTenants());
    const select = await screen.findByRole('combobox', { name: 'Tenant' });
    await waitFor(() => expect(within(select).getByRole('option')).toHaveTextContent('no tenants'));
    expect(select).toBeDisabled();
    expect(screen.getByRole('status')).toHaveTextContent(/No tenants yet/);
    expect(screen.queryByRole('alert')).not.toBeInTheDocument();
  });

  it('Explorer and Inventory stop saying "Loading" / "Waiting"', async () => {
    renderApp('/', noTenants());
    await screen.findByRole('status');
    expect(screen.queryByText('Loading graph…')).not.toBeInTheDocument();
    expect(screen.getByText(/no tenant to show/i)).toBeInTheDocument();
  });

  it('Inventory shows the empty state', async () => {
    renderApp('/inventory', noTenants());
    await screen.findByRole('status');
    expect(screen.queryByText('Waiting for tenants…')).not.toBeInTheDocument();
    expect(await screen.findByText(/no tenants yet.*inventory/i)).toBeInTheDocument();
  });

  it('still says loading while the tenant list is in flight', async () => {
    renderApp('/', { ...createFixtureApi(acme), tenants: () => new Promise(() => undefined) });
    expect(screen.getByRole('combobox', { name: 'Tenant' })).toHaveTextContent('loading…');
    expect(screen.queryByRole('status')).not.toBeInTheDocument();
  });
});
