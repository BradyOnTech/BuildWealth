import { fetchJson } from '../lib/api.js';
import { state } from '../lib/state.js';
import { byId, fmtDate, truncate, writeLog } from '../lib/utils.js';
import { planSelectOptions } from '../lib/components.js';

const DEFAULT_RESEARCH_PERIOD = '6mo';
const DEFAULT_RESEARCH_INTERVAL = '1d';
const DEFAULT_RESEARCH_SYMBOL_LIMIT = 5;
const DEFAULT_SUMMARY_MAX_CHARS = 1800;
const DEFAULT_CONTEXT_DETAIL_LEVEL = 'light';

export const id = 'copilot';
export const label = 'Copilot';
export const icon = '<svg viewBox="0 0 20 20" fill="none" stroke="currentColor" stroke-width="1.6"><path d="M4 5h12a1 1 0 011 1v7a1 1 0 01-1 1H8l-4 3V6a1 1 0 011-1z"/><circle cx="8" cy="10" r="0.8" fill="currentColor"/><circle cx="12" cy="10" r="0.8" fill="currentColor"/></svg>';

export function template() {
  return `
    <div class="view-header">
      <h2>BuildWealth Copilot</h2>
      <div class="header-actions"><button class="ghost small" id="reload-conversations">Reload</button><button class="primary small" id="new-conversation">New Chat</button></div>
    </div>
    <p class="hint">Ask questions about your portfolio, contribution strategy, and investment ideas using synced account context.</p>
    <div class="split-layout">
      <aside class="sidebar-panel">
        <p class="sidebar-label">Conversations</p>
        <div id="conversation-list" class="sidebar-list"></div>
      </aside>
      <section class="main-panel">
        <section class="copilot-context-card">
          <div class="copilot-context-header">
            <p class="sidebar-label">Unified Context</p>
            <div class="header-actions">
              <button class="ghost small" id="copilot-reset-context-cache" type="button">Reset Cache</button>
              <button class="ghost small" id="copilot-refresh-context" type="button">Refresh Context</button>
            </div>
          </div>
          <div class="copilot-context-controls">
            <label class="inline-check"><input type="checkbox" id="copilot-use-unified-context" /> Use unified context in chat</label>
            <label class="inline-check"><input type="checkbox" id="copilot-include-research-context" /> Include research highlights</label>
            <label class="inline-check"><input type="checkbox" id="copilot-include-projection-context" /> Include baseline projection</label>
            <label class="field compact-field"><span>Research Symbols (optional)</span><input id="copilot-research-symbols" type="text" placeholder="AAPL, MSFT, VTI" /></label>
          </div>
          <p id="copilot-context-meta" class="hint copilot-context-meta">No context preview loaded yet.</p>
          <pre id="copilot-context-summary" class="copilot-context-summary empty">Click "Refresh Context" to preview the package sent to Copilot.</pre>
        </section>
        <div id="chat-messages" class="chat-messages"></div>
        <form id="copilot-form" class="copilot-form">
          <label class="field"><span>Question</span>
            <textarea id="copilot-question" rows="3" placeholder="Example: What is my concentration risk and which contribution change improves long-term outcomes most?" required></textarea>
          </label>
          <div class="copilot-controls">
            <label class="field compact-field"><span>Plan</span><select id="copilot-plan"></select></label>
            <label class="inline-check"><input type="checkbox" id="copilot-live-context" /> Live context</label>
            <button class="primary" id="copilot-send" type="submit">Ask Copilot</button>
          </div>
        </form>
      </section>
    </div>`;
}

function parseSymbolInput(rawValue) {
  const seen = new Set();
  const symbols = [];
  for (const chunk of String(rawValue || '').split(',')) {
    const symbol = chunk.trim().toUpperCase().replace(/[^A-Z0-9._-]+/g, '');
    if (!symbol || seen.has(symbol)) continue;
    seen.add(symbol);
    symbols.push(symbol);
    if (symbols.length >= DEFAULT_RESEARCH_SYMBOL_LIMIT) break;
  }
  return symbols;
}

