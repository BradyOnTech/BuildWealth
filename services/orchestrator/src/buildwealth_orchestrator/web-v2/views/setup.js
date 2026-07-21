// SETUP — a resumable first-outcome journey across Profile, Portfolio, and Plan.
// Progress belongs to the journey; financial readiness remains derived from
// Canonical State and is never fabricated by advancing or skipping a step.

import { api } from '../lib/api.js';
import { html, raw, $, esc, setView, delegate } from '../lib/dom.js';
import { fmtUsd } from '../lib/format.js';
import { isEmptyWorkspace } from './today.js';

export const meta = {
  id: 'setup',
  label: 'Setup',
  numeral: '·',
  group: 'utility',
};

export const SETUP_STEPS = [
  {
    id: 'welcome',
    numeral: 'I',
    short: 'Welcome',
    title: 'Start with a private household workspace.',
    lede: 'BuildWealth needs enough context to make the first picture useful—not every detail of your financial life.',
  },
  {
    id: 'foundation',
    numeral: 'II',
    short: 'Foundation',
    title: 'Give the numbers their household context.',
    lede: 'Who is in the household, what comes in, what usually goes out, and whether debt needs a place in the plan.',
  },
  {
    id: 'portfolio',
    numeral: 'III',
    short: 'What you own',
    title: 'Bring in the accounts that shape today.',
    lede: 'A statement is fastest, but current balances are enough for a first allocation and net-worth picture.',
  },
  {
    id: 'future',
    numeral: 'IV',
    short: 'What is ahead',
    title: 'Name one thing the money needs to make possible.',
    lede: 'A goal or life event gives the first forecast a direction. It can stay rough and change later.',
  },
  {
    id: 'first_picture',
    numeral: 'V',
    short: 'First picture',
    title: 'See what the current evidence can support.',
    lede: 'BuildWealth shows the useful numbers now and names what still needs evidence before you rely on the plan.',
  },
];

export const ui = {
  loaded: false,
  busy: false,
  error: null,
  notice: null,
  progress: null,
  onboarding: null,
  today: null,
  health: null,
  profile: null,
};

export function template() {
  return html`
    <section class="page setup-page" id="setup-page">
      <div class="setup-shell" id="setup-shell">
        <p class="marginalia">Opening your setup…</p>
      </div>
    </section>
  `;
}

export async function init() {
  const root = $('#setup-shell');
  if (!root) return;
  ui.loaded = false;
  ui.error = null;
  render();
  try {
    let progress = await api.onboardingProgress();
    if (!progress?.started) progress = await api.startOnboarding();
    const [onboarding, today, health, profile] = await Promise.all([
      api.onboarding().catch(() => null),
      api.today().catch(() => null),
      api.financialHealth().catch(() => null),
      api.profile(),
    ]);
    ui.progress = progress;
    ui.onboarding = onboarding;
    ui.today = today;
    ui.health = health;
    ui.profile = profile;
    ui.loaded = true;
  } catch (err) {
    ui.error = err?.message || 'Could not open Setup.';
  }
  render();
  bind(root);
}

function bind(root) {
  delegate(root, 'click', '[data-setup-step]', async (event, target) => {
    event.preventDefault();
    await moveToStep(target.dataset.setupStep);
  });
  delegate(root, 'click', '[data-setup-next]', async (event, target) => {
    event.preventDefault();
    await advance(target.dataset.setupNext, { completed: target.dataset.setupCurrent });
  });
  delegate(root, 'click', '[data-setup-skip]', async (event, target) => {
    event.preventDefault();
    await advance(target.dataset.setupSkip, { skipped: target.dataset.setupCurrent });
  });
  delegate(root, 'click', '[data-setup-finish]', async (event) => {
    event.preventDefault();
    await finish();
  });
  delegate(root, 'submit', '[data-setup-foundation-form]', async (event, form) => {
    event.preventDefault();
    if (!form.reportValidity()) return;
    await saveFoundation(form);
  });
  delegate(root, 'submit', '[data-setup-portfolio-form]', async (event, form) => {
    event.preventDefault();
    if (!form.reportValidity()) return;
    await savePortfolio(form);
  });
  delegate(root, 'submit', '[data-setup-future-form]', async (event, form) => {
    event.preventDefault();
    if (!form.reportValidity()) return;
    await saveFuture(form);
  });
  delegate(root, 'change', '[data-setup-asset-kind]', (_, select) => {
    const form = select.closest('form');
    form?.querySelector('[data-setup-symbol-field]')?.toggleAttribute('hidden', select.value !== 'investment');
  });
}

