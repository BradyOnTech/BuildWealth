// SETTINGS — Connections & AI.
// One concern: get Copilot talking to a provider the user trusts.
// Backups, restore, and Git history live under Data & Recovery; this page
// does not try to be a control panel.

import { api } from '../lib/api.js';
import { state } from '../lib/state.js';
import { html, raw, $, esc, setView, delegate } from '../lib/dom.js';
import { fmtRelative } from '../lib/format.js';
import {
  PROVIDERS,
  PROVIDER_DEFAULTS,
  PROVIDER_MODELS,
  buildLlmOptionsFromSettings,
} from '../lib/llm_catalog.js';

export const meta = {
  id: 'settings',
  label: 'Connections & AI',
  numeral: '·',
  group: 'utility',
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
  contextSettings: null,           // last server snapshot of context/embedding state
  contextDraft:    null,           // working copy of embedding settings
  contextSaving:   false,
  contextTesting:  false,
  contextSaveError:null,
  contextTestResult: null,
  workspaces:       [],
  activeWorkspaceId:null,
  session:          null,
  authConfig:       null,
  hostedReadiness:  null,
  hostedReadinessError: null,
  demoResetting:    false,
  demoResetResult:  null,
  demoResetError:   null,
  accountExporting: false,
  accountExportResult: null,
  accountError: null,
  passwordChanging: false,
  passwordResult: null,
  deactivateResult: null,
  deactivateBusy: false,
  hostedCloseResult: null,
  hostedCloseBusy: false,
  accountDeletionScope: 'workspace',
  accountDeletionPreview: null,
  accountDeletionRequests: [],
  accountDeletionBusy: false,
  accountDeletionRequesting: false,
  accountDeletionCancelingId: null,
  accountDeletionResult: null,
};

const EMBEDDING_PROVIDERS = [
  { value: 'disabled',                 label: 'Disabled',                hint: 'Structured data only' },
  { value: 'ollama',                   label: 'Local Ollama',            hint: 'localhost:11434' },
  { value: 'custom_openai_compatible', label: 'Custom (OpenAI-compatible)', hint: 'Self-hosted endpoint' },
];

const EMBEDDING_DEFAULT_MODELS = {
  ollama: 'nomic-embed-text',
  custom_openai_compatible: 'text-embedding-3-small',
  disabled: 'nomic-embed-text',
};

const EMBEDDING_DEFAULT_URLS = {
  ollama: 'http://localhost:11434',
  custom_openai_compatible: '',
  disabled: 'http://localhost:11434',
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
    const [settings, contextSettings, workspaces, session, authConfig, deletionRequests, llmUsage] = await Promise.all([
      api.settings(),
      api.contextSettings().catch(() => null),
      api.workspaces().catch(() => null),
      api.authSession().catch(() => null),
      api.authConfig().catch(() => null),
      api.accountDataDeletionRequests().catch(() => null),
      api.llmUsage().catch(() => null),
    ]);
    const hostedReadiness = authConfig?.hosted_auth_enabled
      ? await api.hostedAuthReadiness().catch((err) => ({ error: err.message || 'Could not load hosted readiness.' }))
      : null;
    ui.loadedSettings = settings;
    ui.draft = toDraft(settings);
    ui.apiKeyDirty = false;
    ui.testResult = null;
    ui.saveError = null;
    ui.contextSettings = contextSettings;
    ui.llmUsage = llmUsage;
    ui.contextDraft = contextDraft(contextSettings);
    ui.contextSaving = false;
    ui.contextTesting = false;
    ui.contextSaveError = null;
    ui.contextTestResult = null;
    ui.workspaces = Array.isArray(workspaces?.items) ? workspaces.items : [];
    ui.activeWorkspaceId = workspaces?.active_workspace_id || null;
    ui.session = session;
    ui.authConfig = authConfig;
    ui.hostedReadiness = hostedReadiness?.error ? null : hostedReadiness;
    ui.hostedReadinessError = hostedReadiness?.error || null;
    ui.demoResetting = false;
    ui.demoResetResult = null;
    ui.demoResetError = null;
    ui.accountExporting = false;
    ui.accountExportResult = null;
    ui.accountError = null;
    ui.passwordChanging = false;
    ui.passwordResult = null;
    ui.deactivateResult = null;
    ui.deactivateBusy = false;
    ui.hostedCloseResult = null;
    ui.hostedCloseBusy = false;
    ui.accountDeletionScope = 'workspace';
    ui.accountDeletionPreview = null;
    ui.accountDeletionRequests = Array.isArray(deletionRequests?.items) ? deletionRequests.items : [];
    ui.accountDeletionBusy = false;
    ui.accountDeletionRequesting = false;
    ui.accountDeletionCancelingId = null;
    ui.accountDeletionResult = null;
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

  const usage = usageCard(ui.llmUsage);
  setView(shell, html`
    ${raw(masthead())}
    ${raw(sectionNav({ hasUsage: Boolean(usage) }))}
    <div class="settings-main">
      <div id="settings-ai" class="settings-section">${raw(providerCard())}</div>
      ${usage ? html`<div id="settings-usage" class="settings-section">${raw(usage)}</div>` : ''}
      <div id="settings-context" class="settings-section">${raw(contextCard())}</div>
      <div id="settings-demo" class="settings-section">${raw(demoWorkspaceCard(ui))}</div>
      <div id="settings-account" class="settings-section">${raw(accountCard(ui))}</div>
      ${raw(handoffCard())}
    </div>
  `);
}

/* ─────────────  Usage ledger card  ───────────── */

// What the household's key actually spends — counts from the provider,
// dollars as list-price estimates. Local file, nothing leaves the machine.
export function usageCard(usage = null) {
  const current = usage?.current;
  if (!current || !Array.isArray(current.rows) || !current.rows.length) return '';
  const monthLabel = usage.month || 'this month';
  const cost = Number(current.estimated_cost_usd) || 0;
  const costText = cost >= 0.01 ? `~$${cost.toFixed(2)}` : (cost > 0 ? '<$0.01' : '$0.00');
  return html`
    <section class="settings-card settings-card-quiet">
      <header class="settings-card-head">
        <div class="settings-card-kicker">Spend</div>
        <h2 class="settings-card-title">AI usage · ${monthLabel}</h2>
        <p class="settings-card-lede">
          ${costText} estimated across ${current.requests} request${current.requests === 1 ? '' : 's'}.
          Token counts from the provider; dollars are list-price estimates. Local file only.
        </p>
      </header>
      <div class="benchmark-rows">
        ${raw(current.rows.slice(0, 8).map(row => {
          const rowCost = Number(row.estimated_cost_usd) || 0;
          return html`
            <div class="benchmark-row">
              <strong>${esc(String(row.task || ''))}</strong>
              <span>${esc(String(row.model || ''))} · ${Number(row.prompt_tokens || 0).toLocaleString('en-US')} in / ${Number(row.completion_tokens || 0).toLocaleString('en-US')} out</span>
              <span>${rowCost >= 0.01 ? `~$${rowCost.toFixed(2)}` : (rowCost > 0 ? '<$0.01' : 'free / local')}</span>
            </div>
          `.toString();
        }).join(''))}
      </div>
    </section>
  `;
}

/* ─────────────  Composition  ───────────── */

function masthead() {
  const status = currentStatus();
  return html`
    <header class="settings-masthead">
      <div class="settings-masthead-text">
        <p class="settings-eyebrow">System</p>
        <h1 class="settings-title">Settings</h1>
        <p class="settings-lede">
          Connect Copilot, tune context search, and manage account data.
        </p>
      </div>
      <div class="settings-statuses">
        ${raw(statusChip(status))}
      </div>
    </header>
  `;
}

