import { fetchJson } from '../lib/api.js';
import { state } from '../lib/state.js';
import { byId, fmtCurrency, fmtDate, uid, parseOptionalNumber, writeLog } from '../lib/utils.js';
import { emptyFinancialProfile, renderItemList } from '../lib/components.js';

export const id = 'profile';
export const label = 'Profile';
export const icon = '<svg viewBox="0 0 20 20" fill="none" stroke="currentColor" stroke-width="1.6"><circle cx="10" cy="7" r="3.5"/><path d="M3.5 18c0-3.6 2.9-6.5 6.5-6.5s6.5 2.9 6.5 6.5"/></svg>';

export function template() {
  return `
    <div class="view-header"><h2>Financial Profile</h2>
      <div class="header-actions"><button class="ghost small" id="reload-profile">Reload</button><button class="primary small" id="save-profile">Save Profile</button></div>
    </div>
    <p class="hint" id="onboarding-summary">Loading onboarding status...</p>
    <div class="progress-wrap"><div class="progress-bar"><div id="onboarding-progress-fill" class="progress-fill"></div></div><p class="hint tight" id="onboarding-ready">-</p></div>
    <div id="onboarding-steps" class="item-list"></div>
    <h3 class="section-title">Tax & Preferences</h3>
    <div class="settings-grid">
      <label class="field"><span>Filing Status</span><select id="profile-filing-status"><option value="">Select</option><option value="single">Single</option><option value="married_filing_jointly">Married Filing Jointly</option><option value="married_filing_separately">Married Filing Separately</option><option value="head_of_household">Head of Household</option></select></label>
      <label class="field"><span>Marginal Tax Rate (%)</span><input type="number" id="profile-marginal-tax-rate" step="0.01" min="0" max="100" placeholder="e.g. 24" /></label>
      <label class="field"><span>Effective Tax Rate (%)</span><input type="number" id="profile-effective-tax-rate" step="0.01" min="0" max="100" placeholder="e.g. 18" /></label>
      <label class="field"><span>State</span><input type="text" id="profile-state" placeholder="MN" /></label>
      <label class="field"><span>No Debt</span><label class="inline-check"><input type="checkbox" id="profile-no-debt" /> I have no debt</label></label>
      <label class="field"><span>No Goals Yet</span><label class="inline-check"><input type="checkbox" id="profile-no-goals" /> Not tracking goals yet</label></label>
    </div>
    <label class="field"><span>Profile Notes</span><textarea id="profile-notes" rows="2" placeholder="Optional context for Copilot."></textarea></label>
    ${section('Income', 'income', ['Label|text|income-label|Source label', 'Monthly USD|number|income-amount|0', 'Type|select|income-source-type|salary:Salary,bonus:Bonus,business:Business,rental:Rental,other:Other', 'Pre-tax|checkbox|income-pre-tax|'], ['Label', 'Monthly', 'Type', 'Pre-Tax'])}
    ${section('Expenses', 'expense', ['Label|text|expense-label|Expense label', 'Monthly USD|number|expense-amount|0', 'Category|text|expense-category|Category', 'Fixed|checkbox|expense-fixed|checked'], ['Label', 'Monthly', 'Category', 'Fixed'])}
    ${section('Debt', 'debt', ['Label|text|debt-label|Debt label', 'Balance USD|number|debt-balance|0', 'Rate %|number|debt-rate|0', 'Min Payment|number|debt-min-payment|0'], ['Label', 'Balance', 'Rate', 'Min Payment'])}
    ${section('Goals', 'goal', ['Label|text|goal-label|Goal label', 'Target USD|number|goal-amount|0', 'Target Date|date|goal-date|', 'Priority|select|goal-priority|high:High,medium:Medium,low:Low'], ['Label', 'Target', 'Target Date', 'Priority'])}`;
}

function section(title, key, fields, headers) {
  const inputs = fields.map(f => {
    const [label, type, id, extra] = f.split('|');
    if (type === 'select') {
      const opts = extra.split(',').map(o => { const [v, l] = o.split(':'); return `<option value="${v}">${l}</option>`; }).join('');
      return `<select id="${id}">${opts}</select>`;
    }
    if (type === 'checkbox') return `<label class="inline-check"><input type="checkbox" id="${id}" ${extra} /> ${label}</label>`;
    return `<input type="${type}" id="${id}" step="0.01" min="0" placeholder="${extra || label}" />`;
  }).join('');
  const ths = headers.map(h => `<th>${h}</th>`).join('') + '<th>Action</th>';
  return `<h3 class="section-title">${title}</h3><div class="inline-builder">${inputs}<button class="ghost small" id="add-${key}" type="button">Add</button></div><div class="table-wrap"><table><thead><tr>${ths}</tr></thead><tbody id="profile-${key}-body"></tbody></table></div>`;
}