async function moveToStep(step) {
  if (!step || ui.busy) return;
  await saveProgress({ current_step: step });
}

async function advance(next, { completed = '', skipped = '' } = {}) {
  if (!next || ui.busy) return;
  await saveProgress({
    current_step: next,
    ...(completed ? { completed_step: completed } : {}),
    ...(skipped ? { skipped_step: skipped } : {}),
  });
}

async function finish() {
  if (ui.busy) return;
  const saved = await saveProgress({ completed_step: 'first_picture', complete: true });
  if (saved) window.location.hash = 'today';
}

async function saveProgress(payload) {
  ui.busy = true;
  ui.error = null;
  ui.notice = null;
  render();
  try {
    ui.progress = await api.updateOnboardingProgress(payload);
    return ui.progress;
  } catch (err) {
    ui.error = err?.message || 'Could not save Setup progress.';
    return null;
  } finally {
    ui.busy = false;
    render();
  }
}

async function saveFoundation(form) {
  const missing = missingFoundationKeys(ui.onboarding);
  const fields = Object.fromEntries(new FormData(form));
  await runSetupMutation(async () => {
    const next = buildFoundationProfile(ui.profile, fields, missing);
    ui.profile = await api.updateProfile(next, { source: 'setup_foundation' });
    return 'Foundation saved. The full Profile remains editable whenever life changes.';
  });
}

async function savePortfolio(form) {
  const fields = Object.fromEntries(new FormData(form));
  await runSetupMutation(async () => {
    const result = await api.portfolioAdd(buildSetupPortfolioBody(fields));
    return result?.detail || 'Current value added to your portfolio.';
  });
}

async function saveFuture(form) {
  const fields = Object.fromEntries(new FormData(form));
  await runSetupMutation(async () => {
    const next = buildFutureProfile(ui.profile, fields);
    ui.profile = await api.updateProfile(next, { source: 'setup_future' });
    return 'Goal saved. It is a starting direction, not a permanent commitment.';
  });
}

async function runSetupMutation(mutate) {
  if (ui.busy) return;
  ui.busy = true;
  ui.error = null;
  ui.notice = null;
  render();
  try {
    ui.notice = await mutate();
    await refreshSetupContext();
  } catch (err) {
    ui.error = err?.message || 'That could not be saved. Nothing else was changed.';
  } finally {
    ui.busy = false;
    render();
  }
}

async function refreshSetupContext() {
  const [onboarding, today, health, profile] = await Promise.all([
    api.onboarding().catch(() => ui.onboarding),
    api.today().catch(() => ui.today),
    api.financialHealth().catch(() => ui.health),
    api.profile().catch(() => ui.profile),
  ]);
  ui.onboarding = onboarding;
  ui.today = today;
  ui.health = health;
  ui.profile = profile;
}

export function deriveSetupJourney({ progress = {}, onboarding = {}, today = null, health = null } = {}) {
  const currentId = SETUP_STEPS.some(step => step.id === progress.current_step)
    ? progress.current_step
    : SETUP_STEPS[0].id;
  const completed = new Set(Array.isArray(progress.completed_steps) ? progress.completed_steps : []);
  const skipped = new Set(Array.isArray(progress.skipped_steps) ? progress.skipped_steps : []);
  const sections = Array.isArray(onboarding?.profile_readiness?.sections)
    ? onboarding.profile_readiness.sections
    : [];
  const bySection = new Map(sections.map(section => [section.key, section]));
  const onboardingSteps = new Map(
    (Array.isArray(onboarding?.steps) ? onboarding.steps : []).map(step => [step.id, step]),
  );
  const foundationKeys = ['household', 'income', 'expenses', 'debt'];
  const foundationReady = foundationKeys.every(key => bySection.get(key)?.status === 'complete');
  const portfolioReady = ['complete', 'attention'].includes(onboardingSteps.get('snapshot')?.status);
  const futureReady = bySection.get('goals')?.status === 'complete';
  const firstPictureReady = Boolean(today || health) && !isEmptyWorkspace(today || {}, health);
  const evidence = {
    welcome: true,
    foundation: foundationReady,
    portfolio: portfolioReady,
    future: futureReady,
    first_picture: firstPictureReady,
  };

  return SETUP_STEPS.map((step, index) => ({
    ...step,
    index,
    current: step.id === currentId,
    completed: completed.has(step.id),
    skipped: skipped.has(step.id),
    evidenceReady: Boolean(evidence[step.id]),
  }));
}

