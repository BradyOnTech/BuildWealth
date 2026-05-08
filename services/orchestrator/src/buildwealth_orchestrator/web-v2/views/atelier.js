// ATELIER — foundation/admin shelf.
// First v2 slice: trust and durability visibility from existing protection,
// backup, checkpoint, and audit endpoints.

import { api } from '../lib/api.js';
import { html, raw, setView, $, esc } from '../lib/dom.js';
import { fmtDateLong } from '../lib/format.js';

export const meta = {
  id: 'atelier',
  label: 'Data & Recovery',
  numeral: '·',
  group: 'utility',
};

const trustUi = {
  actionMessage: '',
  restorePreview: null,
};

export function template() {
  return html`
    <section class="page" id="atelier-page">
      <div class="atelier-shell" id="atelier-shell">
        <section class="atelier-hero">
          <p class="hero-eyebrow">Foundation shelf</p>
          <h1>Atelier</h1>
          <p class="section-lede">Operations, storage, protection, checkpoints, and lower-frequency maintenance.</p>
        </section>
        <section id="atelier-trust-root">
          ${raw(renderTrustSkeleton())}
        </section>
        ${raw(renderClassicLinks())}
      </div>
    </section>
  `;
}

export async function init() {
  await loadTrustDurability();
}

async function loadTrustDurability() {
  const root = $('#atelier-trust-root');
  if (!root) return;
  const [durable, readiness, backups, protection, git, activity] = await Promise.all([
    api.durableStorageStatus().catch(errorPayload),
    api.releaseReadiness().catch(errorPayload),
    api.storageBackups().catch(errorPayload),
    api.storageProtectionStatus().catch(errorPayload),
    api.gitStatus().catch(errorPayload),
    api.gitActivity({ limit: 25 }).catch(errorPayload),
  ]);
  setView(root, renderTrustDurability({
    durable,
    backups,
    protection,
    git,
    activity,
    readiness,
    actionMessage: trustUi.actionMessage,
    restorePreview: trustUi.restorePreview,
  }));
  wireTrustActions(root);
}

function errorPayload(error) {
  return { error: error?.message || 'Unavailable' };
}

function renderTrustSkeleton() {
  return html`
    <div class="quiet-panel">
      <p class="quiet-statement"><span class="glyph">◇</span>Loading trust and durability status.</p>
    </div>
  `;
}

export function renderTrustDurability({
  durable = {},
  backups = {},
  protection = {},
  git = {},
  activity = {},
  readiness = null,
  actionMessage = '',
  restorePreview = null,
} = {}) {
  const summary = summarizeTrust({ durable, backups, protection, git, activity });
  return html`
    <section>
      <header class="section-head">
        <span class="section-eyebrow">Movement VI</span>
        <h2 class="section-title">Trust &amp; durability</h2>
        <p class="section-lede">${summary.lede}</p>
      </header>
      <div class="trust-grid">
        ${raw(renderTrustItem({
          title: 'Durable store',
          status: summary.durableStatus,
          detail: durable.error || durableStoreDetail(durable),
          metric: durable.database_exists ? `${Number(durable.document_count || 0)} docs` : 'Not ready',
        }))}
        ${raw(renderTrustItem({
          title: 'Latest backup',
          status: summary.backupStatus,
          detail: latestBackupDetail(backups),
          metric: summary.latestBackupId || 'None',
        }))}
        ${raw(renderTrustItem({
          title: 'Protection',
          status: summary.protectionStatus,
          detail: protectionDetail(protection),
          metric: summary.protectionIssueLabel,
        }))}
        ${raw(renderTrustItem({
          title: 'Git checkpoints',
          status: summary.gitStatus,
          detail: gitDetail(git),
          metric: summary.gitMetric,
        }))}
        ${raw(renderTrustItem({
          title: 'Audit events',
          status: summary.auditStatus,
          detail: auditDetail(activity),
          metric: String(summary.auditCount),
        }))}
      </div>
      <div class="entry-meta trust-actions">
        <a class="link-editorial" href="/classic#settings">Open classic storage tools</a>
        <a class="link-editorial" href="/classic#settings">Backup, restore, and checkpoints</a>
      </div>
      ${raw(renderReleaseReadiness(summary, { durable, backups, protection, git, activity, readiness, restorePreview }))}
      ${raw(renderProfileCopilotAudit(activity))}
      ${raw(renderTrustOperations({ git, actionMessage, restorePreview }))}
    </section>
  `;
}

