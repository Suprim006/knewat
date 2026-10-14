import { screen, waitFor, within } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import { acme, renderApp } from '../test/render';

describe('Inventory', () => {
  it('totals match the fixtures', async () => {
    renderApp('/inventory');
    await waitFor(() => expect(screen.getByTestId('inventory-node-total')).toBeInTheDocument());
    expect(screen.getByTestId('inventory-node-total')).toHaveTextContent(String(acme.nodes.length));
    expect(screen.getByTestId('inventory-edge-total')).toHaveTextContent(String(acme.edges.length));
  });

  it('shows per-label and per-edge-type counts that add up', async () => {
    renderApp('/inventory');
    await screen.findByTestId('inventory-node-total');
    const labels = new Map<string, number>();
    for (const n of acme.nodes) labels.set(n.label, (labels.get(n.label) ?? 0) + 1);
    let sum = 0;
    for (const [label, count] of labels) {
      const row = screen.getByTestId(`label-row-${label}`);
      expect(within(row).getByText(String(count), { selector: 'td' })).toBeInTheDocument();
      sum += count;
    }
    expect(sum).toBe(acme.nodes.length);
    const types = new Map<string, number>();
    for (const e of acme.edges) types.set(e.type, (types.get(e.type) ?? 0) + 1);
    let edgeSum = 0;
    for (const [type, count] of types) {
      const row = screen.getByTestId(`edge-row-${type}`);
      expect(within(row).getByText(String(count), { selector: 'td' })).toBeInTheDocument();
      edgeSum += count;
    }
    expect(edgeSum).toBe(acme.edges.length);
  });

  it('lists sample nodes per label and the model indexes', async () => {
    renderApp('/inventory');
    const card = await screen.findByTestId('sample-Agent');
    await waitFor(() => expect(within(card).getByText('planner')).toBeInTheDocument());
    expect(within(card).getByText('researcher')).toBeInTheDocument();
    expect(within(screen.getByTestId('sample-Task')).getAllByRole('listitem').length).toBeGreaterThanOrEqual(
      3,
    );
    const vector = screen.getByTestId('indexes-vector');
    expect(within(vector).getByText('Fact.embedding')).toBeInTheDocument();
    expect(within(screen.getByTestId('indexes-unique')).getAllByRole('listitem')).toHaveLength(5);
  });
});
