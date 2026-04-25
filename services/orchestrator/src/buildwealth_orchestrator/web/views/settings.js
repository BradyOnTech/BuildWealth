import {
  applyGitRestore,
  connectGitRemote,
  createGitCheckpoint,
  fetchJson,
  getGitActivity,
  getGitAutoGitState,
  getGitDiff,
  getGitHistory,
  getGitPolicy,
  getGitRestorePreview,
  getGitStatus,
  initializeGitRepository,
  pullGitRemote,
  pushGitRemote,
  runDueGitAutoGit,
  updateGitPolicy,
} from '../lib/api.js';
import { byId, writeLog } from '../lib/utils.js';

export const id = 'settings';
export const label = 'Settings';
export const icon = '<svg viewBox="0 0 20 20" fill="none" stroke="currentColor" stroke-width="1.6"><circle cx="10" cy="10" r="3"/><path d="M10 2v2M10 16v2M2 10h2M16 10h2M4.2 4.2l1.4 1.4M14.4 14.4l1.4 1.4M4.2 15.8l1.4-1.4M14.4 5.6l1.4-1.4"/></svg>';

const FIELDS = [
  { key: 'openai_api_key', label: 'OpenAI API Key', type: 'password', placeholder: 'sk-...', hint: 'Required for Copilot AI conversations.' },
  { key: 'openai_model', label: 'OpenAI Model', type: 'text', placeholder: 'gpt-5-mini', hint: 'Model used for Copilot responses.' },
  { key: 'openai_base_url', label: 'OpenAI Base URL', type: 'text', placeholder: 'https://api.openai.com/v1', hint: 'Custom endpoint for OpenAI-compatible APIs.' },
];

const gitUiState = {
  policy: null,
  status: null,
  history: [],
  autogit: null,
  restorePreview: null,
  restorePreviewSignatures: new Map(),
  auditEvents: [],
  serverActivity: [],
};

const SUPPORTED_PLAN_RESTORE_FILES = new Map([
  ['plan.md', 'Plan markdown'],
  ['tasks.md', 'Plan tasks'],
  ['settings.json', 'Plan settings'],
  ['timeline.json', 'Plan timeline'],
  ['contribution_rules.json', 'Contribution rules'],
  ['assumption_sets.json', 'Assumption sets'],
  ['branch_templates.json', 'Branch templates'],
]);

