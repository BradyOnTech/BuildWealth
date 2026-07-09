// COPILOT — chat masthead, thread, sticky composer.
// One conversation visible at a time. Past conversations live behind a picker.
// Plan scope sets which plan's context is used. Composer auto-grows; ⌘↵ to send.

import { api } from '../lib/api.js';
import { state } from '../lib/state.js';
import { html, raw, esc, $, delegate } from '../lib/dom.js';
import { renderThread } from './copilot/thread.js';
import { renderComposer, attachComposerBehavior } from './copilot/composer.js';
import { fmtRelative } from '../lib/format.js';

export const meta = {
  id: 'copilot',
  label: 'Copilot',
  numeral: 'VI',
  group: 'primary',
};

const SUGGESTIONS = [
  'What should I do this week?',
  'Am I on track with my retirement plan?',
  'What if I increased my contribution to $2,000 a month?',
  'Compare AAPL and MSFT for a $10,000 add.',
  'Can I afford a $450,000 house given my plan?',
];

const PROFILE_SETUP_PROMPT = [
  'Help me fill out my financial profile.',
  'First call get_onboarding_status and get_financial_profile.',
  'Ask me one focused question at a time for missing income, expenses, debt, goals, tax basics, and physical assets.',
  'When you have enough information, call draft_financial_profile_update so I can review the changes.',
  'do not save anything with update_financial_profile until I explicitly confirm the draft.',
].join(' ');

const GOAL_SETUP_PROMPT = [
  'Help me add financial goals to my financial profile.',
  'First call get_onboarding_status and get_financial_profile.',
  'Focus only on missing goal_items for now.',
  'Ask me one focused question at a time for each goal label, target_amount_usd, target_date, priority, and any useful notes.',
  'When you have enough information, call draft_financial_profile_update with goal_items so I can review the changes.',
  'do not save anything with update_financial_profile until I explicitly confirm the draft.',
].join(' ');

const DEBT_SETUP_PROMPT = [
  'Help me review debt for my financial profile.',
  'First call get_onboarding_status and get_financial_profile.',
  'Focus only on missing debt_items or flags.no_debt for now.',
  'Ask me one focused question at a time for each debt label, balance_usd, interest_rate, minimum_monthly_payment_usd, and payoff priority when relevant.',
  'If I have no current debt, call draft_financial_profile_update with flags.no_debt set to true instead of creating debt_items.',
  'When you have enough information, call draft_financial_profile_update with debt_items or flags.no_debt so I can review the changes.',
  'do not save anything with update_financial_profile until I explicitly confirm the draft.',
].join(' ');

const PHYSICAL_ASSET_SETUP_PROMPT = [
  'Help me add physical assets to my financial profile.',
  'First call get_onboarding_status and get_financial_profile.',
  'Focus only on missing physical_assets for now.',
  'Ask me one focused question at a time for each asset label, current_value_usd, asset_type, purchase_date, and annual_growth_rate when known.',
  'When you have enough information, call draft_financial_profile_update with physical_assets so I can review the changes.',
  'do not save anything with update_financial_profile until I explicitly confirm the draft.',
].join(' ');

const TAX_SETUP_PROMPT = [
  'Help me add tax basics to my financial profile.',
  'First call get_onboarding_status and get_financial_profile.',
  'Focus only on missing tax_profile fields for now.',
  'Ask me one focused question at a time for filing_status, marginal_tax_rate, and state.',
  'When you have enough information, call draft_financial_profile_update with tax_profile so I can review the changes.',
  'do not save anything with update_financial_profile until I explicitly confirm the draft.',
].join(' ');

const INVESTMENT_POLICY_SETUP_PROMPT = [
  'Help me define my personal investment policy.',
  'First call get_onboarding_status and get_financial_profile.',
  'Focus only on missing or weak investment_policy fields for now.',
  'Ask me one focused question at a time for max_single_symbol_exposure_pct, max_sector_exposure_pct, minimum_research_confidence, minimum_cash_runway_months, max_asset_class_exposure_pct, simplicity_preference, tax_sensitivity, risk_tolerance, preferred_account_locations, restricted_symbols, and restricted_sectors.',
  'Frame this as investment-fit guardrails, not buy/sell advice.',
  'When you have enough information, call draft_financial_profile_update with investment_policy so I can review the changes.',
  'do not save anything with update_financial_profile until I explicitly confirm the draft.',
].join(' ');

const CHART_DESCRIPTIONS = {
  'trajectory-fan': 'the Monte Carlo trajectory fan (10th–90th percentile bands, the median line, and the retirement / coast-FI markers)',
  'failure-histogram': 'the failure-year histogram (share of simulated paths first running short, by year)',
  'strategy-balances': 'the withdrawal strategy balance trajectories (one line per strategy)',
  'strategy-taxes': 'the annual taxes by withdrawal strategy chart',
};

