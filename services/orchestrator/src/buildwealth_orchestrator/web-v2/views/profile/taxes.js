// Profile · Taxes form.
// Filing status, marginal/effective/state rates, and state. The form is the
// only writer for tax_profile and household flags. Saving routes through the
// shared persist() so onboarding refreshes after each edit.

import { html, raw, esc } from '../../lib/dom.js';
import { persist, render as renderProfile } from '../profile.js';
import { getSuggestion, suggestionLine } from './suggestions.js';

const FILING_STATUSES = [
  { value: '',                          label: 'Choose…' },
  { value: 'single',                    label: 'Single' },
  { value: 'married_filing_jointly',    label: 'Married filing jointly' },
  { value: 'married_filing_separately', label: 'Married filing separately' },
  { value: 'head_of_household',         label: 'Head of household' },
  { value: 'qualifying_widow',          label: 'Qualifying widow(er)' },
];

let pendingSave = false;
let lastSaveError = null;

export function renderTaxes(ui) {
  const tax = ui.profile?.tax_profile || {};
  const flags = ui.profile?.flags || {};
  const suggestions = ui.suggestions || {};
  const ratePct = (decimal) => (Number(decimal) * 100).toFixed(1).replace(/\.0$/, '');
  return html`
    <div class="profile-taxes">
      <header class="profile-table-head">
        <div>
          <p class="profile-table-eyebrow">§ Foundation · Taxes &amp; status</p>
          <h2 class="profile-table-title">Tax profile and simple status answers</h2>
          <p class="profile-table-lede">
            Used in plan trajectory, Roth-conversion math, and tax-loss harvesting.
            Rates shape tax-aware planning. Simple no-debt and not-yet-tracking-goals answers
            keep BuildWealth from repeatedly asking about things that do not apply.
          </p>
        </div>
      </header>

      <div class="settings-grid">
        <label class="settings-field">
          <span class="settings-label">Filing status</span>
          <select class="settings-input" id="taxes-filing-status">
            ${raw(FILING_STATUSES.map(o => `
              <option value="${esc(o.value)}" ${o.value === (tax.filing_status || '') ? 'selected' : ''}>${esc(o.label)}</option>
            `).join(''))}
          </select>
          <span class="settings-hint">Drives tax-bracket-aware suggestions.</span>
        </label>

        <label class="settings-field">
          <span class="settings-label">State</span>
          <input class="settings-input mono" id="taxes-state" type="text" maxlength="2"
                 placeholder="MN" value="${esc(tax.state || '')}" />
          <span class="settings-hint">Two-letter postal code.</span>
        </label>

        <label class="settings-field">
          <span class="settings-label">Marginal tax rate (%)</span>
          <input class="settings-input mono" id="taxes-marginal" type="number" min="0" max="100" step="0.01"
                 placeholder="e.g. 24" value="${esc(toPercent(tax.marginal_tax_rate))}" />
          <span class="settings-hint">Top federal bracket on the next dollar.
            ${raw(suggestionLine(suggestions, 'tax_profile.marginal_tax_rate', { target: 'taxes-marginal', format: ratePct }))}</span>
        </label>

        <label class="settings-field">
          <span class="settings-label">Effective tax rate (%)</span>
          <input class="settings-input mono" id="taxes-effective" type="number" min="0" max="100" step="0.01"
                 placeholder="e.g. 18" value="${esc(toPercent(tax.effective_tax_rate))}" />
          <span class="settings-hint">Average federal rate across total income.
            ${raw(suggestionLine(suggestions, 'tax_profile.effective_tax_rate', { target: 'taxes-effective', format: ratePct }))}</span>
        </label>

        <label class="settings-field">
          <span class="settings-label">State tax rate (%)</span>
          <input class="settings-input mono" id="taxes-state-rate" type="number" min="0" max="100" step="0.01"
                 placeholder="e.g. 5" value="${esc(toPercent(tax.state_tax_rate))}" />
          <span class="settings-hint">Optional; leave blank if state has no income tax.
            ${raw(suggestionLine(suggestions, 'tax_profile.state_tax_rate', { target: 'taxes-state-rate', format: ratePct }))}</span>
        </label>

        <label class="settings-field span-2 settings-field-toggle">
          <input type="checkbox" id="taxes-no-debt" ${flags.no_debt ? 'checked' : ''} />
          <span>
            <span class="settings-label">I have no debt</span>
            <span class="settings-hint">Tells BuildWealth not to plan around debt pay-down.</span>
          </span>
        </label>

        <label class="settings-field span-2 settings-field-toggle">
          <input type="checkbox" id="taxes-no-goals" ${flags.no_goals ? 'checked' : ''} />
          <span>
            <span class="settings-label">Not tracking goals yet</span>
            <span class="settings-hint">Hides the "no goals tracked" warning until you are ready.</span>
          </span>
        </label>
      </div>

      ${getSuggestion(suggestions, 'tax_profile.marginal_tax_rate') || getSuggestion(suggestions, 'tax_profile.effective_tax_rate') || getSuggestion(suggestions, 'tax_profile.state_tax_rate') ? html`
        <p class="suggestion-banner">
          Don't know these? Use the estimates — they come from your own income and state,
          and you can correct them any time.
        </p>
      ` : ''}
      ${lastSaveError ? html`<p class="inline-warning">${lastSaveError}</p>` : ''}
      <div class="profile-composer-actions">
        <button class="btn btn-primary" type="button" data-taxes-save ${pendingSave ? 'disabled' : ''}>
          ${pendingSave ? 'Saving…' : 'Save tax profile'}
        </button>
      </div>
    </div>
  `;
}

