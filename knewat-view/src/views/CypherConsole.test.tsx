import { screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';
import { ApiError } from '../api';
import type { CypherResult } from '../api';
import { buildAcme } from '../fixtures/acme';
import { createFixtureApi } from '../fixtures/client';
import { renderApp } from '../test/render';

const base = createFixtureApi(buildAcme());
const result = (over: Partial<CypherResult> = {}): CypherResult => ({
  tenant: 'acme',
  columns: ['n', 'x'],
  rows: [
    [{ _type: 'node', id: 1, labels: ['Fact'], properties: { id: 'f1' } }, null],
    ['hello', 3],
  ],
  row_count: 2,
  truncated: false,
  run_time_ms: 12,
  ...over,
});

describe('CypherConsole', () => {
  it('runs a query and shows the table and status', async () => {
    const cypher = vi.fn(async () => result());
    const user = userEvent.setup();
    renderApp('/cypher', { ...base, cypher });
    await screen.findByText(/tenant acme/);
    await user.click(screen.getByRole('button', { name: 'Run' }));
    const table = await screen.findByRole('table', { name: 'Query result' });
    expect(within(table).getByText('(:Fact {id: "f1"})')).toBeInTheDocument();
    expect(within(table).getByText('null')).toBeInTheDocument();
    expect(within(table).getByText('hello')).toBeInTheDocument();
    expect(screen.getByTestId('cypher-status')).toHaveTextContent('2 rows · 12 ms');
    expect(cypher).toHaveBeenCalledWith('acme', expect.stringContaining('MATCH'));
  });

  it('shows the server detail on error', async () => {
    const cypher = async () => {
      throw new ApiError(400, 'u', 'Invalid input near FOO');
    };
    const user = userEvent.setup();
    renderApp('/cypher', { ...base, cypher });
    await screen.findByText(/tenant acme/);
    await user.click(screen.getByRole('button', { name: 'Run' }));
    expect(await screen.findByRole('alert')).toHaveTextContent('Invalid input near FOO');
  });

  it('shows a truncation notice', async () => {
    const user = userEvent.setup();
    renderApp('/cypher', { ...base, cypher: async () => result({ truncated: true }) });
    await screen.findByText(/tenant acme/);
    await user.click(screen.getByRole('button', { name: 'Run' }));
    expect(await screen.findByText(/truncated at 500 rows/i)).toBeInTheDocument();
  });

  it('fills the textarea from an example, disables Run when empty, and runs on Ctrl+Enter', async () => {
    const cypher = vi.fn(async () => result());
    const user = userEvent.setup();
    renderApp('/cypher', { ...base, cypher });
    await screen.findByText(/tenant acme/);
    const box = screen.getByRole('textbox', { name: 'Cypher query' });
    await user.clear(box);
    expect(screen.getByRole('button', { name: 'Run' })).toBeDisabled();
    await user.click(screen.getByRole('button', { name: 'Labels' }));
    expect(box).toHaveValue('CALL db.labels()');
    await user.click(box);
    await user.keyboard('{Control>}{Enter}{/Control}');
    await waitFor(() => expect(cypher).toHaveBeenCalledWith('acme', 'CALL db.labels()'));
  });

  it('works against the fixtures client', async () => {
    const user = userEvent.setup();
    renderApp('/cypher');
    await screen.findByText(/tenant acme/);
    await user.click(screen.getByRole('button', { name: 'Run' }));
    const table = await screen.findByRole('table', { name: 'Query result' });
    expect(within(table).getByText('Fact')).toBeInTheDocument();
  });
});
