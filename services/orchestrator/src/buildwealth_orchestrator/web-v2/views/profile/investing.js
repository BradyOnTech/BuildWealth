// Profile · Investing tab.
// Plain-language guardrails: most users don't know what an "investment policy"
// is, but they know how comfortable they are with one stock owning their
// portfolio, or how much cash they want before taking more risk. Each row
// pairs a friendly label with the technical field that drives recommendations.

import { html, raw, esc } from '../../lib/dom.js';
import { persist, render as renderProfile } from '../profile.js';

const RISK_OPTIONS = [
  { value: '',             label: 'Not set' },
  { value: 'conservative', label: 'Conservative — protect what I have' },
  { value: 'moderate',     label: 'Moderate — accept volatility for long-term growth' },
  { value: 'aggressive',   label: 'Aggressive — go for growth, expect drawdowns' },
];

const SENSITIVITY_OPTIONS = [
  { value: '',       label: 'Not set' },
  { value: 'low',    label: 'Low — taxes are not a major concern yet' },
  { value: 'medium', label: 'Medium — be reasonable about taxable sales' },
  { value: 'high',   label: 'High — avoid taxable surprises whenever possible' },
];

const SIMPLICITY_OPTIONS = [
  { value: '',       label: 'Not set' },
  { value: 'low',    label: 'Low — comfortable with many positions' },
  { value: 'medium', label: 'Medium — balance simplicity and optimization' },
  { value: 'high',   label: 'High — prefer few funds, low maintenance' },
];

let pendingSave = false;
let lastSaveError = null;

export function renderInvesting(ui) {
  const policy = ui.profile?.investment_policy || {};
  return html`
    <div class="profile-investing">
      <header class="profile-table-head">
        <div>
          <p class="profile-table-eyebrow">§ Foundation · Investing</p>
          <h2 class="profile-table-title">Investment guardrails</h2>
          <p class="profile-table-lede">
            BuildWealth uses these to shape recommendations and Copilot answers.
            Plain-language defaults work; the technical field name is the same
            one Copilot reads.
          </p>
        </div>
      </header>

      ${raw(guardrailsCard(policy))}
      ${raw(targetsCard(policy))}
      ${raw(restrictedCard(policy))}
      ${raw(handoffCard())}

      ${lastSaveError ? html`<p class="inline-warning">${lastSaveError}</p>` : ''}
      <div class="profile-composer-actions">
        <button class="btn btn-primary" type="button" data-investing-save ${pendingSave ? 'disabled' : ''}>
          ${pendingSave ? 'Saving…' : 'Save guardrails'}
        </button>
      </div>
    </div>
  `;
}

/* ─────────────  Target mix card  ───────────── */

const TARGET_CLASSES = [
  ['equity', 'Stocks & stock funds'],
  ['fixed_income', 'Bonds & bond funds'],
  ['real_estate', 'Real estate'],
  ['cash', 'Cash'],
];

export function targetsCard(policy) {
  const targets = policy?.target_asset_class_allocation_pct || {};
  const total = TARGET_CLASSES.reduce((sum, [key]) => sum + (Number(targets[key]) || 0), 0);
  return html`
    <article class="profile-card">
      <header class="profile-card-head">
        <h3 class="profile-card-title">Target mix</h3>
        <p class="profile-table-lede">
          Where you want the portfolio to sit. When reality drifts more than five
          points from a target, BuildWealth suggests where the next contribution
          should go — guidance only, it never trades.
        </p>
      </header>
      <div class="profile-guardrails">
        ${raw(TARGET_CLASSES.map(([key, label]) => html`
          <label class="scenario-field">
            <span class="assumption-label">${label}</span>
            <input
              data-investing-target-class="${key}"
              type="number" step="1" min="0" max="100" inputmode="numeric"
              value="${targets[key] != null ? Number(targets[key]) : ''}"
              placeholder="—"
            />
            <span class="assumption-current">% of portfolio</span>
          </label>
        `.toString()).join(''))}
      </div>
      ${total > 0 && Math.round(total) !== 100 ? html`
        <p class="marginalia">Targets add to ${Math.round(total)}% — that's allowed, but 100% reads cleanest.</p>
      ` : ''}
    </article>
  `;
}

/* ─────────────  Guardrails card  ───────────── */

