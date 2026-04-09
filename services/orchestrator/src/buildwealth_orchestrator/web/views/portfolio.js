import { fetchJson } from '../lib/api.js';
import { byId, fmtCurrency, fmtPct, fmtDate, writeLog } from '../lib/utils.js';

export const id = 'portfolio';
export const label = 'Portfolio';
export const icon = '<svg viewBox="0 0 20 20" fill="none" stroke="currentColor" stroke-width="1.6"><polyline points="3,14 7,8 11,11 17,4"/><line x1="3" y1="17" x2="17" y2="17"/></svg>';

let accountNameById = new Map();

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

export function template() {
  const accountTypeOptions = ACCOUNT_TYPE_OPTIONS.map((type) => `<option value="${type}">${type}</option>`).join('');
  const customAssetTypeOptions = CUSTOM_ASSET_TYPE_OPTIONS.map((type) => `<option value="${type}">${type}</option>`).join('');
  const txnActionOptions = TRANSACTION_ACTION_OPTIONS.map(([value, label]) => `<option value="${value}">${label}</option>`).join('');
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
      <article class="kpi-card"><p class="kpi-label">Price Return</p><p class="kpi-value" id="port-price-return">-</p></article>
      <article class="kpi-card"><p class="kpi-label">Income Return</p><p class="kpi-value" id="port-income-return">-</p></article>
      <article class="kpi-card"><p class="kpi-label">TWR</p><p class="kpi-value" id="port-twr">-</p></article>
      <article class="kpi-card"><p class="kpi-label">XIRR</p><p class="kpi-value" id="port-xirr">-</p></article>
      <article class="kpi-card"><p class="kpi-label">Positions</p><p class="kpi-value" id="port-count">-</p></article>
      <article class="kpi-card"><p class="kpi-label">Prices Updated</p><p class="kpi-value" id="port-updated">-</p></article>
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
    <div class="table-wrap"><table>
      <thead><tr><th>Symbol</th><th>Account</th><th>CCY</th><th>Asset Class</th><th>Method</th><th>Qty</th><th>Avg Cost</th><th>Price</th><th>Value</th><th>Gain/Loss</th><th>Return</th><th>Alloc</th></tr></thead>
      <tbody id="port-holdings-body"><tr><td colspan="12">Loading...</td></tr></tbody>
    </table></div>
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
}

function renderHoldings(data) {
  const tbody = byId('port-holdings-body');
  const holdings = data.holdings || {};
  const manualPrices = data.manual_prices || {};
  const baseCurrency = String(data.base_currency || 'USD').toUpperCase();
  const total = data.total_value || 0;
  const entries = Object.values(holdings).sort((a, b) => (b.current_value || 0) - (a.current_value || 0));

  if (!entries.length) {
    tbody.innerHTML = '<tr><td colspan="12">No holdings. Add transactions to build your portfolio.</td></tr>';
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
  const breakdowns = data.allocation_breakdowns || {};
  renderBreakdownTable(breakdowns.asset_class, 'port-breakdown-asset-class');
  renderBreakdownTable(breakdowns.sector, 'port-breakdown-sector');
  renderBreakdownTable(breakdowns.region, 'port-breakdown-region');
}

function renderCustomAssets(data) {
  const tbody = byId('port-custom-assets-body');
  const rows = Object.values(data.holdings_by_symbol || {})
    .filter((row) => row?.is_custom_asset || String(row?.data_source || '').toUpperCase() === 'MANUAL')
    .sort((a, b) => (b.current_value || 0) - (a.current_value || 0));

  if (!rows.length) {
    tbody.innerHTML = '<tr><td colspan="6">No custom assets yet.</td></tr>';
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
    const [holdings, txns, accountRows] = await Promise.all([
      fetchJson('/api/portfolio/holdings'),
      fetchJson('/api/portfolio/transactions?limit=100'),
      fetchJson('/api/portfolio/accounts'),
    ]);
    renderAccounts(accountRows || holdings.accounts || [], holdings.account_totals || {});
    renderKPIs(holdings);
    renderFxRates(holdings);
    renderHoldings(holdings);
    renderBreakdowns(holdings);
    renderCustomAssets(holdings);
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
  byId('port-refresh-prices').addEventListener('click', refreshPrices);
  byId('port-txn-form').addEventListener('submit', addTxn);
  byId('port-account-form').addEventListener('submit', addAccount);
  byId('port-fx-form').addEventListener('submit', setFxRate);
  byId('port-custom-asset-form').addEventListener('submit', addCustomAsset);
  syncTxnFieldRequirements();
  loadAll();
}
