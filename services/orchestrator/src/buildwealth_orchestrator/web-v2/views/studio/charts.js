// Simulation Studio — chart figure builders.
// Plain-language legends; optional baseline overlay, peer guides, timeline events.

import { html, raw, esc } from '../../lib/dom.js';
import { fanChart, compactUsd } from '../../lib/chart.js';
import { histogram, stackedArea } from '../../lib/chart_extra.js';
import { firstDrawdownYear, coastFireYear } from '../plan/milestones.js';

const TREATMENT_SERIES = [
  { key: 'taxable', cls: 'chart-area-taxable', label: 'Regular taxable accounts' },
  { key: 'tax_deferred', cls: 'chart-area-tax-deferred', label: 'Tax-deferred (like 401k / IRA)' },
  { key: 'tax_free', cls: 'chart-area-tax-free', label: 'Tax-free (like Roth)' },
];

function monteCarlo(result = {}) {
  return result && typeof result.monte_carlo === 'object' && result.monte_carlo ? result.monte_carlo : {};
}

function baselineScenario(result = {}) {
  const scenarios = Array.isArray(result.scenarios) ? result.scenarios : [];
  return scenarios.find(item => item?.label === 'baseline') || scenarios[0] || {};
}

function balanceKey(band, dollarsMode) {
  if (dollarsMode === 'real') return `${band}_ending_balance_real_usd`;
  return `${band}_ending_balance_usd`;
}

function peerGuides(peer, maxY) {
  const milestones = Array.isArray(peer?.milestones) ? peer.milestones : [];
  return milestones
    .filter(m => Number.isFinite(Number(m.median_usd)) && Number(m.median_usd) <= maxY * 1.08)
    .slice(-2)
    .map(m => ({
      y: Number(m.median_usd),
      label: `Typical US household · ${m.label} (incl. home)`,
      cls: 'chart-guide-peer',
    }));
}

function eventMarkers(events, usedYears) {
  const markers = [];
  const list = Array.isArray(events) ? events : [];
  for (const event of list) {
    if (markers.length >= 4) break;
    const year = Number(String(event?.date || event?.year || '').toString().slice(0, 4));
    if (!Number.isFinite(year) || year < 1900) continue;
    if (usedYears.has(year)) continue;
    const label = String(event.label || event.title || '').trim();
    if (!label) continue;
    usedYears.add(year);
    markers.push({
      x: year,
      label: label.length > 18 ? `${label.slice(0, 17)}…` : label,
      cls: 'chart-marker-event',
    });
  }
  return markers;
}

/**
 * Hero fan: candidate futures + optional dashed "your plan" median.
 * @param {object} result candidate planning response
 * @param {object|null} baselineResult pinned plan run
 * @param {object} opts { dollarsMode, peer, timelineEvents, showCloud }
 */
