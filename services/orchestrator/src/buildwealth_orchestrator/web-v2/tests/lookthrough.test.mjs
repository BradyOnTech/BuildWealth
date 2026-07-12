import test from 'node:test';
import assert from 'node:assert/strict';
import { renderLookThrough, coverageLine, overlapSentence } from '../views/portfolio/lookthrough.js';

const FAKE_REPORT = {
  schema_version: 1,
  total_portfolio_value_usd: 100000,
  coverage: {
    covered_value_usd: 80000,
    total_fund_value_usd: 85000,
    covered_fund_count: 2,
    unknown_funds: ['MYSTERY'],
  },
  effective_company_exposure: [
    {
      symbol: 'AAPL',
      exposure_usd: 20150,
      exposure_pct: 20.15,
      via: [{ fund: 'direct', usd: 15000 }, { fund: 'VTI', usd: 3050 }, { fund: 'VOO', usd: 2100 }],
    },
    {
      symbol: 'NVDA',
      exposure_usd: 4910,
      exposure_pct: 4.91,
      via: [{ fund: 'VTI', usd: 2900 }, { fund: 'VOO', usd: 2010 }],
    },
  ],
  sector_exposure: [
    { key: 'information_technology', exposure_usd: 40650, exposure_pct: 40.65 },
    { key: 'financials', exposure_usd: 10650, exposure_pct: 10.65 },
  ],
  region_exposure: [
    { key: 'united_states', exposure_usd: 95000, exposure_pct: 95 },
  ],
  pairwise_fund_overlap: [
    {
      fund_a: 'VTI',
      fund_b: 'VOO',
      overlap_weight: 0.331,
      shared_top_holdings: ['AAPL', 'NVDA', 'MSFT'],
      basis: 'top_10_holdings',
    },
  ],
  notes: ['Pairwise overlap counts only each fund\'s top-10 holdings, so it understates true overlap.'],
};

test('renderLookThrough shows the coverage line', () => {
  const markup = String(renderLookThrough(FAKE_REPORT));
  assert.ok(markup.includes('Look-through'));
  assert.ok(markup.includes('Constituent estimates cover $80,000 of $85,000 in funds (2 funds).'));
  assert.ok(markup.includes('Not covered: MYSTERY.'));
});

test('renderLookThrough lists company rows with via funds', () => {
  const markup = String(renderLookThrough(FAKE_REPORT));
  assert.ok(markup.includes('data-lookthrough-companies'));
  assert.ok(markup.includes('AAPL'));
  assert.ok(markup.includes('20.2%') || markup.includes('20.15%'));
  assert.ok(markup.includes('via direct, VTI, VOO'));
  assert.ok(markup.includes('NVDA'));
});

test('renderLookThrough shows sector and region rows humanized', () => {
  const markup = String(renderLookThrough(FAKE_REPORT));
  assert.ok(markup.includes('Information Technology'));
  assert.ok(markup.includes('United States'));
  assert.ok(markup.includes('$95,000'));
});

test('renderLookThrough writes the plain-English overlap sentence', () => {
  const markup = String(renderLookThrough(FAKE_REPORT));
  assert.ok(markup.includes('data-lookthrough-overlap'));
  assert.ok(markup.includes('VTI and VOO share an estimated 33% of their weight'));
  assert.ok(markup.includes('shared: AAPL, NVDA, MSFT'));
  assert.equal(overlapSentence({ fund_a: 'VTI', fund_b: 'QQQ', overlap_weight: 0.304 }),
    'VTI and QQQ share an estimated 30% of their weight');
});

test('renderLookThrough surfaces the honesty notes', () => {
  const markup = String(renderLookThrough(FAKE_REPORT));
  assert.ok(markup.includes('understates true overlap'));
});

test('renderLookThrough renders a quiet hint for empty and malformed reports', () => {
  for (const report of [null, undefined, {}, { coverage: {} }, { coverage: { covered_fund_count: 0 } }]) {
    const markup = String(renderLookThrough(report));
    assert.ok(markup.includes('Look-through'));
    assert.ok(markup.includes('fit-empty'));
    assert.ok(markup.includes('broad fund like VTI or VOO'));
    assert.ok(!markup.includes('benchmark-row'));
  }
  // Unknown-only portfolios name the funds that lack estimates.
  const markup = String(renderLookThrough({ coverage: { covered_fund_count: 0, unknown_funds: ['ARKK'] } }));
  assert.ok(markup.includes('No constituent estimates for ARKK yet'));
});

test('coverageLine pluralizes and formats', () => {
  assert.equal(
    coverageLine({ covered_value_usd: 50000, total_fund_value_usd: 50000, covered_fund_count: 1, unknown_funds: [] }),
    'Constituent estimates cover $50,000 of $50,000 in funds (1 fund).',
  );
});
