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
      ${raw(renderDiversificationPanel(analytics.diversification || {}))}
      ${raw(renderHousingPanel(analytics.housing || {}))}
      ${raw(renderFeesPanel(analytics.fees || {}))}
      ${raw(renderRiskExplanationPanel(risk))}
      ${raw(renderAnalyticsWarnings(analytics.warnings))}
    </section>
  `;
}

// One honest number for "how spread out am I?", with the weakest links named.
export function renderDiversificationPanel(diversification = {}) {
  if (diversification.status !== 'ready') return '';
  const components = Array.isArray(diversification.components) ? diversification.components : [];
  const reasons = Array.isArray(diversification.reasons) ? diversification.reasons : [];
  const caveats = Array.isArray(diversification.caveats) ? diversification.caveats : [];
  const score = Number(diversification.score);
  return html`
    <article class="analytics-panel wide">
      <span class="analytics-kicker">How spread out is this?</span>
      <dl class="analytics-metrics compact">
        ${raw(metric('Diversification', Number.isFinite(score) ? `${score.toFixed(0)}/100` : '—'))}
        ${diversification.label ? raw(metric('Reading', diversification.label)) : ''}
        ${Number(diversification.investable_value_usd) > 0 ? raw(metric('Invested money', fmtUsd(diversification.investable_value_usd))) : ''}
      </dl>
      <div class="benchmark-rows">
        ${raw(components.map(component => html`
          <div class="benchmark-row">
            <strong>${esc(String(component.label || ''))}</strong>
            <span>${Number(component.score).toFixed(0)}/100</span>
            <span>${esc(String(component.sentence || ''))}</span>
          </div>
        `).join(''))}
      </div>
      ${reasons.length ? html`
        <p class="marginalia">Weakest links: ${reasons.map(esc).join(' ')}</p>
      ` : ''}
      ${raw(caveats.map(caveat => html`<p class="marginalia">${caveat}</p>`.toString()).join(''))}
    </article>
  `;
}

// The home is housing, not a portfolio position — so it gets its own lens
// instead of a seat in the diversification score. Value, loan, equity, and
// the plain fact that it all sits in one local market.
export function renderHousingPanel(housing = {}) {
  if (housing.status !== 'ready') return '';
  const properties = Array.isArray(housing.properties) ? housing.properties : [];
  const notes = Array.isArray(housing.notes) ? housing.notes : [];
  // Number(null) is 0 — a home with no recorded mortgage has null equity,
  // which must read as "unknown", not "$0 is yours".
  const equity = housing.equity_usd == null ? NaN : Number(housing.equity_usd);
  const share = housing.share_of_total_assets_pct == null ? NaN : Number(housing.share_of_total_assets_pct);
  const ltv = housing.loan_to_value_pct == null ? NaN : Number(housing.loan_to_value_pct);
  return html`
    <article class="analytics-panel wide">
      <span class="analytics-kicker">The roof over your head</span>
      <dl class="analytics-metrics compact">
        ${raw(metric('Home value', fmtUsd(numberOr(housing.home_value_usd, 0))))}
        ${Number(housing.mortgage_balance_usd) > 0 ? raw(metric('Mortgage', fmtUsd(housing.mortgage_balance_usd))) : ''}
        ${Number.isFinite(equity) ? raw(metric('Your equity', fmtUsd(equity))) : ''}
        ${Number.isFinite(ltv) ? raw(metric('Loan to value', `${ltv.toFixed(0)}%`)) : ''}
        ${Number.isFinite(share) ? raw(metric('Share of what you own', `${share.toFixed(0)}%`)) : ''}
      </dl>
      ${properties.length > 1 ? html`
        <div class="benchmark-rows">
          ${raw(properties.slice(0, 4).map(row => html`
            <div class="benchmark-row">
              <strong>${esc(String(row.label || ''))}</strong>
              <span>${fmtUsd(numberOr(row.value_usd, 0))}</span>
            </div>
          `).join(''))}
        </div>
      ` : ''}
      ${raw(notes.map(note => html`<p class="marginalia">${note}</p>`.toString()).join(''))}
    </article>
  `;
}

// The cost of holding — Sharpe's arithmetic in the user's own dollars.
// Percentages don't hurt; dollars per year do.
export function renderFeesPanel(fees = {}) {
  const rows = Array.isArray(fees.rows) ? fees.rows : [];
  const uncovered = Array.isArray(fees.uncovered_symbols) ? fees.uncovered_symbols : [];
  if (fees.status !== 'ready') {
    if (!uncovered.length) return '';
    return html`
      <article class="analytics-panel wide">
        <span class="analytics-kicker">The cost of holding</span>
        <p class="fit-empty">
          No expense ratios recorded yet. Add them on ${raw(uncoveredLinks(uncovered))}
          to see what your funds cost per year.
        </p>
      </article>
    `;
  }
  const weighted = Number(fees.weighted_expense_ratio_pct);
  const excess = Number(fees.total_excess_vs_index_usd);
  return html`
    <article class="analytics-panel wide">
      <span class="analytics-kicker">The cost of holding</span>
      <dl class="analytics-metrics compact">
        ${raw(metric('Fees per year', fmtUsd(numberOr(fees.total_annual_fee_usd, 0))))}
        ${Number.isFinite(weighted) ? raw(metric('Weighted expense ratio', `${weighted.toFixed(2)}%`)) : ''}
        ${excess > 0 ? raw(metric('Above index-fund cost', fmtUsd(excess) + '/yr')) : ''}
      </dl>
      <div class="benchmark-rows">
        ${raw(rows.slice(0, 6).map(row => html`
          <div class="benchmark-row">
            <strong>${esc(String(row.symbol || ''))}</strong>
            <span>${Number(row.expense_ratio_pct).toFixed(2)}% · ${fmtUsd(row.annual_fee_usd)}/yr</span>
            <span class="${Number(row.excess_fee_usd) > 0 ? 'delta-down' : 'delta-up'}">
              ${Number(row.excess_fee_usd) > 0 ? `${fmtUsd(row.excess_fee_usd)}/yr above an index equivalent` : 'index-fund cheap'}
            </span>
          </div>
        `).join(''))}
      </div>
      ${excess > 0 ? html`
        <p class="marginalia">
          At today's balance that difference is ${fmtUsd(numberOr(fees.ten_year_excess_usd, 0))} over ten years —
          before compounding works against you.
        </p>
      ` : html`<p class="marginalia">Your funds are already at or near index-fund cost. Nothing to fix here.</p>`}
      ${uncovered.length ? html`
        <p class="marginalia">No expense ratio yet for ${raw(uncoveredLinks(uncovered))} — add one on the asset page for full coverage.</p>
      ` : ''}
    </article>
  `;
}

function uncoveredLinks(symbols = []) {
  return symbols.slice(0, 4)
    .map(symbol => html`<a class="link-editorial" href="#portfolio?asset=${encodeURIComponent(String(symbol))}">${esc(String(symbol))}</a>`.toString())
    .join(', ');
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
