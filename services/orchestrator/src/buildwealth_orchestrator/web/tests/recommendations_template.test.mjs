import test from 'node:test';
import assert from 'node:assert/strict';

import { template } from '../views/recommendations.js';

test('recommendations view exposes outcome tracking workflow', () => {
  const html = template();

  for (const label of [
    'Outcome Tracker',
    'Log Next Outcome',
    'Realized Future-Value Delta',
    'Realized Real-Value Delta',
    'Measurement Source',
    'Save Outcome',
  ]) {
    assert.match(html, new RegExp(label));
  }

  assert.match(html, /id="recommendation-outcome-tracker-summary"/);
  assert.match(html, /id="recommendation-outcome-tracker-list"/);
  assert.match(html, /id="recommendation-outcome-form"/);
  assert.match(html, /id="recommendation-outcome-current"/);
  assert.match(html, /id="recommendation-outcome-observed-at"/);
  assert.match(html, /id="recommendation-outcome-window-days"/);
  assert.match(html, /id="recommendation-outcome-save"/);
  assert.match(html, /What actually happened, and what should the system learn/);
});
