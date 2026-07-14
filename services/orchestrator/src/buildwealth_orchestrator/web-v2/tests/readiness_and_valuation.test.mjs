import test from 'node:test';
import assert from 'node:assert/strict';

const storage = new Map();
globalThis.window = globalThis.window || {
  sessionStorage: {
    getItem: key => storage.get(key) || '',
    setItem: (key, value) => storage.set(key, String(value)),
    removeItem: key => storage.delete(key),
  },
};

const { fmtPctOrDash, fmtUsdOrDash } = await import('../lib/format.js');
const { renderStanding } = await import('../views/portfolio/standing.js');
const { renderComposition } = await import('../views/portfolio/composition.js');
const { decisionReadiness, copilotConnectionState } = await import('../views/copilot.js');
const { assumptionCoverageSummary } = await import('../views/plan/assumptions.js');

test('formatters safely unwrap provenance values and never leak object text', () => {
  assert.equal(fmtPctOrDash({ value: 0.03, source: 'profile' }), '3.00%');
  assert.equal(fmtUsdOrDash({ value: 1250, source: 'profile' }), '$1,250');
  assert.equal(fmtPctOrDash({ source: 'profile' }), '—');
});

test('unpriced holdings render as pending instead of zero and a total loss', () => {
  const payload = {
    valuation_status: 'unavailable',
    total_value: 0,
    total_cost_basis: 2000,
    unpriced_cost_basis: 2000,
    unpriced_holdings_count: 1,
    net_performance: null,
    net_performance_pct: null,
    holdings: {
      'default:VTI': {
        symbol: 'VTI', name: 'Vanguard Total Stock Market ETF', quantity: 10,
        cost_basis: 2000, current_value: null, current_price: null,
      },
    },
  };
  const standing = String(renderStanding(payload));
  const composition = String(renderComposition(payload));

  assert.match(standing, /<span class="currency">\$<\/span>2,000/);
  assert.match(standing, /recorded cost basis/i);
  assert.match(standing, /current value pending/i);
  assert.doesNotMatch(standing, /-\$2,000/);
  assert.match(composition, /VTI/);
  assert.match(composition, /Price needed/);
  assert.match(composition, /Update value/);
});

test('readiness uses milestone language instead of competing percentages', () => {
  assert.deepEqual(decisionReadiness({
    ready_for_daily_review: false,
    profile_readiness: { status: 'attention', next_gap_title: 'Income' },
  }), {
    label: 'Build your first forecast',
    detail: 'Next: Income.',
    stage: 'profile',
  });
  assert.equal(decisionReadiness({
    ready_for_daily_review: false,
    profile_readiness: { status: 'ready' },
    steps: [{ key: 'portfolio_snapshot', status: 'pending' }],
  }).label, 'Enough for a first forecast');
});

test('copilot reports unavailable before advertising a model', () => {
  assert.equal(copilotConnectionState(null).status, 'loading');
  assert.equal(copilotConnectionState({ providers: [{ id: 'openai', connected: false }] }).status, 'unavailable');
  assert.equal(copilotConnectionState({ providers: [{ id: 'openai', connected: true }] }).status, 'ready');
});

test('plan summary distinguishes starting assumptions from reviewed values', () => {
  const defaults = {
    years: { value: 30, source: 'buildwealth_default' },
    inflation_rate: { value: 0.025, source: 'buildwealth_default' },
  };
  assert.equal(assumptionCoverageSummary({}, defaults), 'Using 2 starting assumptions');
  assert.equal(assumptionCoverageSummary({ years: 20 }, defaults), '1 reviewed · 1 starting value');
});
