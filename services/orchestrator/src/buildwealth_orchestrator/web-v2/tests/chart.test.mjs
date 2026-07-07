import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';
import {
  compactUsd,
  niceTicks,
  linePath,
  bandPath,
  fanChart,
  barChart,
} from '../lib/chart.js';
import { renderScenarios } from '../views/plan/scenarios.js';
import { renderBranches } from '../views/plan/branches.js';
import { renderWithdrawals } from '../views/plan/withdrawals.js';

const ROWS = Array.from({ length: 11 }, (_, index) => {
  const year = 2030 + index;
  const step = year - 2029;
  return {
    year,
    age: year - 1990,
    p10_ending_balance_usd: step * 1000,
    p25_ending_balance_usd: step * 2000,
    p50_ending_balance_usd: step * 3000,
    p75_ending_balance_usd: step * 4000,
    p90_ending_balance_usd: step * 5000,
  };
});

const FIXTURE = {
  scenario_deltas: [],
  monte_carlo_delta: {},
  simulation_delta: {},
  base_settings: {},
  candidate_settings: {},
  base_result: {
    monte_carlo: {
      percentile_timeline: ROWS,
    },
  },
  candidate_result: {
    monte_carlo: {
      runs: 2000,
      percentile_timeline: ROWS,
    },
    scenarios: [
      {
        label: 'baseline',
        timeline_points: [{ year: 2035, withdrawals_usd: 40000 }],
      },
    ],
  },
};

test('compactUsd formats finite dollar values compactly', () => {
  assert.equal(compactUsd(1234567), '$1.2M');
  assert.equal(compactUsd(850000), '$850k');
  assert.equal(compactUsd(310), '$310');
  assert.equal(compactUsd(-2500000), '-$2.5M');
  assert.equal(compactUsd(2100000000), '$2.1B');
  assert.equal(compactUsd(null), '—');
  assert.equal(compactUsd(Number.NaN), '—');
});

test('niceTicks returns ascending round uniform steps', () => {
  const ticks = niceTicks(0, 100, 4);

  assert.ok(ticks.length >= 2);
  assert.equal(ticks[0], 0);
  assert.ok(ticks.at(-1) <= 100 + Number.EPSILON);
  for (let index = 1; index < ticks.length; index += 1) {
    assert.ok(ticks[index] > ticks[index - 1]);
  }

  const step = ticks[1] - ticks[0];
  for (let index = 2; index < ticks.length; index += 1) {
    assert.ok(Math.abs((ticks[index] - ticks[index - 1]) - step) < 1e-9);
  }

  assert.deepEqual(niceTicks(5, 5), []);
  assert.deepEqual(niceTicks(Number.NaN, 10), []);
});

test('linePath builds SVG move and line commands for valid point series', () => {
  assert.equal(linePath([[0, 0], [10, 20]]), 'M0,0L10,20');
  assert.equal(linePath([[0, 0]]), '');
  assert.equal(linePath([[0, Number.NaN], [1, 2]]), '');
});

test('bandPath closes the region between upper and lower point series', () => {
  assert.equal(
    bandPath([[0, 0], [10, 0]], [[0, 5], [10, 5]]),
    'M0,0L10,0L10,5L0,5Z',
  );
  assert.match(
    bandPath([[0, 1], [10, 2], [20, 1]], [[0, 4], [10, 5], [20, 4]]),
    /Z$/,
  );
});

test('fanChart renders bands, median line, marker, and accessible SVG shell', () => {
  const chart = fanChart({
    rows: ROWS,
    xKey: 'year',
    bands: [
      { lo: 'p10_ending_balance_usd', hi: 'p90_ending_balance_usd', cls: 'chart-band-outer' },
      { lo: 'p25_ending_balance_usd', hi: 'p75_ending_balance_usd', cls: 'chart-band-inner' },
    ],
    lines: [
      { key: 'p50_ending_balance_usd', cls: 'chart-line-median' },
    ],
    markers: [
      { x: 2035, label: 'Retirement' },
    ],
    ariaLabel: 'Fan',
  });

  assert.match(chart, /^<svg/);
  assert.match(chart, /chart-band-outer/);
  assert.match(chart, /chart-band-inner/);
  assert.match(chart, /chart-line-median/);
  assert.match(chart, /chart-marker-label/);
  assert.match(chart, /Retirement/);
  assert.match(chart, /role="img"/);
  assert.equal(fanChart({ rows: ROWS.slice(0, 1) }), '');
  assert.equal(fanChart({}), '');

  const outsideMarker = fanChart({
    rows: ROWS,
    xKey: 'year',
    bands: [
      { lo: 'p10_ending_balance_usd', hi: 'p90_ending_balance_usd', cls: 'chart-band-outer' },
    ],
    lines: [
      { key: 'p50_ending_balance_usd', cls: 'chart-line-median' },
    ],
    markers: [
      { x: 2099, label: 'Outside' },
    ],
  });
  assert.doesNotMatch(outsideMarker, /chart-marker/);
});

