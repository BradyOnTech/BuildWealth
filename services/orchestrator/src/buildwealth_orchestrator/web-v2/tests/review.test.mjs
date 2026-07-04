import test from 'node:test';
import assert from 'node:assert/strict';
import { renderReviewDocument, meta } from '../views/review.js';

const HEALTH = {
  net_worth_usd: 582985,
  total_monthly_expenses_usd: 6000,
  savings_rate_pct: 27.2,
  emergency_fund_months: 4.0,
  debt_to_income_ratio_pct: 22.5,
  highlights: ['Savings rate of 27.2% is strong.', 'Emergency fund needs building.'],
};

const ANALYTICS = {
  performance: {
    twr_annualized_return_pct: 11.4,
    xirr_annualized_return_pct: 10.1,
    price_return_usd: 48200,
    income_return_usd: 6100,
    net_contributions: 30000,
    fees_paid_usd: 340,
  },
  attribution: {
    status: 'ready',
    contributors: [{ symbol: 'VTI', total_return: 22000 }],
    detractors: [{ symbol: 'ARKK', total_return: -4100 }],
  },
  benchmark: { rows: [{ symbol: 'SPY', benchmark_return_pct: 9.8, alpha_pct: 1.6 }] },
};

const PLAN = {
  decisions: [
    {
      label: 'Raised 401k contribution',
      rationale: 'Guardrail drift after raise.',
      created_at: '2026-03-02T00:00:00Z',
      outcome_captured: true,
      expected_outcome: 'On-track probability improves.',
      realized_outcome: 'Funded rate rose 4 points.',
    },
    { label: 'Deferred car purchase', created_at: '2026-05-11T00:00:00Z', outcome_captured: false },
    { label: 'Ancient decision', created_at: '2020-01-01T00:00:00Z', outcome_captured: false },
  ],
};

const SIMS = { simulations: [{ title: 'Job loss stress test', created_at: '2026-06-01T00:00:00Z' }] };

test('review view registers as a utility surface', () => {
  assert.equal(meta.id, 'review');
  assert.equal(meta.group, 'utility');
});

test('renderReviewDocument compiles the full edition', () => {
  const markup = renderReviewDocument({
    health: HEALTH,
    analytics: ANALYTICS,
    plan: PLAN,
    savedSims: SIMS,
    now: new Date('2026-07-03T12:00:00Z'),
  });

  assert.match(markup, /The 2026 Edition/);
  assert.match(markup, /582,985/);
  assert.match(markup, /The year in causes/);
  assert.match(markup, /Progress to financial independence/);
  assert.match(markup, /32% of \$1\.8M/);
  assert.match(markup, /Time-weighted return/);
  assert.match(markup, /11\.4%/);
  assert.match(markup, /SPY 1\.6% alpha/);
  assert.match(markup, /Carried the year/);
  assert.match(markup, /VTI/);
  assert.match(markup, /2 recorded · 1 with outcomes measured/);
  assert.match(markup, /Raised 401k contribution/);
  assert.match(markup, /Funded rate rose 4 points/);
  assert.doesNotMatch(markup, /Ancient decision/);
  assert.match(markup, /Job loss stress test/);
  assert.match(markup, /Savings rate of 27\.2% is strong/);
  assert.match(markup, /Print \/ save as PDF/);
});

test('renderReviewDocument degrades gracefully with no data', () => {
  const markup = renderReviewDocument({ now: new Date('2026-07-03T12:00:00Z') });
  assert.match(markup, /The 2026 Edition/);
  assert.match(markup, /Add profile and portfolio data/);
  assert.match(markup, /No decisions were recorded/);
  assert.doesNotMatch(markup, /The experiments/);
});
