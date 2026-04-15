import { fetchJson } from '../lib/api.js';
import { state } from '../lib/state.js';
import {
  PLAN_SETTING_VALUE_FIELDS,
  DIFF_SETTING_VALUE_FIELDS,
  HOUSEHOLD_MODE_OPTIONS,
  FILING_STATUS_OPTIONS,
  SIMULATION_MODE_OPTIONS,
  SIMULATION_MONTE_CARLO_VARIANT_OPTIONS,
} from '../lib/plan_setting_fields.js';
import { byId, fmtCurrency, fmtDate, writeLog } from '../lib/utils.js';
import { collectPlanSettingsPayload, setPlanSettingsInputs } from '../lib/components.js';

const PROJECTION_SOURCE_OPTIONS = [
  { value: 'diff_base', label: 'Scenario Diff - Base' },
  { value: 'diff_candidate', label: 'Scenario Diff - Candidate' },
  { value: 'branch_base', label: 'Scenario Branch - Base' },
  { value: 'branch_branch', label: 'Scenario Branch - Branch' },
];
const DEFAULT_WITHDRAWAL_STRATEGIES = ['cashflow_only', 'four_percent_rule', 'dynamic_guardrails', 'bond_tent', 'bucket_strategy'];

const ACCOUNT_TYPE_COLORS = {
  brokerage: '#2f6e47',
  cash: '#486f8f',
  checking: '#3a6f88',
  hsa: '#886a2d',
  '403b': '#9a4f39',
  '401k': '#6d5f8f',
  '457b': '#6e4f8f',
  ira: '#5a7d3a',
  roth_ira: '#4b7f64',
  roth_401k: '#4f6f90',
  traditional_ira: '#8b6c37',
  traditional_401k: '#7e4d4d',
  taxable: '#32608e',
  tax_free: '#4f8a66',
  tax_deferred: '#8a6b31',
};

const FALLBACK_ACCOUNT_TYPE_COLORS = ['#2f6e47', '#3e6f96', '#8a6018', '#7d4a4a', '#5f6f39', '#6d5f8f', '#4f7f7a', '#8a4f6a'];

const projectionState = {
  diffResult: null,
  branchResult: null,
  profilePayload: null,
  profileLoading: false,
};

const TIMELINE_EVENT_TYPES = new Set(['purchase', 'windfall', 'job_change', 'retirement', 'milestone']);
const TIMELINE_IMPACT_TYPES = new Set(['income', 'expense', 'portfolio', 'contribution', 'debt_payment']);
const TIMELINE_FREQUENCIES = new Set(['one_time', 'monthly', 'yearly']);
const HOUSEHOLD_MODES = new Set(HOUSEHOLD_MODE_OPTIONS.map(option => option.value));
const FILING_STATUSES = new Set(FILING_STATUS_OPTIONS.map(option => option.value));
const SIMULATION_MODES = new Set(SIMULATION_MODE_OPTIONS.map(option => option.value));
const SIMULATION_MONTE_CARLO_VARIANTS = new Set(SIMULATION_MONTE_CARLO_VARIANT_OPTIONS.map(option => option.value));
const TIMELINE_DEFAULT_IMPACT_BY_EVENT = {
  purchase: 'expense',
  windfall: 'income',
  job_change: 'income',
  retirement: 'contribution',
  milestone: 'portfolio',
};
const CONTRIBUTION_AMOUNT_TYPES = new Set(['dollarAmount', 'percentRemaining', 'unlimited']);

function makeEditorId(prefix) {
  return `${prefix}-${Math.random().toString(36).slice(2, 10)}`;
}

function coerceOptionalNumber(rawValue) {
  if (rawValue === null || rawValue === undefined) return null;
  const text = String(rawValue).trim();
  if (!text) return null;
  const value = Number(text);
  return Number.isFinite(value) ? value : null;
}

function coerceOptionalInteger(rawValue) {
  const value = coerceOptionalNumber(rawValue);
  if (value === null) return null;
  return Math.trunc(value);
}

function dateInputValue(rawValue) {
  const text = String(rawValue || '').trim();
  return text ? text.slice(0, 10) : '';
}

function parseObjectJsonFromEditor(elementId, label) {
  const raw = String(byId(elementId)?.value || '').trim();
  if (!raw) return {};
  let payload;
  try {
    payload = JSON.parse(raw);
  } catch (error) {
    throw new Error(`${label} JSON is invalid: ${error.message}`);
  }
  if (!payload || typeof payload !== 'object' || Array.isArray(payload)) {
    throw new Error(`${label} JSON must be an object.`);
  }
  return payload;
}

function normalizeTimelineEvent(rawEvent, index) {
  const event = rawEvent && typeof rawEvent === 'object' ? { ...rawEvent } : {};
  const eventTypeRaw = String(event.event_type || 'milestone').trim().toLowerCase();
  const eventType = TIMELINE_EVENT_TYPES.has(eventTypeRaw) ? eventTypeRaw : 'milestone';
  const impactTypeRaw = String(event.impact_type || '').trim().toLowerCase();
  const impactType = TIMELINE_IMPACT_TYPES.has(impactTypeRaw)
    ? impactTypeRaw
    : (TIMELINE_DEFAULT_IMPACT_BY_EVENT[eventType] || 'portfolio');
  const recurringFrequencyRaw = String(event.recurring_frequency || 'one_time').trim().toLowerCase();
  const recurringFrequency = TIMELINE_FREQUENCIES.has(recurringFrequencyRaw) ? recurringFrequencyRaw : 'one_time';
  const amountUsd = coerceOptionalNumber(event.amount_usd);

  return {
    id: String(event.id || '').trim() || `event-${index + 1}`,
    date: dateInputValue(event.date),
    label: String(event.label || '').trim(),
    event_type: eventType,
    impact_type: impactType,
    amount_usd: amountUsd === null ? 0 : amountUsd,
    recurring_frequency: recurringFrequency,
    end_date: dateInputValue(event.end_date) || null,
    account_id: String(event.account_id || '').trim() || null,
    notes: String(event.notes || '').trim(),
  };
}

function normalizeTimelinePayload(rawPayload) {
  const payload = rawPayload && typeof rawPayload === 'object' && !Array.isArray(rawPayload)
    ? { ...rawPayload }
    : {};
  const eventsRaw = Array.isArray(payload.events) ? payload.events : [];
  const retirementRaw = payload.retirement && typeof payload.retirement === 'object' && !Array.isArray(payload.retirement)
    ? payload.retirement
    : {};
  payload.events = eventsRaw.map((event, index) => normalizeTimelineEvent(event, index));
  payload.retirement = { ...retirementRaw };
  return payload;
}

function readTimelinePayloadFromEditor({ strict = false } = {}) {
  const raw = String(byId('plan-timeline')?.value || '').trim();
  if (!raw) return normalizeTimelinePayload({ events: [], retirement: {} });
  try {
    return normalizeTimelinePayload(JSON.parse(raw));
  } catch (error) {
    if (strict) throw new Error(`Timeline JSON is invalid: ${error.message}`);
    return normalizeTimelinePayload({ events: [], retirement: {} });
  }
}

function setTimelineRetirementInputs(retirementRaw) {
  const retirement = retirementRaw && typeof retirementRaw === 'object' ? retirementRaw : {};
  const setValue = (id, value) => {
    const input = byId(id);
    if (!input) return;
    input.value = value === null || value === undefined ? '' : String(value);
  };

  setValue('timeline-retirement-age', coerceOptionalInteger(retirement.target_retirement_age));
  setValue('timeline-withdrawal-strategy', String(retirement.withdrawal_strategy || '').trim());
  setValue('timeline-drawdown-order', String(retirement.drawdown_order || '').trim());
  setValue('timeline-ss-birth-year', coerceOptionalInteger(retirement.social_security_birth_year));
  setValue('timeline-ss-claiming-age', coerceOptionalInteger(retirement.social_security_claiming_age));
  setValue('timeline-ss-life-expectancy-age', coerceOptionalInteger(retirement.social_security_life_expectancy_age));
  setValue('timeline-ss-fra-benefit', coerceOptionalNumber(retirement.social_security_fra_monthly_benefit_usd));
  setValue('timeline-ss-annual-earnings', coerceOptionalNumber(retirement.social_security_estimated_annual_earnings_usd));
  setValue('timeline-rmd-birth-year', coerceOptionalInteger(retirement.rmd_birth_year));
  setValue('timeline-rmd-start-age', coerceOptionalInteger(retirement.rmd_start_age));
}

function collectTimelineRetirementInputs() {
  return {
    target_retirement_age: coerceOptionalInteger(byId('timeline-retirement-age')?.value),
    withdrawal_strategy: String(byId('timeline-withdrawal-strategy')?.value || '').trim() || null,
    drawdown_order: String(byId('timeline-drawdown-order')?.value || '').trim() || null,
    social_security_birth_year: coerceOptionalInteger(byId('timeline-ss-birth-year')?.value),
    social_security_claiming_age: coerceOptionalInteger(byId('timeline-ss-claiming-age')?.value),
    social_security_life_expectancy_age: coerceOptionalInteger(byId('timeline-ss-life-expectancy-age')?.value),
    social_security_fra_monthly_benefit_usd: coerceOptionalNumber(byId('timeline-ss-fra-benefit')?.value),
    social_security_estimated_annual_earnings_usd: coerceOptionalNumber(byId('timeline-ss-annual-earnings')?.value),
    rmd_birth_year: coerceOptionalInteger(byId('timeline-rmd-birth-year')?.value),
    rmd_start_age: coerceOptionalInteger(byId('timeline-rmd-start-age')?.value),
  };
}

function updateSimulationModeDependentControls(prefix, { clearIrrelevant = false } = {}) {
  const modeInput = byId(`${prefix}-simulation-mode`);
  if (!modeInput) return;

  const modeRaw = String(modeInput.value || '').trim().toLowerCase();
  const mode = SIMULATION_MODES.has(modeRaw) ? modeRaw : '';
  const variantInput = byId(`${prefix}-simulation-monte-carlo-variant`);
  const historicalStartYearInput = byId(`${prefix}-simulation-historical-start-year`);
  const seedInput = byId(`${prefix}-simulation-seed`);
  const controlsLocked = modeInput.disabled;

  let variantEnabled = true;
  let historicalStartYearEnabled = true;
  let seedEnabled = true;

  if (mode === 'fixed') {
    variantEnabled = false;
    historicalStartYearEnabled = false;
    seedEnabled = false;
  } else if (mode === 'stochastic') {
    variantEnabled = false;
    historicalStartYearEnabled = false;
    seedEnabled = true;
  } else if (mode === 'historical') {
    variantEnabled = false;
    historicalStartYearEnabled = true;
    seedEnabled = true;
  } else if (mode === 'monte_carlo') {
    variantEnabled = true;
    historicalStartYearEnabled = false;
    seedEnabled = true;
  }

  const syncControl = (input, enabled) => {
    if (!input) return;
    if (!controlsLocked) input.disabled = !enabled;
    if (!enabled && clearIrrelevant) input.value = '';
  };

  syncControl(variantInput, variantEnabled);
  syncControl(historicalStartYearInput, historicalStartYearEnabled);
  syncControl(seedInput, seedEnabled);
}

function renderTimelineEventsTable(payload) {
  const tbody = byId('plan-timeline-events-body');
  if (!tbody) return;
  const events = Array.isArray(payload?.events) ? payload.events : [];
  if (!events.length) {
    tbody.innerHTML = '<tr><td colspan="10">No timeline events yet.</td></tr>';
    return;
  }

  tbody.innerHTML = '';
  for (const event of events) {
    const tr = document.createElement('tr');
    tr.innerHTML = `
      <td>${dateInputValue(event.date) || '-'}</td>
      <td>${event.label || '-'}</td>
      <td>${event.event_type || '-'}</td>
      <td>${event.impact_type || '-'}</td>
      <td>${fmtCurrency(Number(event.amount_usd || 0))}</td>
      <td>${event.recurring_frequency || 'one_time'}</td>
      <td>${dateInputValue(event.end_date) || '-'}</td>
      <td><code>${event.account_id || '-'}</code></td>
      <td>${event.notes || '-'}</td>
      <td></td>`;
    const button = document.createElement('button');
    button.type = 'button';
    button.className = 'ghost small';
    button.textContent = 'Remove';
    button.addEventListener('click', () => {
      const current = readTimelinePayloadFromEditor();
      current.events = (current.events || []).filter(item => String(item.id || '') !== String(event.id || ''));
      writeTimelinePayloadToEditor(current);
    });
    tr.lastElementChild.appendChild(button);
    tbody.appendChild(tr);
  }
}

function writeTimelinePayloadToEditor(rawPayload, { preferFormValues = true } = {}) {
  const payload = normalizeTimelinePayload(rawPayload);
  payload.retirement = preferFormValues ? collectTimelineRetirementInputs() : (payload.retirement || {});
  byId('plan-timeline').value = JSON.stringify(payload, null, 2);
  setTimelineRetirementInputs(payload.retirement);
  renderTimelineEventsTable(payload);
}

function refreshTimelineBuilderFromEditor(silent = true) {
  try {
    const payload = readTimelinePayloadFromEditor({ strict: true });
    setTimelineRetirementInputs(payload.retirement);
    renderTimelineEventsTable(payload);
    return true;
  } catch (error) {
    if (!silent) writeLog(error.message, null, true);
    return false;
  }
}

function normalizeContributionRule(rawRule, index) {
  const rule = rawRule && typeof rawRule === 'object' ? { ...rawRule } : {};
  const amountRaw = rule.amount && typeof rule.amount === 'object' ? rule.amount : {};
  const amountTypeRaw = String(
    amountRaw.type || rule.amount_type || rule.contribution_type || 'unlimited',
  ).trim();
  const amountType = CONTRIBUTION_AMOUNT_TYPES.has(amountTypeRaw) ? amountTypeRaw : 'unlimited';
  const rank = coerceOptionalInteger(rule.rank);
  const amount = { type: amountType };
  if (amountType === 'dollarAmount') {
    amount.dollarAmount = Math.max(
      0,
      Number(coerceOptionalNumber(
        amountRaw.dollarAmount ?? rule.dollarAmount ?? rule.dollar_amount_usd,
      ) ?? 0),
    );
  } else if (amountType === 'percentRemaining') {
    amount.percentRemaining = Math.max(
      0,
      Math.min(
        100,
        Number(coerceOptionalNumber(
          amountRaw.percentRemaining ?? rule.percentRemaining ?? rule.percent_remaining,
        ) ?? 0),
      ),
    );
  }

  const normalized = {
    id: String(rule.id || rule.rule_id || '').trim() || `rule-${index + 1}`,
    accountId: String(rule.accountId || rule.account_id || '').trim(),
    rank: rank === null ? (index + 1) : Math.max(1, rank),
    amount,
  };

  const employerMatch = coerceOptionalNumber(rule.employerMatch ?? rule.employer_match_usd);
  const maxBalance = coerceOptionalNumber(rule.maxBalance ?? rule.max_balance_usd);
  if (employerMatch !== null) normalized.employerMatch = Math.max(0, employerMatch);
  if (maxBalance !== null) normalized.maxBalance = Math.max(0, maxBalance);
  if (rule.enableMegaBackdoorRoth || rule.enable_mega_backdoor_roth) normalized.enableMegaBackdoorRoth = true;
  if (rule.disabled) normalized.disabled = true;
  return normalized;
}

function normalizeContributionRulesPayload(rawPayload) {
  const payload = rawPayload && typeof rawPayload === 'object' && !Array.isArray(rawPayload)
    ? { ...rawPayload }
    : {};
  const baseTypeRaw = String(payload.base_rule?.type || 'save').trim().toLowerCase();
  payload.base_rule = { type: baseTypeRaw === 'spend' ? 'spend' : 'save' };
  payload.rules = (Array.isArray(payload.rules) ? payload.rules : []).map((rule, index) => normalizeContributionRule(rule, index));
  payload.profile_id = String(payload.profile_id || '').trim() || null;
  const employerMatchTarget = coerceOptionalNumber(payload.employer_match_target_usd);
  payload.employer_match_target_usd = employerMatchTarget === null ? 6000 : Math.max(0, employerMatchTarget);
  const age = coerceOptionalInteger(payload.age);
  payload.age = age === null ? 35 : Math.max(0, Math.min(120, age));
  payload.rules.sort((left, right) => left.rank - right.rank);
  return payload;
}

