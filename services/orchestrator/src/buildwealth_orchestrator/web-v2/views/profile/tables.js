// Profile · Editable tables.
// Income / Expenses / Debt / Goals / Physical assets.
// Each section is a declarative spec: columns, the row composer, and the
// row-builder + row-validator used when the user taps "Add". Removal,
// addition, and form drafting all flow through `persist()` so the server
// stays the source of truth and onboarding refreshes automatically.

import { html, raw, esc } from '../../lib/dom.js';
import { fmtUsdOrDash, fmtPctOrDash, unwrapDisplayValue } from '../../lib/format.js';
import { showUndoToast } from '../../lib/undo.js';
import { persist, render as renderProfile, replaceProfileSection } from '../profile.js';
import {
  AMOUNT_FIELD_KEY,
  amountToggleHtml,
  applyAmountUnit,
  cancelRowEdit,
  handleAmountUnit,
  isRowEditing,
  renderEditRow,
  saveRowEdit,
  startRowEdit,
} from './row_edit.js';

/* ─────────────  Specs  ───────────── */

const COMPOSER_DRAFTS = new Map();
const REPLACEMENT_DRAFTS = new Map();

const SECTIONS_BY_KEY = new Map();

export const TABLE_SECTIONS = [
  defineHousehold(),
  defineIncome(),
  defineExpenses(),
  defineDebt(),
  defineGoals(),
  defineAssets(),
  defineInsurance(),
  defineBenefits(),
];

for (const section of TABLE_SECTIONS) SECTIONS_BY_KEY.set(section.key, section);

export function sectionForKey(key) {
  return SECTIONS_BY_KEY.get(key);
}

/* ─────────────  Render  ───────────── */

export function renderTable(ui, section) {
  if (!section) return '';
  const items = ui.profile?.[section.key] || [];
  return html`
    <div class="profile-table-wrap">
      <header class="profile-table-head">
        <div>
          <p class="profile-table-eyebrow">§ ${section.eyebrow}</p>
          <h2 class="profile-table-title">${section.title}</h2>
          <p class="profile-table-lede">${section.lede}</p>
        </div>
        <div class="profile-table-meta">
          <span class="profile-table-count">${items.length} entr${items.length === 1 ? 'y' : 'ies'}</span>
          <button class="btn btn-ghost profile-replace-trigger" type="button"
                  data-table-action="replace-open"
                  data-table-key="${esc(section.key)}">
            Replace section
          </button>
        </div>
      </header>

      ${replacementDraft(section.key)
        ? raw(renderReplacement(ui, section, items))
        : raw(renderComposer(section, ui))}
      ${section.key === 'physical_assets' ? raw(renderAssetConnections(ui, items)) : ''}
      ${raw(renderRows(section, items, ui))}
      ${section.key === 'expense_items' ? raw(renderExpenseConfirmation(ui, items)) : ''}
      ${ui.saveError ? html`<p class="inline-warning">${ui.saveError}</p>` : ''}
    </div>
  `;
}

function renderExpenseConfirmation(ui, items) {
  if (!items.length) return '';
  const complete = !!ui.profile?.flags?.expenses_complete;
  return html`
    <aside class="suggestion-banner">
      <strong>${complete ? 'Monthly budget confirmed.' : 'Is this a representative monthly budget?'}</strong>
      <span>
        ${complete
          ? 'Cash flow, runway, and affordability can use this budget. Editing an expense will ask you to confirm again.'
          : 'Include normal housing, food, transport, insurance, and recurring costs. One rough all-in total is okay if it represents a typical month.'}
      </span>
      <button class="btn btn-ghost" type="button" data-expenses-complete="${complete ? 'false' : 'true'}">
        ${complete ? 'Mark incomplete' : 'Yes, use this budget'}
      </button>
    </aside>
  `;
}

function renderRows(section, items, ui) {
  if (!items.length) {
    // A composer sits directly above this, so the empty state's whole job is one
    // sentence. The shared .empty-block spends ~300px on a centred pilcrow and
    // an italic line — two of them fill a viewport with nothing to act on.
    return html`
      <p class="profile-empty-line">
        <span class="profile-empty-mark" aria-hidden="true">○</span>
        ${section.emptyHint}
      </p>
    `;
  }
  // Per-row Source/Status pulls from optional row-level fields the backend
  // may grow later (item.source, item.status). Until then, rows added through
  // the v2 editor default to "You / Confirmed" — explicit about provenance
  // without claiming knowledge we don't have.
  const headers = section.columns.map(c => `<th>${esc(c.header)}</th>`).join('')
    + '<th>Source</th><th>Status</th><th aria-label="Action"></th>';
  const rows = items.map(item => {
    if (isRowEditing(section.key, item.id)) return renderEditRow(section, item);
    const cells = section.columns.map(col => {
      const rawValue = col.format
        ? col.format(item[col.key], item, ui)
        : unwrapDisplayValue(item[col.key]);
      const displayValue = rawValue == null || typeof rawValue === 'object' ? '—' : rawValue;
      return `<td class="${col.numeric ? 'num' : ''}">${esc(displayValue)}</td>`;
    }).join('');
    const source = humanRowSource(item);
    const status = humanRowStatus(item);
    return `
      <tr>
        ${cells}
        <td class="profile-row-source">${esc(source.label)}</td>
        <td class="profile-row-status">
          <span class="status-pill ${esc(status.tone)}"><span class="dot"></span>${esc(status.label)}</span>
        </td>
        <td class="profile-row-actions">
          <button class="link-quiet" type="button"
                  data-table-action="edit"
                  data-table-key="${esc(section.key)}"
                  data-row-id="${esc(item.id || '')}">
            Edit
          </button>
          <button class="link-quiet danger" type="button"
                  data-table-action="remove"
                  data-table-key="${esc(section.key)}"
                  data-row-id="${esc(item.id || '')}">
            Remove
          </button>
        </td>
      </tr>
    `;
  }).join('');

  return html`
    <div class="profile-table-scroll">
      <table class="profile-table">
        <thead><tr>${raw(headers)}</tr></thead>
        <tbody>${raw(rows)}</tbody>
      </table>
    </div>
  `;
}

function humanRowSource(item) {
  const raw = String(item?.source || item?.source_label || '').trim().toLowerCase();
  if (!raw || raw === 'profile_editor' || raw === 'user' || raw === 'you') {
    return { label: 'You' };
  }
  if (raw === 'copilot' || raw === 'copilot_chat') return { label: 'Copilot' };
  if (raw.startsWith('import')) return { label: 'Import' };
  if (raw === 'plan' || raw === 'plan_workspace') return { label: 'Plan' };
  return { label: raw.replace(/_/g, ' ') };
}

function humanRowStatus(item) {
  const status = String(item?.status || '').toLowerCase();
  if (status === 'pending_review' || status === 'needs_review') return { tone: 'proposed', label: 'Review' };
  if (status === 'stale')     return { tone: 'stale',    label: 'Possibly outdated' };
  if (status === 'rejected')  return { tone: 'rejected', label: 'Rejected' };
  if (status === 'draft')     return { tone: 'pending',  label: 'Draft' };
  return { tone: 'applied', label: 'Confirmed' };
}

