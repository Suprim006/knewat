import { useCallback, useEffect, useMemo, useState } from 'react';
import { Link, useSearchParams } from 'react-router-dom';
import type { StepAgent, StepFact, StepWrote } from '../api';
import { useApi, useTenant } from '../app/context';
import { agentColor, formatClock } from '../lib/flow';
import { labelColor } from '../lib/labels';
import { agentIdsOf, diffAgent, isEmptyDiff } from '../lib/timeMachine';
import type { KnowledgeDiff } from '../lib/timeMachine';
import { useAsync } from '../lib/useAsync';
import { useFlowFeed } from '../lib/useFlowFeed';

const PLAY_MS = 900;
const DEBOUNCE_MS = 120;

const factText = (f: StepFact) => `${f.entity ?? '?'} · ${f.predicate ?? '?'} = ${f.value ?? '?'}`;

function FactRow({ fact, kind }: { fact: StepFact; kind?: 'new' }) {
  return (
    <li className={kind ? `diff-${kind}` : undefined} data-diff={kind}>
      <span className="dot" style={{ background: labelColor('Fact') }} />
      {factText(fact)}
      {fact.status && fact.status !== 'active' && <span className="muted"> ({fact.status})</span>}{' '}
      <Link to={`/why/${encodeURIComponent(fact.id)}`}>Why?</Link>
    </li>
  );
}

function WroteRow({ w, isNew }: { w: StepWrote; isNew: boolean }) {
  return (
    <li className={isNew ? 'diff-new' : undefined} data-diff={isNew ? 'new' : undefined}>
      <span className="dot" style={{ background: labelColor(w.label) }} />
      <b>{w.label}</b> {w.summary}
      {w.step_n != null && <span className="muted"> · step {w.step_n}</span>}{' '}
      {(w.label === 'Decision' || w.label === 'Fact') && (
        <Link to={`/why/${encodeURIComponent(w.id)}`}>Why?</Link>
      )}
    </li>
  );
}

function AgentCard({ id, agent, diff }: { id: string; agent: StepAgent | undefined; diff: KnowledgeDiff }) {
  const newIds = new Set(diff.added.concat(diff.changed.map((c) => c.to)).map((f) => f.id));
  const newWrites = new Set(diff.newWrites.map((w) => w.id));
  return (
    <article
      className="card agent-card"
      style={{ borderTopColor: agentColor(id) }}
      data-testid={`agent-${id}`}
      aria-label={`What ${id} knew`}
    >
      <header>
        <strong style={{ color: agentColor(id) }}>{id}</strong>
        {agent ? (
          <span className="muted">
            its step {agent.step_n} · {formatClock(agent.step_at)}
          </span>
        ) : (
          <span className="muted">no steps yet</span>
        )}
      </header>
      {agent && (
        <div className="know-cols">
          <div>
            <h4>Knew ({agent.read.length})</h4>
            <ul>
              {agent.read.map((f) => (
                <FactRow key={f.id} fact={f} kind={newIds.has(f.id) ? 'new' : undefined} />
              ))}
              {agent.read.length === 0 && <li className="muted">nothing read yet</li>}
            </ul>
          </div>
          <div>
            <h4>Wrote ({agent.wrote.length})</h4>
            <ul>
              {agent.wrote.map((w) => (
                <WroteRow key={w.id} w={w} isNew={newWrites.has(w.id)} />
              ))}
              {agent.wrote.length === 0 && <li className="muted">nothing written yet</li>}
            </ul>
          </div>
        </div>
      )}
      {!isEmptyDiff(diff) && (
        <div className="diff-box" data-testid={`diff-${id}`}>
          <h4>Since the previous step</h4>
          <ul>
            {diff.changed.map((c) => (
              <li key={c.to.id} className="diff-changed" data-diff="changed">
                <b>{c.to.predicate}</b> changed: <del>{c.from.value}</del> → <ins>{c.to.value}</ins>{' '}
                <span className="muted">({c.to.entity})</span>
              </li>
            ))}
            {diff.added.map((f) => (
              <li key={f.id} className="diff-new" data-diff="new">
                learned {factText(f)}
              </li>
            ))}
            {diff.removed.map((f) => (
              <li key={f.id} className="diff-gone" data-diff="gone">
                no longer valid: {factText(f)}
              </li>
            ))}
            {diff.newWrites.map((w) => (
              <li key={w.id} className="diff-new" data-diff="new">
                wrote {w.label} {w.summary}
              </li>
            ))}
          </ul>
        </div>
      )}
    </article>
  );
}