function sectionNav({ hasUsage = false } = {}) {
  const items = [
    { id: 'settings-ai', label: 'AI provider' },
    hasUsage ? { id: 'settings-usage', label: 'Usage' } : null,
    { id: 'settings-context', label: 'Context' },
    { id: 'settings-demo', label: 'Demo' },
    { id: 'settings-account', label: 'Account' },
  ].filter(Boolean);
  return html`
    <nav class="settings-nav" aria-label="Settings sections">
      ${items.map(item => html`
        <a class="settings-nav-link" href="#${item.id}" data-settings-section="${item.id}">${item.label}</a>
      `)}
    </nav>
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

function keyIsConfigured() {
  const s = ui.loadedSettings || {};
  const provider = ui.draft?.llm_provider || s.llm_provider;
  const meta = providerKeyMeta(provider);
  if (meta?.configured) return true;
  if (provider === s.llm_provider && s.llm_api_key_configured) return true;
  if (provider === s.llm_provider) {
    const masked = String(s.llm_api_key || '');
    return Boolean(masked && masked.startsWith(MASK));
  }
  return false;
}

function keyLast4() {
  const s = ui.loadedSettings || {};
  const provider = ui.draft?.llm_provider || s.llm_provider;
  const meta = providerKeyMeta(provider);
  if (meta?.last4) return String(meta.last4);
  if (provider === s.llm_provider && s.llm_api_key_last4) return String(s.llm_api_key_last4);
  if (provider === s.llm_provider) {
    const masked = String(s.llm_api_key || '');
    if (masked.startsWith(MASK) && masked.length > MASK.length) return masked.slice(-4);
  }
  return '';
}

function providerKeyMeta(provider) {
  const s = ui.loadedSettings || {};
  const meta = s.llm_provider_keys_meta;
  if (!meta || typeof meta !== 'object') return null;
  return meta[provider] || null;
}

function connectedProvidersSummary() {
  const s = ui.loadedSettings || {};
  const list = Array.isArray(s.llm_connected_providers) ? s.llm_connected_providers : [];
  const fromApi = list.filter(p => p.connected);
  if (fromApi.length) return fromApi;
  // Older backends omit llm_connected_providers — derive from catalog + key badge.
  const fallback = buildLlmOptionsFromSettings(s);
  return (fallback.connected_providers || []).map(p => ({
    id: p.id,
    label: p.label,
    connected: true,
    last4: s.llm_api_key_last4 || null,
    is_active_default: p.is_active_default,
  }));
}

function modelsForProvider(provider) {
  return PROVIDER_MODELS[provider] || [];
}

function modelSelectOptions(provider, selectedId) {
  const models = modelsForProvider(provider);
  const selected = String(selectedId || '');
  const known = models.some(m => m.id === selected);
  const options = models.map(m => {
    const rec = m.recommended ? ' · recommended' : '';
    const price = m.price ? ` · ${m.price}` : '';
    return `<option value="${esc(m.id)}" ${m.id === selected ? 'selected' : ''}>${esc(m.cost)} · ${esc(m.label)}${esc(rec)}${esc(price)}</option>`;
  });
  if (selected && !known) {
    options.unshift(`<option value="${esc(selected)}" selected>Custom · ${esc(selected)}</option>`);
  }
  options.push('<option value="__custom__">Custom model id…</option>');
  return options.join('');
}

function providerCard() {
  const d = ui.draft;
  const provider = PROVIDERS.find(p => p.value === d.llm_provider) || PROVIDERS[0];
  const configured = keyIsConfigured() && !ui.apiKeyDirty;
  const last4 = keyLast4();
  const models = modelsForProvider(d.llm_provider);
  const selectedModel = d.llm_model || '';
  const knownModel = models.some(m => m.id === selectedModel);
  const showCustomModel = d.llm_provider === 'custom_openai_compatible' || (selectedModel && !knownModel) || d._modelCustom;
  const connected = connectedProvidersSummary();

  return html`
    <section class="settings-card">
      <header class="settings-card-head">
        <div class="settings-card-kicker">Copilot</div>
        <h2 class="settings-card-title">AI providers</h2>
        <p class="settings-card-lede">
          Keys stay local. Save a key for each vendor you want — several can stay connected at once.
          Copilot’s model menu then lists every connected provider. Prefer <strong>OpenRouter</strong> for many cheap models under one key.
        </p>
      </header>

      ${connected.length ? html`
        <div class="settings-connected-strip" aria-label="Connected providers">
          <span class="settings-connected-label">Connected</span>
          ${connected.map(p => html`
            <span class="settings-connected-chip ${p.is_active_default ? 'active' : ''}" title="${esc(p.id)}">
              ${esc(p.label || p.id)}${p.last4 ? html`<span class="settings-connected-last4">…${esc(String(p.last4))}</span>` : ''}
              ${p.is_active_default ? html`<span class="settings-connected-default">default</span>` : ''}
            </span>
          `)}
        </div>
      ` : ''}

      <div class="settings-grid">
        <label class="settings-field span-2">
          <span class="settings-label">Default provider</span>
          <select id="settings-provider" class="settings-input">
            ${raw(PROVIDERS.map(p => {
              const meta = providerKeyMeta(p.value);
              const mark = meta?.configured ? ' · key saved' : '';
              return `
              <option value="${esc(p.value)}" ${p.value === d.llm_provider ? 'selected' : ''}>
                ${esc(p.label)} · ${esc(p.hint)}${esc(mark)}
              </option>`;
            }).join(''))}
          </select>
          <span class="settings-hint">
            ${d.llm_provider === 'openrouter'
              ? 'One OpenRouter key unlocks DeepSeek, Llama, mini models, and more — ideal for low cost.'
              : 'Default for new chats. Other connected providers stay available in the Copilot model picker.'}
          </span>
        </label>

        <div class="settings-field span-2">
          <span class="settings-label">
            API key
            ${configured
              ? html`<button type="button" class="link-quiet" id="settings-clear-key">Remove saved key</button>`
              : ''}
          </span>
          <div class="settings-key-row">
            <input id="settings-api-key" class="settings-input mono settings-key-input"
                   type="password" autocomplete="off" spellcheck="false"
                   name="llm_api_key"
                   placeholder="${configured ? 'Leave blank to keep saved key, or paste a new one' : `Paste your ${esc(provider.label)} API key`}"
                   value="${ui.apiKeyDirty ? esc(d.llm_api_key || '') : ''}" />
            ${configured
              ? html`<span class="settings-key-badge ok">Saved${last4 ? ` · …${esc(last4)}` : ''}</span>`
              : html`<span class="settings-key-badge warn">Not saved</span>`}
          </div>
          <span class="settings-hint">
            ${configured
              ? 'A key is stored for this workspace. Paste a new key only if you want to replace it, then Save.'
              : 'Paste the key, then Save provider. Test connection uses what you save (or the text in this field).'}
          </span>
        </div>

        <label class="settings-field span-2">
          <span class="settings-label">Model</span>
          ${models.length ? html`
            <select id="settings-model-select" class="settings-input">
              ${raw(modelSelectOptions(d.llm_provider, selectedModel))}
            </select>
          ` : ''}
          <input id="settings-model" class="settings-input mono ${models.length && !showCustomModel ? 'is-hidden' : ''}"
                 type="text" autocomplete="off" spellcheck="false"
                 placeholder="${esc(PROVIDER_DEFAULTS[d.llm_provider]?.llm_model || 'model id')}"
                 value="${esc(d.llm_model || '')}" />
          <span class="settings-hint">
            ${models.length
              ? '$, $$, $$$, $$$$ are relative cost bands. Prefer models with reliable tool calling.'
              : 'Enter any OpenAI-compatible model id your endpoint serves.'}
          </span>
          ${models.length ? html`
            <div class="settings-model-guide">
              ${models.slice(0, d.llm_provider === 'openrouter' ? 6 : 5).map(m => html`
                <button type="button" class="settings-model-chip ${m.id === selectedModel ? 'active' : ''}"
                        data-model-pick="${esc(m.id)}" title="${esc(m.blurb || '')}${m.price ? ` · ${m.price} per 1M in/out` : ''}">
                  <span class="settings-model-cost">${esc(m.cost)}</span>
                  <span class="settings-model-name">${esc(m.label)}</span>
                  ${m.recommended ? html`<span class="settings-model-rec">rec</span>` : ''}
                  ${m.cheap && !m.recommended ? html`<span class="settings-model-rec cheap">cheap</span>` : ''}
                </button>
              `)}
            </div>
          ` : ''}
        </label>

        <label class="settings-field span-2">
          <span class="settings-label">Base URL</span>
          <input id="settings-base-url" class="settings-input mono"
                 type="text" autocomplete="off" spellcheck="false"
                 placeholder="${esc(PROVIDER_DEFAULTS[d.llm_provider]?.llm_base_url || 'https://...')}"
                 value="${esc(d.llm_base_url || '')}" />
          <span class="settings-hint">Filled automatically when you switch providers.</span>
        </label>
      </div>

      <details class="settings-advanced">
        <summary>Advanced · timeouts, tools, background models</summary>
        <div class="settings-grid settings-advanced-grid">
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
              <span class="settings-hint">Batch tool calls when the provider supports it. Turn off only if ordering breaks.</span>
            </span>
          </label>

          <div class="settings-field span-2">
            <span class="settings-label">Background tasks</span>
            <span class="settings-hint">
              Summaries and draft prep can use a cheaper or local model while chat keeps the provider above.
              Leave “Same as chat” to route everything to one model.
            </span>
          </div>

          <label class="settings-field">
            <span class="settings-label">Background provider</span>
            <select id="settings-task-summarize-provider" class="settings-input">
              <option value="" ${!d.llm_task_summarize_provider ? 'selected' : ''}>Same as chat</option>
              ${raw(PROVIDERS.map(p => `
                <option value="${esc(p.value)}" ${p.value === d.llm_task_summarize_provider ? 'selected' : ''}>
                  ${esc(p.label)}
                </option>`).join(''))}
            </select>
          </label>

          <label class="settings-field">
            <span class="settings-label">Background model</span>
            <input id="settings-task-summarize-model" class="settings-input mono"
                   type="text" autocomplete="off" spellcheck="false"
                   placeholder="inherit"
                   value="${esc(d.llm_task_summarize_model || '')}" />
          </label>

          <label class="settings-field span-2">
            <span class="settings-label">Background base URL</span>
            <input id="settings-task-summarize-base-url" class="settings-input mono"
                   type="text" autocomplete="off" spellcheck="false"
                   placeholder="inherit (e.g. http://localhost:11434/v1 for Ollama)"
                   value="${esc(d.llm_task_summarize_base_url || '')}" />
          </label>
        </div>
      </details>

      <footer class="settings-actions">
        <button class="btn btn-primary" id="settings-save" ${ui.saving ? 'disabled' : ''}>
          ${ui.saving ? 'Saving…' : 'Save provider'}
        </button>
        <button class="btn btn-ghost" id="settings-test" ${ui.testing ? 'disabled' : ''}>
          ${ui.testing ? 'Testing…' : 'Test connection'}
        </button>
        <button class="btn btn-quiet" id="settings-reset-defaults">
          Reset defaults
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
  const d = ui.contextDraft || contextDraft(c);
  const provider = EMBEDDING_PROVIDERS.find(p => p.value === d.context_embedding_provider) || EMBEDDING_PROVIDERS[0];
  const isDisabled = d.context_embedding_provider === 'disabled' || !d.context_embeddings_enabled;

  return html`
    <section class="settings-card settings-card-quiet">
      <header class="settings-card-head">
        <div class="settings-card-kicker">Optional</div>
        <h2 class="settings-card-title">Context search</h2>
        <p class="settings-card-lede">
          Profile, plan, and portfolio stay the source of truth. Embeddings only help find older notes and research.
        </p>
      </header>

      <div class="settings-grid">
        <label class="settings-field span-2 settings-field-toggle">
          <input id="context-enabled" type="checkbox" ${d.context_embeddings_enabled ? 'checked' : ''} />
          <span>
            <span class="settings-label">Enable narrative search</span>
            <span class="settings-hint">When on, Copilot can pull older notes and research that aren't in your structured profile yet.</span>
          </span>
        </label>

        <label class="settings-field span-2">
          <span class="settings-label">Embedding provider</span>
          <select id="context-provider" class="settings-input">
            ${raw(EMBEDDING_PROVIDERS.map(p => `
              <option value="${esc(p.value)}" ${p.value === d.context_embedding_provider ? 'selected' : ''}>
                ${esc(p.label)} · ${esc(p.hint)}
              </option>
            `).join(''))}
          </select>
          <span class="settings-hint">Local Ollama is the most private; custom OpenAI-compatible covers self-hosted endpoints.</span>
        </label>

        <label class="settings-field">
          <span class="settings-label">Model</span>
          <input id="context-model" class="settings-input mono"
                 type="text" autocomplete="off" spellcheck="false"
                 placeholder="${esc(EMBEDDING_DEFAULT_MODELS[d.context_embedding_provider] || 'embedding model')}"
                 value="${esc(d.context_embedding_model || '')}" />
          <span class="settings-hint">${provider.value === 'ollama' ? 'nomic-embed-text is a good default for local search.' : 'Use any model that supports the provider\'s embed endpoint.'}</span>
        </label>

        <label class="settings-field">
          <span class="settings-label">Endpoint</span>
          <input id="context-base-url" class="settings-input mono"
                 type="text" autocomplete="off" spellcheck="false"
                 placeholder="${esc(EMBEDDING_DEFAULT_URLS[d.context_embedding_provider] || 'https://...')}"
                 value="${esc(d.context_embedding_base_url || '')}" />
          <span class="settings-hint">Where the embedding requests are sent.</span>
        </label>

        <label class="settings-field">
          <span class="settings-label">Timeout (seconds)</span>
          <input id="context-timeout" class="settings-input mono"
                 type="number" min="1" max="120" step="0.5"
                 value="${esc(String(d.context_embedding_timeout_seconds ?? 5))}" />
          <span class="settings-hint">Drop the request if the embedding endpoint is slow.</span>
        </label>

        ${raw(contextRow('Indexed items · candidates pending review',
          c ? `${c.registry?.item_count ?? 0} · ${c.registry?.pending_review_count ?? 0}` : '—',
          'archived',
          { mono: true }))}
      </div>

      <footer class="settings-actions">
        <button class="btn btn-primary" id="context-save" ${ui.contextSaving ? 'disabled' : ''}>
          ${ui.contextSaving ? 'Saving…' : 'Save embedding settings'}
        </button>
        <button class="btn btn-ghost" id="context-test" ${ui.contextTesting || isDisabled ? 'disabled' : ''}>
          ${ui.contextTesting ? 'Testing…' : 'Test embedding provider'}
        </button>
        ${ui.contextSaveError ? html`<p class="inline-warning">${ui.contextSaveError}</p>` : ''}
      </footer>

      ${raw(contextTestResultBlock())}
    </section>
  `;
}

