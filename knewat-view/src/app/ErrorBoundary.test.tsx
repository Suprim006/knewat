import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { AppProviders } from './AppProviders';
import { ErrorBoundary } from './ErrorBoundary';
import { Layout } from './Layout';
import { createFixtureApi } from '../fixtures/client';
import { GraphCanvas } from '../components/GraphCanvas';
import { acme } from '../test/render';

let broken = true;
function Flaky() {
  if (broken) throw new Error('bad payload: nodes is not iterable');
  return <p>all good</p>;
}

beforeEach(() => {
  broken = true;
  vi.spyOn(console, 'error').mockImplementation(() => undefined); // React logs caught render errors
});
afterEach(() => vi.restoreAllMocks());

describe('ErrorBoundary', () => {
  it('shows the error with a retry button, and retry renders the child again', async () => {
    const user = userEvent.setup();
    render(
      <ErrorBoundary resetKey="a">
        <Flaky />
      </ErrorBoundary>,
    );
    expect(screen.getByRole('alert')).toHaveTextContent('Something went wrong');
    expect(screen.getByRole('alert')).toHaveTextContent('bad payload: nodes is not iterable');
    broken = false;
    await user.click(screen.getByRole('button', { name: 'Try again' }));
    expect(screen.getByText('all good')).toBeInTheDocument();
    expect(screen.queryByRole('alert')).not.toBeInTheDocument();
  });

  it('resets by itself when the resetKey changes (navigating away)', () => {
    const { rerender } = render(
      <ErrorBoundary resetKey="/a">
        <Flaky />
      </ErrorBoundary>,
    );
    expect(screen.getByRole('alert')).toBeInTheDocument();
    broken = false;
    rerender(
      <ErrorBoundary resetKey="/b">
        <Flaky />
      </ErrorBoundary>,
    );
    expect(screen.getByText('all good')).toBeInTheDocument();
  });

  it('keeps the app shell (nav, tenant selector) alive when a page throws', async () => {
    render(
      <AppProviders api={createFixtureApi(acme)}>
        <MemoryRouter initialEntries={['/boom']}>
          <Routes>
            <Route element={<Layout />}>
              <Route path="boom" element={<Flaky />} />
            </Route>
          </Routes>
        </MemoryRouter>
      </AppProviders>,
    );
    expect(await screen.findByRole('alert')).toHaveTextContent('Something went wrong');
    expect(screen.getByRole('navigation', { name: 'Main' })).toBeInTheDocument();
    expect(screen.getByRole('combobox', { name: 'Tenant' })).toBeInTheDocument();
  });
});

describe('graph canvas accessibility', () => {
  it('describes the canvas and points keyboard users at search and the details panel', () => {
    render(<GraphCanvas onReady={() => undefined} onSelect={() => undefined} />);
    const canvas = screen.getByRole('img', { name: 'Graph canvas' });
    const desc = canvas.getAttribute('aria-describedby');
    expect(desc).toBeTruthy();
    expect(document.getElementById(desc!)).toHaveTextContent(/search/i);
  });
});
