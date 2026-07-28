// Profile · Editable tables.
// Income / Expenses / Debt / Goals / Physical assets.
// Each section is a declarative spec: columns, the row composer, and the
// row-builder + row-validator used when the user taps "Add". Removal,
// addition, and form drafting all flow through `persist()` so the server
// stays the source of truth and onboarding refreshes automatically.

import { html, raw, esc } from '../../lib/dom.js';
import { fmtUsdOrDash, fmtPctOrDash, unwrapDisplayValue } from '../../lib/format.js';
import { showUndoToast } from '../../lib/undo.js';
import { persist, render as renderProfile } from '../profile.js';
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

const SECTIONS_BY_KEY = new Map();

export const TABLE_SECTIONS = [
  defineHousehold(),
  defineIncome(),
  defineExpenses(),
  defineDebt(),
  defineGoals(),
  defineAssets(),
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
        </div>
      </header>

      ${raw(renderComposer(section))}
      ${raw(renderRows(section, items))}
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

function renderRows(section, items) {
  if (!items.length) {
    return html`
      <div class="empty-block">
        <span class="glyph">¶</span>
        <p>${section.emptyHint}</p>
      </div>
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
        ? col.format(item[col.key], item)
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

function renderComposer(section) {
  const draft = composerDraft(section.key);
  const { primary, more } = composerFieldSplit(section);
  const primaryFields = (primary.length ? primary : section.composer).map(f => fieldHtml(section.key, f, draft)).join('');
  const moreFields = primary.length ? more.map(f => fieldHtml(section.key, f, draft)).join('') : '';
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

function fieldHtml(key, field, draft) {
  const value = draft[field.key] ?? (
    key === 'income_items' && field.key === 'is_pre_tax' ? true : ''
  );
  const id = `composer-${key}-${field.key}`;
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
                 data-composer-input="${esc(field.key)}"
                 data-composer-table="${esc(key)}"
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
    const options = field.options.map(o => `<option value="${esc(o.value)}" ${o.value === value ? 'selected' : ''}>${esc(o.label)}</option>`).join('');
    return `
      <label class="settings-field">
        <span class="settings-label">${esc(field.label)}</span>
        <select class="settings-input" id="${id}" data-composer-input="${esc(field.key)}" data-composer-table="${esc(key)}">
          ${options}
        </select>
      </label>
    `;
  }
  if (field.kind === 'checkbox') {
    return `
      <label class="settings-field settings-field-toggle">
        <input type="checkbox" id="${id}" data-composer-input="${esc(field.key)}" data-composer-table="${esc(key)}" ${value ? 'checked' : ''} />
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
             data-composer-input="${esc(field.key)}"
             data-composer-table="${esc(key)}"
             ${field.placeholder ? `placeholder="${esc(field.placeholder)}"` : ''}
             ${field.min != null ? `min="${esc(field.min)}"` : ''}
             ${field.max != null ? `max="${esc(field.max)}"` : ''}
             ${field.step != null ? `step="${esc(field.step)}"` : ''}
             value="${esc(value)}" />
      ${field.hint ? `<small class="settings-hint">${esc(field.hint)}</small>` : ''}
    </label>
  `;
}

/* ─────────────  Actions  ───────────── */

async function handleRemove(ui, section, dataset) {
  const id = dataset.rowId;
  if (!id) return;
  const items = ui.profile?.[section.key] || [];
  const removed = items.find(item => item.id === id);
  if (!removed) return;
  const prior = items.slice();
  ui.profile[section.key] = items.filter(item => item.id !== id);
  if (section.key === 'expense_items') {
    ui.profile.flags = { ...(ui.profile.flags || {}), expenses_complete: false };
  }
  await persist();
  const label = removed.label || removed.display_name || `this ${section.singular}`;
  showUndoToast({
    message: `Removed ${label}`,
    onUndo: async () => {
      ui.profile[section.key] = prior;
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
  ui.profile[section.key].push(row);
  if (section.key === 'expense_items') {
    ui.profile.flags = { ...(ui.profile.flags || {}), expenses_complete: false };
  }
  COMPOSER_DRAFTS.set(section.key, {});
  await persist();
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
      { key: 'category',           header: 'Category' },
      { key: 'is_fixed',           header: 'Fixed',    format: boolWord },
      { key: 'inflation_rate',     header: 'Inflation',numeric: true, format: fmtPctOrDash },
      { key: 'start_date',         header: 'Start',    format: dateSafe },
      { key: 'end_date',           header: 'End',      format: dateSafe },
    ],
    composer: [
      { key: 'label',              kind: 'text',     label: 'Label',       placeholder: 'Rent, groceries…' },
      { key: 'monthly_amount_usd', kind: 'number',   label: 'Monthly USD', min: 0, step: 1, placeholder: '0' },
      { key: 'category',           kind: 'text',     label: 'Category',    placeholder: 'housing, food, …' },
      { key: 'is_fixed',           kind: 'checkbox', label: 'Fixed' },
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
        is_fixed: !!draft.is_fixed,
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
      { key: 'balance_usd',            header: 'Balance',     numeric: true, format: fmtUsdOrDash },
      { key: 'interest_rate',          header: 'Rate',        numeric: true, format: fmtPctOrDash },
      { key: 'minimum_payment_usd',    header: 'Min payment', numeric: true, format: fmtUsdOrDash },
      { key: 'payoff_strategy',        header: 'Strategy',    format: humanWord },
      { key: 'custom_monthly_payment_usd', header: 'Custom',  numeric: true, format: fmtUsdOrDash },
    ],
    composer: [
      { key: 'label',                      kind: 'text',   label: 'Debt label',    placeholder: 'Credit card, student loan…' },
      { key: 'balance_usd',                kind: 'number', label: 'Balance USD',   min: 0, step: 1, placeholder: '0' },
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
    title: 'Physical assets',
    singular: 'asset',
    eyebrow: 'Foundation · Assets',
    lede: 'Real estate, vehicles, and other non-portfolio holdings that affect net worth and runway.',
    emptyHint: 'No physical assets tracked. Liquid investments belong in Portfolio.',
    primary: ['label', 'current_value_usd'],
    columns: [
      { key: 'label',              header: 'Asset' },
      { key: 'current_value_usd',  header: 'Value',   numeric: true, format: fmtUsdOrDash },
      { key: 'asset_type',         header: 'Type',    format: humanWord },
      { key: 'annual_growth_rate', header: 'Growth',  numeric: true, format: fmtPctOrDash },
      { key: 'purchase_date',      header: 'Bought',  format: dateSafe },
    ],
    composer: [
      { key: 'label',              kind: 'text',   label: 'Asset label',   placeholder: 'House, car…' },
      { key: 'current_value_usd',  kind: 'number', label: 'Current value', min: 0, step: 1, placeholder: '0' },
      { key: 'asset_type',         kind: 'select', label: 'Type',          options: [
        { value: 'real_estate', label: 'Real estate' },
        { value: 'vehicle',     label: 'Vehicle' },
        { value: 'jewelry',     label: 'Jewelry' },
        { value: 'equipment',   label: 'Equipment' },
        { value: 'collectible', label: 'Collectible' },
        { value: 'other',       label: 'Other' },
      ] },
      { key: 'annual_growth_rate', kind: 'number', label: 'Growth %/yr',   step: 0.01, placeholder: 'optional', ratio: true },
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
        asset_type: draft.asset_type || 'other',
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
