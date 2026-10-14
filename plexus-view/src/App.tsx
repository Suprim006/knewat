import { lazy, Suspense } from 'react';
import { Navigate, Route, Routes } from 'react-router-dom';
import { Layout } from './app/Layout';
import { Flow } from './views/Flow';
import { Inventory } from './views/Inventory';
import { TimeMachine } from './views/TimeMachine';
import { Why } from './views/Why';
import { Placeholder } from './views/Placeholder';

// Cytoscape + fcose are ~560 kB; keep them out of the entry chunk (docs/spikes/S3-view-lib.md).
const Explorer = lazy(() => import('./views/Explorer').then((m) => ({ default: m.Explorer })));

export function AppRoutes() {
  return (
    <Routes>
      <Route element={<Layout />}>
        <Route
          index
          element={
            <Suspense fallback={<p className="page muted">Loading explorer…</p>}>
              <Explorer />
            </Suspense>
          }
        />
        <Route path="flow" element={<Flow />} />
        <Route path="time" element={<TimeMachine />} />
        <Route path="why/:id" element={<Why />} />
        <Route path="inventory" element={<Inventory />} />
        <Route
          path="results"
          element={
            <Placeholder
              title="Results"
              blurb="Crucible benchmark results across memory backends."
              phase="P4"
            />
          }
        />
        <Route path="*" element={<Navigate to="/" replace />} />
      </Route>
    </Routes>
  );
}
