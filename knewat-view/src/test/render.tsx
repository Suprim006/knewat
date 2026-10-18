import { render } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { AppProviders } from '../app/AppProviders';
import { AppRoutes } from '../App';
import { buildAcme } from '../fixtures/acme';
import { createFixtureApi } from '../fixtures/client';
import { createGraphController } from '../lib/graphController';
import type { ViewApi } from '../api';

export const acme = buildAcme();

// D1: App lazy-loads Explorer/Flow (cytoscape + fcose, ~560 kB). On a cold start with 16 jsdom files in
// parallel, the first test of a file paid for that import inside its 5 s budget and timed out. Importing
// them here, at module load, moves the cost into collection (no per-test timeout) and the lazy()
// calls then resolve from the module cache.
await Promise.all([import('../views/Explorer'), import('../views/Flow')]);
// ... and run one tiny fcose layout so its first-call setup (the Explorer's `load`) is paid here too.
{
  const warm = createGraphController({ headless: true });
  warm.load(acme.nodes.slice(0, 8), acme.edges);
  warm.destroy();
}

export function renderApp(route = '/', api: ViewApi = createFixtureApi(acme)) {
  localStorage.clear();
  return render(
    <AppProviders api={api}>
      <MemoryRouter initialEntries={[route]}>
        <AppRoutes />
      </MemoryRouter>
    </AppProviders>,
  );
}