export function heroFigure(result = {}, baselineResult = null, opts = {}) {
  const dollarsMode = opts.dollarsMode === 'nominal' ? 'nominal' : 'real';
  const mc = monteCarlo(result);
  const rows = Array.isArray(mc.percentile_timeline) ? mc.percentile_timeline : [];
  if (rows.length < 2) {
    // Historical / deterministic-only: fall back to scenario line if present.
    return deterministicPathFigure(result, baselineResult, opts);
  }

  const p10 = balanceKey('p10', dollarsMode);
  const p25 = balanceKey('p25', dollarsMode);
  const p50 = balanceKey('p50', dollarsMode);
  const p75 = balanceKey('p75', dollarsMode);
  const p90 = balanceKey('p90', dollarsMode);

  // Prefer real keys when present; fall back to nominal if real missing.
  const sample = rows[Math.floor(rows.length / 2)] || {};
  const useReal = dollarsMode === 'real' && Number.isFinite(Number(sample[p50]));
  const keys = useReal
    ? { p10, p25, p50, p75, p90 }
    : {
      p10: 'p10_ending_balance_usd',
      p25: 'p25_ending_balance_usd',
      p50: 'p50_ending_balance_usd',
      p75: 'p75_ending_balance_usd',
      p90: 'p90_ending_balance_usd',
    };

  const baseMc = monteCarlo(baselineResult || {});
  const baseRows = Array.isArray(baseMc.percentile_timeline) ? baseMc.percentile_timeline : [];
  const baseByYear = new Map(
    baseRows.map(row => [Number(row.year), Number(row[keys.p50] ?? row.p50_ending_balance_usd)]),
  );
  const merged = rows.map(row => ({
    ...row,
    studio_base_p50: baseByYear.get(Number(row.year)),
  }));
  const hasBaseline = merged.some(row => Number.isFinite(row.studio_base_p50));

  const timelinePoints = Array.isArray(baselineScenario(result).timeline_points)
    ? baselineScenario(result).timeline_points
    : [];
  const markers = [];
  const usedYears = new Set();
  const coastYear = coastFireYear(timelinePoints);
  const drawdownYear = firstDrawdownYear(timelinePoints);
  if (coastYear != null && coastYear !== drawdownYear) {
    markers.push({ x: coastYear, label: 'Could stop saving', cls: 'chart-marker-coast' });
    usedYears.add(coastYear);
  }
  if (drawdownYear != null) {
    markers.push({ x: drawdownYear, label: 'Retirement' });
    usedYears.add(drawdownYear);
  }
  markers.push(...eventMarkers(opts.timelineEvents, usedYears));
  markers.sort((a, b) => a.x - b.x);

  const fanMax = Math.max(
    ...merged.map(row => Number(row[keys.p90] ?? row.p90_ending_balance_usd)).filter(Number.isFinite),
  );
  const guides = Number.isFinite(fanMax) ? peerGuides(opts.peer, fanMax) : [];

  const sampled = mc.sampled_paths && typeof mc.sampled_paths === 'object' ? mc.sampled_paths : {};
  const cloudPaths = Array.isArray(sampled.paths) ? sampled.paths : [];
  // Path cloud is nominal only; hide in today’s-dollars mode to avoid mixing units.
  const showCloud = opts.showCloud !== false && !useReal && cloudPaths.length > 0;

  const chart = fanChart({
    rows: merged,
    xKey: 'year',
    height: 360,
    cloud: showCloud
      ? {
        xs: Array.isArray(sampled.years) ? sampled.years : rows.map(row => row.year),
        paths: cloudPaths.map(path => ({ values: path.values_usd, failed: Boolean(path.failed) })),
      }
      : null,
    bands: [
      { lo: keys.p10, hi: keys.p90, cls: 'chart-band-outer' },
      { lo: keys.p25, hi: keys.p75, cls: 'chart-band-inner' },
    ],
    lines: [
      ...(hasBaseline ? [{ key: 'studio_base_p50', cls: 'chart-line-compare' }] : []),
      { key: keys.p50, cls: 'chart-line-median' },
    ],
    markers,
    guides,
    seriesLabels: {
      [keys.p90]: 'Better markets',
      [keys.p75]: 'Above middle',
      [keys.p50]: 'Middle outcome',
      studio_base_p50: 'Your plan',
      [keys.p25]: 'Below middle',
      [keys.p10]: 'Tougher markets',
    },
    ariaLabel: 'Simulated portfolio balance range by year',
  });
  if (!chart) return '';

  const failedShown = showCloud ? cloudPaths.filter(path => path.failed).length : 0;
  const runs = Number(mc.runs);
  const first = rows[0];
  const last = rows[rows.length - 1];
  const ageSpan = Number(first.age) > 0 ? ` · ages ${first.age}–${last.age}` : '';
  const unitLabel = useReal ? 'Today’s dollars' : 'Future dollars (not inflation-adjusted)';

  return html`
    <figure class="chart-figure">
      <div class="chart-legend">
        ${showCloud ? html`<span><i class="legend-swatch cloud-funded"></i>One possible market path</span>` : ''}
        ${failedShown ? html`<span><i class="legend-swatch cloud-failed"></i>Path that ran short</span>` : ''}
        <span><i class="legend-swatch band-outer"></i>Most outcomes (tougher → better)</span>
        <span><i class="legend-swatch band-inner"></i>The middle half of outcomes</span>
        <span><i class="legend-swatch line-median"></i>Middle outcome</span>
        ${hasBaseline ? html`<span><i class="legend-swatch line-compare"></i>Your plan (unchanged)</span>` : ''}
        ${guides.length ? html`<span><i class="legend-swatch guide-peer"></i>Typical US household net worth by age (includes home)</span>` : ''}
      </div>
      ${raw(chart)}
      <figcaption class="chart-caption">
        ${esc(unitLabel)} ·
        ${showCloud
          ? `${esc(String(cloudPaths.length))} sample paths drawn from ${esc(Number.isFinite(runs) ? runs.toLocaleString('en-US') : '—')} histories`
          : `${esc(Number.isFinite(runs) ? runs.toLocaleString('en-US') : '—')} market histories`}
        ${ageSpan}
        · shaded band = where most histories land, not a promise
      </figcaption>
    </figure>
  `.toString();
}

