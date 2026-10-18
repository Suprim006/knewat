import { describe, expect, it } from 'vitest';
import { tokenizeCypher } from './cypher';

const types = (src: string) => tokenizeCypher(src).map((t) => [t.type, t.text]);

describe('tokenizeCypher', () => {
  it('colours keywords, labels, params, strings, numbers and comments', () => {
    const toks = tokenizeCypher("// hi\nMATCH (t:Task {id: $id}) WHERE t.n > 3 RETURN 'x'");
    const by = (type: string) => toks.filter((t) => t.type === type).map((t) => t.text);
    expect(by('comment')).toEqual(['// hi']);
    expect(by('keyword')).toEqual(['MATCH', 'WHERE', 'RETURN']);
    expect(by('label')).toEqual([':Task']);
    expect(by('param')).toEqual(['$id']);
    expect(by('number')).toEqual(['3']);
    expect(by('string')).toEqual(["'x'"]);
  });

  it('marks function calls and leaves keywords inside comments and strings alone', () => {
    expect(types('count(x)')).toEqual([
      ['function', 'count'],
      ['text', '(x)'],
    ]);
    expect(types("'MATCH' // RETURN")).toEqual([
      ['string', "'MATCH'"],
      ['text', ' '],
      ['comment', '// RETURN'],
    ]);
  });

  it('round-trips the source text exactly', () => {
    const src =
      "MATCH (a:Agent {id: $agent})\nOPTIONAL MATCH (t)-[:CLAIMED {at: 1.5}]->(x)\nRETURN a.id AS id, 'q\\'s' // end";
    expect(
      tokenizeCypher(src)
        .map((t) => t.text)
        .join(''),
    ).toBe(src);
  });
});
