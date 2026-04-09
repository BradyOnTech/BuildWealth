import { fetchJson } from '../lib/api.js';
import { byId, fmtCurrency, fmtPct, fmtDate, writeLog } from '../lib/utils.js';

export const id = 'portfolio';
export const label = 'Portfolio';
export const icon = '<svg viewBox="0 0 20 20" fill="none" stroke="currentColor" stroke-width="1.6"><polyline points="3,14 7,8 11,11 17,4"/><line x1="3" y1="17" x2="17" y2="17"/></svg>';

let holdingsData = null;

export function template() {
  return `
    <div class="view-header">
      <h2>Portfolio</h2>
      <div class="header-actions">
        <button class="ghost small" id="port-reload">Reload</button>
        <button class="primary small" id="port-refresh-prices">Refresh Prices</button>
      </div>
    </div>
    <div class="kpi-row">
      <article class="kpi-card"><p class="kpi-label">Total Value</p><p class="kpi-value" id="port-total">-</p></article>
      <article class="kpi-card"><p class="kpi-label">Net Performance</p><p class="kpi-value" id="port-perf">-</p></article>
      <article class="kpi-card"><p class="kpi-label">Holdings</p><p class="kpi-value" id="port-count">-</p></article>
      <article class="kpi-card"><p class="kpi-label">Prices Updated</p><p class="kpi-value" id="port-updated">-</p></article>
    </div>
    <h3 class="section-title">Holdings</h3>
    <div class="table-wrap"><table>
      <thead><tr><th>Symbol</th><th>Qty</th><th>Avg Cost</th><th>Price</th><th>Value</th><th>Gain/Loss</th><th>Return</th><th>Alloc</th></tr></thead>
      <tbody id="port-holdings-body"><tr><td colspan="8">Loading...</td></tr></tbody>
    </table></div>
    <h3 class="section-title">Record Transaction</h3>
    <form id="port-txn-form" class="txn-form">
      <label class="field"><span>Date</span><input type="date" id="txn-date" required /></label>
      <label class="field"><span>Symbol</span><input type="text" id="txn-symbol" placeholder="AAPL" required /></label>
      <label class="field"><span>Action</span>
        <select id="txn-action"><option value="BUY">Buy</option><option value="SELL">Sell</option><option value="DIVIDEND">Dividend</option></select>
      </label>
      <label class="field"><span>Quantity</span><input type="number" id="txn-qty" step="0.0001" min="0" placeholder="10" required /></label>
      <label class="field"><span>Price</span><input type="number" id="txn-price" step="0.01" min="0" placeholder="150.00" required /></label>
      <label class="field"><span>Fee</span><input type="number" id="txn-fee" step="0.01" min="0" value="0" /></label>
      <button class="primary" type="submit">Add Transaction</button>
    </form>
    <h3 class="section-title">Transaction History</h3>
    <div class="table-wrap"><table>
      <thead><tr><th>Date</th><th>Symbol</th><th>Action</th><th>Qty</th><th>Price</th><th>Total</th><th>Fee</th><th></th></tr></thead>
      <tbody id="port-txn-body"><tr><td colspan="8">Loading...</td></tr></tbody>
    </table></div>`;
}

function renderKPIs(data) {
  holdingsData = data;
  const total = data.total_value || 0;
  const perf = data.net_performance || 0;
  const perfPct = data.net_performance_pct || 0;
  const count = Object.keys(data.holdings || {}).length;
  byId('port-total').textContent = fmtCurrency(total);
  const perfEl = byId('port-perf');
  perfEl.textContent = `${perf >= 0 ? '+' : ''}${fmtCurrency(perf)} (${perfPct >= 0 ? '+' : ''}${fmtPct(perfPct)})`;
  perfEl.className = `kpi-value ${perf >= 0 ? 'drift-pos' : 'drift-neg'}`;
  byId('port-count').textContent = String(count);
  byId('port-updated').textContent = data.prices_updated_at ? fmtDate(data.prices_updated_at) : 'Never';
}