export function buildPlanReviewPrompt(intent, { planId = '', chart = '' } = {}) {
  const normalizedIntent = String(intent || '').trim().toLowerCase();
  const id = String(planId || '').trim();
  const planPhrase = id ? `plan ${id}` : 'the active plan';
  if (normalizedIntent === 'explain-chart') {
    const chartPhrase = CHART_DESCRIPTIONS[String(chart || '').trim().toLowerCase()]
      || 'the chart I am looking at';
    return [
      `Explain ${chartPhrase} for ${planPhrase} in plain language, as if to someone new to investing.`,
      id
        ? `First call get_plan_review_context with plan_id="${id}" and max_health_signals=5.`
        : 'First call get_plan_review_context with max_health_signals=5.',
      'Walk through what the shape of the chart says about my situation, what would change it, and what — if anything — it suggests I review next.',
      'Do not apply plan settings automatically.',
    ].join(' ');
  }
  const base = [
    `Review ${planPhrase} with bounded Plan context.`,
    id
      ? `First call get_plan_review_context with plan_id="${id}" and max_health_signals=5.`
      : 'First call get_plan_review_context with max_health_signals=5.',
    'Use the active assumption set summary, top 5 health signals, selected artifact ids and citations, and selected simulation result summary when present.',
    'Do not request full artifact contents. Do not request long decision history unless I explicitly open a specific artifact or decision.',
  ];
  if (normalizedIntent === 'explain_scenario_diff' || normalizedIntent === 'plan-scenario') {
    return [
      `Explain the simulation for ${planPhrase}.`,
      ...base.slice(1),
      'Focus on what changed, why it matters, confidence gaps, and the next review step. Do not apply plan settings automatically.',
    ].join(' ');
  }
  if (normalizedIntent === 'review_stale_assumptions') {
    return [
      `Review stale assumptions for ${planPhrase}.`,
      ...base.slice(1),
      'Focus on assumptions that block Today, Inbox, Portfolio-fit, Research, or scenario confidence.',
    ].join(' ');
  }
  return [
    `Review plan assumptions for ${planPhrase}.`,
    ...base.slice(1),
    'Explain which assumptions are decision-grade, which are weak, and what should be reviewed next.',
  ].join(' ');
}

// Keep in sync with services/session_focus.py FOCUS_DOMAIN_CATALOG (server is authoritative on write).
const FOCUS_DOMAIN_OPTIONS = [
  { id: 'plan', label: 'Plan' },
  { id: 'profile', label: 'Profile' },
  { id: 'profile.goals', label: 'Goals' },
  { id: 'profile.cashflow', label: 'Cashflow' },
  { id: 'profile.debt', label: 'Debt' },
  { id: 'profile.tax', label: 'Tax' },
  { id: 'profile.policy', label: 'Policy' },
  { id: 'portfolio', label: 'Portfolio' },
  { id: 'portfolio.holdings', label: 'Holdings' },
  { id: 'recommendation', label: 'Inbox' },
  { id: 'research', label: 'Research' },
];

function defaultSessionFocus() {
  return {
    mode: 'balanced',
    primary_domains: [],
    secondary_domains: [],
    muted_domains: [],
    pinned_entity_ids: [],
    priority_note: '',
    set_by: 'default',
    schema_version: 1,
  };
}

function seedFocusFromEntry(params = {}) {
  const intent = String(params.intent || '').trim().toLowerCase();
  const focusId = String(params.focus || '').trim();
  const base = defaultSessionFocus();
  base.set_by = 'entry_surface';
  if (intent === 'review_plan_assumptions' || intent === 'plan-scenario' || intent === 'explain_scenario_diff') {
    return { ...base, mode: 'narrow', primary_domains: ['plan'], secondary_domains: ['profile'], muted_domains: intent === 'review_plan_assumptions' ? ['research'] : [] };
  }
  if (intent === 'review_stale_assumptions') {
    return { ...base, mode: 'narrow', primary_domains: ['plan'], secondary_domains: ['profile', 'recommendation'] };
  }
  if (intent === 'explain-chart' || intent === 'withdrawal-strategy' || intent === 'plan-branch') {
    return { ...base, mode: 'narrow', primary_domains: ['plan'], muted_domains: intent === 'explain-chart' ? ['research'] : [] };
  }
  if (intent === 'investment-policy') {
    return { ...base, mode: 'narrow', primary_domains: ['profile.policy'], muted_domains: ['research'] };
  }
  if (intent === 'investment-fit') {
    return {
      ...base,
      mode: 'narrow',
      primary_domains: ['research'],
      secondary_domains: ['portfolio', 'profile.policy', 'recommendation'],
      pinned_entity_ids: focusId ? [`recommendation:${focusId}`] : [],
    };
  }
  if (intent === 'complete-context') {
    return {
      ...base,
      mode: 'narrow',
      primary_domains: ['profile'],
      secondary_domains: ['recommendation'],
      pinned_entity_ids: focusId ? [`recommendation:${focusId}`] : [],
    };
  }
  if (intent === 'review-decision') {
    return {
      ...base,
      mode: 'narrow',
      primary_domains: ['recommendation'],
      secondary_domains: ['plan'],
      pinned_entity_ids: focusId ? [`recommendation:${focusId}`] : [],
    };
  }
  if (intent === 'affordability') {
    return {
      ...base,
      mode: 'narrow',
      primary_domains: ['profile.cashflow', 'portfolio'],
      secondary_domains: ['plan', 'profile.debt'],
    };
  }
  return defaultSessionFocus();
}

