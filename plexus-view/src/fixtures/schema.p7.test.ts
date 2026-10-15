import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';
import { describe, expect, it } from 'vitest';
import { buildAcme } from './acme';
import { createFixtureApi } from './client';
import { applyP7 } from './p7';

/** The fixtures must carry exactly the fields the real API schema (docs/view-api.schema.json) names. */
interface Def {
  properties: Record<string, unknown>;
  required?: string[];
}
const schema = JSON.parse(readFileSync(resolve(process.cwd(), '../docs/view-api.schema.json'), 'utf8')) as {
  $defs: Record<string, Def>;
};
const keys = (name: string): string[] => Object.keys(schema.$defs[name]!.properties).sort();
const api = createFixtureApi(applyP7(buildAcme()));

describe('fixtures match docs/view-api.schema.json (P7)', () => {
  it('VerifyRow, VerifyChange', async () => {
    const row = (await api.verifyQueue('acme')).rows.find((r) => r.change)!;
    expect(Object.keys(row).sort()).toEqual(keys('VerifyRow'));
    expect(Object.keys(row.change!).sort()).toEqual(keys('VerifyChange'));
  });
  it('DocRow, DocChange', async () => {
    const doc = (await api.docsToUpdate('acme')).docs[0]!;
    expect(Object.keys(doc).sort()).toEqual(keys('DocRow'));
    expect(Object.keys(doc.changes[0]!).sort()).toEqual(keys('DocChange'));
  });
  it('MemoryStrengthResponse', async () => {
    const f = applyP7(buildAcme()).ids['f.jwt']!;
    expect(Object.keys(await api.memoryStrength('acme', f)).sort()).toEqual(keys('MemoryStrengthResponse'));
  });
  it('InventoryResponse memory counts', async () => {
    const inv = await api.inventory('acme');
    for (const k of ['suspect_facts', 'dormant_facts', 'pinned_facts', 'changes', 'code_anchors'])
      expect(Object.keys(schema.$defs.InventoryResponse!.properties)).toContain(k);
    expect(Object.keys(inv).sort()).toEqual(keys('InventoryResponse'));
  });
});