function ensure() { if (!state.financialProfile || typeof state.financialProfile !== 'object') state.financialProfile = emptyFinancialProfile(); }

function renderTables() {
  ensure();
  const p = state.financialProfile;
  tableRows('profile-income-body', p.income_items, i => [i.label, fmtCurrency(i.monthly_amount_usd), i.source_type, i.is_pre_tax ? 'Yes' : 'No'], 'income_items');
  tableRows('profile-expense-body', p.expense_items, i => [i.label, fmtCurrency(i.monthly_amount_usd), i.category, i.is_fixed ? 'Yes' : 'No'], 'expense_items');
  tableRows('profile-debt-body', p.debt_items, i => [i.label, fmtCurrency(i.balance_usd), typeof i.interest_rate === 'number' ? `${(i.interest_rate * 100).toFixed(2)}%` : '-', fmtCurrency(i.minimum_payment_usd)], 'debt_items');
  tableRows('profile-goal-body', p.goal_items, i => [i.label, fmtCurrency(i.target_amount_usd), i.target_date ? fmtDate(i.target_date) : '-', i.priority], 'goal_items');
}

function tableRows(tbodyId, items, cellsFn, stateKey) {
  const tbody = byId(tbodyId);
  tbody.innerHTML = '';
  if (!Array.isArray(items) || !items.length) { tbody.innerHTML = `<tr><td colspan="5">No items yet.</td></tr>`; return; }
  for (const item of items) {
    const tr = document.createElement('tr');
    for (const cell of cellsFn(item)) { const td = document.createElement('td'); td.textContent = cell || '-'; tr.appendChild(td); }
    const td = document.createElement('td');
    const btn = document.createElement('button'); btn.type = 'button'; btn.className = 'ghost small'; btn.textContent = 'Remove';
    btn.addEventListener('click', () => { state.financialProfile[stateKey] = state.financialProfile[stateKey].filter(r => r.id !== item.id); renderTables(); });
    td.appendChild(btn); tr.appendChild(td); tbody.appendChild(tr);
  }
}

function renderForm() {
  ensure();
  const p = state.financialProfile;
  const tax = p.tax_profile || {};
  const flags = p.flags || {};
  byId('profile-filing-status').value = tax.filing_status || '';
  byId('profile-marginal-tax-rate').value = typeof tax.marginal_tax_rate === 'number' ? (tax.marginal_tax_rate * 100).toString() : '';
  byId('profile-effective-tax-rate').value = typeof tax.effective_tax_rate === 'number' ? (tax.effective_tax_rate * 100).toString() : '';
  byId('profile-state').value = tax.state || '';
  byId('profile-no-debt').checked = Boolean(flags.no_debt);
  byId('profile-no-goals').checked = Boolean(flags.no_goals);
  byId('profile-notes').value = p.notes || '';
  renderTables();
}

function renderOnboarding(status) {
  state.onboardingStatus = status;
  byId('onboarding-summary').textContent = `Onboarding ${Number(status.completion_percent || 0).toFixed(1)}% complete`;
  byId('onboarding-progress-fill').style.width = `${Math.max(0, Math.min(100, status.completion_percent || 0))}%`;
  byId('onboarding-ready').textContent = status.ready_for_daily_review ? 'Ready for daily review.' : 'Complete remaining steps for best Copilot context.';
  renderItemList('onboarding-steps', status.steps || [], (item) => {
    const el = document.createElement('article');
    el.className = `list-item ${item.status || 'incomplete'}`;
    el.innerHTML = `<p class="list-item-title">${item.title || '-'}</p><p class="list-item-meta">${item.detail || ''}</p>`;
    return el;
  });
}

function collectFromInputs() {
  ensure();
  const p = state.financialProfile;
  const mr = parseOptionalNumber(byId('profile-marginal-tax-rate').value, 'Marginal tax rate');
  const er = parseOptionalNumber(byId('profile-effective-tax-rate').value, 'Effective tax rate');
  if (mr !== null && (mr < 0 || mr > 100)) throw new Error('Marginal tax rate must be 0-100.');
  if (er !== null && (er < 0 || er > 100)) throw new Error('Effective tax rate must be 0-100.');
  p.tax_profile = { filing_status: byId('profile-filing-status').value || null, marginal_tax_rate: mr === null ? null : mr / 100, effective_tax_rate: er === null ? null : er / 100, state: byId('profile-state').value.trim() || null };
  p.flags = { no_debt: byId('profile-no-debt').checked, no_goals: byId('profile-no-goals').checked };
  p.notes = byId('profile-notes').value.trim();
}

