import test from 'node:test';
import assert from 'node:assert/strict';
import { renderDiversificationPanel } from '../views/portfolio/analytics.js';

test('diversification panel shows score, reading, components, and the look-through caveat', () => {
  const markup = String(renderDiversificationPanel({
    status: 'ready',
    score: 23.4,
    label: 'Concentrated',
    components: [
      { key: 'effective_positions', label: 'Independent positions', score: 8, sentence: 'The portfolio behaves like about 1.4 independent positions.' },
      { key: 'vehicle_mix', label: 'Funds vs single stocks', score: 13, sentence: '8% of investable value sits in diversified funds.' },
    ],
    reasons: ['The portfolio behaves like about 1.4 independent positions.'],
    caveats: ['Funds are scored as single diversified units — overlapping funds are not yet examined (no holdings look-through).'],
  }));

  assert.match(markup, /How spread out is this\?/);
  assert.match(markup, /23\/100/);
  assert.match(markup, /Concentrated/);
  assert.match(markup, /behaves like about 1\.4 independent positions/);
  assert.match(markup, /Weakest links/);
  assert.match(markup, /look-through/);
});

test('diversification panel hides without data', () => {
  assert.equal(String(renderDiversificationPanel({ status: 'no_data' })), '');
  assert.equal(String(renderDiversificationPanel({})), '');
});
