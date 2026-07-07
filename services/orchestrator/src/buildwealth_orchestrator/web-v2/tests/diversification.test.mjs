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
  // Verdict-first: a concentrated score renders as an opened details panel
  // with the verdict in the summary line.
  assert.match(markup, /<details[^>]*verdict-panel[^>]*tone-bad[^>]*open/);
  assert.match(markup, /verdict-line">23\/100 — Concentrated/);
  assert.match(markup, /Concentrated/);
  assert.match(markup, /behaves like about 1\.4 independent positions/);
  assert.match(markup, /Weakest links/);
  assert.match(markup, /look-through/);
});

test('diversification panel hides without data', () => {
  assert.equal(String(renderDiversificationPanel({ status: 'no_data' })), '');
  assert.equal(String(renderDiversificationPanel({})), '');
});

test('diversification panel names fund overlap findings', () => {
  const markup = String(renderDiversificationPanel({
    status: 'ready',
    score: 55,
    label: 'Reasonably spread',
    components: [],
    reasons: [],
    caveats: [],
    overlap: [
      {
        kind: 'duplicate',
        symbols: ['VOO', 'SPY'],
        combined_value_usd: 50000,
        sentence: 'VOO and SPY track the S&P 500 — effectively one position ($50,000 combined).',
      },
      {
        kind: 'contained',
        symbols: ['QQQ', 'VTI'],
        combined_value_usd: 15000,
        sentence: 'QQQ (the Nasdaq-100) already lives inside VTI (the total US market) — $15,000 of doubled-up exposure.',
      },
    ],
  }));
  assert.match(markup, /VOO · SPY/);
  assert.match(markup, /same index/);
  assert.match(markup, /effectively one position/);
  assert.match(markup, /QQQ · VTI/);
  assert.match(markup, /overlapping/);
  assert.match(markup, /already lives inside/);
});
