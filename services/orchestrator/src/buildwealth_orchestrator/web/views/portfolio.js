import { fetchJson } from '../lib/api.js';
import { byId, fmtCurrency, fmtPct, fmtDate, writeLog } from '../lib/utils.js';

export const id = 'portfolio';
export const label = 'Portfolio';
export const icon = '<svg viewBox="0 0 20 20" fill="none" stroke="currentColor" stroke-width="1.6"><polyline points="3,14 7,8 11,11 17,4"/><line x1="3" y1="17" x2="17" y2="17"/></svg>';

let accountNameById = new Map();
let benchmarkSymbolsFilter = 'SPY';
let activeAccountFilter = '';
let latestHoldingsPayload = null;

const ACCOUNT_TYPE_OPTIONS = [
  'taxable',
  'traditional_ira',
  'roth_ira',
  'traditional_401k',
  'roth_401k',
  'hsa',
  '529',
  'savings',
  'checking',
];
const COST_BASIS_METHOD_OPTIONS = ['FIFO', 'LIFO', 'AVERAGE'];
const CUSTOM_ASSET_TYPE_OPTIONS = [
  'real_estate',
  'private_equity',
  'private_credit',
  'art_collectible',
  'business_equity',
  'custom_asset',
];
const TRANSACTION_ACTION_OPTIONS = [
  ['BUY', 'Buy'],
  ['SELL', 'Sell'],
  ['DIVIDEND', 'Dividend'],
  ['INTEREST', 'Interest'],
  ['FEE', 'Fee'],
  ['TRANSFER_IN', 'Transfer In'],
  ['TRANSFER_OUT', 'Transfer Out'],
  ['CASH_DEPOSIT', 'Cash Deposit'],
  ['CASH_WITHDRAW', 'Cash Withdraw'],
  ['STOCK_SPLIT', 'Stock Split'],
  ['MERGER', 'Merger'],
];
const SYMBOL_OPTIONAL_ACTIONS = new Set(['TRANSFER_IN', 'TRANSFER_OUT', 'CASH_DEPOSIT', 'CASH_WITHDRAW']);

function accountLabel(accountId) {
  if (!accountId) return '-';
  return accountNameById.get(accountId) || accountId;
}

function pctOrDash(value) {
  return Number.isFinite(value) ? fmtPct(value) : '-';
}

