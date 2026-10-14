import { createContext, useContext } from 'react';
import type { TenantInfo, ViewApi } from '../api';

export const ApiContext = createContext<ViewApi | null>(null);

export function useApi(): ViewApi {
  const api = useContext(ApiContext);
  if (!api) throw new Error('useApi must be used inside <AppProviders>');
  return api;
}

export interface TenantState {
  tenants: TenantInfo[];
  /** Selected tenant id ('' until the tenant list has loaded). */
  tenant: string;
  setTenant: (id: string) => void;
  error?: string;
  /** True until the tenant list has answered (success or error). */
  loading: boolean;
  /** The list loaded fine but is empty: no tenant exists yet. */
  empty: boolean;
  /** True when the data comes from the built-in fixtures. */
  fixtures: boolean;
}

export const TenantContext = createContext<TenantState | null>(null);

export function useTenant(): TenantState {
  const t = useContext(TenantContext);
  if (!t) throw new Error('useTenant must be used inside <AppProviders>');
  return t;
}