// The 2-3 required fields render by default; everything else folds into a
// "More detail" disclosure so adding a row stays a two-field affair.
export function composerFieldSplit(section) {
  const primaryKeys = Array.isArray(section.primary) ? section.primary : [];
  return {
    primary: section.composer.filter(f => primaryKeys.includes(f.key)),
    more: section.composer.filter(f => !primaryKeys.includes(f.key)),
  };
}

function renderComposer(section, ui) {
  const draft = composerDraft(section.key);
  const { primary, more } = composerFieldSplit(section);
  const primaryFields = (primary.length ? primary : section.composer).map(f => fieldHtml(section.key, f, draft, ui)).join('');
  const moreFields = primary.length ? more.map(f => fieldHtml(section.key, f, draft, ui)).join('') : '';
  return html`
    <form class="profile-composer" data-composer-key="${esc(section.key)}" novalidate>
      <div class="profile-composer-grid">
        ${raw(primaryFields)}
      </div>
      ${moreFields ? raw(`
        <details class="composer-more">
          <summary>More detail</summary>
          <div class="profile-composer-grid">${moreFields}</div>
        </details>
      `) : ''}
      <div class="profile-composer-actions">
        <button class="btn btn-primary" type="button"
                data-table-add="${esc(section.key)}">
          Add ${section.singular}
        </button>
      </div>
    </form>
  `;
}

function fieldHtml(key, field, draft, ui, scope = 'composer') {
  const value = draft[field.key] ?? (
    key === 'income_items' && field.key === 'is_pre_tax' ? true : ''
  );
  const id = `${scope}-${key}-${field.key}`;
  const inputAttr = scope === 'replace' ? 'data-replace-input' : 'data-composer-input';
  const tableAttr = scope === 'replace' ? 'data-replace-table' : 'data-composer-table';
  if (field.key === AMOUNT_FIELD_KEY) {
    // People think in annual salary; storage is monthly. The unit rides on
    // the segmented toggle (module-level, remembered), so the label is just
    // "Amount" — handleAdd converts before build().
    return `
      <div class="settings-field">
        <span class="settings-label">Amount</span>
        <span class="amount-input-row">
          <input class="settings-input mono"
                 id="${id}"
                 type="number"
                 aria-label="Amount"
                 ${inputAttr}="${esc(field.key)}"
                 ${tableAttr}="${esc(key)}"
                 data-amount-input="1"
                 ${field.placeholder ? `placeholder="${esc(field.placeholder)}"` : ''}
                 ${field.min != null ? `min="${esc(field.min)}"` : ''}
                 ${field.step != null ? `step="${esc(field.step)}"` : ''}
                 value="${esc(value)}" />
          ${amountToggleHtml(key)}
        </span>
      </div>
    `;
  }
  if (field.kind === 'select') {
    const options = fieldOptions(field, ui).map(o => `<option value="${esc(o.value)}" ${o.value === value ? 'selected' : ''}>${esc(o.label)}</option>`).join('');
    return `
      <label class="settings-field">
        <span class="settings-label">${esc(field.label)}</span>
        <select class="settings-input" id="${id}" ${inputAttr}="${esc(field.key)}" ${tableAttr}="${esc(key)}">
          ${options}
        </select>
      </label>
    `;
  }
  if (field.kind === 'checkbox') {
    return `
      <label class="settings-field settings-field-toggle">
        <input type="checkbox" id="${id}" ${inputAttr}="${esc(field.key)}" ${tableAttr}="${esc(key)}" ${value ? 'checked' : ''} />
        <span><span class="settings-label">${esc(field.label)}</span></span>
      </label>
    `;
  }
  return `
    <label class="settings-field">
      <span class="settings-label">${esc(field.label)}</span>
      <input class="settings-input ${field.kind === 'number' ? 'mono' : ''}"
             id="${id}"
             type="${esc(field.kind)}"
             ${inputAttr}="${esc(field.key)}"
             ${tableAttr}="${esc(key)}"
             ${field.placeholder ? `placeholder="${esc(field.placeholder)}"` : ''}
             ${field.min != null ? `min="${esc(field.min)}"` : ''}
             ${field.max != null ? `max="${esc(field.max)}"` : ''}
             ${field.step != null ? `step="${esc(field.step)}"` : ''}
             value="${esc(value)}" />
      ${field.hint ? `<small class="settings-hint">${esc(field.hint)}</small>` : ''}
    </label>
  `;
}

function fieldOptions(field, ui) {
  const options = typeof field.options === 'function' ? field.options(ui) : field.options;
  return Array.isArray(options) ? options : [];
}

function replacementDraft(key) {
  return REPLACEMENT_DRAFTS.get(key) || null;
}

function renderReplacement(ui, section, currentItems) {
  const replacement = replacementDraft(section.key);
  if (!replacement) return '';
  const { primary, more } = composerFieldSplit(section);
  const fields = primary.length ? [...primary, ...more] : section.composer;
  const draft = replacement.entry || {};
  const proposed = replacement.items || [];
  return html`
    <section class="profile-replace-panel" aria-label="Replace ${esc(section.title)}">
      <header class="profile-replace-head">
        <div>
          <p class="profile-card-kicker">Section-only change</p>
          <h3>Replace ${section.title.toLowerCase()}</h3>
          <p>
            ${currentItems.length} current entr${currentItems.length === 1 ? 'y' : 'ies'} will be replaced by
            ${proposed.length} reviewed entr${proposed.length === 1 ? 'y' : 'ies'}.
            Nothing outside ${section.title} will change.
          </p>
        </div>
        <button class="btn btn-quiet" type="button" data-table-action="replace-cancel"
                data-table-key="${esc(section.key)}">Cancel</button>
      </header>
      <div class="profile-replace-current">
        <span>Currently saved</span>
        <strong>${currentItems.length ? currentItems.map(item => item.label || item.display_name || 'Untitled').slice(0, 4).join(' · ') : 'No entries'}</strong>
      </div>
      <div class="profile-replace-composer">
        <div class="profile-composer-grid">
          ${raw(fields.map(field => fieldHtml(section.key, field, draft, ui, 'replace')).join(''))}
        </div>
        <button class="btn btn-ghost" type="button" data-table-action="replace-add"
                data-table-key="${esc(section.key)}">Add to replacement</button>
      </div>
      <div class="profile-replace-proposed">
        <p class="settings-label">Proposed replacement</p>
        ${proposed.length ? html`
          <ol>
            ${proposed.map(item => html`
              <li>
                <span>
                  <strong>${item.label || item.display_name || 'Untitled'}</strong>
                  ${item.monthly_amount_usd != null ? html`<small>${fmtUsdOrDash(item.monthly_amount_usd)} monthly</small>` : ''}
                </span>
                <button class="link-quiet danger" type="button"
                        data-table-action="replace-remove"
                        data-table-key="${esc(section.key)}"
                        data-replace-id="${esc(item.id || '')}">Remove</button>
              </li>
            `)}
          </ol>
        ` : html`<p class="profile-replace-empty">Add at least one entry, or apply an empty replacement to clear this section.</p>`}
      </div>
      <footer class="profile-replace-actions">
        <p><strong>Before:</strong> ${currentItems.length} · <strong>After:</strong> ${proposed.length}</p>
        <button class="btn ${proposed.length ? 'btn-primary' : 'btn-danger'}" type="button"
                data-table-action="replace-apply"
                data-table-key="${esc(section.key)}"
                ${ui.saving ? 'disabled' : ''}>
          ${ui.saving ? 'Applying…' : proposed.length ? `Replace only ${section.title}` : `Clear only ${section.title}`}
        </button>
      </footer>
    </section>
  `;
}

