// Simulation Studio — chart figure builders.
// Each takes the /api/planning/scenarios response and returns figure markup.

import { html, raw, esc } from '../../lib/dom.js';
import { fanChart, compactUsd } from '../../lib/chart.js';
import { histogram, stackedArea } from '../../lib/chart_extra.js';
import { firstDrawdownYear, coastFireYear } from '../plan/milestones.js';

const TREATMENT_SERIES = [
  { key: 'taxable', cls: 'chart-area-taxable', label: 'Taxable' },
  { key: 'tax_deferred', cls: 'chart-area-tax-deferred', label: 'Tax-deferred' },
  { key: 'tax_free', cls: 'chart-area-tax-free', label: 'Tax-free' },
];

function monteCarlo(result = {}) {
  return result && typeof result.monte_carlo === 'object' && result.monte_carlo ? result.monte_carlo : {};
}

function baselineScenario(result = {}) {
  const scenarios = Array.isArray(result.scenarios) ? result.scenarios : [];
  return scenarios.find(item => item?.label === 'baseline') || scenarios[0] || {};
}

// Hero — every simulated future at once: sampled trial paths as ink strokes,
// percentile fan on top, milestone uprights from the baseline timeline.
export function heroFigure(result = {}) {
  const mc = monteCarlo(result);
  const rows = Array.isArray(mc.percentile_timeline) ? mc.percentile_timeline : [];
  const sampled = mc.sampled_paths && typeof mc.sampled_paths === 'object' ? mc.sampled_paths : {};
  const cloudPaths = Array.isArray(sampled.paths) ? sampled.paths : [];
  if (rows.length < 2) return '';

  const timelinePoints = Array.isArray(baselineScenario(result).timeline_points)
    ? baselineScenario(result).timeline_points
    : [];
  const markers = [];
  const coastYear = coastFireYear(timelinePoints);
  const drawdownYear = firstDrawdownYear(timelinePoints);
  if (coastYear != null && coastYear !== drawdownYear) {
    markers.push({ x: coastYear, label: 'Coast FI', cls: 'chart-marker-coast' });
  }
  if (drawdownYear != null) markers.push({ x: drawdownYear, label: 'Retirement' });

  const chart = fanChart({
    rows,
    xKey: 'year',
    height: 360,
    cloud: {
      xs: Array.isArray(sampled.years) ? sampled.years : rows.map(row => row.year),
      paths: cloudPaths.map(path => ({ values: path.values_usd, failed: Boolean(path.failed) })),
    },
    bands: [
      { lo: 'p10_ending_balance_usd', hi: 'p90_ending_balance_usd', cls: 'chart-band-outer' },
      { lo: 'p25_ending_balance_usd', hi: 'p75_ending_balance_usd', cls: 'chart-band-inner' },
    ],
    lines: [{ key: 'p50_ending_balance_usd', cls: 'chart-line-median' }],
    markers,
    seriesLabels: {
      p90_ending_balance_usd: 'P90',
      p75_ending_balance_usd: 'P75',
      p50_ending_balance_usd: 'Most likely',
      p25_ending_balance_usd: 'P25',
      p10_ending_balance_usd: 'P10',
    },
    ariaLabel: 'Simulated portfolio balance paths and percentile range by year',
  });
  if (!chart) return '';

  const failedShown = cloudPaths.filter(path => path.failed).length;
  const runs = Number(mc.runs);
  const first = rows[0];
  const last = rows[rows.length - 1];
  const ageSpan = Number(first.age) > 0 ? ` · ages ${first.age}–${last.age}` : '';
  return html`
    <figure class="chart-figure">
      <div class="chart-legend">
        <span><i class="legend-swatch cloud-funded"></i>Simulated path (funded)</span>
        ${failedShown ? html`<span><i class="legend-swatch cloud-failed"></i>Simulated path (ran short)</span>` : ''}
        <span><i class="legend-swatch band-outer"></i>10th–90th percentile</span>
        <span><i class="legend-swatch band-inner"></i>25th–75th</span>
        <span><i class="legend-swatch line-median"></i>Median</span>
      </div>
      ${raw(chart)}
      <figcaption class="chart-caption">
        Nominal dollars · ${esc(String(cloudPaths.length))} of ${esc(Number.isFinite(runs) ? runs.toLocaleString('en-US') : '—')} simulated paths drawn${ageSpan}
      </figcaption>
    </figure>
  `.toString();
}

// Terminal-outcome distribution with percentile uprights.
export function terminalFigure(result = {}) {
  const mc = monteCarlo(result);
  const distribution = mc.terminal_distribution && typeof mc.terminal_distribution === 'object'
    ? mc.terminal_distribution
    : {};
  const bins = Array.isArray(distribution.bins) ? distribution.bins : [];
  if (!bins.length) return '';

  const chart = histogram({
    bins: bins.map(bin => ({ lo: bin.lo_usd, hi: bin.hi_usd, count: bin.count, share: bin.share_pct })),
    markers: [
      { x: mc.p10_future_value_usd, label: 'P10', cls: 'chart-marker-quiet' },
      { x: mc.p50_future_value_usd, label: 'Median', cls: 'chart-marker-median' },
      { x: mc.p90_future_value_usd, label: 'P90', cls: 'chart-marker-quiet' },
    ],
    ariaLabel: 'Distribution of simulated ending balances',
  });
  if (!chart) return '';

  return html`
    <figure class="chart-figure">
      <div class="chart-legend">
        <span><i class="legend-swatch hist-terminal"></i>Share of simulations ending here</span>
      </div>
      ${raw(chart)}
      <figcaption class="chart-caption">
        Ending balance after the full horizon, nominal dollars · bins run to the 99th percentile
      </figcaption>
    </figure>
  `.toString();
}

