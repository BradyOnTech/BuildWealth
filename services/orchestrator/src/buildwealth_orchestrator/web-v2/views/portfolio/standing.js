// Movement I — The standing.
// One reverent number for total portfolio value, with marginalia
// for net performance, TWR, XIRR, position count, and price freshness.

import { html, raw } from '../../lib/dom.js';
import { fmtUsd, splitUsd, fmtUsdSigned, fmtPctSigned, fmtRelative } from '../../lib/format.js';
import { changeChip } from '../../lib/change_chip.js';

export function renderStanding(data, change = null) {
  const knownTotal = data.total_portfolio_value ?? data.total_value ?? 0;
  const cash = data.total_cash ?? 0;
  const performance = data.performance || {};
  const valuationStatus = String(data.valuation_status || '').toLowerCase();
  const valuationPending = valuationStatus === 'partial' || valuationStatus === 'unavailable';
  const pendingCount = Number(data.unpriced_holdings_count || 0);
  const pendingBasis = Number(data.unpriced_cost_basis ?? data.total_cost_basis ?? 0);
  const total = valuationStatus === 'unavailable' && Number(knownTotal) <= 0 && pendingBasis > 0
    ? pendingBasis
    : knownTotal;
  const netPerf = valuationPending ? null : numberOrNull(data.net_performance);
  const netPerfPct = valuationPending ? null : numberOrNull(data.net_performance_pct);
  const twr = valuationPending ? null : numberOrNull(performance.twr_annualized_return_pct);
  const xirr = valuationPending ? null : numberOrNull(performance.xirr_annualized_return_pct);
  const positions = countHoldings(data);
  const pricesAt = data.prices_updated_at || data.updated_at;

  const { currency, number } = splitUsd(total);

  // The window chip rides on snapshot history of the same total the hero
  // shows, so its basis matches exactly. Hidden while valuation is partial —
  // a delta over half-priced data would be a confident lie.
  const chip = (!valuationPending && change)
    ? changeChip({ deltaUsd: change.deltaUsd, deltaPct: change.deltaPct, windowDays: change.windowDays })
    : '';

  const marginalia = [];
  if (chip) marginalia.push(String(chip));
  if (netPerf != null && netPerfPct != null && (netPerf !== 0 || netPerfPct !== 0)) {
    marginalia.push(margin(
      `${fmtUsdSigned(netPerf)} (${fmtPctSigned(netPerfPct)})`,
      'net performance',
      netPerf >= 0 ? 'up' : 'down',
    ));
  }
  if (twr != null)  marginalia.push(margin(`${fmtPctSigned(twr)}`, 'annualized return', twr >= 0 ? 'up' : 'down'));
  if (xirr != null) marginalia.push(margin(`${fmtPctSigned(xirr)}`, 'your money-weighted return', xirr >= 0 ? 'up' : 'down'));
  if (positions > 0) marginalia.push(margin(`${positions}`, `position${positions === 1 ? '' : 's'}`, 'up'));
  if (valuationPending && pendingCount > 0) {
    marginalia.push(margin(
      `${pendingCount}`,
      `position${pendingCount === 1 ? ' needs' : 's need'} a current value; performance is hidden`,
      'down',
    ));
  }
  if (cash > 0)      marginalia.push(margin(fmtUsd(cash), 'in cash', 'up'));
  if (pricesAt)      marginalia.push(margin(fmtRelative(pricesAt), 'prices refreshed', 'up'));

  return html`
    <section class="hero-stack">
      <p class="hero-eyebrow">
        ${valuationStatus === 'unavailable'
          ? 'Recorded cost basis · current value pending'
          : valuationStatus === 'partial'
            ? 'Known current value · some positions pending'
            : `As of ${data.updated_at ? new Date(data.updated_at).toLocaleString('en-US', { dateStyle: 'long', timeStyle: 'short' }) : 'now'}`}
      </p>
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
