import { useCallback, useMemo, useState } from 'react';
import type { ReactNode } from 'react';
import { createApi, isFixtureMode } from '../api';
import type { ViewApi } from '../api';
import { useAsync } from '../lib/useAsync';
import { ApiContext, TenantContext } from './context';

const STORAGE_KEY = 'plexus.tenant';

function readStored(): string {
  try {
    return localStorage.getItem(STORAGE_KEY) ?? '';
  } catch {
    return '';
  }
}

export function AppProviders({ api: given, children }: { api?: ViewApi; children: ReactNode }) {
  const api = useMemo(() => given ?? createApi(), [given]);
  const load = useCallback(() => api.tenants(), [api]);
  const { data, error } = useAsync(load);
  const [chosen, setChosen] = useState(readStored);

  const tenants = useMemo(() => data?.tenants ?? [], [data]);
  const tenant = tenants.some((t) => t.tenant === chosen) ? chosen : (tenants[0]?.tenant ?? '');
  const setTenant = useCallback((id: string) => {
    setChosen(id);
    try {
      localStorage.setItem(STORAGE_KEY, id);
    } catch {
      /* storage unavailable: selection just isn't remembered */
    }
  }, []);

  const value = useMemo(
    () => ({ tenants, tenant, setTenant, error: error?.message, fixtures: given ? false : isFixtureMode() }),
    [tenants, tenant, setTenant, error, given],
  );
  return (
    <ApiContext.Provider value={api}>
      <TenantContext.Provider value={value}>{children}</TenantContext.Provider>
    </ApiContext.Provider>
  );
}