const ui = {
  conversationId: null,
  conversationTitle: '',
  messages: [],
  conversations: [],
  onboarding: null,
  busy: false,
  thinking: false,
  error: null,
  planId: null,
  recommendationFocus: null,
  pickerOpen: null,                 // 'conversations' | 'plans' | 'focus' | null
  draftFocus: null,
  sessionFocus: defaultSessionFocus(),
};

export function template() {
  return html`
    <section class="page" id="copilot-page">
      <div class="copilot-shell" id="copilot-shell">
        <div class="copilot-top" id="copilot-masthead"></div>
        <div class="copilot-main" id="copilot-body"></div>
        <div class="copilot-bottom" id="copilot-composer"></div>
      </div>
    </section>
  `;
}

export async function init(params = {}) {
  ui.planId = params.plan_id || params.plan || state.activePlanId || null;
  ui.conversationId = params.conversation_id || null;
  ui.conversations = [];
  ui.messages = [];
  ui.onboarding = null;
  ui.busy = false;
  ui.thinking = false;
  ui.error = null;
  ui.recommendationFocus = String(params.focus || '').trim() || null;
  ui.pickerOpen = null;
  ui.sessionFocus = seedFocusFromEntry(params);
  attachHandlers();

  rerenderAll();

  // Load past conversations, then the active one (if any).
  loadConversations().then(() => rerenderMasthead()).catch(() => {});
  loadOnboarding().then(() => rerenderBody()).catch(() => {});
  if (ui.conversationId) {
    loadConversation(ui.conversationId).catch(() => {});
  }
  if (String(params.intent || '').trim().toLowerCase() === 'investment-policy') {
    fillDraft(INVESTMENT_POLICY_SETUP_PROMPT);
  }
  if (isPlanReviewIntent(params.intent)) {
    fillDraft(buildPlanReviewPrompt(params.intent, { planId: ui.planId, chart: params.chart }));
  }
  if (params.focus) {
    // Linked from inbox: prefill question. Conversation stays empty until sent.
    fillDraft(recommendationFocusPrompt(params.focus, params.intent));
  }
  // Goal/debt setup cards still use prompts; seed focus when those prompts apply.
  seedFocusFromOnboardingIfNeeded();
}

/* ─────────────  data  ───────────── */

async function loadConversations() {
  try {
    const list = await api.conversations(25);
    ui.conversations = Array.isArray(list) ? list : [];
  } catch {
    ui.conversations = [];
  }
}

async function loadOnboarding() {
  try {
    ui.onboarding = await api.onboarding();
  } catch {
    ui.onboarding = null;
  }
}

async function loadConversation(id) {
  ui.busy = true;
  ui.error = null;
  rerenderBody();
  try {
    const res = await api.conversation(id);
    ui.conversationId = res.id;
    ui.conversationTitle = res.title || '';
    ui.messages = Array.isArray(res.messages) ? res.messages : [];
    if (res.focus && typeof res.focus === 'object') {
      ui.sessionFocus = normalizeClientFocus(res.focus);
    }
  } catch (err) {
    ui.error = err.message;
  } finally {
    ui.busy = false;
    rerenderAll();
  }
}

async function sendMessage(question, { useLive }) {
  // Optimistic user message.
  const now = new Date().toISOString();
  ui.messages.push({ role: 'user', content: question, created_at: now, metadata: {} });
  ui.thinking = true;
  ui.error = null;
  rerenderBody();
  rerenderComposer({ draft: '' });

  try {
    const res = await api.copilotChat({
      question,
      conversation_id: ui.conversationId,
      use_live_snapshot: !!useLive,
      plan_id: ui.planId,
      context_options: { detail_level: 'light' },
      focus: clientFocusPayload(ui.sessionFocus),
      persist_focus: true,
    });
    ui.conversationId = res.conversation_id;
    if (res.focus && typeof res.focus === 'object') {
      ui.sessionFocus = normalizeClientFocus(res.focus);
    }
    ui.messages.push({
      role: 'assistant',
      content: res.answer || '',
      created_at: res.created_at || new Date().toISOString(),
      metadata: {
        tool_calls: res.tool_calls || [],
        model: res.model || null,
        context_trace: res.context_trace || {},
      },
    });
    if (!ui.conversationTitle) ui.conversationTitle = derivedTitle(question);
    loadConversations().then(() => rerenderMasthead()).catch(() => {});
  } catch (err) {
    ui.error = err.message;
    ui.messages.push({
      role: 'assistant',
      content: `_Could not reach Copilot — ${err.message}_`,
      created_at: new Date().toISOString(),
      metadata: {},
    });
  } finally {
    ui.thinking = false;
    rerenderAll();
    scrollToBottom();
  }
}

/* ─────────────  rendering  ───────────── */

function rerenderAll() {
  rerenderMasthead();
  rerenderBody();
  rerenderComposer();
}

