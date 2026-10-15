import { describe, expect, it } from 'vitest';
import * as controller from './graphController';

/** graphController.ts re-exports the helper modules it was split into; importers rely on these names. */
describe('graphController public API', () => {
  it('still exports the runtime names the views and tests import', () => {
    for (const name of [
      'createGraphController',
      'buildStyle',
      'LIGHT_THEME',
      'DARK_THEME',
      'SUSPECT_COLOR',
      'HAYSTACK_EDGE_THRESHOLD',
      'LABEL_MAX_WIDTH',
      'LAYOUT_OPTIONS',
      'MINI_CONTROLLER_OPTIONS',
    ]) {
      expect(controller, name).toHaveProperty(name);
    }
  });
});