function renderAssetConnections(ui, assets) {
  if (!assets.length) return '';
  const debts = ui.profile?.debt_items || [];
  const expenses = ui.profile?.expense_items || [];
  const incomeItems = ui.profile?.income_items || [];
  return html`
    <section class="property-card-grid" aria-label="Property and vehicle overview">
      ${assets.map(asset => {
        const linkedDebts = debts.filter(debt => debt.linked_asset_id === asset.id);
        const linkedExpenses = expenses.filter(expense => expense.linked_asset_id === asset.id);
        const linkedIncome = incomeItems.filter(income => income.linked_asset_id === asset.id);
        const debtBalance = linkedDebts.reduce((sum, debt) => sum + Number(debt.balance_usd || 0), 0);
        const debtPayment = linkedDebts.reduce((sum, debt) => sum + Number(debt.minimum_payment_usd || 0), 0);
        const operatingCost = linkedExpenses
          .filter(expense => !expense.linked_debt_id)
          .reduce((sum, expense) => sum + Number(expense.monthly_amount_usd || 0), 0);
        const monthlyIncome = linkedIncome.reduce(
          (sum, income) => sum + Number(income.monthly_amount_usd || 0),
          0,
        );
        const ownership = Math.min(Math.max(Number(asset.ownership_pct ?? 100), 0), 100) / 100;
        const householdValue = Number(asset.current_value_usd || 0) * ownership;
        const equity = householdValue - debtBalance;
        return html`
          <article class="property-card">
            <header>
              <div>
                <p class="profile-card-kicker">${humanWord(asset.asset_subtype || asset.asset_type)}</p>
                <h3>${asset.label || 'Untitled asset'}</h3>
              </div>
              <span class="status-pill ${asset.include_in_plan_funding ? 'applied' : 'pending'}">
                <span class="dot"></span>${asset.include_in_plan_funding ? 'Plan funding' : 'Net worth only'}
              </span>
            </header>
            <dl>
              <div><dt>Household value</dt><dd>${fmtUsdOrDash(householdValue)}</dd></div>
              <div><dt>Linked debt</dt><dd>${fmtUsdOrDash(debtBalance)}</dd></div>
              <div><dt>Net equity</dt><dd>${fmtUsdOrDash(equity)}</dd></div>
              <div><dt>Monthly payment</dt><dd>${fmtUsdOrDash(debtPayment)}</dd></div>
              <div><dt>Operating costs</dt><dd>${fmtUsdOrDash(operatingCost)}</dd></div>
              <div><dt>Linked income</dt><dd>${fmtUsdOrDash(monthlyIncome)}</dd></div>
              <div><dt>Intent</dt><dd>${humanWord(asset.disposition_intent || 'keep')}</dd></div>
            </dl>
            <p class="property-card-foot">
              ${linkedDebts.length || linkedExpenses.length
                ? `${linkedDebts.length} linked debt${linkedDebts.length === 1 ? '' : 's'} · ${linkedExpenses.length} linked cost${linkedExpenses.length === 1 ? '' : 's'}`
                : 'Link its financing in Debt and operating costs in Expenses.'}
            </p>
          </article>
        `;
      })}
    </section>
  `;
}

/* ─────────────  Actions  ───────────── */

async function handleRemove(ui, section, dataset) {
  const id = dataset.rowId;
  if (!id) return;
  const items = ui.profile?.[section.key] || [];
  const removed = items.find(item => item.id === id);
  if (!removed) return;
  const prior = captureLinkedState(ui);
  ui.profile[section.key] = items.filter(item => item.id !== id);
  unlinkReferences(ui, section.key, id);
  if (section.key === 'expense_items') {
    ui.profile.flags = { ...(ui.profile.flags || {}), expenses_complete: false };
  }
  const saved = await persist();
  if (!saved) {
    restoreLinkedState(ui, prior);
    renderProfile();
    return;
  }
  const label = removed.label || removed.display_name || `this ${section.singular}`;
  showUndoToast({
    message: `Removed ${label}`,
    onUndo: async () => {
      restoreLinkedState(ui, prior);
      await persist();
    },
  });
}

async function handleAdd(ui, section, root) {
  const draft = composerDraft(section.key);
  // Pull the latest values out of the DOM so we don't need to wire change
  // events on every input — the composer is short-lived per section view.
  const inputs = root.querySelectorAll(`[data-composer-table="${section.key}"]`);
  for (const el of inputs) {
    const fieldKey = el.getAttribute('data-composer-input');
    const field = section.composer.find(f => f.key === fieldKey);
    if (!field) continue;
    if (field.kind === 'checkbox') {
      draft[fieldKey] = !!el.checked;
    } else {
      draft[fieldKey] = el.value;
    }
  }
  let row;
  try {
    // Convert Annual-entered amounts to stored monthly dollars on a copy so a
    // failed add re-renders the composer with what the user actually typed.
    row = section.build(applyAmountUnit(section, draft));
  } catch (err) {
    ui.saveError = err.message || 'Could not validate row.';
    renderProfile();
    return;
  }
  if (!Array.isArray(ui.profile[section.key])) ui.profile[section.key] = [];
  const priorItems = ui.profile[section.key].slice();
  const priorFlags = { ...(ui.profile.flags || {}) };
  ui.profile[section.key].push(row);
  if (section.key === 'expense_items') {
    ui.profile.flags = { ...(ui.profile.flags || {}), expenses_complete: false };
  }
  COMPOSER_DRAFTS.set(section.key, {});
  const saved = await persist();
  if (!saved) {
    ui.profile[section.key] = priorItems;
    ui.profile.flags = priorFlags;
    renderProfile();
  }
}

function handleReplaceOpen(ui, section) {
  REPLACEMENT_DRAFTS.set(section.key, { items: [], entry: {} });
  ui.saveError = null;
  renderProfile();
}

function handleReplaceCancel(ui, section) {
  REPLACEMENT_DRAFTS.delete(section.key);
  ui.saveError = null;
  renderProfile();
}

function handleReplaceAdd(ui, section) {
  const replacement = replacementDraft(section.key);
  if (!replacement || typeof document === 'undefined') return;
  const draft = {};
  for (const el of document.querySelectorAll(`[data-replace-table="${section.key}"]`)) {
    const fieldKey = el.getAttribute('data-replace-input');
    const field = section.composer.find(item => item.key === fieldKey);
    if (!field) continue;
    draft[fieldKey] = field.kind === 'checkbox' ? !!el.checked : el.value;
  }
  replacement.entry = draft;
  try {
    replacement.items.push(section.build(applyAmountUnit(section, draft)));
    replacement.entry = {};
    ui.saveError = null;
  } catch (err) {
    ui.saveError = err.message || 'Could not validate the replacement entry.';
  }
  renderProfile();
}