export function template() {
  const accountTypeOptions = ACCOUNT_TYPE_OPTIONS.map((type) => `<option value="${type}">${type}</option>`).join('');
  const customAssetTypeOptions = CUSTOM_ASSET_TYPE_OPTIONS.map((type) => `<option value="${type}">${type}</option>`).join('');
  const txnActionOptions = TRANSACTION_ACTION_OPTIONS.map(([value, label]) => `<option value="${value}">${label}</option>`).join('');
  return `
    <div class="view-header">
      <h2>Portfolio</h2>
      <div class="header-actions">
        <button class="ghost small" id="port-reload">Reload</button>
        <button class="ghost small" id="port-backfill-history-btn">Backfill History</button>
        <button class="primary small" id="port-refresh-prices">Refresh Prices</button>
      </div>
    </div>
    <div class="kpi-row">
      <article class="kpi-card"><p class="kpi-label">Total Value</p><p class="kpi-value" id="port-total">-</p></article>
      <article class="kpi-card"><p class="kpi-label">Net Performance</p><p class="kpi-value" id="port-perf">-</p></article>
      <article class="kpi-card"><p class="kpi-label">Price Return</p><p class="kpi-value" id="port-price-return">-</p></article>
      <article class="kpi-card"><p class="kpi-label">Income Return</p><p class="kpi-value" id="port-income-return">-</p></article>
      <article class="kpi-card"><p class="kpi-label">TWR</p><p class="kpi-value" id="port-twr">-</p></article>
      <article class="kpi-card"><p class="kpi-label">XIRR</p><p class="kpi-value" id="port-xirr">-</p></article>
      <article class="kpi-card"><p class="kpi-label">Positions</p><p class="kpi-value" id="port-count">-</p></article>
      <article class="kpi-card"><p class="kpi-label">Prices Updated</p><p class="kpi-value" id="port-updated">-</p></article>
    </div>

    <h3 class="section-title">Value History</h3>
    <p class="hint" id="port-history-summary">No historical snapshots yet.</p>
    <div class="history-toolbar">
      <label class="field">
        <span>Benchmark Symbols</span>
        <input type="text" id="port-benchmark-symbols" value="${benchmarkSymbolsFilter}" placeholder="SPY or SPY,QQQ" />
      </label>
      <button class="ghost small" id="port-benchmark-apply">Apply Benchmark</button>
      <p class="hint history-benchmark-note" id="port-benchmark-summary">Benchmark overlay not loaded yet.</p>
    </div>
    <form id="port-backfill-form" class="txn-form">
      <label class="field"><span>Days</span><input type="number" id="backfill-days" min="1" max="3650" placeholder="365" /></label>
      <label class="field"><span>Start Date</span><input type="date" id="backfill-start-date" /></label>
      <label class="field"><span>End Date</span><input type="date" id="backfill-end-date" /></label>
      <label class="field"><span>Overwrite</span><input type="checkbox" id="backfill-overwrite" checked /></label>
      <button class="primary" type="submit" id="port-backfill-submit">Run Backfill</button>
    </form>
    <div class="history-chart-card">
      <svg id="port-history-chart" viewBox="0 0 760 220" role="img" aria-label="Portfolio value history chart"></svg>
    </div>
    <div class="table-wrap">
      <table>
        <thead><tr><th>As Of</th><th>Total Value</th><th>Net Performance</th></tr></thead>
        <tbody id="port-history-body"><tr><td colspan="3">No history yet.</td></tr></tbody>
      </table>
    </div>

    <h3 class="section-title">Performance Attribution</h3>
    <p class="hint" id="port-attribution-summary">Attribution not loaded yet.</p>
    <div class="two-col">
      <div class="table-wrap">
        <table>
          <thead><tr><th colspan="5">Top Contributors</th></tr><tr><th>Position</th><th>Return</th><th>Contribution</th><th>Allocation</th><th>Class</th></tr></thead>
          <tbody id="port-attribution-contributors"><tr><td colspan="5">Loading...</td></tr></tbody>
        </table>
      </div>
      <div class="table-wrap">
        <table>
          <thead><tr><th colspan="5">Top Detractors</th></tr><tr><th>Position</th><th>Return</th><th>Contribution</th><th>Allocation</th><th>Class</th></tr></thead>
          <tbody id="port-attribution-detractors"><tr><td colspan="5">Loading...</td></tr></tbody>
        </table>
      </div>
    </div>

    <h3 class="section-title">Accounts</h3>
    <div class="table-wrap"><table>
      <thead><tr><th>Name</th><th>ID</th><th>Type</th><th>Currency</th><th>Cash</th><th>Market Value</th><th>Total</th></tr></thead>
      <tbody id="port-accounts-body"><tr><td colspan="7">Loading...</td></tr></tbody>
    </table></div>
    <form id="port-account-form" class="txn-form">
      <label class="field"><span>Name</span><input type="text" id="account-name" placeholder="Roth IRA" required /></label>
      <label class="field"><span>Type</span>
        <select id="account-type">${accountTypeOptions}</select>
      </label>
      <label class="field"><span>Currency</span><input type="text" id="account-currency" value="USD" maxlength="8" /></label>
      <button class="primary" type="submit">Add Account</button>
    </form>

    <h3 class="section-title">FX Rates</h3>
    <div class="table-wrap"><table>
      <thead><tr><th>Currency</th><th>Rate To Base</th><th>Base</th><th></th></tr></thead>
      <tbody id="port-fx-body"><tr><td colspan="4">Loading...</td></tr></tbody>
    </table></div>
    <form id="port-fx-form" class="txn-form">
      <label class="field"><span>Currency</span><input type="text" id="fx-currency" placeholder="EUR" maxlength="8" required /></label>
      <label class="field"><span>Rate To Base</span><input type="number" id="fx-rate" step="0.00000001" min="0" placeholder="1.0800" required /></label>
      <button class="primary" type="submit">Set FX Rate</button>
    </form>

    <h3 class="section-title">Holdings</h3>
    <div class="filter-bar">
      <label class="field compact-field"><span>Account</span><select id="port-account-filter"><option value="">All Accounts</option></select></label>
      <p class="hint tight" id="port-allocation-summary">Viewing all accounts.</p>
    </div>
    <div class="table-wrap"><table>
      <thead><tr><th>Symbol</th><th>Account</th><th>CCY</th><th>Asset Class</th><th>Method</th><th>Qty</th><th>Avg Cost</th><th>Price</th><th>Value</th><th>Gain/Loss</th><th>Return</th><th>Alloc</th></tr></thead>
      <tbody id="port-holdings-body"><tr><td colspan="12">Loading...</td></tr></tbody>
    </table></div>
    <div class="history-chart-card">
      <p class="hint tight">Allocation charts by asset class, sector, and region for the selected account scope.</p>
      <h4 class="section-title">Asset Class</h4>
      <div id="port-allocation-chart-asset-class" class="allocation-bar-list"></div>
      <h4 class="section-title">Sector</h4>
      <div id="port-allocation-chart-sector" class="allocation-bar-list"></div>
      <h4 class="section-title">Region</h4>
      <div id="port-allocation-chart-region" class="allocation-bar-list"></div>
    </div>
    <div class="table-wrap">
      <table>
        <thead><tr><th colspan="3">Asset Class Breakdown</th></tr><tr><th>Category</th><th>Value</th><th>Alloc</th></tr></thead>
        <tbody id="port-breakdown-asset-class"><tr><td colspan="3">Loading...</td></tr></tbody>
      </table>
    </div>
    <div class="table-wrap">
      <table>
        <thead><tr><th colspan="3">Sector Breakdown</th></tr><tr><th>Category</th><th>Value</th><th>Alloc</th></tr></thead>
        <tbody id="port-breakdown-sector"><tr><td colspan="3">Loading...</td></tr></tbody>
      </table>
    </div>
    <div class="table-wrap">
      <table>
        <thead><tr><th colspan="3">Region Breakdown</th></tr><tr><th>Category</th><th>Value</th><th>Alloc</th></tr></thead>
        <tbody id="port-breakdown-region"><tr><td colspan="3">Loading...</td></tr></tbody>
      </table>
    </div>

    <h3 class="section-title">Custom Assets</h3>
    <div class="table-wrap"><table>
      <thead><tr><th>Name</th><th>Symbol</th><th>Type</th><th>Value</th><th>Price Source</th><th>Positions</th></tr></thead>
      <tbody id="port-custom-assets-body"><tr><td colspan="6">Loading...</td></tr></tbody>
    </table></div>
    <form id="port-custom-asset-form" class="txn-form">
      <label class="field"><span>Name</span><input type="text" id="custom-asset-name" placeholder="Rental Property - Austin" required /></label>
      <label class="field"><span>Type</span><select id="custom-asset-type">${customAssetTypeOptions}</select></label>
      <label class="field"><span>Account</span><select id="custom-asset-account"></select></label>
      <label class="field"><span>Value</span><input type="number" id="custom-asset-value" step="0.01" min="0" placeholder="250000" required /></label>
      <button class="primary" type="submit">Add Custom Asset</button>
    </form>

    <h3 class="section-title">Watchlist</h3>
    <p class="hint" id="port-watchlist-summary">No watchlist items yet.</p>
    <div class="table-wrap"><table>
      <thead><tr><th>Symbol</th><th>Rank</th><th>Score</th><th>Last</th><th>Day</th><th>Window</th><th>Trend 50d</th><th>Trend 200d</th><th>Condition</th><th>Target</th><th>Tags</th><th>Note</th><th></th></tr></thead>
      <tbody id="port-watchlist-body"><tr><td colspan="13">No watchlist items yet.</td></tr></tbody>
    </table></div>
    <form id="port-watchlist-form" class="txn-form">
      <label class="field"><span>Symbol</span><input type="text" id="watchlist-symbol" placeholder="NVDA" required /></label>
      <label class="field"><span>Target Price</span><input type="number" id="watchlist-target-price" step="0.01" min="0" placeholder="Optional" /></label>
      <label class="field"><span>Tags</span><input type="text" id="watchlist-tags" placeholder="ai, quality, dividend" /></label>
      <label class="field"><span>Note</span><input type="text" id="watchlist-note" placeholder="Entry thesis" /></label>
      <button class="primary" type="submit">Add / Update Watchlist Item</button>
    </form>

    <h3 class="section-title">Record Transaction</h3>
    <form id="port-txn-form" class="txn-form">
      <label class="field"><span>Date</span><input type="date" id="txn-date" required /></label>
      <label class="field"><span>Account</span><select id="txn-account"></select></label>
      <label class="field"><span>Symbol</span><input type="text" id="txn-symbol" placeholder="AAPL" required /></label>
      <label class="field"><span>Action</span>
        <select id="txn-action">${txnActionOptions}</select>
      </label>
      <label class="field"><span>Quantity</span><input type="number" id="txn-qty" step="0.0001" min="0" placeholder="10" required /></label>
      <label class="field"><span>Price</span><input type="number" id="txn-price" step="0.01" min="0" placeholder="150.00" required /></label>
      <label class="field"><span>Fee</span><input type="number" id="txn-fee" step="0.01" min="0" value="0" /></label>
      <button class="primary" type="submit">Add Transaction</button>
    </form>

    <h3 class="section-title">Transaction History</h3>
    <div class="table-wrap"><table>
      <thead><tr><th>Date</th><th>Account</th><th>Symbol</th><th>Action</th><th>Qty</th><th>Price</th><th>Total</th><th>Fee</th><th></th></tr></thead>
      <tbody id="port-txn-body"><tr><td colspan="9">Loading...</td></tr></tbody>
    </table></div>`;
}

