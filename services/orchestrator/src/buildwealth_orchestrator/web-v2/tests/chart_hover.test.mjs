import test from 'node:test';
import assert from 'node:assert/strict';
import { fanChart, barChart } from '../lib/chart.js';
// Importing chart_hover.js under node (no document) is itself part of the
// contract: DOM binding must be a guarded side effect.
import { findNearestPoint, formatHoverValue } from '../lib/chart_hover.js';

const ROWS = Array.from({ length: 5 }, (_, index) => {
  const year = 2030 + index;
  const step = index + 1;
  return {
    year,
    p10_ending_balance_usd: step * 1000.4,
    p50_ending_balance_usd: step * 3000,
    p90_ending_balance_usd: step * 5000,
  };
});

function hoverPayload(markup) {
  const match = String(markup).match(/data-chart-hover="([^"]+)"/);
  assert.ok(match, 'expected data-chart-hover attribute');
  const json = match[1]
    .replace(/&quot;/g, '"')
    .replace(/&#39;/g, "'")
    .replace(/&lt;/g, '<')
    .replace(/&gt;/g, '>')
    .replace(/&amp;/g, '&');
  return JSON.parse(json);
}

test('fanChart embeds a parseable hover payload matching input rows', () => {
  const chart = fanChart({
    rows: ROWS,
    xKey: 'year',
    bands: [{ lo: 'p10_ending_balance_usd', hi: 'p90_ending_balance_usd', cls: 'chart-band-outer' }],
    lines: [{ key: 'p50_ending_balance_usd', cls: 'chart-line-median' }],
  });
  const payload = hoverPayload(chart);

  assert.equal(payload.xKey, 'year');
  assert.equal(payload.formatY, 'usd');
  assert.equal(payload.points.length, ROWS.length);
  assert.deepEqual(payload.points.map(point => point.x), ROWS.map(row => row.year));
  assert.equal(payload.points[0].values.p50_ending_balance_usd, 3000);
  assert.equal(payload.points[0].values.p10_ending_balance_usd, 1000.4);
  assert.ok(payload.points.every(point => Number.isFinite(point.px)));
  // Default percentile labels, in top-to-bottom order.
  assert.deepEqual(payload.labels, {
    p90_ending_balance_usd: 'P90',
    p50_ending_balance_usd: 'Median',
    p10_ending_balance_usd: 'P10',
  });
  assert.ok(Number.isFinite(payload.plot.t) && payload.plot.b > payload.plot.t);
});

test('fanChart seriesLabels override the derived labels', () => {
  const chart = fanChart({
    rows: ROWS,
    xKey: 'year',
    lines: [
      { key: 'p50_ending_balance_usd', cls: 'chart-line-median' },
      { key: 'p90_ending_balance_usd', cls: 'chart-line-compare' },
    ],
    seriesLabels: { p50_ending_balance_usd: 'Most likely' },
  });
  const payload = hoverPayload(chart);

  assert.equal(payload.labels.p50_ending_balance_usd, 'Most likely');
  assert.equal(payload.labels.p90_ending_balance_usd, 'P90');
});

test('barChart embeds a hover payload with ordinal slot positions', () => {
  const chart = barChart({
    rows: [
      { year: 2035, trial_share_pct: 12.345 },
      { year: 2036, trial_share_pct: 8 },
    ],
    xKey: 'year',
    yKey: 'trial_share_pct',
    seriesLabels: { trial_share_pct: 'Paths first short' },
    hoverFormat: 'pct',
  });
  const payload = hoverPayload(chart);

  assert.equal(payload.formatY, 'pct');
  assert.equal(payload.points.length, 2);
  assert.equal(payload.points[0].x, 2035);
  assert.equal(payload.points[0].values.trial_share_pct, 12.35);
  assert.ok(payload.points[1].px > payload.points[0].px);
  assert.deepEqual(payload.labels, { trial_share_pct: 'Paths first short' });
});

test('findNearestPoint picks the closest point and guards bad input', () => {
  const points = [
    { x: 2030, px: 100, values: {} },
    { x: 2031, px: 200, values: {} },
    { x: 2032, px: 300, values: {} },
  ];

  assert.equal(findNearestPoint(points, 140).x, 2030);
  assert.equal(findNearestPoint(points, 160).x, 2031);
  assert.equal(findNearestPoint(points, 9999).x, 2032);
  // Falls back to data x when px is absent (pure/test usage).
  assert.equal(findNearestPoint([{ x: 2030 }, { x: 2040 }], 2036).x, 2040);
  assert.equal(findNearestPoint([], 100), null);
  assert.equal(findNearestPoint(null, 100), null);
  assert.equal(findNearestPoint(points, Number.NaN), null);
  assert.equal(findNearestPoint([{ x: 'bad' }], 10), null);
});

test('formatHoverValue formats per payload formatY', () => {
  assert.equal(formatHoverValue(1234567, 'usd'), '$1.2M');
  assert.equal(formatHoverValue(12.35, 'pct'), '12.35%');
  assert.equal(formatHoverValue(42, 'raw'), '42');
});
