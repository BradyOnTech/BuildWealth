import test from 'node:test';
import assert from 'node:assert/strict';
import { renderStanding } from '../views/portfolio/standing.js';
import { standingChange } from '../views/portfolio.js';

test('standingChange derives the chip window from the snapshot span', () => {
  const change = standingChange({
    delta_total_value_usd: 10635.13,
    delta_total_value_percent: 2.0,
    latest_as_of: '2026-08-25T14:00:00Z',
    oldest_as_of: '2026-07-26T14:00:00Z',
  });
  assert.deepEqual(change, { deltaUsd: 10635.13, deltaPct: 2.0, windowDays: 30 });

  const partialDayChange = standingChange({
    delta_total_value_usd: 100,
    delta_total_value_percent: 1,
    latest_as_of: '2026-08-26T13:00:00Z',
    oldest_as_of: '2026-08-25T14:00:00Z',
  });
  assert.equal(partialDayChange.windowDays, 0);

  assert.equal(standingChange(null), null);
  assert.equal(standingChange({}), null);
});

test('standing hero carries a change chip when snapshot history exists', () => {
  const markup = String(renderStanding(
    {
      total_portfolio_value: 541793.51,
      total_cash: 12000,
      net_performance: 41793.51,
      net_performance_pct: 8.36,
      valuation_status: 'ready',
      updated_at: '2026-08-25T14:00:00Z',
      holdings: [{ symbol: 'VTI', current_value: 200000 }],
    },
    { deltaUsd: 10635.13, deltaPct: 2.0, windowDays: 31 },
  ));
  assert.match(markup, /change-chip delta-up/);
  assert.match(markup, /\+\$10,635/);
  assert.match(markup, /\(\+2%\)/);
  assert.match(markup, /past month/);
});

test('standing hides the chip while valuation is pending — never a naked guess', () => {
  const markup = String(renderStanding(
    {
      total_portfolio_value: 541793.51,
      valuation_status: 'partial',
      unpriced_holdings_count: 2,
      holdings: [{ symbol: 'VTI', current_value: 200000 }],
    },
    { deltaUsd: 10635.13, deltaPct: 2.0, windowDays: 31 },
  ));
  assert.doesNotMatch(markup, /change-chip/);
});

test('standing renders no chip without history', () => {
  const markup = String(renderStanding(
    {
      total_portfolio_value: 541793.51,
      valuation_status: 'ready',
      updated_at: '2026-08-25T14:00:00Z',
      holdings: [{ symbol: 'VTI', current_value: 200000 }],
    },
    null,
  ));
  assert.doesNotMatch(markup, /change-chip/);
});