function renderKPIs(data) {
  const total = data.total_portfolio_value ?? data.total_value ?? 0;
  const perf = data.net_performance || 0;
  const perfPct = data.net_performance_pct || 0;
  const count = Object.keys(data.holdings || {}).length;
  const performance = data.performance || {};
  byId('port-total').textContent = fmtCurrency(total);

  const perfEl = byId('port-perf');
  perfEl.textContent = `${perf >= 0 ? '+' : ''}${fmtCurrency(perf)} (${perfPct >= 0 ? '+' : ''}${fmtPct(perfPct)})`;
  perfEl.className = `kpi-value ${perf >= 0 ? 'drift-pos' : 'drift-neg'}`;

  const priceReturn = performance.price_return_usd;
  const priceReturnPct = performance.price_return_pct;
  const priceReturnEl = byId('port-price-return');
  if (typeof priceReturn === 'number') {
    const signed = priceReturn >= 0 ? '+' : '';
    const pctText = typeof priceReturnPct === 'number' ? ` (${priceReturnPct >= 0 ? '+' : ''}${fmtPct(priceReturnPct)})` : '';
    priceReturnEl.textContent = `${signed}${fmtCurrency(priceReturn)}${pctText}`;
    priceReturnEl.className = `kpi-value ${priceReturn >= 0 ? 'drift-pos' : 'drift-neg'}`;
  } else {
    priceReturnEl.textContent = '-';
    priceReturnEl.className = 'kpi-value';
  }

  const incomeReturn = performance.income_return_usd;
  const incomeReturnPct = performance.income_return_pct;
  const incomeReturnEl = byId('port-income-return');
  if (typeof incomeReturn === 'number') {
    const signed = incomeReturn >= 0 ? '+' : '';
    const pctText = typeof incomeReturnPct === 'number' ? ` (${incomeReturnPct >= 0 ? '+' : ''}${fmtPct(incomeReturnPct)})` : '';
    incomeReturnEl.textContent = `${signed}${fmtCurrency(incomeReturn)}${pctText}`;
    incomeReturnEl.className = `kpi-value ${incomeReturn >= 0 ? 'drift-pos' : 'drift-neg'}`;
  } else {
    incomeReturnEl.textContent = '-';
    incomeReturnEl.className = 'kpi-value';
  }

  const twrEl = byId('port-twr');
  const twr = performance.twr_return_pct;
  twrEl.textContent = typeof twr === 'number' ? `${twr >= 0 ? '+' : ''}${fmtPct(twr)}` : '-';
  twrEl.className = `kpi-value ${typeof twr === 'number' ? (twr >= 0 ? 'drift-pos' : 'drift-neg') : ''}`;

  const xirrEl = byId('port-xirr');
  const xirr = performance.xirr_annualized_return_pct;
  xirrEl.textContent = typeof xirr === 'number' ? `${xirr >= 0 ? '+' : ''}${fmtPct(xirr)}` : '-';
  xirrEl.className = `kpi-value ${typeof xirr === 'number' ? (xirr >= 0 ? 'drift-pos' : 'drift-neg') : ''}`;

  byId('port-count').textContent = String(count);
  byId('port-updated').textContent = data.prices_updated_at ? fmtDate(data.prices_updated_at) : 'Never';
}

function renderAccounts(accountRows, accountTotals = {}) {
  const accounts = Array.isArray(accountRows) ? accountRows : [];
  accountNameById = new Map(accounts.map((account) => [account.id, account.name || account.id]));

  const tbody = byId('port-accounts-body');
  if (!accounts.length) {
    tbody.innerHTML = '<tr><td colspan="7">No accounts yet.</td></tr>';
  } else {
    tbody.innerHTML = '';
    for (const account of accounts) {
      const totals = accountTotals?.[account.id] || {};
      const tr = document.createElement('tr');
      tr.innerHTML = `
        <td><strong>${account.name || account.id}</strong></td>
        <td><code>${account.id}</code></td>
        <td>${account.type || '-'}</td>
        <td>${account.currency || 'USD'}</td>
        <td>${fmtCurrency(totals.cash_balance || 0)}</td>
        <td>${fmtCurrency(totals.market_value || 0)}</td>
        <td>${fmtCurrency(totals.total_value || 0)}</td>`;
      tbody.appendChild(tr);
    }
  }

  const accountSelect = byId('txn-account');
  accountSelect.innerHTML = '';
  if (!accounts.length) {
    accountSelect.innerHTML = '<option value="default">default</option>';
    return;
  }

  for (const account of accounts) {
    const option = document.createElement('option');
    option.value = account.id;
    option.textContent = `${account.name || account.id} (${account.type || 'taxable'})`;
    accountSelect.appendChild(option);
  }

  const customAccountSelect = byId('custom-asset-account');
  if (customAccountSelect) {
    customAccountSelect.innerHTML = accountSelect.innerHTML;
  }

  const accountFilterSelect = byId('port-account-filter');
  if (accountFilterSelect) {
    const previous = String(activeAccountFilter || '').trim();
    accountFilterSelect.innerHTML = '<option value="">All Accounts</option>';
    for (const account of accounts) {
      const option = document.createElement('option');
      option.value = account.id;
      option.textContent = `${account.name || account.id} (${account.type || 'taxable'})`;
      accountFilterSelect.appendChild(option);
    }
    const validValues = new Set(accounts.map((account) => account.id));
    activeAccountFilter = validValues.has(previous) ? previous : '';
    accountFilterSelect.value = activeAccountFilter;
  }
}

function filteredHoldingEntries(data) {
  const holdings = data?.holdings || {};
  const entries = Object.values(holdings);
  if (!activeAccountFilter) return entries;
  return entries.filter((holding) => String(holding?.account || '').trim() === activeAccountFilter);
}

function breakdownRowsFromEntries(entries, keyField) {
  const totals = new Map();
  let totalValue = 0;
  for (const entry of entries) {
    const key = String(entry?.[keyField] || 'Unknown').trim() || 'Unknown';
    const value = Number(entry?.current_value || 0);
    if (!Number.isFinite(value) || value <= 0) continue;
    totalValue += value;
    totals.set(key, Number(totals.get(key) || 0) + value);
  }

  const rows = [...totals.entries()]
    .map(([key, value]) => ({
      key,
      value,
      allocation_pct: totalValue > 0 ? (value / totalValue) * 100 : 0,
    }))
    .sort((left, right) => right.value - left.value);
  return rows;
}

function resolveBreakdownRows(data, entries) {
  if (!activeAccountFilter) {
    const breakdowns = data?.allocation_breakdowns || {};
    return {
      asset_class: Array.isArray(breakdowns.asset_class) ? breakdowns.asset_class : [],
      sector: Array.isArray(breakdowns.sector) ? breakdowns.sector : [],
      region: Array.isArray(breakdowns.region) ? breakdowns.region : [],
    };
  }
  return {
    asset_class: breakdownRowsFromEntries(entries, 'asset_class'),
    sector: breakdownRowsFromEntries(entries, 'sector'),
    region: breakdownRowsFromEntries(entries, 'region'),
  };
}

function renderAllocationBars(rows, containerId) {
  const container = byId(containerId);
  if (!container) return;
  const entries = Array.isArray(rows) ? rows : [];
  if (!entries.length) {
    container.innerHTML = '<p class="hint tight">No allocation data.</p>';
    return;
  }

  const maxAllocation = Math.max(...entries.map((row) => Number(row?.allocation_pct || 0)), 0);
  container.innerHTML = '';
  for (const row of entries.slice(0, 8)) {
    const allocation = Number(row?.allocation_pct || 0);
    const width = maxAllocation > 0 ? (allocation / maxAllocation) * 100 : 0;
    const line = document.createElement('div');
    line.className = 'allocation-bar-row';
    line.innerHTML = `
      <span class="allocation-bar-label">${row.key || '-'}</span>
      <span class="allocation-bar-track"><span class="allocation-bar-fill" style="width:${Math.max(0, Math.min(100, width)).toFixed(2)}%"></span></span>
      <span class="allocation-bar-metric">${fmtPct(allocation)}</span>`;
    container.appendChild(line);
  }
}

