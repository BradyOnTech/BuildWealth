// SETUP · stage bodies.
// One screen per step. Each stage renders its own question and nothing else —
// the flow bar owns progress and the sticky footer owns navigation, so no stage
// repeats either. Fields carry visible labels and hints rather than placeholder
// numbers, which read as pre-filled values when the subject is money.

import { html, raw, esc } from '../../lib/dom.js';
import { fmtUsd } from '../../lib/format.js';
import { isEmptyWorkspace } from '../today.js';
import { missingFoundationKeys, sectionMap } from './profile_patch.js';

export function renderStageBody(active, context) {
  if (active.id === 'welcome')   return renderWelcome();
  if (active.id === 'foundation') return renderFoundation(context);
  if (active.id === 'portfolio')  return renderPortfolio(active, context);
  if (active.id === 'future')     return renderFuture(active, context);
  return renderFirstPicture(context);
}

function renderWelcome() {
  return html`
    <div class="setup-principles">
      ${raw(principle('Private by design', 'Your information stays inside this household workspace and remains exportable.'))}
      ${raw(principle('Confirmation over interrogation', 'BuildWealth labels estimates and asks you to correct them instead of pretending they are facts.'))}
      ${raw(principle('Evidence before confidence', 'Missing inputs stay visible. Setup never turns incomplete information into a confident recommendation.'))}
    </div>
  `;
}

// The four foundation items each show their own readiness detail and a deep
// link, but the quick form below covers all of them without leaving the flow.
// Production offered the links *instead* of a return path, which stranded
// anyone who followed one.
function renderFoundation({ onboarding, busy }) {
  const sections = sectionMap(onboarding);
  const missing = missingFoundationKeys(onboarding);
  const items = [
    ['household', 'Household', 'household'],
    ['income', 'Income', 'income'],
    ['expenses', 'Representative expenses', 'expenses'],
    ['debt', 'Debt or debt-free answer', 'debt'],
  ];
  return html`
    <ul class="setup-checklist">
      ${raw(items.map(([key, label, section]) => setupCheck(label, sections.get(key), section)).join(''))}
    </ul>
    ${missing.length ? raw(renderFoundationForm(missing, busy)) : ''}
  `;
}

function renderPortfolio(active, { onboarding, busy }) {
  const snapshot = (Array.isArray(onboarding?.steps) ? onboarding.steps : [])
    .find(step => step.id === 'snapshot');
  const connected = active.evidenceReady;
  return html`
    ${connected ? '' : raw(renderPortfolioForm(busy))}
    <p class="setup-evidence ${connected ? 'ready' : ''}">
      <span class="setup-evidence-mark" aria-hidden="true">${connected ? '✓' : '○'}</span>
      ${connected ? esc(snapshot?.detail || 'Portfolio context is available.') : 'No portfolio snapshot yet. You can continue and add it later.'}
    </p>
    <div class="setup-alternates">
      <span>Have a statement or need more detail?</span>
      <a href="#import-sync?section=statement">Import and reconcile</a>
      <a href="#portfolio?section=maintenance">Open full Portfolio</a>
    </div>
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
      <span class="setup-evidence-mark" aria-hidden="true">${active.evidenceReady ? '✓' : '○'}</span>
      ${esc(goals?.detail || 'No goal or future event is on record yet.')}
    </p>
  `;
}

