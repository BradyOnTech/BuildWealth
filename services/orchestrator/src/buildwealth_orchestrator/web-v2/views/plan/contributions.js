// Movement IIE - Contribution rules.
// Dense v2 view over account priority, targets, and contribution posture.

import { html, raw, esc } from '../../lib/dom.js';
import { fmtUsd } from '../../lib/format.js';

export const CONTRIBUTION_EDIT_FIELDS = [
  {
    key: 'base_rule_type',
    label: 'Base rule',
    type: 'select',
    options: [
      ['save', 'Save'],
      ['spend', 'Spend'],
    ],
  },
  { key: 'employer_match_target_usd', label: 'Employer match target', type: 'money' },
  { key: 'age', label: 'Planning age', type: 'integer' },
  { key: 'profile_id', label: 'Profile id', type: 'text' },
];

export function buildContributionRulesPayload(contributionRules = {}, draft = {}) {
  const normalized = normalizeContributionRules(contributionRules);
  const payload = {
    schema_version: Number(normalized.schema_version || 2),
    base_rule: { ...normalized.base_rule },
    profile_id: normalized.profile_id,
    employer_match_target_usd: normalized.employer_match_target_usd,
    age: normalized.age,
    rules: normalized.rules,
  };

  if (Object.prototype.hasOwnProperty.call(draft, 'base_rule_type')) {
    payload.base_rule = {
      ...payload.base_rule,
      type: clean(draft.base_rule_type) || 'save',
    };
  }
  if (Object.prototype.hasOwnProperty.call(draft, 'employer_match_target_usd')) {
    payload.employer_match_target_usd = parseNumberOrNull(draft.employer_match_target_usd, false);
  }
  if (Object.prototype.hasOwnProperty.call(draft, 'age')) {
    payload.age = parseNumberOrNull(draft.age, true);
  }
  if (Object.prototype.hasOwnProperty.call(draft, 'profile_id')) {
    payload.profile_id = clean(draft.profile_id) || null;
  }
  return payload;
}

export function renderContributions(plan = {}, state = {}) {
  const contributionRules = normalizeContributionRules(state.contributionRules);
  const draft = objectValue(state.draft);
  const editing = Boolean(state.editing);
  const sortedRules = contributionRules.rules.slice().sort((left, right) => ruleRank(left) - ruleRank(right));

  return html`
    <section class="plan-contributions" data-plan-section="contributions">
      <header class="section-head compact">
        <span class="section-eyebrow">Contributions</span>
        <h2 class="section-title">Contribution rules</h2>
        <p class="section-lede">Review the account priorities and annual targets that drive contribution advice.</p>
      </header>

      ${state.error ? html`<p class="error-banner">${esc(state.error)}</p>` : ''}

      <div class="structure-summary">
        ${raw(summaryItem('Base rule', titleText(contributionRules.base_rule.type || 'save')))}
        ${raw(summaryItem('Employer match', fmtUsd(contributionRules.employer_match_target_usd)))}
        ${raw(summaryItem('Age', contributionRules.age == null ? 'Unset' : String(contributionRules.age)))}
        ${raw(summaryItem('Profile', contributionRules.profile_id || 'Default'))}
      </div>

      ${editing ? html`
        <div class="structure-form" data-form="plan-contribution-rules">
          ${raw(CONTRIBUTION_EDIT_FIELDS.map(field => renderContributionField(field, contributionRules, draft)).join(''))}
        </div>
        <div class="structure-actions">
          <button class="btn btn-primary" data-contribution-action="save" ${state.saving ? 'disabled' : ''}>
            ${state.saving ? 'Saving...' : 'Save contributions'}
          </button>
          <button class="btn btn-ghost" data-contribution-action="cancel" ${state.saving ? 'disabled' : ''}>Cancel</button>
          ${state.dirty ? html`<span class="marginalia">Contribution edits are staged.</span>` : html`<span class="marginalia">Adjust rule posture without changing account rows.</span>`}
        </div>
      ` : html`
        <div class="structure-actions">
          <button class="action-link" data-contribution-action="edit">Edit contribution rules <span class="arrow">&rsaquo;</span></button>
          ${state.busy ? html`<span class="marginalia">Loading contribution rules...</span>` : ''}
        </div>
      `}

      <div class="structure-table">
        <div class="structure-table-head">
          <span>Priority</span>
          <span>Account</span>
          <span>Target</span>
          <span>Match</span>
        </div>
        ${sortedRules.length ? raw(sortedRules.map(renderRuleRow).join('')) : html`
          <p class="marginalia">No contribution rows saved yet.</p>
        `}
      </div>
    </section>
  `;
}