function readContextControlsToState() {
  state.copilotUseUnifiedContext = byId('copilot-use-unified-context').checked;
  state.copilotIncludeResearchContext = byId('copilot-include-research-context').checked;
  state.copilotIncludeProjectionContext = byId('copilot-include-projection-context').checked;
  state.copilotResearchSymbols = byId('copilot-research-symbols').value || '';
}

function syncContextControlsFromState() {
  byId('copilot-use-unified-context').checked = !!state.copilotUseUnifiedContext;
  byId('copilot-include-research-context').checked = !!state.copilotIncludeResearchContext;
  byId('copilot-include-projection-context').checked = !!state.copilotIncludeProjectionContext;
  byId('copilot-research-symbols').value = state.copilotResearchSymbols || '';
  setContextControlAvailability();
}

function setContextControlAvailability() {
  const enabled = byId('copilot-use-unified-context').checked;
  byId('copilot-include-research-context').disabled = !enabled;
  byId('copilot-include-projection-context').disabled = !enabled;
  byId('copilot-research-symbols').disabled = !enabled;
}

function buildContextOptionsFromState() {
  const useUnifiedContext = !!state.copilotUseUnifiedContext;
  const symbols = useUnifiedContext ? parseSymbolInput(state.copilotResearchSymbols) : [];
  return {
    include_research: useUnifiedContext && !!state.copilotIncludeResearchContext,
    include_plan_projection: useUnifiedContext && !!state.copilotIncludeProjectionContext,
    force_refresh: false,
    detail_level: DEFAULT_CONTEXT_DETAIL_LEVEL,
    research_symbols: symbols,
    research_period: DEFAULT_RESEARCH_PERIOD,
    research_interval: DEFAULT_RESEARCH_INTERVAL,
    research_symbol_limit: DEFAULT_RESEARCH_SYMBOL_LIMIT,
    summary_max_chars: DEFAULT_SUMMARY_MAX_CHARS,
  };
}

function renderContextSummary() {
  const summaryEl = byId('copilot-context-summary');
  const metaEl = byId('copilot-context-meta');
  if (state.copilotContextLoading) {
    metaEl.textContent = 'Refreshing unified context...';
    summaryEl.classList.remove('empty');
    summaryEl.textContent = 'Refreshing unified context...';
    return;
  }

  if (!state.copilotContextPayload) {
    metaEl.textContent = 'No context preview loaded yet.';
    summaryEl.classList.add('empty');
    summaryEl.textContent = 'Click "Refresh Context" to preview the package sent to Copilot.';
    return;
  }

  const payload = state.copilotContextPayload;
  const warnings = Array.isArray(payload.warnings) ? payload.warnings.length : 0;
  const updatedAt = state.copilotContextUpdatedAt ? fmtDate(state.copilotContextUpdatedAt) : 'unknown time';
  const cache = payload && typeof payload.cache === 'object' ? payload.cache : null;
  const quality = payload && typeof payload.quality === 'object' ? payload.quality : null;
  const cacheDetails = [];
  if (cache?.enabled) {
    if (typeof cache?.research?.hit === 'boolean') {
      const writeLabel = typeof cache?.research?.written === 'boolean' ? `, write ${cache.research.written ? 'yes' : 'no'}` : '';
      cacheDetails.push(`research cache ${cache.research.hit ? 'hit' : 'miss'}${writeLabel}`);
    }
    if (typeof cache?.baseline_projection?.hit === 'boolean') {
      const writeLabel = typeof cache?.baseline_projection?.written === 'boolean' ? `, write ${cache.baseline_projection.written ? 'yes' : 'no'}` : '';
      cacheDetails.push(`projection cache ${cache.baseline_projection.hit ? 'hit' : 'miss'}${writeLabel}`);
    }
    if (cache?.read_enabled === false && cache?.bypass_reason) {
      cacheDetails.push(`cache read bypassed (${cache.bypass_reason})`);
    }
  }
  const qualityDetails = [];
  const coverageScore = Number(quality?.coverage?.score_pct);
  if (Number.isFinite(coverageScore)) {
    qualityDetails.push(`coverage ${coverageScore.toFixed(1)}%`);
  }
  const staleState = quality?.freshness?.snapshot_stale;
  const snapshotAgeSeconds = Number(quality?.freshness?.snapshot_age_seconds);
  if (staleState === true && Number.isFinite(snapshotAgeSeconds)) {
    qualityDetails.push(`snapshot stale (${(snapshotAgeSeconds / 3600).toFixed(1)}h old)`);
  } else if (staleState === false && Number.isFinite(snapshotAgeSeconds)) {
    qualityDetails.push(`snapshot fresh (${(snapshotAgeSeconds / 3600).toFixed(1)}h old)`);
  }
  if (quality?.summary?.truncated === true) {
    qualityDetails.push('summary truncated');
  }

  const metaBits = [`Last refreshed ${updatedAt}`];
  if (warnings) metaBits.push(`${warnings} warning(s)`);
  if (qualityDetails.length) metaBits.push(qualityDetails.join(', '));
  if (cacheDetails.length) metaBits.push(cacheDetails.join(', '));
  metaEl.textContent = metaBits.join(' • ');

  const summary = String(state.copilotContextSummary || '').trim();
  if (summary) {
    summaryEl.classList.remove('empty');
    summaryEl.textContent = summary;
  } else {
    summaryEl.classList.add('empty');
    summaryEl.textContent = 'Context summary is empty; open Dev Log for full payload details.';
  }
}

