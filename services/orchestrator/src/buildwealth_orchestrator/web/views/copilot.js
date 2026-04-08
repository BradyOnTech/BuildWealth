import { fetchJson } from '../lib/api.js';
import { state } from '../lib/state.js';
import { byId, fmtDate, truncate, writeLog } from '../lib/utils.js';
import { planSelectOptions } from '../lib/components.js';

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
  state.currentMessages.push({ role: 'user', content: question, created_at: new Date().toISOString(), metadata: {} });
  renderMessages();
  input.value = '';
  const selectedPlanId = byId('copilot-plan').value || null;
  state.copilotPlanId = selectedPlanId || '';
  const payload = { question, conversation_id: state.currentConversationId, use_live_snapshot: byId('copilot-live-context').checked, plan_id: selectedPlanId };
  setBusy(true);
  writeLog('Sending Copilot request...', payload);
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
  byId('reload-conversations').addEventListener('click', () => loadConversations(false).catch(e => writeLog(e.message, null, true)));
  byId('new-conversation').addEventListener('click', startNew);
  byId('copilot-form').addEventListener('submit', submit);
  byId('copilot-plan').addEventListener('change', (e) => { state.copilotPlanId = e.target.value || ''; });
  loadConversations(true);
  if (params.dailyReview) {
    const q = byId('copilot-question');
    q.value = 'Run my daily financial review using current context.\n1) Summarize top portfolio changes and concentration risk.\n2) Highlight the most important recommendation for today with assumptions.\n3) Suggest one workflow template I should run now.';
    q.focus();
  }
}
