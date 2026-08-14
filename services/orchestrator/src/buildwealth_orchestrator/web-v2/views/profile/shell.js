// Profile · page chrome — compact header, grouped section rail, reset dialog.
//
// The header replaces a ~400px editorial masthead: on a working surface the
// readiness meter is the headline. The rail replaces a flat, wrapping 13-tab
// strip that rendered below an embedded editor and so was invisible on load;
// grouping it also gives the set somewhere to grow.

import { html, raw, esc } from '../../lib/dom.js';
import { fmtRelative } from '../../lib/format.js';
import { readinessCount } from './readiness.js';

// Groups exist so the list stays scannable past a dozen entries. Ids must match
// views/profile.js SECTIONS — routing validates ?section= against them.
export const SECTION_GROUPS = [
  { label: 'Overview',    ids: ['overview'] },
  { label: 'Foundation',  ids: ['household', 'income', 'expenses', 'debt', 'goals'] },
  { label: 'Position',    ids: ['assets', 'benefits', 'insurance', 'estate'] },
  { label: 'Preferences', ids: ['taxes', 'investing'] },
  { label: 'Sources',     ids: ['data-quality'] },
];

export function renderHeader(ui) {
  const readiness = ui.onboarding?.profile_readiness || null;
  const { complete, total } = readinessCount(ui.onboarding);
  const ready = String(readiness?.status || '').toLowerCase() === 'ready';
  const pct = total ? Math.round((complete / total) * 100) : (ready ? 100 : 0);
  const updated = ui.profile?.updated_at ? fmtRelative(ui.profile.updated_at) : null;
  const reviewCount = ui.candidates.length;

  return html`
    <header class="profile-header">
      <div class="profile-header-id">
        <p class="profile-eyebrow">§ Foundation · Personal context</p>
        <h1 class="profile-title">Your financial picture</h1>
        <p class="profile-subline">
          ${updated ? html`Updated ${updated}` : 'Not yet saved'}
          ·
          ${reviewCount
            ? html`<a class="link-editorial" href="#inbox" data-route>${reviewCount} to review</a>`
            : 'nothing pending review'}
        </p>
      </div>
      <div class="profile-readiness">
        <div class="profile-readiness-row">
          <span class="profile-readiness-label">Core profile</span>
          <span class="profile-readiness-value num-mono">
            ${total ? `${complete} of ${total} sections` : ready ? 'Ready' : 'In progress'}
          </span>
        </div>
        <div class="profile-readiness-meter" role="img"
             aria-label="${total ? `${complete} of ${total} core sections complete` : 'Readiness in progress'}">
          <i style="width:${pct}%"></i>
        </div>
        <div class="profile-readiness-row">
          <span class="profile-readiness-next ${ready ? 'ready' : ''}">
            ${ready ? 'Core evidence ready' : readiness?.next_gap_title ? `Next: ${esc(readiness.next_gap_title)}` : 'Next: start setup'}
          </span>
          <a class="link-editorial" href="#setup" data-route>${ready ? 'Review setup' : 'Resume setup'}</a>
        </div>
      </div>
    </header>
  `;
}

export function renderRail(ui, sections) {
  const byId = new Map(sections.map(section => [section.id, section]));
  return html`
    <nav class="profile-rail" aria-label="Profile sections">
      ${raw(SECTION_GROUPS.map(group => {
        const items = group.ids.map(id => byId.get(id)).filter(Boolean);
        if (!items.length) return '';
        return html`
          <div class="profile-rail-group">
            <p class="profile-rail-label">${group.label}</p>
            ${raw(items.map(section => railItem(ui, section)).join(''))}
          </div>
        `;
      }).join(''))}
    </nav>
  `;
}

function railItem(ui, section) {
  const active = section.id === ui.section;
  const status = sectionStatus(ui, section);
  const count = section.kind === 'table' || section.kind === 'goals'
    ? (ui.profile?.[section.tableKey]?.length || 0)
    : null;
  return html`
    <a class="profile-rail-item ${active ? 'active' : ''}"
       href="#profile?section=${esc(section.id)}"
       data-tab="${esc(section.id)}"
       aria-current="${active ? 'page' : 'false'}">
      <span class="profile-mark profile-mark-${status}" aria-hidden="true">${status === 'complete' ? '✓' : status === 'attention' ? '!' : '·'}</span>
      <span class="profile-rail-text">${section.label}</span>
      ${count != null ? html`<span class="profile-rail-count ${count ? '' : 'zero'}">${count}</span>` : ''}
    </a>
  `;
}

// A section's mark comes from server readiness when it has an opinion, and
// otherwise from whether the section holds anything at all. "0" alone never
// reads as "needs attention".
function sectionStatus(ui, section) {
  const sections = ui.onboarding?.profile_readiness?.sections;
  const readinessKey = RAIL_READINESS_KEYS[section.id];
  if (Array.isArray(sections) && readinessKey) {
    const match = sections.find(s => s.key === readinessKey);
    if (match?.status === 'complete') return 'complete';
    if (match?.status === 'attention') return 'attention';
    if (match) return 'todo';
  }
  if (section.kind === 'table' || section.kind === 'goals') {
    return (ui.profile?.[section.tableKey]?.length || 0) > 0 ? 'complete' : 'todo';
  }
  if (section.id === 'overview') {
    return ui.candidates.length ? 'attention' : 'complete';
  }
  if (section.id === 'estate') return estateStatus(ui.profile);
  // Data quality is clean exactly when nothing is waiting on a human decision.
  if (section.id === 'data-quality') return ui.candidates.length ? 'attention' : 'complete';
  return 'todo';
}

const RAIL_READINESS_KEYS = {
  household: 'household',
  income: 'income',
  expenses: 'expenses',
  debt: 'debt',
  goals: 'goals',
  taxes: 'tax_profile',
  investing: 'investment_policy',
  assets: 'physical_assets',
};

// Estate readiness is answered rather than counted: four questions, each of
// which can be complete, in progress, or unanswered.
const ESTATE_KEYS = ['will_status', 'trust_status', 'power_of_attorney_status', 'healthcare_directive_status'];

function estateStatus(profile) {
  const estate = profile?.estate_readiness;
  if (!estate || typeof estate !== 'object') return 'todo';
  const answered = ESTATE_KEYS.filter(key => estate[key] && estate[key] !== 'unknown');
  if (!answered.length) return 'todo';
  return answered.length === ESTATE_KEYS.length && ESTATE_KEYS.every(key => estate[key] === 'complete')
    ? 'complete'
    : 'attention';
}

/* ─────────────  Protected reset  ───────────── */

export function renderResetDialog(ui) {
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

function formatBytes(value) {
  const bytes = Number(value || 0);
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}
