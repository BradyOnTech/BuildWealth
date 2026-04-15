import { state } from './state.js';
import { byId, parseOptionalNumericField, formatNumericInput } from './utils.js';

export function emptyFinancialProfile() {
  return {
    income_items: [], expense_items: [], debt_items: [], goal_items: [], physical_assets: [],
    tax_profile: { filing_status: '', marginal_tax_rate: null, effective_tax_rate: null, state_tax_rate: null, state: '' },
    flags: { no_debt: false, no_goals: false },
    notes: '', updated_at: null,
  };
}

export function recommendationStatusClass(statusValue) {
  const s = String(statusValue || 'proposed').toLowerCase();
  if (s === 'applied') return 'complete';
  if (s === 'rejected') return 'incomplete';
  return 'attention';
}

export function renderItemList(containerId, items, formatter) {
  const container = byId(containerId);
  if (!container) return;
  container.innerHTML = '';
  if (!Array.isArray(items) || !items.length) {
    container.innerHTML = '<p class="empty-text">No items available.</p>';
    return;
  }
  for (const item of items) container.appendChild(formatter(item));
}

export function planSelectOptions(selectId, currentValue = '') {
  const select = byId(selectId);
  if (!select) return;
  const current = currentValue || '';
  select.innerHTML = '<option value="">Active plan (default)</option>';
  for (const plan of state.plans) {
    const opt = document.createElement('option');
    opt.value = plan.id;
    opt.textContent = plan.is_active ? `${plan.title} (Active)` : plan.title;
    select.appendChild(opt);
  }
  const has = [...select.options].some(o => o.value === current);
  if (has) select.value = current;
  else if (state.currentPlanId && [...select.options].some(o => o.value === state.currentPlanId)) {
    select.value = state.currentPlanId;
  } else select.value = '';
}

export function settingsGridHtml(fields, prefix = '') {
  return fields.map(f => {
    const id = prefix ? f.inputId.replace(/^(setting|diff)-/, `${prefix}-`) : f.inputId;
    const maxAttr = f.max !== undefined ? `max="${f.max}"` : '';
    return `<label class="field"><span>${f.label}</span><input type="number" id="${id}" step="${f.step}" min="${f.min ?? ''}" ${maxAttr} placeholder="${f.placeholder}" /></label>`;
  }).join('');
}

export function collectSettingsPayload(fields, { includeNulls }) {
  const payload = {};
  for (const field of fields) {
    const input = byId(field.inputId);
    if (!input) continue;
    const parsed = parseOptionalNumericField(input.value, field.key, Boolean(field.integer));
    if (!parsed.present) {
      if (includeNulls) payload[field.key] = null;
      continue;
    }
    const divisor = field.scale || 1;
    payload[field.key] = field.integer ? Math.trunc(parsed.value / divisor) : parsed.value / divisor;
  }
  return payload;
}

export function setSettingsInputs(fields, settingsPayload) {
  const settings = settingsPayload && typeof settingsPayload === 'object' ? settingsPayload : {};
  for (const field of fields) {
    const input = byId(field.inputId);
    if (!input) continue;
    const raw = settings[field.key];
    if (raw === null || raw === undefined || raw === '') { input.value = ''; continue; }
    input.value = formatNumericInput(Number(raw) * (field.scale || 1));
  }
}
