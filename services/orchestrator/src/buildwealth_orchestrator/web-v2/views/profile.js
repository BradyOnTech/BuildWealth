// PROFILE — "Your Financial Picture".
// The user-facing expression of Context Intelligence: what does BuildWealth
// know, what's confirmed, what needs review, what is missing.
//
// The Profile view is composed of three concerns:
//   - masthead + completion stats        (top of page)
//   - tab navigation across sections     (#profile?section=...)
//   - section content                    (overview cards or editable tables)
//
// Section render is delegated to ./profile/*.js to keep this file under the
// 300-line ceiling.

import { api } from '../lib/api.js';
import { state, emit } from '../lib/state.js';
import { html, raw, $, esc, setView, delegate } from '../lib/dom.js';
import { fmtRelative } from '../lib/format.js';
import { skeleton } from '../lib/skeleton.js';
import { renderOverview } from './profile/overview.js';
import { renderTable, sectionForKey, TABLE_SECTIONS } from './profile/tables.js';
import { renderTaxes, submitTaxesForm } from './profile/taxes.js';
import { renderInvesting, submitInvestingForm, addRestricted, removeRestricted } from './profile/investing.js';
import { renderDataQuality, resolveConflict } from './profile/data_quality.js';
import { renderEstateReadiness, submitEstateReadiness } from './profile/estate.js';
import { renderSetupRail, onRailAction } from './profile/setup_rail.js';
import {
  renderLifeInterview,
  onInterviewAction,
  onInterviewField,
  onDraftPick,
  onDraftField,
  onDraftTimeline,
} from './profile/life_plans.js';

export const meta = {
  id: 'profile',
  label: 'Profile',
  numeral: 'VI',
  group: 'primary',
};

const SECTIONS = [
  { id: 'overview',     label: 'Overview',     kind: 'overview' },
  { id: 'household',    label: 'Household',    kind: 'table',   tableKey: 'household_members' },
  { id: 'income',       label: 'Income',       kind: 'table',   tableKey: 'income_items' },
  { id: 'benefits',     label: 'Benefits',     kind: 'table',   tableKey: 'benefit_items' },
  { id: 'expenses',     label: 'Expenses',     kind: 'table',   tableKey: 'expense_items' },
  { id: 'debt',         label: 'Debt',         kind: 'table',   tableKey: 'debt_items' },
  { id: 'goals',        label: 'Goals',        kind: 'goals',   tableKey: 'goal_items' },
  { id: 'taxes',        label: 'Taxes & status', kind: 'taxes' },
  { id: 'investing',    label: 'Investing',    kind: 'investing' },
  { id: 'assets',       label: 'Property & vehicles', kind: 'table', tableKey: 'physical_assets' },
  { id: 'insurance',    label: 'Insurance',    kind: 'table',   tableKey: 'insurance_policies' },
  { id: 'estate',       label: 'Estate',       kind: 'estate' },
  { id: 'data-quality', label: 'Data quality', kind: 'data-quality' },
];

export const ui = {
  loaded:       false,
  loadError:    null,
  saveError:    null,
  saving:       false,
  profile:      null,
  onboarding:   null,
  onboardingProgress: null,
  candidates:   [],          // pending profile context candidates
  financialHealth: null,
  section:      'overview',
  resetOpen:    false,
  resetLoading: false,
  resetSubmitting: false,
  resetPreview: null,
  resetError:   null,
};

export function template() {
  return html`
    <section class="page" id="profile-page">
      <div class="profile-shell" id="profile-shell">
        ${raw(masthead())}
        ${raw(skeletonBody())}
      </div>
    </section>
  `;
}

export async function init(params = {}) {
  const requested = String(params.section || 'overview').toLowerCase();
  ui.section = SECTIONS.some(s => s.id === requested) ? requested : 'overview';
  attachHandlers();
  await load();
}