function readContributionRulesPayloadFromEditor({ strict = false } = {}) {
  const raw = String(byId('plan-contribution-rules')?.value || '').trim();
  if (!raw) return normalizeContributionRulesPayload({});
  try {
    return normalizeContributionRulesPayload(JSON.parse(raw));
  } catch (error) {
    if (strict) throw new Error(`Contribution rules JSON is invalid: ${error.message}`);
    return normalizeContributionRulesPayload({});
  }
}

function setContributionRuleMetaInputs(payloadRaw) {
  const payload = payloadRaw && typeof payloadRaw === 'object' ? payloadRaw : {};
  const baseRuleSelect = byId('contribution-base-rule');
  if (baseRuleSelect) baseRuleSelect.value = payload.base_rule?.type === 'spend' ? 'spend' : 'save';
  const profileInput = byId('contribution-profile-id');
  if (profileInput) profileInput.value = String(payload.profile_id || '').trim();
  const employerInput = byId('contribution-employer-match-target');
  if (employerInput) employerInput.value = coerceOptionalNumber(payload.employer_match_target_usd) === null ? '' : String(payload.employer_match_target_usd);
  const ageInput = byId('contribution-age');
  if (ageInput) ageInput.value = coerceOptionalInteger(payload.age) === null ? '' : String(Math.trunc(payload.age));
}

function collectContributionRuleMetaInputs() {
  return {
    base_rule: {
      type: String(byId('contribution-base-rule')?.value || 'save').trim().toLowerCase() === 'spend'
        ? 'spend'
        : 'save',
    },
    profile_id: String(byId('contribution-profile-id')?.value || '').trim() || null,
    employer_match_target_usd: coerceOptionalNumber(byId('contribution-employer-match-target')?.value),
    age: coerceOptionalInteger(byId('contribution-age')?.value),
  };
}

function formatContributionRuleAmount(rule) {
  const amount = rule?.amount && typeof rule.amount === 'object' ? rule.amount : {};
  const amountType = String(amount.type || 'unlimited');
  if (amountType === 'dollarAmount') return fmtCurrency(Number(amount.dollarAmount || 0));
  if (amountType === 'percentRemaining') return `${Number(amount.percentRemaining || 0).toFixed(2)}%`;
  return 'Unlimited';
}

function renderContributionRulesTable(payload) {
  const tbody = byId('plan-contribution-rules-body');
  if (!tbody) return;
  const rules = Array.isArray(payload?.rules) ? payload.rules : [];
  if (!rules.length) {
    tbody.innerHTML = '<tr><td colspan="9">No contribution rules yet.</td></tr>';
    return;
  }

  tbody.innerHTML = '';
  for (const rule of rules) {
    const tr = document.createElement('tr');
    tr.innerHTML = `
      <td>${Math.max(1, Math.trunc(Number(rule.rank || 1)))}</td>
      <td><code>${rule.accountId || '-'}</code></td>
      <td>${rule.amount?.type || 'unlimited'}</td>
      <td>${formatContributionRuleAmount(rule)}</td>
      <td>${rule.employerMatch !== undefined ? fmtCurrency(Number(rule.employerMatch || 0)) : '-'}</td>
      <td>${rule.maxBalance !== undefined ? fmtCurrency(Number(rule.maxBalance || 0)) : '-'}</td>
      <td>${rule.enableMegaBackdoorRoth ? 'Yes' : 'No'}</td>
      <td>${rule.disabled ? 'Yes' : 'No'}</td>
      <td></td>`;
    const button = document.createElement('button');
    button.type = 'button';
    button.className = 'ghost small';
    button.textContent = 'Remove';
    button.addEventListener('click', () => {
      const current = readContributionRulesPayloadFromEditor();
      current.rules = (current.rules || []).filter(item => String(item.id || '') !== String(rule.id || ''));
      writeContributionRulesPayloadToEditor(current);
    });
    tr.lastElementChild.appendChild(button);
    tbody.appendChild(tr);
  }
}

function writeContributionRulesPayloadToEditor(rawPayload, { preferFormValues = true } = {}) {
  const payload = normalizeContributionRulesPayload(rawPayload);
  const meta = preferFormValues ? collectContributionRuleMetaInputs() : {
    base_rule: payload.base_rule,
    profile_id: payload.profile_id,
    employer_match_target_usd: payload.employer_match_target_usd,
    age: payload.age,
  };
  payload.base_rule = meta.base_rule;
  payload.profile_id = meta.profile_id;
  payload.employer_match_target_usd = meta.employer_match_target_usd === null ? 6000 : Math.max(0, meta.employer_match_target_usd);
  payload.age = meta.age === null ? 35 : Math.max(0, Math.min(120, meta.age));
  payload.rules.sort((left, right) => left.rank - right.rank);
  byId('plan-contribution-rules').value = JSON.stringify(payload, null, 2);
  setContributionRuleMetaInputs(payload);
  renderContributionRulesTable(payload);
}

function refreshContributionBuilderFromEditor(silent = true) {
  try {
    const payload = readContributionRulesPayloadFromEditor({ strict: true });
    setContributionRuleMetaInputs(payload);
    renderContributionRulesTable(payload);
    return true;
  } catch (error) {
    if (!silent) writeLog(error.message, null, true);
    return false;
  }
}

function resetTimelineEventInputs() {
  const defaults = [
    ['timeline-event-date', ''],
    ['timeline-event-label', ''],
    ['timeline-event-type', 'milestone'],
    ['timeline-event-impact-type', ''],
    ['timeline-event-amount', ''],
    ['timeline-event-frequency', 'one_time'],
    ['timeline-event-end-date', ''],
    ['timeline-event-account-id', ''],
    ['timeline-event-notes', ''],
  ];
  for (const [id, value] of defaults) {
    const input = byId(id);
    if (!input) continue;
    input.value = value;
  }
}

function updateContributionRuleAmountField() {
  const amountType = String(byId('contribution-rule-amount-type')?.value || 'unlimited');
  const amountInput = byId('contribution-rule-amount-value');
  if (!amountInput) return;
  if (amountType === 'dollarAmount') {
    amountInput.placeholder = 'Dollar Amount';
    amountInput.disabled = false;
    return;
  }
  if (amountType === 'percentRemaining') {
    amountInput.placeholder = 'Percent Remaining';
    amountInput.disabled = false;
    return;
  }
  amountInput.placeholder = 'Not required';
  amountInput.value = '';
  amountInput.disabled = true;
}

function resetContributionRuleInputs() {
  const defaults = [
    ['contribution-rule-account-id', ''],
    ['contribution-rule-rank', ''],
    ['contribution-rule-amount-type', 'unlimited'],
    ['contribution-rule-amount-value', ''],
    ['contribution-rule-employer-match', ''],
    ['contribution-rule-max-balance', ''],
  ];
  for (const [id, value] of defaults) {
    const input = byId(id);
    if (!input) continue;
    input.value = value;
  }
  const megaCheckbox = byId('contribution-rule-mega-backdoor');
  if (megaCheckbox) megaCheckbox.checked = false;
  const disabledCheckbox = byId('contribution-rule-disabled');
  if (disabledCheckbox) disabledCheckbox.checked = false;
  updateContributionRuleAmountField();
}

function setControlsEnabled(enabled) {
  [
    'activate-plan', 'refresh-plan-context', 'open-plan-recommendations', 'generate-plan-closure-summary', 'refresh-plan-closure-trend', 'save-plan', 'save-plan-timeline', 'save-plan-assumption-sets',
    'save-plan-contribution-rules', 'save-plan-branch-templates', 'save-plan-settings', 'run-scenario-diff',
    'run-withdrawal-strategy-compare', 'apply-scenario-overrides', 'load-branch-template', 'run-scenario-branch',
    'pin-watchlist-branch-template', 'open-latest-research-bridge-artifact',
    'refresh-projection-profile', 'projection-source', 'projection-scenario-label', 'projection-account-metric',
    'add-decision', 'plan-markdown', 'plan-tasks', 'plan-timeline', 'plan-assumption-sets',
    'plan-contribution-rules', 'plan-branch-templates', 'diff-assumption-set-id',
    'diff-candidate-assumption-set-id', 'withdrawal-assumption-set-id', 'withdrawal-current-portfolio-value',
    'withdrawal-strategies', 'withdrawal-include-raw-results', 'branch-template-id', 'scenario-branch-name',
    'research-bridge-symbols',
    'branch-assumption-set-id', 'scenario-branch-events', 'decision-summary', 'decision-rationale',
    'decision-status', 'timeline-event-date', 'timeline-event-label', 'timeline-event-type',
    'timeline-event-impact-type', 'timeline-event-amount', 'timeline-event-frequency', 'timeline-event-end-date',
    'timeline-event-account-id', 'timeline-event-notes', 'add-timeline-event', 'timeline-retirement-age',
    'timeline-withdrawal-strategy', 'timeline-drawdown-order', 'timeline-ss-birth-year', 'timeline-ss-claiming-age',
    'timeline-ss-life-expectancy-age', 'timeline-ss-fra-benefit', 'timeline-ss-annual-earnings',
    'timeline-rmd-birth-year', 'timeline-rmd-start-age', 'contribution-base-rule', 'contribution-profile-id',
    'contribution-employer-match-target', 'contribution-age', 'contribution-rule-account-id',
    'contribution-rule-rank', 'contribution-rule-amount-type', 'contribution-rule-amount-value',
    'contribution-rule-employer-match', 'contribution-rule-max-balance', 'contribution-rule-mega-backdoor',
    'contribution-rule-disabled', 'add-contribution-rule',
  ].forEach((id) => {
    const el = byId(id);
    if (el) el.disabled = !enabled;
  });
  for (const f of [...PLAN_SETTING_VALUE_FIELDS, ...DIFF_SETTING_VALUE_FIELDS]) { const el = byId(f.inputId); if (el) el.disabled = !enabled; }
  if (enabled) {
    updateSimulationModeDependentControls('setting', { clearIrrelevant: false });
    updateSimulationModeDependentControls('diff', { clearIrrelevant: false });
  }
}

function parseAssumptionSets(rawPayload) {
  let payload = {};
  if (typeof rawPayload === 'string') {
    const text = rawPayload.trim();
    if (text) {
      try {
        payload = JSON.parse(text);
      } catch {
        payload = {};
      }
    }
  } else if (rawPayload && typeof rawPayload === 'object') {
    payload = rawPayload;
  }

  const rawSets = Array.isArray(payload.sets) ? payload.sets : [];
  const sets = [];
  const seen = new Set();
  for (const item of rawSets) {
    if (!item || typeof item !== 'object') continue;
    const id = String(item.id || '').trim();
    if (!id || seen.has(id)) continue;
    seen.add(id);
    sets.push({ id, name: String(item.name || id).trim() || id });
  }

  return {
    activeId: String(payload.active_assumption_set_id || '').trim(),
    sets,
  };
}

function setAssumptionSetOptions(rawPayload) {
  const baseSelect = byId('diff-assumption-set-id');
  const candidateSelect = byId('diff-candidate-assumption-set-id');
  const branchSelect = byId('branch-assumption-set-id');
  const withdrawalSelect = byId('withdrawal-assumption-set-id');
  if (!baseSelect || !candidateSelect || !branchSelect || !withdrawalSelect) return;

  const prevBase = String(baseSelect.value || '').trim();
  const prevCandidate = String(candidateSelect.value || '').trim();
  const prevBranch = String(branchSelect.value || '').trim();
  const prevWithdrawal = String(withdrawalSelect.value || '').trim();
  const parsed = parseAssumptionSets(rawPayload);

  baseSelect.innerHTML = '<option value="">Active plan set (default)</option>';
  candidateSelect.innerHTML = '<option value="">Same as base</option>';
  branchSelect.innerHTML = '<option value="">Active plan set (default)</option>';
  withdrawalSelect.innerHTML = '<option value="">Active plan set (default)</option>';
  for (const set of parsed.sets) {
    const baseOption = document.createElement('option');
    baseOption.value = set.id;
    baseOption.textContent = `${set.name} (${set.id})`;
    baseSelect.appendChild(baseOption);

    const candidateOption = document.createElement('option');
    candidateOption.value = set.id;
    candidateOption.textContent = `${set.name} (${set.id})`;
    candidateSelect.appendChild(candidateOption);

    const branchOption = document.createElement('option');
    branchOption.value = set.id;
    branchOption.textContent = `${set.name} (${set.id})`;
    branchSelect.appendChild(branchOption);

    const withdrawalOption = document.createElement('option');
    withdrawalOption.value = set.id;
    withdrawalOption.textContent = `${set.name} (${set.id})`;
    withdrawalSelect.appendChild(withdrawalOption);
  }

  const validIds = new Set(parsed.sets.map(s => s.id));
  const baseValue = validIds.has(prevBase) ? prevBase : (validIds.has(parsed.activeId) ? parsed.activeId : '');
  const candidateValue = validIds.has(prevCandidate) ? prevCandidate : '';
  const branchValue = validIds.has(prevBranch) ? prevBranch : '';
  const withdrawalValue = validIds.has(prevWithdrawal) ? prevWithdrawal : '';
  baseSelect.value = baseValue;
  candidateSelect.value = candidateValue;
  branchSelect.value = branchValue;
  withdrawalSelect.value = withdrawalValue;
}

function parseBranchTemplates(rawPayload) {
  let payload = {};
  if (typeof rawPayload === 'string') {
    const text = rawPayload.trim();
    if (text) {
      try {
        payload = JSON.parse(text);
      } catch {
        payload = {};
      }
    }
  } else if (rawPayload && typeof rawPayload === 'object') {
    payload = rawPayload;
  }

  const rawTemplates = Array.isArray(payload.templates) ? payload.templates : [];
  const templates = [];
  const seen = new Set();
  for (const item of rawTemplates) {
    if (!item || typeof item !== 'object') continue;
    const id = String(item.id || '').trim();
    if (!id || seen.has(id)) continue;
    seen.add(id);
    templates.push({
      id,
      name: String(item.name || id).trim() || id,
      description: String(item.description || '').trim(),
      branch_name: String(item.branch_name || '').trim(),
      assumption_set_id: String(item.assumption_set_id || '').trim(),
      compare_settings: item.compare_settings && typeof item.compare_settings === 'object' ? item.compare_settings : {},
      branch_events: Array.isArray(item.branch_events) ? item.branch_events : [],
    });
  }

  const defaultTemplateId = String(payload.default_template_id || '').trim();
  return { defaultTemplateId, templates };
}

function setBranchTemplateOptions(rawPayload, preferredId = '') {
  const select = byId('branch-template-id');
  if (!select) return '';

  const parsed = parseBranchTemplates(rawPayload);
  const current = String(select.value || '').trim();
  select.innerHTML = '<option value="">None</option>';
  for (const template of parsed.templates) {
    const option = document.createElement('option');
    option.value = template.id;
    option.textContent = `${template.name} (${template.id})`;
    select.appendChild(option);
  }

  const validIds = new Set(parsed.templates.map(item => item.id));
  const nextValue = validIds.has(preferredId)
    ? preferredId
    : validIds.has(current)
      ? current
      : validIds.has(parsed.defaultTemplateId)
        ? parsed.defaultTemplateId
        : '';
  select.value = nextValue;
  return nextValue;
}

function selectedBranchTemplateFromEditor() {
  const selectedId = String(byId('branch-template-id')?.value || '').trim();
  if (!selectedId) return null;
  const parsed = parseBranchTemplates(String(byId('plan-branch-templates')?.value || '').trim());
  return parsed.templates.find(item => item.id === selectedId) || null;
}

function applyBranchTemplateToEditor(template) {
  if (!template || typeof template !== 'object') return false;
  const branchName = String(template.branch_name || template.name || '').trim();
  if (branchName) byId('scenario-branch-name').value = branchName;

  const assumptionSetId = String(template.assumption_set_id || '').trim();
  const assumptionSelect = byId('branch-assumption-set-id');
  if (assumptionSelect) {
    assumptionSelect.value = assumptionSetId;
    if (assumptionSetId && assumptionSelect.value !== assumptionSetId) assumptionSelect.value = '';
  }

  const branchEvents = Array.isArray(template.branch_events) ? template.branch_events : [];
  byId('scenario-branch-events').value = branchEvents.length ? JSON.stringify(branchEvents, null, 2) : '';

  const compareSettings = template.compare_settings && typeof template.compare_settings === 'object'
    ? template.compare_settings
    : {};
  setPlanSettingsInputs(DIFF_SETTING_VALUE_FIELDS, compareSettings);
  return true;
}