/** Single historical / deterministic path when Monte Carlo fan is absent. */
function deterministicPathFigure(result = {}, baselineResult = null, opts = {}) {
  const scenario = baselineScenario(result);
  const points = Array.isArray(scenario.timeline_points) ? scenario.timeline_points : [];
  if (points.length < 2) return '';

  const dollarsMode = opts.dollarsMode === 'nominal' ? 'nominal' : 'real';
  const rows = points.map(point => ({
    year: Number(point.year),
    age: Number(point.age),
    ending_balance_usd: Number(point.ending_balance_usd),
    ending_balance_real_usd: Number(point.ending_balance_real_usd ?? point.ending_balance_usd),
  }));
  const yKey = dollarsMode === 'real' && rows.some(r => Number.isFinite(r.ending_balance_real_usd))
    ? 'ending_balance_real_usd'
    : 'ending_balance_usd';

  const baseScenario = baselineScenario(baselineResult || {});
  const basePoints = Array.isArray(baseScenario.timeline_points) ? baseScenario.timeline_points : [];
  const baseByYear = new Map(
    basePoints.map(p => [Number(p.year), Number(p.ending_balance_usd)]),
  );
  const merged = rows.map(row => ({
    ...row,
    studio_base: baseByYear.get(row.year),
  }));
  const hasBaseline = merged.some(row => Number.isFinite(row.studio_base));

  const markers = [];
  const usedYears = new Set();
  const drawdownYear = firstDrawdownYear(points);
  if (drawdownYear != null) {
    markers.push({ x: drawdownYear, label: 'Retirement' });
    usedYears.add(drawdownYear);
  }
  markers.push(...eventMarkers(opts.timelineEvents, usedYears));

  const chart = fanChart({
    rows: merged,
    xKey: 'year',
    height: 320,
    bands: [],
    lines: [
      ...(hasBaseline ? [{ key: 'studio_base', cls: 'chart-line-compare' }] : []),
      { key: yKey, cls: 'chart-line-median' },
    ],
    markers,
    seriesLabels: {
      [yKey]: 'Historical replay',
      studio_base: 'Your plan',
    },
    ariaLabel: 'Portfolio path under historical market returns',
  });
  if (!chart) return '';

  return html`
    <figure class="chart-figure">
      <div class="chart-legend">
        <span><i class="legend-swatch line-median"></i>This historical stretch</span>
        ${hasBaseline ? html`<span><i class="legend-swatch line-compare"></i>Your plan (Monte Carlo middle)</span>` : ''}
      </div>
      ${raw(chart)}
      <figcaption class="chart-caption">
        One past market path applied to your plan — not a forecast of the future
      </figcaption>
    </figure>
  `.toString();
}

export function terminalFigure(result = {}, { dollarsMode = 'real' } = {}) {
  const mc = monteCarlo(result);
  const distribution = mc.terminal_distribution && typeof mc.terminal_distribution === 'object'
    ? mc.terminal_distribution
    : {};
  const bins = Array.isArray(distribution.bins) ? distribution.bins : [];
  if (!bins.length) return '';

  // Histogram bins are nominal; caption explains. Markers use matching units.
  const loKey = dollarsMode === 'real' ? 'p10_real_value_usd' : 'p10_future_value_usd';
  const midKey = dollarsMode === 'real' ? 'p50_real_value_usd' : 'p50_future_value_usd';
  const hiKey = dollarsMode === 'real' ? 'p90_real_value_usd' : 'p90_future_value_usd';

  const chart = histogram({
    bins: bins.map(bin => ({ lo: bin.lo_usd, hi: bin.hi_usd, count: bin.count, share: bin.share_pct })),
    markers: [
      { x: mc[loKey] ?? mc.p10_future_value_usd, label: 'Tougher', cls: 'chart-marker-quiet' },
      { x: mc[midKey] ?? mc.p50_future_value_usd, label: 'Middle', cls: 'chart-marker-median' },
      { x: mc[hiKey] ?? mc.p90_future_value_usd, label: 'Better', cls: 'chart-marker-quiet' },
    ],
    ariaLabel: 'How often simulations end at each balance',
  });
  if (!chart) return '';

  return html`
    <figure class="chart-figure">
      <div class="chart-legend">
        <span><i class="legend-swatch hist-terminal"></i>Share of market histories ending here</span>
      </div>
      ${raw(chart)}
      <figcaption class="chart-caption">
        Ending balances after the full period (chart bars use future dollars).
        Markers: tougher markets · middle · better markets.
      </figcaption>
    </figure>
  `.toString();
}