test('barChart renders positive bars and skips empty or zero-only data', () => {
  const chart = barChart({
    rows: [
      { year: 2035, trial_share_pct: 12 },
      { year: 2036, trial_share_pct: 8 },
    ],
    xKey: 'year',
    yKey: 'trial_share_pct',
    formatY: value => `${value}%`,
    ariaLabel: 'Failures',
  });

  assert.match(chart, /<rect/);
  assert.match(chart, /chart-bar/);
  assert.match(chart, /2035/);
  assert.equal(barChart({ rows: [] }), '');
  assert.equal(barChart({
    rows: [
      { year: 2035, trial_share_pct: 0 },
      { year: 2036, trial_share_pct: 0 },
    ],
    xKey: 'year',
    yKey: 'trial_share_pct',
  }), '');
});

test('renderScenarios includes trajectory chart for Monte Carlo timelines', () => {
  const state = {
    draft: {},
    result: FIXTURE,
    savedSimulations: {},
  };
  const result = renderScenarios(
    { id: 'plan-1', settings: {} },
    state,
    { assumptionSets: { sets: [] } },
  );
  const markup = String(result);

  assert.match(markup, /chart-figure/);
  assert.match(markup, /chart-band-outer/);
  assert.match(markup, /chart-line-compare/);
  assert.match(markup, /Retirement/);
  assert.match(markup, /2,000 simulated paths/);

  const emptyTimeline = renderScenarios(
    { id: 'plan-1', settings: {} },
    {
      ...state,
      result: {
        ...FIXTURE,
        candidate_result: {
          ...FIXTURE.candidate_result,
          monte_carlo: {
            ...FIXTURE.candidate_result.monte_carlo,
            percentile_timeline: [],
          },
        },
      },
    },
    { assumptionSets: { sets: [] } },
  );

  assert.doesNotMatch(String(emptyTimeline), /chart-figure/);
});

test('renderWithdrawals overlays drawdown trajectories from raw results', () => {
  const timeline = strategyId => Array.from({ length: 21 }, (_, index) => ({
    year: 2030 + index,
    ending_balance_usd: (strategyId === 'four_percent_rule' ? 900000 : 850000) - index * 20000,
    withdrawals_usd: 2030 + index >= 2040 ? 50000 : 0,
    taxes_usd: 2030 + index >= 2040 ? (strategyId === 'four_percent_rule' ? 9000 : 7000) : 2000,
  }));
  const result = {
    current_portfolio_value_usd: 500000,
    comparisons: [
      { strategy: 'four_percent_rule', baseline_future_value_usd: 1 },
      { strategy: 'dynamic_guardrails', baseline_future_value_usd: 2 },
    ],
    best_strategy_by_metric: {},
    explanation: {},
    warnings: [],
    raw_results: {
      four_percent_rule: { scenarios: [{ label: 'baseline', timeline_points: timeline('four_percent_rule') }] },
      dynamic_guardrails: { scenarios: [{ label: 'baseline', timeline_points: timeline('dynamic_guardrails') }] },
    },
  };
  const state = { draft: {}, selectedStrategies: ['four_percent_rule', 'dynamic_guardrails'], result };
  const markup = String(renderWithdrawals({ id: 'plan-1' }, state, { assumptionSets: { sets: [] } }));

  assert.match(markup, /chart-figure/);
  assert.match(markup, /chart-line-s0/);
  assert.match(markup, /chart-line-s1/);
  assert.match(markup, /Drawdown/);
  assert.match(markup, /4% Rule/);
  assert.match(markup, /Dynamic Guardrails/);
  assert.match(markup, /deterministic baseline path per strategy/);
  assert.match(markup, /Annual taxes/);
  assert.match(markup, /same strategy colors/);

  const bare = String(renderWithdrawals(
    { id: 'plan-1' },
    { ...state, result: { ...result, raw_results: {} } },
    { assumptionSets: { sets: [] } },
  ));
  assert.doesNotMatch(bare, /chart-figure/);
});

