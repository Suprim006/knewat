import { screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it } from 'vitest';
import { createFixtureApi } from '../fixtures/client';
import { layoutWhy, pathTo } from '../lib/whyLayout';
import { acme, renderApp } from '../test/render';

const x = (el: Element) => Number(/translate\(([\d.]+)/.exec(el.getAttribute('transform') ?? '')?.[1]);

describe('Why page', () => {
  it('renders the provenance path of a decision as a left-to-right layered graph', async () => {
    renderApp(`/why/${acme.ids['d.jwt']}`);
    const graph = await screen.findByTestId('why-graph');
    const decision = within(graph).getByTestId('why-node-Decision');
    expect(decision).toHaveAttribute('data-id', acme.ids['d.jwt']);
    const facts = within(graph).getAllByTestId('why-node-Fact');
    const sources = within(graph).getAllByTestId('why-node-Source');
    const agents = within(graph).getAllByTestId('why-node-Agent');
    expect(facts.length).toBeGreaterThanOrEqual(1);
    expect(sources.length).toBeGreaterThanOrEqual(1);
    expect(agents.length).toBeGreaterThanOrEqual(1);
    // columns: decision (root) < facts < sources/agents
    const jwt = facts.find((f) => f.getAttribute('data-id') === acme.ids['f.jwt'])!;
    expect(x(decision)).toBeLessThan(x(jwt));
    expect(x(jwt)).toBeLessThan(x(sources[0]!));
    expect(x(jwt)).toBeLessThan(x(agents.find((a) => a.getAttribute('data-id') === 'researcher')!));
    // edges carry their relationship names
    expect(graph.querySelector('[data-edge$="|' + acme.ids['f.jwt'] + '"]')).not.toBeNull();
    expect(within(graph).getAllByText('BASED_ON').length).toBeGreaterThan(0);
    // the facts it rests on are listed
    expect(within(screen.getByTestId('why-facts')).getByText(/scheme: JWT/)).toBeInTheDocument();
    expect(screen.getByTestId('why-summary')).toHaveTextContent('facts');
  });

  it('lights up the path to a node when it is clicked', async () => {
    const user = userEvent.setup();
    renderApp(`/why/${acme.ids['d.jwt']}`);
    const graph = await screen.findByTestId('why-graph');
    expect(graph.querySelectorAll('[data-on]').length).toBe(0);
    await user.click(within(graph).getAllByTestId('why-node-Source')[0]!);
    const lit = graph.querySelectorAll('g.why-node[data-on]');
    const litLabels = [...lit].map((n) => n.getAttribute('data-testid'));
    expect(litLabels).toContain('why-node-Decision');
    expect(litLabels).toContain('why-node-Fact');
    expect(litLabels).toContain('why-node-Source');
    expect(graph.querySelectorAll('g[data-edge][data-on]').length).toBeGreaterThanOrEqual(2);
    expect(screen.getByText('Selected node')).toBeInTheDocument();
  });

  it('explains the newest decision for /why/latest and lists decisions and facts to pick from', async () => {
    renderApp('/why/latest');
    const graph = await screen.findByTestId('why-graph');
    expect(within(graph).getByTestId('why-node-Decision')).toBeInTheDocument();
    const picker = screen.getByRole('combobox', { name: /Decision or fact to explain/ });
    expect(within(picker).getAllByRole('option').length).toBeGreaterThan(10);
  });

  it('can start from a fact', async () => {
    renderApp(`/why/${acme.ids['f.v2']}`);
    const graph = await screen.findByTestId('why-graph');
    const ids = within(graph)
      .getAllByTestId('why-node-Fact')
      .map((n) => n.getAttribute('data-id'));
    expect(ids).toContain(acme.ids['f.v2']);
    expect(ids).toContain(acme.ids['f.v1']);
    expect(within(graph).getAllByText('SUPERSEDES').length).toBeGreaterThan(0);
  });

  it('says so when the id is unknown, and when a tenant has nothing yet', async () => {
    renderApp('/why/no-such-id');
    expect(await screen.findByRole('alert')).toHaveTextContent('No Decision or Fact with this id');
  });

  it('shows an empty state for a tenant without decisions', async () => {
    const user = userEvent.setup();
    renderApp('/why/latest');
    await screen.findByTestId('why-graph');
    await user.selectOptions(screen.getByRole('combobox', { name: 'Tenant' }), 'scratch');
    await waitFor(() =>
      expect(screen.getByText(/No decisions or facts in this tenant yet/)).toBeInTheDocument(),
    );
  });
});

describe('layoutWhy', () => {
  it('puts every node in the column of its shortest hop distance and keeps edges between placed nodes', async () => {
    const api = createFixtureApi(acme);
    const { result } = await api.why('acme', acme.ids['d.jwt']!);
    const layout = layoutWhy(result);
    const col = new Map(layout.nodes.map((n) => [n.id, n.depth]));
    expect(col.get(result.root)).toBe(0);
    for (const path of result.paths) path.forEach((h, i) => expect(col.get(h.to)).toBeLessThanOrEqual(i + 1));
    const ids = new Set(layout.nodes.map((n) => n.id));
    expect(layout.nodes).toHaveLength(result.nodes.length);
    expect(layout.edges.every((e) => ids.has(e.from) && ids.has(e.to))).toBe(true);
    // no two nodes overlap
    const seen = new Set(layout.nodes.map((n) => `${n.x},${n.y}`));
    expect(seen.size).toBe(layout.nodes.length);
    const hit = pathTo(result, result.sources[0]!);
    expect(hit.nodes.has(result.root)).toBe(true);
    expect(hit.edges.size).toBeGreaterThanOrEqual(2);
  });
});
