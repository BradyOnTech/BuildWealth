import test from 'node:test';
import assert from 'node:assert/strict';
import {
  buildAffordabilityPayload,
  renderAffordabilitySection,
} from '../views/today/affordability.js';
import { computeFiProgress } from '../views/today.js';

test('buildAffordabilityPayload shapes one-time and monthly requests', () => {
  assert.deepEqual(
    buildAffordabilityPayload({ description: 'A newer car', mode: 'one_time', amount: '42000', loan_rate_pct: '6.5', loan_term_years: '5', down_payment_pct: '20' }),
    { description: 'A newer car', purchase_price_usd: 42000, loan_rate_pct: 6.5, loan_term_years: 5, down_payment_pct: 20 },
  );
  assert.deepEqual(
    buildAffordabilityPayload({ description: 'Gym', mode: 'monthly', amount: '180' }),
    { description: 'Gym', monthly_amount_usd: 180 },
  );
  assert.equal(buildAffordabilityPayload({ mode: 'monthly', amount: '' }), null);
  assert.equal(buildAffordabilityPayload({ mode: 'one_time', amount: '0' }), null);
  // cash purchase: loan fields omitted when blank
  assert.deepEqual(
    buildAffordabilityPayload({ description: 'Roof', mode: 'one_time', amount: '18000' }),
    { description: 'Roof', purchase_price_usd: 18000 },
  );
});

test('renderAffordabilitySection renders form and verdict states', () => {
  const empty = String(renderAffordabilitySection({ draft: { mode: 'one_time' }, busy: false, result: null, error: null }));
  assert.match(empty, /Price a decision/);
  assert.match(empty, /Can we afford it\?/);
  assert.match(empty, /Loan rate/);
  assert.match(empty, /Price it/);

  const monthly = String(renderAffordabilitySection({ draft: { mode: 'monthly' }, busy: false, result: null, error: null }));
  assert.doesNotMatch(monthly, /Loan rate/);

  const verdict = String(renderAffordabilitySection({
    draft: { mode: 'one_time' },
    busy: false,
    error: null,
    result: {
      description: 'A newer car',
      assessment: 'stretch',
      assessment_detail: 'This is technically affordable but would significantly reduce your savings capacity.',
      proposed_monthly_usd: 640,
      is_loan_estimate: true,
      estimated_monthly_payment_usd: 640,
      current_monthly_surplus_usd: 2400,
      new_monthly_surplus_usd: 1760,
      current_savings_rate_pct: 22.5,
      new_savings_rate_pct: 16.5,
      current_dti_pct: 12,
      new_dti_pct: 18,
      current_annual_savings_usd: 28800,
      new_annual_savings_usd: 21120,
      annual_savings_reduction_usd: 7680,
      plan_impact_detail: 'Annual savings drop by $7,680.',
      highlights: ['Savings rate falls from 22.5% to 16.5%.', 'DTI stays under 28%.'],
    },
  }));
  assert.match(verdict, /A stretch\./);
  assert.match(verdict, /Thin margins/);
  assert.match(verdict, /\$2,400/);
  assert.match(verdict, /\$1,760/);
  assert.match(verdict, /Savings rate falls/);
  assert.match(verdict, /Talk it through in Copilot/);
  assert.match(verdict, /-\$7,680/);
});

test('computeFiProgress derives 25x target from monthly expenses', () => {
  const fi = computeFiProgress({ total_monthly_expenses_usd: 6000, net_worth_usd: 774000 });
  assert.equal(fi.targetUsd, 1800000);
  assert.equal(fi.progressPct, 43);

  assert.equal(computeFiProgress({ total_monthly_expenses_usd: 0, net_worth_usd: 100000 }), null);
  assert.equal(computeFiProgress(null), null);
  assert.equal(computeFiProgress({ total_monthly_expenses_usd: 6000, net_worth_usd: -5 }), null);
});
