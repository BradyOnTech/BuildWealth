// Movement I — The standing.
// One reverent number for total portfolio value, with marginalia
// for net performance, TWR, XIRR, position count, and price freshness.

import { html, raw } from '../../lib/dom.js';
import { fmtUsd, splitUsd, fmtUsdSigned, fmtPctSigned, fmtRelative } from '../../lib/format.js';

export function renderStanding(data) {
  const total = data.total_value ?? data.total_portfolio_value ?? 0;
  const cash = data.total_cash ?? 0;
  const performance = data.performance || {};
  const netPerf = data.net_performance ?? 0;
  const netPerfPct = data.net_performance_pct ?? 0;
  const twr = numberOrNull(performance.twr_annualized_return_pct);
  const xirr = numberOrNull(performance.xirr_annualized_return_pct);
  const positions = countHoldings(data);
  const pricesAt = data.prices_updated_at || data.updated_at;

  const { currency, number } = splitUsd(total);

  const marginalia = [];
  if (netPerf !== 0 || netPerfPct !== 0) {
    marginalia.push(margin(
      `${fmtUsdSigned(netPerf)} (${fmtPctSigned(netPerfPct)})`,
      'net performance',
      netPerf >= 0 ? 'up' : 'down',
    ));
  }
  if (twr != null)  marginalia.push(margin(`${fmtPctSigned(twr)}`, 'annualized return', twr >= 0 ? 'up' : 'down'));
  if (xirr != null) marginalia.push(margin(`${fmtPctSigned(xirr)}`, 'your money-weighted return', xirr >= 0 ? 'up' : 'down'));
  if (positions > 0) marginalia.push(margin(`${positions}`, `position${positions === 1 ? '' : 's'}`, 'up'));
  if (cash > 0)      marginalia.push(margin(fmtUsd(cash), 'in cash', 'up'));
  if (pricesAt)      marginalia.push(margin(fmtRelative(pricesAt), 'prices refreshed', 'up'));

  return html`
    <section class="hero-stack">
      <p class="hero-eyebrow">As of ${data.updated_at ? new Date(data.updated_at).toLocaleString('en-US', { dateStyle: 'long', timeStyle: 'short' }) : 'now'}</p>
      <h1 class="hero-number">
        <span class="currency">${currency}</span>${number}
      </h1>
      ${marginalia.length ? html`
        <p class="hero-marginalia">${raw(marginalia.join(''))}</p>
      ` : html`
        <p class="hero-marginalia"><span class="marginalia">No holdings recorded yet — record a transaction to begin.</span></p>
      `}
    </section>
  `;
}

function margin(value, label, dir) {
  const cls = dir === 'down' ? 'delta-down' : 'delta-up';
  return html`
    <span class="${cls}">
      <span class="glyph">·</span>
      <b class="num-mono">${value}</b>
      <span class="marginalia"> ${label}</span>
    </span>
  `;
}

function countHoldings(data) {
  const h = data.holdings;
  if (!h) return 0;
  if (Array.isArray(h)) return h.length;
  return Object.keys(h).length;
}

function numberOrNull(v) {
  if (v == null) return null;
  const n = Number(v);
  return Number.isFinite(n) ? n : null;
}
