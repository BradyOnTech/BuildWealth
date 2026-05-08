// SETTINGS — Connections & AI.
// One concern: get Copilot talking to a provider the user trusts.
// Backups, restore, and Git history live under Data & Recovery; this page
// does not try to be a control panel.

import { api } from '../lib/api.js';
import { state } from '../lib/state.js';
import { html, raw, $, esc, setView, delegate } from '../lib/dom.js';
import { fmtRelative } from '../lib/format.js';

export const meta = {
  id: 'settings',
  label: 'Connections & AI',
  numeral: '·',
  group: 'utility',
};

const PROVIDERS = [
  { value: 'openai',                   label: 'OpenAI',                       hint: 'gpt-5.5 · default' },
  { value: 'anthropic',                label: 'Anthropic',                    hint: 'Claude family' },
  { value: 'gemini',                   label: 'Google Gemini',                hint: 'gemini-3.1' },
  { value: 'xai',                      label: 'xAI',                          hint: 'Grok 4.x' },
  { value: 'custom_openai_compatible', label: 'Custom (OpenAI-compatible)',   hint: 'Self-hosted, proxies' },
];

// Mirrors services/user_settings.py LLM_PROVIDER_DEFAULTS so a provider switch
// can pre-fill model + base URL inline without a server round-trip.
const PROVIDER_DEFAULTS = {
  openai:                   { llm_model: 'gpt-5.5',                  llm_base_url: 'https://api.openai.com/v1' },
  anthropic:                { llm_model: 'claude-opus-4-7',          llm_base_url: 'https://api.anthropic.com/v1' },
  gemini:                   { llm_model: 'gemini-3.1-flash-lite',    llm_base_url: 'https://generativelanguage.googleapis.com/v1beta/openai' },
  xai:                      { llm_model: 'grok-4.20-reasoning-latest', llm_base_url: 'https://api.x.ai/v1' },
  custom_openai_compatible: { llm_model: '',                          llm_base_url: '' },
};

const MASK = '••••••••';

const ui = {
  loaded:          false,
  saving:          false,
  testing:         false,
  loadedSettings:  null,           // last server snapshot (with mask)
  draft:           null,           // working copy edited in the UI
  apiKeyDirty:     false,          // true once the user types over the masked key
  testResult:      null,           // { ok, stage, detail, provider, model } or null
  saveError:       null,
  loadError:       null,
  contextSettings: null,           // read-only context/embedding state
};

export function template() {
  return html`
    <section class="page" id="settings-page">
      <div class="settings-shell" id="settings-shell">
        ${raw(skeleton())}
      </div>
    </section>
  `;
}

export async function init() {
  attachHandlers();
  await load();
}

async function load() {
  ui.loaded = false;
  ui.loadError = null;
  try {
    const [settings, contextSettings] = await Promise.all([
      api.settings(),
      api.contextSettings().catch(() => null),
    ]);
    ui.loadedSettings = settings;
    ui.draft = toDraft(settings);
    ui.apiKeyDirty = false;
    ui.testResult = null;
    ui.saveError = null;
    ui.contextSettings = contextSettings;
    ui.loaded = true;
  } catch (err) {
    ui.loadError = err.message || 'Could not load settings.';
    state.lastError = ui.loadError;
  }
  render();
}

