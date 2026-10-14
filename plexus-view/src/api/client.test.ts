import { describe, expect, it, vi } from 'vitest';
import { ApiError, buildUrl, createHttpApi, graphParams } from './client';
import { createApi, isFixtureMode } from './index';

function fakeFetch(body: unknown = {}, status = 200) {
  return vi.fn(
    async (_url: string | URL | Request, _init?: RequestInit) =>
      new Response(JSON.stringify(body), { status, headers: { 'Content-Type': 'application/json' } }),
  );
}

describe('buildUrl', () => {
  it('joins base and path, trimming trailing slashes', () => {
    expect(buildUrl('http://h:8080/', '/api/tenants')).toBe('http://h:8080/api/tenants');
  });
  it('skips undefined params and encodes the rest', () => {
    expect(buildUrl('http://h', '/x', { a: 1, b: undefined, c: 'x y&z' })).toBe('http://h/x?a=1&c=x%20y%26z');
  });
  it('turns graph queries into comma-joined labels', () => {
    expect(graphParams({ labels: ['Fact', 'Task'], since: 5, limit: 200 })).toEqual({
      labels: 'Fact,Task',
      since: 5,
      until: undefined,
      limit: 200,
    });
    expect(graphParams({ labels: [] }).labels).toBeUndefined();
  });
});

describe('createHttpApi', () => {
  type Api = ReturnType<typeof createHttpApi>;
  const cases: [string, (api: Api) => Promise<unknown>, string][] = [
    ['tenants', (a) => a.tenants(), 'http://api/api/tenants'],
    ['inventory', (a) => a.inventory('acme'), 'http://api/api/acme/inventory'],
    [
      'graph',
      (a) => a.graph('acme', { labels: ['Fact'], since: 10, until: 20, limit: 50 }),
      'http://api/api/acme/graph?labels=Fact&since=10&until=20&limit=50',
    ],
    ['graph (no params)', (a) => a.graph('acme'), 'http://api/api/acme/graph'],
    ['flow', (a) => a.flow('acme', 123), 'http://api/api/acme/flow?after=123'],
    ['flow (from start)', (a) => a.flow('acme'), 'http://api/api/acme/flow'],
    ['step', (a) => a.step('acme', 7), 'http://api/api/acme/step/7'],
    ['why', (a) => a.why('acme', 'abc-1'), 'http://api/api/acme/why/abc-1'],
    [
      'queryText',
      (a) => a.queryText('relay/claim_next_task'),
      'http://api/api/queries/relay/claim_next_task',
    ],
    ['results', (a) => a.results(), 'http://api/api/results'],
  ];
  it.each(cases)('%s requests the right URL', async (_name, call, expected) => {
    const f = fakeFetch();
    await call(createHttpApi('http://api', f as unknown as typeof fetch));
    expect(f).toHaveBeenCalledTimes(1);
    expect(f.mock.calls[0]?.[0]).toBe(expected);
  });

  it('escapes tenant ids in the path', async () => {
    const f = fakeFetch();
    await createHttpApi('http://api', f as unknown as typeof fetch).inventory('a/b');
    expect(f.mock.calls[0]?.[0]).toBe('http://api/api/a%2Fb/inventory');
  });

  it('exposes the SSE stream url', () => {
    expect(createHttpApi('http://api').streamUrl('acme')).toBe('http://api/api/acme/stream');
  });

  it('parses JSON and throws ApiError on non-2xx', async () => {
    const ok = await createHttpApi(
      'http://api',
      fakeFetch({ tenants: [] }) as unknown as typeof fetch,
    ).tenants();
    expect(ok).toEqual({ tenants: [] });
    const bad = createHttpApi('http://api', fakeFetch({}, 503) as unknown as typeof fetch);
    await expect(bad.tenants()).rejects.toBeInstanceOf(ApiError);
    await expect(bad.tenants()).rejects.toMatchObject({ status: 503 });
  });
});

describe('createApi', () => {
  it('detects fixture mode', () => {
    expect(isFixtureMode({ VITE_FIXTURES: '1' })).toBe(true);
    expect(isFixtureMode({})).toBe(false);
  });
  it('serves fixtures when VITE_FIXTURES=1', async () => {
    const api = createApi({ VITE_FIXTURES: '1' });
    const t = await api.tenants();
    expect(t.tenants.map((x) => x.tenant)).toContain('acme');
    expect(api.streamUrl('acme')).toBeNull();
  });
  it('uses VITE_PLEXUS_API otherwise, defaulting to :8080', () => {
    expect(createApi({ VITE_PLEXUS_API: 'http://x:9' }).streamUrl('t')).toBe('http://x:9/api/t/stream');
    expect(createApi({}).streamUrl('t')).toBe('http://localhost:8080/api/t/stream');
  });
});
