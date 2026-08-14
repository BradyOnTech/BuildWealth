// PROFILE — "Your Financial Picture".
// The user-facing expression of Context Intelligence: what does BuildWealth
// know, what's confirmed, what needs review, what is missing.
//
// The Profile view is a two-pane workspace:
//   - compact sticky header carrying the readiness meter   (./profile/shell.js)
//   - grouped section rail, sticky and visible on load     (./profile/shell.js)
//   - a "Needs you" band, capped at three gaps             (./profile/needs.js)
//   - one section at a time in the pane                    (./profile/*.js)
//
// Section render is delegated to ./profile/*.js to keep this file under the
// 300-line ceiling.

import { api } from '../lib/api.js';
import { state, emit } from '../lib/state.js';
import { html, raw, $, esc, setView, delegate } from '../lib/dom.js';
import { skeleton } from '../lib/skeleton.js';
import { renderOverview } from './profile/overview.js';
import { renderTable, sectionForKey, TABLE_SECTIONS } from './profile/tables.js';
import { renderTaxes, submitTaxesForm } from './profile/taxes.js';
import { renderInvesting, submitInvestingForm, addRestricted, removeRestricted } from './profile/investing.js';
import { renderDataQuality, resolveConflict } from './profile/data_quality.js';
import { renderEstateReadiness, submitEstateReadiness } from './profile/estate.js';
import { renderHeader, renderRail, renderResetDialog } from './profile/shell.js';
import { renderNeedsBand, onNeedsAction } from './profile/needs.js';
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
    setView(shell, html`<p class="error-banner">${ui.loadError}</p>`);
    return;
  }
  if (!ui.loaded) {
    setView(shell, raw(skeletonBody()));
    return;
  }

  const section = SECTIONS.find(s => s.id === ui.section) || SECTIONS[0];
  setView(shell, html`
    ${raw(renderHeader(ui))}
    <div class="profile-workspace">
      ${raw(renderRail(ui, SECTIONS))}
      <div class="profile-pane">
        ${raw(renderNeedsBand(ui))}
        <section class="profile-section profile-section-${section.id}"
                 id="profile-section" aria-label="${esc(section.label)}">
          ${raw(renderSectionBody(section))}
        </section>
      </div>
    </div>
    ${raw(renderResetDialog(ui))}
  `);
  syncResetDialog();
  trackHeaderHeight();
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

/* ─────────────  Events  ───────────── */

function attachHandlers() {
  const root = $('#profile-page');
  if (!root) return;

  delegate(root, 'click', '[data-tab]', (event, el) => {
    // Rail items are real anchors so they can be opened in a new tab and read by
    // assistive tech as links. Only take over the plain left-click.
    if (isModifiedClick(event)) return;
    const next = el.getAttribute('data-tab');
    event.preventDefault();
    if (!next || next === ui.section) return;
    showSection(next);
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

  // "Needs you" band: dismiss / doc-capture toggle / use-estimates /
  // mark-no-debt / defer-goals / apply-candidate all route through one
  // dispatcher in needs.js.
  delegate(root, 'click', '[data-needs-action]', (e, el) => {
    e.preventDefault();
    onNeedsAction(ui, el.getAttribute('data-needs-action'), el.dataset);
  });

  // A band row's "Open <section>" is an in-page jump, not a reload.
  delegate(root, 'click', '[data-needs-goto]', (e, el) => {
    if (isModifiedClick(e)) return;
    e.preventDefault();
    const next = el.getAttribute('data-needs-goto');
    if (!next || !SECTIONS.some(s => s.id === next)) return;
    showSection(next);
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

  // Overview rows keep their rationale behind a "?" so the value stays legible.
  delegate(root, 'click', '[data-line-why]', (e, el) => {
    e.preventDefault();
    const detail = el.parentElement?.querySelector('.profile-line-detail');
    if (!detail) return;
    const open = detail.hasAttribute('hidden');
    detail.toggleAttribute('hidden', !open);
    el.setAttribute('aria-expanded', String(open));
  });

  delegate(root, 'click', '[data-conflict-action]', (e, el) => {
    e.preventDefault();
    const action = el.getAttribute('data-conflict-action');
    const id = el.getAttribute('data-candidate-id');
    if (!action || !id) return;
    resolveConflict(id, action);
  });
}

// Cmd/Ctrl/Shift/middle-click must reach the browser so rail anchors can open in
// a new tab.
function isModifiedClick(event) {
  return event.metaKey || event.ctrlKey || event.shiftKey || event.altKey || event.button !== 0;
}

function showSection(next) {
  ui.section = next;
  history.replaceState(null, '', `#profile?section=${encodeURIComponent(next)}`);
  render();
  focusSection();
}

// Switching sections replaces the pane's whole contents. Without moving focus,
// keyboard and screen-reader users stay parked on the rail with no signal that
// anything changed; without scrolling, sighted users land mid-page in the new
// section with its header off-screen.
function focusSection() {
  // .app-main is height-locked with overflow hidden, so .content is the
  // scroller — window.scrollTo(0, 0) does nothing on this shell.
  document.querySelector('.content')?.scrollTo({ top: 0, behavior: 'smooth' });
  const heading = $('#profile-section')?.querySelector('h2, h3');
  if (!heading) return;
  heading.setAttribute('tabindex', '-1');
  heading.focus({ preventScroll: true });
}

// ── P1: the rail is sticky below a sticky header whose height is not a
// constant: it is 114px normally and 218px between 901px and 969px, where the
// header's two flex children wrap. A hard-coded offset let the header cover —
// and swallow clicks on — the first rail items in that band. Measure instead.
function trackHeaderHeight() {
  const shell = $('#profile-shell');
  const header = shell?.querySelector('.profile-header');
  if (!shell || !header || typeof ResizeObserver === 'undefined') return;
  const apply = () => shell.style.setProperty(
    '--profile-header-h', `${Math.ceil(header.getBoundingClientRect().height)}px`);
  apply();
  headerObserver?.disconnect();
  headerObserver = new ResizeObserver(apply);
  headerObserver.observe(header);
}

let headerObserver = null;

/* ─────────────  Plumbing  ───────────── */

// Exported for needs.js, which reloads the profile after applying an inference
// candidate and must normalize it the same way load() does.
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