function setContextBusy(busy) {
  state.copilotContextLoading = busy;
  const button = byId('copilot-refresh-context');
  const resetButton = byId('copilot-reset-context-cache');
  button.disabled = busy;
  button.textContent = busy ? 'Refreshing...' : 'Refresh Context';
  if (resetButton) {
    resetButton.disabled = busy;
  }
  renderContextSummary();
}

async function resetContextCache() {
  if (state.copilotContextLoading) return;
  writeLog('Resetting unified context caches...');
  try {
    const status = await fetchJson('/api/copilot/context/cache/reset', {
      method: 'POST',
      headers: { 'content-type': 'application/json' },
      body: JSON.stringify({}),
    });
    const stores = Array.isArray(status?.stores) ? status.stores : [];
    writeLog('Unified context caches reset.', { stores });
    await refreshContextPreview();
  } catch (error) {
    writeLog(`Context cache reset failed: ${error.message}`, null, true);
  }
}

async function refreshContextPreview() {
  if (state.copilotContextLoading) return;
  readContextControlsToState();
  const selectedPlanId = byId('copilot-plan').value || null;
  state.copilotPlanId = selectedPlanId || '';
  const useLiveSnapshot = byId('copilot-live-context').checked;
  const contextOptions = buildContextOptionsFromState();
  const refreshContextOptions = { ...contextOptions, force_refresh: true };
  const params = new URLSearchParams();
  params.set('use_live_snapshot', useLiveSnapshot ? 'true' : 'false');
  if (selectedPlanId) params.set('plan_id', selectedPlanId);
  params.set('include_research', refreshContextOptions.include_research ? 'true' : 'false');
  params.set('include_plan_projection', refreshContextOptions.include_plan_projection ? 'true' : 'false');
  params.set('force_refresh', 'true');
  params.set('research_period', refreshContextOptions.research_period);
  params.set('research_interval', refreshContextOptions.research_interval);
  params.set('research_symbol_limit', String(refreshContextOptions.research_symbol_limit));
  params.set('summary_max_chars', String(refreshContextOptions.summary_max_chars));
  params.set('detail_level', String(refreshContextOptions.detail_level || DEFAULT_CONTEXT_DETAIL_LEVEL));
  if (refreshContextOptions.research_symbols.length) {
    params.set('research_symbols', refreshContextOptions.research_symbols.join(','));
  }

  setContextBusy(true);
  writeLog('Refreshing unified context preview...', {
    plan_id: selectedPlanId,
    use_live_snapshot: useLiveSnapshot,
    context_options: refreshContextOptions,
  });
  try {
    const payload = await fetchJson(`/api/copilot/context?${params.toString()}`);
    state.copilotContextPayload = payload;
    state.copilotContextSummary = String(payload.summary || '').trim();
    state.copilotContextUpdatedAt = payload.generated_at || new Date().toISOString();
    renderContextSummary();
    writeLog('Unified context refreshed.', {
      generated_at: payload.generated_at,
      warnings: Array.isArray(payload.warnings) ? payload.warnings.length : 0,
    });
  } catch (error) {
    writeLog(`Unified context refresh failed: ${error.message}`, null, true);
    state.copilotContextSummary = '';
    state.copilotContextPayload = null;
    state.copilotContextUpdatedAt = null;
    renderContextSummary();
  } finally {
    setContextBusy(false);
  }
}

