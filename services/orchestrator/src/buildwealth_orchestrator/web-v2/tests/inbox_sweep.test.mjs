import test from 'node:test';
import assert from 'node:assert/strict';

import { renderSweep } from '../views/inbox/sweep.js';

test('inbox sweep labels profile completeness factory results', () => {
  const html = String(renderSweep({
    phase: 'preview-ready',
    preview: {
      counts: {
        portfolio_risk: 1,
        profile_completeness: 1,
      },
      total: 2,
      skipped: 0,
    },
    busy: false,
  }));

  assert.match(html, /portfolio risk/);
  assert.match(html, /profile completeness/);
  assert.match(html, /Create 2 suggestions/);
});
