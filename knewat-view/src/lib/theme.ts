import { useCallback, useSyncExternalStore } from 'react';

export type ThemeMode = 'auto' | 'light' | 'dark';
const KEY = 'plexus.theme';

function stored(): ThemeMode {
  try {
    const v = localStorage.getItem(KEY);
    return v === 'light' || v === 'dark' ? v : 'auto';
  } catch {
    return 'auto';
  }
}

function applyTheme(mode: ThemeMode): void {
  const el = document.documentElement;
  if (mode === 'auto') delete el.dataset.theme;
  else el.dataset.theme = mode;
}

const listeners = new Set<() => void>();
function subscribe(cb: () => void): () => void {
  listeners.add(cb);
  const mq = typeof matchMedia === 'function' ? matchMedia('(prefers-color-scheme: dark)') : null;
  mq?.addEventListener('change', cb);
  return () => {
    listeners.delete(cb);
    mq?.removeEventListener('change', cb);
  };
}

/** Effective colour scheme: explicit data-theme, else the OS preference. */
function isDarkNow(): boolean {
  const t = document.documentElement.dataset.theme;
  if (t === 'dark') return true;
  if (t === 'light') return false;
  return typeof matchMedia === 'function' && matchMedia('(prefers-color-scheme: dark)').matches;
}

export function useIsDark(): boolean {
  return useSyncExternalStore(subscribe, isDarkNow, () => false);
}

export function useThemeMode(): [ThemeMode, () => void] {
  const mode = useSyncExternalStore(
    subscribe,
    () => document.documentElement.dataset.theme ?? 'auto',
    () => 'auto',
  ) as ThemeMode;
  const cycle = useCallback(() => {
    const next: ThemeMode = mode === 'auto' ? 'light' : mode === 'light' ? 'dark' : 'auto';
    applyTheme(next);
    try {
      if (next === 'auto') localStorage.removeItem(KEY);
      else localStorage.setItem(KEY, next);
    } catch {
      /* ignore */
    }
    listeners.forEach((l) => l());
  }, [mode]);
  return [mode, cycle];
}

export function initTheme(): void {
  applyTheme(stored());
}