function guardrailsCard(policy) {
  return html`
    <article class="profile-card">
      <header class="profile-card-head">
        <h3 class="profile-card-title">Plain-language guardrails</h3>
      </header>
      <div class="profile-guardrails">
        ${raw(numberRow({
          id: 'inv-single-symbol',
          field: 'max_single_symbol_exposure_pct',
          plain: 'Single-investment limit',
          why: 'The most of your portfolio BuildWealth should be comfortable seeing in one stock or fund.',
          unit: '%', step: '1', min: '0', max: '100',
          value: policy.max_single_symbol_exposure_pct,
          placeholder: 'e.g. 10',
        }))}

        ${raw(numberRow({
          id: 'inv-sector',
          field: 'max_sector_exposure_pct',
          plain: 'Single-sector limit',
          why: 'How much of the portfolio can sit in one sector before BuildWealth flags concentration.',
          unit: '%', step: '1', min: '0', max: '100',
          value: policy.max_sector_exposure_pct,
          placeholder: 'e.g. 30',
        }))}

        ${raw(numberRow({
          id: 'inv-cash',
          field: 'minimum_cash_runway_months',
          plain: 'Minimum cash cushion',
          why: 'Months of expenses you want available before taking on more investment risk.',
          unit: 'months', step: '1', min: '0',
          value: policy.minimum_cash_runway_months,
          placeholder: 'e.g. 6',
        }))}

        ${raw(selectRow({
          id: 'inv-risk',
          field: 'risk_tolerance',
          plain: 'Risk comfort',
          why: 'How much volatility you are willing to accept.',
          options: RISK_OPTIONS,
          value: policy.risk_tolerance,
        }))}

        ${raw(selectRow({
          id: 'inv-tax',
          field: 'tax_sensitivity',
          plain: 'Tax sensitivity',
          why: 'How careful BuildWealth should be about taxable sales or tax-heavy investments.',
          options: SENSITIVITY_OPTIONS,
          value: policy.tax_sensitivity,
        }))}

        ${raw(selectRow({
          id: 'inv-simplicity',
          field: 'simplicity_preference',
          plain: 'Simplicity preference',
          why: 'Whether to prefer fewer holdings and easier maintenance over fine-grained optimization.',
          options: SIMPLICITY_OPTIONS,
          value: policy.simplicity_preference,
        }))}

        ${raw(selectRow({
          id: 'inv-research',
          field: 'minimum_research_confidence',
          plain: 'Required research confidence',
          why: 'How much evidence BuildWealth should require before recommending a position.',
          options: SIMPLICITY_OPTIONS.map(o => o.value === '' ? o : { ...o, label: o.label.replace(/—.*$/, '').trim() + (o.value === 'low' ? ' — broad evidence is enough' : o.value === 'medium' ? ' — balanced evidence' : ' — only strong evidence') }),
          value: policy.minimum_research_confidence,
        }))}
      </div>
    </article>
  `;
}

function numberRow({ id, field, plain, why, unit, step, min, max, value, placeholder }) {
  return html`
    <label class="profile-guardrail" for="${id}">
      <div class="profile-guardrail-text">
        <span class="profile-guardrail-label">${plain}</span>
        <span class="profile-guardrail-why">${why}</span>
      </div>
      <div class="profile-guardrail-input">
        <input class="settings-input mono" id="${id}" type="number"
               data-investing-field="${field}"
               step="${step}" ${min != null ? `min="${min}"` : ''} ${max != null ? `max="${max}"` : ''}
               placeholder="${esc(placeholder || '')}"
               value="${value == null || value === '' ? '' : esc(String(value))}" />
        <span class="profile-guardrail-unit">${unit}</span>
      </div>
    </label>
  `;
}

function selectRow({ id, field, plain, why, options, value }) {
  return html`
    <label class="profile-guardrail" for="${id}">
      <div class="profile-guardrail-text">
        <span class="profile-guardrail-label">${plain}</span>
        <span class="profile-guardrail-why">${why}</span>
      </div>
      <div class="profile-guardrail-input">
        <select class="settings-input" id="${id}" data-investing-field="${field}">
          ${raw(options.map(o => `<option value="${esc(o.value)}" ${o.value === (value || '') ? 'selected' : ''}>${esc(o.label)}</option>`).join(''))}
        </select>
      </div>
    </label>
  `;
}

/* ─────────────  Restricted symbols / sectors  ───────────── */

function restrictedCard(policy) {
  const symbols = Array.isArray(policy.restricted_symbols) ? policy.restricted_symbols : [];
  const sectors = Array.isArray(policy.restricted_sectors) ? policy.restricted_sectors : [];
  return html`
    <article class="profile-card">
      <header class="profile-card-head">
        <h3 class="profile-card-title">Restricted investments</h3>
      </header>
      <p class="profile-card-empty" style="margin: 0 0 var(--s-3);">
        Symbols or sectors BuildWealth should avoid suggesting. Useful for ESG preferences, employer restrictions, or long-running personal rules.
      </p>

      ${raw(chipList({
        kind: 'symbol',
        title: 'Symbols',
        items: symbols,
        placeholder: 'AAPL, XOM…',
        emptyHint: 'No symbols restricted.',
      }))}

      ${raw(chipList({
        kind: 'sector',
        title: 'Sectors',
        items: sectors,
        placeholder: 'tobacco, oil…',
        emptyHint: 'No sectors restricted.',
      }))}
    </article>
  `;
}

