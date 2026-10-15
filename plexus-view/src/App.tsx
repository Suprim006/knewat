import { lazy, Suspense } from 'react';
import { Navigate, Route, Routes } from 'react-router-dom';
import { Layout } from './app/Layout';
import { Inventory } from './views/Inventory';
import { Results } from './views/Results';
import { TimeMachine } from './views/TimeMachine';
import { Verify } from './views/Verify';
import { Why } from './views/Why';

// Cytoscape + fcose are ~560 kB; keep them out of the entry chunk (docs/spikes/S3-view-lib.md).
// Explorer and Flow (its mini-graph) are the only pages that draw with Cytoscape.
const Explorer = lazy(() => import('./views/Explorer').then((m) => ({ default: m.Explorer })));
const Flow = lazy(() => import('./views/Flow').then((m) => ({ default: m.Flow })));

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
        <Route
          path="flow"
          element={
            <Suspense fallback={<p className="page muted">Loading flow…</p>}>
              <Flow />
            </Suspense>
          }
        />
        <Route path="time" element={<TimeMachine />} />
        <Route path="why" element={<Navigate to="/why/latest" replace />} />
        <Route path="why/:id" element={<Why />} />
        <Route path="verify" element={<Verify />} />
        <Route path="inventory" element={<Inventory />} />
        <Route path="results" element={<Results />} />
        <Route path="*" element={<Navigate to="/" replace />} />
      </Route>
    </Routes>
  );
}