function summarizeTrust({ durable, backups, protection, git, activity }) {
  const backupList = Array.isArray(backups?.backups) ? backups.backups : [];
  const latestBackup = backupList[0] || null;
  const protectionIssues = Number(protection?.total_non_compliant_files || 0)
    + Number(protection?.total_non_compliant_directories || 0);
  const changedFiles = Array.isArray(git?.changed_files) ? git.changed_files.length : 0;
  const auditCount = Number(activity?.summary?.total_matched || 0);

  const durableStatus = durable?.error || !durable?.database_exists ? 'warning' : 'ready';
  const backupStatus = backupList.length ? 'ready' : 'critical';
  const protectionStatus = protection?.error || protection?.supported === false
    ? 'critical'
    : protectionIssues > 0 ? 'warning' : 'ready';
  const gitStatus = git?.error || git?.status === 'no_repo'
    ? 'warning'
    : changedFiles > 0 ? 'warning' : 'ready';
  const auditStatus = activity?.error ? 'warning' : 'ready';
  const issueCount = [durableStatus, backupStatus, protectionStatus, gitStatus, auditStatus]
    .filter(status => status !== 'ready').length;

  return {
    lede: issueCount
      ? `${issueCount} trust area${issueCount === 1 ? '' : 's'} need review.`
      : 'Backup, protection, checkpoint, and audit signals are available.',
    durableStatus,
    backupStatus,
    protectionStatus,
    gitStatus,
    auditStatus,
    auditCount,
    latestBackupId: latestBackup?.backup_id || '',
    protectionIssueLabel: protectionIssues ? `${protectionIssues} issue${protectionIssues === 1 ? '' : 's'}` : 'Compliant',
    gitMetric: changedFiles ? `${changedFiles} uncheckpointed` : git?.status === 'no_repo' ? 'No repo' : 'Clean',
  };
}

function renderReleaseReadiness(summary, { durable, backups, protection, git, activity, readiness, restorePreview } = {}) {
  if (readiness && !readiness.error && Array.isArray(readiness.checks)) {
    const checks = readiness.checks.map(check => ({
      label: check.title || check.id || 'Readiness check',
      status: check.status,
      detail: check.detail || '',
    }));
    return html`
      <section class="release-readiness" aria-label="Release readiness">
        <div class="trust-operation-head">
          <h3>Ready to rely today?</h3>
          <p>${Number(readiness.ready_count || 0)}/${Number(readiness.total_count || checks.length)} checks ready. ${readiness.summary || 'Review readiness before treating today’s data as dependable.'}</p>
        </div>
        <div class="release-checklist">
          ${raw(checks.map(renderReleaseCheck).join(''))}
        </div>
        ${raw(renderReleaseActions(readiness.recommended_actions))}
      </section>
    `;
  }
  const restorePreviewRecorded = hasActivityEvent(activity, 'restore_preview');
  const checks = [
    {
      label: 'Durable store ready',
      status: summary.durableStatus,
      detail: durable?.database_exists ? 'Profile, plan, recommendation, and artifact storage is reachable.' : 'Durable storage is not ready.',
    },
    {
      label: 'Backup available',
      status: summary.backupStatus,
      detail: summary.latestBackupId ? `Latest backup ${summary.latestBackupId}.` : 'Create a backup before relying on today’s state.',
    },
    {
      label: 'Protection compliant',
      status: summary.protectionStatus,
      detail: protectionDetail(protection),
    },
    {
      label: 'Checkpoint clean',
      status: summary.gitStatus,
      detail: gitDetail(git),
    },
    {
      label: 'Audit feed present',
      status: activity?.error ? 'warning' : summary.auditCount > 0 ? 'ready' : 'warning',
      detail: summary.auditCount > 0 ? `${summary.auditCount} recent event${summary.auditCount === 1 ? '' : 's'} available.` : 'No recent audit events are available yet.',
    },
    {
      label: 'Restore preview verified',
      status: restorePreview || restorePreviewRecorded ? 'ready' : 'warning',
      detail: restorePreview
        ? 'A read-only restore preview is loaded on this page.'
        : restorePreviewRecorded
          ? 'A restore preview was recorded recently.'
          : 'Run a read-only restore preview when you need recovery confidence.',
    },
  ];
  const readyCount = checks.filter(check => normalizeTrustStatus(check.status) === 'ready').length;
  return html`
    <section class="release-readiness" aria-label="Release readiness">
      <div class="trust-operation-head">
        <h3>Ready to rely today?</h3>
        <p>${readyCount}/${checks.length} checks ready. Review warnings before treating today’s data as dependable.</p>
      </div>
      <div class="release-checklist">
        ${raw(checks.map(renderReleaseCheck).join(''))}
      </div>
    </section>
  `;
}