function addItem(key, builder) {
  ensure();
  const item = builder();
  if (!item) return;
  state.financialProfile[key].push(item);
  renderTables();
}

async function load() {
  try { state.financialProfile = await fetchJson('/api/financial-profile'); renderForm(); } catch (e) { state.financialProfile = emptyFinancialProfile(); renderForm(); writeLog(`Profile load failed: ${e.message}`, null, true); }
  try { renderOnboarding(await fetchJson('/api/onboarding/status')); } catch (e) { byId('onboarding-summary').textContent = `Onboarding unavailable: ${e.message}`; }
}

async function save() {
  try { collectFromInputs(); } catch (e) { writeLog(e.message, null, true); return; }
  writeLog('Saving financial profile...');
  try {
    state.financialProfile = await fetchJson('/api/financial-profile', { method: 'PUT', headers: { 'content-type': 'application/json' }, body: JSON.stringify(state.financialProfile) });
    renderForm();
    try { renderOnboarding(await fetchJson('/api/onboarding/status')); } catch (_) {}
    writeLog('Profile saved.', { updated_at: state.financialProfile.updated_at });
  } catch (e) { writeLog(`Save failed: ${e.message}`, null, true); }
}

export function init() {
  byId('reload-profile').addEventListener('click', () => load().catch(e => writeLog(e.message, null, true)));
  byId('save-profile').addEventListener('click', save);
  byId('add-income').addEventListener('click', () => addItem('income_items', () => {
    const label = byId('income-label').value.trim(); if (!label) { writeLog('Income label required.', null, true); return null; }
    let amt; try { amt = parseOptionalNumber(byId('income-amount').value, 'Amount'); } catch (e) { writeLog(e.message, null, true); return null; }
    if (amt === null || amt < 0) { writeLog('Amount must be >= 0.', null, true); return null; }
    const item = { id: uid('income'), label, monthly_amount_usd: amt, source_type: byId('income-source-type').value || 'salary', is_pre_tax: byId('income-pre-tax').checked };
    byId('income-label').value = ''; byId('income-amount').value = ''; byId('income-pre-tax').checked = false; return item;
  }));
  byId('add-expense').addEventListener('click', () => addItem('expense_items', () => {
    const label = byId('expense-label').value.trim(); if (!label) { writeLog('Expense label required.', null, true); return null; }
    let amt; try { amt = parseOptionalNumber(byId('expense-amount').value, 'Amount'); } catch (e) { writeLog(e.message, null, true); return null; }
    if (amt === null || amt < 0) { writeLog('Amount must be >= 0.', null, true); return null; }
    const item = { id: uid('expense'), label, monthly_amount_usd: amt, category: byId('expense-category').value.trim() || 'general', is_fixed: byId('expense-fixed').checked };
    byId('expense-label').value = ''; byId('expense-amount').value = ''; byId('expense-category').value = ''; byId('expense-fixed').checked = true; return item;
  }));
  byId('add-debt').addEventListener('click', () => addItem('debt_items', () => {
    const label = byId('debt-label').value.trim(); if (!label) { writeLog('Debt label required.', null, true); return null; }
    let bal, rate, min; try { bal = parseOptionalNumber(byId('debt-balance').value, 'Balance'); rate = parseOptionalNumber(byId('debt-rate').value, 'Rate'); min = parseOptionalNumber(byId('debt-min-payment').value, 'Min payment'); } catch (e) { writeLog(e.message, null, true); return null; }
    if (bal === null || bal < 0) { writeLog('Balance must be >= 0.', null, true); return null; }
    const item = { id: uid('debt'), label, balance_usd: bal, interest_rate: rate === null ? null : rate / 100, minimum_payment_usd: min };
    byId('debt-label').value = ''; byId('debt-balance').value = ''; byId('debt-rate').value = ''; byId('debt-min-payment').value = ''; return item;
  }));
  byId('add-goal').addEventListener('click', () => addItem('goal_items', () => {
    const label = byId('goal-label').value.trim(); if (!label) { writeLog('Goal label required.', null, true); return null; }
    let amt; try { amt = parseOptionalNumber(byId('goal-amount').value, 'Target'); } catch (e) { writeLog(e.message, null, true); return null; }
    if (amt === null || amt < 0) { writeLog('Target must be >= 0.', null, true); return null; }
    const raw = byId('goal-date').value; const date = raw ? new Date(`${raw}T00:00:00.000Z`).toISOString() : null;
    const item = { id: uid('goal'), label, target_amount_usd: amt, target_date: date, priority: byId('goal-priority').value || 'medium', notes: '' };
    byId('goal-label').value = ''; byId('goal-amount').value = ''; byId('goal-date').value = ''; byId('goal-priority').value = 'medium'; return item;
  }));
  load();
}