export function template() {
  return `
    <div class="view-header"><h2>Settings</h2><button class="primary small" id="save-settings">Save Settings</button></div>
    <p class="hint">Configure local Copilot settings. Values are stored locally on your machine and masked in the UI.</p>
    <div class="settings-form">
      <h3 class="section-title">AI Copilot</h3>
      <div class="settings-grid">${FIELDS.map(fieldHtml).join('')}</div>
      <h3 class="section-title">Backup & Restore</h3>
      <p class="hint tight">Create local backup archives and restore a selected archive when recovery is needed.</p>
      <div class="settings-grid">
        <label class="field">
          <span>Available Backups</span>
          <select id="backup-select"></select>
          <span class="field-hint">Archives are stored under <code>data/backups</code>.</span>
        </label>
        <label class="field">
          <span>Pre-Restore Backup</span>
          <select id="backup-restore-pre-backup">
            <option value="true">Enabled (recommended)</option>
            <option value="false">Disabled</option>
          </select>
          <span class="field-hint">Create a safety backup before restore.</span>
        </label>
      </div>
      <div class="header-actions">
        <button class="ghost small" id="refresh-backups">Refresh Backups</button>
        <button class="ghost small" id="create-backup">Create Backup</button>
        <button class="primary small" id="restore-backup">Restore Selected</button>
      </div>
      <p class="hint" id="backup-status"></p>
      <h3 class="section-title">Data Protection</h3>
      <p class="hint tight">Control local file-permission hardening for sensitive stores.</p>
      <div class="settings-grid">
        <label class="field">
          <span>Protection Level</span>
          <select id="protection-level">
            <option value="standard">Standard (owner/group)</option>
            <option value="hardened">Hardened (owner only)</option>
          </select>
          <span class="field-hint">Hardened mode applies strict owner-only file permissions.</span>
        </label>
        <label class="field">
          <span>Include Backups</span>
          <select id="protection-include-backups">
            <option value="false">No</option>
            <option value="true">Yes</option>
          </select>
          <span class="field-hint">Apply permission hardening to backup archives too.</span>
        </label>
      </div>
      <div class="settings-grid">
        <label class="field">
          <span>Auto Apply On Startup</span>
          <select id="protection-auto-apply">
            <option value="false">Disabled</option>
            <option value="true">Enabled</option>
          </select>
          <span class="field-hint">Re-apply protection policy when orchestrator starts.</span>
        </label>
        <label class="field">
          <span>Current Compliance</span>
          <input type="text" id="protection-compliance" readonly value="Unknown" />
          <span class="field-hint">Detected non-compliant files/directories against active policy.</span>
        </label>
      </div>
      <div class="header-actions">
        <button class="ghost small" id="refresh-protection-status">Refresh Status</button>
        <button class="ghost small" id="save-protection-policy">Save Protection Policy</button>
        <button class="primary small" id="apply-protection-now">Apply Protection Now</button>
      </div>
      <p class="hint" id="protection-status"></p>
      <h3 class="section-title">Version History</h3>
      <p class="hint tight">Create local Git checkpoints for plans, recommendations, review packets, and selected audit artifacts.</p>
      <section class="git-panel">
        <div class="git-panel-header">
          <div>
            <h4>Git Setup Guide</h4>
            <p class="hint tight">Follow the safe path: enable history, initialize the local repo, create a checkpoint, then inspect the diff.</p>
          </div>
          <button class="primary small" id="git-guided-next-action">Run Next Recommended Step</button>
        </div>
        <div class="settings-grid">
          <label class="field">
            <span>Recommended Next Step</span>
            <input type="text" id="git-guided-next-step" readonly value="Load Git status to see the next step." />
            <span class="field-hint">One-click path: Enable → Initialize → Checkpoint → Preview diff.</span>
          </label>
          <label class="field">
            <span>Workflow Status</span>
            <input type="text" id="git-workflow-status" readonly value="Unknown" />
            <span class="field-hint">Plain-language summary of local, AutoGit, remote, and restore-preview readiness.</span>
          </label>
        </div>
      </section>
      <section class="git-panel">
        <div class="git-panel-header">
          <div>
            <h4>Local History</h4>
            <p class="hint tight">Local checkpoints are the safe default and work without any remote service.</p>
          </div>
          <div class="header-actions">
            <button class="ghost small" id="save-git-policy">Save Policy</button>
            <button class="ghost small" id="init-git-repo">Initialize</button>
            <button class="ghost small" id="refresh-git-status">Refresh</button>
            <button class="primary small" id="create-git-checkpoint">Create Checkpoint</button>
          </div>
        </div>
        <div class="settings-grid">
          <label class="field">
            <span>Version History</span>
            <select id="git-enabled">
              <option value="false">Disabled</option>
              <option value="true">Enabled</option>
            </select>
            <span class="field-hint">Controls whether BuildWealth should treat the versioned workspace as active.</span>
          </label>
          <label class="field">
            <span>Workspace Path</span>
            <input type="text" id="git-workspace-dir" autocomplete="off" />
            <span class="field-hint">Local generated workspace used for Git checkpoints.</span>
          </label>
          <label class="field">
            <span>Financial Profile Export</span>
            <select id="git-include-financial-profile">
              <option value="false">Excluded</option>
              <option value="true">Included</option>
            </select>
            <span class="field-hint">Sensitive by default. Only include when you want it in Git history.</span>
          </label>
        </div>
        <div class="settings-grid">
          <label class="field">
            <span>Repository Status</span>
            <input type="text" id="git-repo-status" readonly value="Unknown" />
            <span class="field-hint">Initialized, clean, dirty, or not initialized.</span>
          </label>
          <label class="field">
            <span>Branch</span>
            <input type="text" id="git-branch" readonly value="-" />
            <span class="field-hint">Current branch for the versioned workspace.</span>
          </label>
          <label class="field">
            <span>Last Checkpoint</span>
            <input type="text" id="git-last-commit" readonly value="-" />
            <span class="field-hint">Most recent local commit in the versioned workspace.</span>
          </label>
        </div>
        <div class="settings-grid">
          <label class="field">
            <span>Changed Files</span>
            <input type="text" id="git-changed-files" readonly value="0" />
            <span class="field-hint">Files currently changed in the generated workspace.</span>
          </label>
          <label class="field">
            <span>Recent History</span>
            <select id="git-history-select"></select>
            <span class="field-hint">Latest local checkpoints.</span>
          </label>
        </div>
        <div class="header-actions">
          <button class="ghost small" id="view-current-git-diff">View Current Diff</button>
          <button class="ghost small" id="view-selected-git-diff">View Selected Diff</button>
        </div>
        <label class="field form-span">
          <span>Diff Preview</span>
          <textarea id="git-diff-preview" rows="14" readonly placeholder="View current changes or select a checkpoint to inspect its patch."></textarea>
          <span class="field-hint">Shows generated workspace changes without leaving BuildWealth.</span>
        </label>
      </section>
      <section class="git-panel">
        <div class="git-panel-header">
          <div>
            <h4>AutoGit</h4>
            <p class="hint tight">Automatic checkpoints are local-only and wait for meaningful app changes to settle.</p>
          </div>
          <button class="ghost small" id="run-due-git-autogit">Run Due AutoGit</button>
        </div>
        <div class="settings-grid">
          <label class="field">
            <span>AutoGit</span>
            <select id="git-autogit-enabled">
              <option value="false">Disabled</option>
              <option value="true">Enabled</option>
            </select>
            <span class="field-hint">Queues automatic local checkpoints after meaningful app changes.</span>
          </label>
          <label class="field">
            <span>Auto Push</span>
            <select id="git-auto-push-enabled">
              <option value="false">Disabled</option>
              <option value="true">Enabled</option>
            </select>
            <span class="field-hint">Stored now; remote push remains opt-in.</span>
          </label>
          <label class="field">
            <span>Idle Seconds</span>
            <input type="number" id="git-auto-checkpoint-idle-seconds" min="30" max="86400" step="30" />
            <span class="field-hint">AutoGit waits this long after the latest eligible event.</span>
          </label>
        </div>
        <div class="settings-grid">
          <label class="field">
            <span>Pending AutoGit</span>
            <input type="text" id="git-autogit-pending" readonly value="None" />
            <span class="field-hint">Queued event waiting for the idle window.</span>
          </label>
          <label class="field">
            <span>Last AutoGit Result</span>
            <input type="text" id="git-autogit-last-result" readonly value="None" />
            <span class="field-hint">Most recent automatic checkpoint outcome.</span>
          </label>
        </div>
      </section>
      <section class="git-panel">
        <div class="git-panel-header">
          <div>
            <h4>Remote Sync</h4>
            <p class="hint tight">Optional private remote sync. Push and pull are manual; BuildWealth never force-pushes.</p>
          </div>
          <div class="header-actions">
            <button class="ghost small" id="connect-git-remote">Connect Remote</button>
            <button class="ghost small" id="push-git-remote">Push</button>
            <button class="ghost small" id="pull-git-remote">Pull</button>
          </div>
        </div>
        <div class="settings-grid">
          <label class="field">
            <span>Remote</span>
            <input type="text" id="git-remote-status" readonly value="Local only" />
            <span class="field-hint">Shows local-only, remote-connected, and ahead/behind state.</span>
          </label>
          <label class="field">
            <span>Remote Name</span>
            <input type="text" id="git-remote-name" autocomplete="off" placeholder="origin" />
            <span class="field-hint">Defaults to <code>origin</code>.</span>
          </label>
          <label class="field">
            <span>Remote URL</span>
            <input type="text" id="git-remote-url" autocomplete="off" placeholder="git@github.com:you/buildwealth-history.git" />
            <span class="field-hint">Use a private repo. BuildWealth refuses incompatible histories.</span>
          </label>
        </div>
      </section>
      <section class="git-panel">
        <div class="git-panel-header">
          <div>
            <h4>Restore Preview</h4>
            <p class="hint tight">Guarded restore planning. Preview impact first, then apply selected files through BuildWealth validation.</p>
          </div>
          <div class="header-actions">
            <button class="ghost small" id="preview-git-restore">Preview Selected Restore</button>
            <button class="primary small" id="apply-git-restore">Apply Selected Restore</button>
          </div>
        </div>
        <div class="settings-grid">
          <label class="field">
            <span>Restore Preview Path</span>
            <input type="text" id="git-restore-preview-path" autocomplete="off" placeholder="plans/, recommendations/, or a specific exported file" />
            <span class="field-hint">Preview can inspect folders. Apply requires one explicit supported file path.</span>
          </label>
        </div>
        <div class="restore-action-summary" id="git-restore-preview-summary">Preview a checkpoint to select restorable files.</div>
        <div class="header-actions">
          <button class="ghost small" id="select-supported-git-restore">Select Restorable Changes</button>
          <button class="ghost small" id="clear-git-restore-selection">Clear Selection</button>
        </div>
        <div class="git-restore-table-wrap">
          <table class="git-restore-table">
            <thead>
              <tr>
                <th>Apply</th>
                <th>Status</th>
                <th>Path</th>
                <th>Support</th>
              </tr>
            </thead>
            <tbody id="git-restore-preview-rows">
              <tr><td colspan="4">No restore preview loaded.</td></tr>
            </tbody>
          </table>
        </div>
        <label class="field form-span">
          <span>Selected Restore Diff</span>
          <textarea id="git-restore-preview" rows="12" readonly placeholder="Select a checkpoint and preview what restoring it would change."></textarea>
          <span class="field-hint">Apply creates pre/post checkpoints, uses service-layer validation, and never runs raw git checkout.</span>
        </label>
      </section>
      <section class="git-panel">
        <div class="git-panel-header">
          <div>
            <h4>Git Activity Feed</h4>
            <p class="hint tight">Recent checkpoints, AutoGit, remote sync, restore previews, and restore applies in one place.</p>
          </div>
          <button class="ghost small" id="refresh-git-activity">Refresh Activity</button>
        </div>
        <div class="settings-grid">
          <label class="field">
            <span>Event Type</span>
            <select id="git-activity-event-type">
              <option value="">All events</option>
              <option value="checkpoint">Checkpoint</option>
              <option value="autogit">AutoGit</option>
              <option value="remote_connect">Remote connect</option>
              <option value="remote_push">Remote push</option>
              <option value="remote_pull">Remote pull</option>
              <option value="restore_preview">Restore preview</option>
              <option value="restore_apply">Restore apply</option>
            </select>
            <span class="field-hint">Filter the durable Git event log.</span>
          </label>
          <label class="field">
            <span>Status</span>
            <select id="git-activity-status">
              <option value="">All statuses</option>
              <option value="ok">OK</option>
              <option value="committed">Committed</option>
              <option value="applied">Applied</option>
              <option value="pushed">Pushed</option>
              <option value="pulled">Pulled</option>
              <option value="failed">Failed</option>
            </select>
            <span class="field-hint">Narrow activity by outcome.</span>
          </label>
          <label class="field">
            <span>Checkpoint Hash</span>
            <input type="text" id="git-activity-ref" autocomplete="off" placeholder="optional hash" />
            <span class="field-hint">Filter by exact commit hash when needed.</span>
          </label>
        </div>
        <div class="git-audit-feed" id="git-audit-feed">Load Git status to see recent activity.</div>
      </section>
      <p class="hint" id="git-status"></p>
    </div>
    <p class="hint">Engine sidecar endpoints and health probes are configured via environment variables (<code>infra/env/orchestrator.env</code>).</p>
    <p class="hint" id="settings-status"></p>`;
}