function contextRow(label, value, tone, opts = {}) {
  const valueClass = `settings-context-value${opts.mono ? ' mono' : ''}`;
  return html`
    <div class="settings-context-row settings-field span-2">
      <span class="status-pill ${tone}"><span class="dot"></span></span>
      <span class="settings-context-label">${label}</span>
      <span class="${valueClass}">${value}</span>
    </div>
  `;
}

function contextTestResultBlock() {
  const r = ui.contextTestResult;
  if (!r) return '';
  if (r.ok && r.enabled) {
    return html`
      <div class="settings-test-block ok">
        <p class="settings-test-headline">Embedding handshake succeeded.</p>
        <p class="settings-test-detail">${r.provider || ''}${r.model ? ` · ${r.model}` : ''} · vector length ${r.vector_length || 0}</p>
      </div>
    `;
  }
  if (r.ok && !r.enabled) {
    return html`
      <div class="settings-test-block">
        <p class="settings-test-headline">Embeddings are off — falling back to structured data.</p>
        <p class="settings-test-detail">${r.detail || ''}</p>
      </div>
    `;
  }
  return html`
    <div class="settings-test-block fail">
      <p class="settings-test-headline">Embedding handshake failed.</p>
      <p class="settings-test-detail">${r.stage ? `${humanStage(r.stage)} · ` : ''}${truncate(r.detail || 'No detail returned.', 220)}</p>
    </div>
  `;
}

