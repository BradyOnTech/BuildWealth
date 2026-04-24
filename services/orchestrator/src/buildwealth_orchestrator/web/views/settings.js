import {
  createGitCheckpoint,
  fetchJson,
  getGitAutoGitState,
  getGitDiff,
  getGitHistory,
  getGitPolicy,
  getGitStatus,
  initializeGitRepository,
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
          <span>Remote</span>
          <input type="text" id="git-remote-status" readonly value="Local only" />
          <span class="field-hint">Remote connection support comes after local checkpoints.</span>
        </label>
        <label class="field">
          <span>Recent History</span>
          <select id="git-history-select"></select>
          <span class="field-hint">Latest local checkpoints.</span>
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
      <div class="header-actions">
        <button class="ghost small" id="save-git-policy">Save Version Policy</button>
        <button class="ghost small" id="init-git-repo">Initialize Repository</button>
        <button class="ghost small" id="refresh-git-status">Refresh Status</button>
        <button class="ghost small" id="view-current-git-diff">View Current Diff</button>
        <button class="ghost small" id="view-selected-git-diff">View Selected Diff</button>
        <button class="ghost small" id="run-due-git-autogit">Run Due AutoGit</button>
        <button class="primary small" id="create-git-checkpoint">Create Checkpoint</button>
      </div>
      <label class="field form-span">
        <span>Diff Preview</span>
        <textarea id="git-diff-preview" rows="14" readonly placeholder="View current changes or select a checkpoint to inspect its patch."></textarea>
        <span class="field-hint">Shows generated workspace changes without leaving BuildWealth.</span>
      </label>
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
}

function collectGitPolicyPayload() {
  return {
    enabled: byId('git-enabled')?.value === 'true',
    workspace_dir: byId('git-workspace-dir')?.value || '',
    autogit_enabled: byId('git-autogit-enabled')?.value === 'true',
    auto_push_enabled: byId('git-auto-push-enabled')?.value === 'true',
    auto_checkpoint_idle_seconds: Number(byId('git-auto-checkpoint-idle-seconds')?.value || 180),
    include_financial_profile: byId('git-include-financial-profile')?.value === 'true',
  };
}

function formatCommit(commit) {
  if (!commit) return '-';
  const shortHash = commit.short_hash || String(commit.hash || '').slice(0, 7);
  const date = commit.date ? new Date(commit.date).toLocaleString() : '';
  return `${shortHash || '-'} ${commit.message || ''}${date ? ` (${date})` : ''}`.trim();
}

function setGitStatusInputs(status = {}) {
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
    remoteStatus.value = remote.has_remote ? `${remote.name || 'remote'} ahead ${remote.ahead || 0}, behind ${remote.behind || 0}` : 'Local only';
  }
}

function setGitHistory(commits = []) {
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
}

function setGitDiff(payload = {}) {
  const preview = byId('git-diff-preview');
  if (!preview) return;
  const diffText = String(payload.diff || '').trimEnd();
  const truncatedText = payload.truncated ? '\n\n[Diff truncated in preview.]' : '';
  preview.value = diffText ? `${diffText}${truncatedText}` : 'No diff available.';
}

function setGitAutoGitState(state = {}) {
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
}

async function loadGitPolicy() {
  try {
    const policy = await getGitPolicy();
    setGitPolicyInputs(policy);
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
    const [status, history, autogit] = await Promise.all([
      getGitStatus(),
      getGitHistory(10),
      getGitAutoGitState(),
    ]);
    setGitStatusInputs(status);
    setGitHistory(history.commits || []);
    setGitAutoGitState(autogit);
    setGitStatus(status.message || 'Version history status loaded.');
  } catch (e) {
    setGitStatus(`Version history status failed: ${e.message}`, true);
    writeLog(`Version history status failed: ${e.message}`, null, true);
  }
}

async function initGitRepository() {
  const button = byId('init-git-repo');
  if (button) button.disabled = true;
  try {
    const result = await initializeGitRepository();
    setGitStatus(result.message || 'Git repository initialized.');
    writeLog(result.message || 'Git repository initialized.');
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

async function runDueAutoGit() {
  const button = byId('run-due-git-autogit');
  if (button) button.disabled = true;
  try {
    const state = await runDueGitAutoGit();
    setGitAutoGitState(state);
    setGitStatus(`AutoGit status: ${state.status || 'idle'}`);
    await loadGitStatus();
  } catch (e) {
    setGitStatus(`AutoGit run failed: ${e.message}`, true);
    writeLog(`AutoGit run failed: ${e.message}`, null, true);
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
  byId('init-git-repo').addEventListener('click', initGitRepository);
  byId('refresh-git-status').addEventListener('click', loadGitStatus);
  byId('view-current-git-diff').addEventListener('click', loadCurrentGitDiff);
  byId('view-selected-git-diff').addEventListener('click', loadSelectedGitDiff);
  byId('run-due-git-autogit').addEventListener('click', runDueAutoGit);
  byId('create-git-checkpoint').addEventListener('click', checkpointGitWorkspace);
  load();
  loadBackups();
  loadProtectionStatus();
  loadGitPolicy();
  loadGitStatus();
}
