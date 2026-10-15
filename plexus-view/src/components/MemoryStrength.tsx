import { useCallback } from 'react';
import { Link } from 'react-router-dom';
import type { VerifyRow } from '../api';
import { useApi, useTenant } from '../app/context';
import { formatProp } from '../lib/labels';
import type { Props } from '../api';
import { factMemory, hasMemoryData, strengthCounts } from '../lib/memory';
import { useAsync } from '../lib/useAsync';

const fmt = (v: number | null | undefined, digits = 2): string =>
  typeof v === 'number' && Number.isFinite(v) ? v.toFixed(digits) : '—';

/** Short form of a `decision:<uuid>` style protection reason. */
const shortReason = (r: string): string => {
  const [kind, id] = r.split(':');
  return id ? `${kind} ${id.slice(0, 8)}` : r;
};

interface SectionProps {
  factId: string;
  props: Props;
}

/**
 * The node panel's "Memory strength" section for a Fact: activation, protection, surprise, the events behind
 * the activation (`/memory-strength/{id}`) and the verify state with the change that made it suspect
 * (`/verify-queue`). Read-only; the viewer never writes.
 */
export function MemoryStrengthSection({ factId, props }: SectionProps) {
  const api = useApi();
  const { tenant } = useTenant();
  const present = hasMemoryData(props);
  const mem = factMemory(props, Date.now());

  const loadStrength = useCallback(
    () => (present && tenant ? api.memoryStrength(tenant, factId) : Promise.resolve(undefined)),
    [api, tenant, factId, present],
  );
  const loadQueue = useCallback(
    () => (mem.suspect && tenant ? api.verifyQueue(tenant, { limit: 200 }) : Promise.resolve(undefined)),
    [api, tenant, mem.suspect],
  );
  const strength = useAsync(loadStrength);
  const queue = useAsync(loadQueue);
  const row: VerifyRow | undefined = queue.data?.rows.find((r) => r.fact_id === factId);

  if (!present) {
    return (
      <section aria-labelledby="ms-h" className="memory-strength">
        <h3 id="ms-h">Memory strength</h3>
        <p className="muted">
          No memory-strength data for this fact (this tenant has no staleness or forgetting fields yet).
        </p>
      </section>
    );
  }

  const s = strength.data;
  const activation = s ? s.activation : mem.activation;
  const isProtected = s ? s.protected : mem.protected;
  const reasons = s?.protect_reasons ?? [];
  const verifyState = s?.verify_state ?? String(props.verify_state ?? 'verified');
  const since = s?.suspect_since ?? Number(props.suspect_since ?? 0);
  const change = row?.change;

  return (
    <section aria-labelledby="ms-h" className="memory-strength">
      <h3 id="ms-h">Memory strength</h3>
      <dl className="props strength">
        <div className="prop-row">
          <dt>activation</dt>
          <dd data-testid="strength-activation">
            {fmt(activation)}
            {s && (
              <span className="muted">
                {' '}
                (neutral {fmt(s.a0)}, rank ×{fmt(s.multiplier)})
              </span>
            )}
          </dd>
        </div>
        <div className="prop-row">
          <dt>protected</dt>
          <dd data-testid="strength-protected">
            {isProtected ? 'protected' : 'not protected'}
            {reasons.length > 0 && <span className="muted"> · {reasons.map(shortReason).join(', ')}</span>}
          </dd>
        </div>
        <div className="prop-row">
          <dt>surprise</dt>
          <dd data-testid="strength-surprise">{fmt(s?.surprise ?? mem.surprise)}</dd>
        </div>
        {s && (
          <div className="prop-row">
            <dt>events</dt>
            <dd data-testid="strength-events">
              {strengthCounts(s.counts)}
              {s.last_use ? <span className="muted"> · last use {formatProp('at', s.last_use)}</span> : null}
              {s.last_recall ? (
                <span className="muted"> · last recall {formatProp('at', s.last_recall)}</span>
              ) : null}
            </dd>
          </div>
        )}
        <div className="prop-row">
          <dt>verify</dt>
          <dd data-testid="strength-verify">
            {mem.suspect ? 'suspect' : verifyState}
            {mem.suspect && since > 0 && <span> since {formatProp('suspect_since', since)}</span>}
            {mem.suspect && (
              <span className="muted"> · {row?.reason ?? mem.reason}</span>
            )}
            {change && (
              <span className="muted">
                {' '}
                · commit <code>{change.commit || 'working tree'}</code>
                {change.paths.length > 0 && <> · {change.paths.join(', ')}</>}
              </span>
            )}
          </dd>
        </div>
      </dl>
      {s && <p className="muted strength-explain">{s.explanation}</p>}
      {s && !s.forgetting && (
        <p className="muted">Forgetting is off on this server: recall ignores activation.</p>
      )}
      {strength.error && (
        <p className="muted" role="note">
          Strength details unavailable ({strength.error.message}); showing what the graph carries.
        </p>
      )}
      {mem.suspect && (
        <Link className="btn small" to={`/verify?fact=${encodeURIComponent(factId)}`}>
          Needs verification
        </Link>
      )}
    </section>
  );
}
