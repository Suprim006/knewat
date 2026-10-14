import { createHttpApi, DEFAULT_API_BASE } from './client';
import type { ViewApi } from './types';

export * from './types';
export * from './client';
export * from './sse';

type Env = Record<string, string | boolean | undefined>;

export function isFixtureMode(env: Env = import.meta.env): boolean {
  return env.VITE_FIXTURES === '1' || env.VITE_FIXTURES === 'true';
}

/** Lazily loads the fixture client so the dataset stays out of the main chunk until used. */
function lazyFixtureApi(): ViewApi {
  const load = import('../fixtures/client').then((m) => m.createFixtureApi());
  return {
    tenants: async () => (await load).tenants(),
    inventory: async (t) => (await load).inventory(t),
    graph: async (t, q) => (await load).graph(t, q),
    flow: async (t, a) => (await load).flow(t, a),
    step: async (t, n) => (await load).step(t, n),
    why: async (t, id) => (await load).why(t, id),
    queryText: async (n) => (await load).queryText(n),
    results: async () => (await load).results(),
    streamUrl: () => null,
  };
}

/** The API the app uses: fixtures when `VITE_FIXTURES=1`, else HTTP at `VITE_PLEXUS_API`. */
export function createApi(env: Env = import.meta.env): ViewApi {
  const base =
    typeof env.VITE_PLEXUS_API === 'string' && env.VITE_PLEXUS_API ? env.VITE_PLEXUS_API : DEFAULT_API_BASE;
  return isFixtureMode(env) ? lazyFixtureApi() : createHttpApi(base);
}
