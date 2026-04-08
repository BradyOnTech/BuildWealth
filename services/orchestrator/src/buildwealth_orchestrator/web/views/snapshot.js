import { fetchJson } from '../lib/api.js';
import { byId, fmtCurrency, fmtPct, fmtDate, writeLog } from '../lib/utils.js';

export const id = 'snapshot';
export const label = 'Portfolio';
export const icon = '<svg viewBox="0 0 20 20" fill="none" stroke="currentColor" stroke-width="1.6"><polyline points="3,14 7,8 11,11 17,4"/><line x1="3" y1="17" x2="17" y2="17"/></svg>';

export function template() {
  return `
    <div class="view-header"><h2>Portfolio Snapshot</h2><button class="ghost small" id="reload-snapshot">Reload</button></div>
    <p class="snapshot-total" id="snapshot-total">No snapshot yet.</p>
    <div class="table-wrap">
      <table><thead><tr><th>Symbol</th><th>Name</th><th>Value (USD)</th><th>Allocation</th></tr></thead>
      <tbody id="holdings-body"></tbody></table>
    </div>
    <h3 class="section-title">Snapshot History</h3>
    <p class="hint" id="snapshot-history-summary">Snapshot trend unavailable.</p>
    <div class="table-wrap">
      <table><thead><tr><th>As Of</th><th>Total Value (USD)</th><th>Net Perf (USD)</th></tr></thead>
      <tbody id="snapshot-history-body"></tbody></table>
    </div>`;
}

function renderSnapshot(snapshot) {
  byId('snapshot-total').textContent = `Total Value ${fmtCurrency(snapshot.total_value_usd)} | Net ${fmtCurrency(snapshot.net_performance_usd)} (${fmtPct(snapshot.net_performance_percent)})`;
  const tbody = byId('holdings-body');
  tbody.innerHTML = '';
  const top = (snapshot.holdings || []).slice(0, 12);
  for (const row of top) {
    const tr = document.createElement('tr');
    tr.innerHTML = `<td>${row.symbol || '-'}</td><td>${row.name || '-'}</td><td>${fmtCurrency(row.value_usd)}</td><td>${fmtPct(row.allocation_percent)}</td>`;
    tbody.appendChild(tr);
  }
  if (!top.length) tbody.innerHTML = '<tr><td colspan="4">No holdings in latest snapshot.</td></tr>';
}

function renderHistory(payload) {
  const el = byId('snapshot-history-summary');
  const tbody = byId('snapshot-history-body');
  tbody.innerHTML = '';
  const points = Array.isArray(payload?.points) ? payload.points : [];
  if (!points.length) {
    el.textContent = 'No snapshot history available yet.';
    tbody.innerHTML = '<tr><td colspan="3">Run sync multiple times to build trend history.</td></tr>';
    return;
  }
  el.textContent = `Window: ${payload.window_points || points.length} points | Delta total value: ${fmtCurrency(payload.delta_total_value_usd)} (${fmtPct(payload.delta_total_value_percent)})`;
  for (const p of points.slice(0, 10)) {
    const tr = document.createElement('tr');
    tr.innerHTML = `<td>${fmtDate(p.as_of)}</td><td>${fmtCurrency(p.total_value_usd)}</td><td>${fmtCurrency(p.net_performance_usd)}</td>`;
    tbody.appendChild(tr);
  }
}

async function load() {
  try { renderSnapshot(await fetchJson('/api/snapshot/latest')); }
  catch (e) {
    byId('snapshot-total').textContent = `Snapshot unavailable: ${e.message}`;
    byId('holdings-body').innerHTML = '<tr><td colspan="4">Run a sync to generate a snapshot.</td></tr>';
  }
  try { renderHistory(await fetchJson('/api/snapshot/history?limit=20')); }
  catch (e) {
    byId('snapshot-history-summary').textContent = `History unavailable: ${e.message}`;
    byId('snapshot-history-body').innerHTML = '<tr><td colspan="3">Snapshot history unavailable.</td></tr>';
  }
}

export function init() {
  byId('reload-snapshot').addEventListener('click', () => load().catch(e => writeLog(e.message, null, true)));
  load();
}
