import { useMemo } from 'react';
import { tokenizeCypher } from '../lib/cypher';

/** A `.cypher` file, syntax-highlighted. Colours come from `.cy-*` classes in styles.css. */
export function CypherView({ text, label }: { text: string; label?: string }) {
  const tokens = useMemo(() => tokenizeCypher(text), [text]);
  return (
    <pre className="cypher" aria-label={label ?? 'Cypher'} data-testid="cypher-text">
      <code>
        {tokens.map((t, i) =>
          t.type === 'text' ? (
            t.text
          ) : (
            <span key={i} className={`cy-${t.type}`}>
              {t.text}
            </span>
          ),
        )}
      </code>
    </pre>
  );
}