function renderConversationList() {
  const el = byId('conversation-list');
  el.innerHTML = '';
  if (!state.conversations.length) { el.innerHTML = '<p class="empty-text">No saved conversations yet.</p>'; return; }
  for (const c of state.conversations) {
    const btn = document.createElement('button');
    btn.type = 'button';
    btn.className = `sidebar-item${c.id === state.currentConversationId ? ' active' : ''}`;
    btn.innerHTML = `<p class="sidebar-item-title">${c.title || 'Conversation'}</p><p class="sidebar-item-meta">${truncate(c.last_message_preview || '', 88)}</p><p class="sidebar-item-meta">${fmtDate(c.updated_at)}</p>`;
    btn.addEventListener('click', () => loadConversation(c.id).catch(e => writeLog(e.message, null, true)));
    el.appendChild(btn);
  }
}

function renderToolTraces(toolCalls) {
  const wrap = document.createElement('div');
  wrap.className = 'tool-trace-list';
  for (const tc of toolCalls) {
    const details = document.createElement('details');
    details.className = 'tool-trace';
    details.innerHTML = `<summary>Tool: ${tc.name || 'unknown'} (${tc.error ? 'error' : 'ok'})</summary><pre>${JSON.stringify(tc, null, 2)}</pre>`;
    wrap.appendChild(details);
  }
  return wrap;
}

function renderMessages() {
  const el = byId('chat-messages');
  el.innerHTML = '';
  if (!state.currentMessages.length) {
    el.innerHTML = '<p class="empty-text">Start a new conversation. Copilot will use your snapshot, sync status, and selected plan context.</p>';
    return;
  }
  for (const m of state.currentMessages) {
    const role = m.role === 'user' ? 'user' : 'assistant';
    const wrap = document.createElement('article');
    wrap.className = `message ${role}`;
    wrap.innerHTML = `<p class="message-meta">${role === 'user' ? 'You' : 'Copilot'} \u2022 ${fmtDate(m.created_at)}</p><p class="message-content">${String(m.content || '')}</p>`;
    if (role === 'assistant') {
      const tc = Array.isArray(m.metadata?.tool_calls) ? m.metadata.tool_calls : [];
      if (tc.length) wrap.appendChild(renderToolTraces(tc));
    }
    el.appendChild(wrap);
  }
  el.scrollTop = el.scrollHeight;
}

function setBusy(busy) {
  state.copilotLoading = busy;
  byId('copilot-send').disabled = busy;
  byId('copilot-send').textContent = busy ? 'Thinking...' : 'Ask Copilot';
  byId('copilot-question').disabled = busy;
  byId('new-conversation').disabled = busy;
}

async function loadConversations(autoSelect = true) {
  const list = await fetchJson('/api/copilot/conversations?limit=80');
  state.conversations = Array.isArray(list) ? list : [];
  if (state.currentConversationId && !state.conversations.some(c => c.id === state.currentConversationId)) {
    state.currentConversationId = null;
    state.currentMessages = [];
  }
  if (autoSelect && !state.currentConversationId && state.conversations.length) {
    state.currentConversationId = state.conversations[0].id;
  }
  renderConversationList();
  if (state.currentConversationId) await loadConversation(state.currentConversationId);
  else renderMessages();
}

async function loadConversation(conversationId) {
  if (!conversationId) return;
  const payload = await fetchJson(`/api/copilot/conversations/${encodeURIComponent(conversationId)}`);
  state.currentConversationId = payload.id;
  state.currentMessages = Array.isArray(payload.messages) ? payload.messages : [];
  renderConversationList();
  renderMessages();
}