function rerenderMasthead() {
  const root = $('#copilot-masthead');
  if (!root) return;
  root.innerHTML = renderMasthead();
}

function rerenderBody() {
  const root = $('#copilot-body');
  if (!root) return;
  root.innerHTML = renderBody();
}

function rerenderComposer({ draft = readDraft() } = {}) {
  const root = $('#copilot-composer');
  if (!root) return;
  root.innerHTML = renderComposer({ busy: ui.busy, draft });
  attachComposerBehavior(root, {
    onSubmit: ({ question, useLive }) => sendMessage(question, { useLive }),
  });
  if (ui.draftFocus) {
    const ta = root.querySelector('#composer-textarea');
    if (ta) {
      ta.focus();
      ta.setSelectionRange(ta.value.length, ta.value.length);
    }
    ui.draftFocus = null;
  }
}

function renderMasthead() {
  const plans = state.plans || [];
  const plan = plans.find(p => p.id === ui.planId) || plans.find(p => p.is_active) || plans[0];
  const focusLabel = focusSummaryLabel(ui.sessionFocus);
  const title = ui.conversationId
    ? (ui.conversationTitle || 'Untitled')
    : 'New chat';
  return html`
    <header class="copilot-masthead">
      <div class="copilot-masthead-left">
        <span class="copilot-picker">
          <button type="button" class="copilot-title-btn" data-picker="conversations" title="Conversations">
            <span class="copilot-title-text">${esc(title)}</span>
          </button>
          ${ui.pickerOpen === 'conversations' ? raw(renderConversationsMenu()) : ''}
        </span>
        <div class="copilot-scope-pills">
          ${plans.length ? html`
            <span class="copilot-picker">
              <button type="button" class="copilot-scope-pill" data-picker="plans" title="Plan scope">
                <span class="copilot-scope-k">Plan</span>
                <span class="copilot-scope-v">${esc(plan?.title || 'none')}</span>
              </button>
              ${ui.pickerOpen === 'plans' ? raw(renderPlansMenu(plans, plan?.id)) : ''}
            </span>
          ` : ''}
          <span class="copilot-picker">
            <button type="button" class="copilot-scope-pill" data-picker="focus" title="Session Focus — which domains expand in the brief">
              <span class="copilot-scope-k">Focus</span>
              <span class="copilot-scope-v">${esc(focusLabel)}</span>
            </button>
            ${ui.pickerOpen === 'focus' ? raw(renderFocusMenu()) : ''}
          </span>
        </div>
      </div>
      <button type="button" class="copilot-new-btn" data-action="new-chat" title="New conversation">
        New chat
      </button>
    </header>
  `;
}

function renderFocusMenu() {
  const focus = ui.sessionFocus || defaultSessionFocus();
  const primary = new Set(focus.primary_domains || []);
  const muted = new Set(focus.muted_domains || []);
  return html`
    <div class="copilot-picker-menu copilot-focus-panel open" data-menu="focus">
      <div class="copilot-focus-panel-head">
        <span class="copilot-focus-panel-title">Session Focus</span>
        <button type="button" class="copilot-focus-reset" data-focus-reset>Reset</button>
      </div>
      <p class="copilot-focus-hint">
        Steers the default brief. Mute does not block tools; critical warnings can still appear.
      </p>
      <div class="copilot-focus-mode" role="group" aria-label="Focus mode">
        <button type="button" class="copilot-focus-mode-btn ${focus.mode === 'narrow' ? 'active' : ''}" data-focus-mode="narrow">Narrow</button>
        <button type="button" class="copilot-focus-mode-btn ${focus.mode === 'balanced' ? 'active' : ''}" data-focus-mode="balanced">Balanced</button>
        <button type="button" class="copilot-focus-mode-btn ${focus.mode === 'wide' ? 'active' : ''}" data-focus-mode="wide">Wide</button>
      </div>
      <div class="copilot-focus-chips" role="group" aria-label="Focus domains">
        ${FOCUS_DOMAIN_OPTIONS.map(opt => {
          const stateClass = primary.has(opt.id) ? 'primary' : muted.has(opt.id) ? 'muted' : 'idle';
          return html`
            <button
              type="button"
              class="copilot-focus-chip ${stateClass}"
              data-focus-domain="${esc(opt.id)}"
              title="Click to cycle: off → primary → muted → off"
            >${esc(opt.label)}</button>
          `;
        })}
      </div>
      <p class="copilot-focus-legend">
        <span class="leg primary">Primary</span>
        <span class="leg muted">Muted</span>
        <span class="leg idle">Off</span>
      </p>
    </div>
  `;
}

function renderConversationsMenu() {
  return html`
    <div class="copilot-picker-menu open" data-menu="conversations">
      <button class="copilot-picker-item" data-conversation="__new__">
        <span class="copilot-picker-item-meta">New conversation</span>
        <span class="copilot-picker-item-title">Start a fresh thread</span>
      </button>
      ${ui.conversations.length ? html`<div class="copilot-picker-divider"></div>` : ''}
      ${ui.conversations.map(c => html`
        <button class="copilot-picker-item ${c.id === ui.conversationId ? 'active' : ''}" data-conversation="${c.id}">
          <span class="copilot-picker-item-meta">${c.updated_at ? fmtRelative(c.updated_at) : ''}</span>
          <span class="copilot-picker-item-title">${esc(c.title || c.last_message_preview || 'Untitled')}</span>
        </button>
      `)}
    </div>
  `;
}