export function renderSetup({ progress, onboarding, today, health, profile, busy = false, error = '', notice = '' } = {}) {
  const journey = deriveSetupJourney({ progress, onboarding, today, health });
  const active = journey.find(step => step.current) || journey[0];
  return html`
    ${raw(renderMasthead())}
    ${raw(renderProgress(journey, busy))}
    <div class="setup-workspace">
      ${raw(renderStageContext(active, journey))}
      <article class="setup-card" aria-labelledby="setup-active-title">
        <div class="setup-card-copy setup-enter">
          <p class="setup-eyebrow">Step ${active.index + 1} of ${journey.length} · ${active.short}</p>
          <h2 id="setup-active-title">${active.title}</h2>
          <p class="setup-lede">${active.lede}</p>
        </div>
        ${error ? html`<p class="error-banner setup-enter" role="alert">${error}</p>` : ''}
        ${notice ? html`<p class="setup-notice setup-enter" role="status">${notice}</p>` : ''}
        <div class="setup-enter">${raw(renderStageBody(active, { onboarding, today, health, profile, busy }))}</div>
      </article>
    </div>
  `.toString();
}

function render() {
  const root = $('#setup-shell');
  if (!root) return;
  if (!ui.loaded && !ui.error) {
    setView(root, html`
      ${raw(renderMasthead())}
      <div class="setup-loading" aria-live="polite">
        <span class="setup-loading-mark">§</span>
        <p>Opening your private household workspace…</p>
      </div>
    `);
    return;
  }
  setView(root, raw(renderSetup({ ...ui })));
}

function renderMasthead() {
  return html`
    <header class="setup-masthead">
      <div>
        <p class="setup-folio">The Wealth Almanac · First edition</p>
        <h1>Build your first decision picture.</h1>
        <p>Five small steps. Leave whenever you want; every answer stays editable.</p>
      </div>
      <a class="setup-leave" href="#today">Explore the app <span aria-hidden="true">↗</span></a>
    </header>
  `;
}

function renderProgress(journey, busy) {
  return html`
    <nav class="setup-progress" aria-label="Setup progress">
      ${raw(journey.map(step => {
        const state = step.completed ? 'complete' : step.skipped ? 'skipped' : step.current ? 'current' : 'upcoming';
        return html`
          <button type="button" class="setup-progress-step ${state}"
                  data-setup-step="${step.id}" ${busy ? 'disabled' : ''}
                  aria-current="${step.current ? 'step' : 'false'}">
            <span class="setup-progress-number">${step.completed ? '✓' : step.numeral}</span>
            <span class="setup-progress-label">${step.short}</span>
            <span class="setup-progress-state">${step.completed ? 'Done' : step.skipped ? 'Later' : step.current ? 'Now' : ''}</span>
          </button>
        `;
      }).join(''))}
    </nav>
  `;
}

function renderStageContext(active, journey) {
  const done = journey.filter(step => step.completed).length;
  const deferred = journey.filter(step => step.skipped).length;
  return html`
    <aside class="setup-context">
      <p class="setup-context-number num-mono">${done}/${journey.length}</p>
      <p class="setup-context-label">journey steps finished</p>
      <div class="setup-context-rule"></div>
      <p class="setup-context-note">
        ${active.evidenceReady
          ? 'The underlying financial evidence for this step is ready to continue.'
          : 'Progress here never marks financial data complete. BuildWealth checks the underlying evidence separately.'}
      </p>
      ${deferred ? html`<p class="setup-context-deferred">${deferred} left for later</p>` : ''}
    </aside>
  `;
}

function renderStageBody(active, context) {
  if (active.id === 'welcome') return renderWelcome(context);
  if (active.id === 'foundation') return renderFoundation(active, context);
  if (active.id === 'portfolio') return renderPortfolio(active, context);
  if (active.id === 'future') return renderFuture(active, context);
  return renderFirstPicture(context);
}

