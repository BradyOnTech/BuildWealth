// Movement IA — Plan assumptions.
// Read/edit surface for the assumptions that drive recommendations, fit, and scenarios.

import { html, raw, esc } from '../../lib/dom.js';
import { fmtUsd } from '../../lib/format.js';

export const PLAN_ASSUMPTION_FIELDS = [
  { key: 'annual_contribution_usd', label: 'Annual contribution', type: 'money' },
  { key: 'years', label: 'Years horizon', type: 'integer' },
  { key: 'expected_return_baseline', label: 'Expected return', type: 'percent' },
  { key: 'inflation_rate', label: 'Inflation', type: 'percent' },
  { key: 'marginal_tax_rate', label: 'Marginal tax', type: 'percent' },
  {
    key: 'filing_status',
    label: 'Filing status',
    type: 'select',
    options: [
      ['', 'Unspecified'],
      ['single', 'Single'],
      ['married_filing_jointly', 'Married filing jointly'],
      ['married_filing_separately', 'Married filing separately'],
      ['head_of_household', 'Head of household'],
    ],
  },
  {
    key: 'withdrawal_strategy',
    label: 'Withdrawal strategy',
    type: 'select',
    options: [
      ['', 'Unspecified'],
      ['guardrails', 'Guardrails'],
      ['fixed_real', 'Fixed real'],
      ['fixed_percent', 'Fixed percent'],
      ['bucket', 'Bucket'],
    ],
  },
  {
    key: 'drawdown_order',
    label: 'Drawdown order',
    type: 'select',
    options: [
      ['', 'Unspecified'],
      ['taxable_first', 'Taxable first'],
      ['tax_deferred_first', 'Tax deferred first'],
      ['roth_first', 'Roth first'],
      ['pro_rata', 'Pro rata'],
    ],
  },
  {
    key: 'simulation_mode',
    label: 'Simulation',
    type: 'select',
    options: [
      ['', 'Unspecified'],
      ['fixed', 'Fixed'],
      ['historical', 'Historical'],
      ['monte_carlo', 'Monte Carlo'],
    ],
  },
];

export function renderAssumptions(plan = {}, state = {}, defaults = {}) {
  const assumptionSets = normalizeAssumptionSets(state.assumptionSets);
  const activeSet = activeAssumptionSet(assumptionSets);
  const draft = state.draft && typeof state.draft === 'object' ? state.draft : {};
  const warnings = assumptionWarnings(plan, defaults);

  return html`
    <section class="plan-assumptions" data-plan-section="assumptions">
      <header class="section-head compact">
        <span class="section-eyebrow">Assumptions</span>
        <h2 class="section-title">Plan assumptions</h2>
        <p class="section-lede">These are the durable inputs behind Plan, Today, Copilot, simulations, and fit checks.</p>
      </header>

      <div class="assumption-summary">
        <div>
          <span class="story-block-eyebrow">Active assumption set</span>
          <p class="assumption-set-name">${esc(activeSet.name || activeSet.id || 'Default')}</p>
        </div>
        <div>
          <span class="story-block-eyebrow">Quality</span>
          ${warnings.length ? html`
            <ul class="assumption-warning-list">
              ${warnings.map(warning => html`<li>${esc(warning)}</li>`)}
            </ul>
          ` : html`<p class="marginalia">Core assumptions are filled.</p>`}
        </div>
      </div>

      ${state.error ? html`<p class="error-banner">${esc(state.error)}</p>` : ''}

      <div class="assumption-grid" data-form="plan-assumptions">
        ${raw(PLAN_ASSUMPTION_FIELDS.map(field => renderAssumptionField(field, plan, draft, defaults)).join(''))}
        ${renderAssumptionSetPicker(assumptionSets, draft)}
      </div>

      <div class="assumption-actions">
        ${state.dirty ? html`
          <button class="btn btn-primary" data-assumption-action="save" ${state.saving ? 'disabled' : ''}>
            ${state.saving ? 'Saving...' : 'Save assumptions'}
          </button>
          <button class="btn btn-ghost" data-assumption-action="reset" ${state.saving ? 'disabled' : ''}>Reset</button>
        ` : html`
          <span class="marginalia">No staged changes.</span>
        `}
      </div>
    </section>
  `;
}