export function failureFigure(result = {}) {
  const mc = monteCarlo(result);
  const failure = mc.failure_analysis && typeof mc.failure_analysis === 'object' ? mc.failure_analysis : {};
  const rows = Array.isArray(failure.first_failure_year_distribution)
    ? failure.first_failure_year_distribution
    : [];
  if (!rows.length) {
    return html`
      <p class="studio-allclear">
        Good news under these settings: every market history we tried still had money
        through the end of the period. Try spending more, saving less, or bumpier markets
        in Advanced options if you want to find where the plan gets tight.
      </p>
    `.toString();
  }

  const median = Number(failure.first_failure_year_median);
  const chart = histogram({
    bins: rows.map(row => ({ lo: row.year, hi: Number(row.year) + 1, count: row.count, share: row.trial_share_pct })),
    markers: Number.isFinite(median) ? [{ x: median + 0.5, label: 'Most common', cls: 'chart-marker-median' }] : [],
    barCls: 'chart-hist-bar-short',
    formatX: value => String(Math.round(value)),
    ariaLabel: 'Years when shortfalls first appear',
  });
  if (!chart) return '';

  const failed = Number(failure.failed_trial_count);
  const runs = Number(mc.runs);
  return html`
    <figure class="chart-figure">
      <div class="chart-legend">
        <span><i class="legend-swatch hist-short"></i>Histories that first ran short this year</span>
      </div>
      ${raw(chart)}
      <figcaption class="chart-caption">
        ${esc(Number.isFinite(failed) ? failed.toLocaleString('en-US') : '—')} of
        ${esc(Number.isFinite(runs) ? runs.toLocaleString('en-US') : '—')} histories ran short ·
        taller bars mean more histories first ran out of money that year
      </figcaption>
    </figure>
  `.toString();
}

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
        <span><i class="legend-swatch area-taxable"></i>Regular taxable</span>
        <span><i class="legend-swatch area-tax-deferred"></i>Tax-deferred</span>
        <span><i class="legend-swatch area-tax-free"></i>Tax-free (Roth-style)</span>
      </div>
      ${raw(chart)}
      <figcaption class="chart-caption">
        Where the money sits matters for future taxes — this is the straight-line plan path, not every market history
      </figcaption>
    </figure>
  `.toString();
}

export function scenarioStrip(result = {}) {
  const scenarios = Array.isArray(result.scenarios) ? result.scenarios : [];
  if (!scenarios.length) return '';
  const baseline = scenarios.find(item => item?.label === 'baseline');
  const baseValue = Number(baseline?.future_value_usd);
  const labels = {
    baseline: 'Steady path',
    optimistic: 'Stronger growth',
    conservative: 'Weaker growth',
    hsa_delta: 'With extra HSA savings',
  };
  const helps = {
    baseline: 'A single middle-of-the-road growth path (not the full range of markets).',
    optimistic: 'Same plan if investments grow faster than usual.',
    conservative: 'Same plan if investments grow slower than usual.',
    hsa_delta: 'Steady path plus a bit more saved in an HSA each year.',
  };
  return html`
    <div class="studio-scenario-strip">
      ${raw(scenarios.map(item => {
        const value = Number(item?.future_value_usd);
        const delta = Number.isFinite(value) && Number.isFinite(baseValue) && item.label !== 'baseline'
          ? value - baseValue
          : null;
        return html`
          <div class="studio-scenario-card" title="${esc(helps[item.label] || '')}">
            <span class="studio-scenario-label">${esc(labels[item.label] || item.label)}</span>
            <span class="studio-scenario-value">${esc(compactUsd(value))}</span>
            <span class="studio-scenario-delta ${delta == null ? '' : delta >= 0 ? 'is-up' : 'is-down'}">
              ${delta == null
                ? esc(`${compactUsd(Number(item?.real_value_usd))} in today’s $`)
                : esc(`${delta >= 0 ? '+' : '−'}${compactUsd(Math.abs(delta))} vs steady`)}
            </span>
          </div>
        `.toString();
      }).join(''))}
    </div>
    <p class="studio-section-note">
      These four are simple straight-line stories for comparison. The big chart above is the fuller “many markets” view.
    </p>
  `.toString();
}