function contextDraft(snapshot) {
  // Snapshots come from /api/settings/context which exposes the current
  // settings *values* (env-driven by default). The first save promotes the
  // user-supplied values into the user_settings store.
  const s = snapshot || {};
  return {
    context_embeddings_enabled:        Boolean(s.embeddings_enabled),
    context_embedding_provider:        s.embedding_provider || 'disabled',
    context_embedding_model:           s.embedding_model || '',
    context_embedding_base_url:        s.embedding_base_url || '',
    context_embedding_timeout_seconds: Number(s.embedding_timeout_seconds ?? 5),
  };
}

/* ─────────────  Handoff card (where the rest lives)  ───────────── */

function handoffCard() {
  return html`
    <aside class="settings-handoff">
      <p class="settings-handoff-eyebrow">Backups &amp; restore</p>
      <p class="settings-handoff-body">
        Live in <a href="#atelier" class="link-editorial">Data &amp; Recovery</a> — keep Settings focused on connections and account control.
      </p>
    </aside>
  `;
}

export function demoWorkspaceCard(model) {
  const demo = (model.workspaces || []).find(w => w.is_demo || w.workspace_type === 'demo');
  const activeIsDemo = demo && model.activeWorkspaceId === demo.id;
  return html`
    <section class="settings-card settings-card-quiet">
      <header class="settings-card-head">
        <div class="settings-card-kicker">Sandbox</div>
        <h2 class="settings-card-title">Demo workspace</h2>
        <p class="settings-card-lede">
          A separate household for testing — never touches your real financial picture.
        </p>
      </header>
      ${demo ? html`
        <div class="settings-context-row settings-field span-2">
          <span class="status-pill ${activeIsDemo ? 'proposed' : 'archived'}"><span class="dot"></span></span>
          <span class="settings-context-label">${demo.name || 'Demo Household'}</span>
          <span class="settings-context-value">${activeIsDemo ? 'Active now' : 'Available'}</span>
        </div>
        <footer class="settings-actions">
          <button class="btn btn-primary" id="demo-reset" ${model.demoResetting ? 'disabled' : ''}>
            ${model.demoResetting ? 'Resetting…' : 'Reset demo data'}
          </button>
          <button class="btn btn-ghost" id="demo-switch" ${activeIsDemo ? 'disabled' : ''}>
            Switch to demo
          </button>
          ${model.demoResetError ? html`<p class="inline-warning">${model.demoResetError}</p>` : ''}
        </footer>
        ${model.demoResetResult ? html`
          <div class="settings-test-block ok">
            <p class="settings-test-headline">Demo workspace reset.</p>
            <p class="settings-test-detail">
              ${Number(model.demoResetResult.profile_household_members || 0)} household members ·
              ${Number(model.demoResetResult.recommendations || 0)} recommendations ·
              portfolio value ${model.demoResetResult.portfolio_total_value || 'seeded'}
            </p>
          </div>
        ` : ''}
      ` : html`
        <p class="settings-card-empty">
          Demo workspace is not available yet. The backend will create one during workspace bootstrap.
        </p>
      `}
    </section>
  `;
}

export function accountCard(model) {
  const exported = model.accountExportResult || null;
  const exportedWorkspaces = Number(exported?.workspaces?.length || 0);
  const exportedAudit = Number(exported?.audit_events?.length || 0);
  const authProvider = model.session?.user?.auth_provider || 'local';
  const localAccount = authProvider === 'local';
  const providerLabel = localAccount ? 'BuildWealth local sign-in' : authProvider;
  const authConfig = model.authConfig || {};
  const providerLinks = [
    ['Account security', authConfig.account_management_url],
    ['Reset password', authConfig.password_reset_url],
    ['Set up multi-factor sign-in', authConfig.mfa_enrollment_url],
    ['Set up passkeys', authConfig.passkey_enrollment_url],
  ].filter(([, href]) => href);
  return html`
    <section class="settings-card">
      <header class="settings-card-head">
        <div class="settings-card-kicker">Privacy</div>
        <h2 class="settings-card-title">Account &amp; data</h2>
        <p class="settings-card-lede">
          Export, sign-in, access closure, and data deletion.
        </p>
      </header>

      <div class="settings-actions">
        <button class="btn btn-quiet" id="account-export" ${model.accountExporting ? 'disabled' : ''}>
          ${model.accountExporting ? 'Preparing…' : 'Prepare account export'}
        </button>
      </div>

      ${exported ? html`
        <div class="settings-test-result ok">
          <p class="settings-test-headline">Account export ready.</p>
          <p>${exportedWorkspaces} workspace${exportedWorkspaces === 1 ? '' : 's'} · ${exportedAudit} recent audit event${exportedAudit === 1 ? '' : 's'} · exported ${esc(fmtRelative(exported.exported_at) || 'now')}</p>
        </div>
      ` : ''}

      <div class="settings-test-block">
        <p class="settings-test-headline">Hosted policy pages</p>
        <p class="settings-test-detail">
          Review how BuildWealth describes privacy, terms, AI use, access closure, and data deletion.
        </p>
        <div class="settings-actions">
          <a class="btn btn-quiet" href="/privacy" target="_blank" rel="noopener noreferrer">Privacy notice</a>
          <a class="btn btn-quiet" href="/terms" target="_blank" rel="noopener noreferrer">Terms</a>
          <a class="btn btn-quiet" href="/ai-disclosure" target="_blank" rel="noopener noreferrer">AI disclosure</a>
        </div>
      </div>

      ${raw(accountDataDeletionPanel(model))}

      ${localAccount ? html`
        <form id="account-password-form" class="settings-grid">
          <label class="settings-field">
            <span class="settings-label">Current password</span>
            <input class="settings-input" name="current_password" type="password" autocomplete="current-password" />
          </label>
          <label class="settings-field">
            <span class="settings-label">New password</span>
            <input class="settings-input" name="new_password" type="password" autocomplete="new-password" minlength="8" />
          </label>
          <div class="settings-actions span-2">
            <button class="btn btn-primary" type="submit" ${model.passwordChanging ? 'disabled' : ''}>
              ${model.passwordChanging ? 'Changing…' : 'Change password'}
            </button>
          </div>
        </form>

        <form id="account-deactivate-form" class="settings-grid">
          <label class="settings-field">
            <span class="settings-label">Password</span>
            <input class="settings-input" name="current_password" type="password" autocomplete="current-password" />
          </label>
          <label class="settings-field">
            <span class="settings-label">Type deactivate</span>
            <input class="settings-input" name="confirm" type="text" autocomplete="off" />
          </label>
          <div class="settings-actions span-2">
            <button class="btn btn-danger" type="submit" ${model.deactivateBusy ? 'disabled' : ''}>
              ${model.deactivateBusy ? 'Deactivating…' : 'Deactivate account'}
            </button>
          </div>
        </form>
      ` : html`
        <div class="settings-test-result">
          <p class="settings-test-headline">Sign-in security is managed by ${providerLabel}.</p>
          <p>Use your identity provider for password reset, multi-factor sign-in, and passkeys.</p>
        </div>
        ${providerLinks.length ? html`
          <div class="settings-actions">
            ${providerLinks.map(([label, href]) => html`
              <a class="btn btn-quiet" href="${href}" target="_blank" rel="noopener noreferrer">${label}</a>
            `)}
          </div>
        ` : ''}
        ${raw(hostedReadinessPanel(model.hostedReadiness, model.hostedReadinessError))}
        <div class="settings-test-block">
          <p class="settings-test-headline">Close BuildWealth access</p>
          <p class="settings-test-detail">
            This signs you out, disables your BuildWealth account, and removes active workspace memberships.
            It does not delete workspace data or your identity-provider account.
          </p>
        </div>
        <form id="account-hosted-close-form" class="settings-grid">
          <label class="settings-field span-2">
            <span class="settings-label">Type close buildwealth access</span>
            <input class="settings-input" name="confirm" type="text" autocomplete="off" />
          </label>
          <div class="settings-actions span-2">
            <button class="btn btn-danger" type="submit" ${model.hostedCloseBusy ? 'disabled' : ''}>
              ${model.hostedCloseBusy ? 'Closing…' : 'Close BuildWealth access'}
            </button>
          </div>
        </form>
      `}

      ${model.passwordResult ? html`<p class="success-banner">${esc(model.passwordResult.message || 'Password changed.')}</p>` : ''}
      ${model.deactivateResult ? html`<p class="success-banner">${esc(model.deactivateResult.message || 'Account deactivated.')}</p>` : ''}
      ${model.hostedCloseResult ? html`<p class="success-banner">${esc(model.hostedCloseResult.message || 'BuildWealth access closed.')}</p>` : ''}
      ${model.accountError ? html`<p class="inline-warning">${esc(model.accountError)}</p>` : ''}
    </section>
  `;
}

