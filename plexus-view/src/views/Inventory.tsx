import { useCallback } from 'react';
import type { GraphNode, Inventory as InventoryData } from '../api';
import { useApi, useTenant } from '../app/context';
import { LABEL_MODULES, MODULE_ORDER, displayName, labelColor } from '../lib/labels';
import { SUMMARY_LABELS, summarize } from '../lib/summary';
import { useAsync } from '../lib/useAsync';

const SAMPLES_PER_LABEL = 3;

function Bar({ value, max, color }: { value: number; max: number; color: string }) {
  const pct = max > 0 ? Math.max(2, Math.round((value / max) * 100)) : 0;
  return (
    <div className="bar" aria-hidden="true">
      <div className="bar-fill" style={{ width: `${pct}%`, background: color }} />
    </div>
  );
}

type IndexKind = 'RANGE' | 'FULLTEXT' | 'VECTOR';
const KIND_ORDER: IndexKind[] = ['RANGE', 'FULLTEXT', 'VECTOR'];
const KIND_NAME: Record<IndexKind, string> = {
  RANGE: 'Range indexes',
  FULLTEXT: 'Full-text indexes',
  VECTOR: 'Vector indexes (384-d, cosine)',
};

/** One row per (label, property, kind): the API groups index kinds by label and property. */
function flattenIndexes(indexes: InventoryData['indexes']) {
  return indexes.flatMap((i) =>
    i.properties.flatMap((property) =>
      (i.types[property] ?? []).map((kind) => ({ label: i.label, property, kind, status: i.status })),
    ),
  );
}

function SummaryCard({
  id,
  title,
  value,
  parts,
}: {
  id: string;
  title: string;
  value: number;
  parts?: [string, number][];
}) {
  return (
    <article className="card summary-card" data-testid={`summary-${id}`}>
      <div className="stat-n">{value}</div>
      <div className="stat-l">{title}</div>
      {parts && (
        <ul className="parts">
          {parts.map(([k, v]) => (
            <li key={k}>
              <b>{v}</b> {k}
            </li>
          ))}
        </ul>
      )}
    </article>
  );
}

