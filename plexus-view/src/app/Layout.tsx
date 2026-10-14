import { NavLink, Outlet } from 'react-router-dom';
import { useTenant } from './context';
import { useThemeMode } from '../lib/theme';

const NAV: { to: string; label: string; end?: boolean }[] = [
  { to: '/', label: 'Explorer', end: true },
  { to: '/flow', label: 'Flow' },
  { to: '/time', label: 'Time Machine' },
  { to: '/why/latest', label: 'Why' },
  { to: '/inventory', label: 'Inventory' },
  { to: '/results', label: 'Results' },
];

const THEME_LABEL = { auto: 'Auto', light: 'Light', dark: 'Dark' } as const;

export function Layout() {
  const { tenants, tenant, setTenant, fixtures, error } = useTenant();
  const [mode, cycleTheme] = useThemeMode();
  return (
    <div className="app">
      <header className="topbar">
        <div className="brand">
          <span className="brand-mark" aria-hidden="true" />
          Plexus <span className="brand-sub">View</span>
        </div>
        <nav aria-label="Main">
          {NAV.map((n) => (
            <NavLink
              key={n.to}
              to={n.to}
              end={n.end}
              className={({ isActive }) => (isActive ? 'active' : undefined)}
            >
              {n.label}
            </NavLink>
          ))}
        </nav>
        <div className="topbar-right">
          {fixtures && (
            <span className="badge" title="Serving built-in Acme Notes API fixtures (VITE_FIXTURES=1)">
              fixtures
            </span>
          )}
          <label className="tenant">
            <span>Tenant</span>
            <select
              aria-label="Tenant"
              value={tenant}
              onChange={(e) => setTenant(e.target.value)}
              disabled={tenants.length === 0}
            >
              {tenants.length === 0 && <option value="">{error ? 'unavailable' : 'loading…'}</option>}
              {tenants.map((t) => (
                <option key={t.tenant} value={t.tenant}>
                  {t.tenant}
                </option>
              ))}
            </select>
          </label>
          <button type="button" className="btn" onClick={cycleTheme} title="Cycle colour theme">
            Theme: {THEME_LABEL[mode]}
          </button>
        </div>
      </header>
      {error && (
        <div className="banner error" role="alert">
          Cannot reach the View API: {error}
        </div>
      )}
      <main className="content">
        <Outlet />
      </main>
    </div>
  );
}
