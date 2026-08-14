// SETUP — a resumable first-outcome journey across Profile, Portfolio, and Plan.
// Progress belongs to the journey; financial readiness remains derived from
// Canonical State and is never fabricated by advancing or skipping a step.
//
// The flow runs with the app chrome collapsed (meta.focus, honoured by app.js):
// one bar carrying the only progress indicator, one question per screen, and one
// sticky footer carrying the only navigation. Nothing repeats between them.

import { api } from '../lib/api.js';
import { html, raw, $, setView, delegate } from '../lib/dom.js';
import { renderStageBody } from './setup/stages.js';
import { renderFlowBar, renderFlowFoot } from './setup/chrome.js';
import { deriveSetupJourney, SETUP_STEPS } from './setup/journey.js';
import {
  missingFoundationKeys,
  buildFoundationProfile,
  buildSetupPortfolioBody,
  buildFutureProfile,
} from './setup/profile_patch.js';

// Re-exported so callers and tests reach these through the view.
export {
  missingFoundationKeys,
  buildFoundationProfile,
  buildSetupPortfolioBody,
  buildFutureProfile,
};
export { deriveSetupJourney, SETUP_STEPS };

export const meta = {
  id: 'setup',
  label: 'Setup',
  numeral: '·',
  group: 'utility',
  focus: true,          // app.js collapses the sidebar and topbar for this view
};

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
  delegate(root, 'click', '[data-setup-back]', async (event, target) => {
    event.preventDefault();
    await moveToStep(target.dataset.setupBack);
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
    focusStage();
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


export function renderSetup({ progress, onboarding, today, health, profile, busy = false, error = '', notice = '' } = {}) {
  const journey = deriveSetupJourney({ progress, onboarding, today, health });
  const active = journey.find(step => step.current) || journey[0];
  return html`
    ${raw(renderFlowBar(journey, active, busy))}
    <article class="setup-card" aria-labelledby="setup-active-title">
      <div class="setup-card-copy setup-enter">
        <p class="setup-eyebrow">Step ${active.index + 1} of ${journey.length} · ${active.short}</p>
        <h2 id="setup-active-title" tabindex="-1">${active.title}</h2>
        <p class="setup-lede">${active.lede}</p>
      </div>
      ${error ? html`<p class="error-banner setup-enter" role="alert">${error}</p>` : ''}
      ${notice ? html`<p class="setup-notice setup-enter" role="status">${notice}</p>` : ''}
      <div class="setup-enter">${raw(renderStageBody(active, { onboarding, today, health, profile, busy }))}</div>
    </article>
    ${raw(renderFlowFoot(journey, active, busy))}
  `.toString();
}

function render() {
  const root = $('#setup-shell');
  if (!root) return;
  if (!ui.loaded && !ui.error) {
    setView(root, html`
      <div class="setup-loading" aria-live="polite">
        <span class="setup-loading-mark">§</span>
        <p>Opening your private household workspace…</p>
      </div>
    `);
    return;
  }
  setView(root, raw(renderSetup({ ...ui })));
}

// Advancing a step changes content 500px below the bar. Without this the screen
// appears not to have changed at all.
function focusStage() {
  const heading = $('#setup-active-title');
  if (!heading) return;
  heading.focus({ preventScroll: true });
  heading.scrollIntoView({ block: 'start', behavior: 'smooth' });
}