function renderFirstPicture({ today, health }) {
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
  `;
}

/* ─────────────  Forms  ───────────── */

function renderFoundationForm(missing, busy) {
  const needs = new Set(missing);
  return html`
    <form class="setup-inline-form" data-setup-foundation-form>
      <div class="setup-form-heading">
        <p class="setup-path-eyebrow">Quick foundation</p>
        <h3>Fill only what is missing.</h3>
        <p class="setup-form-note">These totals create editable starter records; they do not replace details already on file.</p>
      </div>
      <div class="setup-form-grid">
        ${needs.has('household') ? raw(setupField('Your name', 'display_name', 'text', { autocomplete: 'name', hint: 'What BuildWealth should call you.' })) : ''}
        ${needs.has('income') ? raw(setupField('Annual household income', 'annual_income_usd', 'number', { prefix: '$', hint: 'Before tax; an estimate is fine.', min: '0', step: '1' })) : ''}
        ${needs.has('expenses') ? raw(setupField('Typical monthly spending', 'monthly_expenses_usd', 'number', { prefix: '$', hint: 'One representative total for now.', min: '0', step: '1' })) : ''}
        ${needs.has('debt') ? raw(setupField('Current debt balance', 'debt_balance_usd', 'number', { prefix: '$', hint: 'Enter 0 if you have no current debt.', min: '0', step: '1' })) : ''}
      </div>
      <div class="setup-form-footer">
        <button class="btn btn-primary" type="submit" ${busy ? 'disabled' : ''}>${busy ? 'Saving…' : 'Save foundation'}</button>
      </div>
    </form>
  `;
}

function renderPortfolioForm(busy) {
  return html`
    <form class="setup-inline-form" data-setup-portfolio-form>
      <div class="setup-form-heading">
        <p class="setup-path-eyebrow">Quick balance</p>
        <h3>Add one current value.</h3>
        <p class="setup-form-note">This is enough for a first net-worth picture. Cost basis and transaction history can come later.</p>
      </div>
      <div class="setup-form-grid">
        <label class="setup-field"><span>What is it?</span>
          <span class="setup-input-wrap"><select name="kind" data-setup-asset-kind><option value="cash">Cash or savings</option><option value="investment">Investment account</option></select></span>
        </label>
        ${raw(setupField('Account name', 'account_name', 'text', { autocomplete: 'off', placeholder: 'Main savings' }))}
        ${raw(setupField('Current value', 'value_usd', 'number', { prefix: '$', min: '0', step: 'any' }))}
        <label class="setup-field" data-setup-symbol-field hidden><span>Ticker symbol</span>
          <span class="setup-input-wrap"><input name="symbol" type="text" placeholder="VTI" maxlength="24" autocomplete="off"></span>
          <small>Use the main holding for this quick start.</small>
        </label>
      </div>
      <div class="setup-form-footer"><button class="btn btn-primary" type="submit" ${busy ? 'disabled' : ''}>${busy ? 'Adding…' : 'Add current value'}</button></div>
    </form>
  `;
}

function renderFutureForm(busy) {
  return html`
    <form class="setup-inline-form" data-setup-future-form>
      <div class="setup-form-heading">
        <p class="setup-path-eyebrow">One direction</p>
        <h3>Name a goal in plain language.</h3>
        <p class="setup-form-note">A rough amount is useful. The date can stay open until you know more.</p>
      </div>
      <div class="setup-form-grid">
        ${raw(setupField('What are you working toward?', 'goal_label', 'text', { placeholder: 'More flexibility at work', span: true }))}
        ${raw(setupField('Rough target', 'target_amount_usd', 'number', { prefix: '$', min: '0', step: '1' }))}
        ${raw(setupField('Target date', 'target_date', 'date', { required: false, optional: true, hint: 'The first forecast can stay directional.' }))}
      </div>
      <div class="setup-form-footer">
        <button class="btn btn-primary" type="submit" ${busy ? 'disabled' : ''}>${busy ? 'Saving…' : 'Save this direction'}</button>
        <a class="link-editorial" href="#profile?section=goals">Use the guided interview</a>
      </div>
    </form>
  `;
}

// Money fields carry no placeholder: a greyed "85000" inside an empty amount
// box reads as a value already entered.
function setupField(label, name, type, options = {}) {
  const attrs = [
    options.required === false ? '' : 'required',
    options.autocomplete ? `autocomplete="${esc(options.autocomplete)}"` : '',
    options.placeholder ? `placeholder="${esc(options.placeholder)}"` : '',
    options.min != null ? `min="${esc(options.min)}"` : '',
    options.step ? `step="${esc(options.step)}"` : '',
  ].filter(Boolean).join(' ');
  return html`
    <label class="setup-field ${options.span ? 'setup-field-span' : ''}">
      <span>${label}${options.optional ? html`<i> — optional</i>` : ''}</span>
      <span class="setup-input-wrap">${options.prefix ? html`<b aria-hidden="true">${options.prefix}</b>` : ''}<input name="${name}" type="${type}" ${raw(attrs)}></span>
      ${options.hint ? html`<small>${options.hint}</small>` : ''}
    </label>
  `;
}

/* ─────────────  Pieces  ───────────── */

function principle(title, detail) {
  return html`
    <section class="setup-principle">
      <span class="setup-principle-mark" aria-hidden="true">§</span>
      <div><h3>${title}</h3><p>${detail}</p></div>
    </section>
  `;
}

function setupCheck(label, section, sectionId) {
  const complete = section?.status === 'complete';
  return html`
    <li class="setup-check ${complete ? 'complete' : ''}">
      <span class="setup-check-mark" aria-hidden="true">${complete ? '✓' : '○'}</span>
      <span class="setup-check-copy">
        <strong>${label}</strong>
        <small>${section?.detail || 'Add this when you are ready.'}</small>
      </span>
      <a class="setup-check-link" href="#profile?section=${esc(sectionId)}">Open in Profile</a>
    </li>
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

function finiteValue(value) {
  const number = Number(value);
  return Number.isFinite(number) ? number : null;
}