async function load() {
  ui.loaded = false;
  ui.loadError = null;
  try {
    const [profile, onboarding, onboardingProgress, candidates, defaults, financialHealth] = await Promise.all([
      api.profile(),
      api.onboarding().catch(() => null),
      api.onboardingProgress().catch(() => null),
      api.contextCandidates({ lifecycleState: 'proposed' }).catch(() => []),
      api.profileDefaults().catch(() => null),
      api.financialHealth().catch(() => null),
    ]);
    ui.profile = ensureShape(profile);
    ui.suggestions = defaults?.suggestions || {};
    ui.onboarding = onboarding;
    ui.onboardingProgress = onboardingProgress;
    ui.financialHealth = financialHealth;
    ui.candidates = Array.isArray(candidates) ? candidates : (candidates?.items || []);
    ui.loaded = true;
    state.financialProfile = ui.profile;
    emit('profile:loaded', ui.profile);
  } catch (err) {
    ui.loadError = err.message || 'Could not load profile.';
    state.lastError = ui.loadError;
  }
  render();
}

export function getProfile() {
  return ui.profile;
}

// Resolves true when the server accepted the save; callers that mutated
// ui.profile optimistically must roll back when this returns false.
export async function persist({ optimistic = true } = {}) {
  if (!ui.profile) return false;
  ui.saving = true;
  ui.saveError = null;
  if (!optimistic) render();
  try {
    const saved = await api.updateProfile(ui.profile);
    ui.profile = ensureShape(saved);
    ui.financialHealth = await api.financialHealth().catch(() => ui.financialHealth);
    state.financialProfile = ui.profile;
    api.onboarding().then((o) => { ui.onboarding = o; render(); }).catch(() => {});
    api.profileDefaults()
      .then((d) => { ui.suggestions = d?.suggestions || {}; render(); })
      .catch(() => {});
    return true;
  } catch (err) {
    ui.saveError = err.message || 'Could not save profile.';
    return false;
  } finally {
    ui.saving = false;
    render();
  }
}

export async function replaceProfileSection(sectionKey, items) {
  if (!ui.profile || !sectionKey || !Array.isArray(items)) return false;
  ui.saving = true;
  ui.saveError = null;
  render();
  try {
    const saved = await api.updateProfileSection(sectionKey, {
      mode: 'replace',
      items,
      expected_updated_at: ui.profile.updated_at || null,
    });
    ui.profile = ensureShape(saved);
    ui.financialHealth = await api.financialHealth().catch(() => ui.financialHealth);
    state.financialProfile = ui.profile;
    emit('profile:loaded', ui.profile);
    return true;
  } catch (err) {
    ui.saveError = err?.detail?.message || err.message || 'Could not replace this profile section.';
    return false;
  } finally {
    ui.saving = false;
    render();
  }
}

export function render() {
  const shell = $('#profile-shell');
  if (!shell) return;
  if (ui.loadError) {
    setView(shell, html`
      ${raw(masthead())}
      <p class="error-banner">${ui.loadError}</p>
    `);
    return;
  }
  if (!ui.loaded) {
    setView(shell, html`
      ${raw(masthead())}
      ${raw(skeletonBody())}
    `);
    return;
  }

  const section = SECTIONS.find(s => s.id === ui.section) || SECTIONS[0];
  setView(shell, html`
    ${raw(masthead())}
    ${raw(reviewBanner())}
    ${raw(renderSetupRail(ui))}
    ${raw(tabs())}
    <section class="profile-section profile-section-${section.id}">
      ${raw(renderSectionBody(section))}
    </section>
    ${raw(resetRegistrationDialog())}
  `);
  syncResetDialog();
}

/* ─────────────  Composition  ───────────── */

function masthead() {
  const o = ui.onboarding;
  const readiness = o?.profile_readiness || null;
  const readinessReady = String(readiness?.status || '').toLowerCase() === 'ready';
  const readinessLabel = readinessReady
    ? 'Core profile ready'
    : readiness?.next_gap_title
      ? `Needs ${readiness.next_gap_title}`
      : 'In progress';
  const reviewCount = ui.candidates.length;
  const updated = ui.profile?.updated_at ? fmtRelative(ui.profile.updated_at) : null;

  return html`
    <header class="profile-masthead">
      <p class="profile-eyebrow">§ Foundation · Personal context</p>
      <h1 class="profile-title">Your financial picture</h1>
      <p class="profile-lede">
        BuildWealth uses this to personalize planning, Copilot, and review.
        Confirm what's true, mark what's missing, and let the rest become
        fewer surprises later.
      </p>
      <ul class="profile-stat-strip">
        ${raw(stat('Readiness', readinessLabel, readinessReady ? 'ok' : 'warn'))}
        ${raw(stat('Need review', reviewCount ? `${reviewCount}` : 'None', reviewCount ? 'attn' : 'ok'))}
        ${raw(stat('Last updated', updated || '—', 'quiet'))}
      </ul>
    </header>
  `;
}