function extractAssumptionSetSummary(resultPayload) {
  if (!resultPayload || typeof resultPayload !== 'object') return null;
  const scenarios = Array.isArray(resultPayload.scenarios) ? resultPayload.scenarios : [];
  const baseline = scenarios.find(item => item && item.label === 'baseline') || scenarios[0];
  const assumptions = baseline && typeof baseline === 'object' ? baseline.assumptions : null;
  if (!assumptions || typeof assumptions !== 'object') return null;
  const id = String(assumptions.assumption_set_id || '').trim() || null;
  const name = String(assumptions.assumption_set_name || '').trim() || null;
  if (!id && !name) return null;
  return { id, name };
}

function describeAssumptionSetSummary(summary) {
  if (!summary || typeof summary !== 'object') return 'Not available';
  const id = String(summary.id || '').trim();
  const name = String(summary.name || '').trim();
  if (id && name) return `${name} (${id})`;
  if (name) return name;
  if (id) return id;
  return 'Not available';
}

function resetProjectionState() {
  projectionState.diffResult = null;
  projectionState.branchResult = null;
  projectionState.profilePayload = null;
  projectionState.profileLoading = false;
}

function projectionSourceAvailable(optionValue) {
  if (optionValue === 'diff_base' || optionValue === 'diff_candidate') return !!projectionState.diffResult;
  if (optionValue === 'branch_base' || optionValue === 'branch_branch') return !!projectionState.branchResult;
  return false;
}

function setProjectionSourceOptions(preferredValue = '') {
  const select = byId('projection-source');
  if (!select) return '';

  const available = PROJECTION_SOURCE_OPTIONS.filter(item => projectionSourceAvailable(item.value));
  const current = String(select.value || '').trim();
  if (!available.length) {
    select.innerHTML = '<option value="">No scenario data yet</option>';
    select.value = '';
    return '';
  }

  select.innerHTML = '';
  for (const item of available) {
    const option = document.createElement('option');
    option.value = item.value;
    option.textContent = item.label;
    select.appendChild(option);
  }

  const next = available.some(item => item.value === preferredValue)
    ? preferredValue
    : available.some(item => item.value === current)
      ? current
      : available[0].value;
  select.value = next;
  return next;
}

function maybeLoadProjectionProfile(force = false) {
  if (force) {
    projectionState.profilePayload = null;
    projectionState.profileLoading = false;
  }
  if (projectionState.profilePayload || projectionState.profileLoading) return;
  if (!projectionState.diffResult && !projectionState.branchResult) return;

  projectionState.profileLoading = true;
  fetchJson('/api/financial-profile')
    .then((payload) => {
      projectionState.profilePayload = payload && typeof payload === 'object' ? payload : { physical_assets: [] };
    })
    .catch((error) => {
      projectionState.profilePayload = { physical_assets: [] };
      writeLog(`Projection profile load failed: ${error.message}`, null, true);
    })
    .finally(() => {
      projectionState.profileLoading = false;
      renderProjectionVisuals();
    });
}

function normalizeYear(raw) {
  const value = Number(raw);
  if (!Number.isFinite(value)) return null;
  return Math.trunc(value);
}

function yearFromIso(rawDate) {
  const text = String(rawDate || '').slice(0, 4);
  const value = Number(text);
  if (!Number.isFinite(value)) return null;
  return Math.trunc(value);
}

function projectionPlanningResultForSource(source) {
  if (source === 'diff_base') return projectionState.diffResult?.base_result || null;
  if (source === 'diff_candidate') return projectionState.diffResult?.candidate_result || null;
  if (source === 'branch_base') return projectionState.branchResult?.base_result || null;
  if (source === 'branch_branch') return projectionState.branchResult?.branch_result || null;
  return null;
}

function resolveScenarioFromPlanningResult(planningResult, preferredLabel) {
  const scenarios = Array.isArray(planningResult?.scenarios) ? planningResult.scenarios : [];
  if (!scenarios.length) return null;
  const resolved = scenarios.find(item => item && item.label === preferredLabel) || scenarios[0];
  if (!resolved || typeof resolved !== 'object') return null;
  return resolved;
}

function buildDebtBalanceSeries(years, debtProjection) {
  const series = new Map();
  const selected = debtProjection && typeof debtProjection === 'object' ? debtProjection.selected_scenario : null;
  const monthPoints = Array.isArray(selected?.month_points) ? selected.month_points : [];
  const byYear = new Map();
  for (const point of monthPoints) {
    const year = yearFromIso(point?.as_of);
    if (year === null) continue;
    const balance = Number(point?.total_balance_usd);
    if (!Number.isFinite(balance)) continue;
    byYear.set(year, Math.max(0, balance));
  }

  let lastValue = 0;
  for (const year of years) {
    if (byYear.has(year)) lastValue = Number(byYear.get(year));
    series.set(year, Math.max(0, lastValue));
  }
  return series;
}

function buildPhysicalAssetsSeries(years) {
  const series = new Map();
  if (!years.length) return series;

  const assets = Array.isArray(projectionState.profilePayload?.physical_assets)
    ? projectionState.profilePayload.physical_assets
    : [];
  if (!assets.length) {
    for (const year of years) series.set(year, 0);
    return series;
  }

  const startYear = years[0];
  for (const year of years) {
    const offset = Math.max(0, year - startYear);
    let total = 0;
    for (const asset of assets) {
      const currentValue = Number(asset?.current_value_usd);
      if (!Number.isFinite(currentValue) || currentValue <= 0) continue;
      const growthRateRaw = Number(asset?.annual_growth_rate);
      const growthRate = Number.isFinite(growthRateRaw) ? Math.max(-0.95, Math.min(1.0, growthRateRaw)) : 0;
      total += currentValue * ((1 + growthRate) ** offset);
    }
    series.set(year, total);
  }

  return series;
}

function buildNetWorthSeries(timelinePoints, debtProjection) {
  const years = [];
  for (const point of timelinePoints) {
    const year = normalizeYear(point?.year);
    if (year === null) continue;
    years.push(year);
  }

  years.sort((a, b) => a - b);
  const uniqueYears = years.filter((value, index) => index === 0 || value !== years[index - 1]);
  if (!uniqueYears.length) return [];

  const debtByYear = buildDebtBalanceSeries(uniqueYears, debtProjection);
  const physicalAssetsByYear = buildPhysicalAssetsSeries(uniqueYears);
  const timelineByYear = new Map();
  for (const point of timelinePoints) {
    const year = normalizeYear(point?.year);
    if (year === null) continue;
    timelineByYear.set(year, point);
  }

  return uniqueYears.map((year) => {
    const point = timelineByYear.get(year) || {};
    const portfolio = Number(point?.ending_balance_usd);
    const portfolioReal = Number(point?.ending_balance_real_usd);
    const debtBalance = Number(debtByYear.get(year) || 0);
    const physicalAssets = Number(physicalAssetsByYear.get(year) || 0);
    const resolvedPortfolio = Number.isFinite(portfolio) ? portfolio : 0;
    const resolvedReal = Number.isFinite(portfolioReal) ? portfolioReal : resolvedPortfolio;
    return {
      year,
      portfolio: resolvedPortfolio,
      portfolio_real: resolvedReal,
      debt_balance: debtBalance,
      physical_assets: physicalAssets,
      net_worth: resolvedPortfolio + physicalAssets - debtBalance,
    };
  });
}

function buildLinePath(points, valueKey, toY) {
  return points.map((point, index) => `${index === 0 ? 'M' : 'L'} ${point.x.toFixed(2)} ${toY(Number(point[valueKey] || 0)).toFixed(2)}`).join(' ');
}

function renderNetWorthChart(series) {
  const chart = byId('plan-net-worth-chart');
  if (!chart) return;
  if (!Array.isArray(series) || !series.length) {
    chart.innerHTML = '';
    return;
  }

  const width = 760;
  const height = 220;
  const left = 44;
  const right = 18;
  const top = 14;
  const bottom = 30;
  const plotWidth = width - left - right;
  const plotHeight = height - top - bottom;

  let minValue = Number.POSITIVE_INFINITY;
  let maxValue = Number.NEGATIVE_INFINITY;
  for (const row of series) {
    for (const key of ['net_worth', 'portfolio', 'physical_assets', 'debt_balance']) {
      const value = Number(row[key]);
      if (!Number.isFinite(value)) continue;
      minValue = Math.min(minValue, value);
      maxValue = Math.max(maxValue, value);
    }
  }
  if (!Number.isFinite(minValue) || !Number.isFinite(maxValue)) {
    chart.innerHTML = '';
    return;
  }
  if (minValue === maxValue) {
    const pad = Math.max(1, Math.abs(minValue) * 0.1);
    minValue -= pad;
    maxValue += pad;
  }
  const valueRange = maxValue - minValue;

  const toY = value => top + ((maxValue - value) / valueRange) * plotHeight;
  const points = series.map((row, index) => ({
    ...row,
    x: left + (series.length === 1 ? 0 : (index / (series.length - 1)) * plotWidth),
  }));

  const netWorthPath = buildLinePath(points, 'net_worth', toY);
  const portfolioPath = buildLinePath(points, 'portfolio', toY);
  const physicalPath = buildLinePath(points, 'physical_assets', toY);
  const debtPath = buildLinePath(points, 'debt_balance', toY);

  const grid = [];
  const ticks = 4;
  for (let i = 0; i <= ticks; i += 1) {
    const ratio = i / ticks;
    const y = top + ratio * plotHeight;
    const tickValue = maxValue - ratio * valueRange;
    grid.push(`<line x1="${left}" y1="${y.toFixed(2)}" x2="${(left + plotWidth).toFixed(2)}" y2="${y.toFixed(2)}" class="projection-grid-line"></line>`);
    grid.push(`<text x="4" y="${(y + 4).toFixed(2)}" class="projection-axis-label">${fmtCurrency(tickValue)}</text>`);
  }

  if (minValue < 0 && maxValue > 0) {
    const zeroY = toY(0);
    grid.push(`<line x1="${left}" y1="${zeroY.toFixed(2)}" x2="${(left + plotWidth).toFixed(2)}" y2="${zeroY.toFixed(2)}" class="projection-zero-line"></line>`);
  }

  const firstYear = series[0]?.year || '-';
  const lastYear = series[series.length - 1]?.year || '-';
  chart.innerHTML = `
    ${grid.join('')}
    <path d="${netWorthPath}" class="projection-line projection-line-net-worth"></path>
    <path d="${portfolioPath}" class="projection-line projection-line-portfolio"></path>
    <path d="${physicalPath}" class="projection-line projection-line-physical"></path>
    <path d="${debtPath}" class="projection-line projection-line-debt"></path>
    <text x="${left}" y="${height - 8}" class="projection-axis-label">${firstYear}</text>
    <text x="${(left + plotWidth - 40).toFixed(2)}" y="${height - 8}" class="projection-axis-label">${lastYear}</text>
  `;
}

function accountTypeColor(accountType, index) {
  const key = String(accountType || '').trim().toLowerCase();
  if (Object.prototype.hasOwnProperty.call(ACCOUNT_TYPE_COLORS, key)) return ACCOUNT_TYPE_COLORS[key];
  return FALLBACK_ACCOUNT_TYPE_COLORS[index % FALLBACK_ACCOUNT_TYPE_COLORS.length];
}

function buildAccountMetricSeries(accountPoints, metricKey) {
  const byYear = new Map();
  const accountTypes = new Set();
  for (const point of accountPoints) {
    const year = normalizeYear(point?.year);
    if (year === null) continue;
    const accountType = String(point?.account_type || 'unknown').trim() || 'unknown';
    const rawValue = Number(point?.[metricKey]);
    const value = Number.isFinite(rawValue) ? rawValue : 0;
    if (!byYear.has(year)) byYear.set(year, {});
    const bucket = byYear.get(year);
    bucket[accountType] = Number(bucket[accountType] || 0) + value;
    accountTypes.add(accountType);
  }

  const years = [...byYear.keys()].sort((a, b) => a - b);
  const types = [...accountTypes].sort((a, b) => a.localeCompare(b));
  const rows = years.map((year) => {
    const values = byYear.get(year) || {};
    let positiveTotal = 0;
    let negativeTotal = 0;
    for (const type of types) {
      const value = Number(values[type] || 0);
      if (value >= 0) positiveTotal += value;
      else negativeTotal += value;
    }
    return {
      year,
      values,
      positive_total: positiveTotal,
      negative_total: negativeTotal,
    };
  });

  return { rows, types };
}

function renderAccountTypeChart(accountPoints, metricKey) {
  const chart = byId('plan-account-type-chart');
  const legend = byId('plan-account-type-legend');
  if (!chart || !legend) return;

  const series = buildAccountMetricSeries(accountPoints, metricKey);
  if (!series.rows.length || !series.types.length) {
    chart.innerHTML = '';
    legend.innerHTML = '';
    return;
  }

  const width = 760;
  const height = 220;
  const left = 44;
  const right = 18;
  const top = 14;
  const bottom = 30;
  const plotWidth = width - left - right;
  const plotHeight = height - top - bottom;

  const maxValue = Math.max(0, ...series.rows.map(item => item.positive_total));
  const minValue = Math.min(0, ...series.rows.map(item => item.negative_total));
  const range = Math.max(1, maxValue - minValue);
  const toY = value => top + ((maxValue - value) / range) * plotHeight;

  const bars = [];
  const yearSpan = plotWidth / Math.max(1, series.rows.length);
  const barWidth = Math.max(6, yearSpan * 0.66);

  for (let rowIndex = 0; rowIndex < series.rows.length; rowIndex += 1) {
    const row = series.rows[rowIndex];
    const x = left + rowIndex * yearSpan + ((yearSpan - barWidth) / 2);
    let positiveCursor = 0;
    let negativeCursor = 0;

    for (let typeIndex = 0; typeIndex < series.types.length; typeIndex += 1) {
      const type = series.types[typeIndex];
      const value = Number(row.values[type] || 0);
      if (!value) continue;

      let start = 0;
      let end = 0;
      if (value > 0) {
        start = positiveCursor;
        positiveCursor += value;
        end = positiveCursor;
      } else {
        start = negativeCursor;
        negativeCursor += value;
        end = negativeCursor;
      }

      const y1 = toY(start);
      const y2 = toY(end);
      const y = Math.min(y1, y2);
      const h = Math.max(1, Math.abs(y1 - y2));
      bars.push(`<rect x="${x.toFixed(2)}" y="${y.toFixed(2)}" width="${barWidth.toFixed(2)}" height="${h.toFixed(2)}" fill="${accountTypeColor(type, typeIndex)}" opacity="0.86"></rect>`);
    }
  }

  const grid = [];
  const ticks = 4;
  for (let i = 0; i <= ticks; i += 1) {
    const ratio = i / ticks;
    const y = top + ratio * plotHeight;
    const tickValue = maxValue - ratio * range;
    grid.push(`<line x1="${left}" y1="${y.toFixed(2)}" x2="${(left + plotWidth).toFixed(2)}" y2="${y.toFixed(2)}" class="projection-grid-line"></line>`);
    grid.push(`<text x="4" y="${(y + 4).toFixed(2)}" class="projection-axis-label">${fmtCurrency(tickValue)}</text>`);
  }

  if (minValue < 0 && maxValue > 0) {
    const zeroY = toY(0);
    grid.push(`<line x1="${left}" y1="${zeroY.toFixed(2)}" x2="${(left + plotWidth).toFixed(2)}" y2="${zeroY.toFixed(2)}" class="projection-zero-line"></line>`);
  }

  const firstYear = series.rows[0]?.year || '-';
  const lastYear = series.rows[series.rows.length - 1]?.year || '-';
  chart.innerHTML = `
    ${grid.join('')}
    ${bars.join('')}
    <text x="${left}" y="${height - 8}" class="projection-axis-label">${firstYear}</text>
    <text x="${(left + plotWidth - 40).toFixed(2)}" y="${height - 8}" class="projection-axis-label">${lastYear}</text>
  `;

  legend.innerHTML = series.types.map((type, index) => (
    `<span class="projection-legend-item"><span class="projection-legend-swatch" style="background:${accountTypeColor(type, index)}"></span>${type}</span>`
  )).join('');
}