function handleReplaceRemove(ui, section, dataset) {
  const replacement = replacementDraft(section.key);
  if (!replacement) return;
  replacement.items = replacement.items.filter(item => item.id !== dataset.replaceId);
  renderProfile();
}

async function handleReplaceApply(ui, section) {
  const replacement = replacementDraft(section.key);
  if (!replacement) return;
  const saved = await replaceProfileSection(section.key, replacement.items);
  if (saved) REPLACEMENT_DRAFTS.delete(section.key);
}

function captureLinkedState(ui) {
  const keys = [
    'household_members',
    'income_items',
    'expense_items',
    'debt_items',
    'physical_assets',
    'insurance_policies',
    'benefit_items',
  ];
  return Object.fromEntries(keys.map(key => [
    key,
    (ui.profile?.[key] || []).map(item => ({ ...item })),
  ]));
}

function restoreLinkedState(ui, snapshot) {
  for (const [key, items] of Object.entries(snapshot || {})) {
    ui.profile[key] = items.map(item => ({ ...item }));
  }
}

function unlinkReferences(ui, removedSection, removedId) {
  const clear = (sectionKey, field) => {
    ui.profile[sectionKey] = (ui.profile?.[sectionKey] || []).map(item => (
      item[field] === removedId ? { ...item, [field]: null } : item
    ));
  };
  if (removedSection === 'physical_assets') {
    clear('debt_items', 'linked_asset_id');
    clear('expense_items', 'linked_asset_id');
    clear('income_items', 'linked_asset_id');
    clear('insurance_policies', 'linked_asset_id');
  } else if (removedSection === 'debt_items') {
    clear('expense_items', 'linked_debt_id');
  } else if (removedSection === 'expense_items') {
    clear('insurance_policies', 'premium_expense_id');
  } else if (removedSection === 'household_members') {
    clear('income_items', 'owner_member_id');
    clear('expense_items', 'related_member_id');
    clear('physical_assets', 'owner_member_id');
    clear('insurance_policies', 'insured_member_id');
    clear('benefit_items', 'owner_member_id');
  }
}

/* ─────────────  Drafts  ───────────── */

function composerDraft(key) {
  if (!COMPOSER_DRAFTS.has(key)) COMPOSER_DRAFTS.set(key, {});
  return COMPOSER_DRAFTS.get(key);
}

/* ─────────────  Section definitions  ───────────── */

function defineHousehold() {
  const currentYear = new Date().getFullYear();
  const section = {
    key: 'household_members',
    title: 'Household',
    singular: 'member',
    eyebrow: 'Foundation · Household',
    lede: 'Who the plan is for. Birth years drive retirement timing, catch-up contributions, RMDs, Medicare, and education goals.',
    emptyHint: 'No household members yet. Add yourself first — then a partner and any dependents.',
    primary: ['display_name', 'relationship', 'birth_year'],
    columns: [
      { key: 'display_name',   header: 'Name' },
      { key: 'relationship',   header: 'Relationship', format: humanWord },
      { key: 'birth_year',     header: 'Born',         numeric: true, format: v => (v ? String(v) : '—') },
      { key: 'retirement_age', header: 'Retire at',    numeric: true, format: v => (v ? String(v) : '—') },
      { key: 'dependent',      header: 'Dependent',    format: boolWord },
      { key: 'notes',          header: 'Notes' },
    ],
    composer: [
      { key: 'display_name',   kind: 'text',   label: 'Name',        placeholder: 'e.g. Brady' },
      { key: 'relationship',   kind: 'select', label: 'Relationship', options: [
        { value: 'self',      label: 'Self' },
        { value: 'partner',   label: 'Partner / spouse' },
        { value: 'child',     label: 'Child' },
        { value: 'dependent', label: 'Other dependent' },
        { value: 'other',     label: 'Other' },
      ] },
      { key: 'birth_year',     kind: 'number', label: 'Birth year',  min: 1900, max: currentYear, step: 1, placeholder: 'e.g. 1988', hint: 'An estimate is fine. Leave blank for now and retirement timing stays directional.' },
      { key: 'retirement_age', kind: 'number', label: 'Retire at',   min: 18, max: 100, step: 1, placeholder: 'adults only' },
      { key: 'notes',          kind: 'text',   label: 'Notes',       placeholder: 'optional' },
    ],
    build(draft) {
      const name = String(draft.display_name || '').trim();
      if (!name) throw new Error('A name is required.');
      const relationship = String(draft.relationship || 'self');
      const birthYear = Number(draft.birth_year);
      const retirementAge = Number(draft.retirement_age);
      return {
        id: uid(),
        display_name: name,
        relationship,
        birth_year: Number.isFinite(birthYear) && birthYear >= 1900 ? Math.round(birthYear) : null,
        retirement_age: Number.isFinite(retirementAge) && retirementAge >= 18 ? Math.round(retirementAge) : null,
        dependent: relationship === 'child' || relationship === 'dependent',
        notes: String(draft.notes || '').trim(),
      };
    },
    onAction: () => {},
    onAdd: () => {},
  };
  bindActions(section);
  return section;
}

