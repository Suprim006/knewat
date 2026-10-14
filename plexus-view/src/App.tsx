import { lazy, Suspense } from 'react';
import { Navigate, Route, Routes } from 'react-router-dom';
import { Layout } from './app/Layout';
import { Inventory } from './views/Inventory';
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
        <Route
          path="flow"
          element={
            <Placeholder
              title="Flow"
              blurb="Live ToolCall timeline over SSE; click an event to light up what it created."
            />
          }
        />
        <Route
          path="time"
          element={
            <Placeholder
              title="Time Machine"
              blurb="Step slider: what each agent knew and wrote at step N."
            />
          }
        />
        <Route
          path="why/:id"
          element={
            <Placeholder title="Why" blurb="Path highlight from a decision or fact back to its evidence." />
          }
        />
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
