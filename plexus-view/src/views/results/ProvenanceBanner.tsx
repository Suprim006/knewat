import type { Provenance } from '../../lib/provenance';

/** Which build the shown numbers come from; which of them are current is tracked in docs/NUMBERS_STATUS.md. */
export function ProvenanceBanner({ p }: { p: Provenance }) {
  return (
    <p className="provenance" data-testid="provenance" role="note">
      Measured on build <code>{p.build}</code>
      {p.dirty && ' (dirty tree)'} ({p.date || 'date unknown'}). Which numbers are current:{' '}
      <code>docs/NUMBERS_STATUS.md</code>
    </p>
  );
}