export function buildPlanSettingsPatch(plan = {}, draft = {}) {
  const settings = plan.settings && typeof plan.settings === 'object' ? plan.settings : {};
  const patch = {};
  for (const field of PLAN_ASSUMPTION_FIELDS) {
    if (!Object.prototype.hasOwnProperty.call(draft, field.key)) continue;
    const nextValue = parseDraftValue(field, draft[field.key]);
    const currentValue = normalizeComparableValue(field, settings[field.key]);
    if (!sameValue(nextValue, currentValue)) {
      patch[field.key] = nextValue;
    }
  }
  return patch;
}

export function buildAssumptionSetsPayload(assumptionSets = {}, activeAssumptionSetId = '') {
  const normalized = normalizeAssumptionSets(assumptionSets);
  return {
    schema_version: Number(normalized.schema_version || 2),
    active_assumption_set_id: String(activeAssumptionSetId || normalized.active_assumption_set_id || 'default').trim() || 'default',
    sets: normalized.sets,
  };
}

export function assumptionCoverageSummary(settings = {}, defaults = {}) {
  const reviewed = PLAN_ASSUMPTION_FIELDS.filter(
    field => settings?.[field.key] != null && settings[field.key] !== '',
  ).length;
  const resolved = PLAN_ASSUMPTION_FIELDS.filter(field => {
    if (settings?.[field.key] != null && settings[field.key] !== '') return true;
    const row = defaults?.[field.key];
    const value = row && typeof row === 'object' ? row.value : row;
    return value != null && value !== '';
  }).length;
  const starting = Math.max(0, resolved - reviewed);
  if (!reviewed && starting) return `Using ${starting} starting assumption${starting === 1 ? '' : 's'}`;
  if (reviewed && starting) return `${reviewed} reviewed · ${starting} starting value${starting === 1 ? '' : 's'}`;
  if (reviewed) return `${reviewed} reviewed`;
  return 'Assumptions need review';
}

export function draftValueForField(field, plan = {}, draft = {}, defaults = {}) {
  if (Object.prototype.hasOwnProperty.call(draft, field.key)) {
    return String(draft[field.key] ?? '');
  }
  const settings = plan.settings && typeof plan.settings === 'object' ? plan.settings : {};
  const durable = settings[field.key];
  const fallback = defaults?.[field.key];
  const value = durable == null || durable === ''
    ? (fallback && typeof fallback === 'object' ? fallback.value : fallback)
    : durable;
  if (value == null) return '';
  if (field.type === 'percent') return trimNumber(Number(value) * 100);
  return String(value);
}

function renderAssumptionField(field, plan, draft, defaults) {
  const durableValue = plan.settings?.[field.key];
  const fallback = defaults?.[field.key];
  const fallbackValue = fallback && typeof fallback === 'object' ? fallback.value : fallback;
  const source = fallback && typeof fallback === 'object' ? fallback.source : 'starting value';
  const value = draftValueForField(field, plan, draft, defaults);
  const usesFallback = durableValue == null || durableValue === '';
  const displayValue = usesFallback && fallbackValue != null && fallbackValue !== ''
    ? `Starting: ${displayFieldValue(field, fallbackValue)} · ${humanText(source)}; review and save`
    : displayFieldValue(field, durableValue);
  const weak = isWeakField(field.key, usesFallback ? fallbackValue : durableValue);
  return html`
    <label class="assumption-field ${weak ? 'weak' : ''}">
      <span class="assumption-label">${esc(field.label)}</span>
      ${field.type === 'select' ? renderSelect(field, value) : renderInput(field, value)}
      <span class="assumption-current">${esc(displayValue)}</span>
    </label>
  `;
}

function renderInput(field, value) {
  const step = field.type === 'integer' ? '1' : '0.1';
  const inputMode = field.type === 'integer' || field.type === 'money' || field.type === 'percent'
    ? 'decimal'
    : 'text';
  return html`
    <input
      data-assumption-field="${esc(field.key)}"
      type="number"
      step="${step}"
      inputmode="${inputMode}"
      value="${esc(value)}"
    />
  `;
}

function renderSelect(field, value) {
  return html`
    <select data-assumption-field="${esc(field.key)}">
      ${(field.options || []).map(([optionValue, label]) => html`
        <option value="${esc(optionValue)}" ${String(optionValue) === String(value) ? 'selected' : ''}>${esc(label)}</option>
      `)}
    </select>
  `;
}