function renderContributionField(field, contributionRules, draft) {
  const value = draftValue(field, contributionRules, draft);
  const current = currentFieldDisplay(field, contributionRules);
  return html`
    <label class="structure-field">
      <span class="assumption-label">${esc(field.label)}</span>
      ${field.type === 'select' ? renderSelect(field, value) : renderInput(field, value)}
      <span class="assumption-current">Current ${esc(current)}</span>
    </label>
  `;
}

function renderInput(field, value) {
  return html`
    <input
      data-contribution-field="${esc(field.key)}"
      type="${field.type === 'text' ? 'text' : 'number'}"
      step="${field.type === 'integer' ? '1' : '100'}"
      inputmode="${field.type === 'text' ? 'text' : 'decimal'}"
      value="${esc(value)}"
    />
  `;
}

function renderSelect(field, value) {
  return html`
    <select data-contribution-field="${esc(field.key)}">
      ${(field.options || []).map(([optionValue, label]) => html`
        <option value="${esc(optionValue)}" ${String(optionValue) === String(value) ? 'selected' : ''}>${esc(label)}</option>
      `)}
    </select>
  `;
}

function renderRuleRow(rule = {}) {
  const rank = ruleRank(rule);
  const account = clean(rule.accountId || rule.account_id || rule.account || rule.id) || 'Unassigned';
  const target = ruleTarget(rule);
  const match = rule.employerMatch ?? rule.employer_match_usd ?? rule.match_target_usd;
  return html`
    <article class="structure-table-row">
      <span>${rank === Number.POSITIVE_INFINITY ? '-' : esc(rank)}</span>
      <strong>${esc(account)}</strong>
      <span>${esc(fmtUsd(target))}</span>
      <span>${esc(fmtUsd(match))}</span>
    </article>
  `;
}

function summaryItem(label, value) {
  return html`
    <div class="structure-summary-item">
      <dt>${esc(label)}</dt>
      <dd>${esc(value || 'Unset')}</dd>
    </div>
  `;
}

function draftValue(field, contributionRules, draft = {}) {
  if (Object.prototype.hasOwnProperty.call(draft, field.key)) return clean(draft[field.key]);
  if (field.key === 'base_rule_type') return clean(contributionRules.base_rule.type) || 'save';
  const value = contributionRules[field.key];
  return value == null ? '' : String(value);
}

function currentFieldDisplay(field, contributionRules) {
  if (field.key === 'base_rule_type') return titleText(contributionRules.base_rule.type || 'save');
  const value = contributionRules[field.key];
  if (value == null || value === '') return 'Unset';
  if (field.type === 'money') return fmtUsd(value);
  return String(value);
}

function ruleRank(rule = {}) {
  const value = Number(rule.rank ?? rule.priority ?? rule.order);
  return Number.isFinite(value) ? value : Number.POSITIVE_INFINITY;
}

function ruleTarget(rule = {}) {
  const direct = rule.annual_target_usd ?? rule.target_usd ?? rule.limit_usd;
  if (direct != null) return direct;
  const amount = rule.amount && typeof rule.amount === 'object' ? rule.amount : {};
  return amount.dollarAmount ?? amount.dollar_amount ?? amount.annual_target_usd ?? null;
}

function parseNumberOrNull(rawValue, integer = false) {
  const text = clean(rawValue);
  if (!text) return null;
  const number = Number(text);
  if (!Number.isFinite(number)) return null;
  return integer ? Math.round(number) : number;
}

function normalizeContributionRules(contributionRules = {}) {
  const source = contributionRules && typeof contributionRules === 'object' ? contributionRules : {};
  const baseRule = source.base_rule && typeof source.base_rule === 'object' ? source.base_rule : { type: 'save' };
  return {
    schema_version: Number(source.schema_version || 2),
    base_rule: { ...baseRule, type: clean(baseRule.type) || 'save' },
    profile_id: source.profile_id ?? null,
    employer_match_target_usd: source.employer_match_target_usd ?? null,
    age: source.age ?? null,
    rules: Array.isArray(source.rules) ? source.rules.filter(rule => rule && typeof rule === 'object') : [],
  };
}

function objectValue(value) {
  return value && typeof value === 'object' ? value : {};
}

function clean(value) {
  return String(value ?? '').trim();
}

function titleText(value) {
  return clean(value)
    .replace(/[_-]+/g, ' ')
    .replace(/\b\w/g, char => char.toUpperCase());
}