function renderPlansMenu(plans, currentId) {
  return html`
    <div class="copilot-picker-menu open" data-menu="plans">
      <button class="copilot-picker-item ${ui.planId == null ? 'active' : ''}" data-plan="__none__">
        <span class="copilot-picker-item-meta">no plan</span>
        <span class="copilot-picker-item-title">Don't include a plan in context</span>
      </button>
      <div class="copilot-picker-divider"></div>
      ${plans.map(p => html`
        <button class="copilot-picker-item ${p.id === currentId ? 'active' : ''}" data-plan="${p.id}">
          <span class="copilot-picker-item-meta">${p.is_active ? 'active' : ''}</span>
          <span class="copilot-picker-item-title">${esc(p.title || 'Untitled')}</span>
        </button>
      `)}
    </div>
  `;
}

function renderBody() {
  if (ui.busy && !ui.messages.length) {
    return html`<div class="copilot-scroll"><div class="skeleton copilot-skeleton">.</div></div>`;
  }
  if (!ui.messages.length && !ui.thinking) {
    return html`<div class="copilot-scroll">${raw(renderEmpty())}</div>`;
  }
  return html`
    <div class="copilot-scroll">
      <div class="copilot-thread-wrap">
        ${raw(renderThread(ui.messages, { thinking: ui.thinking }))}
        ${ui.error ? html`<p class="error-banner">${esc(ui.error)}</p>` : ''}
      </div>
    </div>
  `;
}

function renderEmpty() {
  return html`
    <div class="copilot-empty">
      <div class="copilot-empty-hero">
        <p class="copilot-empty-headline">How can I help?</p>
        <p class="copilot-empty-lede">
          Portfolio, plan, and profile are available — ask a question or pick a starter.
        </p>
      </div>
      ${raw(renderProfileOnboardingCard())}
      <div class="suggestion-grid">
        ${SUGGESTIONS.map(s => html`
          <button type="button" class="suggestion-card" data-suggest="${esc(s)}">
            <span class="suggestion-card-text">${esc(s)}</span>
          </button>
        `)}
      </div>
    </div>
  `;
}

function renderProfileOnboardingCard() {
  const status = ui.onboarding;
  if (!status || status.ready_for_daily_review) return '';
  const percent = Math.round(Number(status.completion_percent || 0));
  const nextStep = nextOnboardingStep(status);
  const actionLabel = onboardingActionLabel(status);
  return html`
    <article class="profile-onboarding-card">
      <p class="profile-draft-eyebrow">Profile setup</p>
      <p class="profile-draft-summary">
        Your profile is ${percent}% complete${nextStep?.title ? `. Next: ${nextStep.title}.` : '.'}
      </p>
      ${raw(renderProfileReadinessHint(status.profile_readiness))}
      <div class="entry-actions">
        <button class="action-link" data-profile-onboarding-prompt>
          ${actionLabel} <span class="arrow">›</span>
        </button>
      </div>
    </article>
  `;
}

function renderProfileReadinessHint(readiness) {
  if (!readiness || typeof readiness !== 'object') return '';
  const detail = String(readiness.next_gap_detail || '').trim();
  const sources = Array.isArray(readiness.blocking_recommendation_sources)
    ? readiness.blocking_recommendation_sources
      .map(item => String(item || '').replace(/_/g, ' ').trim())
      .filter(Boolean)
      .slice(0, 2)
    : [];
  if (!detail && !sources.length) return '';
  const sourceText = sources.length ? ` Needed for ${sources.join(' and ')}.` : '';
  return html`<p class="profile-readiness-hint">${esc(detail)}${esc(sourceText)}</p>`;
}

/* ─────────────  helpers  ───────────── */

function readDraft() {
  const ta = document.querySelector('#composer-textarea');
  return ta ? ta.value : '';
}

function fillDraft(text) {
  ui.draftFocus = true;
  rerenderComposer({ draft: text });
}

function nextOnboardingStep(status) {
  const steps = Array.isArray(status?.steps) ? status.steps : [];
  return steps.find(step => step.status !== 'complete');
}

function isGoalOnboardingStep(step) {
  const key = String(step?.key || '').toLowerCase();
  const title = String(step?.title || '').toLowerCase();
  return key.includes('goal') || title.includes('goal');
}

function isDebtOnboardingStep(step) {
  const key = String(step?.key || '').toLowerCase();
  const title = String(step?.title || '').toLowerCase();
  return key.includes('debt') || title.includes('debt');
}

function isPhysicalAssetOnboardingStep(step) {
  const key = String(step?.key || '').toLowerCase();
  const title = String(step?.title || '').toLowerCase();
  return key.includes('physical_asset') || title.includes('physical asset') || title.includes('asset');
}