export function accountDataDeletionPanel(model) {
  const preview = model.accountDeletionPreview || null;
  const requests = Array.isArray(model.accountDeletionRequests) ? model.accountDeletionRequests : [];
  const pending = requests.filter(request => request.status === 'pending');
  const scope = model.accountDeletionScope || preview?.scope || 'workspace';
  const phrase = preview?.confirmation_phrase || deletionPhraseForScope(scope);
  const totals = preview?.totals || {};
  return html`
    <div class="settings-test-block">
      <p class="settings-test-headline">Delete BuildWealth data</p>
      <p class="settings-test-detail">
        Preview first. Deletion is delayed for ${esc(preview?.recovery_window_days || 30)} days and can be canceled during that window.
        After the window ends, a private purge job removes due workspace files, backups, and encrypted workspace secrets.
      </p>
      <div class="settings-grid">
        <label class="settings-field">
          <span class="settings-label">Deletion scope</span>
          <select class="settings-input" id="account-deletion-scope">
            <option value="workspace" ${scope === 'workspace' ? 'selected' : ''}>Current workspace</option>
            <option value="household" ${scope === 'household' ? 'selected' : ''}>Household data</option>
            <option value="account" ${scope === 'account' ? 'selected' : ''}>Account data</option>
          </select>
        </label>
        <div class="settings-actions">
          <button class="btn btn-quiet" id="account-deletion-preview" ${model.accountDeletionBusy ? 'disabled' : ''}>
            ${model.accountDeletionBusy ? 'Previewing…' : 'Preview deletion'}
          </button>
        </div>
      </div>

      ${preview ? html`
        <div class="settings-context-grid">
          <div class="settings-context-row">
            <span class="status-pill ${preview.can_request ? 'pending' : 'rejected'}"><span class="dot"></span></span>
            <span class="settings-context-label">Affected data</span>
            <span class="settings-context-value">
              ${Number(totals.workspace_count || preview.affected_workspace_count || 0)} workspace${Number(totals.workspace_count || preview.affected_workspace_count || 0) === 1 ? '' : 's'} ·
              ${Number(totals.file_count || 0)} file${Number(totals.file_count || 0) === 1 ? '' : 's'} ·
              ${formatBytes(Number(totals.size_bytes || 0))}
            </span>
          </div>
          <div class="settings-context-row">
            <span class="status-pill pending"><span class="dot"></span></span>
            <span class="settings-context-label">Secrets and backups</span>
            <span class="settings-context-value">
              ${Number(totals.secret_count || 0)} secret key${Number(totals.secret_count || 0) === 1 ? '' : 's'} ·
              ${Number(totals.backup_archive_count || 0)} backup archive${Number(totals.backup_archive_count || 0) === 1 ? '' : 's'}
            </span>
          </div>
          <div class="settings-context-row">
            <span class="status-pill archived"><span class="dot"></span></span>
            <span class="settings-context-label">Recovery window</span>
            <span class="settings-context-value">
              Purge after ${esc(formatDateTime(preview.purge_after) || preview.purge_after || 'recovery window')}
            </span>
          </div>
          <div class="settings-context-row">
            <span class="status-pill archived"><span class="dot"></span></span>
            <span class="settings-context-label">Retained</span>
            <span class="settings-context-value">${esc((preview.will_retain || []).join(' · '))}</span>
          </div>
          <div class="settings-context-row">
            <span class="status-pill archived"><span class="dot"></span></span>
            <span class="settings-context-label">Important</span>
            <span class="settings-context-value">Limited security, audit, legal, and operational records may remain.</span>
          </div>
        </div>

        <form id="account-data-deletion-form" class="settings-grid">
          <label class="settings-field span-2">
            <span class="settings-label">Type ${esc(phrase)}</span>
            <input class="settings-input" name="confirm" type="text" autocomplete="off" />
          </label>
          <div class="settings-actions span-2">
            <button class="btn btn-danger" type="submit" ${model.accountDeletionRequesting || !preview.can_request ? 'disabled' : ''}>
              ${model.accountDeletionRequesting ? 'Scheduling…' : 'Schedule deletion'}
            </button>
          </div>
        </form>
      ` : ''}

      ${pending.length ? html`
        <div class="settings-context-grid">
          ${raw(pending.map(request => deletionRequestRow(request, model)).join(''))}
        </div>
      ` : ''}
      ${model.accountDeletionResult ? html`<p class="success-banner">${esc(model.accountDeletionResult.message || 'Data deletion updated.')}</p>` : ''}
    </div>
  `;
}

function deletionRequestRow(request, model) {
  const busy = model.accountDeletionCancelingId === request.id;
  const scope = request.scope || 'workspace';
  const preview = request.preview || {};
  const count = Number(preview.affected_workspace_count || preview.totals?.workspace_count || 0);
  return html`
    <div class="settings-context-row">
      <span class="status-pill pending"><span class="dot"></span></span>
      <span class="settings-context-label">${esc(titleCase(scope))} deletion pending</span>
      <span class="settings-context-value">
        ${count || 'Pending'} workspace${count === 1 ? '' : 's'} · purge after ${esc(formatDateTime(request.purge_after) || request.purge_after || 'recovery window')}
        <button class="link-quiet danger account-data-deletion-cancel" data-request-id="${esc(request.id)}" ${busy ? 'disabled' : ''}>
          ${busy ? 'Canceling' : 'Cancel'}
        </button>
      </span>
    </div>
  `;
}