function updateAllocationSummary(filteredEntries) {
  const summary = byId('port-allocation-summary');
  if (!summary) return;
  const totalValue = filteredEntries.reduce((sum, entry) => sum + Number(entry?.current_value || 0), 0);
  const accountLabelText = activeAccountFilter ? accountLabel(activeAccountFilter) : 'All Accounts';
  summary.textContent = `${accountLabelText} | Holdings ${filteredEntries.length} | Value ${fmtCurrency(totalValue)}`;
}

function renderHoldings(data) {
  const tbody = byId('port-holdings-body');
  const manualPrices = data.manual_prices || {};
  const baseCurrency = String(data.base_currency || 'USD').toUpperCase();
  const entries = filteredHoldingEntries(data).sort((a, b) => (b.current_value || 0) - (a.current_value || 0));
  const total = entries.reduce((sum, item) => sum + Number(item.current_value || 0), 0);
  updateAllocationSummary(entries);

  if (!entries.length) {
    tbody.innerHTML = activeAccountFilter
      ? '<tr><td colspan="12">No holdings for this account filter.</td></tr>'
      : '<tr><td colspan="12">No holdings. Add transactions to build your portfolio.</td></tr>';
    return;
  }

  tbody.innerHTML = '';
  for (const h of entries) {
    const value = h.current_value || 0;
    const cost = h.cost_basis || 0;
    const gain = value - cost;
    const gainPct = cost > 0 ? (gain / cost * 100) : 0;
    const alloc = total > 0 ? (value / total * 100) : 0;
    const cls = gain >= 0 ? 'drift-pos' : 'drift-neg';
    const sign = gain >= 0 ? '+' : '';

    const manualEntry = manualPrices[h.symbol];
    const manualPriceValue = typeof manualEntry?.price === 'number' ? manualEntry.price : '';
    const priceSource = h.price_source || (manualEntry ? 'MANUAL' : '-');
    const currency = String(h.currency || baseCurrency).toUpperCase();
    const showNative = currency !== baseCurrency;
    const nativeAvgCost = Number.isFinite(h.avg_cost_per_share_native) ? h.avg_cost_per_share_native : null;
    const nativePrice = Number.isFinite(h.current_price_native) ? h.current_price_native : null;
    const nativeValue = Number.isFinite(h.current_value_native) ? h.current_value_native : null;
    const tr = document.createElement('tr');
    const currentMethod = COST_BASIS_METHOD_OPTIONS.includes(h.cost_basis_method) ? h.cost_basis_method : 'FIFO';
    const methodOptions = COST_BASIS_METHOD_OPTIONS.map((method) => `<option value="${method}" ${method === currentMethod ? 'selected' : ''}>${method}</option>`).join('');
    tr.innerHTML = `
      <td><strong>${h.symbol}</strong></td>
      <td>${accountLabel(h.account)}</td>
      <td><code>${currency}</code></td>
      <td>${h.asset_class || '-'}</td>
      <td>
        <select class="compact-method" data-symbol="${h.symbol}" data-account="${h.account}">${methodOptions}</select>
        <button class="ghost small" data-action="save-method" data-symbol="${h.symbol}" data-account="${h.account}">Set</button>
      </td>
      <td>${h.quantity?.toFixed(4)}</td>
      <td>
        <div>${fmtCurrency(h.avg_cost_per_share)}</div>
        ${showNative && nativeAvgCost !== null ? `<div class="muted">${nativeAvgCost.toFixed(4)} ${currency}</div>` : ''}
      </td>
      <td>
        <div>${h.current_price ? fmtCurrency(h.current_price) : '-'}</div>
        ${showNative && nativePrice !== null ? `<div class="muted">${nativePrice.toFixed(4)} ${currency}</div>` : ''}
        <div class="muted">${priceSource}</div>
        <div>
          <input type="number" class="compact-manual-price" data-symbol="${h.symbol}" step="0.0001" min="0" placeholder="Manual" value="${manualPriceValue}" />
          <button class="ghost small" data-action="set-manual" data-symbol="${h.symbol}">Set</button>
          <button class="ghost small" data-action="clear-manual" data-symbol="${h.symbol}">Clear</button>
        </div>
      </td>
      <td>
        <div>${value ? fmtCurrency(value) : '-'}</div>
        ${showNative && nativeValue !== null ? `<div class="muted">${nativeValue.toFixed(2)} ${currency}</div>` : ''}
      </td>
      <td class="${cls}">${sign}${fmtCurrency(gain)}</td>
      <td class="${cls}">${sign}${fmtPct(gainPct)}</td>
      <td>${fmtPct(alloc)}</td>`;
    const saveButton = tr.querySelector('button[data-action="save-method"]');
    if (saveButton) {
      saveButton.addEventListener('click', async () => {
        const selector = tr.querySelector('select.compact-method');
        const method = selector?.value || currentMethod;
        await setCostBasisMethod({ account: h.account, symbol: h.symbol, method });
      });
    }
    const setManualButton = tr.querySelector('button[data-action="set-manual"]');
    if (setManualButton) {
      setManualButton.addEventListener('click', async () => {
        const input = tr.querySelector('input.compact-manual-price');
        const price = parseFloat(input?.value || '');
        if (!Number.isFinite(price) || price <= 0) return;
        await setManualPrice({ symbol: h.symbol, price });
      });
    }
    const clearManualButton = tr.querySelector('button[data-action="clear-manual"]');
    if (clearManualButton) {
      clearManualButton.addEventListener('click', async () => {
        await clearManualPrice(h.symbol);
      });
    }
    tbody.appendChild(tr);
  }
}

function renderFxRates(data) {
  const tbody = byId('port-fx-body');
  const baseCurrency = String(data.base_currency || 'USD').toUpperCase();
  const rates = data.fx_rates || {};
  const entries = Object.entries(rates).sort((a, b) => a[0].localeCompare(b[0]));

  if (!entries.length) {
    tbody.innerHTML = '<tr><td colspan="4">No FX rates configured.</td></tr>';
    return;
  }

  tbody.innerHTML = '';
  for (const [currency, rawRate] of entries) {
    const rate = Number(rawRate);
    const tr = document.createElement('tr');
    tr.innerHTML = `
      <td><code>${currency}</code></td>
      <td>${Number.isFinite(rate) ? rate.toFixed(8) : '-'}</td>
      <td>${currency === baseCurrency ? 'Yes' : ''}</td>
      <td></td>`;
    if (currency !== baseCurrency) {
      const clearBtn = document.createElement('button');
      clearBtn.className = 'ghost small';
      clearBtn.textContent = 'Clear';
      clearBtn.addEventListener('click', () => clearFxRate(currency));
      tr.lastElementChild.appendChild(clearBtn);
    }
    tbody.appendChild(tr);
  }
}

function renderBreakdownTable(rows, tbodyId) {
  const tbody = byId(tbodyId);
  const entries = Array.isArray(rows) ? rows : [];
  if (!entries.length) {
    tbody.innerHTML = '<tr><td colspan="3">No data</td></tr>';
    return;
  }
  tbody.innerHTML = '';
  for (const row of entries) {
    const tr = document.createElement('tr');
    tr.innerHTML = `
      <td>${row.key || '-'}</td>
      <td>${fmtCurrency(row.value || 0)}</td>
      <td>${fmtPct(row.allocation_pct || 0)}</td>`;
    tbody.appendChild(tr);
  }
}

