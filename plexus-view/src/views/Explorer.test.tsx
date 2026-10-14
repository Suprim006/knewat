import { act, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { acme, renderApp } from '../test/render';

const total = acme.nodes.length;
const toolCalls = acme.nodes.filter((n) => n.label === 'ToolCall').length;
const countOf = (label: string) => acme.nodes.filter((n) => n.label === label).length;

/** Parses "Showing X of N nodes · Y of M edges". */
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

afterEach(() => vi.useRealTimers());

describe('Explorer', () => {
  it('renders the fixture graph with ToolCall nodes hidden by default', async () => {
    renderApp('/');
    const c = await loaded();
    expect(c.totalNodes).toBe(total);
    expect(c.totalEdges).toBe(acme.edges.length);
    expect(c.nodes).toBe(total - toolCalls);
    expect(c.edges).toBeLessThan(c.totalEdges);
    expect(screen.getByRole('checkbox', { name: /^ToolCall/ })).not.toBeChecked();
    const fact = screen.getByRole('checkbox', { name: /^Fact/ });
    expect(fact).toBeChecked();
    // the legend shows per-label counts
    expect(within(fact.closest('label')!).getByText(String(countOf('Fact')))).toBeInTheDocument();
  });

  it('label filters reduce the visible nodes and edges', async () => {
    const user = userEvent.setup();
    renderApp('/');
    const before = await loaded();
    await user.click(screen.getByRole('checkbox', { name: /^Fact/ }));
    const noFacts = counts();
    expect(noFacts.nodes).toBe(before.nodes - countOf('Fact'));
    expect(noFacts.edges).toBeLessThan(before.edges);
    expect(noFacts.totalNodes).toBe(before.totalNodes);
    await user.click(screen.getByRole('checkbox', { name: /^Fact/ }));
    expect(counts()).toEqual(before);
    await user.click(screen.getByRole('checkbox', { name: /^ToolCall/ }));
    expect(counts().nodes).toBe(total);
  });

  it('edge-type filters reduce the visible edges but not the nodes', async () => {
    const user = userEvent.setup();
    renderApp('/');
    const before = await loaded();
    await user.click(screen.getByRole('checkbox', { name: /^DERIVED_FROM/ }));
    const after = counts();
    expect(after.nodes).toBe(before.nodes);
    expect(after.edges).toBe(before.edges - acme.edges.filter((e) => e.type === 'DERIVED_FROM').length);
  });

  it('search lists matches; picking one opens the side panel with properties and neighbours', async () => {
    const user = userEvent.setup();
    renderApp('/');
    await loaded();
    expect(screen.getByText(/Click a node/)).toBeInTheDocument();
    await user.type(screen.getByRole('searchbox', { name: /search nodes/i }), 'Authenticate with JWT');
    const result = await screen.findByRole('button', { name: /Authenticate with JWT bearer tokens/ });
    await user.click(result);
    const panel = screen.getByRole('complementary', { name: 'Node details' });
    expect(within(panel).getByRole('heading', { level: 2 })).toHaveTextContent(
      'Authenticate with JWT bearer tokens',
    );
    expect(within(panel).getByText('Decision')).toBeInTheDocument();
    expect(within(panel).getByText(/BASED_ON/)).toBeInTheDocument();
    // follow a neighbour
    await user.click(within(panel).getByRole('button', { name: /scheme: JWT/ }));
    const next = screen.getByRole('complementary', { name: 'Node details' });
    expect(within(next).getByRole('heading', { level: 2 })).toHaveTextContent('scheme: JWT');
    await user.click(screen.getByRole('button', { name: 'Close details' }));
    expect(screen.getByText(/Click a node/)).toBeInTheDocument();
  });

  it('switching tenant reloads the graph', async () => {
    const user = userEvent.setup();
    renderApp('/');
    await loaded();
    await user.selectOptions(await screen.findByRole('combobox', { name: 'Tenant' }), 'scratch');
    await waitFor(() => expect(counts().totalNodes).toBe(0));
    expect(await screen.findByText(/no data yet/i)).toBeInTheDocument();
  });

  it('adds nodes live (replay of the last events) without removing existing ones', async () => {
    const user = userEvent.setup({ advanceTimers: (ms) => vi.advanceTimersByTime(ms) });
    renderApp('/');
    await loaded();
    vi.useFakeTimers({ shouldAdvanceTime: true });
    await user.click(screen.getByRole('checkbox', { name: /^ToolCall/ })); // show tool calls so each event adds a visible node
    const full = counts().nodes;
    await user.click(screen.getByRole('button', { name: /Replay last events/ }));
    await waitFor(() => expect(counts().totalNodes).toBeLessThan(total));
    expect(counts().totalNodes).toBeGreaterThan(total - 60);
    for (let i = 0; i < 30; i++) await act(() => vi.advanceTimersByTimeAsync(700));
    await waitFor(() => expect(counts().nodes).toBe(full));
    expect(counts().totalNodes).toBe(total);
    expect(screen.queryByRole('button', { name: /Stop replay/ })).not.toBeInTheDocument();
  });
});