function renderWelcome({ busy }) {
  return html`
    <div class="setup-principles">
      ${raw(principle('Private by design', 'Your information stays inside this household workspace and remains exportable.'))}
      ${raw(principle('Confirmation over interrogation', 'BuildWealth labels estimates and asks you to correct them instead of pretending they are facts.'))}
      ${raw(principle('Evidence before confidence', 'Missing inputs stay visible. Setup never turns incomplete information into a confident recommendation.'))}
    </div>
    <div class="setup-actions">
      <button class="btn btn-primary setup-next" data-setup-next="foundation" data-setup-current="welcome" ${busy ? 'disabled' : ''}>
        Start with my household <span aria-hidden="true">→</span>
      </button>
      <p>Usually 5–10 minutes for a useful first picture.</p>
    </div>
  `;
}

function renderFoundation(active, { onboarding, busy }) {
  const sections = sectionMap(onboarding);
  const missing = missingFoundationKeys(onboarding);
  const items = [
    ['household', 'Household', '#profile?section=household'],
    ['income', 'Income', '#profile?section=income'],
    ['expenses', 'Representative expenses', '#profile?section=expenses'],
    ['debt', 'Debt or debt-free answer', '#profile?section=debt'],
  ];
  return html`
    <div class="setup-checklist">
      ${raw(items.map(([key, label, href]) => setupCheck(label, sections.get(key), href)).join(''))}
    </div>
    ${missing.length ? raw(renderFoundationForm(missing, busy)) : ''}
    ${raw(stageActions(active, {
      ready: active.evidenceReady,
      next: 'portfolio',
      nextLabel: 'Continue to what I own',
      busy,
    }))}
  `;
}

function renderPortfolio(active, { onboarding, busy }) {
  const snapshot = (Array.isArray(onboarding?.steps) ? onboarding.steps : [])
    .find(step => step.id === 'snapshot');
  const connected = active.evidenceReady;
  return html`
    ${connected ? '' : raw(renderPortfolioForm(busy))}
    <div class="setup-alternates">
      <span>Have a statement or need more detail?</span>
      <a href="#import-sync?section=statement">Import and reconcile</a>
      <a href="#portfolio?section=maintenance">Open full Portfolio</a>
    </div>
    <p class="setup-evidence ${connected ? 'ready' : ''}">
      <span aria-hidden="true">${connected ? '✓' : '○'}</span>
      ${connected ? esc(snapshot?.detail || 'Portfolio context is available.') : 'No portfolio snapshot yet. You can continue and add it later.'}
    </p>
    ${raw(stageActions(active, {
      ready: connected,
      next: 'future',
      nextLabel: 'Continue to what is ahead',
      busy,
    }))}
  `;
}

function renderFuture(active, { onboarding, busy }) {
  const goals = sectionMap(onboarding).get('goals');
  return html`
    <div class="setup-future-prompt">
      <p class="setup-quote">“What is most likely to change how your household earns, spends, or uses money next?”</p>
      <p>The existing interview turns one answer into reviewable goal and timeline drafts. Nothing is applied until you approve it.</p>
    </div>
    ${active.evidenceReady ? '' : raw(renderFutureForm(busy))}
    <p class="setup-evidence ${active.evidenceReady ? 'ready' : ''}">
      <span aria-hidden="true">${active.evidenceReady ? '✓' : '○'}</span>
      ${esc(goals?.detail || 'No goal or future event is on record yet.')}
    </p>
    ${raw(stageActions(active, {
      ready: active.evidenceReady,
      next: 'first_picture',
      nextLabel: 'Show my first picture',
      busy,
    }))}
  `;
}