function stat(label, value, tone) {
  return html`
    <li class="profile-stat ${tone || ''}">
      <span class="profile-stat-label">${label}</span>
      <span class="profile-stat-value">${value}</span>
    </li>
  `;
}

function reviewBanner() {
  if (!ui.candidates.length) return '';
  const first = ui.candidates[0];
  const more = ui.candidates.length - 1;
  return html`
    <aside class="profile-review-banner">
      <p class="profile-review-eyebrow">Review before relying on advice</p>
      <p class="profile-review-body">
        ${esc(first.headline || first.title || 'A suggested context update is waiting.')}
        ${more > 0 ? html`<span class="profile-review-more">· ${more} more in Inbox</span>` : ''}
      </p>
      <div class="profile-review-actions">
        <a class="link-editorial" href="#inbox" data-route>Review in Inbox</a>
        <a class="link-editorial muted" href="#copilot" data-route>Ask Copilot to explain</a>
      </div>
    </aside>
  `;
}

function tabs() {
  return html`
    <nav class="profile-tabs" aria-label="Profile sections">
      ${raw(SECTIONS.map(tab).join(''))}
    </nav>
  `;
}

function tab(section) {
  const isActive = section.id === ui.section;
  const count = section.kind === 'table' ? (ui.profile?.[section.tableKey]?.length || 0) : null;
  return html`
    <button class="profile-tab ${isActive ? 'active' : ''}"
            data-tab="${esc(section.id)}"
            aria-pressed="${isActive ? 'true' : 'false'}">
      <span class="profile-tab-label">${section.label}</span>
      ${count != null ? html`<span class="profile-tab-count">${count}</span>` : ''}
    </button>
  `;
}

function renderSectionBody(section) {
  if (section.kind === 'overview')     return renderOverview(ui);
  if (section.kind === 'taxes')        return renderTaxes(ui);
  if (section.kind === 'investing')    return renderInvesting(ui);
  if (section.kind === 'estate')       return renderEstateReadiness(ui);
  if (section.kind === 'data-quality') return renderDataQuality(ui);
  if (section.kind === 'table')        return renderTable(ui, sectionForKey(section.tableKey));
  // Goals: the life-plans interview sits above the editable table it feeds.
  if (section.kind === 'goals') {
    return html`
      ${raw(renderLifeInterview(ui))}
      ${raw(renderTable(ui, sectionForKey(section.tableKey)))}
    `;
  }
  return '';
}

function resetRegistrationDialog() {
  const preview = ui.resetPreview || null;
  const phrase = preview?.confirmation_phrase || 'reset and register again';
  return html`
    <dialog class="profile-reset-dialog" data-profile-reset-dialog aria-labelledby="profile-reset-title">
      <form method="dialog" class="profile-reset-dialog-shell" data-profile-reset-form>
        <header class="profile-reset-dialog-head">
          <div>
            <p class="profile-card-kicker">Protected reset</p>
            <h2 id="profile-reset-title">Register this profile again</h2>
          </div>
          <button class="profile-reset-close" type="button" data-profile-reset-close aria-label="Close reset dialog">×</button>
        </header>

        ${ui.resetLoading ? html`
          <p class="profile-reset-loading">Reviewing the current workspace…</p>
        ` : html`
          <p class="profile-reset-lede">
            This restarts the financial setup for your current workspace. It does not create a second
            account or change how you sign in.
          </p>
          <div class="profile-reset-split">
            <section>
              <h3>Cleared from the active workspace</h3>
              <ul>
                ${(preview?.will_clear || []).map(item => html`<li>${esc(item)}</li>`)}
              </ul>
            </section>
            <section>
              <h3>Kept for you</h3>
              <ul>
                ${(preview?.will_preserve || []).map(item => html`<li>${esc(item)}</li>`)}
              </ul>
            </section>
          </div>
          ${preview ? html`
            <p class="profile-reset-count">
              ${Number(preview.file_count || 0).toLocaleString('en-US')} active file${Number(preview.file_count || 0) === 1 ? '' : 's'}
              · ${formatBytes(Number(preview.size_bytes || 0))}
              · ${Number(preview.existing_backup_count || 0)} existing backup${Number(preview.existing_backup_count || 0) === 1 ? '' : 's'}
            </p>
          ` : ''}
          <label class="settings-field">
            <span class="settings-label">Type ${esc(phrase)} to confirm</span>
            <input class="settings-input" name="confirm" type="text" autocomplete="off" />
          </label>
          ${ui.resetError ? html`<p class="inline-warning">${esc(ui.resetError)}</p>` : ''}
          <div class="profile-reset-actions">
            <button class="btn btn-quiet" type="button" data-profile-reset-close>Keep my current data</button>
            <button class="btn btn-danger" type="submit" ${ui.resetSubmitting || !preview ? 'disabled' : ''}>
              ${ui.resetSubmitting ? 'Resetting…' : 'Create backup & restart setup'}
            </button>
          </div>
        `}
      </form>
    </dialog>
  `;
}