function renderBreakdowns(data) {
  const entries = filteredHoldingEntries(data);
  const breakdowns = resolveBreakdownRows(data, entries);
  renderBreakdownTable(breakdowns.asset_class, 'port-breakdown-asset-class');
  renderBreakdownTable(breakdowns.sector, 'port-breakdown-sector');
  renderBreakdownTable(breakdowns.region, 'port-breakdown-region');
  renderAllocationBars(breakdowns.asset_class, 'port-allocation-chart-asset-class');
  renderAllocationBars(breakdowns.sector, 'port-allocation-chart-sector');
  renderAllocationBars(breakdowns.region, 'port-allocation-chart-region');
}

function renderCustomAssets(data) {
  const tbody = byId('port-custom-assets-body');
  const rows = filteredHoldingEntries(data)
    .filter((row) => row?.is_custom_asset || String(row?.data_source || '').toUpperCase() === 'MANUAL')
    .sort((a, b) => (b.current_value || 0) - (a.current_value || 0));

  if (!rows.length) {
    tbody.innerHTML = activeAccountFilter
      ? '<tr><td colspan="6">No custom assets for this account filter.</td></tr>'
      : '<tr><td colspan="6">No custom assets yet.</td></tr>';
    return;
  }

  tbody.innerHTML = '';
  for (const row of rows) {
    const tr = document.createElement('tr');
    tr.innerHTML = `
      <td><strong>${row.name || row.symbol}</strong></td>
      <td><code>${row.symbol}</code></td>
      <td>${row.asset_type || 'custom_asset'}</td>
      <td>${fmtCurrency(row.current_value || 0)}</td>
      <td>${row.price_source || '-'}</td>
      <td>${row.position_count || 0}</td>`;
    tbody.appendChild(tr);
  }
}