function renderFoundationForm(missing, busy) {
  const needs = new Set(missing);
  return html`
    <form class="setup-inline-form" data-setup-foundation-form>
      <div class="setup-form-heading">
        <div><p class="setup-path-eyebrow">Quick foundation</p><h3>Fill only what is missing.</h3></div>
        <p>These totals create editable starter records; they do not replace details already on file.</p>
      </div>
      <div class="setup-form-grid">
        ${needs.has('household') ? raw(setupField('Your name', 'display_name', 'text', 'Taylor', { autocomplete: 'name' })) : ''}
        ${needs.has('income') ? raw(setupField('Annual household income', 'annual_income_usd', 'number', '85000', { prefix: '$', hint: 'Before tax; an estimate is fine.', min: '0', step: '1' })) : ''}
        ${needs.has('expenses') ? raw(setupField('Typical monthly spending', 'monthly_expenses_usd', 'number', '4200', { prefix: '$', hint: 'One representative total for now.', min: '0', step: '1' })) : ''}
        ${needs.has('debt') ? raw(setupField('Current debt balance', 'debt_balance_usd', 'number', '0', { prefix: '$', hint: 'Enter 0 if you have no current debt.', min: '0', step: '1' })) : ''}
      </div>
      <div class="setup-form-footer">
        <button class="btn btn-primary" type="submit" ${busy ? 'disabled' : ''}>${busy ? 'Saving…' : 'Save foundation'}</button>
        <a class="link-editorial" href="#profile">Use the full Profile editor</a>
      </div>
    </form>
  `;
}

function renderPortfolioForm(busy) {
  return html`
    <form class="setup-inline-form" data-setup-portfolio-form>
      <div class="setup-form-heading">
        <div><p class="setup-path-eyebrow">Quick balance</p><h3>Add one current value.</h3></div>
        <p>This is enough for a first net-worth picture. Cost basis and transaction history can come later.</p>
      </div>
      <div class="setup-form-grid">
        <label class="setup-field"><span>What is it?</span><select name="kind" data-setup-asset-kind><option value="cash">Cash or savings</option><option value="investment">Investment account</option></select></label>
        ${raw(setupField('Account name', 'account_name', 'text', 'Main savings', { autocomplete: 'off' }))}
        ${raw(setupField('Current value', 'value_usd', 'number', '12500', { prefix: '$', min: '0', step: 'any' }))}
        <label class="setup-field" data-setup-symbol-field hidden><span>Ticker symbol</span><input name="symbol" type="text" placeholder="VTI" maxlength="24" autocomplete="off"><small>Use the main holding for this quick start.</small></label>
      </div>
      <div class="setup-form-footer"><button class="btn btn-primary" type="submit" ${busy ? 'disabled' : ''}>${busy ? 'Adding…' : 'Add current value'}</button></div>
    </form>
  `;
}

function renderFutureForm(busy) {
  return html`
    <form class="setup-inline-form" data-setup-future-form>
      <div class="setup-form-heading">
        <div><p class="setup-path-eyebrow">One direction</p><h3>Name a goal in plain language.</h3></div>
        <p>A rough amount is useful. The date can stay open until you know more.</p>
      </div>
      <div class="setup-form-grid">
        ${raw(setupField('What are you working toward?', 'goal_label', 'text', 'More flexibility at work'))}
        ${raw(setupField('Rough target', 'target_amount_usd', 'number', '50000', { prefix: '$', min: '0', step: '1' }))}
        ${raw(setupField('Target date', 'target_date', 'date', '', { required: false, hint: 'Optional; the first forecast can stay directional.' }))}
      </div>
      <div class="setup-form-footer">
        <button class="btn btn-primary" type="submit" ${busy ? 'disabled' : ''}>${busy ? 'Saving…' : 'Save this direction'}</button>
        <a class="link-editorial" href="#profile?section=goals">Use the guided interview</a>
      </div>
    </form>
  `;
}

function setupField(label, name, type, placeholder, options = {}) {
  const required = options.required === false ? '' : 'required';
  const attrs = [
    required,
    options.autocomplete ? `autocomplete="${esc(options.autocomplete)}"` : '',
    options.min != null ? `min="${esc(options.min)}"` : '',
    options.step ? `step="${esc(options.step)}"` : '',
  ].filter(Boolean).join(' ');
  return html`
    <label class="setup-field">
      <span>${label}</span>
      <span class="setup-input-wrap">${options.prefix ? html`<b aria-hidden="true">${options.prefix}</b>` : ''}<input name="${name}" type="${type}" placeholder="${placeholder}" ${raw(attrs)}></span>
      ${options.hint ? html`<small>${options.hint}</small>` : ''}
    </label>
  `;
}

