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

const { renderHarvestCard, renderLadderResult } = await import('../views/tax.js');

test('renderHarvestCard lists candidate lots with wash-sale flags and totals', () => {
  const markup = String(renderHarvestCard({
    as_of: '2026-07-12',
    candidate_count: 2,
    total_harvestable_loss_usd: -650,
    total_estimated_tax_benefit_usd: 143.5,
    candidates: [
      { symbol: 'LOSER', term: 'long', quantity: 10, unit_cost: 100, current_price: 50,
        unrealized_loss_usd: -500, estimated_tax_benefit_usd: 100, wash_sale_risk: false },
      { symbol: 'LOSER', term: 'short', quantity: 5, unit_cost: 80, current_price: 50,
        unrealized_loss_usd: -150, estimated_tax_benefit_usd: 43.5, wash_sale_risk: true },
    ],
    notes: ['Wash-sale rule: …'],
  }));
  assert.match(markup, /Tax-loss harvesting · as of 2026-07-12/);
  assert.match(markup, /2 lots below basis/);
  assert.match(markup, /LOSER · long-term/);
  assert.match(markup, /wash-sale risk/);
  assert.match(markup, /save ≈\$44/); // fmtUsd rounds to whole dollars
});

test('renderHarvestCard celebrates an empty report', () => {
  const markup = String(renderHarvestCard({
    as_of: '2026-07-12', candidate_count: 0,
    total_harvestable_loss_usd: 0, total_estimated_tax_benefit_usd: 0,
    candidates: [], notes: [],
  }));
  assert.match(markup, /No taxable lots sit far enough below basis/);
});

test('renderLadderResult shows schedule rows, totals, and warnings', () => {
  const markup = String(renderLadderResult({
    schedule: [
      { year: 2026, starting_balance_usd: 400000, conversion_usd: 153600,
        estimated_tax_usd: 40244, effective_rate_on_conversion: 0.262, ending_balance_usd: 258720 },
      { year: 2027, starting_balance_usd: 258720, conversion_usd: 153600,
        estimated_tax_usd: 40244, effective_rate_on_conversion: 0.262, ending_balance_usd: 110376 },
    ],
    total_converted_usd: 307200,
    total_estimated_tax_usd: 80488,
    average_rate_on_conversions: 0.262,
    remaining_balance_usd: 110376,
    warnings: ['Conversions push income across an IRMAA threshold in at least one year — Medicare premiums rise two years later.'],
  }));
  assert.match(markup, /Converts \$307,200 over 2 years/);
  assert.match(markup, /26\.2% average/);
  assert.match(markup, /2026/);
  assert.match(markup, /IRMAA/);
  assert.match(markup, /\$110,376 remains unconverted/);
});