function fieldHtml(f) {
  return `<label class="field">
    <span>${f.label}</span>
    <input type="${f.type}" id="setting-${f.key}" placeholder="${f.placeholder}" autocomplete="off" />
    <span class="field-hint">${f.hint}</span>
  </label>`;
}

function populate(data) {
  for (const f of FIELDS) {
    const el = byId(`setting-${f.key}`);
    if (el) el.value = data[f.key] || '';
  }
}

function formatBackupOptionLabel(item) {
  const created = item.created_at ? new Date(item.created_at).toLocaleString() : 'Unknown time';
  const sizeMb = item.size_bytes ? `${(Number(item.size_bytes) / (1024 * 1024)).toFixed(2)} MB` : '0.00 MB';
  return `${item.backup_id} (${created}, ${sizeMb})`;
}

function setBackupStatus(message, isError = false) {
  const el = byId('backup-status');
  if (!el) return;
  el.textContent = message || '';
  el.style.color = isError ? 'var(--danger)' : '';
}

function setProtectionStatus(message, isError = false) {
  const el = byId('protection-status');
  if (!el) return;
  el.textContent = message || '';
  el.style.color = isError ? 'var(--danger)' : '';
}

function setGitStatus(message, isError = false) {
  const el = byId('git-status');
  if (!el) return;
  el.textContent = message || '';
  el.style.color = isError ? 'var(--danger)' : '';
}

function setProtectionInputs(policy = {}, status = null) {
  const level = String(policy.protection_level || 'standard');
  const includeBackups = Boolean(policy.include_backups);
  const autoApply = Boolean(policy.auto_apply_on_startup);

  const levelSelect = byId('protection-level');
  if (levelSelect) levelSelect.value = level === 'hardened' ? 'hardened' : 'standard';
  const includeSelect = byId('protection-include-backups');
  if (includeSelect) includeSelect.value = includeBackups ? 'true' : 'false';
  const autoApplySelect = byId('protection-auto-apply');
  if (autoApplySelect) autoApplySelect.value = autoApply ? 'true' : 'false';

  const complianceInput = byId('protection-compliance');
  if (!complianceInput) return;
  if (!status) {
    complianceInput.value = 'Unknown';
    return;
  }
  const files = Number(status.total_non_compliant_files || 0);
  const dirs = Number(status.total_non_compliant_directories || 0);
  complianceInput.value = `${files} files, ${dirs} dirs non-compliant`;
}

async function loadBackups() {
  const select = byId('backup-select');
  if (!select) return;
  try {
    const payload = await fetchJson('/api/storage/backups');
    const items = Array.isArray(payload.backups) ? payload.backups : [];
    select.innerHTML = '';
    if (!items.length) {
      const opt = document.createElement('option');
      opt.value = '';
      opt.textContent = 'No backups available';
      select.appendChild(opt);
      setBackupStatus('No backup archives found yet.');
      return;
    }
    for (const item of items) {
      const opt = document.createElement('option');
      opt.value = item.backup_id || '';
      opt.textContent = formatBackupOptionLabel(item);
      select.appendChild(opt);
    }
    const latest = items[0];
    setBackupStatus(`Loaded ${items.length} backups. Latest: ${latest.backup_id}`);
  } catch (e) {
    setBackupStatus(`Backup list failed: ${e.message}`, true);
    writeLog(`Backup list failed: ${e.message}`, null, true);
  }
}

async function createBackup() {
  const button = byId('create-backup');
  if (button) button.disabled = true;
  try {
    const payload = await fetchJson('/api/storage/backups', {
      method: 'POST',
      headers: { 'content-type': 'application/json' },
      body: JSON.stringify({ reason: 'ui_manual_backup' }),
    });
    await loadBackups();
    setBackupStatus(`Backup created: ${payload.backup_id}`);
    writeLog(`Backup created: ${payload.backup_id}`);
  } catch (e) {
    setBackupStatus(`Backup create failed: ${e.message}`, true);
    writeLog(`Backup create failed: ${e.message}`, null, true);
  } finally {
    if (button) button.disabled = false;
  }
}

async function restoreBackup() {
  const select = byId('backup-select');
  const preBackup = byId('backup-restore-pre-backup')?.value !== 'false';
  const backupId = select?.value || '';
  if (!backupId) {
    setBackupStatus('Select a backup to restore.', true);
    return;
  }

  const confirmed = window.confirm(
    `Restore backup ${backupId}? This replaces current data files.`
      + (preBackup ? ' A pre-restore backup will be created first.' : '')
  );
  if (!confirmed) return;

  const button = byId('restore-backup');
  if (button) button.disabled = true;
  try {
    const payload = await fetchJson('/api/storage/backups/restore', {
      method: 'POST',
      headers: { 'content-type': 'application/json' },
      body: JSON.stringify({ backup_id: backupId, create_pre_restore_backup: preBackup }),
    });
    await loadBackups();
    const preBackupText = payload.pre_restore_backup_id
      ? ` Pre-restore backup: ${payload.pre_restore_backup_id}.`
      : '';
    setBackupStatus(`Restore completed for ${payload.backup_id}.${preBackupText}`);
    writeLog(`Backup restored: ${payload.backup_id}`);
  } catch (e) {
    setBackupStatus(`Backup restore failed: ${e.message}`, true);
    writeLog(`Backup restore failed: ${e.message}`, null, true);
  } finally {
    if (button) button.disabled = false;
  }
}

async function loadProtectionStatus() {
  try {
    const status = await fetchJson('/api/storage/protection/status');
    setProtectionInputs(status.policy || {}, status);
    const files = Number(status.total_non_compliant_files || 0);
    const dirs = Number(status.total_non_compliant_directories || 0);
    setProtectionStatus(`Protection status loaded. Non-compliant: ${files} files, ${dirs} directories.`);
  } catch (e) {
    setProtectionStatus(`Protection status failed: ${e.message}`, true);
    writeLog(`Protection status failed: ${e.message}`, null, true);
  }
}