function renderFirstPicture({ today, health, busy }) {
  const netWorth = finiteValue(health?.net_worth_usd ?? today?.net_worth_usd ?? today?.total_value_usd);
  const surplus = finiteValue(health?.monthly_surplus_usd ?? today?.monthly_surplus_usd);
  const runway = finiteValue(health?.emergency_fund_months ?? today?.emergency_fund_months);
  const profileStatus = String(today?.profile_readiness?.status || '').toLowerCase();
  const useful = !isEmptyWorkspace(today || {}, health);
  return html`
    <dl class="setup-picture ${useful ? '' : 'not-ready'}">
      ${raw(metric('Net worth', netWorth == null ? 'Not enough data' : fmtUsd(netWorth)))}
      ${raw(metric('Monthly room', surplus == null ? 'Not enough data' : fmtUsd(surplus)))}
      ${raw(metric('Emergency runway', runway == null ? 'Not enough data' : `${runway.toFixed(1)} months`))}
    </dl>
    <div class="setup-reliance ${profileStatus === 'ready' ? 'ready' : ''}">
      <p class="setup-reliance-label">What you can rely on</p>
      <p>
        ${profileStatus === 'ready'
          ? 'The core Profile evidence is ready. Portfolio and Plan details can still deepen the picture.'
          : `This is an early baseline, not a finished plan. Next evidence gap: ${esc(today?.profile_readiness?.next_gap_title || 'complete the core Profile')}.`}
      </p>
    </div>
    <div class="setup-actions">
      <button class="btn btn-primary setup-next" data-setup-finish ${busy ? 'disabled' : ''}>
        Finish Setup and open Today <span aria-hidden="true">→</span>
      </button>
      <a class="link-editorial" href="#profile">Keep improving the picture</a>
    </div>
  `;
}

function stageActions(active, { ready, next, nextLabel, openHref = '', openLabel = '', busy }) {
  return html`
    <div class="setup-actions">
      ${openHref ? html`<a class="btn btn-primary" href="${openHref}">${openLabel} <span aria-hidden="true">→</span></a>` : ''}
      ${ready ? html`
        <button class="btn ${openHref ? 'btn-ghost' : 'btn-primary'}" data-setup-next="${next}" data-setup-current="${active.id}" ${busy ? 'disabled' : ''}>
          ${nextLabel}
        </button>
      ` : html`
        <button class="link-editorial" data-setup-skip="${next}" data-setup-current="${active.id}" ${busy ? 'disabled' : ''}>
          Leave this for later
        </button>
      `}
    </div>
  `;
}

function principle(title, detail) {
  return html`
    <section class="setup-principle">
      <span class="setup-principle-mark" aria-hidden="true">§</span>
      <div><h3>${title}</h3><p>${detail}</p></div>
    </section>
  `;
}

function setupCheck(label, section, href) {
  const complete = section?.status === 'complete';
  return html`
    <a class="setup-check ${complete ? 'complete' : ''}" href="${href}">
      <span class="setup-check-mark" aria-hidden="true">${complete ? '✓' : '○'}</span>
      <span class="setup-check-copy"><strong>${label}</strong><small>${section?.detail || 'Add this when you are ready.'}</small></span>
      <span class="setup-check-arrow" aria-hidden="true">→</span>
    </a>
  `;
}

function pathCard(eyebrow, title, detail, href) {
  return html`
    <a class="setup-path" href="${href}">
      <span class="setup-path-eyebrow">${eyebrow}</span>
      <strong>${title}</strong>
      <span>${detail}</span>
      <span class="setup-path-arrow" aria-hidden="true">Open →</span>
    </a>
  `;
}

function metric(label, value) {
  return html`
    <div class="setup-metric">
      <dt>${label}</dt>
      <dd class="num-mono">${value}</dd>
    </div>
  `;
}

function sectionMap(onboarding) {
  const sections = Array.isArray(onboarding?.profile_readiness?.sections)
    ? onboarding.profile_readiness.sections
    : [];
  return new Map(sections.map(section => [section.key, section]));
}

function finiteValue(value) {
  const number = Number(value);
  return Number.isFinite(number) ? number : null;
}

export function missingFoundationKeys(onboarding = {}) {
  const sections = sectionMap(onboarding);
  return ['household', 'income', 'expenses', 'debt']
    .filter(key => sections.get(key)?.status !== 'complete');
}