function startNew() {
  state.currentConversationId = null;
  state.currentMessages = [];
  renderConversationList();
  renderMessages();
  byId('copilot-question').focus();
}

async function submit(event) {
  event.preventDefault();
  if (state.copilotLoading) return;
  const input = byId('copilot-question');
  const question = input.value.trim();
  if (!question) return;
  readContextControlsToState();
  const contextOptions = buildContextOptionsFromState();
  const useUnifiedContext = !!state.copilotUseUnifiedContext;

  state.currentMessages.push({ role: 'user', content: question, created_at: new Date().toISOString(), metadata: {} });
  renderMessages();
  input.value = '';
  const selectedPlanId = byId('copilot-plan').value || null;
  state.copilotPlanId = selectedPlanId || '';
  const payload = {
    question,
    conversation_id: state.currentConversationId,
    use_live_snapshot: byId('copilot-live-context').checked,
    plan_id: selectedPlanId,
    context_options: contextOptions,
  };
  setBusy(true);
  writeLog('Sending Copilot request...', { ...payload, use_unified_context: useUnifiedContext });
  try {
    const result = await fetchJson('/api/copilot/chat', { method: 'POST', headers: { 'content-type': 'application/json' }, body: JSON.stringify(payload) });
    state.currentConversationId = result.conversation_id;
    state.currentMessages.push({ role: 'assistant', content: result.answer || '', created_at: result.created_at || new Date().toISOString(), metadata: { tool_calls: Array.isArray(result.tool_calls) ? result.tool_calls : [], model: result.model || null } });
    renderMessages();
    writeLog('Copilot response received.', { conversation_id: result.conversation_id, tool_calls: Array.isArray(result.tool_calls) ? result.tool_calls.length : 0 });
    await loadConversations(false);
    await loadConversation(state.currentConversationId);
  } catch (error) {
    state.currentMessages.push({ role: 'assistant', content: `Copilot request failed: ${error.message}`, created_at: new Date().toISOString(), metadata: {} });
    renderMessages();
    writeLog(`Copilot failed: ${error.message}`, null, true);
  } finally { setBusy(false); }
}

export function init(params = {}) {
  planSelectOptions('copilot-plan', state.copilotPlanId);
  syncContextControlsFromState();
  renderContextSummary();

  byId('reload-conversations').addEventListener('click', () => loadConversations(false).catch(e => writeLog(e.message, null, true)));
  byId('new-conversation').addEventListener('click', startNew);
  byId('copilot-reset-context-cache').addEventListener('click', () => resetContextCache().catch(e => writeLog(e.message, null, true)));
  byId('copilot-refresh-context').addEventListener('click', () => refreshContextPreview().catch(e => writeLog(e.message, null, true)));
  byId('copilot-form').addEventListener('submit', submit);

  byId('copilot-plan').addEventListener('change', (e) => {
    state.copilotPlanId = e.target.value || '';
  });
  byId('copilot-use-unified-context').addEventListener('change', () => {
    readContextControlsToState();
    setContextControlAvailability();
  });
  byId('copilot-include-research-context').addEventListener('change', readContextControlsToState);
  byId('copilot-include-projection-context').addEventListener('change', readContextControlsToState);
  byId('copilot-research-symbols').addEventListener('change', readContextControlsToState);
  byId('copilot-live-context').addEventListener('change', () => {
    state.copilotContextUpdatedAt = null;
  });

  loadConversations(true);
  refreshContextPreview().catch(e => writeLog(e.message, null, true));

  if (params.dailyReview) {
    byId('copilot-use-unified-context').checked = true;
    state.copilotUseUnifiedContext = true;
    setContextControlAvailability();
    const q = byId('copilot-question');
    q.value = 'Run my daily financial review using current context.\n1) Summarize top portfolio changes and concentration risk.\n2) Highlight the most important recommendation for today with assumptions.\n3) Suggest one workflow template I should run now.';
    q.focus();
  }
}