function renderWatchlist(payload) {
  const summary = byId('port-watchlist-summary');
  const tbody = byId('port-watchlist-body');
  const rows = Array.isArray(payload?.items) ? payload.items : [];
  const warnings = Array.isArray(payload?.warnings) ? payload.warnings : [];
  const periodLabel = String(payload?.period || '').trim();
  const scoreModel = String(payload?.score_model || '').trim();
  const sortedBy = String(payload?.sorted_by || '').trim();
  const warningLabel = warnings.length ? ` | Warnings: ${warnings.length}` : '';

  if (!rows.length) {
    summary.textContent = warnings.length ? `No watchlist items yet.${warningLabel}` : 'No watchlist items yet.';
    tbody.innerHTML = '<tr><td colspan="13">No watchlist items yet.</td></tr>';
    return;
  }

  const topSymbol = rows[0]?.symbol || null;
  const rankingLabel = sortedBy ? ` | Sorted: ${sortedBy}` : '';
  const modelLabel = scoreModel ? ` | Model: ${scoreModel}` : '';
  const topLabel = topSymbol ? ` | Top: ${topSymbol}` : '';
  summary.textContent = `Items: ${rows.length}${periodLabel ? ` | Window: ${periodLabel}` : ''}${rankingLabel}${modelLabel}${topLabel}${warningLabel}`;
  tbody.innerHTML = '';
  for (const row of rows) {
    const quotePrice = Number(row.quote_price);
    const quoteChange = Number(row.quote_change_pct);
    const periodChange = Number(row.period_change_pct);
    const rank = Number(row.watchlist_rank);
    const scoreTotal = Number(row.watchlist_score_total);
    const score = row.watchlist_score && typeof row.watchlist_score === 'object' ? row.watchlist_score : {};
    const reasons = Array.isArray(row.watchlist_score_reasons) ? row.watchlist_score_reasons : [];
    const quoteClass = Number.isFinite(quoteChange) ? (quoteChange >= 0 ? 'drift-pos' : 'drift-neg') : '';
    const periodClass = Number.isFinite(periodChange) ? (periodChange >= 0 ? 'drift-pos' : 'drift-neg') : '';
    const scoreClass = Number.isFinite(scoreTotal) ? (scoreTotal >= 65 ? 'drift-pos' : scoreTotal < 45 ? 'drift-neg' : '') : '';
    const noteText = row.note || '-';
    const driverText = reasons.length ? ` Drivers: ${reasons.slice(0, 3).join(', ')}.` : '';
    const upside = Number(score?.upside_to_target_pct);
    const upsideText = Number.isFinite(upside) ? ` Upside-to-target: ${upside >= 0 ? '+' : ''}${fmtPct(upside)}.` : '';
    const tr = document.createElement('tr');
    tr.innerHTML = `
      <td><strong>${row.symbol || '-'}</strong></td>
      <td>${Number.isFinite(rank) && rank > 0 ? `#${Math.trunc(rank)}` : '-'}</td>
      <td class="${scoreClass}">${Number.isFinite(scoreTotal) ? scoreTotal.toFixed(1) : '-'}</td>
      <td>${Number.isFinite(quotePrice) ? fmtCurrency(quotePrice) : '-'}</td>
      <td class="${quoteClass}">${Number.isFinite(quoteChange) ? `${quoteChange >= 0 ? '+' : ''}${fmtPct(quoteChange)}` : '-'}</td>
      <td class="${periodClass}">${Number.isFinite(periodChange) ? `${periodChange >= 0 ? '+' : ''}${fmtPct(periodChange)}` : '-'}</td>
      <td>${row.trend50d || 'UNKNOWN'}</td>
      <td>${row.trend200d || 'UNKNOWN'}</td>
      <td>${row.market_condition || 'UNKNOWN'}</td>
      <td>${Number.isFinite(Number(row.target_price_usd)) ? fmtCurrency(Number(row.target_price_usd)) : '-'}</td>
      <td>${Array.isArray(row.tags) && row.tags.length ? row.tags.join(', ') : '-'}</td>
      <td>${noteText}${driverText}${upsideText}</td>
      <td></td>`;
    const removeBtn = document.createElement('button');
    removeBtn.className = 'ghost small';
    removeBtn.textContent = 'Remove';
    removeBtn.addEventListener('click', () => deleteWatchlistItem(row.symbol));
    tr.lastElementChild.appendChild(removeBtn);
    tbody.appendChild(tr);
  }
}

function renderHistory(historyPayload, benchmarkPayload = null) {
  const summary = byId('port-history-summary');
  const benchmarkSummary = byId('port-benchmark-summary');
  const tbody = byId('port-history-body');
  const chart = byId('port-history-chart');

  const points = Array.isArray(historyPayload?.points) ? historyPayload.points : [];
  if (!points.length) {
    summary.textContent = 'No snapshot history available. Run backfill or sync over multiple days.';
    if (benchmarkSummary) benchmarkSummary.textContent = 'Benchmark overlay unavailable: no history points.';
    tbody.innerHTML = '<tr><td colspan="3">No history yet.</td></tr>';
    chart.innerHTML = '';
    return;
  }

  const chron = [...points].reverse();
  const portfolioValues = chron.map((point) => Number(point.total_value_usd || 0));
  const firstPortfolioValue = portfolioValues[0] || 0;

  let benchmarkSymbol = null;
  let benchmarkValues = null;
  if (Array.isArray(benchmarkPayload?.series) && benchmarkPayload.series.length) {
    const symbolCandidates = Array.isArray(benchmarkPayload?.benchmark_symbols)
      ? benchmarkPayload.benchmark_symbols
      : [];
    const firstPointBench = benchmarkPayload.series[0]?.benchmark_index_by_symbol || {};
    benchmarkSymbol = symbolCandidates[0] || Object.keys(firstPointBench)[0] || null;
    if (benchmarkSymbol) {
      const indexByDate = new Map();
      for (const row of benchmarkPayload.series) {
        const key = String(row.date || '').slice(0, 10);
        const indexValue = Number(row.benchmark_index_by_symbol?.[benchmarkSymbol]);
        if (key && Number.isFinite(indexValue) && indexValue > 0) {
          indexByDate.set(key, indexValue);
        }
      }
      if (indexByDate.size) {
        let baseIndex = null;
        let previous = firstPortfolioValue;
        benchmarkValues = chron.map((point) => {
          const key = String(point.as_of || '').slice(0, 10);
          const indexValue = Number(indexByDate.get(key));
          if (Number.isFinite(indexValue) && indexValue > 0) {
            if (baseIndex === null) baseIndex = indexValue;
            previous = baseIndex > 0 ? firstPortfolioValue * (indexValue / baseIndex) : previous;
          }
          return previous;
        });
      }
    }
  }

  const values = benchmarkValues ? [...portfolioValues, ...benchmarkValues] : portfolioValues;
  const minValue = Math.min(...values);
  const maxValue = Math.max(...values);
  const valueRange = Math.max(maxValue - minValue, 1);

  const width = 760;
  const height = 220;
  const left = 44;
  const right = 18;
  const top = 12;
  const bottom = 30;
  const plotWidth = width - left - right;
  const plotHeight = height - top - bottom;

  const toCoords = (seriesValues) => seriesValues.map((value, index) => {
    const x = left + (chron.length === 1 ? 0 : (index / (chron.length - 1)) * plotWidth);
    const y = top + ((maxValue - value) / valueRange) * plotHeight;
    return { x, y, value, asOf: chron[index]?.as_of };
  });
  const coords = toCoords(portfolioValues);
  const benchmarkCoords = benchmarkValues ? toCoords(benchmarkValues) : null;

  const linePath = coords.map((c, i) => `${i === 0 ? 'M' : 'L'} ${c.x.toFixed(2)} ${c.y.toFixed(2)}`).join(' ');
  const benchmarkPath = benchmarkCoords
    ? benchmarkCoords.map((c, i) => `${i === 0 ? 'M' : 'L'} ${c.x.toFixed(2)} ${c.y.toFixed(2)}`).join(' ')
    : '';
  const areaPath = [
    `M ${coords[0].x.toFixed(2)} ${(top + plotHeight).toFixed(2)}`,
    ...coords.map((c) => `L ${c.x.toFixed(2)} ${c.y.toFixed(2)}`),
    `L ${coords[coords.length - 1].x.toFixed(2)} ${(top + plotHeight).toFixed(2)}`,
    'Z',
  ].join(' ');

  const yTicks = 4;
  const grid = [];
  for (let i = 0; i <= yTicks; i += 1) {
    const ratio = i / yTicks;
    const y = top + ratio * plotHeight;
    const tickValue = maxValue - ratio * valueRange;
    grid.push(`<line x1="${left}" y1="${y.toFixed(2)}" x2="${(left + plotWidth).toFixed(2)}" y2="${y.toFixed(2)}" class="history-grid-line"></line>`);
    grid.push(`<text x="4" y="${(y + 4).toFixed(2)}" class="history-axis-label">${fmtCurrency(tickValue)}</text>`);
  }

  const firstDate = chron[0]?.as_of ? fmtDate(chron[0].as_of) : '-';
  const lastDate = chron[chron.length - 1]?.as_of ? fmtDate(chron[chron.length - 1].as_of) : '-';
  chart.innerHTML = `
    ${grid.join('')}
    <path d="${areaPath}" class="history-area"></path>
    <path d="${linePath}" class="history-line"></path>
    ${benchmarkPath ? `<path d="${benchmarkPath}" class="history-line history-line-benchmark"></path>` : ''}
    <text x="${left}" y="${height - 8}" class="history-axis-label">${firstDate}</text>
    <text x="${(left + plotWidth - 72).toFixed(2)}" y="${height - 8}" class="history-axis-label">${lastDate}</text>
  `;

  summary.textContent = `Window: ${historyPayload.window_points || points.length} points | Delta total value: ${fmtCurrency(historyPayload.delta_total_value_usd || 0)} (${fmtPct(historyPayload.delta_total_value_percent || 0)})`;
  if (benchmarkSummary) {
    if (!benchmarkPayload || !benchmarkSymbol) {
      benchmarkSummary.textContent = 'Benchmark overlay unavailable.';
    } else {
      const benchReturn = Number(benchmarkPayload.summary?.benchmark_return_pct_by_symbol?.[benchmarkSymbol]);
      const alphaPct = Number(benchmarkPayload.summary?.alpha_pct_by_symbol?.[benchmarkSymbol]);
      const engineStatus = benchmarkPayload.engine_status || 'unknown';
      const fallback = benchmarkPayload.fallback_method ? ` (${benchmarkPayload.fallback_method})` : '';
      benchmarkSummary.textContent = `${benchmarkSymbol}: ${pctOrDash(benchReturn)} | Alpha: ${pctOrDash(alphaPct)} | Engine: ${engineStatus}${fallback}`;
    }
  }

  tbody.innerHTML = '';
  for (const point of points.slice(0, 14)) {
    const tr = document.createElement('tr');
    tr.innerHTML = `
      <td>${fmtDate(point.as_of)}</td>
      <td>${fmtCurrency(point.total_value_usd || 0)}</td>
      <td>${fmtCurrency(point.net_performance_usd || 0)}</td>`;
    tbody.appendChild(tr);
  }
}

function renderAttributionRows(rows, tbodyId, emptyText) {
  const tbody = byId(tbodyId);
  const entries = Array.isArray(rows) ? rows : [];
  if (!entries.length) {
    tbody.innerHTML = `<tr><td colspan="5">${emptyText}</td></tr>`;
    return;
  }

  tbody.innerHTML = '';
  for (const row of entries) {
    const totalReturn = Number(row.total_return_base || 0);
    const contribution = Number(row.contribution_pct || 0);
    const cls = totalReturn >= 0 ? 'drift-pos' : 'drift-neg';
    const sign = totalReturn >= 0 ? '+' : '';
    const tr = document.createElement('tr');
    tr.innerHTML = `
      <td><strong>${row.symbol || '-'}</strong>${row.account_id ? `<div class="muted">${accountLabel(row.account_id)}</div>` : ''}</td>
      <td class="${cls}">${sign}${fmtCurrency(totalReturn)}</td>
      <td class="${cls}">${contribution >= 0 ? '+' : ''}${fmtPct(contribution)}</td>
      <td>${fmtPct(Number(row.allocation_pct || 0))}</td>
      <td>${row.asset_class || '-'}</td>`;
    tbody.appendChild(tr);
  }
}

function renderAttribution(payload) {
  const summary = byId('port-attribution-summary');
  const contributors = byId('port-attribution-contributors');
  const detractors = byId('port-attribution-detractors');

  if (!payload || typeof payload !== 'object') {
    summary.textContent = 'Attribution unavailable.';
    contributors.innerHTML = '<tr><td colspan="5">No contributor data.</td></tr>';
    detractors.innerHTML = '<tr><td colspan="5">No detractor data.</td></tr>';
    return;
  }

  const totalReturn = Number(payload.summary?.portfolio_total_return_base || 0);
  const accounted = Number(payload.summary?.accounted_return_base || 0);
  const residual = Number(payload.summary?.residual_return_base || 0);
  const engineStatus = payload.engine_status || 'unknown';
  const fallback = payload.fallback_method ? ` (${payload.fallback_method})` : '';
  summary.textContent = `Total return: ${fmtCurrency(totalReturn)} | Accounted: ${fmtCurrency(accounted)} | Residual: ${fmtCurrency(residual)} | Engine: ${engineStatus}${fallback}`;

  renderAttributionRows(payload.contributors, 'port-attribution-contributors', 'No positive contributors in this window.');
  renderAttributionRows(payload.detractors, 'port-attribution-detractors', 'No detractors in this window.');
}

function renderTransactions(txns) {
  const tbody = byId('port-txn-body');
  if (!txns.length) {
    tbody.innerHTML = '<tr><td colspan="9">No transactions recorded yet.</td></tr>';
    return;
  }

  tbody.innerHTML = '';
  for (const t of txns) {
    const total = (t.quantity || 0) * (t.unit_price || 0);
    const tr = document.createElement('tr');
    const actionClass = ['BUY', 'TRANSFER_IN', 'CASH_DEPOSIT', 'DIVIDEND', 'INTEREST'].includes(t.action)
      ? 'drift-pos'
      : ['SELL', 'TRANSFER_OUT', 'CASH_WITHDRAW', 'FEE'].includes(t.action)
        ? 'drift-neg'
        : '';
    tr.innerHTML = `
      <td>${t.date || '-'}</td>
      <td>${accountLabel(t.account)}</td>
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
    const benchmarkQuery = benchmarkSymbolsFilter ? `&symbols=${encodeURIComponent(benchmarkSymbolsFilter)}` : '';
    const [holdingsResult, txnsResult, accountResult, historyResult, benchmarkResult, attributionResult, watchlistResult] = await Promise.allSettled([
      fetchJson('/api/portfolio/holdings'),
      fetchJson('/api/portfolio/transactions?limit=100'),
      fetchJson('/api/portfolio/accounts'),
      fetchJson('/api/snapshot/history?limit=120'),
      fetchJson(`/api/portfolio/benchmark?limit=120${benchmarkQuery}`),
      fetchJson('/api/portfolio/attribution?top_n=6'),
      fetchJson('/api/research/watchlist-rank?period=2y&interval=1d&limit=200'),
    ]);

    if (holdingsResult.status !== 'fulfilled') throw holdingsResult.reason;
    if (txnsResult.status !== 'fulfilled') throw txnsResult.reason;
    if (accountResult.status !== 'fulfilled') throw accountResult.reason;

    const holdings = holdingsResult.value;
    latestHoldingsPayload = holdings;
    const txns = txnsResult.value;
    const accountRows = accountResult.value;
    renderAccounts(accountRows || holdings.accounts || [], holdings.account_totals || {});
    renderKPIs(holdings);
    if (historyResult.status === 'fulfilled') {
      renderHistory(
        historyResult.value,
        benchmarkResult.status === 'fulfilled' ? benchmarkResult.value : null,
      );
    } else {
      renderHistory(null, null);
    }
    renderAttribution(attributionResult.status === 'fulfilled' ? attributionResult.value : null);
    renderFxRates(holdings);
    renderHoldings(holdings);
    renderBreakdowns(holdings);
    renderCustomAssets(holdings);
    renderWatchlist(watchlistResult.status === 'fulfilled' ? watchlistResult.value : null);
    renderTransactions(txns);
  } catch (e) {
    writeLog(`Portfolio load failed: ${e.message}`, null, true);
  }
}

