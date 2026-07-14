// The portfolio front door — "Add to portfolio" on Standing.
// Four plain flows (Investment / Cash / Property / Import a statement) hide
// the ledger vocabulary: a BUY, SELL, or TRANSFER_IN transaction, a
// CASH_DEPOSIT, or a custom asset + manual price, all via POST /api/portfolio/add.
// Two required fields per flow; everything else waits behind "More detail".

import { api } from '../../lib/api.js';
import { html, raw, esc, setView } from '../../lib/dom.js';

// Survives the full-view re-render that follows a successful add, so the
// card stays open with its success line showing (same idiom as railState).
export const addFlowState = {
  open: false,
  tab: 'investment',
  result: null,
  prefill: null, // { symbol, account, action }
};

export const ADD_FLOW_TABS = [
  ['investment', 'Investment'],
  ['cash', 'Cash'],
  ['property', 'Property'],
];

export function renderAddFlow(data = {}) {
  const accounts = Array.isArray(data.accounts) ? data.accounts : [];
  const prefill = addFlowState.prefill || {};
  return html`
    <div class="portfolio-add" data-add-flow>
      <button type="button" class="portfolio-add-button" data-add-open aria-expanded="${String(addFlowState.open)}">
        Add to portfolio
      </button>
      <article class="portfolio-add-card" data-add-card ${addFlowState.open ? '' : raw('hidden')}>
        <nav class="portfolio-add-tabs" role="tablist" aria-label="What are you adding?">
          ${raw(ADD_FLOW_TABS.map(([id, label]) => `
            <button type="button" role="tab" data-add-tab="${esc(id)}"
              aria-selected="${addFlowState.tab === id ? 'true' : 'false'}">${esc(label)}</button>
          `).join(''))}
          <a class="portfolio-add-import" href="#import-sync" data-route>Import a statement</a>
        </nav>
        ${raw(renderInvestmentPanel(accounts, prefill))}
        ${raw(renderCashPanel(accounts))}
        ${raw(renderPropertyPanel(accounts))}
        <p class="portfolio-add-status" data-add-status ${addFlowState.result ? '' : raw('hidden')}>
          ${addFlowState.result ? raw(String(renderAddResult(addFlowState.result))) : ''}
        </p>
      </article>
    </div>
  `;
}

function renderInvestmentPanel(accounts, prefill = {}) {
  const action = prefill.action === 'SELL' ? 'SELL' : 'BUY';
  return html`
    <form class="portfolio-add-panel" data-add-panel="investment" ${panelHidden('investment')}>
      <div class="portfolio-add-toggle" role="radiogroup" aria-label="Buy or sell">
        <label class="portfolio-add-chip"><input type="radio" name="action" value="BUY" ${action === 'BUY' ? 'checked' : ''}> Buy</label>
        <label class="portfolio-add-chip"><input type="radio" name="action" value="SELL" ${action === 'SELL' ? 'checked' : ''}> Sell</label>
      </div>
      <label class="fit-field">
        <span>Symbol</span>
        <input name="symbol" type="text" autocomplete="off" list="portfolio-add-symbols"
          placeholder="VTI" maxlength="24" value="${esc(prefill.symbol || '')}" required>
      </label>
      <datalist id="portfolio-add-symbols"></datalist>
      <div class="portfolio-add-either">
        <label class="fit-field"><span>Shares</span>
          <input name="quantity" type="number" step="any" min="0" inputmode="decimal" placeholder="10">
        </label>
        <span class="portfolio-add-or">or</span>
        <label class="fit-field"><span>Current value (USD)</span>
          <input name="value_usd" type="number" step="any" min="0" inputmode="decimal" placeholder="2500">
        </label>
      </div>
      <label class="fit-field"><span>What you paid per share <small>(estimate is okay)</small></span>
        <input name="unit_cost" type="number" step="any" min="0" inputmode="decimal"
          placeholder="Needed when a current quote is unavailable">
      </label>
      ${raw(renderAccountField(accounts, prefill.account || ''))}
      <details class="portfolio-add-more">
        <summary>More detail</summary>
        <label class="fit-field"><span>Date acquired</span>
          <input name="acquired_date" type="date">
        </label>
      </details>
      <button class="fit-review-button" type="submit">Add investment</button>
    </form>
  `;
}

function renderCashPanel(accounts) {
  return html`
    <form class="portfolio-add-panel" data-add-panel="cash" ${panelHidden('cash')}>
      ${raw(renderAccountField(accounts, ''))}
      <label class="fit-field"><span>Amount (USD)</span>
        <input name="amount_usd" type="number" step="any" min="0" inputmode="decimal" placeholder="5000" required>
      </label>
      <button class="fit-review-button" type="submit">Add cash</button>
    </form>
  `;
}