export function hostedReadinessPanel(readiness, error = '') {
  if (error) {
    return html`
      <div class="settings-test-block fail">
        <p class="settings-test-headline">Hosted sign-in readiness could not be loaded.</p>
        <p class="settings-test-detail">${esc(error)}</p>
      </div>
    `;
  }
  if (!readiness) return '';
  const checks = Array.isArray(readiness.checks) ? readiness.checks : [];
  const visible = checks.filter(check => check.status !== 'ready').slice(0, 5);
  const readyCount = checks.filter(check => check.status === 'ready').length;
  const blockedCount = checks.filter(check => check.status === 'blocked').length;
  const warningCount = checks.filter(check => check.status === 'warning').length;
  const status = readiness.status || 'warning';
  const tone = status === 'ready' ? 'ok' : (status === 'blocked' ? 'fail' : '');
  const headline = status === 'ready'
    ? `${readiness.provider || 'Hosted sign-in'} is ready for browser testing.`
    : (status === 'blocked'
      ? `${readiness.provider || 'Hosted sign-in'} has setup blockers.`
      : `${readiness.provider || 'Hosted sign-in'} has review items.`);
  return html`
    <div class="settings-test-block ${tone}">
      <p class="settings-test-headline">${headline}</p>
      <p class="settings-test-detail">
        ${readyCount} ready · ${warningCount} warning${warningCount === 1 ? '' : 's'} · ${blockedCount} blocker${blockedCount === 1 ? '' : 's'}
      </p>
      ${visible.length ? html`
        <div class="settings-readiness-list">
          ${raw(visible.map(readinessCheckRow).join(''))}
        </div>
      ` : ''}
    </div>
  `;
}

function readinessCheckRow(check) {
  const status = check?.status || 'warning';
  const tone = status === 'blocked' ? 'rejected' : (status === 'ready' ? 'applied' : 'proposed');
  return html`
    <div class="settings-context-row settings-field span-2">
      <span class="status-pill ${tone}"><span class="dot"></span>${esc(status)}</span>
      <span class="settings-context-label">${esc(check?.summary || check?.id || 'Readiness check')}</span>
      <span class="settings-context-value">${esc(truncate(check?.detail || '', 88))}</span>
    </div>
  `;
}

/* ─────────────  Events  ───────────── */

// init() runs once per route; #settings-page is a fresh node each time, so the
// handlers below survive every re-render() because we delegate from the page
// root, not from individual inputs that get replaced.
function attachHandlers() {
  const root = $('#settings-page');
  if (!root) return;

  delegate(root, 'click', '[data-settings-section]', (e, el) => {
    e.preventDefault();
    const id = el.getAttribute('data-settings-section');
    const target = id ? document.getElementById(id) : null;
    if (!target) return;
    target.scrollIntoView({ behavior: 'smooth', block: 'start' });
    root.querySelectorAll('.settings-nav-link').forEach(link => {
      link.classList.toggle('active', link.getAttribute('data-settings-section') === id);
    });
  });

  delegate(root, 'change', '#settings-provider', (_, el) => {
    const next = el.value;
    const prev = ui.draft.llm_provider;
    if (next === prev) return;
    const defaults = PROVIDER_DEFAULTS[next] || PROVIDER_DEFAULTS.openai;
    const prevDefaults = PROVIDER_DEFAULTS[prev] || {};
    const prefs = (ui.loadedSettings && ui.loadedSettings.llm_provider_prefs) || {};
    const nextPref = prefs[next] || {};
    ui.draft.llm_provider = next;
    // Restore this vendor's last model/base_url when known; else catalog defaults.
    if (nextPref.model) {
      ui.draft.llm_model = nextPref.model;
    } else if (!ui.draft.llm_model || ui.draft.llm_model === prevDefaults.llm_model
        || modelsForProvider(prev).some(m => m.id === ui.draft.llm_model)) {
      ui.draft.llm_model = defaults.llm_model;
    }
    if (nextPref.base_url) {
      ui.draft.llm_base_url = nextPref.base_url;
    } else if (!ui.draft.llm_base_url || ui.draft.llm_base_url === prevDefaults.llm_base_url) {
      ui.draft.llm_base_url = defaults.llm_base_url;
    }
    // Multi-vendor: each provider keeps its own key. Clear only the in-field
    // dirty buffer so the Saved badge reflects the vault for `next`.
    ui.draft.llm_api_key = '';
    ui.apiKeyDirty = false;
    ui.draft._modelCustom = false;
    ui.testResult = null;
    render();
  });

  delegate(root, 'input',  '#settings-api-key',   (_, el) => { ui.draft.llm_api_key = el.value; ui.apiKeyDirty = true; });
  delegate(root, 'change', '#settings-api-key',   (_, el) => { ui.draft.llm_api_key = el.value; if (el.value) ui.apiKeyDirty = true; });
  delegate(root, 'input',  '#settings-model',     (_, el) => { ui.draft.llm_model = el.value; ui.draft._modelCustom = true; });
  delegate(root, 'change', '#settings-model-select', (_, el) => {
    if (el.value === '__custom__') {
      ui.draft._modelCustom = true;
      render();
      const input = document.getElementById('settings-model');
      if (input) input.focus();
      return;
    }
    ui.draft.llm_model = el.value;
    ui.draft._modelCustom = false;
    render();
  });
  delegate(root, 'click', '[data-model-pick]', (e, el) => {
    e.preventDefault();
    const id = el.getAttribute('data-model-pick');
    if (!id) return;
    ui.draft.llm_model = id;
    ui.draft._modelCustom = false;
    render();
  });
  delegate(root, 'input',  '#settings-base-url',  (_, el) => { ui.draft.llm_base_url = el.value; });
  delegate(root, 'input',  '#settings-max-tokens',(_, el) => { ui.draft.llm_max_tokens = parseIntOr(el.value, 2048); });
  delegate(root, 'input',  '#settings-timeout',   (_, el) => { ui.draft.llm_timeout_seconds = parseFloatOr(el.value, 60); });
  delegate(root, 'change', '#settings-parallel',  (_, el) => { ui.draft.llm_parallel_tool_calls = !!el.checked; });
  delegate(root, 'change', '#settings-task-summarize-provider', (_, el) => { ui.draft.llm_task_summarize_provider = el.value; });
  delegate(root, 'input',  '#settings-task-summarize-model',    (_, el) => { ui.draft.llm_task_summarize_model = el.value; });
  delegate(root, 'input',  '#settings-task-summarize-base-url', (_, el) => { ui.draft.llm_task_summarize_base_url = el.value; });

  delegate(root, 'click',  '#settings-save',           (e) => { e.preventDefault(); save(); });
  delegate(root, 'click',  '#settings-test',           (e) => { e.preventDefault(); testProvider(); });
  delegate(root, 'click',  '#settings-reset-defaults', (e) => { e.preventDefault(); resetDefaults(); });
  delegate(root, 'click',  '#settings-clear-key',      (e) => { e.preventDefault(); clearSavedKey(); });

  // Context Intelligence card
  delegate(root, 'change', '#context-enabled', (_, el) => { ui.contextDraft.context_embeddings_enabled = !!el.checked; });
  delegate(root, 'change', '#context-provider', (_, el) => {
    const next = el.value;
    const prev = ui.contextDraft.context_embedding_provider;
    if (next === prev) return;
    ui.contextDraft.context_embedding_provider = next;
    // Auto-fill defaults if the user hasn't set values yet, so switching from
    // Disabled → Local Ollama populates a working pair.
    if (!ui.contextDraft.context_embedding_model || ui.contextDraft.context_embedding_model === EMBEDDING_DEFAULT_MODELS[prev]) {
      ui.contextDraft.context_embedding_model = EMBEDDING_DEFAULT_MODELS[next] || '';
    }
    if (!ui.contextDraft.context_embedding_base_url || ui.contextDraft.context_embedding_base_url === EMBEDDING_DEFAULT_URLS[prev]) {
      ui.contextDraft.context_embedding_base_url = EMBEDDING_DEFAULT_URLS[next] || '';
    }
    ui.contextTestResult = null;
    render();
  });
  delegate(root, 'input',  '#context-model',    (_, el) => { ui.contextDraft.context_embedding_model = el.value; });
  delegate(root, 'input',  '#context-base-url', (_, el) => { ui.contextDraft.context_embedding_base_url = el.value; });
  delegate(root, 'input',  '#context-timeout',  (_, el) => {
    const n = parseFloatOr(el.value, 5);
    ui.contextDraft.context_embedding_timeout_seconds = n;
  });
  delegate(root, 'click',  '#context-save', (e) => { e.preventDefault(); saveContext(); });
  delegate(root, 'click',  '#context-test', (e) => { e.preventDefault(); testEmbedding(); });
  delegate(root, 'click',  '#demo-reset', (e) => { e.preventDefault(); resetDemoWorkspace(); });
  delegate(root, 'click',  '#demo-switch', (e) => { e.preventDefault(); switchToDemoWorkspace(); });
  delegate(root, 'click',  '#account-export', (e) => { e.preventDefault(); prepareAccountExport(); });
  delegate(root, 'change', '#account-deletion-scope', (_, el) => {
    ui.accountDeletionScope = el.value || 'workspace';
    ui.accountDeletionPreview = null;
    ui.accountDeletionResult = null;
    render();
  });
  delegate(root, 'click',  '#account-deletion-preview', (e) => { e.preventDefault(); previewAccountDataDeletion(); });
  delegate(root, 'submit', '#account-data-deletion-form', (e, form) => { e.preventDefault(); requestAccountDataDeletion(form); });
  delegate(root, 'click',  '.account-data-deletion-cancel', (e, button) => {
    e.preventDefault();
    cancelAccountDataDeletion(button.dataset.requestId || '');
  });
  delegate(root, 'submit', '#account-password-form', (e, form) => { e.preventDefault(); changeAccountPassword(form); });
  delegate(root, 'submit', '#account-deactivate-form', (e, form) => { e.preventDefault(); deactivateAccount(form); });
  delegate(root, 'submit', '#account-hosted-close-form', (e, form) => { e.preventDefault(); closeHostedAccount(form); });
}

