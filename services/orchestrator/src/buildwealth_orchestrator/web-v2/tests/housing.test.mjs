import test from 'node:test';
import assert from 'node:assert/strict';
import { renderHousingPanel } from '../views/portfolio/analytics.js';

test('housing panel shows value, mortgage, equity, and plain-language notes', () => {
  const markup = String(renderHousingPanel({
    status: 'ready',
    properties: [{ label: 'Primary residence', value_usd: 500000 }],
    home_value_usd: 500000,
    mortgage_balance_usd: 320000,
    equity_usd: 180000,
    loan_to_value_pct: 64.0,
    share_of_total_assets_pct: 83.3,
    notes: [
      'This is one property in one place — its value moves with one local market, and it can\'t be trimmed or rebalanced like invested money.',
      'For understanding only — nothing here is a recommendation to buy or sell a home.',
    ],
  }));

  assert.match(markup, /The roof over your head/);
  assert.match(markup, /\$500,000/);
  assert.match(markup, /\$320,000/);
  assert.match(markup, /\$180,000/);
  assert.match(markup, /64%/);
  assert.match(markup, /83%/);
  assert.match(markup, /one local market/);
  assert.match(markup, /nothing here is a recommendation/);
});

test('housing panel lists properties when there are several', () => {
  const markup = String(renderHousingPanel({
    status: 'ready',
    properties: [
      { label: 'Primary residence', value_usd: 500000 },
      { label: 'Lake cabin', value_usd: 150000 },
    ],
    home_value_usd: 650000,
    mortgage_balance_usd: 0,
    equity_usd: null,
    loan_to_value_pct: null,
    share_of_total_assets_pct: 71.0,
    notes: [],
  }));
  assert.match(markup, /Lake cabin/);
  assert.match(markup, /\$150,000/);
});

test('housing panel treats null equity as unknown, not $0', () => {
  const markup = String(renderHousingPanel({
    status: 'ready',
    properties: [{ label: 'Primary residence', value_usd: 420000 }],
    home_value_usd: 420000,
    mortgage_balance_usd: 0,
    equity_usd: null,
    loan_to_value_pct: null,
    share_of_total_assets_pct: 84.2,
    notes: ['No mortgage recorded.'],
  }));
  assert.doesNotMatch(markup, /Your equity/);
  assert.doesNotMatch(markup, /Loan to value/);
  assert.match(markup, /84%/);
});

test('housing panel hides when there is no home', () => {
  assert.equal(String(renderHousingPanel({ status: 'none' })), '');
  assert.equal(String(renderHousingPanel({})), '');
});