function renderPropertyPanel(accounts) {
  return html`
    <form class="portfolio-add-panel" data-add-panel="property" ${panelHidden('property')}>
      <label class="fit-field"><span>What is it?</span>
        <input name="label" type="text" placeholder="Home, 2021 Subaru, art collection" required>
      </label>
      <label class="fit-field"><span>Worth today (USD)</span>
        <input name="value_usd" type="number" step="any" min="0" inputmode="decimal" placeholder="450000" required>
      </label>
      <label class="fit-field"><span>Type</span>
        <select name="asset_type">
          <option value="real_estate">Real estate</option>
          <option value="vehicle">Vehicle</option>
          <option value="other" selected>Something else</option>
        </select>
      </label>
      <button class="fit-review-button" type="submit">Add asset</button>
    </form>
  `;
}

function renderAccountField(accounts, selectedId = '') {
  const options = accounts.map((account) => {
    const id = String(account?.id || '').trim();
    if (!id) return '';
    const selected = id === String(selectedId || '') ? ' selected' : '';
    return `<option value="${esc(id)}"${selected}>${esc(account.name || id)}</option>`;
  }).join('');
  return html`
    <label class="fit-field">
      <span>Account</span>
      <select name="account_id">
        ${raw(options)}
        <option value="__new__">New account…</option>
      </select>
    </label>
    <div class="portfolio-add-new-account" data-add-new-account hidden>
      <label class="fit-field"><span>Account name</span>
        <input name="new_account_name" type="text" placeholder="Fidelity Roth IRA">
      </label>
      <label class="fit-field"><span>Account type</span>
        <select name="new_account_type">
          <option value="taxable">Taxable brokerage</option>
          <option value="traditional">Traditional (pre-tax)</option>
          <option value="roth">Roth</option>
          <option value="hsa">HSA</option>
          <option value="cash">Cash / savings</option>
        </select>
      </label>
    </div>
  `;
}

function panelHidden(tab) {
  return addFlowState.tab === tab ? '' : raw('hidden');
}

// Pure: plain field values (as read from the form) → POST /api/portfolio/add body.
export function buildAddBody(tab, fields = {}) {
  const body = { flow: tab };
  const accountRef = String(fields.account_id || '').trim();
  if (accountRef === '__new__') {
    body.new_account = {
      name: String(fields.new_account_name || '').trim(),
      type: String(fields.new_account_type || 'taxable'),
    };
  } else if (accountRef) {
    body.account_id = accountRef;
  }

  if (tab === 'investment') {
    body.symbol = String(fields.symbol || '').trim().toUpperCase();
    if (String(fields.action || '').toUpperCase() === 'SELL') body.action = 'SELL';
    assignNumber(body, 'quantity', fields.quantity);
    assignNumber(body, 'value_usd', fields.value_usd);
    assignNumber(body, 'unit_cost', fields.unit_cost);
    const acquired = String(fields.acquired_date || '').trim();
    if (acquired) body.acquired_date = acquired;
  } else if (tab === 'cash') {
    assignNumber(body, 'amount_usd', fields.amount_usd);
  } else if (tab === 'property') {
    body.label = String(fields.label || '').trim();
    assignNumber(body, 'value_usd', fields.value_usd);
    body.asset_type = String(fields.asset_type || 'other');
  }
  return body;
}

function assignNumber(body, key, value) {
  const text = String(value ?? '').trim();
  if (!text) return;
  const number = Number(text);
  if (Number.isFinite(number)) body[key] = number;
}

export function renderAddResult(result = {}) {
  const detail = String(result.detail || 'Added to your portfolio.');
  return html`
    <span class="portfolio-add-detail">${detail}</span>
    ${result.estimated_basis ? html`
      <span class="portfolio-add-estimated">
        Cost basis was estimated from the current price — correct it under
        Records &amp; tools → Transactions whenever you know the real number.
      </span>
    ` : ''}
  `;
}

export function bindAddFlow(root, { reload } = {}) {
  const wrap = root.querySelector('[data-add-flow]');
  if (!wrap) return;
  const card = wrap.querySelector('[data-add-card]');
  const openButton = wrap.querySelector('[data-add-open]');
  openButton?.addEventListener('click', () => {
    addFlowState.open = !addFlowState.open;
    if (card) card.hidden = !addFlowState.open;
    openButton.setAttribute('aria-expanded', String(addFlowState.open));
  });

  wrap.querySelectorAll('[data-add-tab]').forEach((tab) => {
    tab.addEventListener('click', () => selectTab(wrap, tab.dataset.addTab));
  });

  wrap.querySelectorAll('select[name="account_id"]').forEach((select) => {
    select.addEventListener('change', () => {
      const holder = select.closest('form')?.querySelector('[data-add-new-account]');
      if (holder) holder.hidden = select.value !== '__new__';
    });
  });

  bindSymbolAutocomplete(wrap);

  wrap.querySelectorAll('[data-add-panel]').forEach((form) => {
    form.addEventListener('submit', async (event) => {
      event.preventDefault();
      await submitAddFlow(wrap, form, reload);
    });
  });
}

function selectTab(wrap, tabId) {
  if (!tabId) return;
  addFlowState.tab = tabId;
  wrap.querySelectorAll('[data-add-tab]').forEach((tab) => {
    tab.setAttribute('aria-selected', tab.dataset.addTab === tabId ? 'true' : 'false');
  });
  wrap.querySelectorAll('[data-add-panel]').forEach((panel) => {
    panel.hidden = panel.dataset.addPanel !== tabId;
  });
}