async function saveProtectionPolicy() {
  const payload = {
    protection_level: byId('protection-level')?.value || 'standard',
    include_backups: byId('protection-include-backups')?.value === 'true',
    auto_apply_on_startup: byId('protection-auto-apply')?.value === 'true',
  };
  try {
    const policy = await fetchJson('/api/storage/protection/policy', {
      method: 'PUT',
      headers: { 'content-type': 'application/json' },
      body: JSON.stringify(payload),
    });
    setProtectionInputs(policy, null);
    setProtectionStatus('Protection policy saved.');
    writeLog('Protection policy saved.');
    await loadProtectionStatus();
  } catch (e) {
    setProtectionStatus(`Protection policy save failed: ${e.message}`, true);
    writeLog(`Protection policy save failed: ${e.message}`, null, true);
  }
}

async function applyProtectionNow() {
  const payload = {
    protection_level: byId('protection-level')?.value || 'standard',
    include_backups: byId('protection-include-backups')?.value === 'true',
  };
  const button = byId('apply-protection-now');
  if (button) button.disabled = true;
  try {
    const report = await fetchJson('/api/storage/protection/apply', {
      method: 'POST',
      headers: { 'content-type': 'application/json' },
      body: JSON.stringify(payload),
    });
    setProtectionStatus(
      `Protection applied. Updated ${report.files_updated} files and ${report.directories_updated} directories.`
    );
    writeLog('Protection hardening applied.');
    await loadProtectionStatus();
  } catch (e) {
    setProtectionStatus(`Protection apply failed: ${e.message}`, true);
    writeLog(`Protection apply failed: ${e.message}`, null, true);
  } finally {
    if (button) button.disabled = false;
  }
}

function setGitPolicyInputs(policy = {}) {
  gitUiState.policy = policy;
  const enabled = byId('git-enabled');
  if (enabled) enabled.value = policy.enabled ? 'true' : 'false';
  const workspace = byId('git-workspace-dir');
  if (workspace) workspace.value = policy.workspace_dir || '';
  const includeProfile = byId('git-include-financial-profile');
  if (includeProfile) includeProfile.value = policy.include_financial_profile ? 'true' : 'false';
  const autogit = byId('git-autogit-enabled');
  if (autogit) autogit.value = policy.autogit_enabled ? 'true' : 'false';
  const autoPush = byId('git-auto-push-enabled');
  if (autoPush) autoPush.value = policy.auto_push_enabled ? 'true' : 'false';
  const idleSeconds = byId('git-auto-checkpoint-idle-seconds');
  if (idleSeconds) idleSeconds.value = String(policy.auto_checkpoint_idle_seconds || 180);
  const remoteName = byId('git-remote-name');
  if (remoteName) remoteName.value = policy.remote_name || 'origin';
}

function collectGitPolicyPayload() {
  return {
    enabled: byId('git-enabled')?.value === 'true',
    workspace_dir: byId('git-workspace-dir')?.value || '',
    autogit_enabled: byId('git-autogit-enabled')?.value === 'true',
    auto_push_enabled: byId('git-auto-push-enabled')?.value === 'true',
    auto_checkpoint_idle_seconds: Number(byId('git-auto-checkpoint-idle-seconds')?.value || 180),
    remote_name: byId('git-remote-name')?.value || 'origin',
    include_financial_profile: byId('git-include-financial-profile')?.value === 'true',
  };
}

function formatCommit(commit) {
  if (!commit) return '-';
  const shortHash = commit.short_hash || String(commit.hash || '').slice(0, 7);
  const date = commit.date ? new Date(commit.date).toLocaleString() : '';
  return `${shortHash || '-'} ${commit.message || ''}${date ? ` (${date})` : ''}`.trim();
}

function restoreFileSupport(file = {}) {
  const path = String(file.path || '');
  const parts = path.split('/');
  if (file.status === 'added' || file.historical_excerpt == null) {
    return { supported: false, label: 'Not in checkpoint' };
  }
  if (file.status === 'unchanged') {
    return { supported: false, label: 'No change' };
  }
  if (parts.length === 3 && parts[0] === 'plans' && SUPPORTED_PLAN_RESTORE_FILES.has(parts[2])) {
    return { supported: true, label: SUPPORTED_PLAN_RESTORE_FILES.get(parts[2]) };
  }
  if (parts.length === 2 && parts[0] === 'recommendations' && parts[1] !== 'index.json' && parts[1].endsWith('.json')) {
    return { supported: true, label: 'Recommendation record' };
  }
  if (parts.length === 3 && parts[0] === 'reports' && parts[1] === 'portfolio_review_packets' && /\.(json|md)$/.test(parts[2])) {
    return { supported: true, label: 'Review packet file' };
  }
  return { supported: false, label: 'Preview only' };
}

function restoreFileSignature(file = {}) {
  return JSON.stringify({
    path: file.path || '',
    status: file.status || '',
    current_excerpt: file.current_excerpt ?? null,
  });
}

function checkedRestorePaths() {
  return [...document.querySelectorAll('#git-restore-preview-rows input[type="checkbox"]:checked')]
    .map((input) => input.value)
    .filter(Boolean);
}

function selectedRestoreFile() {
  const checked = document.querySelector('#git-restore-preview-rows input[type="checkbox"]:checked');
  const selectedPath = checked?.value || '';
  const files = Array.isArray(gitUiState.restorePreview?.files) ? gitUiState.restorePreview.files : [];
  return files.find((file) => file.path === selectedPath) || files.find((file) => restoreFileSupport(file).supported) || files[0] || null;
}

function setRestorePreviewText(file = null) {
  const preview = byId('git-restore-preview');
  if (!preview) return;
  if (!file) {
    preview.value = 'No restore preview available.';
    return;
  }
  const support = restoreFileSupport(file);
  const lines = [
    `${file.path || '-'} (${file.status || 'unknown'})`,
    `Support: ${support.label}`,
    '',
    file.diff || 'No diff.',
  ];
  if (file.truncated) lines.push('', '[Diff truncated in preview.]');
  preview.value = lines.join('\n');
}

function renderRestorePreviewRows(files = []) {
  const body = byId('git-restore-preview-rows');
  if (!body) return;
  body.innerHTML = '';
  if (!files.length) {
    const row = document.createElement('tr');
    const cell = document.createElement('td');
    cell.colSpan = 4;
    cell.textContent = 'No restorable files found for this preview.';
    row.appendChild(cell);
    body.appendChild(row);
    setRestorePreviewText(null);
    return;
  }

  for (const file of files) {
    const support = restoreFileSupport(file);
    const row = document.createElement('tr');
    row.className = support.supported ? 'restore-row supported' : 'restore-row unsupported';
    row.dataset.path = file.path || '';

    const selectCell = document.createElement('td');
    const checkbox = document.createElement('input');
    checkbox.type = 'checkbox';
    checkbox.value = file.path || '';
    checkbox.disabled = !support.supported;
    checkbox.addEventListener('change', () => setRestorePreviewText(selectedRestoreFile()));
    selectCell.appendChild(checkbox);
    row.appendChild(selectCell);

    const statusCell = document.createElement('td');
    const status = document.createElement('span');
    status.className = `restore-status restore-status-${file.status || 'unknown'}`;
    status.textContent = file.status || 'unknown';
    statusCell.appendChild(status);
    row.appendChild(statusCell);

    const pathCell = document.createElement('td');
    pathCell.className = 'restore-path';
    pathCell.textContent = file.path || '-';
    row.appendChild(pathCell);

    const supportCell = document.createElement('td');
    supportCell.textContent = support.label;
    row.appendChild(supportCell);

    row.addEventListener('click', (event) => {
      if (event.target !== checkbox && !checkbox.disabled) checkbox.checked = !checkbox.checked;
      setRestorePreviewText(file);
    });
    body.appendChild(row);
  }
  setRestorePreviewText(files.find((file) => restoreFileSupport(file).supported) || files[0]);
}