export async function submitTaxesForm(ui) {
  if (pendingSave) return;
  const root = document.getElementById('profile-page');
  if (!root) return;

  const get = (id) => root.querySelector(`#${id}`);
  const filingStatus = get('taxes-filing-status')?.value || null;
  const state = (get('taxes-state')?.value || '').trim().toUpperCase() || null;
  const marginal = parsePercent(get('taxes-marginal')?.value);
  const effective = parsePercent(get('taxes-effective')?.value);
  const stateRate = parsePercent(get('taxes-state-rate')?.value);
  const noDebt = !!get('taxes-no-debt')?.checked;
  const noGoals = !!get('taxes-no-goals')?.checked;

  for (const [label, value] of [['Marginal', marginal], ['Effective', effective], ['State', stateRate]]) {
    if (value != null && (value < 0 || value > 1)) {
      lastSaveError = `${label} tax rate must be 0–100%.`;
      renderProfile();
      return;
    }
  }

  if (!ui.profile.tax_profile) ui.profile.tax_profile = {};
  if (!ui.profile.flags) ui.profile.flags = {};
  ui.profile.tax_profile.filing_status = filingStatus || null;
  ui.profile.tax_profile.marginal_tax_rate  = marginal;
  ui.profile.tax_profile.effective_tax_rate = effective;
  ui.profile.tax_profile.state_tax_rate     = stateRate;
  ui.profile.tax_profile.state              = state;
  ui.profile.flags.no_debt  = noDebt;
  ui.profile.flags.no_goals = noGoals;

  pendingSave = true;
  lastSaveError = null;
  renderProfile();
  try {
    await persist();
  } catch (err) {
    lastSaveError = err?.message || 'Could not save.';
  } finally {
    pendingSave = false;
    renderProfile();
  }
}

function toPercent(decimal) {
  if (decimal == null || !Number.isFinite(Number(decimal))) return '';
  return String(Math.round(Number(decimal) * 100 * 10000) / 10000);
}

function parsePercent(value) {
  if (value === '' || value == null) return null;
  const n = Number(value);
  if (!Number.isFinite(n)) return null;
  return n / 100;
}