function defineIncome() {
  const section = {
    key: 'income_items',
    title: 'Income',
    singular: 'income',
    eyebrow: 'Foundation · Income',
    lede: 'Recurring income that BuildWealth uses to model surplus, savings rate, and tax-aware planning. A rough monthly or annual estimate is enough to start.',
    emptyHint: 'No income entries yet. Add the streams BuildWealth should plan around.',
    primary: ['label', 'monthly_amount_usd'],
    columns: [
      { key: 'label',                header: 'Item' },
      { key: 'monthly_amount_usd',   header: 'Monthly',     numeric: true, format: fmtUsdOrDash },
      { key: 'source_type',          header: 'Type',        format: humanWord },
      { key: 'variability',          header: 'Pattern',     format: humanWord },
      { key: 'is_pre_tax',           header: 'Pre-tax',     format: boolWord },
      { key: 'annual_growth_rate',   header: 'Growth',      numeric: true, format: fmtPctOrDash },
      { key: 'start_date',           header: 'Start',       format: dateSafe },
      { key: 'end_date',             header: 'End',         format: dateSafe },
    ],
    composer: [
      { key: 'label',              kind: 'text',     label: 'Label',         placeholder: 'Salary, side income…' },
      { key: 'monthly_amount_usd', kind: 'number',   label: 'Monthly USD',   min: 0, step: 1, placeholder: '0' },
      { key: 'source_type',        kind: 'select',   label: 'Type',          options: [
        { value: 'salary',   label: 'Salary' },
        { value: 'bonus',    label: 'Bonus' },
        { value: 'business', label: 'Business' },
        { value: 'rental',   label: 'Rental' },
        { value: 'other',    label: 'Other' },
      ] },
      { key: 'owner_member_id',    kind: 'select',   label: 'Household member', options: ui => memberOptions(ui) },
      { key: 'linked_asset_id',    kind: 'select',   label: 'Related rental property', options: ui => assetOptions(ui) },
      { key: 'employer_name',      kind: 'text',     label: 'Employer / source', placeholder: 'optional' },
      { key: 'variability',        kind: 'select',   label: 'Pattern', options: [
        { value: 'fixed', label: 'Steady' },
        { value: 'variable', label: 'Variable' },
        { value: 'seasonal', label: 'Seasonal' },
      ] },
      { key: 'is_pre_tax',         kind: 'checkbox', label: 'Gross / before tax (usual for salary)' },
      { key: 'annual_growth_rate', kind: 'number',   label: 'Growth %/yr',   step: 0.01, placeholder: 'optional', ratio: true },
      { key: 'start_date',         kind: 'date',     label: 'Start' },
      { key: 'end_date',           kind: 'date',     label: 'End' },
    ],
    build(draft) {
      const label = String(draft.label || '').trim();
      if (!label) throw new Error('Income label is required.');
      const amount = Number(draft.monthly_amount_usd);
      if (!Number.isFinite(amount) || amount < 0) throw new Error('Monthly amount must be 0 or greater.');
      return {
        id: uid(),
        label,
        monthly_amount_usd: amount,
        source_type: draft.source_type || 'salary',
        owner_member_id: draft.owner_member_id || null,
        linked_asset_id: draft.linked_asset_id || null,
        employer_name: String(draft.employer_name || '').trim() || null,
        variability: draft.variability || 'fixed',
        is_pre_tax: draft.is_pre_tax == null ? true : !!draft.is_pre_tax,
        annual_growth_rate: parseRatio(draft.annual_growth_rate),
        start_date: draft.start_date || null,
        end_date: draft.end_date || null,
      };
    },
    onAction: () => {},
    onAdd: () => {},
  };
  bindActions(section);
  return section;
}

function defineExpenses() {
  const section = {
    key: 'expense_items',
    title: 'Expenses',
    singular: 'expense',
    eyebrow: 'Foundation · Expenses',
    lede: 'Monthly outflows that drive runway, savings rate, and inflation-aware projections. Start with a rough total or your largest recurring bills.',
    emptyHint: 'No expenses yet. Add the recurring obligations BuildWealth should plan around.',
    primary: ['label', 'monthly_amount_usd'],
    columns: [
      { key: 'label',              header: 'Item' },
      { key: 'monthly_amount_usd', header: 'Monthly',  numeric: true, format: fmtUsdOrDash },
      { key: 'category',           header: 'Category', format: humanWord },
      { key: 'linked_asset_id',    header: 'Related property', format: (value, _, ui) => relatedLabel(ui, 'physical_assets', value) },
      { key: 'is_fixed',           header: 'Fixed',    format: boolWord },
      { key: 'is_essential',       header: 'Essential',format: boolWord },
      { key: 'inflation_rate',     header: 'Inflation',numeric: true, format: fmtPctOrDash },
      { key: 'start_date',         header: 'Start',    format: dateSafe },
      { key: 'end_date',           header: 'End',      format: dateSafe },
    ],
    composer: [
      { key: 'label',              kind: 'text',     label: 'Label',       placeholder: 'Rent, groceries…' },
      { key: 'monthly_amount_usd', kind: 'number',   label: 'Monthly USD', min: 0, step: 1, placeholder: '0' },
      { key: 'category',           kind: 'select',   label: 'Category', options: [
        { value: 'general', label: 'General' },
        { value: 'housing', label: 'Housing' },
        { value: 'food', label: 'Food' },
        { value: 'transportation', label: 'Transportation' },
        { value: 'insurance', label: 'Insurance premium' },
        { value: 'fuel', label: 'Fuel' },
        { value: 'maintenance', label: 'Maintenance' },
        { value: 'registration_tax', label: 'Registration / property tax' },
        { value: 'hoa', label: 'HOA' },
        { value: 'storage', label: 'Storage' },
        { value: 'lease_payment', label: 'Lease payment' },
        { value: 'childcare', label: 'Childcare' },
        { value: 'education', label: 'Education' },
        { value: 'support', label: 'Support obligation' },
        { value: 'medical', label: 'Medical / care' },
        { value: 'elder_care', label: 'Elder care' },
      ] },
      { key: 'linked_asset_id',    kind: 'select',   label: 'Related property / vehicle', options: ui => assetOptions(ui) },
      { key: 'linked_debt_id',     kind: 'select',   label: 'Already counted debt payment', options: ui => debtOptions(ui), hint: 'Link only when this row describes a payment already counted in Debt.' },
      { key: 'related_member_id',  kind: 'select',   label: 'Related household member', options: ui => memberOptions(ui) },
      { key: 'is_fixed',           kind: 'checkbox', label: 'Fixed' },
      { key: 'is_essential',       kind: 'checkbox', label: 'Required expense' },
      { key: 'inflation_rate',     kind: 'number',   label: 'Inflation %/yr', step: 0.01, placeholder: 'optional', ratio: true },
      { key: 'start_date',         kind: 'date',     label: 'Start' },
      { key: 'end_date',           kind: 'date',     label: 'End' },
    ],
    build(draft) {
      const label = String(draft.label || '').trim();
      if (!label) throw new Error('Expense label is required.');
      const amount = Number(draft.monthly_amount_usd);
      if (!Number.isFinite(amount) || amount < 0) throw new Error('Monthly amount must be 0 or greater.');
      return {
        id: uid(),
        label,
        monthly_amount_usd: amount,
        category: draft.category || 'general',
        linked_asset_id: draft.linked_asset_id || null,
        linked_debt_id: draft.linked_debt_id || null,
        related_member_id: draft.related_member_id || null,
        is_fixed: !!draft.is_fixed,
        is_essential: !!draft.is_essential,
        inflation_rate: parseRatio(draft.inflation_rate),
        start_date: draft.start_date || null,
        end_date: draft.end_date || null,
      };
    },
    onAction: () => {},
    onAdd: () => {},
  };
  bindActions(section);
  return section;
}

