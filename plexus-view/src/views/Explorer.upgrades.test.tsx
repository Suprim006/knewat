import { fireEvent, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it } from 'vitest';
import { edgeId } from '../api/types';
import { ABLATED_EDGE_TYPES } from '../lib/ablation';
import { DEFAULT_HIDDEN_EDGE_TYPES, DEFAULT_HIDDEN_LABELS } from '../lib/labels';
import { acme, renderApp } from '../test/render';

function counts() {
  const t = screen.getByTestId('visible-counts').textContent ?? '';
  const m = /Showing (\d+) of (\d+) nodes · (\d+) of (\d+) edges/.exec(t);
  if (!m) throw new Error(`unexpected counts text: ${t}`);
  return { nodes: +m[1]!, totalNodes: +m[2]!, edges: +m[3]!, totalEdges: +m[4]! };
}
async function loaded() {
  await waitFor(() => expect(counts().totalNodes).toBeGreaterThan(0), { timeout: 5000 });
  return counts();
}

describe('Explorer: ablation toggle', () => {
  it('hides DEPENDS_ON, BASED_ON, DERIVED_FROM and READ edges and lists what stops working', async () => {
    const user = userEvent.setup();
    renderApp('/');
    const before = await loaded();
    expect(screen.queryByTestId('ablation-panel')).not.toBeInTheDocument();

    // what the toggle should remove: edges of those types that are currently visible
    const label = new Map(acme.nodes.map((n) => [n.id, n.label]));
    const seen = new Set<string>();
    const removed = acme.edges.filter((e) => {
      const key = edgeId(e);
      if (!ABLATED_EDGE_TYPES.includes(e.type) || DEFAULT_HIDDEN_EDGE_TYPES.includes(e.type) || seen.has(key))
        return false;
      seen.add(key);
      return ![e.source, e.target].some((id) => DEFAULT_HIDDEN_LABELS.includes(label.get(id)!));
    }).length;
    expect(removed).toBeGreaterThan(10);

    await user.click(screen.getByRole('checkbox', { name: /Ablation/ }));
    const after = counts();
    expect(after.nodes).toBe(before.nodes);
    expect(after.edges).toBe(before.edges - removed);

    const panel = screen.getByTestId('ablation-panel');
    for (const f of ['claim_next_task', 'why(decision)', 'forget_source', 'knew_at'])
      expect(within(panel).getByText(new RegExp(f.replace(/[()]/g, '\\$&')))).toBeInTheDocument();
    expect(within(panel).getByRole('link', { name: /measured ablation results/ })).toHaveAttribute(
      'href',
      '/results#ablation',
    );
    for (const t of ABLATED_EDGE_TYPES) {
      const box = screen.getByRole('checkbox', { name: new RegExp(`^${t}`) });
      expect(box).not.toBeChecked();
      expect(box).toBeDisabled();
    }

    await user.click(screen.getByRole('checkbox', { name: /Ablation/ }));
    expect(counts()).toEqual(before);
    expect(screen.queryByTestId('ablation-panel')).not.toBeInTheDocument();
    expect(screen.getByRole('checkbox', { name: /^BASED_ON/ })).toBeChecked();
  });

  it('keeps the user’s own edge filters when the ablation is switched off', async () => {
    const user = userEvent.setup();
    renderApp('/');
    const before = await loaded();
    await user.click(screen.getByRole('checkbox', { name: /^BASED_ON/ }));
    const manual = counts();
    expect(manual.edges).toBeLessThan(before.edges);
    await user.click(screen.getByRole('checkbox', { name: /Ablation/ }));
    await user.click(screen.getByRole('checkbox', { name: /Ablation/ }));
    expect(counts()).toEqual(manual);
    expect(screen.getByRole('checkbox', { name: /^BASED_ON/ })).not.toBeChecked();
  });
});

describe('Explorer: colour, time range, focus, why', () => {
  it('switches the legend to module colours', async () => {
    const user = userEvent.setup();
    renderApp('/');
    await loaded();
    expect(screen.queryByTestId('module-legend')).not.toBeInTheDocument();
    await user.selectOptions(screen.getByRole('combobox', { name: 'Colour by' }), 'module');
    const legend = screen.getByTestId('module-legend');
    for (const m of ['Engram', 'Relay', 'Lineage', 'Audit'])
      expect(within(legend).getByText(m)).toBeInTheDocument();
  });

  it('filters nodes by a created-at time range', async () => {
    renderApp('/');
    const before = await loaded();
    const from = screen.getByRole('slider', { name: 'Time range from' });
    const max = Number(from.getAttribute('max'));
    const min = Number(from.getAttribute('min'));
    fireEvent.change(from, { target: { value: String(Math.floor((min + max) / 2)) } });
    const cut = counts();
    expect(cut.nodes).toBeLessThan(before.nodes);
    expect(cut.totalNodes).toBe(before.totalNodes);
    fireEvent.click(screen.getByRole('button', { name: 'reset' }));
    expect(counts()).toEqual(before);
  });

  it('focuses the 2-hop neighbourhood of a node and shows everything again', async () => {
    const user = userEvent.setup();
    renderApp('/');
    const before = await loaded();
    await user.type(screen.getByRole('searchbox', { name: /search nodes/i }), 'Authenticate with JWT');
    await user.click(await screen.findByRole('button', { name: /Authenticate with JWT bearer tokens/ }));
    const panel = screen.getByRole('complementary', { name: 'Node details' });
    await user.click(within(panel).getByRole('button', { name: /Focus neighbourhood/ }));
    const focused = counts();
    expect(focused.nodes).toBeGreaterThan(2);
    expect(focused.nodes).toBeLessThan(before.nodes);
    expect(screen.getByTestId('focus-banner')).toHaveTextContent('Authenticate with JWT');
    await user.click(within(screen.getByTestId('focus-banner')).getByRole('button', { name: 'Show all' }));
    expect(counts()).toEqual(before);
    expect(screen.queryByTestId('focus-banner')).not.toBeInTheDocument();
  });

  it('offers “Why?” on decisions and facts only', async () => {
    const user = userEvent.setup();
    renderApp('/');
    await loaded();
    const search = screen.getByRole('searchbox', { name: /search nodes/i });
    await user.type(search, 'Authenticate with JWT');
    await user.click(await screen.findByRole('button', { name: /Authenticate with JWT bearer tokens/ }));
    const why = within(screen.getByRole('complementary', { name: 'Node details' })).getByRole('link', {
      name: 'Why?',
    });
    expect(why).toHaveAttribute('href', `/why/${acme.ids['d.jwt']}`);

    await user.clear(search);
    await user.type(search, 'Acme Notes API');
    const hits = await screen.findAllByRole('button', { name: /Acme Notes API/ });
    await user.click(hits.find((b) => b.textContent?.includes('Entity'))!);
    expect(
      within(screen.getByRole('complementary', { name: 'Node details' })).queryByRole('link', {
        name: 'Why?',
      }),
    ).not.toBeInTheDocument();
  });
});