function render() {
  const shell = $('#settings-shell');
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
      ${raw(skeletonForm())}
    `);
    return;
  }

  setView(shell, html`
    ${raw(masthead())}
    ${raw(providerCard())}
    ${raw(contextCard())}
    ${raw(handoffCard())}
  `);
}

/* ─────────────  Composition  ───────────── */

function masthead() {
  const status = currentStatus();
  return html`
    <header class="settings-masthead">
      <p class="settings-eyebrow">§ System · Connections</p>
      <h1 class="settings-title">Connections &amp; AI</h1>
      <p class="settings-lede">
        Copilot needs an API key before it can use live AI responses.
        Pick a provider, save the key, and run a quick handshake.
      </p>
      <div class="settings-statuses">
        ${raw(statusChip(status))}
      </div>
    </header>
  `;
}

function statusChip(status) {
  const tone = status.tone;
  const label = status.label;
  const detail = status.detail;
  return html`
    <span class="status-pill ${tone}">
      <span class="dot"></span>${label}
    </span>
    ${detail ? html`<span class="settings-status-detail">${detail}</span>` : ''}
  `;
}

function currentStatus() {
  const s = ui.loadedSettings || {};
  const draft = ui.draft || {};
  if (ui.testResult && ui.testResult.ok === true)  {
    return { tone: 'applied',  label: 'Provider verified', detail: ui.testResult.provider ? `${ui.testResult.provider} · ${ui.testResult.model || ''}` : '' };
  }
  if (ui.testResult && ui.testResult.ok === false) {
    return { tone: 'rejected', label: 'Last test failed',  detail: ui.testResult.detail ? truncate(ui.testResult.detail, 88) : 'See details below.' };
  }
  if (s.llm_settings_saved_at && draft.llm_provider) {
    const when = fmtRelative(s.llm_settings_saved_at);
    return { tone: 'proposed', label: 'Saved · awaiting test', detail: when ? `Saved ${when}` : '' };
  }
  return { tone: 'pending', label: 'Not configured', detail: 'Add an API key to begin.' };
}

function truncate(value, n) {
  const text = String(value || '');
  if (text.length <= n) return text;
  return `${text.slice(0, n - 1)}…`;
}

/* ─────────────  Provider card  ───────────── */

function providerCard() {
  const d = ui.draft;
  const provider = PROVIDERS.find(p => p.value === d.llm_provider) || PROVIDERS[0];
  const apiKeyPlaceholder = d.llm_api_key && !ui.apiKeyDirty
    ? `${MASK}${d.llm_api_key.slice(-4)}`
    : `${provider.label} API key`;

  return html`
    <section class="settings-card">
      <header class="settings-card-head">
        <h2 class="settings-card-title">AI provider</h2>
        <p class="settings-card-lede">
          Used for Copilot conversations, suggestion drafting, and explanation flows.
          Settings are stored locally and masked in the UI.
        </p>
      </header>

      <div class="settings-grid">
        <label class="settings-field span-2">
          <span class="settings-label">Provider</span>
          <select id="settings-provider" class="settings-input">
            ${raw(PROVIDERS.map(p => `
              <option value="${esc(p.value)}" ${p.value === d.llm_provider ? 'selected' : ''}>
                ${esc(p.label)} · ${esc(p.hint)}
              </option>`).join(''))}
          </select>
          <span class="settings-hint">Switching provider clears the saved API key for safety.</span>
        </label>

        <label class="settings-field span-2">
          <span class="settings-label">
            API key
            ${d.llm_api_key && !ui.apiKeyDirty
              ? html`<button type="button" class="link-quiet" id="settings-clear-key">Clear saved key</button>`
              : ''}
          </span>
          <input id="settings-api-key" class="settings-input mono"
                 type="password" autocomplete="off" spellcheck="false"
                 placeholder="${esc(apiKeyPlaceholder)}"
                 value="${ui.apiKeyDirty ? esc(d.llm_api_key || '') : ''}" />
          <span class="settings-hint">
            ${d.llm_api_key && !ui.apiKeyDirty
              ? 'A key is saved. Type to replace it; leave blank to keep the existing key.'
              : 'Stored locally, never sent anywhere except the provider you choose.'}
          </span>
        </label>

        <label class="settings-field">
          <span class="settings-label">Model</span>
          <input id="settings-model" class="settings-input mono"
                 type="text" autocomplete="off" spellcheck="false"
                 placeholder="${esc(PROVIDER_DEFAULTS[d.llm_provider]?.llm_model || 'model id')}"
                 value="${esc(d.llm_model || '')}" />
          <span class="settings-hint">Use a model with reliable function/tool calling.</span>
        </label>

        <label class="settings-field">
          <span class="settings-label">Base URL</span>
          <input id="settings-base-url" class="settings-input mono"
                 type="text" autocomplete="off" spellcheck="false"
                 placeholder="${esc(PROVIDER_DEFAULTS[d.llm_provider]?.llm_base_url || 'https://...')}"
                 value="${esc(d.llm_base_url || '')}" />
          <span class="settings-hint">Provider endpoint. Defaults are filled when you switch providers.</span>
        </label>

        <label class="settings-field">
          <span class="settings-label">Max output tokens</span>
          <input id="settings-max-tokens" class="settings-input mono"
                 type="number" min="64" max="32768" step="1"
                 value="${esc(String(d.llm_max_tokens ?? 2048))}" />
          <span class="settings-hint">Caps each model response in the Copilot tool loop.</span>
        </label>

        <label class="settings-field">
          <span class="settings-label">Timeout (seconds)</span>
          <input id="settings-timeout" class="settings-input mono"
                 type="number" min="5" max="600" step="1"
                 value="${esc(String(d.llm_timeout_seconds ?? 60))}" />
          <span class="settings-hint">Per-request timeout for provider calls.</span>
        </label>

        <label class="settings-field span-2 settings-field-toggle">
          <input id="settings-parallel" type="checkbox"
                 ${d.llm_parallel_tool_calls ? 'checked' : ''} />
          <span>
            <span class="settings-label">Allow parallel tool calls</span>
            <span class="settings-hint">Lets Copilot batch tool calls when the provider supports it. Turn off only if you see ordering issues.</span>
          </span>
        </label>
      </div>

      <footer class="settings-actions">
        <button class="btn btn-primary" id="settings-save" ${ui.saving ? 'disabled' : ''}>
          ${ui.saving ? 'Saving…' : 'Save provider'}
        </button>
        <button class="btn btn-ghost" id="settings-test" ${ui.testing ? 'disabled' : ''}>
          ${ui.testing ? 'Testing…' : 'Test provider'}
        </button>
        <button class="btn btn-quiet" id="settings-reset-defaults">
          Reset model &amp; URL to defaults
        </button>
        ${ui.saveError ? html`<p class="inline-warning">${ui.saveError}</p>` : ''}
      </footer>

      ${raw(testResultBlock())}
    </section>
  `;
}

function testResultBlock() {
  if (!ui.testResult) return '';
  const r = ui.testResult;
  if (r.ok) {
    const sample = (r.tool_calls && r.tool_calls.length)
      ? `Tool call: ${r.tool_calls[0]?.name || r.tool_calls[0]?.tool || 'function'}`
      : (r.answer ? `Reply: “${truncate(r.answer, 120)}”` : 'Provider responded.');
    return html`
      <div class="settings-test-block ok">
        <p class="settings-test-headline">Handshake succeeded.</p>
        <p class="settings-test-detail">${r.provider || ''}${r.model ? ` · ${r.model}` : ''} · ${sample}</p>
      </div>
    `;
  }
  return html`
    <div class="settings-test-block fail">
      <p class="settings-test-headline">Handshake failed.</p>
      <p class="settings-test-detail">
        ${r.stage ? `${humanStage(r.stage)} · ` : ''}${truncate(r.detail || 'No detail returned.', 220)}
      </p>
    </div>
  `;
}

function humanStage(stage) {
  return String(stage || '').replace(/_/g, ' ');
}

/* ─────────────  Context Intelligence card  ───────────── */

function contextCard() {
  const c = ui.contextSettings;
  // Tone deliberately quiet — embeddings are optional for v1; the user
  // shouldn't have to learn a new vocabulary to keep using Copilot.
  return html`
    <section class="settings-card settings-card-quiet">
      <header class="settings-card-head">
        <h2 class="settings-card-title">Context intelligence</h2>
        <p class="settings-card-lede">
          Structured profile, plan, and portfolio data are always the source of truth.
          Optional embeddings let Copilot search older notes, research, and conversation
          history when nothing structured is close enough.
        </p>
      </header>

      <div class="settings-context-grid">
        ${raw(contextRow('Context engine', 'On — always running.', 'applied'))}
        ${raw(contextRow(
          'Narrative search (embeddings)',
          c ? (c.embeddings_enabled ? 'On — searching narrative context.' : 'Off — structured data only.') : '—',
          c && c.embeddings_enabled ? 'applied' : 'archived',
        ))}
        ${raw(contextRow(
          'Embedding provider',
          c ? humanProvider(c.embedding_provider) : '—',
          'archived',
        ))}
        ${raw(contextRow(
          'Embedding model',
          c?.embedding_model || '—',
          'archived',
          { mono: true },
        ))}
        ${raw(contextRow(
          'Embedding endpoint',
          c?.embedding_base_url || '—',
          'archived',
          { mono: true },
        ))}
        ${raw(contextRow(
          'Indexed items · candidates pending review',
          c ? `${c.registry?.item_count ?? 0} · ${c.registry?.pending_review_count ?? 0}` : '—',
          'archived',
          { mono: true },
        ))}
      </div>

      <p class="settings-context-note">
        These are read-only for now. To change them, set
        <code>CONTEXT_EMBEDDINGS_ENABLED</code>, <code>CONTEXT_EMBEDDING_PROVIDER</code>,
        <code>CONTEXT_EMBEDDING_MODEL</code>, or <code>CONTEXT_EMBEDDING_BASE_URL</code>
        in the orchestrator environment and restart. User-level editing arrives
        in a follow-up slice.
      </p>
    </section>
  `;
}

function contextRow(label, value, tone, opts = {}) {
  const valueClass = `settings-context-value${opts.mono ? ' mono' : ''}`;
  return html`
    <div class="settings-context-row">
      <span class="status-pill ${tone}"><span class="dot"></span></span>
      <span class="settings-context-label">${label}</span>
      <span class="${valueClass}">${value}</span>
    </div>
  `;
}

function humanProvider(value) {
  if (!value) return '—';
  if (value === 'disabled') return 'Disabled';
  if (value === 'ollama')   return 'Local Ollama';
  if (value === 'custom_openai_compatible') return 'Custom (OpenAI-compatible)';
  return String(value).replace(/_/g, ' ');
}

/* ─────────────  Handoff card (where the rest lives)  ───────────── */

function handoffCard() {
  return html`
    <aside class="settings-handoff">
      <p class="settings-handoff-eyebrow">Looking for backups, restore, or version history?</p>
      <p class="settings-handoff-body">
        Those tools live in <a href="#atelier" class="link-editorial">Data &amp; Recovery</a>.
        Connections &amp; AI is intentionally narrow — provider, model, and the keys that make Copilot work.
      </p>
    </aside>
  `;
}

/* ─────────────  Events  ───────────── */

// init() runs once per route; #settings-page is a fresh node each time, so the
// handlers below survive every re-render() because we delegate from the page
// root, not from individual inputs that get replaced.
function attachHandlers() {
  const root = $('#settings-page');
  if (!root) return;

  delegate(root, 'change', '#settings-provider', (_, el) => {
    const next = el.value;
    const prev = ui.draft.llm_provider;
    if (next === prev) return;
    const defaults = PROVIDER_DEFAULTS[next] || PROVIDER_DEFAULTS.openai;
    const prevDefaults = PROVIDER_DEFAULTS[prev] || {};
    ui.draft.llm_provider = next;
    if (!ui.draft.llm_model || ui.draft.llm_model === prevDefaults.llm_model) {
      ui.draft.llm_model = defaults.llm_model;
    }
    if (!ui.draft.llm_base_url || ui.draft.llm_base_url === prevDefaults.llm_base_url) {
      ui.draft.llm_base_url = defaults.llm_base_url;
    }
    // The saved key belonged to the previous provider; clear it on the draft so
    // a Save with this draft removes it server-side. The user sees the field empty.
    ui.draft.llm_api_key = '';
    ui.apiKeyDirty = true;
    ui.testResult = null;
    render();
  });

  delegate(root, 'input',  '#settings-api-key',   (_, el) => { ui.draft.llm_api_key = el.value; ui.apiKeyDirty = true; });
  delegate(root, 'input',  '#settings-model',     (_, el) => { ui.draft.llm_model = el.value; });
  delegate(root, 'input',  '#settings-base-url',  (_, el) => { ui.draft.llm_base_url = el.value; });
  delegate(root, 'input',  '#settings-max-tokens',(_, el) => { ui.draft.llm_max_tokens = parseIntOr(el.value, 2048); });
  delegate(root, 'input',  '#settings-timeout',   (_, el) => { ui.draft.llm_timeout_seconds = parseFloatOr(el.value, 60); });
  delegate(root, 'change', '#settings-parallel',  (_, el) => { ui.draft.llm_parallel_tool_calls = !!el.checked; });

  delegate(root, 'click',  '#settings-save',           (e) => { e.preventDefault(); save(); });
  delegate(root, 'click',  '#settings-test',           (e) => { e.preventDefault(); testProvider(); });
  delegate(root, 'click',  '#settings-reset-defaults', (e) => { e.preventDefault(); resetDefaults(); });
  delegate(root, 'click',  '#settings-clear-key',      (e) => { e.preventDefault(); clearSavedKey(); });
}

/* ─────────────  Actions  ───────────── */

async function save() {
  if (ui.saving) return;
  ui.saving = true;
  ui.saveError = null;
  render();

  const payload = buildPayload();
  try {
    const updated = await api.updateSettings(payload);
    ui.loadedSettings = updated;
    ui.draft = toDraft(updated);
    ui.apiKeyDirty = false;
    state.lastError = null;
  } catch (err) {
    ui.saveError = err.message || 'Could not save settings.';
  } finally {
    ui.saving = false;
    render();
  }
}

async function testProvider() {
  if (ui.testing) return;
  ui.testing = true;
  ui.testResult = null;
  render();

  const payload = buildPayload();
  try {
    const result = await api.testLlmSettings(payload);
    ui.testResult = result || { ok: true };
  } catch (err) {
    // The endpoint returns the failure shape inside HTTPException.detail; the
    // fetch helper has already flattened that into err.message text.
    ui.testResult = parseTestError(err);
  } finally {
    ui.testing = false;
    render();
  }
}

function resetDefaults() {
  const defaults = PROVIDER_DEFAULTS[ui.draft.llm_provider] || PROVIDER_DEFAULTS.openai;
  ui.draft.llm_model = defaults.llm_model;
  ui.draft.llm_base_url = defaults.llm_base_url;
  render();
}

function clearSavedKey() {
  ui.draft.llm_api_key = '';
  ui.apiKeyDirty = true;
  ui.testResult = null;
  render();
}

/* ─────────────  Plumbing  ───────────── */

export function toDraft(settings) {
  // Accept the masked-key shape from /api/settings and treat the masked
  // string as authoritative until the user types over it.
  return {
    llm_provider:             settings.llm_provider || 'openai',
    llm_api_key:              settings.llm_api_key  || '',
    llm_model:                settings.llm_model    || '',
    llm_base_url:             settings.llm_base_url || '',
    llm_max_tokens:           Number(settings.llm_max_tokens ?? 2048),
    llm_timeout_seconds:      Number(settings.llm_timeout_seconds ?? 60),
    llm_parallel_tool_calls:  Boolean(settings.llm_parallel_tool_calls ?? true),
  };
}

export function buildPayloadFor({ draft, apiKeyDirty, loadedSettings }) {
  const payload = {
    llm_provider:            draft.llm_provider,
    llm_model:               draft.llm_model,
    llm_base_url:            draft.llm_base_url,
    llm_max_tokens:          draft.llm_max_tokens,
    llm_timeout_seconds:     draft.llm_timeout_seconds,
    llm_parallel_tool_calls: draft.llm_parallel_tool_calls,
  };
  // If the user hasn't typed over the masked key, send the mask back so the
  // server preserves the stored value (UserSettingsStore.save understands this).
  payload.llm_api_key = apiKeyDirty
    ? draft.llm_api_key
    : (loadedSettings?.llm_api_key || '');
  return payload;
}

function buildPayload() {
  return buildPayloadFor({ draft: ui.draft, apiKeyDirty: ui.apiKeyDirty, loadedSettings: ui.loadedSettings });
}

export function parseTestError(err) {
  // FastAPI HTTPException with dict detail flows through fetchJson and lands
  // on `err.detail`; older responses may give us a string in `err.message`.
  if (err && err.detail && typeof err.detail === 'object' && 'ok' in err.detail) {
    return err.detail;
  }
  const text = err?.message ? String(err.message) : 'Test failed.';
  return { ok: false, stage: 'provider_error', detail: text };
}

function parseIntOr(value, fallback) {
  const n = parseInt(value, 10);
  return Number.isFinite(n) ? n : fallback;
}

function parseFloatOr(value, fallback) {
  const n = parseFloat(value);
  return Number.isFinite(n) ? n : fallback;
}

/* ─────────────  Skeletons  ───────────── */

function skeleton() {
  return html`
    ${raw(masthead())}
    ${raw(skeletonForm())}
  `;
}

function skeletonForm() {
  return html`
    <section class="settings-card">
      <div class="skeleton" style="height: 28px; width: 220px;">.</div>
      <div class="skeleton" style="height: 72px; margin-top: 12px;">.</div>
      <div class="skeleton" style="height: 72px; margin-top: 8px;">.</div>
      <div class="skeleton" style="height: 72px; margin-top: 8px;">.</div>
    </section>
  `;
}