function renderProjectionAccountTable(accountPoints) {
  const tbody = byId('projection-account-body');
  if (!tbody) return;

  const byAccount = new Map();
  for (const point of accountPoints) {
    const accountId = String(point?.account_id || '').trim();
    if (!accountId) continue;
    const year = normalizeYear(point?.year);
    const ending = Number(point?.ending_balance_usd);
    const contribution = Number(point?.contribution_usd);
    const growth = Number(point?.growth_usd);
    const withdrawal = Number(point?.withdrawal_usd);

    if (!byAccount.has(accountId)) {
      byAccount.set(accountId, {
        account_id: accountId,
        account_type: String(point?.account_type || 'unknown'),
        latest_year: year === null ? -1 : year,
        final_balance: Number.isFinite(ending) ? ending : 0,
        contributions: 0,
        growth: 0,
        withdrawals: 0,
      });
    }

    const row = byAccount.get(accountId);
    if (year !== null && year >= row.latest_year && Number.isFinite(ending)) {
      row.latest_year = year;
      row.final_balance = ending;
    }
    if (Number.isFinite(contribution)) row.contributions += contribution;
    if (Number.isFinite(growth)) row.growth += growth;
    if (Number.isFinite(withdrawal)) row.withdrawals += withdrawal;
  }

  const rows = [...byAccount.values()].sort((a, b) => b.final_balance - a.final_balance);
  if (!rows.length) {
    tbody.innerHTML = '<tr><td colspan="6">No projection data yet.</td></tr>';
    return;
  }

  tbody.innerHTML = '';
  for (const row of rows) {
    const tr = document.createElement('tr');
    tr.innerHTML = `
      <td><code>${row.account_id}</code></td>
      <td>${row.account_type || 'unknown'}</td>
      <td>${fmtCurrency(row.final_balance || 0)}</td>
      <td>${fmtCurrency(row.contributions || 0)}</td>
      <td>${fmtCurrency(row.growth || 0)}</td>
      <td>${fmtCurrency(row.withdrawals || 0)}</td>`;
    tbody.appendChild(tr);
  }
}

function renderProjectionVisuals() {
  const summary = byId('projection-summary');
  if (!summary) return;

  const selectedSource = setProjectionSourceOptions();
  if (!selectedSource) {
    summary.textContent = 'Run a scenario diff or branch to populate projection visuals.';
    renderNetWorthChart([]);
    renderAccountTypeChart([], 'ending_balance_usd');
    renderProjectionAccountTable([]);
    return;
  }

  maybeLoadProjectionProfile();

  const scenarioLabel = String(byId('projection-scenario-label')?.value || 'baseline').trim() || 'baseline';
  const metricKey = String(byId('projection-account-metric')?.value || 'ending_balance_usd').trim() || 'ending_balance_usd';
  const planningResult = projectionPlanningResultForSource(selectedSource);
  const scenario = resolveScenarioFromPlanningResult(planningResult, scenarioLabel);
  if (!planningResult || !scenario) {
    summary.textContent = 'Selected projection source does not include scenario data.';
    renderNetWorthChart([]);
    renderAccountTypeChart([], metricKey);
    renderProjectionAccountTable([]);
    return;
  }

  const timelinePoints = Array.isArray(scenario.timeline_points) ? scenario.timeline_points : [];
  const accountPoints = Array.isArray(scenario.account_balance_points) ? scenario.account_balance_points : [];
  if (!timelinePoints.length) {
    summary.textContent = 'No timeline points available for this scenario.';
    renderNetWorthChart([]);
    renderAccountTypeChart([], metricKey);
    renderProjectionAccountTable([]);
    return;
  }

  const netWorthSeries = buildNetWorthSeries(timelinePoints, planningResult?.debt_projection);
  renderNetWorthChart(netWorthSeries);
  renderAccountTypeChart(accountPoints, metricKey);
  renderProjectionAccountTable(accountPoints);

  const sourceLabel = PROJECTION_SOURCE_OPTIONS.find(item => item.value === selectedSource)?.label || selectedSource;
  const finalPoint = netWorthSeries[netWorthSeries.length - 1] || {};
  const firstYear = netWorthSeries[0]?.year;
  const lastYear = finalPoint?.year;
  const metricLabel = metricKey === 'contribution_usd'
    ? 'Contributions'
    : metricKey === 'growth_usd'
      ? 'Growth'
      : 'Ending Balance';
  summary.textContent = `${sourceLabel} • ${String(scenario.label || scenarioLabel)} • ${firstYear || '-'} to ${lastYear || '-'} • Final net worth ${fmtCurrency(finalPoint.net_worth || 0)} • Account metric: ${metricLabel}`;
}

function renderPlanTopNextActions(actionsRaw) {
  const summaryEl = byId('plan-next-actions-summary');
  const listEl = byId('plan-next-actions');
  if (!summaryEl || !listEl) return;

  const actions = Array.isArray(actionsRaw) ? actionsRaw : [];
  if (!actions.length) {
    summaryEl.textContent = 'No ranked next actions yet for this plan. Use Recommendation Inbox to create or score recommendations.';
    listEl.innerHTML = '<article class="list-item incomplete"><p class="list-item-title">No next actions yet.</p><p class="list-item-meta">Open Recommendation Inbox and add at least one proposed recommendation.</p></article>';
    return;
  }

  const highCount = actions.filter((item) => String(item.priority || 'medium').toLowerCase() === 'high').length;
  summaryEl.textContent = `${actions.length} ranked action(s) loaded${highCount > 0 ? ` • ${highCount} high priority` : ''}.`;
  listEl.innerHTML = '';
  for (const action of actions) {
    const priority = String(action.priority || 'medium').toLowerCase();
    const scoreTotal = Number(action.score_total);
    const scoreRank = Number(action.score_rank);
    const scoreParts = [`Priority: ${priority.toUpperCase()}`];
    if (Number.isFinite(scoreRank) && scoreRank > 0) scoreParts.push(`Rank: #${Math.trunc(scoreRank)}`);
    if (Number.isFinite(scoreTotal)) scoreParts.push(`Score: ${scoreTotal.toFixed(1)}`);
    if (action.recommendation_type) scoreParts.push(`Type: ${String(action.recommendation_type)}`);
    if (action.source) scoreParts.push(`Source: ${String(action.source)}`);
    const reasons = Array.isArray(action.score_reasons)
      ? action.score_reasons.filter(Boolean).slice(0, 2).join(' ')
      : '';

    const card = document.createElement('article');
    card.className = `list-item ${priority === 'high' ? 'attention' : priority === 'low' ? 'complete' : 'incomplete'}`;
    card.innerHTML = `
      <p class="list-item-title">${action.title || '-'}</p>
      <p class="list-item-meta">${scoreParts.join(' • ')}</p>
      <p class="list-item-meta">${action.detail || ''}</p>
      ${reasons ? `<p class="list-item-meta">${reasons}</p>` : ''}
      ${action.action_hint ? `<p class="list-item-meta">Action: ${action.action_hint}</p>` : ''}
    `;
    listEl.appendChild(card);
  }
}

function renderPlanClosureSummary(result) {
  const summaryEl = byId('plan-closure-summary-status');
  const detailsEl = byId('plan-closure-summary-details');
  if (!summaryEl || !detailsEl) return;

  if (!result || typeof result !== 'object' || !result.analytics || typeof result.analytics !== 'object') {
    summaryEl.textContent = 'Generate recommendation closure analytics to capture calibration history for this plan.';
    detailsEl.innerHTML = '<article class="list-item incomplete"><p class="list-item-title">No closure summary generated yet.</p><p class="list-item-meta">Use Generate Artifact to write a calibration artifact and log this review decision.</p></article>';
    return;
  }

  const analytics = result.analytics;
  const summary = analytics.summary && typeof analytics.summary === 'object' ? analytics.summary : {};
  const calibrationSummary = analytics.calibration_summary && typeof analytics.calibration_summary === 'object'
    ? analytics.calibration_summary
    : {};
  const count = Number(analytics.count || 0);
  const measured = Number(summary.measured_count || 0);
  const coverage = Number(summary.realized_coverage_pct || 0);
  const directionRate = Number(calibrationSummary.future_value_direction_match_rate_pct);
  const meanAbsError = Number(calibrationSummary.mean_future_value_abs_error_usd);
  const summaryParts = [`Closed ${count}`, `Measured ${measured}`];
  if (Number.isFinite(coverage)) summaryParts.push(`Coverage ${coverage.toFixed(1)}%`);
  if (Number.isFinite(directionRate)) summaryParts.push(`Match ${directionRate.toFixed(1)}%`);
  if (Number.isFinite(meanAbsError)) summaryParts.push(`MAE ${fmtCurrency(meanAbsError)}`);
  if (calibrationSummary.future_value_bias) summaryParts.push(`Bias ${String(calibrationSummary.future_value_bias).replace('_', ' ')}`);
  if (result.artifact?.id) summaryParts.push(`Artifact ${result.artifact.id}`);
  summaryEl.textContent = summaryParts.join(' • ');

  const fmtPct = (value) => {
    const num = Number(value);
    return Number.isFinite(num) ? `${num.toFixed(1)}%` : 'n/a';
  };
  const fmtMoney = (value) => {
    const num = Number(value);
    return Number.isFinite(num) ? fmtCurrency(num) : 'n/a';
  };

  const cards = [];
  const byType = Array.isArray(analytics.calibration_by_type) ? analytics.calibration_by_type : [];
  if (byType.length) {
    cards.push(`<article class="list-item"><p class="list-item-title">Calibration by Type</p><p class="list-item-meta">${byType.slice(0, 3).map((row) => `${row.key}: measured ${row.measured_count}/${row.count}, match ${fmtPct(row.future_value_direction_match_rate_pct)}, MAE ${fmtMoney(row.mean_future_value_abs_error_usd)}`).join(' • ')}</p></article>`);
  }
  const bySource = Array.isArray(analytics.calibration_by_source) ? analytics.calibration_by_source : [];
  if (bySource.length) {
    cards.push(`<article class="list-item"><p class="list-item-title">Calibration by Source</p><p class="list-item-meta">${bySource.slice(0, 3).map((row) => `${row.key}: measured ${row.measured_count}/${row.count}, match ${fmtPct(row.future_value_direction_match_rate_pct)}, MAE ${fmtMoney(row.mean_future_value_abs_error_usd)}`).join(' • ')}</p></article>`);
  }
  const windows = Array.isArray(analytics.calibration_windows) ? analytics.calibration_windows : [];
  if (windows.length) {
    cards.push(`<article class="list-item"><p class="list-item-title">Calibration Windows</p><p class="list-item-meta">${windows.slice(0, 3).map((row) => `${row.window || row.key}: measured ${row.measured_count}/${row.count}, match ${fmtPct(row.future_value_direction_match_rate_pct)}, MAE ${fmtMoney(row.mean_future_value_abs_error_usd)}`).join(' • ')}</p></article>`);
  }
  detailsEl.innerHTML = cards.length
    ? cards.join('')
    : '<article class="list-item"><p class="list-item-title">No calibration rows available yet.</p></article>';
}

function formatTrendPct(value) {
  const num = Number(value);
  return Number.isFinite(num) ? `${num.toFixed(1)}%` : 'n/a';
}

function renderPlanClosureTrend(payload) {
  const summaryEl = byId('plan-closure-trend-status');
  const detailsEl = byId('plan-closure-trend-details');
  if (!summaryEl || !detailsEl) return;

  if (!payload || typeof payload !== 'object') {
    summaryEl.textContent = 'Select a plan to load recommendation quality trend.';
    detailsEl.innerHTML = '<article class="list-item incomplete"><p class="list-item-title">No trend data loaded yet.</p></article>';
    return;
  }

  const windows = Array.isArray(payload.calibration_windows) ? payload.calibration_windows : [];
  const row30 = windows.find((row) => row && row.window === '30d') || {};
  const row90 = windows.find((row) => row && row.window === '90d') || {};
  const rowAll = windows.find((row) => row && row.window === 'all') || {};

  const rowText = (row) => {
    const measured = Number(row.measured_count || 0);
    const count = Number(row.count || 0);
    return `measured ${measured}/${count} • coverage ${formatTrendPct(row.realized_coverage_pct)} • match ${formatTrendPct(row.future_value_direction_match_rate_pct)} • MAE ${Number.isFinite(Number(row.mean_future_value_abs_error_usd)) ? fmtCurrency(Number(row.mean_future_value_abs_error_usd)) : 'n/a'}`;
  };

  summaryEl.textContent = [
    `Closed ${Number(payload.count || 0)}`,
    `30d ${rowText(row30)}`,
    `90d ${rowText(row90)}`,
  ].join(' • ');

  detailsEl.innerHTML = `
    <article class="list-item">
      <p class="list-item-title">30 Day Trend</p>
      <p class="list-item-meta">${rowText(row30)}</p>
    </article>
    <article class="list-item">
      <p class="list-item-title">90 Day Trend</p>
      <p class="list-item-meta">${rowText(row90)}</p>
    </article>
    <article class="list-item">
      <p class="list-item-title">All-Time Baseline</p>
      <p class="list-item-meta">${rowText(rowAll)}</p>
    </article>
  `;
}

async function loadPlanClosureTrend({ silent = true } = {}) {
  const planId = String(state.currentPlanId || '').trim();
  if (!planId) {
    state.planClosureTrend = null;
    renderPlanClosureTrend(null);
    return;
  }
  try {
    const params = new URLSearchParams();
    params.set('limit', '300');
    params.set('statuses', 'applied,rejected');
    params.set('include_pending_realized', 'true');
    params.set('plan_id', planId);
    const payload = await fetchJson(`/api/recommendations/closure-analytics?${params.toString()}`);
    state.planClosureTrend = payload && typeof payload === 'object' ? payload : null;
    if (state.currentPlanId === planId) {
      renderPlanClosureTrend(state.planClosureTrend);
    }
  } catch (error) {
    state.planClosureTrend = null;
    renderPlanClosureTrend(null);
    if (!silent) writeLog(`Plan closure trend load failed: ${error.message}`, null, true);
  }
}

export function clearDetail() {
  state.currentPlanDetail = null;
  state.planClosureSummary = null;
  state.planClosureTrend = null;
  byId('plan-meta').textContent = 'Select a plan to view details.';
  byId('plan-next-actions-summary').textContent = 'Select a plan to load ranked next actions.';
  byId('plan-closure-summary-status').textContent = 'Select a plan to generate recommendation closure analytics.';
  byId('plan-closure-trend-status').textContent = 'Select a plan to load recommendation quality trend.';
  byId('plan-settings-meta').textContent = 'Blank values use global defaults from planner configuration.';
  ['plan-markdown', 'plan-tasks', 'plan-timeline', 'plan-assumption-sets', 'plan-contribution-rules', 'plan-branch-templates', 'plan-context', 'scenario-diff-output', 'withdrawal-current-portfolio-value', 'withdrawal-strategies', 'withdrawal-strategy-compare-output', 'scenario-branch-name', 'scenario-branch-events', 'scenario-branch-output', 'research-bridge-symbols', 'artifact-content'].forEach(id => { const el = byId(id); if (el) el.value = ''; });
  for (const field of [...PLAN_SETTING_VALUE_FIELDS, ...DIFF_SETTING_VALUE_FIELDS]) {
    const el = byId(field.inputId);
    if (el) el.value = '';
  }
  writeTimelinePayloadToEditor({ events: [], retirement: {} }, { preferFormValues: false });
  resetTimelineEventInputs();
  writeContributionRulesPayloadToEditor({}, { preferFormValues: false });
  resetContributionRuleInputs();
  const includeRawCheckbox = byId('withdrawal-include-raw-results');
  if (includeRawCheckbox) includeRawCheckbox.checked = false;
  byId('scenario-diff-summary').textContent = 'No scenario diff run yet.';
  byId('withdrawal-strategy-compare-summary').textContent = 'No withdrawal strategy comparison run yet.';
  byId('scenario-branch-summary').textContent = 'No scenario branch run yet.';
  byId('research-bridge-summary').textContent = 'No watchlist research bridge activity recorded yet.';
  setResearchBridgeArtifactAction('', '');
  byId('projection-summary').textContent = 'Run a scenario diff or branch to populate projection visuals.';
  byId('plan-next-actions').innerHTML = '<article class="list-item incomplete"><p class="list-item-title">No plan selected.</p></article>';
  byId('plan-closure-summary-details').innerHTML = '<article class="list-item incomplete"><p class="list-item-title">No closure summary generated yet.</p></article>';
  byId('plan-closure-trend-details').innerHTML = '<article class="list-item incomplete"><p class="list-item-title">No trend data loaded yet.</p></article>';
  byId('plan-decisions-body').innerHTML = '<tr><td colspan="4">No decisions yet.</td></tr>';
  byId('plan-artifacts-body').innerHTML = '<tr><td colspan="4">No artifacts yet.</td></tr>';
  byId('projection-account-body').innerHTML = '<tr><td colspan="6">No projection data yet.</td></tr>';
  setPlanSettingsInputs(PLAN_SETTING_VALUE_FIELDS, {});
  setPlanSettingsInputs(DIFF_SETTING_VALUE_FIELDS, {});
  const scenarioLabelSelect = byId('projection-scenario-label');
  if (scenarioLabelSelect) scenarioLabelSelect.value = 'baseline';
  const metricSelect = byId('projection-account-metric');
  if (metricSelect) metricSelect.value = 'ending_balance_usd';
  resetProjectionState();
  setAssumptionSetOptions({});
  setBranchTemplateOptions({});
  setProjectionSourceOptions();
  renderNetWorthChart([]);
  renderAccountTypeChart([], 'ending_balance_usd');
  setControlsEnabled(false);
}

