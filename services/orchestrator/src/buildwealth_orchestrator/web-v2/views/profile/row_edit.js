// Profile tables · inline row editing + amount-unit machinery.
//
// tables.js owns the section specs and the read-only rendering; this module
// owns everything about mutating a row in place:
//   - the single-row edit state (one row at a time, across all tables)
//   - draft building (storage → input space, e.g. ratio 0.03 → "3" percent)
//   - the Monthly | Annual segmented toggle for `monthly_amount_usd` inputs
//   - Save (Enter) / Cancel (Escape) keyboard handling
//
// The pure helpers (buildRowDraft, rebuildRow, toMonthlyAmount,
// fromMonthlyAmount, convertAmount, applyAmountUnit) take the section spec as
// an argument and never touch the DOM, so node tests can exercise them
// directly.

import { esc } from '../../lib/dom.js';
import { persist, render as renderProfile } from '../profile.js';

export const AMOUNT_FIELD_KEY = 'monthly_amount_usd';

/* ─────────────  Amount unit (module state, remembered)  ───────────── */

let amountUnit = 'monthly';

export function getAmountUnit() {
  return amountUnit;
}

export function setAmountUnit(unit) {
  amountUnit = unit === 'annual' ? 'annual' : 'monthly';
}

// Input value (in `unit`) → stored monthly amount. Non-numeric / empty values
// pass through unchanged so build() validation stays the single gatekeeper.
export function toMonthlyAmount(value, unit = amountUnit) {
  return convertAmount(value, unit, 'monthly');
}

// Stored monthly amount → display value in `unit`.
export function fromMonthlyAmount(value, unit = amountUnit) {
  return convertAmount(value, 'monthly', unit);
}

export function convertAmount(value, fromUnit, toUnit) {
  if (fromUnit === toUnit) return value;
  if (value === '' || value == null) return value;
  const n = Number(value);
  if (!Number.isFinite(n)) return value;
  const converted = toUnit === 'monthly' ? n / 12 : n * 12;
  return Math.round(converted * 100) / 100;
}

export function sectionHasAmount(section) {
  return (section?.composer || []).some(f => f.key === AMOUNT_FIELD_KEY);
}

// Returns a copy of `draft` with the amount field converted from `unit` into
// stored monthly dollars. Sections without an amount field pass through.
export function applyAmountUnit(section, draft, unit = amountUnit) {
  if (!sectionHasAmount(section)) return { ...draft };
  return { ...draft, [AMOUNT_FIELD_KEY]: toMonthlyAmount(draft[AMOUNT_FIELD_KEY], unit) };
}

/* ─────────────  Pure draft helpers  ───────────── */

// Storage item → composer-input-space draft (percent for ratio fields,
// booleans for checkboxes, '' for null). Amounts stay monthly; display
// conversion happens at render time.
export function buildRowDraft(section, item) {
  const draft = {};
  for (const field of section.composer) {
    const value = item?.[field.key];
    if (field.kind === 'checkbox') {
      draft[field.key] = !!value;
      continue;
    }
    if (value == null || value === '') {
      draft[field.key] = '';
      continue;
    }
    // Stored rates are decimal fractions (0.03); inputs take percent (3).
    draft[field.key] = field.ratio ? Math.round(Number(value) * 100 * 1e6) / 1e6 : value;
  }
  return draft;
}

// build() generates a fresh id; an inline edit must keep the row's identity.
export function rebuildRow(section, draft, id) {
  const row = section.build(draft);
  return id ? { ...row, id } : row;
}

/* ─────────────  Edit state (one row at a time)  ───────────── */

let editing = null; // { sectionKey, rowId, ui, section, draft }

export function isRowEditing(sectionKey, rowId) {
  return !!editing && editing.sectionKey === sectionKey && editing.rowId === rowId;
}

export function startRowEdit(ui, section, rowId) {
  if (!rowId) return;
  editing = { sectionKey: section.key, rowId, ui, section, draft: null };
  ui.saveError = null;
  renderProfile();
}

export function cancelRowEdit() {
  if (!editing) return;
  const ui = editing.ui;
  editing = null;
  ui.saveError = null;
  renderProfile();
}

