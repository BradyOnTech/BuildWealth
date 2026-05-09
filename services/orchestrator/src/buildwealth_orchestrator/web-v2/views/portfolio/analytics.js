// Movement III — Performance.
// BuildWealth-native performance, benchmark, and return attribution views.

import { html, raw, esc } from '../../lib/dom.js';
import { fmtPctSigned, fmtUsd, fmtUsdSigned } from '../../lib/format.js';

export function renderAnalytics(analytics = null) {
  if (!analytics) {
    return html`
      <section>
        ${raw(sectionHead('III', 'Performance.', 'Returns, benchmarks, and what moved the portfolio.'))}
        <p class="fit-empty">Performance analytics are loading.</p>
      </section>
    `;
  }
  const performance = analytics.performance || {};
  const benchmark = analytics.benchmark || {};
  const attribution = analytics.attribution || {};
  return html`
    <section class="portfolio-analytics">
      ${raw(sectionHead('III', 'Performance.', 'Returns, benchmarks, and what moved the portfolio.'))}
      <div class="analytics-grid">
        ${raw(renderPerformancePanel(performance))}
        ${raw(renderBenchmarkPanel(benchmark))}
      </div>
      ${raw(renderAttributionPanel(attribution))}
      ${raw(renderAnalyticsWarnings(analytics.warnings))}
    </section>
  `;
}

function renderPerformancePanel(performance = {}) {
  return html`
    <article class="analytics-panel">
      <span class="analytics-kicker">Portfolio return</span>
      <dl class="analytics-metrics">
        ${raw(metric('Total return', fmtUsdSigned(numberOr(performance.total_return_usd, 0))))}
        ${raw(metric('Price return', fmtUsdSigned(numberOr(performance.price_return_usd, 0))))}
        ${raw(metric('Income', fmtUsd(numberOr(performance.income_return_usd, 0))))}
        ${raw(metric('TWR', pct(performance.twr_annualized_return_pct ?? performance.twr_return_pct)))}
        ${raw(metric('XIRR', pct(performance.xirr_annualized_return_pct)))}
        ${raw(metric('Net contributions', fmtUsd(numberOr(performance.net_contributions, 0))))}
      </dl>
    </article>
  `;
}

function renderBenchmarkPanel(benchmark = {}) {
  const rows = Array.isArray(benchmark.rows) ? benchmark.rows : [];
  if (benchmark.status !== 'ready' || !rows.length) {
    return html`
      <article class="analytics-panel">
        <span class="analytics-kicker">Benchmarks</span>
        <p class="fit-empty">${esc(benchmark.message || 'Add at least two portfolio snapshots to compare against benchmarks.')}</p>
      </article>
    `;
  }
  return html`
    <article class="analytics-panel">
      <span class="analytics-kicker">Benchmarks</span>
      <dl class="analytics-metrics compact">
        ${raw(metric('Portfolio', pct(benchmark.portfolio_return_pct)))}
        ${raw(metric('Drawdown', pct(benchmark.max_drawdown_pct)))}
        ${benchmark.tracking_error_pct != null ? raw(metric('Tracking error', pct(benchmark.tracking_error_pct))) : ''}
      </dl>
      <div class="benchmark-rows">
        ${raw(rows.map(row => html`
          <div class="benchmark-row">
            <strong>${esc(row.symbol || '')}</strong>
            <span>${pct(row.benchmark_return_pct)}</span>
            <span class="${numberOr(row.alpha_pct, 0) >= 0 ? 'delta-up' : 'delta-down'}">${pct(row.alpha_pct)} alpha</span>
          </div>
        `).join(''))}
      </div>
    </article>
  `;
}

function renderAttributionPanel(attribution = {}) {
  const contributors = Array.isArray(attribution.contributors) ? attribution.contributors : [];
  const detractors = Array.isArray(attribution.detractors) ? attribution.detractors : [];
  if (attribution.status !== 'ready') {
    return html`
      <article class="analytics-panel wide">
        <span class="analytics-kicker">Return contributors</span>
        <p class="fit-empty">${esc(attribution.message || 'Attribution will appear after holdings have return history.')}</p>
      </article>
    `;
  }
  return html`
    <article class="analytics-panel wide">
      <span class="analytics-kicker">Return contributors</span>
      <div class="attribution-grid">
        ${raw(positionList('Contributors', contributors, 'up'))}
        ${raw(positionList('Detractors', detractors, 'down'))}
      </div>
    </article>
  `;
}

function positionList(label, rows, direction) {
  if (!rows.length) {
    return html`
      <div class="attribution-list">
        <h4>${label}</h4>
        <p class="fit-empty">None yet.</p>
      </div>
    `;
  }
  return html`
    <div class="attribution-list">
      <h4>${label}</h4>
      ${raw(rows.slice(0, 5).map(row => html`
        <div class="attribution-row">
          <span>
            <strong>${esc(row.symbol || '')}</strong>
            <em>${esc(row.name || row.asset_class || '')}</em>
          </span>
          <span class="${direction === 'down' ? 'delta-down' : 'delta-up'}">${fmtUsdSigned(numberOr(row.total_return, 0))}</span>
          <span>${pct(row.contribution_pct)} of return</span>
        </div>
      `).join(''))}
    </div>
  `;
}

function renderAnalyticsWarnings(warnings = []) {
  const visible = Array.isArray(warnings) ? warnings.filter(Boolean).slice(0, 2) : [];
  if (!visible.length) return '';
  return html`
    <div class="analytics-warnings">
      ${visible.map(warning => html`<p>${esc(warning)}</p>`)}
    </div>
  `;
}

function metric(label, value) {
  return html`
    <div>
      <dt>${label}</dt>
      <dd>${value}</dd>
    </div>
  `;
}

function pct(value) {
  if (value == null || Number.isNaN(Number(value))) return '-';
  return fmtPctSigned(Number(value));
}

function numberOr(value, fallback) {
  const n = Number(value);
  return Number.isFinite(n) ? n : fallback;
}

function sectionHead(numeral, title, lede) {
  return html`
    <header class="section-head">
      <span class="section-eyebrow">Movement ${numeral}</span>
      <h2 class="section-title">${title}</h2>
      ${lede ? html`<p class="section-lede">${lede}</p>` : ''}
    </header>
  `;
}