export function renderDetail() {
  const d = state.currentPlanDetail;
  if (!d) { clearDetail(); return; }
  resetProjectionState();
  byId('plan-meta').textContent = `${d.title || 'Untitled'} \u2022 ${d.is_active ? 'Active Plan' : 'Inactive'} \u2022 Updated ${fmtDate(d.updated_at)}`;
  byId('plan-markdown').value = d.files?.plan_markdown || '';
  byId('plan-tasks').value = d.files?.tasks_markdown || '';
  byId('plan-assumption-sets').value = d.files?.assumption_sets_json || '';
  byId('plan-branch-templates').value = d.files?.branch_templates_json || '';
  try {
    writeTimelinePayloadToEditor(d.files?.timeline_json ? JSON.parse(d.files.timeline_json) : {}, { preferFormValues: false });
  } catch {
    writeTimelinePayloadToEditor({ events: [], retirement: {} }, { preferFormValues: false });
  }
  resetTimelineEventInputs();
  try {
    writeContributionRulesPayloadToEditor(
      d.files?.contribution_rules_json ? JSON.parse(d.files.contribution_rules_json) : {},
      { preferFormValues: false },
    );
  } catch {
    writeContributionRulesPayloadToEditor({}, { preferFormValues: false });
  }
  resetContributionRuleInputs();
  setAssumptionSetOptions(d.files?.assumption_sets_json || '');
  setBranchTemplateOptions(d.files?.branch_templates_json || '');
  byId('plan-context').value = d.files?.context_markdown || '';
  byId('scenario-diff-summary').textContent = 'No scenario diff run yet.';
  byId('scenario-diff-output').value = '';
  byId('withdrawal-strategy-compare-summary').textContent = 'No withdrawal strategy comparison run yet.';
  byId('withdrawal-current-portfolio-value').value = '';
  byId('withdrawal-strategies').value = DEFAULT_WITHDRAWAL_STRATEGIES.join(', ');
  byId('withdrawal-strategy-compare-output').value = '';
  const includeRawCheckbox = byId('withdrawal-include-raw-results');
  if (includeRawCheckbox) includeRawCheckbox.checked = false;
  byId('scenario-branch-summary').textContent = 'No scenario branch run yet.';
  byId('scenario-branch-output').value = '';
  byId('scenario-branch-name').value = '';
  byId('scenario-branch-events').value = '';
  byId('research-bridge-symbols').value = '';
  byId('projection-summary').textContent = 'Run a scenario diff or branch to populate projection visuals.';
  byId('projection-account-body').innerHTML = '<tr><td colspan="6">No projection data yet.</td></tr>';
  const scenarioLabelSelect = byId('projection-scenario-label');
  if (scenarioLabelSelect) scenarioLabelSelect.value = 'baseline';
  const metricSelect = byId('projection-account-metric');
  if (metricSelect) metricSelect.value = 'ending_balance_usd';
  setProjectionSourceOptions();
  renderNetWorthChart([]);
  renderAccountTypeChart([], 'ending_balance_usd');
  setPlanSettingsInputs(PLAN_SETTING_VALUE_FIELDS, d.settings || {});
  setPlanSettingsInputs(DIFF_SETTING_VALUE_FIELDS, {});
  const su = d.settings?.updated_at ? fmtDate(d.settings.updated_at) : null;
  byId('plan-settings-meta').textContent = su ? `Settings updated ${su}` : 'Blank values use global defaults from planner configuration.';
  renderPlanTopNextActions(Array.isArray(d.top_next_actions) ? d.top_next_actions : []);
  if (state.planClosureSummary && state.planClosureSummary.plan_id === d.id) {
    renderPlanClosureSummary(state.planClosureSummary);
  } else {
    renderPlanClosureSummary(null);
  }
  if (state.planClosureTrend && state.planClosureTrend.plan_id === d.id) {
    renderPlanClosureTrend(state.planClosureTrend);
  } else {
    renderPlanClosureTrend(null);
    void loadPlanClosureTrend({ silent: true });
  }
  renderDecisions(Array.isArray(d.decisions) ? d.decisions : []);
  renderArtifacts(Array.isArray(d.artifacts) ? d.artifacts : []);
  byId('artifact-content').value = '';
  setControlsEnabled(true);
  renderResearchBridgeSummary(d);
}

function renderDecisions(decisions) {
  const tbody = byId('plan-decisions-body');
  tbody.innerHTML = '';
  if (!decisions.length) { tbody.innerHTML = '<tr><td colspan="4">No decisions yet.</td></tr>'; return; }
  for (const d of decisions) {
    const tr = document.createElement('tr');
    tr.innerHTML = `<td>${fmtDate(d.created_at)}</td><td>${d.status || 'proposed'}</td><td>${d.summary || '-'}</td><td>${d.rationale || '-'}</td>`;
    tbody.appendChild(tr);
  }
}

function setResearchBridgeArtifactAction(artifactId, artifactTitle = '') {
  const button = byId('open-latest-research-bridge-artifact');
  if (!button) return;
  const resolvedArtifactId = String(artifactId || '').trim();
  button.dataset.artifactId = resolvedArtifactId;
  button.disabled = !state.currentPlanId || !resolvedArtifactId;
  if (artifactTitle) button.title = String(artifactTitle);
  else button.removeAttribute('title');
}

function renderResearchBridgeSummary(detail) {
  const summaryEl = byId('research-bridge-summary');
  if (!summaryEl) return;
  const decisions = Array.isArray(detail?.decisions) ? detail.decisions : [];
  const artifacts = Array.isArray(detail?.artifacts) ? detail.artifacts : [];
  const latestBridgeDecision = decisions.find((item) => String(item?.summary || '').toLowerCase().includes('research bridge'));
  const latestBridgeArtifact = artifacts.find((item) => String(item?.title || '').toLowerCase().startsWith('research bridge pin'));
  setResearchBridgeArtifactAction(latestBridgeArtifact?.id, latestBridgeArtifact?.title || '');
  if (!latestBridgeDecision && !latestBridgeArtifact) {
    summaryEl.textContent = 'No watchlist research bridge activity recorded yet.';
    return;
  }

  const parts = [];
  if (latestBridgeDecision?.summary) parts.push(String(latestBridgeDecision.summary));
  if (latestBridgeDecision?.created_at) parts.push(`logged ${fmtDate(latestBridgeDecision.created_at)}`);
  if (latestBridgeArtifact?.title) parts.push(`artifact: ${latestBridgeArtifact.title}`);
  summaryEl.textContent = parts.join(' • ');
}

function renderArtifacts(artifacts) {
  const tbody = byId('plan-artifacts-body');
  tbody.innerHTML = '';
  if (!artifacts.length) { tbody.innerHTML = '<tr><td colspan="4">No artifacts yet.</td></tr>'; return; }
  for (const a of artifacts) {
    const tr = document.createElement('tr');
    const btn = document.createElement('button');
    btn.type = 'button'; btn.className = 'ghost small'; btn.textContent = 'Open';
    btn.addEventListener('click', () => loadArtifact(a.id).catch(e => writeLog(`Artifact load failed: ${e.message}`, null, true)));
    tr.innerHTML = `<td>${fmtDate(a.created_at)}</td><td>${a.title || '-'}</td><td>${a.file_name || '-'}</td><td></td>`;
    tr.lastElementChild.appendChild(btn);
    tbody.appendChild(tr);
  }
}

async function loadArtifact(artifactId) {
  if (!state.currentPlanId || !artifactId) return;
  const a = await fetchJson(`/api/plans/${encodeURIComponent(state.currentPlanId)}/artifacts/${encodeURIComponent(artifactId)}`);
  byId('artifact-content').value = a.content || '';
}

function formatHouseholdLabel(rawValue, fallback = 'default') {
  const text = String(rawValue || '').trim().toLowerCase();
  if (!text) return fallback;
  return text.replace(/_/g, ' ');
}

function extractHouseholdContextFromResult(resultPayload) {
  if (!resultPayload || typeof resultPayload !== 'object') return null;
  const household = resultPayload.household;
  if (household && typeof household === 'object' && !Array.isArray(household)) {
    return household;
  }
  const scenarios = Array.isArray(resultPayload.scenarios) ? resultPayload.scenarios : [];
  const baseline = scenarios.find((item) => String(item?.label || '').toLowerCase() === 'baseline') || scenarios[0];
  const assumptions = baseline?.assumptions;
  if (!assumptions || typeof assumptions !== 'object') return null;
  const mode = String(assumptions.household_mode || '').trim().toLowerCase() || 'individual';
  const filingStatus = String(assumptions.filing_status || '').trim().toLowerCase() || null;
  return {
    mode,
    source: null,
    enabled: mode === 'couple',
    filing_status: filingStatus,
    partner_income_usd: Number(coerceOptionalNumber(assumptions.household_partner_income_usd) || 0),
    partner_income_growth_rate: Number(coerceOptionalNumber(assumptions.household_partner_income_growth_rate) || 0),
    partner_retirement_age: coerceOptionalInteger(assumptions.household_partner_retirement_age),
    partner_social_security_annual_usd: Number(coerceOptionalNumber(assumptions.household_partner_social_security_annual_usd) || 0),
    partner_social_security_claiming_age: coerceOptionalInteger(assumptions.household_partner_social_security_claiming_age),
    shared_goal_target_usd: Number(coerceOptionalNumber(assumptions.household_shared_goal_target_usd) || 0),
    shared_goal_target_year: coerceOptionalInteger(assumptions.household_shared_goal_target_year),
    shared_goal_annual_funding_usd: Number(coerceOptionalNumber(assumptions.household_shared_goal_annual_funding_usd) || 0),
    partner_income_added_first_year_usd: Number(coerceOptionalNumber(assumptions.household_partner_income_added_first_year_usd) || 0),
    partner_income_added_total_usd: Number(coerceOptionalNumber(assumptions.household_partner_income_added_total_usd) || 0),
  };
}

function describeHouseholdContext(context) {
  if (!context || typeof context !== 'object') return 'Not available';
  const mode = String(context.mode || '').trim().toLowerCase() || 'individual';
  const filingStatus = String(context.filing_status || '').trim().toLowerCase();
  const partnerIncome = Number(coerceOptionalNumber(context.partner_income_usd) || 0);
  const partnerGrowth = Number(coerceOptionalNumber(context.partner_income_growth_rate) || 0);
  const partnerRetirementAge = coerceOptionalInteger(context.partner_retirement_age);
  const partnerSsAnnual = Number(coerceOptionalNumber(context.partner_social_security_annual_usd) || 0);
  const partnerSsClaimAge = coerceOptionalInteger(context.partner_social_security_claiming_age);
  const sharedGoalTarget = Number(coerceOptionalNumber(context.shared_goal_target_usd) || 0);
  const sharedGoalTargetYear = coerceOptionalInteger(context.shared_goal_target_year);
  const sharedGoalAnnualFunding = Number(coerceOptionalNumber(context.shared_goal_annual_funding_usd) || 0);
  const partnerIncomeFirstYear = Number(coerceOptionalNumber(context.partner_income_added_first_year_usd) || 0);
  const partnerIncomeTotal = Number(coerceOptionalNumber(context.partner_income_added_total_usd) || 0);

  const parts = [
    `mode ${formatHouseholdLabel(mode, 'individual')}`,
    `filing ${formatHouseholdLabel(filingStatus, 'default')}`,
  ];
  if (mode === 'couple') {
    if (partnerIncome > 0) {
      parts.push(`partner income ${fmtCurrency(partnerIncome)}/yr @ ${(partnerGrowth * 100).toFixed(2)}%`);
    }
    if (partnerRetirementAge !== null) {
      parts.push(`partner retirement age ${partnerRetirementAge}`);
    }
    if (partnerSsAnnual > 0) {
      const ssClaimLabel = partnerSsClaimAge === null ? 'n/a' : `age ${partnerSsClaimAge}`;
      parts.push(`partner SS ${fmtCurrency(partnerSsAnnual)}/yr (${ssClaimLabel})`);
    }
    if (sharedGoalTarget > 0) {
      const targetLabel = sharedGoalTargetYear === null ? 'target year n/a' : `target ${sharedGoalTargetYear}`;
      parts.push(`shared goal ${fmtCurrency(sharedGoalTarget)} (${targetLabel}, annual ${fmtCurrency(sharedGoalAnnualFunding)})`);
    }
    if (partnerIncomeFirstYear > 0 || partnerIncomeTotal > 0) {
      parts.push(`modeled partner income +${fmtCurrency(partnerIncomeFirstYear)} first year, +${fmtCurrency(partnerIncomeTotal)} total`);
    }
  }
  const source = String(context.source || '').trim();
  if (source) parts.push(`source ${source}`);
  return parts.join(', ');
}

function summarizeHouseholdTransition(baseContext, candidateContext) {
  if (!baseContext && !candidateContext) return '';
  const baseMode = formatHouseholdLabel(baseContext?.mode, 'individual');
  const candidateMode = formatHouseholdLabel(candidateContext?.mode, 'individual');
  const baseFiling = formatHouseholdLabel(baseContext?.filing_status, 'default');
  const candidateFiling = formatHouseholdLabel(candidateContext?.filing_status, 'default');
  return `household ${baseMode} -> ${candidateMode}, filing ${baseFiling} -> ${candidateFiling}`;
}

function normalizeSimulationSummary(rawSummary) {
  const summary = rawSummary && typeof rawSummary === 'object' ? rawSummary : {};
  const modeRaw = String(summary.mode || '').trim().toLowerCase();
  const timelineModeRaw = String(summary.timeline_mode || '').trim().toLowerCase();
  const variantRaw = String(summary.monte_carlo_variant || '').trim().toLowerCase();
  const seed = coerceOptionalInteger(summary.seed);
  const requestedHistoricalStartYear = coerceOptionalInteger(summary.requested_historical_start_year);
  const resolvedHistoricalRaw = summary.resolved_historical_start_year_by_scenario;
  const resolvedHistorical = {};
  if (resolvedHistoricalRaw && typeof resolvedHistoricalRaw === 'object' && !Array.isArray(resolvedHistoricalRaw)) {
    for (const [label, rawYear] of Object.entries(resolvedHistoricalRaw)) {
      const year = coerceOptionalInteger(rawYear);
      if (year === null) continue;
      const cleanedLabel = String(label || '').trim().toLowerCase();
      if (!cleanedLabel) continue;
      resolvedHistorical[cleanedLabel] = year;
    }
  }

  return {
    mode: SIMULATION_MODES.has(modeRaw) ? modeRaw : null,
    timeline_mode: SIMULATION_MODES.has(timelineModeRaw) ? timelineModeRaw : null,
    monte_carlo_variant: SIMULATION_MONTE_CARLO_VARIANTS.has(variantRaw) ? variantRaw : null,
    seed,
    requested_historical_start_year: requestedHistoricalStartYear,
    resolved_historical_start_year_by_scenario: resolvedHistorical,
  };
}

