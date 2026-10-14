import { screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it } from 'vitest';
import { renderApp } from './test/render';

describe('App shell', () => {
  it('shows the nav, a tenant selector and the fixture tenants', async () => {
    renderApp('/flow');
    const nav = screen.getByRole('navigation', { name: 'Main' });
    for (const name of ['Explorer', 'Flow', 'Time Machine', 'Why', 'Inventory', 'Results']) {
      expect(within(nav).getByRole('link', { name })).toBeInTheDocument();
    }
    const select = await screen.findByRole('combobox', { name: 'Tenant' });
    await waitFor(() =>
      expect(
        within(select)
          .getAllByRole('option')
          .map((o) => o.textContent),
      ).toEqual(['acme', 'scratch']),
    );
  });

  it.each([
    ['/why/abc-123', 'Why'],
    ['/results', 'Results'],
  ])('%s is a placeholder page', (route, title) => {
    renderApp(route);
    expect(screen.getByRole('heading', { level: 1, name: title })).toBeInTheDocument();
    expect(screen.getByText(/Placeholder/)).toBeInTheDocument();
  });

  it('routes /flow to the Flow page', async () => {
    renderApp('/flow');
    expect(await screen.findByRole('heading', { level: 1, name: 'Flow' })).toBeInTheDocument();
    expect(screen.queryByText(/Placeholder/)).not.toBeInTheDocument();
  });

  it('passes the :id of /why/:id to the page', () => {
    renderApp('/why/abc-123');
    expect(screen.getByText('abc-123')).toBeInTheDocument();
  });

  it('navigates between pages and cycles the theme', async () => {
    const user = userEvent.setup();
    renderApp('/');
    await user.click(screen.getByRole('link', { name: 'Inventory' }));
    expect(await screen.findByRole('heading', { level: 1, name: /Inventory/ })).toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: /Theme: Auto/ }));
    expect(document.documentElement.dataset.theme).toBe('light');
    await user.click(screen.getByRole('button', { name: /Theme: Light/ }));
    expect(document.documentElement.dataset.theme).toBe('dark');
    await user.click(screen.getByRole('button', { name: /Theme: Dark/ }));
    expect(document.documentElement.dataset.theme).toBeUndefined();
  });
});