export function Inventory() {
  const api = useApi();
  const { tenant } = useTenant();
  const loadInventory = useCallback(
    () => (tenant ? api.inventory(tenant) : Promise.resolve(undefined)),
    [api, tenant],
  );
  const loadSamples = useCallback(
    () => (tenant ? api.graph(tenant, { limit: 2000 }) : Promise.resolve(undefined)),
    [api, tenant],
  );
  const loadSummary = useCallback(
    () => (tenant ? api.graph(tenant, { labels: SUMMARY_LABELS, limit: 2000 }) : Promise.resolve(undefined)),
    [api, tenant],
  );
  const inv = useAsync(loadInventory);
  const summaryGraph = useAsync(loadSummary);
  const graph = useAsync(loadSamples);

  if (inv.error) {
    return (
      <section className="page">
        <h1>Inventory</h1>
        <div className="banner error" role="alert">
          Could not load the inventory: {inv.error.message}
        </div>
      </section>
    );
  }
  const data = inv.data;
  if (inv.loading || !data) {
    return (
      <section className="page">
        <h1>Inventory</h1>
        <p className="muted">{tenant ? 'Loading inventory…' : 'Waiting for tenants…'}</p>
      </section>
    );
  }

  const summary = summarize(data, summaryGraph.data);
  const indexes = flattenIndexes(data.indexes);
  const labels = [...data.labels].sort((a, b) => b.count - a.count || a.label.localeCompare(b.label));
  const edgeTypes = [...data.edge_types].sort((a, b) => b.count - a.count || a.type.localeCompare(b.type));
  const maxLabel = labels[0]?.count ?? 0;
  const maxEdge = edgeTypes[0]?.count ?? 0;

  const samples = new Map<string, GraphNode[]>();
  for (const n of graph.data?.nodes ?? []) {
    const list = samples.get(n.label) ?? [];
    if (list.length < SAMPLES_PER_LABEL) samples.set(n.label, [...list, n]);
  }
  const byModule = MODULE_ORDER.map((m) => ({
    module: m,
    labels: labels.filter((l) => (LABEL_MODULES[l.label] ?? 'Other') === m),
  })).filter((g) => g.labels.length > 0);
  const knownLabels = new Set(byModule.flatMap((g) => g.labels.map((l) => l.label)));
  const otherLabels = labels.filter((l) => !knownLabels.has(l.label));
  if (otherLabels.length > 0) byModule.push({ module: 'Other', labels: otherLabels });

  return (
    <section className="page inventory">
      <h1>
        Inventory <span className="muted">· tenant {data.tenant}</span>
      </h1>
      <div className="stat-row">
        <div className="stat">
          <div className="stat-n" data-testid="inventory-node-total">
            {data.nodes_total}
          </div>
          <div className="stat-l">nodes</div>
        </div>
        <div className="stat">
          <div className="stat-n" data-testid="inventory-edge-total">
            {data.edges_total}
          </div>
          <div className="stat-l">edges</div>
        </div>
        <div className="stat">
          <div className="stat-n">{labels.length}</div>
          <div className="stat-l">labels</div>
        </div>
        <div className="stat">
          <div className="stat-n">{edgeTypes.length}</div>
          <div className="stat-l">edge types</div>
        </div>
        <div className="stat">
          <div className="stat-n">{indexes.length}</div>
          <div className="stat-l">indexes and constraints</div>
        </div>
      </div>

      <h2>What the demo created</h2>
      <div className="cards summary" data-testid="demo-summary">
        <SummaryCard id="agents" title="agents" value={summary.agents} />
        <SummaryCard
          id="tasks"
          title="tasks"
          value={summary.tasks.total}
          parts={[
            ['done', summary.tasks.done],
            ['failed', summary.tasks.failed],
            ['reclaimed', summary.tasks.reclaimed],
          ]}
        />
        <SummaryCard
          id="facts"
          title="facts"
          value={summary.facts.total}
          parts={[
            ['active', summary.facts.active],
            ['superseded', summary.facts.superseded],
            ['contradicting', summary.facts.contradicting],
          ]}
        />
        <SummaryCard id="decisions" title="decisions" value={summary.decisions} />
        <SummaryCard id="handoffs" title="handoffs" value={summary.handoffs} />
        <SummaryCard id="toolcalls" title="tool calls" value={summary.toolCalls} />
      </div>
      {summary.sampled && (
        <p className="muted">Task and fact splits are computed from the newest 2000 nodes only.</p>
      )}

      <div className="two-col">
        <section className="panel" aria-labelledby="inv-labels">
          <h2 id="inv-labels">Nodes per label</h2>
          <table className="bars">
            <tbody>
              {labels.map((l) => (
                <tr key={l.label} data-testid={`label-row-${l.label}`}>
                  <th scope="row">
                    <span className="dot" style={{ background: labelColor(l.label) }} /> {l.label}
                  </th>
                  <td className="bar-cell">
                    <Bar value={l.count} max={maxLabel} color={labelColor(l.label)} />
                  </td>
                  <td className="num">{l.count}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </section>
        <section className="panel" aria-labelledby="inv-edges">
          <h2 id="inv-edges">Edges per type</h2>
          <table className="bars">
            <tbody>
              {edgeTypes.map((e) => (
                <tr key={e.type} data-testid={`edge-row-${e.type}`}>
                  <th scope="row" className="mono">
                    {e.type}
                  </th>
                  <td className="bar-cell">
                    <Bar value={e.count} max={maxEdge} color="var(--accent)" />
                  </td>
                  <td className="num">{e.count}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </section>
      </div>

      <h2>Sample nodes</h2>
      {byModule.map((g) => (
        <div key={g.module}>
          <h3 className="module-h">{g.module}</h3>
          <div className="cards">
            {g.labels.map((l) => (
              <article key={l.label} className="card" data-testid={`sample-${l.label}`}>
                <header>
                  <span className="chip" style={{ background: labelColor(l.label) }}>
                    {l.label}
                  </span>
                  <span className="muted">{l.count}</span>
                </header>
                <ul>
                  {(samples.get(l.label) ?? []).map((n) => (
                    <li key={n.id} title={n.id}>
                      {displayName(n.label, n.props)}
                    </li>
                  ))}
                  {graph.loading && <li className="muted">loading…</li>}
                </ul>
                <div className="keys">
                  {l.keys
                    .filter((k) => k !== 'embedding')
                    .map((k) => (
                      <code key={k}>{k}</code>
                    ))}
                </div>
              </article>
            ))}
          </div>
        </div>
      ))}

      <h2>Indexes</h2>
      <div className="cards">
        {KIND_ORDER.map((kind) => {
          const items = indexes.filter((i) => i.kind === kind);
          if (items.length === 0) return null;
          return (
            <article key={kind} className="card wide" data-testid={`indexes-${kind.toLowerCase()}`}>
              <header>
                <strong>{KIND_NAME[kind]}</strong>
                <span className="muted">{items.length}</span>
              </header>
              <ul className="index-list">
                {items.map((i) => (
                  <li key={`${i.label}.${i.property}`} className="mono">
                    {i.label}.{i.property}
                    {i.status && i.status !== 'OPERATIONAL' && <span className="muted"> ({i.status})</span>}
                  </li>
                ))}
              </ul>
            </article>
          );
        })}
      </div>
    </section>
  );
}