function extractSimulationSummaryFromResult(resultPayload) {
  if (!resultPayload || typeof resultPayload !== 'object') return normalizeSimulationSummary({});
  const summaryFromPayload = normalizeSimulationSummary(resultPayload.simulation);
  if (summaryFromPayload.mode) return summaryFromPayload;

  const scenarios = Array.isArray(resultPayload.scenarios) ? resultPayload.scenarios : [];
  const baseline = scenarios.find((item) => String(item?.label || '').toLowerCase() === 'baseline') || scenarios[0];
  const assumptions = baseline?.assumptions;
  if (!assumptions || typeof assumptions !== 'object') return summaryFromPayload;

  return normalizeSimulationSummary({
    mode: assumptions.simulation_mode,
    timeline_mode: assumptions.simulation_timeline_mode,
    monte_carlo_variant: assumptions.simulation_monte_carlo_variant,
    seed: assumptions.simulation_seed,
    requested_historical_start_year: assumptions.simulation_requested_historical_start_year,
    resolved_historical_start_year_by_scenario: assumptions.simulation_historical_start_year
      ? { baseline: assumptions.simulation_historical_start_year }
      : {},
  });
}

function describeSimulationSummary(summary) {
  const normalized = normalizeSimulationSummary(summary);
  const mode = normalized.mode || 'fixed';
  const timelineMode = normalized.timeline_mode || mode;
  const variant = normalized.monte_carlo_variant || 'p50';
  const seed = normalized.seed === null ? 'default' : String(normalized.seed);
  const requestedStart = normalized.requested_historical_start_year === null
    ? 'auto'
    : String(normalized.requested_historical_start_year);
  const resolvedHistorical = normalized.resolved_historical_start_year_by_scenario || {};
  const resolvedEntries = Object.entries(resolvedHistorical);
  const resolvedLabel = resolvedEntries.length
    ? resolvedEntries
      .sort(([left], [right]) => left.localeCompare(right))
      .map(([label, year]) => `${label}:${year}`)
      .join(', ')
    : 'n/a';
  return `mode ${mode}, timeline ${timelineMode}, variant ${variant}, seed ${seed}, requested historical start ${requestedStart}, resolved historical starts ${resolvedLabel}`;
}

function describeSimulationDelta(simulationDelta, candidateLabel = 'candidate') {
  const payload = simulationDelta && typeof simulationDelta === 'object' ? simulationDelta : {};
  const base = describeSimulationSummary(payload.base || {});
  const candidate = describeSimulationSummary(payload[candidateLabel] || {});
  const changed = Boolean(payload.changed);
  return `base: ${base} | ${candidateLabel}: ${candidate} | changed: ${changed ? 'yes' : 'no'}`;
}

function formatDiffOutput(diff) {
  const rows = Array.isArray(diff?.scenario_deltas) ? diff.scenario_deltas : [];
  const lines = [`Plan: ${diff?.plan_id || '-'}`, `Current Portfolio: ${fmtCurrency(diff?.current_portfolio_value_usd)}`, '', 'Scenario Delta (Candidate - Base):'];
  if (!rows.length) lines.push('- No deltas.');
  else for (const r of rows) lines.push(`- ${r.label}: Future ${fmtCurrency(r.delta_future_value_usd)}, Real ${fmtCurrency(r.delta_real_value_usd)}`);

  const baseAssumptionSet = diff?.base_assumption_set || extractAssumptionSetSummary(diff?.base_result);
  const candidateAssumptionSet = diff?.candidate_assumption_set || extractAssumptionSetSummary(diff?.candidate_result);
  lines.push('', 'Assumption Set Context:');
  if (!baseAssumptionSet && !candidateAssumptionSet) {
    lines.push('- Not available.');
  } else {
    lines.push(`- Base: ${describeAssumptionSetSummary(baseAssumptionSet)}`);
    lines.push(`- Candidate: ${describeAssumptionSetSummary(candidateAssumptionSet)}`);
  }

  const baseHousehold = extractHouseholdContextFromResult(diff?.base_result);
  const candidateHousehold = extractHouseholdContextFromResult(diff?.candidate_result);
  lines.push('', 'Household Context:');
  lines.push(`- Base: ${describeHouseholdContext(baseHousehold)}`);
  lines.push(`- Candidate: ${describeHouseholdContext(candidateHousehold)}`);

  const baseIncome = diff?.base_result?.income_projection;
  const candidateIncome = diff?.candidate_result?.income_projection;
  lines.push('', 'Income Projection Context:');
  if (!baseIncome && !candidateIncome) {
    lines.push('- Not available.');
  } else {
    lines.push(`- Base: ${describeIncomeProjection(baseIncome)}`);
    lines.push(`- Candidate: ${describeIncomeProjection(candidateIncome)}`);
  }

  const baseExpenses = diff?.base_result?.expense_projection;
  const candidateExpenses = diff?.candidate_result?.expense_projection;
  lines.push('', 'Expense Projection Context:');
  if (!baseExpenses && !candidateExpenses) {
    lines.push('- Not available.');
  } else {
    lines.push(`- Base: ${describeExpenseProjection(baseExpenses)}`);
    lines.push(`- Candidate: ${describeExpenseProjection(candidateExpenses)}`);
  }

  const baseDebt = diff?.base_result?.debt_projection;
  const candidateDebt = diff?.candidate_result?.debt_projection;
  lines.push('', 'Debt Projection Context:');
  if (!baseDebt && !candidateDebt) {
    lines.push('- Not available.');
  } else {
    lines.push(`- Base: ${describeDebtProjection(baseDebt)}`);
    lines.push(`- Candidate: ${describeDebtProjection(candidateDebt)}`);
  }

  const baseTimeline = diff?.base_result?.timeline_projection;
  const candidateTimeline = diff?.candidate_result?.timeline_projection;
  lines.push('', 'Timeline Impact Context:');
  if (!baseTimeline && !candidateTimeline) {
    lines.push('- Not available.');
  } else {
    lines.push(`- Base: ${describeTimelineProjection(baseTimeline)}`);
    lines.push(`- Candidate: ${describeTimelineProjection(candidateTimeline)}`);
  }

  const baseSocialSecurity = diff?.base_result?.social_security_projection;
  const candidateSocialSecurity = diff?.candidate_result?.social_security_projection;
  lines.push('', 'Social Security Context:');
  if (!baseSocialSecurity && !candidateSocialSecurity) {
    lines.push('- Not available.');
  } else {
    lines.push(`- Base: ${describeSocialSecurityProjection(baseSocialSecurity)}`);
    lines.push(`- Candidate: ${describeSocialSecurityProjection(candidateSocialSecurity)}`);
  }

  const baseRmd = diff?.base_result?.rmd_projection;
  const candidateRmd = diff?.candidate_result?.rmd_projection;
  lines.push('', 'RMD Context:');
  if (!baseRmd && !candidateRmd) {
    lines.push('- Not available.');
  } else {
    lines.push(`- Base: ${describeRmdProjection(baseRmd)}`);
    lines.push(`- Candidate: ${describeRmdProjection(candidateRmd)}`);
  }

  const mc = diff?.monte_carlo_delta || {};
  lines.push('', 'Monte Carlo Delta:', `- P10: ${fmtCurrency(mc.delta_p10_future_value_usd)}`, `- P50: ${fmtCurrency(mc.delta_p50_future_value_usd)}`, `- P90: ${fmtCurrency(mc.delta_p90_future_value_usd)}`);
  lines.push('', 'Simulation Context:', `- Base: ${describeSimulationSummary(extractSimulationSummaryFromResult(diff?.base_result))}`);
  lines.push(`- Candidate: ${describeSimulationSummary(extractSimulationSummaryFromResult(diff?.candidate_result))}`);
  lines.push('', 'Simulation Delta:', `- ${describeSimulationDelta(diff?.simulation_delta, 'candidate')}`);
  lines.push('', 'Raw Payload:', JSON.stringify(diff, null, 2));
  return lines.join('\n');
}

function parseWithdrawalStrategyInput(rawValue) {
  const text = String(rawValue || '').trim();
  if (!text) return [...DEFAULT_WITHDRAWAL_STRATEGIES];
  const parts = text
    .split(/[\n,]+/)
    .map(item => item.trim())
    .filter(Boolean);
  if (!parts.length) return [...DEFAULT_WITHDRAWAL_STRATEGIES];
  const seen = new Set();
  const strategies = [];
  for (const item of parts) {
    if (seen.has(item)) continue;
    seen.add(item);
    strategies.push(item);
  }
  return strategies;
}

function parseResearchBridgeSymbols(rawValue) {
  const tokens = String(rawValue || '')
    .split(',')
    .map((item) => item.trim().toUpperCase())
    .filter(Boolean);
  const unique = [];
  for (const token of tokens) {
    if (!/^[A-Z0-9._-]{1,24}$/.test(token)) continue;
    if (unique.includes(token)) continue;
    unique.push(token);
    if (unique.length >= 20) break;
  }
  return unique;
}

function formatWithdrawalStrategyCompareOutput(result) {
  const comparisons = Array.isArray(result?.comparisons) ? result.comparisons : [];
  const best = result?.best_strategy_by_metric && typeof result.best_strategy_by_metric === 'object'
    ? result.best_strategy_by_metric
    : {};
  const warnings = Array.isArray(result?.warnings) ? result.warnings : [];
  const assumptionSet = result?.assumption_set && typeof result.assumption_set === 'object' ? result.assumption_set : null;

  const lines = [
    `Plan: ${result?.plan_id || '-'}`,
    `Current Portfolio: ${fmtCurrency(result?.current_portfolio_value_usd)}`,
    `Assumption Set: ${describeAssumptionSetSummary(assumptionSet)}`,
    '',
    'Best Strategy By Metric:',
    `- Future value: ${best.future_value || 'n/a'}`,
    `- Real value: ${best.real_value || 'n/a'}`,
    `- Monte Carlo P50: ${best.monte_carlo_p50 || 'n/a'}`,
    '',
    'Strategy Results:',
  ];

  if (!comparisons.length) {
    lines.push('- No strategy comparisons returned.');
  } else {
    for (const row of comparisons) {
      const strategy = String(row?.strategy || 'unknown');
      const engine = String(row?.engine || 'local');
      const status = String(row?.engine_status || 'ok');
      lines.push(
        `- ${strategy}: future ${fmtCurrency(row?.baseline_future_value_usd)}, real ${fmtCurrency(row?.baseline_real_value_usd)}, `
        + `terminal ${fmtCurrency(row?.terminal_balance_usd)} @ age ${row?.terminal_age ?? 'n/a'}`
      );
      lines.push(
        `  withdrawals ${fmtCurrency(row?.total_withdrawals_usd)}, taxes ${fmtCurrency(row?.total_taxes_usd)}, `
        + `RMDs ${fmtCurrency(row?.total_rmds_usd)}, Roth conv ${fmtCurrency(row?.total_roth_conversions_usd)}, `
        + `MC P50 ${fmtCurrency(row?.monte_carlo_p50_future_value_usd)}`
      );
      lines.push(
        `  simulation mode ${String(row?.simulation_mode || 'fixed')}, `
        + `variant ${String(row?.simulation_monte_carlo_variant || 'p50')}`
      );
      if (
        Number.isFinite(Number(row?.total_federal_taxes_usd))
        || Number.isFinite(Number(row?.total_state_taxes_usd))
        || Number.isFinite(Number(row?.total_irmaa_surcharges_usd))
      ) {
        lines.push(
          `  tax breakdown: federal ${fmtCurrency(row?.total_federal_taxes_usd)}, `
          + `state ${fmtCurrency(row?.total_state_taxes_usd)}, IRMAA ${fmtCurrency(row?.total_irmaa_surcharges_usd)}`
        );
      }
      lines.push(`  engine ${engine}/${status}${row?.fallback_method ? ` (fallback: ${row.fallback_method})` : ''}`);
      if (Array.isArray(row?.warnings) && row.warnings.length) {
        lines.push(`  warnings: ${row.warnings.join(' | ')}`);
      }
    }
  }

  if (warnings.length) {
    lines.push('', 'Warnings:');
    for (const warning of warnings) lines.push(`- ${warning}`);
  }

  if (result?.raw_results && typeof result.raw_results === 'object' && Object.keys(result.raw_results).length) {
    lines.push('', 'Raw Results:', JSON.stringify(result.raw_results, null, 2));
  }

  lines.push('', 'Raw Payload:', JSON.stringify(result, null, 2));
  return lines.join('\n');
}

function formatBranchOutput(branch) {
  const rows = Array.isArray(branch?.scenario_deltas) ? branch.scenario_deltas : [];
  const lines = [
    `Plan: ${branch?.plan_id || '-'}`,
    `Branch: ${branch?.branch_name || '-'}`,
    `Template: ${branch?.branch_template_name || branch?.branch_template_id || 'None'}`,
    `Current Portfolio: ${fmtCurrency(branch?.current_portfolio_value_usd)}`,
    '',
    'Scenario Delta (Branch - Base):',
  ];
  if (!rows.length) lines.push('- No deltas.');
  else for (const row of rows) lines.push(`- ${row.label}: Future ${fmtCurrency(row.delta_future_value_usd)}, Real ${fmtCurrency(row.delta_real_value_usd)}`);

  lines.push('', 'Assumption Set Context:', `- ${describeAssumptionSetSummary(branch?.assumption_set || extractAssumptionSetSummary(branch?.base_result))}`);
  lines.push('', 'Household Context:');
  lines.push(`- Base: ${describeHouseholdContext(extractHouseholdContextFromResult(branch?.base_result))}`);
  lines.push(`- Branch: ${describeHouseholdContext(extractHouseholdContextFromResult(branch?.branch_result))}`);

  const events = Array.isArray(branch?.branch_events) ? branch.branch_events : [];
  lines.push('', 'Branch Events:');
  if (!events.length) {
    lines.push('- None.');
  } else {
    for (const event of events) {
      const dateLabel = String(event?.date || '?');
      const label = String(event?.label || 'Branch Event');
      const eventType = String(event?.event_type || 'milestone');
      const impactType = String(event?.impact_type || 'expense');
      const recurrence = String(event?.recurring_frequency || 'one_time');
      const amount = fmtCurrency(event?.amount_usd);
      const endDate = String(event?.end_date || '').trim();
      const period = endDate ? `${dateLabel} -> ${endDate}` : dateLabel;
      lines.push(`- ${period}: ${label} (${eventType}, ${impactType}, ${recurrence}, ${amount})`);
    }
  }

  lines.push('', 'Timeline Impact Context:');
  lines.push(`- Base: ${describeTimelineProjection(branch?.base_result?.timeline_projection)}`);
  lines.push(`- Branch: ${describeTimelineProjection(branch?.branch_result?.timeline_projection)}`);

  const mc = branch?.monte_carlo_delta || {};
  lines.push('', 'Monte Carlo Delta:', `- P10: ${fmtCurrency(mc.delta_p10_future_value_usd)}`, `- P50: ${fmtCurrency(mc.delta_p50_future_value_usd)}`, `- P90: ${fmtCurrency(mc.delta_p90_future_value_usd)}`);
  lines.push('', 'Simulation Context:');
  lines.push(`- Base: ${describeSimulationSummary(extractSimulationSummaryFromResult(branch?.base_result))}`);
  lines.push(`- Branch: ${describeSimulationSummary(extractSimulationSummaryFromResult(branch?.branch_result))}`);
  lines.push('', 'Simulation Delta:', `- ${describeSimulationDelta(branch?.simulation_delta, 'branch')}`);
  lines.push('', 'Raw Payload:', JSON.stringify(branch, null, 2));
  return lines.join('\n');
}

function describeIncomeProjection(projection) {
  if (!projection || typeof projection !== 'object') return 'Not available';
  const firstYear = fmtCurrency(projection.first_year_gross_income_usd);
  const finalYear = fmtCurrency(projection.final_year_gross_income_usd);
  const years = Number(projection.years);
  const yearsLabel = Number.isFinite(years) && years > 0 ? `${Math.trunc(years)}y` : 'n/a';
  const growth = Number(projection.annualized_income_growth_rate);
  const growthLabel = Number.isFinite(growth) ? `${(growth * 100).toFixed(2)}%` : 'n/a';
  return `${firstYear} -> ${finalYear} (${yearsLabel}, annualized ${growthLabel})`;
}

function describeExpenseProjection(projection) {
  if (!projection || typeof projection !== 'object') return 'Not available';
  const firstYear = fmtCurrency(projection.first_year_expenses_usd);
  const finalYear = fmtCurrency(projection.final_year_expenses_usd);
  const years = Number(projection.years);
  const yearsLabel = Number.isFinite(years) && years > 0 ? `${Math.trunc(years)}y` : 'n/a';
  const growth = Number(projection.annualized_expense_growth_rate);
  const growthLabel = Number.isFinite(growth) ? `${(growth * 100).toFixed(2)}%` : 'n/a';
  return `${firstYear} -> ${finalYear} (${yearsLabel}, annualized ${growthLabel})`;
}