function isTaxOnboardingStep(step) {
  const key = String(step?.key || '').toLowerCase();
  const title = String(step?.title || '').toLowerCase();
  return key.includes('tax') || title.includes('tax');
}

function isInvestmentPolicyOnboardingStep(step) {
  const key = String(step?.key || '').toLowerCase();
  const title = String(step?.title || '').toLowerCase();
  return key.includes('investment_policy')
    || title.includes('investment policy')
    || title.includes('guardrail');
}

function isPlanReviewIntent(intent) {
  const normalized = String(intent || '').trim().toLowerCase();
  return normalized === 'review_plan_assumptions'
    || normalized === 'explain_scenario_diff'
    || normalized === 'review_stale_assumptions'
    || normalized === 'plan-scenario'
    || normalized === 'explain-chart';
}

function onboardingActionLabel(status) {
  const step = nextOnboardingStep(status);
  if (isDebtOnboardingStep(step)) return 'Add debt with Copilot';
  if (isGoalOnboardingStep(step)) return 'Add goals with Copilot';
  if (isTaxOnboardingStep(step)) return 'Add tax basics with Copilot';
  if (isInvestmentPolicyOnboardingStep(step)) return 'Define policy with Copilot';
  if (isPhysicalAssetOnboardingStep(step)) return 'Add assets with Copilot';
  return 'Fill it out with Copilot';
}

function onboardingPrompt(status) {
  const step = nextOnboardingStep(status);
  if (isDebtOnboardingStep(step)) return DEBT_SETUP_PROMPT;
  if (isGoalOnboardingStep(step)) return GOAL_SETUP_PROMPT;
  if (isTaxOnboardingStep(step)) return TAX_SETUP_PROMPT;
  if (isInvestmentPolicyOnboardingStep(step)) return INVESTMENT_POLICY_SETUP_PROMPT;
  if (isPhysicalAssetOnboardingStep(step)) return PHYSICAL_ASSET_SETUP_PROMPT;
  return PROFILE_SETUP_PROMPT;
}

function recommendationFocusPrompt(recommendationId, intent) {
  const id = String(recommendationId || '').trim();
  const normalizedIntent = String(intent || '').trim().toLowerCase();
  if (normalizedIntent === 'complete-context') {
    return [
      `Help me complete the missing context for recommendation ${id}.`,
      'First inspect the recommendation and its quality metadata, especially blocking_context.',
      'Then use get_onboarding_status and get_financial_profile if profile data is missing.',
      'Ask me one focused question at a time and draft any profile updates for review before saving.',
    ].join(' ');
  }
  if (normalizedIntent === 'review-decision') {
    return [
      `Review recommendation ${id} with me.`,
      'Explain the evidence, expected impact, confidence, freshness, reversibility, and downside.',
      'Call preview_recommendation if a preview is available before suggesting that I apply anything.',
    ].join(' ');
  }
  if (normalizedIntent === 'investment-fit') {
    return [
      `Review investment-fit recommendation ${id} with me.`,
      'Inspect the recommendation evidence, provider freshness, evidence packet references, portfolio-fit status, blocking gaps, and suggested next step.',
      'Use assess_portfolio_fit, research_compare, research_dossier, or simulate_trade only when needed. Pass proposed_account_id to assess_portfolio_fit when the recommendation is about a specific account location.',
      'If this is a watchlist thesis review and the thesis should change, call draft_watchlist_thesis_revision so I can review and save the revised thesis.',
      'If this is a saved dossier thesis review and the thesis should change, call draft_dossier_thesis_revision so I can review and save the revised dossier thesis.',
      'Keep the answer framed as fit review, research, comparison, simulation, or missing context. Do not give hidden buy/sell advice.',
    ].join(' ');
  }
  return `Tell me about recommendation ${id}.`;
}

function scrollToBottom() {
  // Bring the latest message into view without snapping the scroll.
  const last = document.querySelector('.message:last-of-type');
  if (last) last.scrollIntoView({ behavior: 'smooth', block: 'end' });
}

function derivedTitle(question) {
  const trimmed = String(question).trim().replace(/\s+/g, ' ');
  if (trimmed.length <= 60) return trimmed;
  return trimmed.slice(0, 57) + '…';
}

function normalizeClientFocus(raw) {
  const base = defaultSessionFocus();
  if (!raw || typeof raw !== 'object') return base;
  return {
    mode: ['narrow', 'balanced', 'wide'].includes(raw.mode) ? raw.mode : 'balanced',
    primary_domains: Array.isArray(raw.primary_domains) ? raw.primary_domains.slice(0, 3) : [],
    secondary_domains: Array.isArray(raw.secondary_domains) ? raw.secondary_domains.slice(0, 5) : [],
    muted_domains: Array.isArray(raw.muted_domains) ? raw.muted_domains.slice(0, 8) : [],
    pinned_entity_ids: Array.isArray(raw.pinned_entity_ids) ? raw.pinned_entity_ids.slice(0, 12) : [],
    priority_note: String(raw.priority_note || '').slice(0, 280),
    set_by: raw.set_by || 'user',
    schema_version: 1,
    updated_at: raw.updated_at || null,
  };
}

