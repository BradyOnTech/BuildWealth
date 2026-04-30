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
  numeral: 'IV',
  group: 'daily',
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

export function buildPlanReviewPrompt(intent, { planId = '' } = {}) {
  const normalizedIntent = String(intent || '').trim().toLowerCase();
  const id = String(planId || '').trim();
  const planPhrase = id ? `plan ${id}` : 'the active plan';
  const base = [
    `Review ${planPhrase} with bounded Plan context.`,
    id
      ? `First call get_plan_review_context with plan_id="${id}" and max_health_signals=5.`
      : 'First call get_plan_review_context with max_health_signals=5.',
    'Use the active assumption set summary, top 5 health signals, selected artifact ids and citations, and selected scenario diff result summary when present.',
    'Do not request full artifact contents. Do not request long decision history unless I explicitly open a specific artifact or decision.',
  ];
  if (normalizedIntent === 'explain_scenario_diff' || normalizedIntent === 'plan-scenario') {
    return [
      `Explain the scenario diff for ${planPhrase}.`,
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
  pickerOpen: null,                 // 'conversations' | 'plans' | null
  draftFocus: null,
};

export function template() {
  return html`
    <section class="page" id="copilot-page">
      <div id="copilot-masthead"></div>
      <div id="copilot-body"></div>
      <div id="copilot-composer"></div>
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
  attachHandlers();

  rerenderAll();

  // Load past conversations, then the active one (if any).
  loadConversations().then(() => rerenderMasthead()).catch(() => {});
  loadOnboarding().then(() => rerenderBody()).catch(() => {});
  if (String(params.intent || '').trim().toLowerCase() === 'investment-policy') {
    fillDraft(INVESTMENT_POLICY_SETUP_PROMPT);
  }
  if (isPlanReviewIntent(params.intent)) {
    fillDraft(buildPlanReviewPrompt(params.intent, { planId: ui.planId }));
  }
  if (params.focus) {
    // Linked from inbox: prefill question. Conversation stays empty until sent.
    fillDraft(recommendationFocusPrompt(params.focus, params.intent));
  }
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
      context_options: { detail_level: 'full' },
    });
    ui.conversationId = res.conversation_id;
    ui.messages.push({
      role: 'assistant',
      content: res.answer || '',
      created_at: res.created_at || new Date().toISOString(),
      metadata: { tool_calls: res.tool_calls || [], model: res.model || null },
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
    rerenderBody();
    rerenderComposer({ draft: '' });
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
  return html`
    <header class="copilot-masthead">
      <div class="copilot-masthead-controls">
        <span class="copilot-masthead-eyebrow">Copilot</span>
        <span class="copilot-picker">
          <button class="copilot-picker-button" data-picker="conversations">
            ${ui.conversationId ? esc(ui.conversationTitle || 'Untitled') : 'New conversation'}
          </button>
          ${ui.pickerOpen === 'conversations' ? raw(renderConversationsMenu()) : ''}
        </span>
        ${plans.length ? html`
          <span class="copilot-picker">
            <button class="copilot-picker-button" data-picker="plans">
              plan: ${esc(plan?.title || 'none')}
            </button>
            ${ui.pickerOpen === 'plans' ? raw(renderPlansMenu(plans, plan?.id)) : ''}
          </span>
        ` : ''}
      </div>
      <div class="entry-actions">
        <button class="action-link muted" data-action="new-chat">New conversation <span class="arrow">›</span></button>
      </div>
    </header>
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
    return html`<div class="skeleton" style="height: 320px; margin-top: var(--s-7);">.</div>`;
  }
  if (!ui.messages.length && !ui.thinking) {
    return renderEmpty();
  }
  return html`
    ${ui.conversationTitle ? html`
      <h1 class="conversation-title">${esc(ui.conversationTitle)}</h1>
    ` : ''}
    ${raw(renderThread(ui.messages, { thinking: ui.thinking }))}
    ${ui.error ? html`<p class="error-banner">${esc(ui.error)}</p>` : ''}
  `;
}

function renderEmpty() {
  return html`
    <div class="copilot-empty">
      <p class="copilot-empty-headline">Ask anything.</p>
      <p class="copilot-empty-lede">
        Copilot has your portfolio, your plan and your profile in scope.
        It can run scenarios, look at concentration, and recommend changes.
      </p>
      ${raw(renderProfileOnboardingCard())}
      <ul class="suggestion-list">
        ${SUGGESTIONS.map(s => html`
          <li>
            <button class="suggestion-row" data-suggest="${esc(s)}">${esc(s)}</button>
          </li>
        `)}
      </ul>
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
    || normalized === 'plan-scenario';
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
    rerenderAll();
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
    fillDraft(onboardingPrompt(ui.onboarding));
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
    const saved = await api.updateProfile(mergeProfileDraft(current, patch));
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
