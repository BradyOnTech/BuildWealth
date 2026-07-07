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
import { renderOverview } from './profile/overview.js';
import { renderTable, sectionForKey, TABLE_SECTIONS } from './profile/tables.js';
import { renderTaxes, submitTaxesForm } from './profile/taxes.js';
import { renderInvesting, submitInvestingForm, addRestricted, removeRestricted } from './profile/investing.js';
import { renderDataQuality, resolveConflict } from './profile/data_quality.js';
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
  numeral: 'V',
  group: 'primary',
};

const SECTIONS = [
  { id: 'overview',     label: 'Overview',     kind: 'overview' },
  { id: 'income',       label: 'Income',       kind: 'table',   tableKey: 'income_items' },
  { id: 'expenses',     label: 'Expenses',     kind: 'table',   tableKey: 'expense_items' },
  { id: 'debt',         label: 'Debt',         kind: 'table',   tableKey: 'debt_items' },
  { id: 'goals',        label: 'Goals',        kind: 'goals',   tableKey: 'goal_items' },
  { id: 'taxes',        label: 'Taxes',        kind: 'taxes' },
  { id: 'investing',    label: 'Investing',    kind: 'investing' },
  { id: 'assets',       label: 'Assets',       kind: 'table',   tableKey: 'physical_assets' },
  { id: 'data-quality', label: 'Data quality', kind: 'data-quality' },
];

export const ui = {
  loaded:       false,
  loadError:    null,
  saveError:    null,
  saving:       false,
  profile:      null,
  onboarding:   null,
  candidates:   [],          // pending profile context candidates
  section:      'overview',
};

export function template() {
  return html`
    <section class="page" id="profile-page">
      <div class="profile-shell" id="profile-shell">
        ${raw(skeleton())}
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
    const [profile, onboarding, candidates] = await Promise.all([
      api.profile(),
      api.onboarding().catch(() => null),
      api.contextCandidates({ lifecycleState: 'proposed' }).catch(() => []),
    ]);
    ui.profile = ensureShape(profile);
    ui.onboarding = onboarding;
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
    state.financialProfile = ui.profile;
    api.onboarding().then((o) => { ui.onboarding = o; render(); }).catch(() => {});
    return true;
  } catch (err) {
    ui.saveError = err.message || 'Could not save profile.';
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
    ${raw(tabs())}
    <section class="profile-section profile-section-${section.id}">
      ${raw(renderSectionBody(section))}
    </section>
  `);
}

/* ─────────────  Composition  ───────────── */

function masthead() {
  const o = ui.onboarding;
  const completion = o ? Math.round(Number(o.completion_percent || 0)) : null;
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
        ${raw(stat('Completeness', completion != null ? `${completion}%` : '—', completionTone(completion)))}
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

function completionTone(pct) {
  if (pct == null) return 'quiet';
  if (pct >= 80) return 'ok';
  if (pct >= 50) return 'warn';
  return 'attn';
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
  if (section.kind === 'data-quality') return renderDataQuality(ui);
  if (section.kind === 'table')        return renderTable(ui, sectionForKey(section.tableKey));
  // Goals: the life-plans interview sits above the editable table it feeds.
  if (section.kind === 'goals') {
    return html`
      ${raw(renderLifeInterview(ui))}
      ${raw(renderTable(ui, sectionForKey(section.tableKey)))}
    `;
  }
  if (section.kind === 'placeholder')  return renderPlaceholder(section);
  return '';
}

function renderPlaceholder(section) {
  return html`
    <div class="placeholder">
      <span class="glyph">¶</span>
      <h2>${section.label}</h2>
      <p>${section.blurb || 'Coming soon.'}</p>
    </div>
  `;
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

  delegate(root, 'click', '[data-taxes-save]', (e) => {
    e.preventDefault();
    submitTaxesForm(ui);
  });

  delegate(root, 'click', '[data-investing-save]', (e) => {
    e.preventDefault();
    submitInvestingForm(ui);
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

function ensureShape(profile) {
  const next = profile && typeof profile === 'object' ? { ...profile } : {};
  for (const key of ['household_members', 'income_items', 'expense_items', 'debt_items', 'goal_items', 'physical_assets']) {
    if (!Array.isArray(next[key])) next[key] = [];
  }
  if (!next.tax_profile || typeof next.tax_profile !== 'object') next.tax_profile = {};
  if (!next.flags || typeof next.flags !== 'object') next.flags = {};
  return next;
}

/* ─────────────  Skeletons  ───────────── */

function skeleton() {
  return html`
    ${raw(masthead())}
    ${raw(skeletonBody())}
  `;
}

function skeletonBody() {
  return html`
    <div class="skeleton" style="height: 36px; width: 60%;">.</div>
    <div class="skeleton" style="height: 240px; margin-top: 24px;">.</div>
  `;
}
