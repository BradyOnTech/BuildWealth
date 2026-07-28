// Budget reader — a statement screenshot or CSV becomes reviewable expense
// and income suggestions. Manual budget arithmetic is the tedium this kills:
// upload, check what was read, apply only what looks right. Nothing touches
// the profile until Apply.

import { api } from '../../lib/api.js';
import { html, raw, esc, delegate } from '../../lib/dom.js';
import { fmtUsd } from '../../lib/format.js';

const ui = {
  busy: false,
  error: null,
  result: null,       // last upload response (csv or vision)
  applied: null,      // last apply response
};

export function renderBudgetReaderCard() {
  return html`
    <section class="settings-card" id="budget-reader-card">
      <header class="settings-card-head">
        <h2 class="settings-card-title">Budget reader</h2>
        <p class="settings-card-lede">
          Drop a bank or card statement — a CSV export or just a screenshot —
          and BuildWealth suggests your monthly expenses and income from it.
          Nothing is saved until you apply.
        </p>
      </header>

      <form class="import-workbench-form" id="budget-reader-form">
        <label class="settings-field span-2">
          <span class="settings-label">Statement CSV or screenshot</span>
          <input class="settings-input" type="file" name="file"
                 accept=".csv,text/csv,image/png,image/jpeg,image/webp,image/gif" required />
          <span class="settings-hint">
            Screenshots are read by AI (needs a vision-capable model in
            Settings → Connections & AI); CSVs are parsed locally. For PDF
            statements, screenshot the pages.
          </span>
        </label>
        <footer class="settings-actions span-2">
          <button class="btn btn-primary" id="budget-reader-upload" ${ui.busy ? 'disabled' : ''}>
            ${ui.busy ? 'Reading…' : 'Read statement'}
          </button>
          ${ui.error ? html`<p class="inline-warning">${ui.error}</p>` : ''}
        </footer>
      </form>

      ${raw(resultPanel())}
    </section>
  `;
}

function resultPanel() {
  const result = ui.result;
  if (!result) return '';
  if (result.status && result.status !== 'ready') {
    return html`
      <div class="analytics-warnings">
        <p>${esc(String(result.detail || 'The statement could not be read.'))}</p>
        ${raw((result.warnings || []).map(w => html`<p>${w}</p>`.toString()).join(''))}
      </div>
    `;
  }

  const expenses = Array.isArray(result.expense_suggestions) ? result.expense_suggestions : [];
  const income = Array.isArray(result.income_suggestions) ? result.income_suggestions : [];
  const fromVision = result.measurement_source === 'ai_vision_extraction';

  return html`
    <div class="budget-reader-result">
      <dl class="analytics-metrics compact">
        ${result.account_name ? raw(metric('Account', `${result.account_name}${result.account_type && result.account_type !== 'unknown' ? ` (${result.account_type.replace('_', ' ')})` : ''}`)) : ''}
        ${result.ending_balance_usd != null ? raw(metric(result.account_type === 'credit_card' ? 'Balance owed' : 'Ending balance', fmtUsd(result.ending_balance_usd))) : ''}
        ${raw(metric('Transactions read', String(result.transaction_count ?? 0)))}
        ${raw(metric('Months covered', String(result.months_covered ?? '—')))}
        ${raw(metric('Monthly expenses', fmtUsd(result.total_monthly_expenses || 0)))}
        ${result.total_monthly_income ? raw(metric('Monthly income', fmtUsd(result.total_monthly_income))) : ''}
      </dl>
      ${fromVision ? html`<p class="marginalia">${esc(String(result.review_note || ''))}</p>` : ''}

      ${expenses.length ? html`
        <div class="benchmark-rows">
          ${raw(expenses.map((s, i) => suggestionRow('expense', s, i)).join(''))}
          ${raw(income.map((s, i) => suggestionRow('income', s, i)).join(''))}
        </div>
        <footer class="settings-actions">
          <button class="btn btn-primary" id="budget-reader-apply" ${ui.busy ? 'disabled' : ''}>
            Apply checked to Profile
          </button>
          <span class="settings-hint">
            Adds only items with no credible Profile match. Possible duplicate payments are held for a Copilot question.
          </span>
        </footer>
      ` : html`<p class="fit-empty">No recurring expenses could be suggested from this statement.</p>`}

      ${(result.warnings || []).length ? html`
        <p class="marginalia">${raw((result.warnings || []).slice(0, 4).map(esc).join(' · '))}</p>
      ` : ''}

      ${ui.applied ? html`
        <p class="quality-quote small">
          Added ${ui.applied.added_expenses} expense item${ui.applied.added_expenses === 1 ? '' : 's'}
          and ${ui.applied.added_income} income item${ui.applied.added_income === 1 ? '' : 's'} to your profile.
          ${ui.applied.skipped_duplicates
            ? `${ui.applied.skipped_duplicates} already-counted payment${ui.applied.skipped_duplicates === 1 ? ' was' : 's were'} not added again.`
            : ''}
        </p>
        ${raw(renderStatementClarifications(ui.applied))}
      ` : ''}
    </div>
  `;
}

