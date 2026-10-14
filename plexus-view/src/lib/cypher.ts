/** A tiny Cypher tokenizer for syntax highlighting (no dependency; the .cypher files are ours and small). */
export type CypherTokenType =
  'comment' | 'string' | 'keyword' | 'function' | 'param' | 'label' | 'number' | 'text';

export interface CypherToken {
  type: CypherTokenType;
  text: string;
}

const KEYWORDS = new Set(
  [
    'MATCH',
    'OPTIONAL',
    'WHERE',
    'RETURN',
    'WITH',
    'CREATE',
    'MERGE',
    'SET',
    'DELETE',
    'DETACH',
    'REMOVE',
    'UNWIND',
    'FOREACH',
    'CALL',
    'YIELD',
    'ORDER',
    'BY',
    'ASC',
    'DESC',
    'LIMIT',
    'SKIP',
    'AS',
    'AND',
    'OR',
    'NOT',
    'XOR',
    'IN',
    'IS',
    'NULL',
    'TRUE',
    'FALSE',
    'CASE',
    'WHEN',
    'THEN',
    'ELSE',
    'END',
    'DISTINCT',
    'ON',
    'UNION',
    'ALL',
    'STARTS',
    'ENDS',
    'CONTAINS',
    'EXISTS',
  ].map((k) => k.toLowerCase()),
);

// Order matters: comments and strings first so keywords inside them are not coloured.
const TOKEN_RE =
  /(\/\/[^\n]*)|('(?:[^'\\]|\\.)*'|"(?:[^"\\]|\\.)*")|(\$[A-Za-z_][A-Za-z0-9_]*)|(:[A-Za-z_][A-Za-z0-9_]*)|(\b\d+(?:\.\d+)?\b)|([A-Za-z_][A-Za-z0-9_.]*)(\s*\()?/g;

export function tokenizeCypher(src: string): CypherToken[] {
  const out: CypherToken[] = [];
  let last = 0;
  const push = (type: CypherTokenType, text: string) => {
    if (!text) return;
    const prev = out[out.length - 1];
    if (prev && prev.type === type && type === 'text') prev.text += text;
    else out.push({ type, text });
  };
  for (const m of src.matchAll(TOKEN_RE)) {
    push('text', src.slice(last, m.index));
    const [whole, comment, str, param, label, num, word, paren] = m;
    if (comment) push('comment', comment);
    else if (str) push('string', str);
    else if (param) push('param', param);
    else if (label) push('label', label);
    else if (num) push('number', num);
    else if (word) {
      if (paren) {
        push(KEYWORDS.has(word.toLowerCase()) ? 'keyword' : 'function', word);
        push('text', paren);
      } else push(KEYWORDS.has(word.toLowerCase()) ? 'keyword' : 'text', word);
    } else push('text', whole);
    last = m.index + whole.length;
  }
  push('text', src.slice(last));
  return out;
}
