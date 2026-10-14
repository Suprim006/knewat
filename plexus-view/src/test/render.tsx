import { render } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { AppProviders } from '../app/AppProviders';
import { AppRoutes } from '../App';
import { buildAcme } from '../fixtures/acme';
import { createFixtureApi } from '../fixtures/client';
import type { ViewApi } from '../api';

export const acme = buildAcme();

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