function setRestoreSummary(payload = {}) {
  const summary = byId('git-restore-preview-summary');
  if (!summary) return;
  const files = Array.isArray(payload.files) ? payload.files : [];
  const restorable = files.filter((file) => restoreFileSupport(file).supported).length;
  const unsupported = files.length - restorable;
  const expires = payload.preview_expires_at ? ` · token expires ${new Date(payload.preview_expires_at).toLocaleTimeString()}` : '';
  summary.textContent = `${files.length} file(s) previewed · ${restorable} restorable · ${unsupported} preview-only${expires}. Select files, then apply with confirmation.`;
}

function addGitAuditEvent(kind, title, detail = '', tone = 'info') {
  gitUiState.auditEvents.unshift({
    kind,
    title,
    detail,
    tone,
    at: new Date().toISOString(),
  });
  gitUiState.auditEvents = gitUiState.auditEvents.slice(0, 8);
  renderGitAuditFeed();
}

function setGitActivity(events = []) {
  gitUiState.serverActivity = Array.isArray(events) ? events : [];
  renderGitAuditFeed();
}

function activityTone(status = '') {
  const normalized = String(status || '').toLowerCase();
  if (['failed', 'error', 'rejected', 'auth_error', 'network_error'].includes(normalized)) return 'warn';
  if (['applied', 'committed', 'initialized', 'connected', 'pushed', 'pulled', 'ok'].includes(normalized)) return 'success';
  return 'info';
}

function renderGitAuditFeed() {
  const feed = byId('git-audit-feed');
  if (!feed) return;
  const events = [];
  for (const event of gitUiState.serverActivity) {
    events.push({
      kind: String(event.event_type || 'Git').replaceAll('_', ' '),
      title: event.title || 'Git activity',
      detail: [
        event.message,
        event.ref ? String(event.ref).slice(0, 7) : '',
        Array.isArray(event.paths) && event.paths.length ? `${event.paths.length} path(s)` : '',
      ].filter(Boolean).join(' · '),
      paths: event.paths || [],
      metadata: event.metadata || {},
      tone: activityTone(event.status),
      at: event.created_at,
    });
  }
  for (const event of gitUiState.auditEvents) {
    events.push(event);
  }
  const autogit = gitUiState.autogit || {};
  if (autogit.last_result) {
    events.push({
      kind: 'AutoGit',
      title: `AutoGit ${autogit.last_result.status || 'result'}`,
      detail: `${autogit.last_result.event_type || 'event'} · ${autogit.last_result.event_count || 1} event(s)`,
      tone: autogit.last_result.status === 'committed' ? 'success' : 'info',
      at: autogit.last_result.ran_at,
    });
  }
  const status = gitUiState.status || {};
  const remote = status.remote || {};
  if (remote.has_remote) {
    events.push({
      kind: 'Remote',
      title: `Remote ${remote.name || 'origin'} connected`,
      detail: `${remote.ahead || 0} ahead · ${remote.behind || 0} behind`,
      tone: remote.behind ? 'warn' : 'info',
      at: new Date().toISOString(),
    });
  }
  for (const commit of gitUiState.history.slice(0, 6)) {
    events.push({
      kind: 'Checkpoint',
      title: commit.message || 'Git checkpoint',
      detail: commit.short_hash || String(commit.hash || '').slice(0, 7),
      tone: 'success',
      at: commit.date,
    });
  }

  feed.innerHTML = '';
  if (!events.length) {
    feed.textContent = 'No Git activity yet.';
    return;
  }
  for (const event of events.slice(0, 10)) {
    const item = document.createElement('div');
    item.className = `git-audit-item ${event.tone || 'info'}`;
    const marker = document.createElement('span');
    marker.className = 'git-audit-marker';
    marker.textContent = event.kind || 'Git';
    const body = document.createElement('details');
    const title = document.createElement('strong');
    title.textContent = event.title || 'Git activity';
    const detail = document.createElement('span');
    const when = event.at ? new Date(event.at).toLocaleString() : '';
    detail.textContent = [event.detail, when].filter(Boolean).join(' · ');
    const summary = document.createElement('summary');
    summary.appendChild(title);
    summary.appendChild(detail);
    body.appendChild(summary);
    if ((event.paths || []).length || event.metadata) {
      const meta = document.createElement('pre');
      meta.textContent = JSON.stringify({
        paths: event.paths || [],
        metadata: event.metadata || {},
      }, null, 2);
      body.appendChild(meta);
    }
    item.appendChild(marker);
    item.appendChild(body);
    feed.appendChild(item);
  }
}

async function loadGitActivity() {
  try {
    const activity = await getGitActivity({
      limit: 30,
      eventType: byId('git-activity-event-type')?.value || '',
      status: byId('git-activity-status')?.value || '',
      ref: byId('git-activity-ref')?.value || '',
    });
    setGitActivity(activity.events || []);
  } catch (e) {
    setGitStatus(`Git activity load failed: ${e.message}`, true);
    writeLog(`Git activity load failed: ${e.message}`, null, true);
  }
}

function setGitStatusInputs(status = {}) {
  gitUiState.status = status;
  const repoStatus = byId('git-repo-status');
  if (repoStatus) {
    const dirtyLabel = status.dirty ? 'dirty' : 'clean';
    repoStatus.value = status.status === 'ok' ? `Initialized, ${dirtyLabel}` : (status.message || status.status || 'Unknown');
  }
  const branch = byId('git-branch');
  if (branch) branch.value = status.branch || '-';
  const lastCommit = byId('git-last-commit');
  if (lastCommit) lastCommit.value = formatCommit(status.last_commit);
  const changedFiles = byId('git-changed-files');
  if (changedFiles) changedFiles.value = String(Array.isArray(status.changed_files) ? status.changed_files.length : 0);
  const remoteStatus = byId('git-remote-status');
  if (remoteStatus) {
    const remote = status.remote || {};
    remoteStatus.value = remote.has_remote
      ? `${remote.name || 'remote'} ahead ${remote.ahead || 0}, behind ${remote.behind || 0}`
      : 'Local only';
    const remoteName = byId('git-remote-name');
    if (remoteName && remote.name) remoteName.value = remote.name;
  const remoteUrl = byId('git-remote-url');
  if (remoteUrl && remote.url) remoteUrl.value = remote.url;
  renderGitAuditFeed();
}
}

