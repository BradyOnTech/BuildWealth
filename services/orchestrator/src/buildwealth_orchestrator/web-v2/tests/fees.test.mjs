import test from 'node:test';
import assert from 'node:assert/strict';
import { renderFeesPanel } from '../views/portfolio/analytics.js';

const READY = {
  status: 'ready',
  rows: [
    { symbol: 'SPICY', name: 'Spicy Active Fund', value_usd: 100000, expense_ratio_pct: 0.75, annual_fee_usd: 750, index_alternative_fee_usd: 50, excess_fee_usd: 700 },
    { symbol: 'VTI', name: 'Total Market', value_usd: 200000, expense_ratio_pct: 0.03, annual_fee_usd: 60, index_alternative_fee_usd: 100, excess_fee_usd: 0 },
  ],
  total_annual_fee_usd: 810,
  total_excess_vs_index_usd: 700,
  ten_year_excess_usd: 7000,
  weighted_expense_ratio_pct: 0.27,
  covered_value_usd: 300000,
  uncovered_symbols: ['MYSTERY'],
  index_alternative_expense_ratio_pct: 0.05,
};

test('fees panel converts ratios into dollars with an index comparison', () => {
  const markup = String(renderFeesPanel(READY));

  assert.match(markup, /The cost of holding/);
  assert.match(markup, /\$810/);
  assert.match(markup, /0\.27%/);
  assert.match(markup, /\$700\/yr/);
  assert.match(markup, /SPICY/);
  assert.match(markup, /\$700\/yr above an index equivalent/);
  assert.match(markup, /index-fund cheap/);
  assert.match(markup, /\$7,000 over ten years/);
  assert.match(markup, /MYSTERY/);
  assert.match(markup, /#portfolio\?asset=MYSTERY/);
});

test('fees panel invites data entry when ratios are missing', () => {
  const empty = String(renderFeesPanel({ status: 'no_data', rows: [], uncovered_symbols: ['VTI', 'VOO'] }));
  assert.match(empty, /No expense ratios recorded yet/);
  assert.match(empty, /#portfolio\?asset=VTI/);

  const silent = String(renderFeesPanel({ status: 'no_data', rows: [], uncovered_symbols: [] }));
  assert.equal(silent, '');
});