/* ─────────────  Actions  ───────────── */

function syncApiKeyFromDom() {
  // Browser autofill often fills password fields without firing input events.
  // Always read the live field before Save / Test so we do not probe with an
  // empty key while the user thinks one is present.
  const el = document.getElementById('settings-api-key');
  if (!el) return;
  const value = String(el.value || '');
  if (value) {
    ui.draft.llm_api_key = value;
    ui.apiKeyDirty = true;
  }
}

function hasProbeableKey() {
  syncApiKeyFromDom();
  if (ui.apiKeyDirty && String(ui.draft.llm_api_key || '').trim()) return true;
  return keyIsConfigured();
}

async function save() {
  if (ui.saving) return;
  syncApiKeyFromDom();
  if (!hasProbeableKey() && ui.apiKeyDirty && !String(ui.draft.llm_api_key || '').trim()) {
    // Explicit clear is allowed via clearSavedKey; empty dirty on first setup is a mistake.
    if (!keyIsConfigured()) {
      ui.saveError = 'Paste an API key before saving.';
      render();
      return;
    }
  }
  ui.saving = true;
  ui.saveError = null;
  render();

  const payload = buildPayload();
  try {
    const updated = await api.updateSettings(payload);
    ui.loadedSettings = updated;
    ui.draft = toDraft(updated);
    ui.apiKeyDirty = false;
    ui.draft._modelCustom = false;
    state.lastError = null;
    // Refresh topbar readiness so "Copilot · needs setup" clears immediately.
    if (typeof window !== 'undefined') {
      window.dispatchEvent(new CustomEvent('buildwealth:settings-saved'));
    }
  } catch (err) {
    ui.saveError = err.message || 'Could not save settings.';
  } finally {
    ui.saving = false;
    render();
  }
}

