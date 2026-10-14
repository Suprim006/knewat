import { useEffect, useState } from 'react';

export interface AsyncState<T> {
  data: T | undefined;
  error: Error | undefined;
  loading: boolean;
}

/**
 * Run `fn` whenever its identity changes (wrap it in useCallback). Results of a superseded call are
 * dropped. `loading` is derived (no synchronous setState inside the effect).
 */
export function useAsync<T>(fn: () => Promise<T>): AsyncState<T> {
  const [state, setState] = useState<{ fn: unknown; data?: T; error?: Error }>({ fn: null });
  useEffect(() => {
    let live = true;
    fn().then(
      (data) => {
        if (live) setState({ fn, data });
      },
      (e: unknown) => {
        if (live) setState({ fn, error: e instanceof Error ? e : new Error(String(e)) });
      },
    );
    return () => {
      live = false;
    };
  }, [fn]);
  const current = state.fn === fn;
  return {
    data: current ? state.data : undefined,
    error: current ? state.error : undefined,
    loading: !current,
  };
}
