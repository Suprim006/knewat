import '@testing-library/jest-dom/vitest';
import { afterEach } from 'vitest';
import { cleanup, configure } from '@testing-library/react';

// The default 1 s is too short for the first render of a graph page when 16 jsdom files (and, in CI,
// other jobs) share the CPU; waitFor/findBy return as soon as the condition holds, so this costs nothing.
configure({ asyncUtilTimeout: 5000 });

afterEach(() => cleanup());