function defineDebt() {
  const section = {
    key: 'debt_items',
    title: 'Debt',
    singular: 'debt',
    eyebrow: 'Foundation · Debt',
    lede: 'Outstanding balances. Strategy here informs pay-down recommendations and tax-aware ordering.',
    emptyHint: 'No debt tracked. If this is correct, mark "I currently have no debt" under Taxes & status.',
    primary: ['label', 'balance_usd'],
    columns: [
      { key: 'label',                  header: 'Debt' },
      { key: 'debt_type',              header: 'Type',        format: humanWord },
      { key: 'balance_usd',            header: 'Balance',     numeric: true, format: fmtUsdOrDash },
      { key: 'interest_rate',          header: 'Rate',        numeric: true, format: fmtPctOrDash },
      { key: 'minimum_payment_usd',    header: 'Min payment', numeric: true, format: fmtUsdOrDash },
      { key: 'payoff_strategy',        header: 'Strategy',    format: humanWord },
      { key: 'custom_monthly_payment_usd', header: 'Custom',  numeric: true, format: fmtUsdOrDash },
    ],
    composer: [
      { key: 'label',                      kind: 'text',   label: 'Debt label',    placeholder: 'Credit card, student loan…' },
      { key: 'balance_usd',                kind: 'number', label: 'Balance USD',   min: 0, step: 1, placeholder: '0' },
      { key: 'debt_type',                  kind: 'select', label: 'Debt type', options: [
        { value: 'mortgage', label: 'Mortgage' },
        { value: 'auto_loan', label: 'Auto loan' },
        { value: 'recreational_vehicle_loan', label: 'Boat / RV / recreational loan' },
        { value: 'student_loan', label: 'Student loan' },
        { value: 'credit_card', label: 'Credit card' },
        { value: 'personal_loan', label: 'Personal loan' },
        { value: 'heloc', label: 'HELOC' },
        { value: 'other', label: 'Other' },
      ] },
      { key: 'linked_asset_id',             kind: 'select', label: 'Secured by property / vehicle', options: ui => assetOptions(ui) },
      { key: 'original_principal_usd',      kind: 'number', label: 'Original principal', min: 0, step: 1, placeholder: 'optional' },
      { key: 'term_months',                 kind: 'number', label: 'Original term (months)', min: 1, max: 1200, step: 1, placeholder: 'optional' },
      { key: 'opened_at',                   kind: 'date',   label: 'Opened' },
      { key: 'maturity_date',               kind: 'date',   label: 'Matures' },
      { key: 'interest_rate',              kind: 'number', label: 'APR %',         min: 0, step: 0.01, placeholder: '0', ratio: true },
      { key: 'minimum_payment_usd',        kind: 'number', label: 'Min payment',   min: 0, step: 1, placeholder: '0' },
      { key: 'payoff_strategy',            kind: 'select', label: 'Strategy',      options: [
        { value: 'minimum',   label: 'Minimum' },
        { value: 'snowball',  label: 'Snowball' },
        { value: 'avalanche', label: 'Avalanche' },
        { value: 'custom',    label: 'Custom' },
      ] },
      { key: 'custom_monthly_payment_usd', kind: 'number', label: 'Custom payment', min: 0, step: 1, placeholder: 'optional' },
    ],
    build(draft) {
      const label = String(draft.label || '').trim();
      if (!label) throw new Error('Debt label is required.');
      const balance = Number(draft.balance_usd);
      if (!Number.isFinite(balance) || balance < 0) throw new Error('Balance must be 0 or greater.');
      return {
        id: uid(),
        label,
        balance_usd: balance,
        debt_type: draft.debt_type || 'other',
        linked_asset_id: draft.linked_asset_id || null,
        original_principal_usd: numOr(draft.original_principal_usd, null),
        term_months: integerOr(draft.term_months, null),
        opened_at: draft.opened_at || null,
        maturity_date: draft.maturity_date || null,
        interest_rate: parseRatio(draft.interest_rate),
        minimum_payment_usd: numOr(draft.minimum_payment_usd, 0),
        payoff_strategy: draft.payoff_strategy || 'minimum',
        custom_monthly_payment_usd: numOr(draft.custom_monthly_payment_usd, null),
      };
    },
    onAction: () => {},
    onAdd: () => {},
  };
  bindActions(section);
  return section;
}

function defineGoals() {
  const section = {
    key: 'goal_items',
    title: 'Goals',
    singular: 'goal',
    eyebrow: 'Foundation · Goals',
    lede: 'What you are saving toward. Goals drive plan trajectory and prioritization.',
    emptyHint: 'No goals tracked yet. Adding goals lets BuildWealth pace your saving.',
    primary: ['label', 'target_amount_usd', 'target_date'],
    columns: [
      { key: 'label',             header: 'Goal' },
      { key: 'target_amount_usd', header: 'Target',  numeric: true, format: fmtUsdOrDash },
      { key: 'target_date',       header: 'By',      format: dateSafe },
      { key: 'priority',          header: 'Priority',format: humanWord },
    ],
    composer: [
      { key: 'label',             kind: 'text',   label: 'Goal label',  placeholder: 'House, college fund…' },
      { key: 'target_amount_usd', kind: 'number', label: 'Target USD',  min: 0, step: 1, placeholder: '0' },
      { key: 'target_date',       kind: 'date',   label: 'Target date', hint: 'Not sure yet? Leave it blank; the forecast will stay directional.' },
      { key: 'priority',          kind: 'select', label: 'Priority',    options: [
        { value: 'high',   label: 'High' },
        { value: 'medium', label: 'Medium' },
        { value: 'low',    label: 'Low' },
      ] },
    ],
    build(draft) {
      const label = String(draft.label || '').trim();
      if (!label) throw new Error('Goal label is required.');
      const target = Number(draft.target_amount_usd);
      if (!Number.isFinite(target) || target < 0) throw new Error('Target amount must be 0 or greater.');
      return {
        id: uid(),
        label,
        target_amount_usd: target,
        target_date: draft.target_date || null,
        priority: draft.priority || 'medium',
      };
    },
    onAction: () => {},
    onAdd: () => {},
  };
  bindActions(section);
  return section;
}