export async function saveRowEdit(ui, section) {
  if (!editing || editing.sectionKey !== section.key) return;
  const rowId = editing.rowId;
  const items = ui.profile?.[section.key] || [];
  const index = items.findIndex(item => item.id === rowId);
  if (index === -1) { editing = null; renderProfile(); return; }

  const draft = readEditDraft(section);
  editing.draft = draft; // keep typed values if validation fails
  let row;
  try {
    row = {
      ...items[index],
      ...rebuildRow(section, applyAmountUnit(section, draft, amountUnit), rowId),
    };
  } catch (err) {
    ui.saveError = err.message || 'Could not validate row.';
    renderProfile();
    return;
  }
  const previous = items[index];
  const previousFlags = { ...(ui.profile.flags || {}) };
  items[index] = row;
  if (section.key === 'expense_items') {
    ui.profile.flags = { ...(ui.profile.flags || {}), expenses_complete: false };
  }
  editing = null;
  const saved = await persist();
  if (!saved) {
    items[index] = previous;
    ui.profile.flags = previousFlags;
    renderProfile();
  }
}

function readEditDraft(section) {
  const draft = {};
  if (typeof document === 'undefined') return draft;
  const inputs = document.querySelectorAll(`[data-edit-table="${section.key}"]`);
  for (const el of inputs) {
    const fieldKey = el.getAttribute('data-edit-input');
    const field = section.composer.find(f => f.key === fieldKey);
    if (!field) continue;
    draft[fieldKey] = field.kind === 'checkbox' ? !!el.checked : el.value;
  }
  return draft;
}

// Save on Enter, cancel on Escape — scoped to inputs inside an editing row.
if (typeof document !== 'undefined') {
  document.addEventListener('keydown', (e) => {
    if (!editing) return;
    const el = e.target instanceof Element ? e.target.closest('[data-edit-input]') : null;
    if (!el) return;
    if (e.key === 'Enter') {
      e.preventDefault();
      saveRowEdit(editing.ui, editing.section);
    } else if (e.key === 'Escape') {
      e.preventDefault();
      cancelRowEdit();
    }
  });
}

/* ─────────────  Amount unit toggle (composer + edit rows)  ───────────── */

// Toggle clicks mutate the DOM in place (values + pressed state) instead of
// re-rendering — a re-render would wipe whatever the user has typed so far.
export function handleAmountUnit(dataset) {
  const next = dataset.unit === 'annual' ? 'annual' : 'monthly';
  if (next === amountUnit) return;
  const prev = amountUnit;
  amountUnit = next;
  if (typeof document === 'undefined') return;
  for (const input of document.querySelectorAll('[data-amount-input]')) {
    // In a new-row composer, changing the unit commonly corrects the user's
    // intent after typing (for example 62000, then Annual). Preserve that
    // typed number. Existing saved rows still convert for convenient review.
    if (input.hasAttribute('data-composer-input') && String(input.value || '').trim()) continue;
    const converted = convertAmount(input.value, prev, next);
    if (converted !== input.value) input.value = String(converted);
  }
  for (const btn of document.querySelectorAll('[data-table-action="amount-unit"]')) {
    const pressed = btn.getAttribute('data-unit') === next;
    btn.setAttribute('aria-pressed', pressed ? 'true' : 'false');
    btn.classList.toggle('active', pressed);
  }
}

export function amountToggleHtml(sectionKey) {
  const option = (value, label) => `
    <button class="amount-unit-option ${amountUnit === value ? 'active' : ''}" type="button"
            aria-pressed="${amountUnit === value ? 'true' : 'false'}"
            data-table-action="amount-unit"
            data-table-key="${esc(sectionKey)}"
            data-unit="${value}">${label}</button>`;
  return `
    <span class="amount-unit-toggle" role="group" aria-label="Amount unit">
      ${option('monthly', 'Monthly')}
      ${option('annual', 'Annual')}
    </span>`;
}

/* ─────────────  Edit-row rendering  ───────────── */