async function testProvider() {
  if (ui.testing) return;
  syncApiKeyFromDom();
  if (!hasProbeableKey()) {
    ui.testResult = {
      ok: false,
      stage: 'configuration',
      detail: 'No API key available. Paste your key above, click Save provider, then Test connection.',
    };
    render();
    return;
  }
  ui.testing = true;
  ui.testResult = null;
  render();

  // Prefer a saved key: if the user typed a new one, save first so the workspace
  // secret store and the probe use the same value.
  const payload = buildPayload();
  try {
    if (ui.apiKeyDirty && String(ui.draft.llm_api_key || '').trim()) {
      const updated = await api.updateSettings(payload);
      ui.loadedSettings = updated;
      ui.draft = toDraft(updated);
      ui.apiKeyDirty = false;
    }
    const result = await api.testLlmSettings(buildPayload());
    ui.testResult = result || { ok: true };
    if (typeof window !== 'undefined') {
      window.dispatchEvent(new CustomEvent('buildwealth:settings-saved'));
    }
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

async function clearSavedKey() {
  ui.draft.llm_api_key = '';
  ui.apiKeyDirty = true;
  ui.testResult = null;
  ui.saveError = null;
  render();
  // Persist the removal so "Saved" badge and topbar status update immediately.
  try {
    const updated = await api.updateSettings(buildPayload());
    ui.loadedSettings = updated;
    ui.draft = toDraft(updated);
    ui.apiKeyDirty = false;
    if (typeof window !== 'undefined') {
      window.dispatchEvent(new CustomEvent('buildwealth:settings-saved'));
    }
  } catch (err) {
    ui.saveError = err?.message || 'Could not clear the saved key.';
  }
  render();
}

async function saveContext() {
  if (ui.contextSaving) return;
  ui.contextSaving = true;
  ui.contextSaveError = null;
  render();
  try {
    // The user_settings store accepts the same keys the backend already
    // expects (context_embeddings_enabled, context_embedding_provider, etc.),
    // so we can ride the same /api/settings PUT endpoint.
    await api.updateSettings(ui.contextDraft);
    const fresh = await api.contextSettings();
    ui.contextSettings = fresh;
    ui.contextDraft = contextDraft(fresh);
  } catch (err) {
    ui.contextSaveError = err?.message || 'Could not save embedding settings.';
  } finally {
    ui.contextSaving = false;
    render();
  }
}

async function testEmbedding() {
  if (ui.contextTesting) return;
  ui.contextTesting = true;
  ui.contextTestResult = null;
  render();
  try {
    const result = await api.testEmbeddingSettings(ui.contextDraft);
    ui.contextTestResult = result || { ok: true, enabled: ui.contextDraft.context_embeddings_enabled };
  } catch (err) {
    ui.contextTestResult = err && err.detail && typeof err.detail === 'object' && 'ok' in err.detail
      ? err.detail
      : { ok: false, stage: 'embed_text', detail: err?.message || 'Test failed.' };
  } finally {
    ui.contextTesting = false;
    render();
  }
}

async function resetDemoWorkspace() {
  const demo = (ui.workspaces || []).find(w => w.is_demo || w.workspace_type === 'demo');
  if (!demo || ui.demoResetting) return;
  ui.demoResetting = true;
  ui.demoResetError = null;
  ui.demoResetResult = null;
  render();
  try {
    const result = await api.resetDemoWorkspace(demo.id);
    ui.demoResetResult = result?.summary || {};
    const workspaces = await api.workspaces().catch(() => null);
    ui.workspaces = Array.isArray(workspaces?.items) ? workspaces.items : ui.workspaces;
    ui.activeWorkspaceId = workspaces?.active_workspace_id || ui.activeWorkspaceId;
  } catch (err) {
    ui.demoResetError = err?.message || 'Could not reset demo workspace.';
  } finally {
    ui.demoResetting = false;
    render();
  }
}

async function switchToDemoWorkspace() {
  const demo = (ui.workspaces || []).find(w => w.is_demo || w.workspace_type === 'demo');
  if (!demo) return;
  try {
    await api.selectWorkspace(demo.id);
    ui.activeWorkspaceId = demo.id;
    location.hash = '#today';
    location.reload();
  } catch (err) {
    ui.demoResetError = err?.message || 'Could not switch to demo workspace.';
    render();
  }
}

async function prepareAccountExport() {
  if (ui.accountExporting) return;
  ui.accountExporting = true;
  ui.accountError = null;
  ui.accountExportResult = null;
  render();
  try {
    ui.accountExportResult = await api.exportAccount();
  } catch (err) {
    ui.accountError = err?.message || 'Could not prepare account export.';
  } finally {
    ui.accountExporting = false;
    render();
  }
}

async function previewAccountDataDeletion() {
  if (ui.accountDeletionBusy) return;
  ui.accountDeletionBusy = true;
  ui.accountError = null;
  ui.accountDeletionResult = null;
  render();
  try {
    ui.accountDeletionPreview = await api.accountDataDeletionPreview(ui.accountDeletionScope || 'workspace');
    ui.accountDeletionScope = ui.accountDeletionPreview?.scope || ui.accountDeletionScope || 'workspace';
  } catch (err) {
    ui.accountError = err?.message || 'Could not preview data deletion.';
  } finally {
    ui.accountDeletionBusy = false;
    render();
  }
}

async function requestAccountDataDeletion(form) {
  if (ui.accountDeletionRequesting) return;
  const data = new FormData(form);
  ui.accountDeletionRequesting = true;
  ui.accountError = null;
  ui.accountDeletionResult = null;
  render();
  try {
    const result = await api.requestAccountDataDeletion({
      scope: ui.accountDeletionScope || ui.accountDeletionPreview?.scope || 'workspace',
      confirm: data.get('confirm') || '',
    });
    ui.accountDeletionResult = result;
    if (result?.request) {
      ui.accountDeletionRequests = [
        result.request,
        ...(ui.accountDeletionRequests || []).filter(request => request.id !== result.request.id),
      ];
    }
    form.reset();
  } catch (err) {
    ui.accountError = err?.message || 'Could not schedule data deletion.';
  } finally {
    ui.accountDeletionRequesting = false;
    render();
  }
}

async function cancelAccountDataDeletion(requestId) {
  if (!requestId || ui.accountDeletionCancelingId) return;
  ui.accountDeletionCancelingId = requestId;
  ui.accountError = null;
  ui.accountDeletionResult = null;
  render();
  try {
    const result = await api.cancelAccountDataDeletion(requestId);
    ui.accountDeletionResult = result;
    if (result?.request) {
      ui.accountDeletionRequests = (ui.accountDeletionRequests || []).map(request => (
        request.id === result.request.id ? result.request : request
      ));
    }
    const workspaces = await api.workspaces().catch(() => null);
    if (workspaces) {
      ui.workspaces = Array.isArray(workspaces.items) ? workspaces.items : ui.workspaces;
      ui.activeWorkspaceId = workspaces.active_workspace_id || ui.activeWorkspaceId;
    }
  } catch (err) {
    ui.accountError = err?.message || 'Could not cancel data deletion.';
  } finally {
    ui.accountDeletionCancelingId = null;
    render();
  }
}

async function changeAccountPassword(form) {
  if (ui.passwordChanging) return;
  const data = new FormData(form);
  ui.passwordChanging = true;
  ui.accountError = null;
  ui.passwordResult = null;
  render();
  try {
    ui.passwordResult = await api.changeAccountPassword({
      current_password: data.get('current_password') || '',
      new_password: data.get('new_password') || '',
    });
    form.reset();
  } catch (err) {
    ui.accountError = err?.message || 'Could not change password.';
  } finally {
    ui.passwordChanging = false;
    render();
  }
}

async function deactivateAccount(form) {
  if (ui.deactivateBusy) return;
  const data = new FormData(form);
  ui.deactivateBusy = true;
  ui.accountError = null;
  ui.deactivateResult = null;
  render();
  try {
    ui.deactivateResult = await api.deactivateAccount({
      current_password: data.get('current_password') || '',
      confirm: data.get('confirm') || '',
    });
    form.reset();
  } catch (err) {
    ui.accountError = err?.message || 'Could not deactivate account.';
  } finally {
    ui.deactivateBusy = false;
    render();
  }
}

async function closeHostedAccount(form) {
  if (ui.hostedCloseBusy) return;
  const data = new FormData(form);
  ui.hostedCloseBusy = true;
  ui.accountError = null;
  ui.hostedCloseResult = null;
  render();
  try {
    ui.hostedCloseResult = await api.closeHostedAccount({
      confirm: data.get('confirm') || '',
    });
    form.reset();
  } catch (err) {
    ui.accountError = err?.message || 'Could not close BuildWealth access.';
  } finally {
    ui.hostedCloseBusy = false;
    render();
  }
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
    llm_task_summarize_provider: settings.llm_task_summarize_provider || '',
    llm_task_summarize_model:    settings.llm_task_summarize_model || '',
    llm_task_summarize_base_url: settings.llm_task_summarize_base_url || '',
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
    llm_task_summarize_provider: draft.llm_task_summarize_provider || '',
    llm_task_summarize_model:    draft.llm_task_summarize_model || '',
    llm_task_summarize_base_url: draft.llm_task_summarize_base_url || '',
  };
  // If the user hasn't typed over the key, send the mask (when configured) so
  // the server preserves the stored secret. Never invent a fake key.
  if (apiKeyDirty) {
    payload.llm_api_key = String(draft.llm_api_key || '');
  } else if (loadedSettings?.llm_api_key_configured || String(loadedSettings?.llm_api_key || '').startsWith(MASK)) {
    payload.llm_api_key = loadedSettings?.llm_api_key || MASK;
  } else {
    payload.llm_api_key = '';
  }
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

function deletionPhraseForScope(scope) {
  const normalized = String(scope || '').trim().toLowerCase();
  if (normalized === 'account') return 'delete my buildwealth data';
  if (normalized === 'household') return 'delete household data';
  return 'delete workspace data';
}

function formatBytes(bytes) {
  const n = Number(bytes || 0);
  if (!Number.isFinite(n) || n <= 0) return '0 B';
  const units = ['B', 'KB', 'MB', 'GB'];
  let value = n;
  let unit = 0;
  while (value >= 1024 && unit < units.length - 1) {
    value /= 1024;
    unit += 1;
  }
  return `${value >= 10 || unit === 0 ? Math.round(value) : value.toFixed(1)} ${units[unit]}`;
}

function formatDateTime(value) {
  if (!value) return '';
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return '';
  return date.toLocaleDateString(undefined, { month: 'short', day: 'numeric', year: 'numeric' });
}

function titleCase(value) {
  return String(value || '')
    .replace(/[_-]+/g, ' ')
    .replace(/\b\w/g, ch => ch.toUpperCase());
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