function describeDebtProjection(projection) {
  if (!projection || typeof projection !== 'object') return 'Not available';
  const selected = projection.selected_scenario || {};
  const strategy = String(projection.strategy || selected.strategy || 'minimum');
  const months = Number(selected.months_to_payoff);
  const remaining = fmtCurrency(selected.remaining_balance_usd);
  const interest = fmtCurrency(selected.total_interest_paid_usd);
  const paidOffLabel = selected.paid_off ? 'paid off' : `remaining ${remaining}`;
  const monthsLabel = Number.isFinite(months) && months > 0 ? `${Math.trunc(months)}m` : 'n/a';
  return `${strategy} (${monthsLabel}, ${paidOffLabel}, interest ${interest})`;
}

function describeTimelineProjection(projection) {
  if (!projection || typeof projection !== 'object') return 'Not available';
  const eventsCount = Number(projection.events_count);
  const years = Number(projection.years);
  const firstYearNet = fmtCurrency(projection.yearly_points?.[0]?.net_cashflow_impact_usd);
  const cumulative = fmtCurrency(projection.cumulative_net_cashflow_impact_usd);
  const eventsLabel = Number.isFinite(eventsCount) ? `${Math.trunc(eventsCount)} event(s)` : 'n/a events';
  const yearsLabel = Number.isFinite(years) ? `${Math.trunc(years)}y` : 'n/a';
  return `${eventsLabel}, first-year net ${firstYearNet}, cumulative net ${cumulative} (${yearsLabel})`;
}

function describeSocialSecurityProjection(projection) {
  if (!projection || typeof projection !== 'object') return 'Not available';
  const selectedAge = Number(projection.selected_claiming_age);
  const optimalAge = Number(projection.optimal_claiming_age);
  const annual = fmtCurrency(projection.selected_annual_benefit_usd);
  const fraMonthly = fmtCurrency(projection.fra_monthly_benefit_usd);
  const selectedAgeLabel = Number.isFinite(selectedAge) ? `age ${Math.trunc(selectedAge)}` : 'n/a';
  const optimalAgeLabel = Number.isFinite(optimalAge) ? `optimal ${Math.trunc(optimalAge)}` : 'optimal n/a';
  return `${selectedAgeLabel} (${optimalAgeLabel}), annual ${annual}, FRA monthly ${fraMonthly}`;
}

function describeRmdProjection(projection) {
  if (!projection || typeof projection !== 'object') return 'Not available';
  const startAge = Number(projection.rmd_start_age);
  const totalProjected = fmtCurrency(projection.total_projected_rmds_usd);
  const firstYear = fmtCurrency(projection.yearly_points?.[0]?.total_rmd_usd);
  const eligibleAccounts = Number(projection.eligible_account_count);
  const startAgeLabel = Number.isFinite(startAge) ? `start age ${Math.trunc(startAge)}` : 'start age n/a';
  const accountLabel = Number.isFinite(eligibleAccounts) ? `${Math.trunc(eligibleAccounts)} account(s)` : 'n/a account(s)';
  return `${startAgeLabel}, first-year ${firstYear}, projected total ${totalProjected}, ${accountLabel}`;
}