function clientFocusPayload(focus) {
  const normalized = normalizeClientFocus(focus);
  return {
    mode: normalized.mode,
    primary_domains: normalized.primary_domains,
    secondary_domains: normalized.secondary_domains,
    muted_domains: normalized.muted_domains,
    pinned_entity_ids: normalized.pinned_entity_ids,
    priority_note: normalized.priority_note,
    set_by: normalized.set_by === 'default' ? 'user' : normalized.set_by,
    schema_version: 1,
  };
}

function focusSummaryLabel(focus) {
  const f = normalizeClientFocus(focus);
  if (f.primary_domains.length) {
    const labels = f.primary_domains
      .map(id => FOCUS_DOMAIN_OPTIONS.find(opt => opt.id === id)?.label || id)
      .slice(0, 2);
    return `${f.mode} · ${labels.join(', ')}`;
  }
  if (f.muted_domains.length) return `${f.mode} · muted ${f.muted_domains.length}`;
  return f.mode;
}

function cycleFocusDomain(focus, domainId) {
  const next = normalizeClientFocus(focus);
  const primary = new Set(next.primary_domains);
  const muted = new Set(next.muted_domains);
  if (primary.has(domainId)) {
    primary.delete(domainId);
    muted.add(domainId);
  } else if (muted.has(domainId)) {
    muted.delete(domainId);
  } else {
    if (primary.size >= 3) {
      const first = [...primary][0];
      primary.delete(first);
    }
    primary.add(domainId);
    muted.delete(domainId);
  }
  next.primary_domains = [...primary];
  next.muted_domains = [...muted].filter(id => !primary.has(id));
  next.secondary_domains = (next.secondary_domains || []).filter(
    id => !primary.has(id) && !muted.has(id),
  );
  next.set_by = 'user';
  return next;
}

function seedFocusFromOnboardingIfNeeded(force = false) {
  if (!force && ui.sessionFocus?.set_by === 'user') return;
  const step = nextOnboardingStep(ui.onboarding);
  if (!step) return;
  const base = defaultSessionFocus();
  base.set_by = 'entry_surface';
  base.mode = 'narrow';
  if (isGoalOnboardingStep(step)) {
    ui.sessionFocus = { ...base, primary_domains: ['profile.goals'], muted_domains: ['research', 'portfolio.holdings'] };
  } else if (isDebtOnboardingStep(step)) {
    ui.sessionFocus = { ...base, primary_domains: ['profile.debt'], muted_domains: ['research'] };
  } else if (isTaxOnboardingStep(step)) {
    ui.sessionFocus = { ...base, primary_domains: ['profile.tax'] };
  } else if (isInvestmentPolicyOnboardingStep(step)) {
    ui.sessionFocus = { ...base, primary_domains: ['profile.policy'], muted_domains: ['research'] };
  } else if (isPhysicalAssetOnboardingStep(step)) {
    ui.sessionFocus = { ...base, primary_domains: ['profile'], muted_domains: ['research'] };
  }
}

/* ─────────────  events  ───────────── */

function attachHandlers() {
  const page = $('#copilot-page');
  if (!page) return;

  delegate(page, 'click', '[data-picker]', (e, t) => {
    e.stopPropagation();
    const which = t.getAttribute('data-picker');
    ui.pickerOpen = ui.pickerOpen === which ? null : which;
    rerenderMasthead();
  });

  delegate(page, 'click', '[data-conversation]', async (_, t) => {
    const id = t.getAttribute('data-conversation');
    ui.pickerOpen = null;
    if (id === '__new__') {
      ui.conversationId = null;
      ui.conversationTitle = '';
      ui.messages = [];
      ui.sessionFocus = defaultSessionFocus();
      rerenderAll();
      return;
    }
    rerenderMasthead();
    await loadConversation(id);
  });

  delegate(page, 'click', '[data-plan]', (_, t) => {
    const id = t.getAttribute('data-plan');
    ui.planId = id === '__none__' ? null : id;
    ui.pickerOpen = null;
    rerenderMasthead();
  });

  delegate(page, 'click', '[data-action="new-chat"]', () => {
    ui.conversationId = null;
    ui.conversationTitle = '';
    ui.messages = [];
    ui.error = null;
    ui.sessionFocus = defaultSessionFocus();
    rerenderAll();
  });

  delegate(page, 'click', '[data-menu="focus"]', (e) => {
    // Keep the focus panel open while interacting inside it.
    e.stopPropagation();
  });

  delegate(page, 'click', '[data-focus-mode]', (e, t) => {
    e.stopPropagation();
    const mode = t.getAttribute('data-focus-mode');
    if (!mode) return;
    ui.sessionFocus = {
      ...normalizeClientFocus(ui.sessionFocus),
      mode,
      set_by: 'user',
    };
    ui.pickerOpen = 'focus';
    rerenderMasthead();
  });

  delegate(page, 'click', '[data-focus-domain]', (e, t) => {
    e.stopPropagation();
    const domain = t.getAttribute('data-focus-domain');
    if (!domain) return;
    ui.sessionFocus = cycleFocusDomain(ui.sessionFocus, domain);
    ui.pickerOpen = 'focus';
    rerenderMasthead();
  });

  delegate(page, 'click', '[data-focus-reset]', (e) => {
    e.stopPropagation();
    ui.sessionFocus = defaultSessionFocus();
    ui.pickerOpen = 'focus';
    rerenderMasthead();
  });

  delegate(page, 'click', '[data-suggest]', (_, t) => {
    const text = t.getAttribute('data-suggest') || '';
    fillDraft(text);
  });

  delegate(page, 'click', '[data-profile-draft]', (_, t) => {
    applyProfileDraft(t);
  });

  delegate(page, 'click', '[data-thesis-draft]', (_, t) => {
    saveThesisDraft(t);
  });

  delegate(page, 'click', '[data-profile-onboarding-prompt]', () => {
    const prompt = onboardingPrompt(ui.onboarding);
    seedFocusFromOnboardingIfNeeded(true);
    fillDraft(prompt);
  });

  // Outside-click closes pickers.
  document.addEventListener('click', closePickersOnOutsideClick, { passive: true });
}

