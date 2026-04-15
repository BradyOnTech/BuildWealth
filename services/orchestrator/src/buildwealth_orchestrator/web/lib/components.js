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
    if (f.kind === 'select') {
      const options = [
        { value: '', label: f.emptyLabel || 'Select an option' },
        ...(Array.isArray(f.options) ? f.options : []),
      ];
      const optionHtml = options.map(option => `<option value="${option.value}">${option.label}</option>`).join('');
      return `<label class="field"><span>${f.label}</span><select id="${id}" autocomplete="off">${optionHtml}</select></label>`;
    }
    const maxAttr = f.max !== undefined ? `max="${f.max}"` : '';
    return `<label class="field"><span>${f.label}</span><input type="number" id="${id}" step="${f.step}" min="${f.min ?? ''}" ${maxAttr} placeholder="${f.placeholder}" /></label>`;
  }).join('');
}

function resolveInputElement(field, getInputById) {
  const resolver = typeof getInputById === 'function' ? getInputById : byId;
  return resolver(field.inputId);
}

function isPlanSettingFieldMetadata(field) {
  if (!field || typeof field !== 'object') return false;
  if (!String(field.key || '').trim()) return false;
  if (!String(field.inputId || '').trim()) return false;
  if (field.kind === 'select') return Array.isArray(field.options);
  return true;
}

function assertPlanSettingFieldMetadata(fields, contextLabel = 'plan settings') {
  if (!Array.isArray(fields) || fields.some(field => !isPlanSettingFieldMetadata(field))) {
    throw new Error(`Invalid ${contextLabel} field metadata.`);
  }
}

export function collectSettingsPayload(fields, { includeNulls = false, getInputById } = {}) {
  const payload = {};
  for (const field of fields) {
    const input = resolveInputElement(field, getInputById);
    if (!input) continue;
    if (field.kind === 'select') {
      const value = String(input.value || '').trim();
      const validValues = new Set((Array.isArray(field.options) ? field.options : []).map(option => String(option.value)));
      if (!value || (validValues.size && !validValues.has(value))) {
        if (includeNulls) payload[field.key] = null;
        continue;
      }
      payload[field.key] = value;
      continue;
    }
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

export function setSettingsInputs(fields, settingsPayload, { getInputById } = {}) {
  const settings = settingsPayload && typeof settingsPayload === 'object' ? settingsPayload : {};
  for (const field of fields) {
    const input = resolveInputElement(field, getInputById);
    if (!input) continue;
    const raw = settings[field.key];
    if (raw === null || raw === undefined || raw === '') { input.value = ''; continue; }
    if (field.kind === 'select') {
      const value = String(raw).trim();
      const validValues = new Set((Array.isArray(field.options) ? field.options : []).map(option => String(option.value)));
      input.value = validValues.has(value) ? value : '';
      continue;
    }
    input.value = formatNumericInput(Number(raw) * (field.scale || 1));
  }
}

export function planSettingsGridHtml(fields, prefix = '') {
  assertPlanSettingFieldMetadata(fields, 'plan settings grid');
  return settingsGridHtml(fields, prefix);
}

export function collectPlanSettingsPayload(fields, options = {}) {
  assertPlanSettingFieldMetadata(fields, 'plan settings');
  return collectSettingsPayload(fields, options);
}

export function setPlanSettingsInputs(fields, settingsPayload, options = {}) {
  assertPlanSettingFieldMetadata(fields, 'plan settings');
  setSettingsInputs(fields, settingsPayload, options);
}
