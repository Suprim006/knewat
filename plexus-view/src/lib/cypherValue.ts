import type { CypherValue } from '../api/types';

type Obj = { [key: string]: CypherValue };

const isObj = (v: CypherValue): v is Obj => typeof v === 'object' && v !== null && !Array.isArray(v);

export type ValueKind = 'null' | 'scalar' | 'node' | 'edge' | 'path' | 'list' | 'map';

export function valueKind(v: CypherValue): ValueKind {
  if (v === null) return 'null';
  if (Array.isArray(v)) return 'list';
  if (isObj(v)) {
    if (v._type === 'node') return 'node';
    if (v._type === 'edge') return 'edge';
    if (v._type === 'path') return 'path';
    return 'map';
  }
  return 'scalar';
}

const SHORT = 40;
function scalar(v: CypherValue): string {
  if (typeof v === 'string') {
    const s = v.length > SHORT ? `${v.slice(0, SHORT - 1)}…` : v;
    return JSON.stringify(s);
  }
  return String(v);
}

function props(p: CypherValue | undefined): string {
  if (!isObj(p ?? null)) return '';
  const entries = Object.entries(p as Obj);
  return entries.length === 0 ? '' : ` {${entries.map(([k, v]) => `${k}: ${compact(v)}`).join(', ')}}`;
}

/** Compact one-line form: `(:Fact {id: "..."})`, `[:ABOUT]`, paths as `(:A)-[:T]->(:B)`. */
export function compact(v: CypherValue): string {
  switch (valueKind(v)) {
    case 'null':
      return 'null';
    case 'scalar':
      return scalar(v);
    case 'list':
      return `[${(v as CypherValue[]).map(compact).join(', ')}]`;
    case 'node': {
      const n = v as Obj;
      const labels = Array.isArray(n.labels) ? n.labels.map((l) => `:${String(l)}`).join('') : '';
      return `(${labels}${props(n.properties)})`;
    }
    case 'edge': {
      const e = v as Obj;
      return `[:${String(e.type)}${props(e.properties)}]`;
    }
    case 'path': {
      const p = v as Obj;
      const nodes = (Array.isArray(p.nodes) ? p.nodes : []) as CypherValue[];
      const edges = (Array.isArray(p.edges) ? p.edges : []) as Obj[];
      let out = nodes[0] ? compact(nodes[0]) : '';
      for (let i = 0; i < edges.length; i++) {
        const e = edges[i]!;
        const prev = nodes[i];
        const forward = !isObj(prev ?? null) || (prev as Obj).id === e.src;
        const rel = `[:${String(e.type)}]`;
        const next = nodes[i + 1] ? compact(nodes[i + 1]!) : '()';
        out += forward ? `-${rel}->${next}` : `<-${rel}-${next}`;
      }
      return out;
    }
    default:
      return `{${Object.entries(v as Obj)
        .map(([k, x]) => `${k}: ${compact(x)}`)
        .join(', ')}}`;
  }
}