function collectGitRemotePayload() {
  return {
    remote_name: byId('git-remote-name')?.value || 'origin',
    remote_url: byId('git-remote-url')?.value || '',
  };
}

function setGitHistory(commits = []) {
  gitUiState.history = Array.isArray(commits) ? commits : [];
  const select = byId('git-history-select');
  if (!select) return;
  select.innerHTML = '';
  if (!Array.isArray(commits) || !commits.length) {
    const option = document.createElement('option');
    option.value = '';
    option.textContent = 'No checkpoints yet';
    select.appendChild(option);
    return;
  }
  for (const commit of commits) {
    const option = document.createElement('option');
    option.value = commit.hash || '';
    option.textContent = formatCommit(commit);
    select.appendChild(option);
  }
  renderGitAuditFeed();
}

function setGitDiff(payload = {}) {
  const preview = byId('git-diff-preview');
  if (!preview) return;
  const diffText = String(payload.diff || '').trimEnd();
  const truncatedText = payload.truncated ? '\n\n[Diff truncated in preview.]' : '';
  preview.value = diffText ? `${diffText}${truncatedText}` : 'No diff available.';
}

function setGitRestorePreview(payload = {}) {
  const files = Array.isArray(payload.files) ? payload.files : [];
  const warnings = Array.isArray(payload.warnings) ? payload.warnings : [];
  gitUiState.restorePreview = payload;
  gitUiState.restorePreviewSignatures = new Map(
    files.map((file) => [file.path, restoreFileSignature(file)]),
  );
  renderRestorePreviewRows(files);
  setRestoreSummary(payload);
  if (warnings.length) {
    const preview = byId('git-restore-preview');
    if (preview && !files.length) preview.value = warnings.map((warning) => `Warning: ${warning}`).join('\n');
  }
}

function setGitRestoreApplyResult(payload = {}) {
  const preview = byId('git-restore-preview');
  if (!preview) return;
  const lines = [
    payload.message || 'Restore apply completed.',
    '',
    `Applied files: ${payload.applied_files || 0}`,
    ...(payload.files || []).map((file) => `- ${file.status}: ${file.path} (${file.action})`),
  ];
  if (payload.before_checkpoint?.commit?.short_hash) {
    lines.push('', `Pre-apply checkpoint: ${payload.before_checkpoint.commit.short_hash}`);
  }
  if (payload.after_checkpoint?.commit?.short_hash) {
    lines.push(`Post-apply checkpoint: ${payload.after_checkpoint.commit.short_hash}`);
  }
  if ((payload.warnings || []).length) {
    lines.push('', 'Warnings:', ...payload.warnings.map((warning) => `- ${warning}`));
  }
  preview.value = lines.join('\n');
  const summary = byId('git-restore-preview-summary');
  if (summary) {
    const before = payload.before_checkpoint?.commit?.short_hash || 'no-op';
    const after = payload.after_checkpoint?.commit?.short_hash || 'no-op';
    summary.textContent = `Restore applied · pre-checkpoint ${before} · post-checkpoint ${after}.`;
  }
}

function setGitAutoGitState(state = {}) {
  gitUiState.autogit = state;
  const pending = byId('git-autogit-pending');
  if (pending) {
    const event = state.pending_event || null;
    if (event) {
      const due = event.due_at ? new Date(event.due_at).toLocaleString() : 'soon';
      pending.value = `${event.event_type || 'event'} x${event.event_count || 1}, due ${due}`;
    } else {
      pending.value = 'None';
    }
  }

  const lastResult = byId('git-autogit-last-result');
  if (lastResult) {
    const result = state.last_result || null;
    if (result) {
      const ran = result.ran_at ? new Date(result.ran_at).toLocaleString() : '';
      lastResult.value = `${result.status || 'unknown'}: ${result.event_type || 'event'}${ran ? ` (${ran})` : ''}`;
    } else {
      lastResult.value = 'None';
    }
  }
  updateGitWorkflowSummary();
  renderGitAuditFeed();
}

function gitNextStep() {
  const policy = gitUiState.policy || {};
  const status = gitUiState.status || {};
  const history = gitUiState.history || [];
  if (!policy.enabled) {
    return {
      label: 'Enable Version History',
      description: 'Version History is off. Enable it first so BuildWealth can maintain local checkpoints.',
      action: 'enable',
    };
  }
  if (status.status !== 'ok') {
    return {
      label: 'Initialize Local Repository',
      description: 'Version History is enabled, but the local Git workspace has not been initialized yet.',
      action: 'init',
    };
  }
  if (status.dirty || !status.last_commit) {
    return {
      label: 'Create Local Checkpoint',
      description: 'The versioned workspace has changes ready for a local checkpoint.',
      action: 'checkpoint',
    };
  }
  if (history.length) {
    return {
      label: 'Preview Latest Checkpoint Diff',
      description: 'Local history is ready. Inspect the selected checkpoint diff before using remote or restore preview tools.',
      action: 'diff',
    };
  }
  return {
    label: 'Refresh Version Status',
    description: 'Refresh Git status to find the next recommended action.',
    action: 'refresh',
  };
}

function updateGitWorkflowSummary() {
  const policy = gitUiState.policy || {};
  const status = gitUiState.status || {};
  const autogit = gitUiState.autogit || {};
  const remote = status.remote || {};
  const next = gitNextStep();
  const nextStep = byId('git-guided-next-step');
  if (nextStep) nextStep.value = `${next.label}: ${next.description}`;

  const workflowStatus = byId('git-workflow-status');
  if (!workflowStatus) return;
  const localLabel = status.status === 'ok'
    ? `Local repo ${status.dirty ? 'has uncheckpointed changes' : 'is checkpointed'}`
    : 'Local repo is not initialized';
  const remoteLabel = remote.has_remote
    ? `remote connected (${remote.ahead || 0} ahead, ${remote.behind || 0} behind)`
    : 'local-only';
  const autogitLabel = autogit.pending_event
    ? `AutoGit pending ${autogit.pending_event.event_type}`
    : `AutoGit ${policy.autogit_enabled ? 'enabled' : 'disabled'}`;
  workflowStatus.value = `${localLabel}; ${remoteLabel}; ${autogitLabel}; restore apply is guarded.`;
}

async function loadGitPolicy() {
  try {
    const policy = await getGitPolicy();
    setGitPolicyInputs(policy);
    updateGitWorkflowSummary();
  } catch (e) {
    setGitStatus(`Version policy load failed: ${e.message}`, true);
    writeLog(`Version policy load failed: ${e.message}`, null, true);
  }
}

async function saveGitPolicy() {
  const button = byId('save-git-policy');
  if (button) button.disabled = true;
  try {
    const policy = await updateGitPolicy(collectGitPolicyPayload());
    setGitPolicyInputs(policy);
    setGitStatus('Version policy saved.');
    writeLog('Version policy saved.');
    await loadGitStatus();
  } catch (e) {
    setGitStatus(`Version policy save failed: ${e.message}`, true);
    writeLog(`Version policy save failed: ${e.message}`, null, true);
  } finally {
    if (button) button.disabled = false;
  }
}

