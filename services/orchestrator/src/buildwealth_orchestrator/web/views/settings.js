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
  const fields = FIELDS.map(f => `
    <label class="field">
      <span>${f.label}</span>
      <input type="${f.type}" id="setting-${f.key}" placeholder="${f.placeholder}" autocomplete="off" />
      <span class="field-hint">${f.hint}</span>
    </label>`).join('');

  return `
    <div class="view-header"><h2>Settings</h2><button class="primary small" id="save-settings">Save Settings</button></div>
    <p class="hint">Configure local Copilot settings. Values are stored locally on your machine and masked in the UI.</p>
    <div class="settings-form">
      <h3 class="section-title">AI Copilot</h3>
      <div class="settings-grid">${FIELDS.filter(f => f.key.startsWith('openai')).map(fieldHtml).join('')}</div>
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
  load();
}