export function renderEditRow(section, item) {
  const draft = editing?.draft && editing.rowId === item.id
    ? editing.draft
    : displayDraft(section, item);
  const fields = section.composer
    .map(field => editFieldHtml(section, field, draft[field.key]))
    .join('');
  const columnCount = section.columns.length + 3;
  return `
    <tr class="profile-row-editing">
      <td colspan="${columnCount}">
        <section class="profile-row-edit-panel" aria-label="Edit ${esc(item.label || item.display_name || section.singular)}">
          <header>
            <div>
              <span class="status-pill pending"><span class="dot"></span>Editing</span>
              <strong>${esc(item.label || item.display_name || `This ${section.singular}`)}</strong>
            </div>
            <span class="profile-edit-keyboard">Enter to save · Esc to cancel</span>
          </header>
          <div class="profile-row-edit-grid">${fields}</div>
          <footer>
            <button class="btn btn-quiet" type="button"
                    data-table-action="edit-cancel"
                    data-table-key="${esc(section.key)}"
                    data-row-id="${esc(item.id || '')}">Cancel</button>
            <button class="btn btn-primary" type="button"
                    data-table-action="edit-save"
                    data-table-key="${esc(section.key)}"
                    data-row-id="${esc(item.id || '')}">Save changes</button>
          </footer>
        </section>
      </td>
    </tr>
  `;
}

// Draft in input space, with the amount shown in the currently-selected unit.
function displayDraft(section, item) {
  const draft = buildRowDraft(section, item);
  if (sectionHasAmount(section)) {
    draft[AMOUNT_FIELD_KEY] = fromMonthlyAmount(draft[AMOUNT_FIELD_KEY], amountUnit);
  }
  return draft;
}

function editInputHtml(section, field, value) {
  const id = `edit-${section.key}-${field.key}`;
  const label = field.key === AMOUNT_FIELD_KEY ? 'Amount' : field.label;
  if (field.kind === 'select') {
    const source = typeof field.options === 'function' ? field.options(editing?.ui) : field.options;
    const options = (Array.isArray(source) ? source : [])
      .map(o => `<option value="${esc(o.value)}" ${o.value === value ? 'selected' : ''}>${esc(o.label)}</option>`)
      .join('');
    return `
      <select class="settings-input" id="${id}" aria-label="${esc(label)}"
              data-edit-input="${esc(field.key)}" data-edit-table="${esc(section.key)}">
        ${options}
      </select>`;
  }
  if (field.kind === 'checkbox') {
    return `
      <input type="checkbox" id="${id}" aria-label="${esc(label)}"
             data-edit-input="${esc(field.key)}" data-edit-table="${esc(section.key)}"
             ${value ? 'checked' : ''} />`;
  }
  const isAmount = field.key === AMOUNT_FIELD_KEY;
  const input = `
    <input class="settings-input ${field.kind === 'number' ? 'mono' : ''}"
           id="${id}"
           type="${esc(field.kind)}"
           aria-label="${esc(label)}"
           data-edit-input="${esc(field.key)}"
           data-edit-table="${esc(section.key)}"
           ${isAmount ? 'data-amount-input="1"' : ''}
           ${field.placeholder ? `placeholder="${esc(field.placeholder)}"` : ''}
           ${field.min != null ? `min="${esc(field.min)}"` : ''}
           ${field.max != null ? `max="${esc(field.max)}"` : ''}
           ${field.step != null ? `step="${esc(field.step)}"` : ''}
           value="${esc(value ?? '')}" />`;
  if (!isAmount) return input;
  return `
    <span class="amount-input-row">
      ${input}
      ${amountToggleHtml(section.key)}
    </span>`;
}

function editFieldHtml(section, field, value) {
  if (field.kind === 'checkbox') {
    return `
      <label class="settings-field settings-field-toggle">
        ${editInputHtml(section, field, value)}
        <span><span class="settings-label">${esc(field.label)}</span></span>
      </label>`;
  }
  return `
    <label class="settings-field">
      <span class="settings-label">${esc(field.key === AMOUNT_FIELD_KEY ? 'Amount' : field.label)}</span>
      ${editInputHtml(section, field, value)}
      ${field.hint ? `<small class="settings-hint">${esc(field.hint)}</small>` : ''}
    </label>`;
}