// When paths run short: which year does the money run out?
export function failureFigure(result = {}) {
  const mc = monteCarlo(result);
  const failure = mc.failure_analysis && typeof mc.failure_analysis === 'object' ? mc.failure_analysis : {};
  const rows = Array.isArray(failure.first_failure_year_distribution)
    ? failure.first_failure_year_distribution
    : [];
  if (!rows.length) {
    return html`
      <p class="studio-allclear">
        Every simulated path stayed funded through the horizon under these assumptions.
        Raise spending, lower returns, or add volatility to find the plan's edge.
      </p>
    `.toString();
  }

  const median = Number(failure.first_failure_year_median);
  const chart = histogram({
    bins: rows.map(row => ({ lo: row.year, hi: Number(row.year) + 1, count: row.count, share: row.trial_share_pct })),
    markers: Number.isFinite(median) ? [{ x: median + 0.5, label: 'Median', cls: 'chart-marker-median' }] : [],
    barCls: 'chart-hist-bar-short',
    formatX: value => String(Math.round(value)),
    ariaLabel: 'First year simulations ran short, by count',
  });
  if (!chart) return '';

  const failed = Number(failure.failed_trial_count);
  const runs = Number(mc.runs);
  return html`
    <figure class="chart-figure">
      <div class="chart-legend">
        <span><i class="legend-swatch hist-short"></i>Share of simulations first running short</span>
      </div>
      ${raw(chart)}
      <figcaption class="chart-caption">
        ${esc(Number.isFinite(failed) ? failed.toLocaleString('en-US') : '—')} of
        ${esc(Number.isFinite(runs) ? runs.toLocaleString('en-US') : '—')} paths ran short ·
        ${esc(failure.failure_definition || '')}
      </figcaption>
    </figure>
  `.toString();
}

// Balance composition by tax treatment over the projection (baseline scenario).
export function compositionFigure(result = {}) {
  const points = Array.isArray(baselineScenario(result).account_balance_points)
    ? baselineScenario(result).account_balance_points
    : [];
  if (!points.length) return '';

  const byYear = new Map();
  for (const point of points) {
    const year = Number(point?.year);
    if (!Number.isFinite(year)) continue;
    const row = byYear.get(year) || { year, taxable: 0, tax_deferred: 0, tax_free: 0 };
    const treatment = String(point.tax_treatment || '');
    if (treatment in row) row[treatment] += Math.max(0, Number(point.ending_balance_usd) || 0);
    byYear.set(year, row);
  }
  const rows = [...byYear.values()].sort((a, b) => a.year - b.year);
  if (rows.length < 2) return '';

  const chart = stackedArea({
    rows,
    xKey: 'year',
    series: TREATMENT_SERIES.map(({ key, cls }) => ({ key, cls })),
    seriesLabels: Object.fromEntries(TREATMENT_SERIES.map(({ key, label }) => [key, label])),
    ariaLabel: 'Projected balances by tax treatment over time',
  });
  if (!chart) return '';

  return html`
    <figure class="chart-figure">
      <div class="chart-legend">
        <span><i class="legend-swatch area-taxable"></i>Taxable</span>
        <span><i class="legend-swatch area-tax-deferred"></i>Tax-deferred</span>
        <span><i class="legend-swatch area-tax-free"></i>Tax-free</span>
      </div>
      ${raw(chart)}
      <figcaption class="chart-caption">
        Baseline deterministic projection · where the money sits shapes every future tax bill
      </figcaption>
    </figure>
  `.toString();
}

// Scenario strip — the four engine scenarios side by side.
export function scenarioStrip(result = {}) {
  const scenarios = Array.isArray(result.scenarios) ? result.scenarios : [];
  if (!scenarios.length) return '';
  const baseline = scenarios.find(item => item?.label === 'baseline');
  const baseValue = Number(baseline?.future_value_usd);
  const labels = {
    baseline: 'Baseline',
    optimistic: 'Optimistic',
    conservative: 'Conservative',
    hsa_delta: 'With extra HSA',
  };
  return html`
    <div class="studio-scenario-strip">
      ${raw(scenarios.map(item => {
        const value = Number(item?.future_value_usd);
        const delta = Number.isFinite(value) && Number.isFinite(baseValue) && item.label !== 'baseline'
          ? value - baseValue
          : null;
        return html`
          <div class="studio-scenario-card">
            <span class="studio-scenario-label">${esc(labels[item.label] || item.label)}</span>
            <span class="studio-scenario-value">${esc(compactUsd(value))}</span>
            <span class="studio-scenario-delta ${delta == null ? '' : delta >= 0 ? 'is-up' : 'is-down'}">
              ${delta == null ? esc(`${compactUsd(Number(item?.real_value_usd))} real`) : esc(`${delta >= 0 ? '+' : '−'}${compactUsd(Math.abs(delta))} vs baseline`)}
            </span>
          </div>
        `.toString();
      }).join(''))}
    </div>
  `.toString();
}