test('renderBranches renders the trajectory fan for branch results', () => {
  const state = {
    draft: {},
    result: {
      scenario_deltas: [],
      monte_carlo_delta: {},
      simulation_delta: {},
      base_result: { monte_carlo: { percentile_timeline: ROWS } },
      branch_result: {
        monte_carlo: { runs: 500, percentile_timeline: ROWS },
        scenarios: [{ label: 'baseline', timeline_points: [{ year: 2035, withdrawals_usd: 1000 }] }],
      },
    },
  };
  const markup = String(renderBranches({ id: 'plan-1' }, state, { assumptionSets: { sets: [] } }));

  assert.match(markup, /chart-figure/);
  assert.match(markup, /chart-band-outer/);
});

test('plan input staging avoids mid-keystroke re-renders and requests raw results', () => {
  const planSource = readFileSync(resolve(import.meta.dirname, '../views/plan.js'), 'utf8');

  assert.match(planSource, /delegate\(page, 'input', '\[data-scenario-field\]'[^\n]*rerender: false/);
  assert.match(planSource, /delegate\(page, 'input', '\[data-branch-field\]'[^\n]*rerender: false/);
  assert.match(planSource, /include_raw_results: true/);
});

test('esc inside html`` escapes exactly once', async () => {
  const { html, esc } = await import('../lib/dom.js');
  assert.equal(String(html`<p>${esc('a <= b & c')}</p>`), '<p>a &lt;= b &amp; c</p>');
  assert.equal(`${esc('x < y')}`, 'x &lt; y');
  assert.equal(String(esc(null)), '');
});

test('fanChart draws horizontal guides and includes them in the y-domain', () => {
  const rows = [
    { year: 2026, p10: 100, p50: 150, p90: 200 },
    { year: 2036, p10: 200, p50: 400, p90: 600 },
  ];
  const svg = fanChart({
    rows,
    xKey: 'year',
    bands: [{ lo: 'p10', hi: 'p90' }],
    lines: [{ key: 'p50' }],
    guides: [{ y: 550, label: 'US median 45–54 (incl. home)', cls: 'chart-guide-peer' }],
  });
  assert.match(svg, /chart-guide chart-guide-peer/);
  assert.match(svg, /US median 45–54 \(incl\. home\)/);

  // A guide above the data extends the domain so it stays visible.
  const tall = fanChart({
    rows,
    xKey: 'year',
    bands: [{ lo: 'p10', hi: 'p90' }],
    lines: [{ key: 'p50' }],
    guides: [{ y: 900, label: 'above the fan' }],
  });
  assert.match(tall, /above the fan/);

  // No guides → no guide markup.
  const plain = fanChart({ rows, xKey: 'year', bands: [{ lo: 'p10', hi: 'p90' }], lines: [{ key: 'p50' }] });
  assert.doesNotMatch(plain, /chart-guide/);
});

test('trajectory fan marks plan-timeline events as vertical moments', async () => {
  const { renderTrajectoryFan, setPlanTimelineEvents } = await import('../views/plan/scenarios.js');
  setPlanTimelineEvents([
    { date: '2033-04-01', label: 'Home down payment', event_type: 'purchase', amount_usd: 70000 },
    { date: '1899-01-01', label: 'Ancient event' },
    { date: '2035-06-01', label: 'Collides with retirement' },
  ]);
  const markup = String(renderTrajectoryFan(FIXTURE.candidate_result, FIXTURE.base_result));
  setPlanTimelineEvents([]);

  // The event lands as a soft vertical marker with its own label...
  assert.match(markup, /chart-marker-event/);
  assert.match(markup, /Home down payment/);
  // ...the Retirement milestone keeps its year's label slot...
  assert.doesNotMatch(markup, /Collides with retirement/);
  // ...and nonsense dates never reach the chart.
  assert.doesNotMatch(markup, /Ancient event/);
  // The caption tells a fresh eye what the dashed uprights are.
  assert.match(markup, /dashed uprights are your plan-timeline events/);

  // With no events set, no event markers render.
  const bare = String(renderTrajectoryFan(FIXTURE.candidate_result, FIXTURE.base_result));
  assert.doesNotMatch(bare, /chart-marker-event/);
});