/** The latest defined value for this key (render-phase state, no effect). */
function useKept<T>(value: T | undefined, key: string): T | undefined {
  const [kept, setKept] = useState<{ key: string; value: T | undefined }>({ key, value });
  if (kept.key !== key) setKept({ key, value });
  else if (value !== undefined && value !== kept.value) setKept({ key, value });
  return kept.key === key ? kept.value : value;
}

export function TimeMachine() {
  const api = useApi();
  const { tenant } = useTenant();
  const feed = useFlowFeed(api, tenant);
  const [params, setParams] = useSearchParams();
  const maxStep = useMemo(() => feed.events.reduce((m, e) => Math.max(m, e.step_n ?? 0), 0), [feed.events]);
  const asked = Number(params.get('step'));
  const wanted = Number.isFinite(asked) && asked > 0 ? asked : maxStep;
  const step = Math.max(1, Math.min(wanted, maxStep || 1));
  const [playing, setPlaying] = useState(false);

  const setStep = useCallback((n: number) => setParams({ step: String(n) }, { replace: true }), [setParams]);

  /*
   * Debounce the fetch while the slider is dragged. Until the first debounce has fired (it waits for
   * the step range to load) the live step is used as is, so the first view never flashes step 1.
   */
  const [committed, setCommitted] = useState<number | null>(null);
  useEffect(() => {
    if (maxStep === 0) return;
    const t = setTimeout(() => setCommitted(step), DEBOUNCE_MS);
    return () => clearTimeout(t);
  }, [step, maxStep]);
  const at = committed ?? step;

  /* play: advance one step at a time, stop at the end */
  const isPlaying = playing && step < maxStep;
  useEffect(() => {
    if (!isPlaying) return;
    const t = setTimeout(() => setStep(step + 1), PLAY_MS);
    return () => clearTimeout(t);
  }, [isPlaying, step, setStep]);

  const loadNow = useCallback(
    () => (tenant && maxStep > 0 ? api.step(tenant, at) : Promise.resolve(undefined)),
    [api, tenant, at, maxStep],
  );
  const loadPrev = useCallback(
    () => (tenant && maxStep > 0 ? api.step(tenant, at - 1) : Promise.resolve(undefined)),
    [api, tenant, at, maxStep],
  );
  const now = useAsync(loadNow);
  const prev = useAsync(loadPrev);
  // Keep showing the last answer while the next step loads, so dragging the slider doesn't flash empty.
  const nowData = useKept(now.data, tenant);
  const prevData = useKept(prev.data, tenant);

  const agents = nowData ? agentIdsOf(nowData, prevData) : [];
  const pending = at !== step || now.loading || prev.loading;
  const latestAt = nowData?.agents.reduce((m, a) => Math.max(m, a.step_at), 0) ?? 0;

  return (
    <section className="page time-machine" aria-labelledby="tm-h">
      <h1 id="tm-h">Time Machine</h1>
      <p className="muted">
        Drag to any step: what each agent <b>knew</b> (facts it had read that were still valid then) and what
        it <b>wrote</b>. Step numbers count per agent, so “step 4” is each agent’s fourth call.
      </p>

      {feed.error && (
        <div className="banner error" role="alert">
          Could not load the step range: {feed.error}
        </div>
      )}
      {feed.loaded && maxStep === 0 && !feed.error && (
        <p className="muted">
          No agent steps yet. Steps appear once agents call the MCP tools (each call is a Lineage{' '}
          <code>Step</code>).
        </p>
      )}

      {maxStep > 0 && (
        <div className="slider-row">
          <button
            type="button"
            className="btn small"
            onClick={() => {
              if (!isPlaying && step >= maxStep) setStep(1);
              setPlaying(!isPlaying);
            }}
          >
            {isPlaying ? '⏸ Pause' : '▶ Play'}
          </button>
          <label className="slider">
            <span>Step</span>
            <input
              type="range"
              aria-label="Step"
              min={1}
              max={maxStep}
              value={step}
              onChange={(e) => {
                setPlaying(false);
                setStep(Number(e.target.value));
              }}
            />
            <output data-testid="step-value">
              {step} / {maxStep}
            </output>
          </label>
          {latestAt > 0 && <span className="muted mono">{formatClock(latestAt)}</span>}
        </div>
      )}

      {now.error && (
        <div className="banner error" role="alert">
          Could not load step {at}: {now.error.message}
        </div>
      )}
      <div className={`agent-grid${pending ? ' pending' : ''}`} data-testid="agent-grid" aria-busy={pending}>
        {agents.map((id) => {
          const a = nowData?.agents.find((x) => x.agent_id === id);
          const p = prevData?.agents.find((x) => x.agent_id === id);
          return <AgentCard key={id} id={id} agent={a} diff={diffAgent(p, a)} />;
        })}
      </div>
    </section>
  );
}
