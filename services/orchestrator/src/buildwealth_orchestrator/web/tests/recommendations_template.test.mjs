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
    'Learning loop',
    'Recommendation Factory',
    'Preview Portfolio Risk Recommendations',
    'Create Recommendations',
    'Generation Limit',
    'Attach to Plan',
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
  assert.match(html, /id="preview-portfolio-risk-recommendations"/);
  assert.match(html, /id="create-portfolio-risk-recommendations"/);
  assert.match(html, /id="recommendation-factory-limit"/);
  assert.match(html, /id="recommendation-factory-plan"/);
  assert.match(html, /id="recommendation-factory-summary"/);
  assert.match(html, /id="recommendation-factory-results"/);
  assert.match(html, /Turn active portfolio risk alerts into specific/);
  assert.match(html, /What actually happened, and what should the system learn/);
});