function syncResetDialog() {
  const dialog = document.querySelector('[data-profile-reset-dialog]');
  if (!(dialog instanceof HTMLDialogElement)) return;
  dialog.addEventListener('cancel', (event) => {
    event.preventDefault();
    if (ui.resetSubmitting) return;
    ui.resetOpen = false;
    ui.resetError = null;
    render();
  }, { once: true });
  if (ui.resetOpen && !dialog.open) dialog.showModal();
  if (!ui.resetOpen && dialog.open) dialog.close();
}

function formatBytes(value) {
  const bytes = Number(value || 0);
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

/* ─────────────  Events  ───────────── */

function attachHandlers() {
  const root = $('#profile-page');
  if (!root) return;

  delegate(root, 'click', '[data-tab]', (_, el) => {
    const next = el.getAttribute('data-tab');
    if (!next || next === ui.section) return;
    ui.section = next;
    history.replaceState(null, '', `#profile?section=${encodeURIComponent(next)}`);
    render();
  });

  delegate(root, 'click', '[data-profile-reset-open]', async (e) => {
    e.preventDefault();
    ui.resetOpen = true;
    ui.resetLoading = true;
    ui.resetPreview = null;
    ui.resetError = null;
    render();
    try {
      ui.resetPreview = await api.onboardingResetPreview();
    } catch (err) {
      ui.resetError = err?.message || 'Could not preview the workspace reset.';
    } finally {
      ui.resetLoading = false;
      render();
    }
  });

  delegate(root, 'click', '[data-profile-reset-close]', (e) => {
    e.preventDefault();
    if (ui.resetSubmitting) return;
    ui.resetOpen = false;
    ui.resetError = null;
    render();
  });

  delegate(root, 'submit', '[data-profile-reset-form]', async (e, form) => {
    e.preventDefault();
    if (ui.resetSubmitting || !ui.resetPreview) return;
    const payload = Object.fromEntries(new FormData(form).entries());
    ui.resetSubmitting = true;
    ui.resetError = null;
    render();
    try {
      const result = await api.resetOnboarding({ confirm: String(payload.confirm || '') });
      window.location.replace(result?.next_path || '/v2#setup');
    } catch (err) {
      ui.resetError = err?.message || 'Could not reset this workspace.';
      ui.resetSubmitting = false;
      render();
    }
  });

  // Table-level row events. Each table sub-view declares data-table-action,
  // data-table-key, data-row-id; we route them to the table module here so
  // that file stays UI-only.
  delegate(root, 'click', '[data-table-action]', (e, el) => {
    e.preventDefault();
    const handler = TABLE_SECTIONS.find(s => s.key === el.getAttribute('data-table-key'));
    if (!handler) return;
    handler.onAction(ui, el.getAttribute('data-table-action'), el.dataset);
  });

  delegate(root, 'click', '[data-table-add]', (e, el) => {
    e.preventDefault();
    const handler = TABLE_SECTIONS.find(s => s.key === el.getAttribute('data-table-add'));
    if (!handler) return;
    handler.onAdd(ui, root);
  });

  delegate(root, 'click', '[data-expenses-complete]', async (e, el) => {
    e.preventDefault();
    if (!ui.profile) return;
    ui.profile.flags = {
      ...(ui.profile.flags || {}),
      expenses_complete: el.getAttribute('data-expenses-complete') === 'true',
    };
    await persist();
  });

  // Guided setup rail: skip / dismiss / doc-capture toggle / use-estimates /
  // apply-candidate all route through one dispatcher in setup_rail.js.
  delegate(root, 'click', '[data-rail-action]', (e, el) => {
    e.preventDefault();
    onRailAction(ui, el.getAttribute('data-rail-action'), el.dataset);
  });

  delegate(root, 'click', '[data-mix-preset]', (e, el) => {
    e.preventDefault();
    let mix = null;
    try { mix = JSON.parse(el.getAttribute('data-mix-preset') || ''); } catch { return; }
    if (!mix || typeof mix !== 'object') return;
    for (const [key, value] of Object.entries(mix)) {
      const input = root.querySelector(`[data-investing-target-class="${key}"]`);
      if (input) {
        input.value = String(value);
        input.dispatchEvent(new Event('input', { bubbles: true }));
      }
    }
  });

  delegate(root, 'click', '[data-use-suggestion]', async (e, el) => {
    e.preventDefault();
    const { applySuggestionClick } = await import('./profile/suggestions.js');
    applySuggestionClick(el, root);
  });

  delegate(root, 'click', '[data-taxes-save]', (e) => {
    e.preventDefault();
    submitTaxesForm(ui);
  });

  delegate(root, 'click', '[data-investing-save]', (e) => {
    e.preventDefault();
    submitInvestingForm(ui);
  });

  delegate(root, 'click', '[data-estate-save]', (e) => {
    e.preventDefault();
    submitEstateReadiness(ui, root);
  });

  delegate(root, 'click', '[data-investing-add]', (e, el) => {
    e.preventDefault();
    addRestricted(ui, el.getAttribute('data-investing-add'));
  });

  delegate(root, 'click', '[data-investing-remove]', (e, el) => {
    e.preventDefault();
    removeRestricted(ui, el.getAttribute('data-investing-remove'), el.getAttribute('data-value'));
  });

  delegate(root, 'keydown', '[data-investing-add-input]', (e, el) => {
    if (e.key === 'Enter') {
      e.preventDefault();
      addRestricted(ui, el.getAttribute('data-investing-add-input'));
    }
  });

  delegate(root, 'click', '[data-interview-action]', (e, el) => {
    e.preventDefault();
    onInterviewAction(ui, el.getAttribute('data-interview-action'));
  });

  delegate(root, 'change', '[data-interview-field]', (_, el) => onInterviewField(el));
  delegate(root, 'change', '[data-draft-pick]', (_, el) => onDraftPick(el));
  delegate(root, 'change', '[data-draft-timeline]', (_, el) => onDraftTimeline(el));
  delegate(root, 'change', '[data-draft-field]', (_, el) => onDraftField(el));
  delegate(root, 'input', '[data-draft-field]', (_, el) => onDraftField(el));

  delegate(root, 'click', '[data-conflict-action]', (e, el) => {
    e.preventDefault();
    const action = el.getAttribute('data-conflict-action');
    const id = el.getAttribute('data-candidate-id');
    if (!action || !id) return;
    resolveConflict(id, action);
  });
}

/* ─────────────  Plumbing  ───────────── */

// Exported for setup_rail.js, which reloads the profile after applying an
// inference candidate and must normalize it the same way load() does.
export function ensureShape(profile) {
  const next = profile && typeof profile === 'object' ? { ...profile } : {};
  for (const key of [
    'household_members',
    'income_items',
    'expense_items',
    'debt_items',
    'goal_items',
    'physical_assets',
    'insurance_policies',
    'benefit_items',
  ]) {
    if (!Array.isArray(next[key])) next[key] = [];
  }
  if (!next.tax_profile || typeof next.tax_profile !== 'object') next.tax_profile = {};
  if (!next.flags || typeof next.flags !== 'object') next.flags = {};
  if (!next.estate_readiness || typeof next.estate_readiness !== 'object') next.estate_readiness = {};
  return next;
}

/* ─────────────  Skeletons  ───────────── */

function skeletonBody() {
  return html`
    ${skeleton('36px', { width: '60%' })}
    ${skeleton('240px', { marginTop: '24px' })}
  `;
}
