import type { ReactNode } from 'react';

/** The red "could not load X" alert the views show when a read fails. */
export function ErrorBanner({ children }: { children: ReactNode }) {
  return (
    <div className="banner error" role="alert">
      {children}
    </div>
  );
}