function defineAssets() {
  const section = {
    key: 'physical_assets',
    title: 'Property & vehicles',
    singular: 'asset',
    eyebrow: 'Foundation · Assets',
    lede: 'Homes, cars, boats, trailers, UTVs, and other property. Value belongs in net worth; only assets you explicitly make available can fund a plan.',
    emptyHint: 'No property or vehicles tracked. Liquid investments belong in Portfolio.',
    primary: ['label', 'current_value_usd', 'asset_subtype'],
    columns: [
      { key: 'label',              header: 'Asset' },
      { key: 'current_value_usd',  header: 'Value',   numeric: true, format: fmtUsdOrDash },
      { key: 'asset_subtype',      header: 'Type',    format: humanWord },
      { key: 'valuation_date',     header: 'Valued',  format: dateSafe },
      { key: 'annual_growth_rate', header: 'Expected change', numeric: true, format: fmtPctOrDash },
      { key: 'include_in_plan_funding', header: 'Plan funding', format: boolWord },
    ],
    composer: [
      { key: 'label',              kind: 'text',   label: 'Asset label',   placeholder: 'House, car…' },
      { key: 'current_value_usd',  kind: 'number', label: 'Current value', min: 0, step: 1, placeholder: '0' },
      { key: 'asset_subtype',      kind: 'select', label: 'Specific kind', options: [
        { value: 'home', label: 'Home' },
        { value: 'rental_property', label: 'Rental property' },
        { value: 'land', label: 'Land' },
        { value: 'car', label: 'Car' },
        { value: 'truck', label: 'Truck' },
        { value: 'motorcycle', label: 'Motorcycle' },
        { value: 'rv', label: 'RV' },
        { value: 'boat', label: 'Boat' },
        { value: 'trailer', label: 'Trailer' },
        { value: 'utv_atv', label: 'UTV / ATV' },
        { value: 'machinery', label: 'Machinery / equipment' },
        { value: 'jewelry', label: 'Jewelry' },
        { value: 'collectible', label: 'Collectible' },
        { value: 'other', label: 'Other' },
      ] },
      { key: 'owner_member_id',    kind: 'select', label: 'Owner', options: ui => memberOptions(ui) },
      { key: 'acquisition_cost_usd', kind: 'number', label: 'Purchase cost', min: 0, step: 1, placeholder: 'optional' },
      { key: 'valuation_date',     kind: 'date',   label: 'Valuation date' },
      { key: 'valuation_source',   kind: 'select', label: 'Valuation source', options: [
        { value: 'user_estimate', label: 'My estimate' },
        { value: 'statement', label: 'Statement / appraisal' },
        { value: 'market_guide', label: 'Market guide' },
        { value: 'import', label: 'Imported' },
      ] },
      { key: 'liquidity',          kind: 'select', label: 'How sellable is it?', options: [
        { value: 'liquid', label: 'Readily sellable' },
        { value: 'sellable', label: 'Sellable with time' },
        { value: 'illiquid', label: 'Illiquid / not practical to sell' },
      ] },
      { key: 'include_in_plan_funding', kind: 'checkbox', label: 'Make proceeds available to fund the plan' },
      { key: 'disposition_intent', kind: 'select', label: 'Intent', options: [
        { value: 'keep', label: 'Keep' },
        { value: 'sell', label: 'Sell' },
        { value: 'replace', label: 'Replace' },
        { value: 'undecided', label: 'Undecided' },
      ] },
      { key: 'planned_disposition_date', kind: 'date', label: 'Planned sale / replacement' },
      { key: 'ownership_pct',      kind: 'number', label: 'Household ownership %', min: 0, max: 100, step: 0.01, placeholder: '100' },
      { key: 'annual_growth_rate', kind: 'number', label: 'Expected value change %/yr', step: 0.01, placeholder: 'Use a negative number for depreciation', ratio: true },
      { key: 'purchase_date',      kind: 'date',   label: 'Purchase date' },
    ],
    build(draft) {
      const label = String(draft.label || '').trim();
      if (!label) throw new Error('Asset label is required.');
      const value = Number(draft.current_value_usd);
      if (!Number.isFinite(value) || value < 0) throw new Error('Asset value must be 0 or greater.');
      return {
        id: uid(),
        label,
        current_value_usd: value,
        asset_type: assetTypeForSubtype(draft.asset_subtype || 'other'),
        asset_subtype: draft.asset_subtype || 'other',
        owner_member_id: draft.owner_member_id || null,
        acquisition_cost_usd: numOr(draft.acquisition_cost_usd, null),
        valuation_date: draft.valuation_date || null,
        valuation_source: draft.valuation_source || 'user_estimate',
        liquidity: draft.liquidity || 'sellable',
        include_in_plan_funding: !!draft.include_in_plan_funding,
        disposition_intent: draft.disposition_intent || 'keep',
        planned_disposition_date: draft.planned_disposition_date || null,
        ownership_pct: numOr(draft.ownership_pct, 100),
        annual_growth_rate: parseRatio(draft.annual_growth_rate),
        purchase_date: draft.purchase_date || null,
      };
    },
    onAction: () => {},
    onAdd: () => {},
  };
  bindActions(section);
  return section;
}

function defineInsurance() {
  const section = {
    key: 'insurance_policies',
    title: 'Insurance',
    singular: 'policy',
    eyebrow: 'Protection · Coverage',
    lede: 'Coverage that protects the household and its property. Link the premium to an Expense instead of entering the payment twice.',
    emptyHint: 'No insurance coverage tracked yet. Start with life, disability, umbrella, home or renters, auto, and health.',
    primary: ['label', 'coverage_type', 'coverage_amount_usd'],
    columns: [
      { key: 'label', header: 'Policy' },
      { key: 'coverage_type', header: 'Coverage', format: humanWord },
      { key: 'coverage_amount_usd', header: 'Limit', numeric: true, format: fmtUsdOrDash },
      { key: 'deductible_usd', header: 'Deductible', numeric: true, format: fmtUsdOrDash },
      { key: 'renewal_date', header: 'Renews', format: dateSafe },
      { key: 'beneficiary_reviewed', header: 'Beneficiaries', format: value => value ? 'Reviewed' : 'Not reviewed' },
    ],
    composer: [
      { key: 'label', kind: 'text', label: 'Policy label', placeholder: 'Term life, auto policy…' },
      { key: 'coverage_type', kind: 'select', label: 'Coverage type', options: [
        { value: 'life', label: 'Life' },
        { value: 'disability', label: 'Disability' },
        { value: 'umbrella', label: 'Umbrella' },
        { value: 'home', label: 'Home' },
        { value: 'renters', label: 'Renters' },
        { value: 'auto', label: 'Auto' },
        { value: 'health', label: 'Health' },
        { value: 'long_term_care', label: 'Long-term care' },
        { value: 'other', label: 'Other' },
      ] },
      { key: 'coverage_amount_usd', kind: 'number', label: 'Coverage amount', min: 0, step: 1, placeholder: 'optional' },
      { key: 'insured_member_id', kind: 'select', label: 'Insured household member', options: ui => memberOptions(ui) },
      { key: 'linked_asset_id', kind: 'select', label: 'Covered property / vehicle', options: ui => assetOptions(ui) },
      { key: 'premium_expense_id', kind: 'select', label: 'Premium expense', options: ui => expenseOptions(ui), hint: 'The linked Expense owns the monthly cash-flow amount.' },
      { key: 'deductible_usd', kind: 'number', label: 'Deductible', min: 0, step: 1, placeholder: 'optional' },
      { key: 'renewal_date', kind: 'date', label: 'Renewal date' },
      { key: 'beneficiary_reviewed', kind: 'checkbox', label: 'Beneficiaries reviewed' },
      { key: 'notes', kind: 'text', label: 'Notes', placeholder: 'Coverage gaps or follow-up' },
    ],
    build(draft) {
      const label = String(draft.label || '').trim();
      if (!label) throw new Error('Policy label is required.');
      return {
        id: uid(),
        label,
        coverage_type: draft.coverage_type || 'other',
        insured_member_id: draft.insured_member_id || null,
        linked_asset_id: draft.linked_asset_id || null,
        premium_expense_id: draft.premium_expense_id || null,
        coverage_amount_usd: numOr(draft.coverage_amount_usd, null),
        deductible_usd: numOr(draft.deductible_usd, null),
        renewal_date: draft.renewal_date || null,
        beneficiary_reviewed: !!draft.beneficiary_reviewed,
        notes: String(draft.notes || '').trim(),
      };
    },
    onAction: () => {},
    onAdd: () => {},
  };
  bindActions(section);
  return section;
}