async function loadGitStatus() {
  try {
    const [status, history, autogit, activity] = await Promise.all([
      getGitStatus(),
      getGitHistory(10),
      getGitAutoGitState(),
      getGitActivity({
        limit: 30,
        eventType: byId('git-activity-event-type')?.value || '',
        status: byId('git-activity-status')?.value || '',
        ref: byId('git-activity-ref')?.value || '',
      }),
    ]);
    setGitStatusInputs(status);
    setGitHistory(history.commits || []);
    setGitAutoGitState(autogit);
    setGitActivity(activity.events || []);
    updateGitWorkflowSummary();
    setGitStatus(status.message || 'Version history status loaded.');
  } catch (e) {
    setGitStatus(`Version history status failed: ${e.message}`, true);
    writeLog(`Version history status failed: ${e.message}`, null, true);
  }
}

async function runGuidedGitStep() {
  const button = byId('git-guided-next-action');
  const next = gitNextStep();
  if (button) button.disabled = true;
  try {
    if (next.action === 'enable') {
      const enabled = byId('git-enabled');
      if (enabled) enabled.value = 'true';
      await saveGitPolicy();
      setGitStatus('Version History enabled. Next step: initialize the local repository.');
    } else if (next.action === 'init') {
      await initGitRepository();
    } else if (next.action === 'checkpoint') {
      await checkpointGitWorkspace();
    } else if (next.action === 'diff') {
      await loadSelectedGitDiff();
    } else {
      await loadGitStatus();
    }
  } finally {
    if (button) button.disabled = false;
  }
}

async function initGitRepository() {
  const button = byId('init-git-repo');
  if (button) button.disabled = true;
  try {
    const result = await initializeGitRepository();
    setGitStatus(result.message || 'Git repository initialized.');
    writeLog(result.message || 'Git repository initialized.');
    addGitAuditEvent('Repository', 'Git repository initialized', result.workspace_dir || '', 'success');
    await loadGitStatus();
  } catch (e) {
    setGitStatus(`Git initialization failed: ${e.message}`, true);
    writeLog(`Git initialization failed: ${e.message}`, null, true);
  } finally {
    if (button) button.disabled = false;
  }
}

async function checkpointGitWorkspace() {
  const button = byId('create-git-checkpoint');
  if (button) button.disabled = true;
  try {
    const result = await createGitCheckpoint({ event_type: 'manual_checkpoint' });
    const commitText = result.commit ? ` ${formatCommit(result.commit)}` : '';
    setGitStatus(`${result.message || 'Checkpoint complete.'}${commitText}`);
    writeLog(result.message || 'Version checkpoint complete.');
    addGitAuditEvent('Checkpoint', result.message || 'Checkpoint complete', result.commit?.short_hash || '', 'success');
    await loadGitStatus();
  } catch (e) {
    setGitStatus(`Checkpoint failed: ${e.message}`, true);
    writeLog(`Checkpoint failed: ${e.message}`, null, true);
  } finally {
    if (button) button.disabled = false;
  }
}

async function loadCurrentGitDiff() {
  const button = byId('view-current-git-diff');
  if (button) button.disabled = true;
  try {
    const payload = await getGitDiff({ maxChars: 200000 });
    setGitDiff(payload);
    setGitStatus(payload.message || 'Current diff loaded.');
  } catch (e) {
    setGitStatus(`Current diff failed: ${e.message}`, true);
    writeLog(`Current diff failed: ${e.message}`, null, true);
  } finally {
    if (button) button.disabled = false;
  }
}

async function loadSelectedGitDiff() {
  const button = byId('view-selected-git-diff');
  const ref = byId('git-history-select')?.value || '';
  if (!ref) {
    setGitStatus('Select a checkpoint to view its diff.', true);
    return;
  }
  if (button) button.disabled = true;
  try {
    const payload = await getGitDiff({ ref, maxChars: 200000 });
    setGitDiff(payload);
    setGitStatus(payload.message || 'Checkpoint diff loaded.');
  } catch (e) {
    setGitStatus(`Checkpoint diff failed: ${e.message}`, true);
    writeLog(`Checkpoint diff failed: ${e.message}`, null, true);
  } finally {
    if (button) button.disabled = false;
  }
}

async function previewSelectedRestore() {
  const button = byId('preview-git-restore');
  const ref = byId('git-history-select')?.value || '';
  if (!ref) {
    setGitStatus('Select a checkpoint to preview restore impact.', true);
    return;
  }
  if (button) button.disabled = true;
  try {
    const payload = await getGitRestorePreview({
      ref,
      path: byId('git-restore-preview-path')?.value || '',
      maxChars: 120000,
    });
    setGitRestorePreview(payload);
    setGitStatus(payload.message || 'Restore preview loaded.');
    addGitAuditEvent(
      'Restore Preview',
      'Restore preview loaded',
      `${payload.total_files || 0} file(s) · ${payload.path || 'all supported artifacts'}`,
      'info',
    );
  } catch (e) {
    setGitStatus(`Restore preview failed: ${e.message}`, true);
    writeLog(`Restore preview failed: ${e.message}`, null, true);
  } finally {
    if (button) button.disabled = false;
  }
}

function selectSupportedRestoreFiles() {
  const boxes = [...document.querySelectorAll('#git-restore-preview-rows input[type="checkbox"]')];
  for (const box of boxes) {
    box.checked = !box.disabled;
  }
  setRestorePreviewText(selectedRestoreFile());
  setGitStatus(`${checkedRestorePaths().length} restorable file(s) selected.`);
}

function clearRestoreSelection() {
  const boxes = [...document.querySelectorAll('#git-restore-preview-rows input[type="checkbox"]')];
  for (const box of boxes) {
    box.checked = false;
  }
  setRestorePreviewText(selectedRestoreFile());
  setGitStatus('Restore selection cleared.');
}

async function selectedRestorePathsChangedSincePreview(ref, paths) {
  const previewPath = gitUiState.restorePreview?.path || byId('git-restore-preview-path')?.value || '';
  const latest = await getGitRestorePreview({
    ref,
    path: previewPath,
    maxChars: 120000,
  });
  const latestFiles = Array.isArray(latest.files) ? latest.files : [];
  const changed = [];
  for (const path of paths) {
    const latestFile = latestFiles.find((file) => file.path === path);
    const latestSignature = latestFile ? restoreFileSignature(latestFile) : null;
    if (latestSignature !== gitUiState.restorePreviewSignatures.get(path)) {
      changed.push(path);
    }
  }
  if (changed.length) setGitRestorePreview(latest);
  return changed;
}