async function refreshPrices() {
  const btn = byId('port-refresh-prices');
  btn.disabled = true;
  btn.textContent = 'Refreshing...';
  try {
    await fetchJson('/api/portfolio/refresh-prices', { method: 'POST' });
    writeLog('Prices refreshed.');
    await loadAll();
  } catch (e) {
    writeLog(`Price refresh failed: ${e.message}`, null, true);
  } finally {
    btn.disabled = false;
    btn.textContent = 'Refresh Prices';
  }
}

async function addTxn(event) {
  event.preventDefault();
  const action = byId('txn-action').value;
  let symbol = byId('txn-symbol').value.trim().toUpperCase();
  if (!symbol && SYMBOL_OPTIONAL_ACTIONS.has(action)) {
    symbol = 'CASH';
  }
  const payload = {
    date: byId('txn-date').value,
    account: byId('txn-account').value || 'default',
    symbol,
    action,
    quantity: parseFloat(byId('txn-qty').value),
    unit_price: parseFloat(byId('txn-price').value),
    fee: parseFloat(byId('txn-fee').value || '0'),
  };
  if (!payload.symbol || !Number.isFinite(payload.quantity) || !Number.isFinite(payload.unit_price)) return;

  try {
    await fetchJson('/api/portfolio/transactions', {
      method: 'POST',
      headers: { 'content-type': 'application/json' },
      body: JSON.stringify(payload),
    });
    byId('txn-symbol').value = '';
    byId('txn-qty').value = '';
    byId('txn-price').value = '';
    byId('txn-fee').value = '0';
    writeLog(`Transaction added: ${payload.action} ${payload.quantity} ${payload.symbol}`);
    await loadAll();
  } catch (e) {
    writeLog(`Add transaction failed: ${e.message}`, null, true);
  }
}

function syncTxnFieldRequirements() {
  const action = byId('txn-action').value;
  const symbolInput = byId('txn-symbol');
  if (SYMBOL_OPTIONAL_ACTIONS.has(action)) {
    symbolInput.required = false;
    symbolInput.placeholder = 'Optional (defaults to CASH)';
  } else {
    symbolInput.required = true;
    symbolInput.placeholder = 'AAPL';
  }
}

async function addAccount(event) {
  event.preventDefault();
  const payload = {
    name: byId('account-name').value.trim(),
    type: byId('account-type').value,
    currency: (byId('account-currency').value || 'USD').trim().toUpperCase(),
  };
  if (!payload.name) return;

  try {
    await fetchJson('/api/portfolio/accounts', {
      method: 'POST',
      headers: { 'content-type': 'application/json' },
      body: JSON.stringify(payload),
    });
    byId('account-name').value = '';
    byId('account-currency').value = 'USD';
    writeLog(`Account added: ${payload.name}`);
    await loadAll();
  } catch (e) {
    writeLog(`Add account failed: ${e.message}`, null, true);
  }
}

async function addCustomAsset(event) {
  event.preventDefault();
  const payload = {
    name: byId('custom-asset-name').value.trim(),
    asset_type: byId('custom-asset-type').value,
    account: byId('custom-asset-account').value || 'default',
    value: parseFloat(byId('custom-asset-value').value),
  };
  if (!payload.name || !Number.isFinite(payload.value) || payload.value <= 0) return;

  try {
    await fetchJson('/api/portfolio/custom-assets', {
      method: 'POST',
      headers: { 'content-type': 'application/json' },
      body: JSON.stringify(payload),
    });
    byId('custom-asset-name').value = '';
    byId('custom-asset-value').value = '';
    writeLog(`Custom asset added: ${payload.name}`);
    await loadAll();
  } catch (e) {
    writeLog(`Add custom asset failed: ${e.message}`, null, true);
  }
}