export function buildFoundationProfile(profile = {}, fields = {}, missing = []) {
  const next = editableProfile(profile);
  const needs = new Set(missing);
  if (needs.has('household')) {
    const displayName = requiredText(fields.display_name, 'Enter the name you want BuildWealth to use.');
    next.household_members.push({
      id: uid(), display_name: displayName, relationship: 'self', birth_year: null,
      retirement_age: null, dependent: false, notes: '',
    });
  }
  if (needs.has('income')) {
    const annual = setupAmount(fields.annual_income_usd, 'Enter annual household income.');
    next.income_items.push({
      id: uid(), label: 'Household income', monthly_amount_usd: Math.round((annual / 12) * 100) / 100,
      source_type: 'setup_estimate', is_pre_tax: true, annual_growth_rate: null,
      start_date: null, end_date: null,
    });
  }
  if (needs.has('expenses')) {
    const monthly = setupAmount(fields.monthly_expenses_usd, 'Enter typical monthly spending.');
    next.expense_items.push({
      id: uid(), label: 'Representative household spending', monthly_amount_usd: monthly,
      category: 'general', is_fixed: false, inflation_rate: null, start_date: null, end_date: null,
    });
    next.flags.expenses_complete = true;
  }
  if (needs.has('debt')) {
    const balance = setupAmount(fields.debt_balance_usd, 'Enter a debt balance, or 0 if debt-free.');
    next.flags.no_debt = balance === 0;
    if (balance > 0) {
      next.debt_items.push({
        id: uid(), label: 'Current debt', balance_usd: balance, interest_rate: null,
        minimum_payment_usd: null, payoff_strategy: 'minimum', custom_monthly_payment_usd: null,
      });
    }
  }
  return next;
}

export function buildSetupPortfolioBody(fields = {}) {
  const kind = String(fields.kind || 'cash');
  const accountName = requiredText(fields.account_name, 'Enter a name for this account.');
  const value = setupAmount(fields.value_usd, 'Enter the current account value.');
  if (value <= 0) throw new Error('Current value must be greater than 0.');
  if (kind === 'investment') {
    const symbol = requiredText(fields.symbol, 'Enter the ticker symbol for the main investment.').toUpperCase();
    return {
      flow: 'investment', symbol, value_usd: value,
      new_account: { name: accountName, type: 'taxable' },
    };
  }
  return {
    flow: 'cash', amount_usd: value,
    new_account: { name: accountName, type: 'cash' },
  };
}

export function buildFutureProfile(profile = {}, fields = {}) {
  const next = editableProfile(profile);
  const label = requiredText(fields.goal_label, 'Describe what you are working toward.');
  const amount = setupAmount(fields.target_amount_usd, 'Enter a rough target amount.');
  next.goal_items.push({
    id: uid(), label, target_amount_usd: amount,
    target_date: String(fields.target_date || '').trim() || null,
    priority: 'medium', notes: 'Added during first-time Setup.',
  });
  next.flags.no_goals = false;
  return next;
}

function editableProfile(profile = {}) {
  const list = key => Array.isArray(profile?.[key]) ? profile[key].map(item => ({ ...item })) : [];
  return {
    household_members: list('household_members'),
    income_items: list('income_items'),
    expense_items: list('expense_items'),
    debt_items: list('debt_items'),
    goal_items: list('goal_items'),
    physical_assets: list('physical_assets'),
    tax_profile: { ...(profile?.tax_profile || {}) },
    investment_policy: { ...(profile?.investment_policy || {}) },
    flags: { ...(profile?.flags || {}) },
    notes: String(profile?.notes || ''),
    profile_metadata: { ...(profile?.profile_metadata || {}) },
  };
}

function requiredText(value, message) {
  const text = String(value || '').trim();
  if (!text) throw new Error(message);
  return text;
}

function setupAmount(value, message) {
  const text = String(value ?? '').trim();
  const amount = Number(text);
  if (!text || !Number.isFinite(amount) || amount < 0) throw new Error(message);
  return Math.round(amount * 100) / 100;
}

function uid() {
  if (typeof crypto !== 'undefined' && typeof crypto.randomUUID === 'function') return crypto.randomUUID();
  return `setup-${Math.random().toString(36).slice(2)}-${Date.now().toString(36)}`;
}