function renderReleaseActions(actions = []) {
  if (!Array.isArray(actions) || !actions.length) return '';
  return html`
    <div class="release-action-list">
      ${raw(actions.slice(0, 4).map(action => html`
        <a class="link-editorial" href="${action.href || '#atelier?section=trust'}">${action.label || action.action_kind || 'Review readiness'}</a>
      `).join(''))}
    </div>
  `;
}

function renderReleaseCheck(check) {
  const status = normalizeTrustStatus(check.status);
  return html`
    <article class="release-check ${status}">
      <span>${status === 'ready' ? 'Ready' : status === 'critical' ? 'Needs action' : 'Review'}</span>
      <h4>${check.label}</h4>
      <p>${check.detail}</p>
    </article>
  `;
}

function renderProfileCopilotAudit(activity = {}) {
  const events = profileCopilotEvents(activity).slice(0, 6);
  return html`
    <section class="trust-audit-feed" aria-label="Profile and Copilot audit">
      <div class="trust-operation-head">
        <h3>Profile &amp; Copilot changes</h3>
        <p>Recent profile edits and Copilot-applied changes that can affect recommendations, plan quality, and fit assessments.</p>
      </div>
      ${events.length ? html`
        <div class="trust-audit-list">
          ${raw(events.map(renderProfileCopilotAuditEvent).join(''))}
        </div>
      ` : html`<p class="marginalia">No profile or Copilot-applied changes are in the recent audit feed yet.</p>`}
    </section>
  `;
}

function renderProfileCopilotAuditEvent(event) {
  const metadata = event?.metadata && typeof event.metadata === 'object' ? event.metadata : {};
  const sections = Array.isArray(metadata.sections)
    ? metadata.sections.map(section => String(section || '').replaceAll('_', ' ')).filter(Boolean)
    : [];
  const source = String(metadata.source || event.event_type || '').replaceAll('_', ' ');
  const recommendationId = metadata.recommendation_id ? ` · ${metadata.recommendation_id}` : '';
  return html`
    <article class="trust-audit-item">
      <span>${source || 'audit'} · ${event.status || 'ok'}${recommendationId}</span>
      <h4>${event.title || 'Profile change'}</h4>
      <p>${event.message || 'No change summary was recorded.'}</p>
      <b>${sections.length ? sections.join(', ') : formatMaybeDate(event.created_at, 'Recorded')}</b>
    </article>
  `;
}

function profileCopilotEvents(activity = {}) {
  const events = Array.isArray(activity?.events) ? activity.events : [];
  const allowed = new Set(['profile_update', 'copilot_profile_update', 'copilot_recommendation_apply']);
  return events.filter(event => allowed.has(String(event?.event_type || '').toLowerCase()));
}

function hasActivityEvent(activity = {}, eventType) {
  return (Array.isArray(activity?.events) ? activity.events : [])
    .some(event => String(event?.event_type || '').toLowerCase() === eventType);
}

function renderTrustItem({ title, status, detail, metric }) {
  return html`
    <article class="trust-item ${normalizeTrustStatus(status)}">
      <span>${normalizeTrustStatus(status) === 'ready' ? 'Ready' : normalizeTrustStatus(status) === 'critical' ? 'Needs action' : 'Needs review'}</span>
      <h3>${title}</h3>
      <p>${detail}</p>
      <b>${metric}</b>
    </article>
  `;
}