function chipList({ kind, title, items, placeholder, emptyHint }) {
  return html`
    <section class="profile-chips-block">
      <header class="profile-chips-head">
        <span class="profile-chips-title">${title}</span>
        <span class="profile-chips-count">${items.length}</span>
      </header>
      <div class="profile-chips">
        ${items.length
          ? raw(items.map(value => `
            <span class="profile-chip">
              <span class="profile-chip-label">${esc(value)}</span>
              <button class="profile-chip-remove" type="button"
                      data-investing-remove="${esc(kind)}"
                      data-value="${esc(value)}"
                      aria-label="Remove ${esc(value)}">×</button>
            </span>
          `).join(''))
          : html`<span class="profile-chips-empty">${emptyHint}</span>`}
      </div>
      <div class="profile-chips-add">
        <input class="settings-input mono" type="text"
               id="profile-chip-input-${kind}"
               data-investing-add-input="${kind}"
               placeholder="${esc(placeholder)}" />
        <button class="btn btn-quiet" type="button" data-investing-add="${kind}">Add</button>
      </div>
    </section>
  `;
}

/* ─────────────  Copilot handoff  ───────────── */

function handoffCard() {
  return html`
    <aside class="settings-handoff">
      <p class="settings-handoff-eyebrow">Not sure what to set?</p>
      <p class="settings-handoff-body">
        <a class="link-editorial" href="#copilot?intent=investment-policy" data-route>Ask Copilot to help me choose</a> —
        Copilot can draft values from your goals, runway, and tax picture and propose them for review. You decide whether to apply.
      </p>
    </aside>
  `;
}

/* ─────────────  Submit  ───────────── */

export async function submitInvestingForm(ui) {
  if (pendingSave) return;
  const root = document.getElementById('profile-page');
  if (!root) return;

  const policy = { ...(ui.profile.investment_policy || {}) };
  // Pull every numeric / select control. Empty strings clear the field.
  for (const el of root.querySelectorAll('[data-investing-field]')) {
    const field = el.getAttribute('data-investing-field');
    if (el.tagName === 'SELECT') {
      policy[field] = el.value === '' ? null : el.value;
    } else {
      const v = el.value;
      if (v === '' || v == null) {
        policy[field] = null;
      } else {
        const n = Number(v);
        policy[field] = Number.isFinite(n) ? n : null;
      }
    }
  }
  if (!Array.isArray(policy.restricted_symbols)) policy.restricted_symbols = [];
  if (!Array.isArray(policy.restricted_sectors)) policy.restricted_sectors = [];

  // Target mix inputs are a dict field; collect them separately.
  const targets = {};
  for (const el of root.querySelectorAll('[data-investing-target-class]')) {
    const klass = el.getAttribute('data-investing-target-class');
    const pct = Number(el.value);
    if (el.value !== '' && Number.isFinite(pct) && pct > 0 && pct <= 100) targets[klass] = pct;
  }
  policy.target_asset_class_allocation_pct = targets;

  ui.profile.investment_policy = policy;
  pendingSave = true;
  lastSaveError = null;
  renderProfile();
  try {
    await persist();
  } catch (err) {
    lastSaveError = err?.message || 'Could not save guardrails.';
  } finally {
    pendingSave = false;
    renderProfile();
  }
}

export function addRestricted(ui, kind) {
  const root = document.getElementById('profile-page');
  if (!root) return;
  const input = root.querySelector(`[data-investing-add-input="${kind}"]`);
  if (!input) return;
  const value = String(input.value || '').trim().toUpperCase();
  if (!value) return;
  const key = kind === 'symbol' ? 'restricted_symbols' : 'restricted_sectors';
  const policy = ui.profile.investment_policy = ui.profile.investment_policy || {};
  if (!Array.isArray(policy[key])) policy[key] = [];
  if (!policy[key].includes(value)) policy[key].push(value);
  input.value = '';
  // Persist immediately — chips feel weird if a Save button has to be hit too.
  saveSilently(ui);
}

export function removeRestricted(ui, kind, value) {
  const key = kind === 'symbol' ? 'restricted_symbols' : 'restricted_sectors';
  const policy = ui.profile.investment_policy || {};
  if (!Array.isArray(policy[key])) return;
  policy[key] = policy[key].filter(v => v !== value);
  ui.profile.investment_policy = policy;
  saveSilently(ui);
}

async function saveSilently(ui) {
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