function defineBenefits() {
  const section = {
    key: 'benefit_items',
    title: 'Benefits',
    singular: 'benefit',
    eyebrow: 'Foundation · Compensation & benefits',
    lede: 'Employer benefits, retirement matches, pensions, equity compensation, and expected public benefits that shape the plan without pretending they are cash today.',
    emptyHint: 'No benefits tracked yet. Add an employer match, pension, equity compensation, or other material benefit.',
    primary: ['label', 'benefit_type', 'owner_member_id'],
    columns: [
      { key: 'label', header: 'Benefit' },
      { key: 'benefit_type', header: 'Type', format: humanWord },
      { key: 'owner_member_id', header: 'For', format: (value, _, ui) => relatedLabel(ui, 'household_members', value) },
      { key: 'estimated_annual_value_usd', header: 'Est. annual value', numeric: true, format: fmtUsdOrDash },
      { key: 'employer_match_pct', header: 'Match', numeric: true, format: value => value == null ? '—' : `${Number(value).toFixed(2)}%` },
      { key: 'vesting_date', header: 'Vests', format: dateSafe },
    ],
    composer: [
      { key: 'label', kind: 'text', label: 'Benefit label', placeholder: '401(k) match, pension…' },
      { key: 'benefit_type', kind: 'select', label: 'Benefit type', options: [
        { value: 'retirement_match', label: 'Retirement match' },
        { value: 'pension', label: 'Pension' },
        { value: 'equity_compensation', label: 'Equity compensation' },
        { value: 'social_security', label: 'Social Security estimate' },
        { value: 'health', label: 'Health benefit' },
        { value: 'disability', label: 'Disability benefit' },
        { value: 'hsa', label: 'HSA contribution' },
        { value: 'other', label: 'Other' },
      ] },
      { key: 'owner_member_id', kind: 'select', label: 'Household member', options: ui => memberOptions(ui) },
      { key: 'employer_name', kind: 'text', label: 'Employer / provider', placeholder: 'optional' },
      { key: 'estimated_annual_value_usd', kind: 'number', label: 'Estimated annual value', min: 0, step: 1, placeholder: 'optional' },
      { key: 'employee_contribution_pct', kind: 'number', label: 'Employee contribution %', min: 0, max: 100, step: 0.01, placeholder: 'optional' },
      { key: 'employer_match_pct', kind: 'number', label: 'Employer match %', min: 0, max: 100, step: 0.01, placeholder: 'optional' },
      { key: 'vesting_date', kind: 'date', label: 'Vesting date' },
      { key: 'start_date', kind: 'date', label: 'Benefit starts' },
      { key: 'notes', kind: 'text', label: 'Notes', placeholder: 'Vesting terms or assumptions' },
    ],
    build(draft) {
      const label = String(draft.label || '').trim();
      if (!label) throw new Error('Benefit label is required.');
      return {
        id: uid(),
        label,
        benefit_type: draft.benefit_type || 'other',
        owner_member_id: draft.owner_member_id || null,
        employer_name: String(draft.employer_name || '').trim() || null,
        estimated_annual_value_usd: numOr(draft.estimated_annual_value_usd, null),
        employee_contribution_pct: numOr(draft.employee_contribution_pct, null),
        employer_match_pct: numOr(draft.employer_match_pct, null),
        vesting_date: draft.vesting_date || null,
        start_date: draft.start_date || null,
        notes: String(draft.notes || '').trim(),
      };
    },
    onAction: () => {},
    onAdd: () => {},
  };
  bindActions(section);
  return section;
}

// Avoids an early-binding circular reference in defineIncome (which had to
// inline its `bound()` call before the others got refactored). All five
// sections route through bindActions for a single source of truth.
function bindActions(section) {
  section.onAction = (ui, action, dataset) => {
    if (action === 'remove')      return handleRemove(ui, section, dataset);
    if (action === 'edit')        return startRowEdit(ui, section, dataset.rowId);
    if (action === 'edit-save')   return saveRowEdit(ui, section);
    if (action === 'edit-cancel') return cancelRowEdit();
    if (action === 'amount-unit') return handleAmountUnit(dataset);
    if (action === 'replace-open') return handleReplaceOpen(ui, section);
    if (action === 'replace-cancel') return handleReplaceCancel(ui, section);
    if (action === 'replace-add') return handleReplaceAdd(ui, section);
    if (action === 'replace-remove') return handleReplaceRemove(ui, section, dataset);
    if (action === 'replace-apply') return handleReplaceApply(ui, section);
  };
  section.onAdd = (ui, root) => handleAdd(ui, section, root);
}

/* ─────────────  Helpers  ───────────── */

function uid() {
  if (typeof crypto !== 'undefined' && typeof crypto.randomUUID === 'function') return crypto.randomUUID();
  return `id-${Math.random().toString(36).slice(2)}-${Date.now().toString(36)}`;
}

function numOr(value, fallback) {
  // Empty inputs mean "not provided" — Number('') is 0, which would silently
  // turn an optional blank field into a real $0 on edit round-trips.
  if (value === '' || value == null) return fallback;
  const n = Number(value);
  return Number.isFinite(n) ? n : fallback;
}

function integerOr(value, fallback) {
  const number = numOr(value, fallback);
  return Number.isFinite(number) ? Math.round(number) : fallback;
}

function memberOptions(ui) {
  return relatedOptions(ui, 'household_members', 'No household member');
}

function assetOptions(ui) {
  return relatedOptions(ui, 'physical_assets', 'No linked property');
}

function debtOptions(ui) {
  return relatedOptions(ui, 'debt_items', 'Not already counted in Debt');
}

function expenseOptions(ui) {
  return relatedOptions(ui, 'expense_items', 'No linked premium expense');
}

function relatedOptions(ui, sectionKey, blankLabel) {
  const items = ui?.profile?.[sectionKey] || [];
  return [
    { value: '', label: blankLabel },
    ...items.map(item => ({
      value: item.id || '',
      label: item.label || item.display_name || 'Untitled',
    })),
  ];
}

function relatedLabel(ui, sectionKey, id) {
  if (!id) return '—';
  const item = (ui?.profile?.[sectionKey] || []).find(candidate => candidate.id === id);
  return item?.label || item?.display_name || 'Missing link';
}

function assetTypeForSubtype(subtype) {
  if (['home', 'rental_property', 'land'].includes(subtype)) return 'real_estate';
  if (['car', 'truck', 'motorcycle', 'rv', 'boat', 'trailer', 'utv_atv'].includes(subtype)) return 'vehicle';
  if (subtype === 'machinery') return 'equipment';
  if (subtype === 'jewelry') return 'jewelry';
  if (subtype === 'collectible') return 'collectible';
  return 'other';
}

function parseRatio(value) {
  if (value === '' || value == null) return null;
  const n = Number(value);
  if (!Number.isFinite(n)) return null;
  // Stored profile rates use decimal fractions (0.05 == 5%). The composer
  // takes percent input; convert here.
  return n / 100;
}

function dateSafe(value) {
  if (!value) return '—';
  const d = new Date(value);
  if (Number.isNaN(d.getTime())) return String(value);
  return d.toLocaleDateString();
}

function boolWord(value) {
  return value ? 'Yes' : 'No';
}

function humanWord(value) {
  if (!value) return '—';
  return String(value).replace(/_/g, ' ');
}