function renderTrustOperations({ git = {}, actionMessage = '', restorePreview = null } = {}) {
  const defaultRef = git?.last_commit?.hash || git?.last_commit?.short_hash || '';
  return html`
    <section class="trust-operation-panel" aria-label="Trust actions">
      <div class="trust-operation-head">
        <h3>Safe trust actions</h3>
        <p>Create protection artifacts and inspect restore impact without applying a restore.</p>
      </div>
      <div class="trust-action-row">
        <button class="btn btn-primary" data-trust-action="create-backup">Create backup</button>
        <button class="btn btn-ghost" data-trust-action="apply-protection">Apply protection</button>
        <button class="btn btn-ghost" data-trust-action="create-checkpoint">Create checkpoint</button>
      </div>
      <div class="trust-restore-form">
        <label>
          <span>Restore preview ref</span>
          <input id="trust-restore-ref" type="text" value="${defaultRef}" placeholder="Commit hash or branch" />
        </label>
        <label>
          <span>Optional path</span>
          <input id="trust-restore-path" type="text" placeholder="plans/example.md" />
        </label>
        <button class="action-link" data-trust-action="preview-restore">
          Preview restore <span class="arrow">&rsaquo;</span>
        </button>
      </div>
      ${actionMessage ? html`<p class="trust-action-message">${actionMessage}</p>` : ''}
      <div id="trust-restore-preview">
        ${raw(renderRestorePreview(restorePreview))}
      </div>
    </section>
  `;
}

function renderRestorePreview(preview) {
  if (!preview) {
    return html`
      <p class="marginalia">
        Read-only restore preview will show changed files and diff excerpts here. No restore is applied from v2.
      </p>
    `;
  }
  const files = Array.isArray(preview.files) ? preview.files.slice(0, 5) : [];
  const warnings = Array.isArray(preview.warnings) ? preview.warnings : [];
  return html`
    <div class="trust-restore-preview">
      <p class="inline-form-title">Read-only restore preview</p>
      <p>${preview.message || 'No files were changed.'}</p>
      <dl class="trust-preview-meta">
        <div><dt>Ref</dt><dd>${preview.ref || '-'}</dd></div>
        <div><dt>Files</dt><dd>${preview.total_files ?? files.length}</dd></div>
        <div><dt>Read only</dt><dd>${preview.read_only === false ? 'No' : 'Yes'}</dd></div>
      </dl>
      ${warnings.length ? html`
        <ul class="trust-preview-list">
          ${raw(warnings.map(warning => html`<li>${warning}</li>`).join(''))}
        </ul>
      ` : ''}
      ${files.length ? html`
        <div class="trust-preview-files">
          ${raw(files.map(renderRestorePreviewFile).join(''))}
        </div>
      ` : html`<p class="marginalia">No restorable file differences were returned.</p>`}
    </div>
  `;
}

function renderRestorePreviewFile(file) {
  return html`
    <article class="trust-preview-file">
      <span>${file.status || 'preview'}</span>
      <h4>${file.path || 'File'}</h4>
      ${file.diff ? raw(`<pre>${esc(file.diff)}</pre>`) : raw('<p class="marginalia">No diff excerpt returned.</p>')}
    </article>
  `;
}

function wireTrustActions(root) {
  root.querySelectorAll('[data-trust-action]').forEach(button => {
    button.addEventListener('click', () => handleTrustAction(button));
  });
}

async function handleTrustAction(button) {
  const action = button.getAttribute('data-trust-action');
  setTrustButtonsDisabled(true);
  trustUi.actionMessage = '';
  try {
    if (action === 'create-backup') {
      const result = await api.createStorageBackup({ reason: 'v2_atelier_manual' });
      trustUi.restorePreview = null;
      trustUi.actionMessage = `Backup ${result.backup_id || 'created'} created.`;
      await loadTrustDurability();
      return;
    }
    if (action === 'apply-protection') {
      const result = await api.applyStorageProtection({});
      trustUi.restorePreview = null;
      trustUi.actionMessage = `Protection applied. ${Number(result.non_compliant_files_after || 0) + Number(result.non_compliant_directories_after || 0)} issue(s) remain.`;
      await loadTrustDurability();
      return;
    }
    if (action === 'create-checkpoint') {
      const result = await api.createGitCheckpoint({
        event_type: 'v2_trust_manual_checkpoint',
        message: 'BuildWealth v2 trust checkpoint',
      });
      trustUi.restorePreview = null;
      trustUi.actionMessage = result.message || 'Checkpoint created.';
      await loadTrustDurability();
      return;
    }
    if (action === 'preview-restore') {
      const ref = String($('#trust-restore-ref')?.value || '').trim();
      const path = String($('#trust-restore-path')?.value || '').trim();
      if (!ref) {
        trustUi.actionMessage = 'Enter a commit ref before previewing restore impact.';
        await loadTrustDurability();
        return;
      }
      trustUi.restorePreview = await api.gitRestorePreview({ ref, path, maxChars: 60000 });
      trustUi.actionMessage = 'Read-only restore preview loaded. No files were changed.';
      await loadTrustDurability();
      return;
    }
  } catch (error) {
    trustUi.actionMessage = error?.message || 'Trust action failed.';
    await loadTrustDurability();
    return;
  } finally {
    setTrustButtonsDisabled(false);
  }
}