async function applySelectedRestore() {
  const button = byId('apply-git-restore');
  const ref = gitUiState.restorePreview?.ref || byId('git-history-select')?.value || '';
  const paths = checkedRestorePaths();
  if (!ref) {
    setGitStatus('Select a checkpoint before applying restore.', true);
    return;
  }
  if (!gitUiState.restorePreview) {
    setGitStatus('Preview restore impact before applying selected files.', true);
    return;
  }
  if (!paths.length) {
    setGitStatus('Select at least one restorable previewed file before applying restore.', true);
    return;
  }
  if (button) button.disabled = true;
  try {
    const stalePaths = await selectedRestorePathsChangedSincePreview(ref, paths);
    if (stalePaths.length) {
      const proceed = window.confirm(
        `${stalePaths.length} selected file(s) changed since the preview was loaded. Review the refreshed preview, then press OK to continue or Cancel to stop.`,
      );
      if (!proceed) {
        setGitStatus('Restore apply cancelled after refreshed stale-preview check.');
        if (button) button.disabled = false;
        return;
      }
    }
  } catch (e) {
    setGitStatus(`Restore stale-preview check failed: ${e.message}`, true);
    if (button) button.disabled = false;
    return;
  }
  const confirmation = window.prompt(`Type APPLY_GIT_RESTORE to restore ${paths.length} selected file(s).`, '');
  if (confirmation !== 'APPLY_GIT_RESTORE') {
    setGitStatus('Restore apply cancelled. Confirmation phrase did not match.');
    if (button) button.disabled = false;
    return;
  }
  try {
    const payload = await applyGitRestore({
      ref,
      paths,
      confirmation,
      preview_token: gitUiState.restorePreview?.preview_token || '',
      rationale: 'Applied from the Settings restore preview flow.',
    });
    setGitRestoreApplyResult(payload);
    await loadGitStatus();
    setGitStatus(payload.message || 'Restore apply completed.');
    writeLog('Restore apply completed', payload);
    addGitAuditEvent(
      'Restore Apply',
      'Restore apply completed',
      `${payload.applied_files || 0} file(s) · ${payload.after_checkpoint?.commit?.short_hash || 'no new checkpoint'}`,
      'success',
    );
  } catch (e) {
    setGitStatus(`Restore apply failed: ${e.message}`, true);
    writeLog(`Restore apply failed: ${e.message}`, null, true);
  } finally {
    if (button) button.disabled = false;
  }
}

async function runDueAutoGit() {
  const button = byId('run-due-git-autogit');
  if (button) button.disabled = true;
  try {
    const state = await runDueGitAutoGit();
    setGitAutoGitState(state);
    setGitStatus(`AutoGit status: ${state.status || 'idle'}`);
    addGitAuditEvent('AutoGit', `AutoGit ${state.status || 'idle'}`, state.last_result?.event_type || '', 'info');
    await loadGitStatus();
  } catch (e) {
    setGitStatus(`AutoGit run failed: ${e.message}`, true);
    writeLog(`AutoGit run failed: ${e.message}`, null, true);
  } finally {
    if (button) button.disabled = false;
  }
}

async function connectRemote() {
  const button = byId('connect-git-remote');
  if (button) button.disabled = true;
  try {
    const result = await connectGitRemote(collectGitRemotePayload());
    setGitStatus(result.message || 'Remote connected.');
    writeLog(result.message || 'Git remote connected.');
    addGitAuditEvent('Remote', result.message || 'Remote connected', result.remote_name || '', 'success');
    await loadGitStatus();
  } catch (e) {
    setGitStatus(`Remote connect failed: ${e.message}`, true);
    writeLog(`Remote connect failed: ${e.message}`, null, true);
  } finally {
    if (button) button.disabled = false;
  }
}

async function pushRemote() {
  const button = byId('push-git-remote');
  if (button) button.disabled = true;
  try {
    const result = await pushGitRemote({ remote_name: byId('git-remote-name')?.value || 'origin' });
    setGitStatus(result.message || 'Git push complete.');
    writeLog(result.message || 'Git push complete.');
    addGitAuditEvent('Remote', result.message || 'Git push complete', result.remote_name || '', 'success');
    await loadGitStatus();
  } catch (e) {
    setGitStatus(`Git push failed: ${e.message}`, true);
    writeLog(`Git push failed: ${e.message}`, null, true);
  } finally {
    if (button) button.disabled = false;
  }
}

async function pullRemote() {
  const button = byId('pull-git-remote');
  if (button) button.disabled = true;
  try {
    const result = await pullGitRemote({ remote_name: byId('git-remote-name')?.value || 'origin' });
    setGitStatus(result.message || 'Git pull complete.');
    writeLog(result.message || 'Git pull complete.');
    addGitAuditEvent('Remote', result.message || 'Git pull complete', result.remote_name || '', 'success');
    await loadGitStatus();
  } catch (e) {
    setGitStatus(`Git pull failed: ${e.message}`, true);
    writeLog(`Git pull failed: ${e.message}`, null, true);
  } finally {
    if (button) button.disabled = false;
  }
}

async function load() {
  try {
    const data = await fetchJson('/api/settings');
    populate(data);
    byId('settings-status').textContent = data.updated_at ? `Last updated: ${new Date(data.updated_at).toLocaleString()}` : '';
  } catch (e) {
    writeLog(`Settings load failed: ${e.message}`, null, true);
  }
}

async function save() {
  const payload = {};
  for (const f of FIELDS) {
    const el = byId(`setting-${f.key}`);
    if (el && el.value) payload[f.key] = el.value;
  }

  try {
    const result = await fetchJson('/api/settings', {
      method: 'PUT',
      headers: { 'content-type': 'application/json' },
      body: JSON.stringify(payload),
    });
    populate(result);
    byId('settings-status').textContent = 'Settings saved. API keys are active immediately.';
    writeLog('Settings saved.');
  } catch (e) {
    byId('settings-status').textContent = `Save failed: ${e.message}`;
    writeLog(`Settings save failed: ${e.message}`, null, true);
  }
}

export function init() {
  byId('save-settings').addEventListener('click', save);
  byId('refresh-backups').addEventListener('click', loadBackups);
  byId('create-backup').addEventListener('click', createBackup);
  byId('restore-backup').addEventListener('click', restoreBackup);
  byId('refresh-protection-status').addEventListener('click', loadProtectionStatus);
  byId('save-protection-policy').addEventListener('click', saveProtectionPolicy);
  byId('apply-protection-now').addEventListener('click', applyProtectionNow);
  byId('save-git-policy').addEventListener('click', saveGitPolicy);
  byId('git-guided-next-action').addEventListener('click', runGuidedGitStep);
  byId('init-git-repo').addEventListener('click', initGitRepository);
  byId('refresh-git-status').addEventListener('click', loadGitStatus);
  byId('view-current-git-diff').addEventListener('click', loadCurrentGitDiff);
  byId('view-selected-git-diff').addEventListener('click', loadSelectedGitDiff);
  byId('preview-git-restore').addEventListener('click', previewSelectedRestore);
  byId('select-supported-git-restore').addEventListener('click', selectSupportedRestoreFiles);
  byId('clear-git-restore-selection').addEventListener('click', clearRestoreSelection);
  byId('apply-git-restore').addEventListener('click', applySelectedRestore);
  byId('run-due-git-autogit').addEventListener('click', runDueAutoGit);
  byId('connect-git-remote').addEventListener('click', connectRemote);
  byId('push-git-remote').addEventListener('click', pushRemote);
  byId('pull-git-remote').addEventListener('click', pullRemote);
  byId('create-git-checkpoint').addEventListener('click', checkpointGitWorkspace);
  byId('refresh-git-activity').addEventListener('click', loadGitActivity);
  byId('git-activity-event-type').addEventListener('change', loadGitActivity);
  byId('git-activity-status').addEventListener('change', loadGitActivity);
  byId('git-activity-ref').addEventListener('change', loadGitActivity);
  load();
  loadBackups();
  loadProtectionStatus();
  loadGitPolicy();
  loadGitStatus();
}
