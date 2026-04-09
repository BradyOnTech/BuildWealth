import { fetchJson } from '../lib/api.js';
import { byId, fmtCurrency, writeLog } from '../lib/utils.js';

export const id = 'import-statement';
export const label = 'Import';
export const icon = '<svg viewBox="0 0 20 20" fill="none" stroke="currentColor" stroke-width="1.6"><path d="M10 3v10M6 9l4 4 4-4"/><path d="M3 14v2a1 1 0 001 1h12a1 1 0 001-1v-2"/></svg>';

export function template() {
  return `
    <div class="view-header"><h2>Import Statement</h2></div>
    <p class="hint">Upload a bank or credit card CSV statement. Transactions will be analyzed and grouped into recurring expense and income suggestions for your financial profile.</p>
    <form id="statement-upload-form" class="card">
      <h3 class="section-title">Upload Statement CSV</h3>
      <div class="two-col">
        <label class="field file-field"><span>CSV File</span><input type="file" id="statement-file" accept=".csv,text/csv" required /></label>
        <label class="field"><span>Delimiter</span><input type="text" id="statement-delimiter" value="," maxlength="1" /></label>
      </div>
      <button class="primary" type="submit">Upload & Analyze</button>
    </form>
    <div id="statement-results" class="statement-results"></div>`;
}

function renderResults(data) {
  const el = byId('statement-results');

  if (data.parse_errors?.length) {
    el.innerHTML = `<div class="context-banner warning"><strong>Parse warnings:</strong> ${data.parse_errors.join('; ')}</div>`;
    if (!data.expense_suggestions?.length && !data.income_suggestions?.length) return;
  }

  const expenses = data.expense_suggestions || [];
  const income = data.income_suggestions || [];

  let html = `
    <div class="card">
      <h3 class="section-title">Analysis Summary</h3>
      <div class="kpi-row">
        <article class="kpi-card"><p class="kpi-label">Transactions</p><p class="kpi-value">${data.transaction_count}</p></article>
        <article class="kpi-card"><p class="kpi-label">Months Covered</p><p class="kpi-value">${data.months_covered}</p></article>
        <article class="kpi-card"><p class="kpi-label">Monthly Expenses</p><p class="kpi-value">${fmtCurrency(data.total_monthly_expenses)}</p></article>
        <article class="kpi-card"><p class="kpi-label">Monthly Income</p><p class="kpi-value">${fmtCurrency(data.total_monthly_income)}</p></article>
      </div>`;

  if (expenses.length) {
    html += `
      <h3 class="section-title">Expense Suggestions</h3>
      <p class="hint">Select the expenses to add to your financial profile. Amounts are monthly averages.</p>
      <div class="table-wrap"><table>
        <thead><tr><th><input type="checkbox" id="select-all-expenses" checked /></th><th>Description</th><th>Monthly</th><th>Category</th><th>Recurring</th><th>Txns</th></tr></thead>
        <tbody>${expenses.map((s, i) => `
          <tr>
            <td><input type="checkbox" class="expense-check" data-idx="${i}" checked /></td>
            <td><strong>${s.label}</strong><br><span class="rec-detail">${(s.sample_descriptions || []).join(', ')}</span></td>
            <td>${fmtCurrency(s.monthly_amount_usd)}</td>
            <td>${s.category}</td>
            <td>${s.is_fixed ? 'Yes' : 'No'}</td>
            <td>${s.transaction_count}</td>
          </tr>`).join('')}
        </tbody>
      </table></div>`;
  }

  if (income.length) {
    html += `
      <h3 class="section-title">Income Suggestions</h3>
      <div class="table-wrap"><table>
        <thead><tr><th><input type="checkbox" id="select-all-income" checked /></th><th>Description</th><th>Monthly</th><th>Type</th><th>Txns</th></tr></thead>
        <tbody>${income.map((s, i) => `
          <tr>
            <td><input type="checkbox" class="income-check" data-idx="${i}" checked /></td>
            <td>${s.label}</td>
            <td>${fmtCurrency(s.monthly_amount_usd)}</td>
            <td>${s.source_type}</td>
            <td>${s.transaction_count}</td>
          </tr>`).join('')}
        </tbody>
      </table></div>`;
  }

  if (expenses.length || income.length) {
    html += `<div class="panel-actions"><button class="primary" id="apply-suggestions">Add Selected to Profile</button></div>`;
  }

  html += '</div>';
  el.innerHTML = html;

  // Wire up select-all toggles
  const allExp = byId('select-all-expenses');
  if (allExp) allExp.addEventListener('change', () => {
    el.querySelectorAll('.expense-check').forEach(cb => { cb.checked = allExp.checked; });
  });
  const allInc = byId('select-all-income');
  if (allInc) allInc.addEventListener('change', () => {
    el.querySelectorAll('.income-check').forEach(cb => { cb.checked = allInc.checked; });
  });

  // Wire apply button
  const applyBtn = byId('apply-suggestions');
  if (applyBtn) {
    applyBtn.addEventListener('click', async () => {
      const selectedExpenses = [];
      el.querySelectorAll('.expense-check:checked').forEach(cb => {
        selectedExpenses.push(expenses[Number(cb.dataset.idx)]);
      });
      const selectedIncome = [];
      el.querySelectorAll('.income-check:checked').forEach(cb => {
        selectedIncome.push(income[Number(cb.dataset.idx)]);
      });

      if (!selectedExpenses.length && !selectedIncome.length) {
        writeLog('No items selected.', null, true);
        return;
      }

      try {
        const result = await fetchJson('/api/import/statement/apply', {
          method: 'POST',
          headers: { 'content-type': 'application/json' },
          body: JSON.stringify({ expenses: selectedExpenses, income: selectedIncome }),
        });
        applyBtn.textContent = `Added ${result.added_expenses} expenses, ${result.added_income} income items`;
        applyBtn.disabled = true;
        writeLog('Statement items applied to profile.', result);
      } catch (e) {
        writeLog(`Apply failed: ${e.message}`, null, true);
      }
    });
  }
}

async function upload(event) {
  event.preventDefault();
  const fileInput = byId('statement-file');
  const file = fileInput.files?.[0];
  if (!file) { writeLog('Choose a CSV file.', null, true); return; }

  const fd = new FormData();
  fd.append('file', file);
  fd.append('delimiter', byId('statement-delimiter').value || ',');

  byId('statement-results').innerHTML = '<p class="empty-text">Analyzing transactions...</p>';
  try {
    const result = await fetchJson('/api/import/statement', { method: 'POST', body: fd });
    renderResults(result);
    writeLog(`Statement analyzed: ${result.transaction_count} transactions, ${result.expense_suggestions.length} expense suggestions.`);
  } catch (e) {
    byId('statement-results').innerHTML = `<div class="context-banner critical">Upload failed: ${e.message}</div>`;
    writeLog(`Statement upload failed: ${e.message}`, null, true);
  }
}

export function init() {
  byId('statement-upload-form').addEventListener('submit', upload);
}