export function renderStatementClarifications(applied) {
  const clarifications = Array.isArray(applied?.clarifications) ? applied.clarifications : [];
  if (!clarifications.length) return '';
  return html`
    <section class="statement-clarifications" aria-label="Statement payment questions">
      <header>
        <p class="settings-eyebrow">Held safely · needs your answer</p>
        <h3>Possible duplicate payments</h3>
        <p>
          These were not added to Profile. Answer the focused question in Copilot
          so BuildWealth can link the payment or keep it separate.
        </p>
      </header>
      ${raw(clarifications.map(item => html`
        <article class="statement-clarification">
          <p>${esc(String(item.question || 'Is this payment already represented in Profile?'))}</p>
          <div class="entry-actions">
            <a class="action-link" href="${esc(String(item.copilot_href || '#copilot'))}" data-route>
              Answer with Copilot <span class="arrow">›</span>
            </a>
          </div>
        </article>
      `).join(''))}
    </section>
  `;
}

function suggestionRow(kind, suggestion, index) {
  const meta = kind === 'expense'
    ? `${suggestion.category || 'general'}${suggestion.is_fixed ? ' · recurring' : ''} · ${suggestion.transaction_count}×`
    : `${suggestion.source_type || 'income'} · ${suggestion.transaction_count}×`;
  return html`
    <div class="benchmark-row">
      <strong>
        <label style="display:flex;gap:8px;align-items:center;cursor:pointer;">
          <input type="checkbox" checked data-budget-suggestion="${kind}:${index}" />
          ${esc(String(suggestion.label || ''))}
        </label>
      </strong>
      <span>${fmtUsd(suggestion.monthly_amount_usd || 0)}/mo</span>
      <span class="${kind === 'income' ? 'delta-up' : ''}">${esc(meta)}</span>
    </div>
  `.toString();
}

function metric(label, value) {
  return html`<div><dt>${label}</dt><dd>${value}</dd></div>`;
}

export function bindBudgetReader(root, rerender) {
  delegate(root, 'click', '#budget-reader-upload', async (event) => {
    event.preventDefault();
    const form = root.querySelector('#budget-reader-form');
    const input = form?.querySelector('input[name="file"]');
    const file = input?.files?.[0];
    if (!file) {
      ui.error = 'Choose a statement file first.';
      rerender();
      return;
    }
    ui.busy = true;
    ui.error = null;
    ui.result = null;
    ui.applied = null;
    rerender();
    try {
      const formData = new FormData();
      formData.append('file', file);
      const isImage = String(file.type || '').startsWith('image/');
      ui.result = isImage
        ? await api.uploadStatementImage(formData)
        : await api.uploadStatement(formData);
    } catch (err) {
      ui.error = err.message || 'The statement could not be read.';
    } finally {
      ui.busy = false;
      rerender();
    }
  });

  delegate(root, 'click', '#budget-reader-apply', async (event) => {
    event.preventDefault();
    const result = ui.result;
    if (!result) return;
    const checked = new Set(
      [...root.querySelectorAll('[data-budget-suggestion]')]
        .filter(box => box.checked)
        .map(box => box.dataset.budgetSuggestion),
    );
    const expenses = (result.expense_suggestions || []).filter((_, i) => checked.has(`expense:${i}`));
    const income = (result.income_suggestions || []).filter((_, i) => checked.has(`income:${i}`));
    if (!expenses.length && !income.length) {
      ui.error = 'Nothing is checked to apply.';
      rerender();
      return;
    }
    ui.busy = true;
    ui.error = null;
    rerender();
    try {
      ui.applied = await api.applyStatementSuggestions({ expenses, income });
    } catch (err) {
      ui.error = err.message || 'Could not apply the suggestions.';
    } finally {
      ui.busy = false;
      rerender();
    }
  });
}