export function initEditor(refreshPlans) {
  byId('projection-source').addEventListener('change', () => renderProjectionVisuals());
  byId('projection-scenario-label').addEventListener('change', () => renderProjectionVisuals());
  byId('projection-account-metric').addEventListener('change', () => renderProjectionVisuals());
  byId('setting-simulation-mode').addEventListener('change', () => {
    updateSimulationModeDependentControls('setting', { clearIrrelevant: true });
  });
  byId('diff-simulation-mode').addEventListener('change', () => {
    updateSimulationModeDependentControls('diff', { clearIrrelevant: true });
  });
  byId('open-plan-recommendations').addEventListener('click', () => {
    location.hash = 'recommendations';
  });
  byId('generate-plan-closure-summary').addEventListener('click', async () => {
    if (!state.currentPlanId) { writeLog('Select a plan first.', null, true); return; }
    writeLog('Generating plan closure analytics artifact...');
    try {
      const result = await fetchJson(
        `/api/plans/${encodeURIComponent(state.currentPlanId)}/recommendation-closure-summary`,
        {
          method: 'POST',
          headers: { 'content-type': 'application/json' },
          body: JSON.stringify({
            limit: 200,
            statuses: ['applied', 'rejected'],
            include_pending_realized: true,
            write_artifact: true,
          }),
        },
      );
      state.planClosureSummary = result && typeof result === 'object' ? result : null;
      await refreshPlans();
      if (state.planClosureSummary && state.planClosureSummary.plan_id === state.currentPlanId) {
        renderPlanClosureSummary(state.planClosureSummary);
      }
      await loadPlanClosureTrend({ silent: true });
      writeLog(
        'Plan closure analytics artifact generated.',
        {
          plan_id: state.currentPlanId,
          artifact_id: result?.artifact?.id || null,
          closed_count: result?.analytics?.count || 0,
          measured_count: result?.analytics?.summary?.measured_count || 0,
        },
      );
    } catch (e) {
      writeLog(`Generate closure summary failed: ${e.message}`, null, true);
    }
  });
  byId('refresh-plan-closure-trend').addEventListener('click', async () => {
    if (!state.currentPlanId) {
      writeLog('Select a plan first.', null, true);
      return;
    }
    writeLog('Refreshing plan closure trend...');
    await loadPlanClosureTrend({ silent: false });
    if (state.planClosureTrend && state.planClosureTrend.plan_id === state.currentPlanId) {
      writeLog('Plan closure trend refreshed.', {
        plan_id: state.currentPlanId,
        closed_count: state.planClosureTrend.count || 0,
        measured_count: state.planClosureTrend.summary?.measured_count || 0,
      });
    }
  });
  byId('plan-timeline').addEventListener('change', () => {
    refreshTimelineBuilderFromEditor(false);
  });
  byId('plan-contribution-rules').addEventListener('change', () => {
    refreshContributionBuilderFromEditor(false);
  });
  byId('timeline-event-type').addEventListener('change', () => {
    const eventType = String(byId('timeline-event-type')?.value || 'milestone').trim().toLowerCase();
    const impactSelect = byId('timeline-event-impact-type');
    if (impactSelect && !impactSelect.value) {
      impactSelect.value = TIMELINE_DEFAULT_IMPACT_BY_EVENT[eventType] || 'portfolio';
    }
  });
  byId('add-timeline-event').addEventListener('click', () => {
    const date = dateInputValue(byId('timeline-event-date')?.value);
    const label = String(byId('timeline-event-label')?.value || '').trim();
    const eventTypeRaw = String(byId('timeline-event-type')?.value || 'milestone').trim().toLowerCase();
    const eventType = TIMELINE_EVENT_TYPES.has(eventTypeRaw) ? eventTypeRaw : 'milestone';
    const impactTypeRaw = String(byId('timeline-event-impact-type')?.value || '').trim().toLowerCase();
    const impactType = TIMELINE_IMPACT_TYPES.has(impactTypeRaw)
      ? impactTypeRaw
      : (TIMELINE_DEFAULT_IMPACT_BY_EVENT[eventType] || 'portfolio');
    const amountUsd = coerceOptionalNumber(byId('timeline-event-amount')?.value);
    const recurringRaw = String(byId('timeline-event-frequency')?.value || 'one_time').trim().toLowerCase();
    const recurringFrequency = TIMELINE_FREQUENCIES.has(recurringRaw) ? recurringRaw : 'one_time';
    const endDate = dateInputValue(byId('timeline-event-end-date')?.value);
    const accountId = String(byId('timeline-event-account-id')?.value || '').trim() || null;
    const notes = String(byId('timeline-event-notes')?.value || '').trim();

    if (!date) {
      writeLog('Timeline event date is required.', null, true);
      return;
    }
    if (!label) {
      writeLog('Timeline event label is required.', null, true);
      return;
    }
    if (amountUsd === null) {
      writeLog('Timeline event amount must be numeric.', null, true);
      return;
    }
    if (endDate && endDate < date) {
      writeLog('Timeline event end date must be on or after event date.', null, true);
      return;
    }

    const payload = readTimelinePayloadFromEditor();
    payload.events = Array.isArray(payload.events) ? payload.events : [];
    payload.events.push({
      id: makeEditorId('event'),
      date,
      label,
      event_type: eventType,
      impact_type: impactType,
      amount_usd: amountUsd,
      recurring_frequency: recurringFrequency,
      end_date: endDate || null,
      account_id: accountId,
      notes,
    });
    payload.events.sort((left, right) => String(left.date || '').localeCompare(String(right.date || '')));
    writeTimelinePayloadToEditor(payload);
    resetTimelineEventInputs();
  });
  [
    'timeline-retirement-age', 'timeline-withdrawal-strategy', 'timeline-drawdown-order', 'timeline-ss-birth-year', 'timeline-ss-claiming-age',
    'timeline-ss-life-expectancy-age', 'timeline-ss-fra-benefit', 'timeline-ss-annual-earnings',
    'timeline-rmd-birth-year', 'timeline-rmd-start-age',
  ].forEach((id) => {
    const input = byId(id);
    if (!input) return;
    input.addEventListener('change', () => {
      const payload = readTimelinePayloadFromEditor();
      payload.retirement = collectTimelineRetirementInputs();
      writeTimelinePayloadToEditor(payload);
    });
  });
  byId('contribution-rule-amount-type').addEventListener('change', () => {
    updateContributionRuleAmountField();
  });
  byId('add-contribution-rule').addEventListener('click', () => {
    const accountId = String(byId('contribution-rule-account-id')?.value || '').trim();
    if (!accountId) {
      writeLog('Contribution rule account ID is required.', null, true);
      return;
    }

    const payload = readContributionRulesPayloadFromEditor();
    const rankInput = coerceOptionalInteger(byId('contribution-rule-rank')?.value);
    const nextRank = rankInput === null
      ? ((payload.rules || []).reduce((maxRank, item) => Math.max(maxRank, Number(item.rank || 0)), 0) + 1)
      : Math.max(1, rankInput);
    const amountTypeRaw = String(byId('contribution-rule-amount-type')?.value || 'unlimited').trim();
    const amountType = CONTRIBUTION_AMOUNT_TYPES.has(amountTypeRaw) ? amountTypeRaw : 'unlimited';
    const amountValue = coerceOptionalNumber(byId('contribution-rule-amount-value')?.value);
    const employerMatch = coerceOptionalNumber(byId('contribution-rule-employer-match')?.value);
    const maxBalance = coerceOptionalNumber(byId('contribution-rule-max-balance')?.value);

    if (amountType !== 'unlimited' && amountValue === null) {
      writeLog('Contribution amount value is required for the selected amount type.', null, true);
      return;
    }
    if (amountType === 'percentRemaining' && (Number(amountValue) < 0 || Number(amountValue) > 100)) {
      writeLog('Percent Remaining must be between 0 and 100.', null, true);
      return;
    }

    const amount = { type: amountType };
    if (amountType === 'dollarAmount') amount.dollarAmount = Math.max(0, Number(amountValue || 0));
    if (amountType === 'percentRemaining') amount.percentRemaining = Math.max(0, Math.min(100, Number(amountValue || 0)));

    const rule = {
      id: makeEditorId('rule'),
      accountId,
      rank: nextRank,
      amount,
    };
    if (employerMatch !== null) rule.employerMatch = Math.max(0, employerMatch);
    if (maxBalance !== null) rule.maxBalance = Math.max(0, maxBalance);
    if (byId('contribution-rule-mega-backdoor')?.checked) rule.enableMegaBackdoorRoth = true;
    if (byId('contribution-rule-disabled')?.checked) rule.disabled = true;

    payload.rules = Array.isArray(payload.rules) ? payload.rules : [];
    payload.rules.push(rule);
    writeContributionRulesPayloadToEditor(payload);
    resetContributionRuleInputs();
  });
  ['contribution-base-rule', 'contribution-profile-id', 'contribution-employer-match-target', 'contribution-age'].forEach((id) => {
    const input = byId(id);
    if (!input) return;
    input.addEventListener('change', () => {
      const payload = readContributionRulesPayloadFromEditor();
      writeContributionRulesPayloadToEditor(payload);
    });
  });
  resetTimelineEventInputs();
  resetContributionRuleInputs();
  byId('refresh-projection-profile').addEventListener('click', () => {
    maybeLoadProjectionProfile(true);
    renderProjectionVisuals();
  });
  byId('branch-template-id').addEventListener('change', () => {
    const selected = selectedBranchTemplateFromEditor();
    if (selected) writeLog(`Selected branch template: ${selected.name}`, { id: selected.id });
  });
  byId('load-branch-template').addEventListener('click', () => {
    const selected = selectedBranchTemplateFromEditor();
    if (!selected) {
      writeLog('Select a branch template first.', null, true);
      return;
    }
    if (applyBranchTemplateToEditor(selected)) {
      writeLog(`Loaded branch template ${selected.id}.`);
    }
  });

  byId('pin-watchlist-branch-template').addEventListener('click', async () => {
    if (!state.currentPlanId) {
      writeLog('Select a plan first.', null, true);
      return;
    }

    const branchTemplateId = String(byId('branch-template-id')?.value || '').trim();
    const assumptionSetId = String(byId('branch-assumption-set-id')?.value || '').trim();
    const branchName = String(byId('scenario-branch-name')?.value || '').trim();
    const symbols = parseResearchBridgeSymbols(byId('research-bridge-symbols')?.value);
    const payload = {};
    if (branchTemplateId) payload.branch_template_id = branchTemplateId;
    if (assumptionSetId) payload.assumption_set_id = assumptionSetId;
    if (branchName) payload.branch_name = branchName;
    if (symbols.length) payload.symbols = symbols;

    writeLog('Pinning watchlist research into branch template...', payload);
    try {
      const result = await fetchJson(`/api/plans/${encodeURIComponent(state.currentPlanId)}/branch-templates/pin-watchlist`, {
        method: 'POST',
        headers: { 'content-type': 'application/json' },
        body: JSON.stringify(payload),
      });
      const templatesPayload = result?.branch_templates || {};
      byId('plan-branch-templates').value = JSON.stringify(templatesPayload, null, 2);
      const templateId = String(result?.template_id || '');
      setBranchTemplateOptions(templatesPayload, templateId);
      const selected = selectedBranchTemplateFromEditor();
      if (selected) applyBranchTemplateToEditor(selected);
      state.currentPlanDetail = await fetchJson(`/api/plans/${encodeURIComponent(state.currentPlanId)}`);
      await refreshPlans();
      const pinnedSymbols = Array.isArray(result?.pinned_symbols) ? result.pinned_symbols : [];
      const bridgeSummaryEl = byId('research-bridge-summary');
      if (bridgeSummaryEl) {
        const parts = [];
        if (result?.decision_summary) parts.push(String(result.decision_summary));
        if (result?.pinned_at) parts.push(`logged ${fmtDate(result.pinned_at)}`);
        if (result?.artifact_title) parts.push(`artifact: ${result.artifact_title}`);
        bridgeSummaryEl.textContent = parts.length
          ? parts.join(' • ')
          : 'No watchlist research bridge activity recorded yet.';
      }
      setResearchBridgeArtifactAction(result?.artifact_id || '', result?.artifact_title || '');
      writeLog(
        `Pinned ${pinnedSymbols.length} watchlist symbol(s) into template ${templateId || '(unknown)'}.`,
        {
          pinned_symbols: pinnedSymbols,
          decision_summary: result?.decision_summary || null,
          artifact_id: result?.artifact_id || null,
        },
      );
    } catch (e) {
      writeLog(`Research bridge pin failed: ${e.message}`, null, true);
    }
  });

  byId('open-latest-research-bridge-artifact').addEventListener('click', async () => {
    if (!state.currentPlanId) {
      writeLog('Select a plan first.', null, true);
      return;
    }
    const artifactId = String(byId('open-latest-research-bridge-artifact')?.dataset?.artifactId || '').trim();
    if (!artifactId) {
      writeLog('No research bridge artifact is available yet.', null, true);
      return;
    }
    try {
      await loadArtifact(artifactId);
      writeLog('Opened latest research bridge artifact.', { artifact_id: artifactId });
    } catch (e) {
      writeLog(`Research bridge artifact load failed: ${e.message}`, null, true);
    }
  });

  byId('save-plan-branch-templates').addEventListener('click', async () => {
    if (!state.currentPlanId) { writeLog('Select a plan first.', null, true); return; }
    const raw = String(byId('plan-branch-templates')?.value || '').trim();
    let payload;
    try {
      payload = raw ? JSON.parse(raw) : {};
    } catch (e) {
      writeLog(`Branch templates JSON is invalid: ${e.message}`, null, true);
      return;
    }
    writeLog('Saving branch templates...', payload);
    try {
      const result = await fetchJson(`/api/plans/${encodeURIComponent(state.currentPlanId)}/branch-templates`, {
        method: 'PUT',
        headers: { 'content-type': 'application/json' },
        body: JSON.stringify(payload),
      });
      byId('plan-branch-templates').value = JSON.stringify(result, null, 2);
      setBranchTemplateOptions(result);
      state.currentPlanDetail = await fetchJson(`/api/plans/${encodeURIComponent(state.currentPlanId)}`);
      await refreshPlans();
      writeLog('Branch templates saved.');
    } catch (e) {
      writeLog(`Save branch templates failed: ${e.message}`, null, true);
    }
  });

  byId('save-plan').addEventListener('click', async () => {
    if (!state.currentPlanId) { writeLog('Select a plan first.', null, true); return; }
    writeLog(`Saving plan ${state.currentPlanId}...`);
    try {
      state.currentPlanDetail = await fetchJson(`/api/plans/${encodeURIComponent(state.currentPlanId)}`, { method: 'PUT', headers: { 'content-type': 'application/json' }, body: JSON.stringify({ plan_markdown: byId('plan-markdown').value, tasks_markdown: byId('plan-tasks').value }) });
      await refreshPlans(); renderDetail(); writeLog('Plan saved.');
    } catch (e) { writeLog(`Save failed: ${e.message}`, null, true); }
  });

  byId('save-plan-timeline').addEventListener('click', async () => {
    if (!state.currentPlanId) { writeLog('Select a plan first.', null, true); return; }
    let payload;
    try {
      payload = normalizeTimelinePayload(parseObjectJsonFromEditor('plan-timeline', 'Timeline'));
      payload.retirement = collectTimelineRetirementInputs();
    } catch (e) {
      writeLog(e.message, null, true);
      return;
    }
    writeTimelinePayloadToEditor(payload);
    writeLog('Saving timeline...', payload);
    try {
      await fetchJson(`/api/plans/${encodeURIComponent(state.currentPlanId)}/timeline`, {
        method: 'PUT',
        headers: { 'content-type': 'application/json' },
        body: JSON.stringify(payload),
      });
      state.currentPlanDetail = await fetchJson(`/api/plans/${encodeURIComponent(state.currentPlanId)}`);
      renderDetail();
      await refreshPlans();
      writeLog('Timeline saved.');
    } catch (e) {
      writeLog(`Save timeline failed: ${e.message}`, null, true);
    }
  });

  byId('save-plan-assumption-sets').addEventListener('click', async () => {
    if (!state.currentPlanId) { writeLog('Select a plan first.', null, true); return; }
    const raw = byId('plan-assumption-sets').value.trim();
    let payload;
    try {
      payload = raw ? JSON.parse(raw) : {};
    } catch (e) {
      writeLog(`Assumption sets JSON is invalid: ${e.message}`, null, true);
      return;
    }
    writeLog('Saving assumption sets...', payload);
    try {
      await fetchJson(`/api/plans/${encodeURIComponent(state.currentPlanId)}/assumption-sets`, {
        method: 'PUT',
        headers: { 'content-type': 'application/json' },
        body: JSON.stringify(payload),
      });
      state.currentPlanDetail = await fetchJson(`/api/plans/${encodeURIComponent(state.currentPlanId)}`);
      renderDetail();
      await refreshPlans();
      writeLog('Assumption sets saved.');
    } catch (e) {
      writeLog(`Save assumption sets failed: ${e.message}`, null, true);
    }
  });

  byId('save-plan-contribution-rules').addEventListener('click', async () => {
    if (!state.currentPlanId) { writeLog('Select a plan first.', null, true); return; }
    let payload;
    try {
      payload = normalizeContributionRulesPayload(parseObjectJsonFromEditor('plan-contribution-rules', 'Contribution rules'));
      const meta = collectContributionRuleMetaInputs();
      payload.base_rule = meta.base_rule;
      payload.profile_id = meta.profile_id;
      payload.employer_match_target_usd = meta.employer_match_target_usd === null ? 6000 : Math.max(0, meta.employer_match_target_usd);
      payload.age = meta.age === null ? 35 : Math.max(0, Math.min(120, meta.age));
    } catch (e) {
      writeLog(e.message, null, true);
      return;
    }
    writeContributionRulesPayloadToEditor(payload);
    writeLog('Saving contribution rules...', payload);
    try {
      await fetchJson(`/api/plans/${encodeURIComponent(state.currentPlanId)}/contribution-rules`, {
        method: 'PUT',
        headers: { 'content-type': 'application/json' },
        body: JSON.stringify(payload),
      });
      state.currentPlanDetail = await fetchJson(`/api/plans/${encodeURIComponent(state.currentPlanId)}`);
      renderDetail();
      await refreshPlans();
      writeLog('Contribution rules saved.');
    } catch (e) {
      writeLog(`Save contribution rules failed: ${e.message}`, null, true);
    }
  });

  byId('save-plan-settings').addEventListener('click', async () => {
    if (!state.currentPlanId) { writeLog('Select a plan first.', null, true); return; }
    let payload;
    try {
      payload = {
        ...collectPlanSettingsPayload(PLAN_SETTING_VALUE_FIELDS, { includeNulls: true }),
      };
    } catch (e) {
      writeLog(e.message, null, true); return;
    }
    writeLog(`Saving settings...`, payload);
    try {
      state.currentPlanDetail = await fetchJson(`/api/plans/${encodeURIComponent(state.currentPlanId)}/settings`, { method: 'PATCH', headers: { 'content-type': 'application/json' }, body: JSON.stringify(payload) });
      renderDetail(); await refreshPlans(); writeLog('Settings saved.');
    } catch (e) { writeLog(`Save settings failed: ${e.message}`, null, true); }
  });

  byId('run-scenario-diff').addEventListener('click', async () => {
    if (!state.currentPlanId) { writeLog('Select a plan first.', null, true); return; }
    let compare;
    try {
      compare = {
        ...collectPlanSettingsPayload(DIFF_SETTING_VALUE_FIELDS, { includeNulls: false }),
      };
    } catch (e) {
      writeLog(e.message, null, true); return;
    }
    const assumptionSetId = String(byId('diff-assumption-set-id')?.value || '').trim();
    const candidateAssumptionSetId = String(byId('diff-candidate-assumption-set-id')?.value || '').trim();
    const payload = { compare_settings: compare };
    if (assumptionSetId) payload.assumption_set_id = assumptionSetId;
    if (candidateAssumptionSetId) payload.candidate_assumption_set_id = candidateAssumptionSetId;
    writeLog('Running scenario diff...', payload);
    try {
      const result = await fetchJson(`/api/plans/${encodeURIComponent(state.currentPlanId)}/scenario-diff`, { method: 'POST', headers: { 'content-type': 'application/json' }, body: JSON.stringify(payload) });
      const bl = (result.scenario_deltas || []).find(r => r.label === 'baseline');
      const householdSummary = summarizeHouseholdTransition(
        extractHouseholdContextFromResult(result?.base_result),
        extractHouseholdContextFromResult(result?.candidate_result),
      );
      byId('scenario-diff-summary').textContent = bl
        ? `Baseline delta: ${fmtCurrency(bl.delta_future_value_usd)} (real: ${fmtCurrency(bl.delta_real_value_usd)})${householdSummary ? ` • ${householdSummary}` : ''}`
        : (householdSummary ? `Diff completed • ${householdSummary}` : 'Diff completed.');
      byId('scenario-diff-output').value = formatDiffOutput(result);
      projectionState.diffResult = result;
      setProjectionSourceOptions('diff_base');
      renderProjectionVisuals();
      writeLog('Scenario diff completed.');
    } catch (e) { writeLog(`Diff failed: ${e.message}`, null, true); byId('scenario-diff-summary').textContent = `Failed: ${e.message}`; }
  });

  byId('run-withdrawal-strategy-compare').addEventListener('click', async () => {
    if (!state.currentPlanId) { writeLog('Select a plan first.', null, true); return; }
    const assumptionSetId = String(byId('withdrawal-assumption-set-id')?.value || '').trim();
    const currentPortfolioValueRaw = String(byId('withdrawal-current-portfolio-value')?.value || '').trim();
    const includeRawResults = !!byId('withdrawal-include-raw-results')?.checked;
    const strategies = parseWithdrawalStrategyInput(byId('withdrawal-strategies')?.value);
    if (!strategies.length) {
      writeLog('Provide at least one withdrawal strategy.', null, true);
      return;
    }

    const payload = { strategies, include_raw_results: includeRawResults };
    if (assumptionSetId) payload.assumption_set_id = assumptionSetId;
    if (currentPortfolioValueRaw) {
      const currentPortfolioValue = Number(currentPortfolioValueRaw);
      if (!Number.isFinite(currentPortfolioValue) || currentPortfolioValue < 0) {
        writeLog('Portfolio value override must be a non-negative number.', null, true);
        return;
      }
      payload.current_portfolio_value_usd = currentPortfolioValue;
    }

    writeLog('Running withdrawal strategy comparison...', payload);
    try {
      const result = await fetchJson(`/api/plans/${encodeURIComponent(state.currentPlanId)}/withdrawal-strategy-compare`, {
        method: 'POST',
        headers: { 'content-type': 'application/json' },
        body: JSON.stringify(payload),
      });
      const best = result?.best_strategy_by_metric || {};
      byId('withdrawal-strategy-compare-summary').textContent = `Best future value: ${best.future_value || 'n/a'} • Best real value: ${best.real_value || 'n/a'} • Best MC P50: ${best.monte_carlo_p50 || 'n/a'}`;
      byId('withdrawal-strategy-compare-output').value = formatWithdrawalStrategyCompareOutput(result);
      writeLog('Withdrawal strategy comparison completed.');
    } catch (e) {
      writeLog(`Withdrawal strategy comparison failed: ${e.message}`, null, true);
      byId('withdrawal-strategy-compare-summary').textContent = `Failed: ${e.message}`;
    }
  });

  byId('run-scenario-branch').addEventListener('click', async () => {
    if (!state.currentPlanId) { writeLog('Select a plan first.', null, true); return; }

    const branchName = String(byId('scenario-branch-name')?.value || '').trim() || 'What-If Branch';
    const assumptionSetId = String(byId('branch-assumption-set-id')?.value || '').trim();
    const branchTemplateId = String(byId('branch-template-id')?.value || '').trim();
    const branchEventsRaw = String(byId('scenario-branch-events')?.value || '').trim();

    let branchEvents = [];
    if (branchEventsRaw) {
      try {
        branchEvents = JSON.parse(branchEventsRaw);
      } catch (e) {
        writeLog(`Branch events JSON is invalid: ${e.message}`, null, true);
        return;
      }
      if (!Array.isArray(branchEvents)) {
        writeLog('Branch events JSON must be an array.', null, true);
        return;
      }
    }

    let compareSettings = {};
    try {
      compareSettings = {
        ...collectPlanSettingsPayload(DIFF_SETTING_VALUE_FIELDS, { includeNulls: false }),
      };
    } catch (e) {
      writeLog(e.message, null, true);
      return;
    }

    if (!branchTemplateId && !branchEvents.length && !Object.keys(compareSettings).length) {
      writeLog('Provide a branch template, at least one branch event, or at least one override field.', null, true);
      return;
    }

    const payload = {
      branch_name: branchName,
      branch_events: branchEvents,
    };
    if (assumptionSetId) payload.assumption_set_id = assumptionSetId;
    if (branchTemplateId) payload.branch_template_id = branchTemplateId;
    if (Object.keys(compareSettings).length) payload.compare_settings = compareSettings;

    writeLog('Running scenario branch...', payload);
    try {
      const result = await fetchJson(`/api/plans/${encodeURIComponent(state.currentPlanId)}/scenario-branch`, { method: 'POST', headers: { 'content-type': 'application/json' }, body: JSON.stringify(payload) });
      const bl = (result.scenario_deltas || []).find(r => r.label === 'baseline');
      const householdSummary = summarizeHouseholdTransition(
        extractHouseholdContextFromResult(result?.base_result),
        extractHouseholdContextFromResult(result?.branch_result),
      );
      byId('scenario-branch-summary').textContent = bl
        ? `Baseline delta: ${fmtCurrency(bl.delta_future_value_usd)} (real: ${fmtCurrency(bl.delta_real_value_usd)})${householdSummary ? ` • ${householdSummary}` : ''}`
        : (householdSummary ? `Branch completed • ${householdSummary}` : 'Branch completed.');
      if (result?.branch_template_id) setBranchTemplateOptions(String(byId('plan-branch-templates')?.value || ''), String(result.branch_template_id));
      byId('scenario-branch-output').value = formatBranchOutput(result);
      projectionState.branchResult = result;
      setProjectionSourceOptions('branch_branch');
      renderProjectionVisuals();
      writeLog('Scenario branch completed.');
    } catch (e) {
      writeLog(`Branch failed: ${e.message}`, null, true);
      byId('scenario-branch-summary').textContent = `Failed: ${e.message}`;
    }
  });

  byId('apply-scenario-overrides').addEventListener('click', async () => {
    if (!state.currentPlanId) { writeLog('Select a plan first.', null, true); return; }
    let payload;
    try {
      payload = {
        ...collectPlanSettingsPayload(DIFF_SETTING_VALUE_FIELDS, { includeNulls: false }),
      };
    } catch (e) { writeLog(e.message, null, true); return; }
    if (!Object.keys(payload).length) { writeLog('Enter at least one override.', null, true); return; }
    writeLog(`Applying overrides...`, payload);
    try {
      state.currentPlanDetail = await fetchJson(`/api/plans/${encodeURIComponent(state.currentPlanId)}/settings`, { method: 'PATCH', headers: { 'content-type': 'application/json' }, body: JSON.stringify(payload) });
      renderDetail(); setPlanSettingsInputs(DIFF_SETTING_VALUE_FIELDS, {});
      byId('scenario-diff-summary').textContent = 'Overrides applied to plan settings.';
      await refreshPlans(); writeLog('Overrides applied.');
    } catch (e) { writeLog(`Apply failed: ${e.message}`, null, true); }
  });

  byId('activate-plan').addEventListener('click', async () => {
    if (!state.currentPlanId) { writeLog('Select a plan first.', null, true); return; }
    try {
      const s = await fetchJson(`/api/plans/${encodeURIComponent(state.currentPlanId)}/activate`, { method: 'POST' });
      await refreshPlans(); writeLog('Plan activated.', { id: s.id });
    } catch (e) { writeLog(`Activate failed: ${e.message}`, null, true); }
  });

  byId('refresh-plan-context').addEventListener('click', async () => {
    if (!state.currentPlanId) { writeLog('Select a plan first.', null, true); return; }
    try {
      state.currentPlanDetail = await fetchJson(`/api/plans/${encodeURIComponent(state.currentPlanId)}/refresh-context`, { method: 'POST' });
      renderDetail(); await refreshPlans(); writeLog('Context refreshed.');
    } catch (e) { writeLog(`Refresh failed: ${e.message}`, null, true); }
  });

  byId('add-decision').addEventListener('click', async () => {
    if (!state.currentPlanId) { writeLog('Select a plan first.', null, true); return; }
    const sumEl = byId('decision-summary');
    const ratEl = byId('decision-rationale');
    const summary = sumEl.value.trim();
    if (!summary) { writeLog('Decision summary required.', null, true); return; }
    try {
      state.currentPlanDetail = await fetchJson(`/api/plans/${encodeURIComponent(state.currentPlanId)}/decisions`, { method: 'POST', headers: { 'content-type': 'application/json' }, body: JSON.stringify({ summary, rationale: ratEl.value.trim(), status: byId('decision-status').value.trim() || 'proposed' }) });
      sumEl.value = ''; ratEl.value = '';
      renderDetail(); await refreshPlans(); writeLog('Decision added.');
    } catch (e) { writeLog(`Add decision failed: ${e.message}`, null, true); }
  });
  updateSimulationModeDependentControls('setting', { clearIrrelevant: false });
  updateSimulationModeDependentControls('diff', { clearIrrelevant: false });
}
