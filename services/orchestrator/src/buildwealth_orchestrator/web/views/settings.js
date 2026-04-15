import { fetchJson } from '../lib/api.js';
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
  load();
  loadBackups();
}