function renderHoldings(data) {
  const tbody = byId('port-holdings-body');
  const holdings = data.holdings || {};
  const total = data.total_value || 0;
  const entries = Object.values(holdings).sort((a, b) => (b.current_value || 0) - (a.current_value || 0));

  if (!entries.length) { tbody.innerHTML = '<tr><td colspan="8">No holdings. Add transactions to build your portfolio.</td></tr>'; return; }

  tbody.innerHTML = '';
  for (const h of entries) {
    const value = h.current_value || 0;
    const cost = h.cost_basis || 0;
    const gain = value - cost;
    const gainPct = cost > 0 ? (gain / cost * 100) : 0;
    const alloc = total > 0 ? (value / total * 100) : 0;
    const cls = gain >= 0 ? 'drift-pos' : 'drift-neg';
    const sign = gain >= 0 ? '+' : '';

    const tr = document.createElement('tr');
    tr.innerHTML = `
      <td><strong>${h.symbol}</strong></td>
      <td>${h.quantity?.toFixed(2)}</td>
      <td>${fmtCurrency(h.avg_cost_per_share)}</td>
      <td>${h.current_price ? fmtCurrency(h.current_price) : '-'}</td>
      <td>${value ? fmtCurrency(value) : '-'}</td>
      <td class="${cls}">${sign}${fmtCurrency(gain)}</td>
      <td class="${cls}">${sign}${fmtPct(gainPct)}</td>
      <td>${fmtPct(alloc)}</td>`;
    tbody.appendChild(tr);
  }
}

function renderTransactions(txns) {
  const tbody = byId('port-txn-body');
  if (!txns.length) { tbody.innerHTML = '<tr><td colspan="8">No transactions recorded yet.</td></tr>'; return; }
  tbody.innerHTML = '';
  for (const t of txns) {
    const total = (t.quantity || 0) * (t.unit_price || 0);
    const tr = document.createElement('tr');
    const actionClass = t.action === 'BUY' ? 'drift-pos' : t.action === 'SELL' ? 'drift-neg' : '';
    tr.innerHTML = `
      <td>${t.date || '-'}</td>
      <td><strong>${t.symbol}</strong></td>
      <td class="${actionClass}">${t.action}</td>
      <td>${t.quantity}</td>
      <td>${fmtCurrency(t.unit_price)}</td>
      <td>${fmtCurrency(total)}</td>
      <td>${t.fee ? fmtCurrency(t.fee) : '-'}</td>
      <td></td>`;
    const delBtn = document.createElement('button');
    delBtn.className = 'ghost small';
    delBtn.textContent = 'Delete';
    delBtn.addEventListener('click', () => deleteTxn(t.id));
    tr.lastElementChild.appendChild(delBtn);
    tbody.appendChild(tr);
  }
}

async function loadAll() {
  try {
    const [holdings, txns] = await Promise.all([
      fetchJson('/api/portfolio/holdings'),
      fetchJson('/api/portfolio/transactions?limit=100'),
    ]);
    renderKPIs(holdings);
    renderHoldings(holdings);
    renderTransactions(txns);
  } catch (e) { writeLog(`Portfolio load failed: ${e.message}`, null, true); }
}

async function refreshPrices() {
  const btn = byId('port-refresh-prices');
  btn.disabled = true; btn.textContent = 'Refreshing...';
  try {
    await fetchJson('/api/portfolio/refresh-prices', { method: 'POST' });
    writeLog('Prices refreshed.');
    await loadAll();
  } catch (e) { writeLog(`Price refresh failed: ${e.message}`, null, true); }
  finally { btn.disabled = false; btn.textContent = 'Refresh Prices'; }
}

async function addTxn(event) {
  event.preventDefault();
  const payload = {
    date: byId('txn-date').value,
    symbol: byId('txn-symbol').value.trim().toUpperCase(),
    action: byId('txn-action').value,
    quantity: parseFloat(byId('txn-qty').value),
    unit_price: parseFloat(byId('txn-price').value),
    fee: parseFloat(byId('txn-fee').value || '0'),
  };
  if (!payload.symbol || !payload.quantity || !payload.unit_price) return;
  try {
    await fetchJson('/api/portfolio/transactions', {
      method: 'POST', headers: { 'content-type': 'application/json' },
      body: JSON.stringify(payload),
    });
    byId('txn-symbol').value = '';
    byId('txn-qty').value = '';
    byId('txn-price').value = '';
    byId('txn-fee').value = '0';
    writeLog(`Transaction added: ${payload.action} ${payload.quantity} ${payload.symbol}`);
    await loadAll();
  } catch (e) { writeLog(`Add transaction failed: ${e.message}`, null, true); }
}

async function deleteTxn(id) {
  try {
    await fetchJson(`/api/portfolio/transactions/${encodeURIComponent(id)}`, { method: 'DELETE' });
    writeLog(`Transaction deleted.`);
    await loadAll();
  } catch (e) { writeLog(`Delete failed: ${e.message}`, null, true); }
}

export function init() {
  byId('txn-date').valueAsDate = new Date();
  byId('port-reload').addEventListener('click', loadAll);
  byId('port-refresh-prices').addEventListener('click', refreshPrices);
  byId('port-txn-form').addEventListener('submit', addTxn);
  loadAll();
}
