import { screen, waitFor, within } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import { buildAcme } from '../fixtures/acme';
import { createFixtureApi } from '../fixtures/client';
import { applyP7 } from '../fixtures/p7';
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
    expect(within(screen.getByTestId('indexes-fulltext')).getByText('Entity.name')).toBeInTheDocument();
  });
});

describe('Inventory: staleness and forgetting counts', () => {
  const p7 = applyP7(buildAcme());
  const facts = p7.nodes.filter((n) => n.label === 'Fact');

  it('shows suspect, dormant, pinned, changes and code anchors', async () => {
    renderApp('/inventory', createFixtureApi(p7));
    const section = await screen.findByRole('region', { name: 'Staleness and forgetting' });
    const inv = await createFixtureApi(p7).inventory('acme');
    expect(inv.suspect_facts).toBeGreaterThanOrEqual(5);
    const value = (k: string) => within(within(section).getByTestId(`memory-${k}`)).getByTestId('stat-n');
    expect(value('suspect_facts')).toHaveTextContent(String(inv.suspect_facts));
    expect(value('dormant_facts')).toHaveTextContent(
      String(facts.filter((f) => f.props.status === 'dormant').length),
    );
    expect(value('pinned_facts')).toHaveTextContent(
      String(facts.filter((f) => f.props.pinned === true).length),
    );
    expect(value('changes')).toHaveTextContent('2');
    expect(value('code_anchors')).toHaveTextContent('3');
    expect(within(section).getByRole('link', { name: /verify/i })).toHaveAttribute('href', '/verify');
    // the new labels appear in the per-label table and as sample cards
    expect(screen.getByTestId('label-row-Change')).toBeInTheDocument();
    expect(screen.getByTestId('label-row-CodeAnchor')).toBeInTheDocument();
    expect(screen.getByTestId('edge-row-SUSPECTED')).toBeInTheDocument();
  });

  it('says there is no data yet for a tenant that has none, and for a server without the fields', async () => {
    const base = createFixtureApi(buildAcme());
    renderApp('/inventory', {
      ...base,
      inventory: async (t) => {
        const inv = await base.inventory(t);
        return {
          tenant: inv.tenant,
          nodes_total: inv.nodes_total,
          edges_total: inv.edges_total,
          labels: inv.labels,
          edge_types: inv.edge_types,
          indexes: inv.indexes,
        };
      },
    });
    const section = await screen.findByRole('region', { name: 'Staleness and forgetting' });
    expect(within(section).getByText(/no staleness or forgetting data yet/i)).toBeInTheDocument();
    expect(within(section).queryByTestId('memory-suspect_facts')).not.toBeInTheDocument();
  });
});