async function applyProfileDraft(button) {
  const encoded = button.getAttribute('data-profile-draft') || '';
  let patch = null;
  try {
    patch = JSON.parse(decodeURIComponent(encoded));
  } catch {
    ui.error = 'Could not read the drafted profile update.';
    rerenderBody();
    return;
  }

  button.disabled = true;
  button.textContent = 'Applying...';
  ui.error = null;

  try {
    const current = await api.profile();
    const saved = await api.updateProfile(
      mergeProfileDraft(current, patch),
      { source: 'copilot_profile_draft' },
    );
    state.financialProfile = saved;
    ui.messages.push({
      role: 'assistant',
      content: 'Profile update applied. Your financial profile is now updated for future reviews.',
      created_at: new Date().toISOString(),
      metadata: {},
    });
    await loadOnboarding();
  } catch (err) {
    ui.error = err.message;
  } finally {
    rerenderBody();
    scrollToBottom();
  }
}

async function saveThesisDraft(button) {
  const encoded = button.getAttribute('data-thesis-draft') || '';
  let patch = null;
  try {
    patch = JSON.parse(decodeURIComponent(encoded));
  } catch {
    ui.error = 'Could not read the drafted thesis revision.';
    rerenderBody();
    return;
  }
  if (ui.recommendationFocus && !patch.recommendation_id) {
    patch.recommendation_id = ui.recommendationFocus;
  }
  const targetType = String(patch?.target_type || 'watchlist').trim().toLowerCase();
  const symbol = String(patch?.symbol || '').trim().toUpperCase();
  const planId = String(patch?.plan_id || '').trim();
  const artifactId = String(patch?.artifact_id || '').trim();
  if (targetType === 'dossier' && (!planId || !artifactId)) {
    ui.error = 'Could not identify the saved dossier for this thesis revision.';
    rerenderBody();
    return;
  }
  if (targetType !== 'dossier' && !symbol) {
    ui.error = 'Could not identify the watchlist symbol for this thesis revision.';
    rerenderBody();
    return;
  }

  button.disabled = true;
  button.textContent = 'Saving...';
  ui.error = null;

  try {
    if (targetType === 'dossier') {
      await api.saveDossierThesisRevision(planId, artifactId, patch);
    } else {
      await api.saveWatchlistThesisRevision(symbol, patch);
    }
    const message = targetType === 'dossier'
      ? `Dossier thesis updated for ${artifactId}. Future thesis readiness checks will use the revised review window.`
      : `Watchlist thesis updated for ${symbol}. Future thesis readiness checks will use the revised review window.`;
    ui.messages.push({
      role: 'assistant',
      content: message,
      created_at: new Date().toISOString(),
      metadata: {},
    });
  } catch (err) {
    ui.error = err.message;
  } finally {
    rerenderBody();
    scrollToBottom();
  }
}

function mergeProfileDraft(current, patch) {
  const merged = { ...(current || {}) };
  for (const key of ['income_items', 'expense_items', 'debt_items', 'goal_items', 'physical_assets']) {
    if (Array.isArray(patch?.[key])) merged[key] = patch[key];
  }
  if (typeof patch?.notes === 'string') merged.notes = patch.notes;
  if (patch?.tax_profile && typeof patch.tax_profile === 'object') {
    merged.tax_profile = { ...(merged.tax_profile || {}), ...patch.tax_profile };
  }
  if (patch?.investment_policy && typeof patch.investment_policy === 'object') {
    merged.investment_policy = { ...(merged.investment_policy || {}), ...patch.investment_policy };
  }
  if (patch?.flags && typeof patch.flags === 'object') {
    merged.flags = { ...(merged.flags || {}), ...patch.flags };
  }
  return merged;
}

function closePickersOnOutsideClick(e) {
  if (!ui.pickerOpen) return;
  const masthead = document.querySelector('#copilot-masthead');
  if (!masthead) return;
  if (!masthead.contains(e.target)) {
    ui.pickerOpen = null;
    rerenderMasthead();
  }
}
