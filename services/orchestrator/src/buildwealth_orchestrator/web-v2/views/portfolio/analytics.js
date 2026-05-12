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
  const risk = analytics.risk_explanations || {};
  return html`
    <section class="portfolio-analytics">
      ${raw(sectionHead('III', 'Performance.', 'Returns, benchmarks, and what moved the portfolio.'))}
      ${raw(renderPeriodSwitch(analytics.period || {}))}
      <div class="analytics-grid">
        ${raw(renderPerformancePanel(performance))}
        ${raw(renderBenchmarkPanel(benchmark))}
      </div>
      ${raw(renderReturnPartsPanel(performance))}
      ${raw(renderAttributionPanel(attribution))}
      ${raw(renderRiskExplanationPanel(risk))}
      ${raw(renderAnalyticsWarnings(analytics.warnings))}
    </section>
  `;
}

function renderPeriodSwitch(period = {}) {
  const options = Array.isArray(period.options) ? period.options : [];
  if (!options.length) return '';
  const current = period.id || '1y';
  return html`
    <nav class="analytics-period-switch" aria-label="Performance period">
      ${raw(options.map(option => `
        <a class="portfolio-guardrails-pill ${option.id === current ? 'active' : ''}"
           href="#portfolio?period=${encodeURIComponent(option.id)}">
          ${esc(option.label || option.id)}
        </a>
      `).join(''))}
    </nav>
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

function renderReturnPartsPanel(performance = {}) {
  const rows = [
    ['Price return', performance.price_return_usd, 'Market price movement from held investments.'],
    ['Income return', performance.income_return_usd ?? performance.income_received_usd, 'Dividends and interest captured in portfolio history.'],
    ['Cash-flow effects', performance.net_contributions, 'Money added or removed from the portfolio.'],
    ['Fees', performance.fees_paid_usd, 'Recorded commissions, service fees, and advisory fees.'],
  ];
  return html`
    <article class="analytics-panel wide">
      <span class="analytics-kicker">Return parts</span>
      <div class="benchmark-rows">
        ${raw(rows.map(([label, value, detail]) => `
          <div class="benchmark-row">
            <strong>${esc(label)}</strong>
            <span>${esc(label === 'Fees' ? fmtUsd(numberOr(value, 0)) : fmtUsdSigned(numberOr(value, 0)))}</span>
            <span>${esc(detail)}</span>
          </div>
        `).join(''))}
      </div>
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

function renderRiskExplanationPanel(risk = {}) {
  const rows = Array.isArray(risk.rows) ? risk.rows : [];
  if (!rows.length) return '';
  return html`
    <article class="analytics-panel wide">
      <span class="analytics-kicker">Risk explained plainly</span>
      <div class="benchmark-rows">
        ${raw(rows.slice(0, 8).map(row => `
          <div class="benchmark-row">
            <strong>${esc(row.label || '')}</strong>
            <span>${esc(formatRiskValue(row))}</span>
            <span>${esc(row.plain || '')}</span>
          </div>
        `).join(''))}
      </div>
      ${raw(renderRiskAlerts(risk.alerts || []))}
    </article>
  `;
}

function renderRiskAlerts(alerts = []) {
  const visible = Array.isArray(alerts) ? alerts.slice(0, 4) : [];
  if (!visible.length) return html`<p class="fit-empty">No active concentration or allocation alerts for this period.</p>`;
  return html`
    <div class="attribution-grid">
      ${raw(visible.map(alert => `
        <div class="attribution-list">
          <h4>${esc(labelize(alert.label || alert.metric || 'Risk alert'))}</h4>
          <p>${esc(alert.message || '')}</p>
          <p>${esc(alert.recommendation || '')}</p>
        </div>
      `).join(''))}
    </div>
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

function formatRiskValue(row = {}) {
  const value = Number(row.value);
  if (!Number.isFinite(value)) return row.context || '-';
  const pctKeys = new Set(['concentration', 'account', 'allocation', 'sector', 'region']);
  const formatted = pctKeys.has(row.key)
    ? `${value.toLocaleString('en-US', { maximumFractionDigits: 1 })}%`
    : value.toLocaleString('en-US', { maximumFractionDigits: 2 });
  return row.context ? `${row.context} · ${formatted}` : formatted;
}

function labelize(value) {
  return String(value || '')
    .replace(/[_-]+/g, ' ')
    .replace(/\b\w/g, (ch) => ch.toUpperCase()) || 'Unknown';
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
