/// <reference types="vitest/config" />
import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

// Ports 5171-5173 are occupied on the dev machine, so the view lives on 5180.
// The View API must allow CORS for http://localhost:5180.
const PORT = 5180;

export default defineConfig({
  plugins: [react()],
  server: { port: PORT, strictPort: true, host: 'localhost' },
  // The lazy Explorer chunk holds cytoscape + fcose (~560 kB raw, accepted in spike S3).
  build: { chunkSizeWarningLimit: 800 },
  preview: { port: PORT, strictPort: true, host: 'localhost' },
  test: {
    environment: 'jsdom',
    setupFiles: ['./src/test/setup.ts'],
    css: false,
    env: { VITE_FIXTURES: '1' },
  },
});