function renderAssumptionSetPicker(assumptionSets, draft) {
  const activeId = String(draft.active_assumption_set_id ?? assumptionSets.active_assumption_set_id ?? 'default');
  const sets = assumptionSets.sets.length
    ? assumptionSets.sets
    : [{ id: 'default', name: 'Default' }];
  return html`
    <label class="assumption-field assumption-field-wide">
      <span class="assumption-label">Active assumption set</span>
      <select data-assumption-field="active_assumption_set_id">
        ${sets.map(set => {
          const id = String(set.id || '').trim() || 'default';
          const name = String(set.name || id).trim();
          return html`<option value="${esc(id)}" ${id === activeId ? 'selected' : ''}>${esc(name)}</option>`;
        })}
      </select>
      <span class="assumption-current">${sets.length} saved set${sets.length === 1 ? '' : 's'}</span>
    </label>
  `;
}

function normalizeAssumptionSets(assumptionSets = {}) {
  const sets = Array.isArray(assumptionSets?.sets)
    ? assumptionSets.sets.filter(item => item && typeof item === 'object')
    : [];
  return {
    schema_version: assumptionSets?.schema_version || 2,
    active_assumption_set_id: String(assumptionSets?.active_assumption_set_id || 'default').trim() || 'default',
    sets,
  };
}

function activeAssumptionSet(assumptionSets) {
  const activeId = String(assumptionSets.active_assumption_set_id || 'default');
  return assumptionSets.sets.find(set => String(set.id || '') === activeId)
    || assumptionSets.sets[0]
    || { id: 'default', name: 'Default' };
}

function assumptionWarnings(plan = {}, defaults = {}) {
  const settings = plan.settings && typeof plan.settings === 'object' ? plan.settings : {};
  const warnings = [];
  if ((settings.marginal_tax_rate == null || settings.marginal_tax_rate === '') && defaults?.marginal_tax_rate?.value == null) {
    warnings.push('Tax assumption missing');
  }
  if (
    (settings.annual_contribution_usd == null || Number(settings.annual_contribution_usd) <= 0)
    && !(Number(defaults?.annual_contribution_usd?.value) > 0)
  ) {
    warnings.push('Contribution assumption missing');
  }
  if ((settings.expected_return_baseline == null || settings.expected_return_baseline === '') && defaults?.expected_return_baseline?.value == null) {
    warnings.push('Expected return missing');
  }
  for (const key of ['marginal_tax_rate', 'filing_status']) {
    const fallback = defaults?.[key];
    if (fallback?.source !== 'profile' || settings[key] == null || settings[key] === '') continue;
    if (String(settings[key]) !== String(fallback.value)) {
      warnings.push(`${PLAN_ASSUMPTION_FIELDS.find(field => field.key === key)?.label || key} differs from Profile`);
    }
  }
  return warnings;
}

function isWeakField(key, value) {
  if (key === 'annual_contribution_usd') return value == null || Number(value) <= 0;
  if (key === 'marginal_tax_rate') return value == null || value === '';
  if (key === 'expected_return_baseline') return value == null || value === '';
  return false;
}

function displayFieldValue(field, value) {
  if (value == null || value === '') return 'Not set';
  if (field.type === 'money') return fmtUsd(Number(value));
  if (field.type === 'percent') return `${trimNumber(Number(value) * 100)}%`;
  if (field.type === 'select') return humanText(value);
  return String(value);
}

function parseDraftValue(field, rawValue) {
  const text = String(rawValue ?? '').trim();
  if (!text) return null;
  if (field.type === 'select') return text;
  const number = Number(text);
  if (!Number.isFinite(number)) return null;
  if (field.type === 'integer') return Math.round(number);
  if (field.type === 'percent') return Number((number / 100).toFixed(6));
  return number;
}

function normalizeComparableValue(field, value) {
  if (value == null || value === '') return null;
  if (field.type === 'integer') return Math.round(Number(value));
  if (field.type === 'percent') return Number(Number(value).toFixed(6));
  if (field.type === 'money') return Number(value);
  return String(value);
}

function sameValue(left, right) {
  if (left == null && right == null) return true;
  if (typeof left === 'number' || typeof right === 'number') {
    return Number(left) === Number(right);
  }
  return String(left) === String(right);
}

function trimNumber(value) {
  if (!Number.isFinite(value)) return '';
  return String(Number(value.toFixed(3)));
}

function humanText(value) {
  return String(value || '').replace(/_/g, ' ');
}
