import { html, esc } from '../../lib/dom.js';
import { persist } from '../profile.js';

const STATUS_OPTIONS = [
  ['unknown', 'Not answered'],
  ['not_started', 'Not started'],
  ['in_progress', 'In progress'],
  ['complete', 'Complete'],
  ['not_needed', 'Not needed'],
];

const FIELDS = [
  ['will_status', 'Will'],
  ['trust_status', 'Trust'],
  ['power_of_attorney_status', 'Power of attorney'],
  ['healthcare_directive_status', 'Healthcare directive'],
];

export function renderEstateReadiness(ui) {
  const estate = ui.profile?.estate_readiness || {};
  return html`
    <div class="profile-table-wrap">
      <header class="profile-table-head">
        <div>
          <p class="profile-table-eyebrow">§ Protection · Estate readiness</p>
          <h2 class="profile-table-title">Estate readiness</h2>
          <p class="profile-table-lede">
            Track whether the household's core documents and beneficiaries have been reviewed.
            BuildWealth stores readiness—not document contents.
          </p>
        </div>
      </header>
      <form class="estate-readiness-form" data-estate-form>
        <div class="estate-readiness-grid">
          ${FIELDS.map(([key, label]) => html`
            <label class="settings-field">
              <span class="settings-label">${label}</span>
              <select class="settings-input" name="${esc(key)}">
                ${STATUS_OPTIONS.map(([value, optionLabel]) => html`
                  <option value="${esc(value)}" ${estate[key] === value ? 'selected' : ''}>${optionLabel}</option>
                `)}
              </select>
            </label>
          `)}
          <label class="settings-field">
            <span class="settings-label">Beneficiaries last reviewed</span>
            <input class="settings-input" type="date" name="beneficiaries_reviewed_at"
                   value="${dateInputValue(estate.beneficiaries_reviewed_at)}" />
          </label>
        </div>
        <label class="settings-field estate-notes">
          <span class="settings-label">Notes</span>
          <textarea class="settings-input" name="notes" rows="3"
                    placeholder="Attorney follow-up, documents to revisit…">${estate.notes || ''}</textarea>
        </label>
        <div class="profile-composer-actions">
          <button class="btn btn-primary" type="button" data-estate-save
                  ${ui.saving ? 'disabled' : ''}>${ui.saving ? 'Saving…' : 'Save estate readiness'}</button>
        </div>
        ${ui.saveError ? html`<p class="inline-warning">${ui.saveError}</p>` : ''}
      </form>
    </div>
  `;
}

export async function submitEstateReadiness(ui, root) {
  const form = root.querySelector('[data-estate-form]');
  if (!form || !ui.profile) return;
  const values = Object.fromEntries(new FormData(form).entries());
  ui.profile.estate_readiness = {
    will_status: values.will_status || 'unknown',
    trust_status: values.trust_status || 'unknown',
    power_of_attorney_status: values.power_of_attorney_status || 'unknown',
    healthcare_directive_status: values.healthcare_directive_status || 'unknown',
    beneficiaries_reviewed_at: values.beneficiaries_reviewed_at || null,
    notes: String(values.notes || '').trim(),
  };
  await persist({ optimistic: false });
}

function dateInputValue(value) {
  return value ? String(value).slice(0, 10) : '';
}
