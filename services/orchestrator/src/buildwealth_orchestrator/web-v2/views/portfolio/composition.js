// Movement II — The composition.
// Three editorial allocation strata (asset class · sector · region)
// and a top-holdings list rendered as ranked rows.

import { html, raw, esc } from '../../lib/dom.js';
import { fmtUsd, fmtPctSigned, roman } from '../../lib/format.js';

export function renderComposition(data) {
  const breakdowns = data.allocation_breakdowns || {};
  const total = data.total_value ?? data.total_portfolio_value ?? 0;
  const top = topHoldings(data, 10);

  return html`
    <section>
      ${raw(sectionHead('II', 'The composition.', 'How wealth is currently distributed.'))}

      <div class="composition-grid">
        ${raw(allocationBlock('Asset class', breakdowns.asset_class, total))}
        ${raw(allocationBlock('Sector',      breakdowns.sector,      total))}
        ${raw(allocationBlock('Region',      breakdowns.region,      total))}
      </div>

      <header class="section-head" style="margin-bottom: var(--s-3);">
        <span class="section-eyebrow">Top holdings</span>
      </header>
      ${raw(renderTopHoldings(top))}
    </section>
  `;
}

// Backend breakdowns can carry raw keys ("real_estate") and case-duplicates
// ("Cash" and "cash" as separate rows). Merge and humanize before display —
// a flagship screen should never leak storage keys.
export function normalizeAllocationRows(rows) {
  const merged = new Map();
  for (const row of Array.isArray(rows) ? rows : []) {
    const rawKey = String(row?.key || row?.label || '—');
    const normKey = rawKey.trim().toLowerCase().replace(/[_\s]+/g, ' ');
    const entry = merged.get(normKey) || { key: humanizeAllocationKey(rawKey), value: 0, allocation: 0 };
    entry.value += Number(row?.value || 0);
    entry.allocation += Number(row?.allocation || row?.allocation_pct || 0);
    merged.set(normKey, entry);
  }
  return [...merged.values()];
}

export function humanizeAllocationKey(key) {
  const text = String(key || '').trim().replace(/_+/g, ' ');
  if (!text) return '—';
  return text
    .split(/\s+/)
    .map(word => (word === word.toUpperCase() && word.length <= 3
      ? word
      : word[0].toUpperCase() + word.slice(1).toLowerCase()))
    .join(' ');
}

function allocationBlock(label, rows, total) {
  const entries = normalizeAllocationRows(rows);
  if (!entries.length) {
    return html`
      <div class="composition-block">
        <span class="composition-eyebrow">${label}</span>
        <p class="marginalia" style="padding: var(--s-4) 0 0;">— no positions yet</p>
      </div>
    `;
  }

  const sorted = [...entries].sort((a, b) => Number(b.value || 0) - Number(a.value || 0)).slice(0, 8);
  const max = Math.max(...sorted.map(r => Number(r.allocation || r.allocation_pct || 0)), 1);

  return html`
    <div class="composition-block">
      <span class="composition-eyebrow">${label}</span>
      <div class="strata">
        ${raw(sorted.map(row => stratum(row, max, total)).join(''))}
      </div>
    </div>
  `;
}

function stratum(row, max, total) {
  const key = row.key || row.label || '—';
  const value = Number(row.value || 0);
  const allocation = Number(row.allocation || row.allocation_pct || 0);
  const width = max > 0 ? (allocation / max) * 100 : 0;

  return html`
    <div class="stratum">
      <span class="stratum-label">${esc(String(key))}</span>
      <span class="stratum-bar">
        <span class="stratum-bar-fill" style="width: ${Math.max(0, Math.min(100, width)).toFixed(1)}%;"></span>
      </span>
      <span class="stratum-pct">${allocation.toFixed(1)}%</span>
      <span class="stratum-value">${fmtUsd(value)}</span>
    </div>
  `;
}

function renderTopHoldings(rows) {
  if (!rows.length) {
    return html`
      <div class="empty-block">
        <span class="glyph">¶</span>
        <p>No holdings recorded yet.</p>
      </div>
    `;
  }
  return html`
    <ol class="holding-list">
      ${raw(rows.map((row, i) => holdingRow(row, i + 1)).join(''))}
    </ol>
  `;
}

function holdingRow(row, index) {
  const symbol = row.symbol || '—';
  const name = row.name || row.long_name || symbol;
  const value = Number(row.current_value || 0);
  const allocation = Number(row.allocation_pct || 0);
  const returnPct = Number(row.gain_loss_pct || 0);
  const returnDir = returnPct >= 0 ? 'up' : 'down';

  return html`
    <li class="holding-row">
      <span class="holding-numeral">${roman(index)}.</span>
      <span>
        <span class="holding-symbol">${esc(String(symbol))}</span>
        <span class="holding-name">${esc(String(name))}</span>
      </span>
      <span class="holding-meta">${row.account ? esc(String(row.account)) : ''}${row.asset_class ? raw(` · ${esc(String(row.asset_class))}`) : ''}</span>
      <span class="holding-value">${fmtUsd(value)}</span>
      <span class="holding-alloc">${allocation.toFixed(1)}%</span>
      <span class="holding-return ${returnDir}">${fmtPctSigned(returnPct)}</span>
    </li>
  `;
}

function topHoldings(data, limit) {
  const h = data.holdings;
  const list = Array.isArray(h) ? h : (h && typeof h === 'object' ? Object.values(h) : []);
  return list
    .filter(row => Number(row?.current_value || 0) > 0)
    .sort((a, b) => Number(b.current_value || 0) - Number(a.current_value || 0))
    .slice(0, limit);
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