async function submitAddFlow(wrap, form, reload) {
  const statusEl = wrap.querySelector('[data-add-status]');
  const button = form.querySelector('button[type="submit"]');
  const fields = {};
  new FormData(form).forEach((value, key) => { fields[key] = value; });
  const body = buildAddBody(form.dataset.addPanel, fields);

  if (button) button.disabled = true;
  if (statusEl) {
    statusEl.hidden = false;
    statusEl.classList.remove('error');
    statusEl.textContent = 'Adding…';
  }
  try {
    const result = await api.portfolioAdd(body);
    addFlowState.result = result;
    addFlowState.prefill = null;
    addFlowState.open = true;
    if (typeof reload === 'function') await reload();
    else if (statusEl) setView(statusEl, renderAddResult(result));
  } catch (err) {
    if (statusEl) {
      statusEl.textContent = err?.message || 'Could not add this to the portfolio.';
      statusEl.classList.add('error');
    }
  } finally {
    if (button) button.disabled = false;
  }
}

// Registry-backed symbol suggestions, debounced, best-effort.
function bindSymbolAutocomplete(wrap) {
  const input = wrap.querySelector('input[name="symbol"]');
  const datalist = wrap.querySelector('#portfolio-add-symbols');
  if (!input || !datalist) return;
  let timer = null;
  input.addEventListener('input', () => {
    clearTimeout(timer);
    const q = input.value.trim();
    if (!q) return;
    timer = setTimeout(async () => {
      try {
        const payload = await api.portfolioAssetSearch({ q, limit: 8 });
        const items = Array.isArray(payload?.items) ? payload.items : [];
        datalist.innerHTML = items.map((item) =>
          `<option value="${esc(item.symbol)}">${esc(item.name || '')}</option>`).join('');
      } catch { /* suggestions are optional */ }
    }, 250);
  });
}

// Opens the card pre-filled from a holding row ("Record buy/sell").
export function openAddFlow(root, { tab = 'investment', symbol = '', account = '', action = '' } = {}) {
  const wrap = root.querySelector('[data-add-flow]');
  if (!wrap) return;
  addFlowState.open = true;
  addFlowState.prefill = { symbol, account, action };
  const card = wrap.querySelector('[data-add-card]');
  if (card) card.hidden = false;
  wrap.querySelector('[data-add-open]')?.setAttribute('aria-expanded', 'true');
  selectTab(wrap, tab);

  const panel = wrap.querySelector(`[data-add-panel="${tab}"]`);
  if (panel && tab === 'investment') {
    const symbolInput = panel.querySelector('input[name="symbol"]');
    if (symbolInput && symbol) symbolInput.value = String(symbol).toUpperCase();
    const accountSelect = panel.querySelector('select[name="account_id"]');
    if (accountSelect && account) accountSelect.value = String(account);
    const actionInput = panel.querySelector(`input[name="action"][value="${action === 'SELL' ? 'SELL' : 'BUY'}"]`);
    if (actionInput) actionInput.checked = true;
  }
  card?.scrollIntoView({ block: 'start' });
  panel?.querySelector('input[name="symbol"], input, select')?.focus();
}

// Quiet per-row actions on the top-holdings list: "Record buy/sell" opens the
// card pre-filled; "Update value" (manual-priced assets) saves a manual price.
export function bindHoldingActions(root, { reload } = {}) {
  root.querySelectorAll('[data-holding-trade]').forEach((button) => {
    button.addEventListener('click', () => openAddFlow(root, {
      tab: 'investment',
      symbol: button.dataset.symbol || '',
      account: button.dataset.account || '',
    }));
  });

  root.querySelectorAll('[data-holding-update-value]').forEach((button) => {
    button.addEventListener('click', () => {
      const form = button.closest('[data-holding-actions]')?.querySelector('[data-holding-update-form]');
      if (!form) return;
      form.hidden = !form.hidden;
      if (!form.hidden) form.querySelector('input')?.focus();
    });
  });

  root.querySelectorAll('[data-holding-update-form]').forEach((form) => {
    form.addEventListener('submit', async (event) => {
      event.preventDefault();
      const value = Number(new FormData(form).get('value'));
      const quantity = Number(form.dataset.quantity) || 1;
      if (!(value > 0)) return;
      const button = form.querySelector('button[type="submit"]');
      if (button) { button.disabled = true; button.textContent = 'Saving'; }
      try {
        await api.setPortfolioManualPrice({
          symbol: String(form.dataset.symbol || '').toUpperCase(),
          price: value / quantity,
          note: 'Updated from the holdings list',
        });
        if (typeof reload === 'function') await reload();
      } catch (err) {
        if (button) { button.disabled = false; button.textContent = 'Save'; }
        const status = form.querySelector('[data-holding-update-status]');
        if (status) status.textContent = err?.message || 'Could not save this value.';
      }
    });
  });
}