async function addWatchlistItem(event) {
  event.preventDefault();
  const symbol = (byId('watchlist-symbol').value || '').trim().toUpperCase();
  const targetPriceRaw = (byId('watchlist-target-price').value || '').trim();
  const tagsRaw = (byId('watchlist-tags').value || '').trim();
  const note = (byId('watchlist-note').value || '').trim();
  if (!symbol) return;

  const payload = { symbol, note };
  if (targetPriceRaw) {
    const target = parseFloat(targetPriceRaw);
    if (!Number.isFinite(target) || target <= 0) {
      writeLog('Target price must be a positive number.', null, true);
      return;
    }
    payload.target_price_usd = target;
  }
  if (tagsRaw) {
    payload.tags = tagsRaw.split(',').map(tag => tag.trim()).filter(Boolean);
  }

  try {
    await fetchJson('/api/portfolio/watchlist', {
      method: 'POST',
      headers: { 'content-type': 'application/json' },
      body: JSON.stringify(payload),
    });
    byId('watchlist-symbol').value = '';
    byId('watchlist-target-price').value = '';
    byId('watchlist-tags').value = '';
    byId('watchlist-note').value = '';
    writeLog(`Watchlist item upserted: ${symbol}`);
    await loadAll();
  } catch (e) {
    writeLog(`Watchlist update failed: ${e.message}`, null, true);
  }
}

async function deleteWatchlistItem(symbol) {
  const normalized = String(symbol || '').trim().toUpperCase();
  if (!normalized) return;
  try {
    await fetchJson(`/api/portfolio/watchlist/${encodeURIComponent(normalized)}`, { method: 'DELETE' });
    writeLog(`Watchlist item removed: ${normalized}`);
    await loadAll();
  } catch (e) {
    writeLog(`Watchlist remove failed: ${e.message}`, null, true);
  }
}

async function setCostBasisMethod({ account, symbol, method }) {
  try {
    await fetchJson('/api/portfolio/cost-basis-methods', {
      method: 'PUT',
      headers: { 'content-type': 'application/json' },
      body: JSON.stringify({ account, symbol, method }),
    });
    writeLog(`Cost basis method set: ${symbol} (${accountLabel(account)}) -> ${method}`);
    await loadAll();
  } catch (e) {
    writeLog(`Set cost basis method failed: ${e.message}`, null, true);
  }
}

async function setManualPrice({ symbol, price }) {
  try {
    await fetchJson('/api/portfolio/manual-prices', {
      method: 'PUT',
      headers: { 'content-type': 'application/json' },
      body: JSON.stringify({ symbol, price }),
    });
    writeLog(`Manual price set: ${symbol} -> ${fmtCurrency(price)}`);
    await loadAll();
  } catch (e) {
    writeLog(`Set manual price failed: ${e.message}`, null, true);
  }
}

async function clearManualPrice(symbol) {
  try {
    await fetchJson(`/api/portfolio/manual-prices/${encodeURIComponent(symbol)}`, { method: 'DELETE' });
    writeLog(`Manual price cleared: ${symbol}`);
    await loadAll();
  } catch (e) {
    writeLog(`Clear manual price failed: ${e.message}`, null, true);
  }
}

async function setFxRate(event) {
  event.preventDefault();
  const currency = (byId('fx-currency').value || '').trim().toUpperCase();
  const rate = parseFloat(byId('fx-rate').value || '');
  if (!currency || !Number.isFinite(rate) || rate <= 0) return;
  try {
    await fetchJson('/api/portfolio/fx-rates', {
      method: 'PUT',
      headers: { 'content-type': 'application/json' },
      body: JSON.stringify({ currency, rate }),
    });
    byId('fx-currency').value = '';
    byId('fx-rate').value = '';
    writeLog(`FX rate set: ${currency} -> ${rate}`);
    await loadAll();
  } catch (e) {
    writeLog(`Set FX rate failed: ${e.message}`, null, true);
  }
}

async function clearFxRate(currency) {
  try {
    await fetchJson(`/api/portfolio/fx-rates/${encodeURIComponent(currency)}`, { method: 'DELETE' });
    writeLog(`FX rate cleared: ${currency}`);
    await loadAll();
  } catch (e) {
    writeLog(`Clear FX rate failed: ${e.message}`, null, true);
  }
}

function buildBackfillPayload() {
  const payload = {};
  const daysValue = byId('backfill-days').value;
  const startDate = byId('backfill-start-date').value;
  const endDate = byId('backfill-end-date').value;
  if (daysValue) {
    const days = parseInt(daysValue, 10);
    if (Number.isFinite(days) && days > 0) payload.days = days;
  }
  if (startDate) payload.start_date = startDate;
  if (endDate) payload.end_date = endDate;
  payload.overwrite = byId('backfill-overwrite').checked;
  return payload;
}

async function runBackfill() {
  const submit = byId('port-backfill-submit');
  const prevText = submit.textContent;
  submit.disabled = true;
  submit.textContent = 'Backfilling...';
  try {
    const result = await fetchJson('/api/snapshot/backfill-history', {
      method: 'POST',
      headers: { 'content-type': 'application/json' },
      body: JSON.stringify(buildBackfillPayload()),
    });
    writeLog(`Backfill completed: wrote ${result.days_written || 0}, skipped ${result.days_skipped || 0}.`);
    await loadAll();
  } catch (e) {
    writeLog(`Backfill failed: ${e.message}`, null, true);
  } finally {
    submit.disabled = false;
    submit.textContent = prevText;
  }
}

async function backfillHistory(event) {
  event.preventDefault();
  await runBackfill();
}

async function backfillHistoryFromHeader() {
  await runBackfill();
}

function applyBenchmarkSymbols() {
  const raw = byId('port-benchmark-symbols').value || '';
  benchmarkSymbolsFilter = raw.trim().toUpperCase();
  loadAll();
}

function applyAccountFilter() {
  activeAccountFilter = String(byId('port-account-filter')?.value || '').trim();
  if (!latestHoldingsPayload) return;
  renderHoldings(latestHoldingsPayload);
  renderBreakdowns(latestHoldingsPayload);
  renderCustomAssets(latestHoldingsPayload);
}

async function deleteTxn(id) {
  try {
    await fetchJson(`/api/portfolio/transactions/${encodeURIComponent(id)}`, { method: 'DELETE' });
    writeLog('Transaction deleted.');
    await loadAll();
  } catch (e) {
    writeLog(`Delete failed: ${e.message}`, null, true);
  }
}

export function init() {
  byId('txn-date').valueAsDate = new Date();
  byId('txn-action').addEventListener('change', syncTxnFieldRequirements);
  byId('port-reload').addEventListener('click', loadAll);
  byId('port-benchmark-apply').addEventListener('click', applyBenchmarkSymbols);
  byId('port-account-filter').addEventListener('change', applyAccountFilter);
  byId('port-backfill-history-btn').addEventListener('click', backfillHistoryFromHeader);
  byId('port-refresh-prices').addEventListener('click', refreshPrices);
  byId('port-txn-form').addEventListener('submit', addTxn);
  byId('port-backfill-form').addEventListener('submit', backfillHistory);
  byId('port-account-form').addEventListener('submit', addAccount);
  byId('port-fx-form').addEventListener('submit', setFxRate);
  byId('port-custom-asset-form').addEventListener('submit', addCustomAsset);
  byId('port-watchlist-form').addEventListener('submit', addWatchlistItem);
  syncTxnFieldRequirements();
  loadAll();
}