function setTrustButtonsDisabled(disabled) {
  $('#atelier-trust-root')?.querySelectorAll('[data-trust-action]').forEach(button => {
    button.disabled = disabled;
  });
}

function durableStoreDetail(durable) {
  if (!durable?.database_exists) return 'Durable storage database has not been created yet.';
  const rollback = durable.latest_rollback_check_passed === true
    ? 'Last rollback check passed.'
    : durable.latest_rollback_check_passed === false
      ? 'Last rollback check did not pass.'
      : 'Rollback check has not run yet.';
  return `${rollback} ${formatMaybeDate(durable.latest_migration_at, 'Last migration')}`;
}

function latestBackupDetail(backups) {
  const list = Array.isArray(backups?.backups) ? backups.backups : [];
  if (backups?.error) return backups.error;
  if (!list.length) return 'No local backup archive is available yet.';
  const latest = list[0];
  return `${list.length} backup archive${list.length === 1 ? '' : 's'} available. ${formatMaybeDate(latest.created_at, 'Latest')}`;
}

function protectionDetail(protection) {
  if (protection?.error) return protection.error;
  if (protection?.supported === false) return 'Permission hardening is not supported on this system.';
  const issues = Number(protection?.total_non_compliant_files || 0)
    + Number(protection?.total_non_compliant_directories || 0);
  const level = protection?.policy?.protection_level || 'standard';
  if (issues > 0) return `${issues} issue${issues === 1 ? '' : 's'} need protection apply. Policy is ${level}.`;
  return `Protection policy is ${level} and currently compliant.`;
}

function gitDetail(git) {
  if (git?.error) return git.error;
  if (git?.status === 'no_repo') return 'Versioned workspace has not been initialized yet.';
  const changed = Array.isArray(git?.changed_files) ? git.changed_files.length : 0;
  if (changed > 0) return `${changed} uncheckpointed file${changed === 1 ? '' : 's'} should be reviewed before risky changes.`;
  if (git?.last_commit?.date) return formatMaybeDate(git.last_commit.date, 'Last checkpoint');
  return 'Git checkpoint status is available.';
}

function auditDetail(activity) {
  if (activity?.error) return activity.error;
  const count = Number(activity?.summary?.total_matched || 0);
  if (!count) return 'No checkpoint or restore audit events recorded yet.';
  return `${count} checkpoint/restore audit event${count === 1 ? '' : 's'} recorded.`;
}

function formatMaybeDate(value, label) {
  if (!value) return `${label} date unavailable.`;
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return `${label} date unavailable.`;
  return `${label} ${fmtDateLong(date)}.`;
}

function normalizeTrustStatus(status) {
  if (status === 'blocked') return 'critical';
  return status === 'critical' || status === 'warning' || status === 'ready' ? status : 'warning';
}

function renderClassicLinks() {
  return html`
    <section class="placeholder atelier-links">
      <span class="glyph">⁂</span>
      <h2>Classic tools remain available.</h2>
      <p>
        Profile, sync, imports, workflow templates, full restore flows, and
        settings still live in classic surfaces while the high-frequency v2
        surfaces stay focused.
      </p>
      <p class="marginalia">Profile · Sync &amp; Import · Workflows · Settings</p>
      <div class="entry-meta">
        <a class="link-editorial" href="/classic#profile">Profile</a>
        <a class="link-editorial" href="/classic#sync">Sync &amp; Import</a>
        <a class="link-editorial" href="/classic#workflows">Workflows</a>
        <a class="link-editorial" href="/classic#settings">Settings</a>
      </div>
    </section>
  `;
}
