const byId = (id) => document.getElementById(id);

const logEl = byId('log');

const state = {
  conversations: [],
  currentConversationId: null,
  currentMessages: [],
  copilotLoading: false,
};

function stamp() {
  return new Date().toLocaleTimeString();
}

function writeLog(message, payload = null, isError = false) {
  const lines = [`[${stamp()}] ${message}`];
  if (payload !== null) {
    lines.push(JSON.stringify(payload, null, 2));
  }

  const block = document.createElement('div');
  if (isError) block.classList.add('error');
  block.textContent = `${lines.join('\n')}\n`;

  logEl.prepend(block);
}

function fmtCurrency(value) {
  if (typeof value !== 'number' || Number.isNaN(value)) return '-';
  return new Intl.NumberFormat('en-US', { style: 'currency', currency: 'USD', maximumFractionDigits: 0 }).format(value);
}

function fmtPct(value) {
  if (typeof value !== 'number' || Number.isNaN(value)) return '-';
  return `${value.toFixed(2)}%`;
}

function fmtDate(value) {
  if (!value) return '-';
  const dateValue = new Date(value);
  if (Number.isNaN(dateValue.getTime())) return String(value);
  return dateValue.toLocaleString();
}

function truncate(value, maxLength = 120) {
  const text = String(value || '').trim();
  if (text.length <= maxLength) return text;
  return `${text.slice(0, maxLength - 3)}...`;
}

async function fetchJson(url, options = {}) {
  const response = await fetch(url, options);
  const data = await response.json().catch(() => ({}));

  if (!response.ok) {
    const detail = data.detail || data.message || response.statusText;
    throw new Error(detail);
  }

  return data;
}

function renderSyncStatus(status) {
  byId('sync-running').textContent = status.running ? 'Running' : 'Idle';
  byId('sync-runs').textContent = String(status.runs_total ?? 0);
  byId('sync-failed').textContent = String(status.runs_failed ?? 0);

  byId('meta-trigger').textContent = status.last_trigger || '-';
  byId('meta-started').textContent = fmtDate(status.last_started_at);
  byId('meta-completed').textContent = fmtDate(status.last_completed_at);
}

function renderSnapshot(snapshot) {
  byId('snapshot-total').textContent =
    `Total Value ${fmtCurrency(snapshot.total_value_usd)} | Net ${fmtCurrency(snapshot.net_performance_usd)} (${fmtPct(snapshot.net_performance_percent)})`;

  const tbody = byId('holdings-body');
  tbody.innerHTML = '';

  const top = (snapshot.holdings || []).slice(0, 12);
  for (const row of top) {
    const tr = document.createElement('tr');
    tr.innerHTML = `
      <td>${row.symbol || '-'}</td>
      <td>${row.name || '-'}</td>
      <td>${fmtCurrency(row.value_usd)}</td>
      <td>${fmtPct(row.allocation_percent)}</td>
    `;
    tbody.appendChild(tr);
  }

  if (top.length === 0) {
    const tr = document.createElement('tr');
    tr.innerHTML = '<td colspan="4">No holdings in latest snapshot.</td>';
    tbody.appendChild(tr);
  }
}

function renderInboxFiles(files) {
  const select = byId('inbox-file');
  select.innerHTML = '';

  if (!files.length) {
    const option = document.createElement('option');
    option.value = '';
    option.textContent = 'No CSV files in inbox';
    select.appendChild(option);
    return;
  }

  for (const file of files) {
    const option = document.createElement('option');
    option.value = file;
    option.textContent = file;
    select.appendChild(option);
  }
}

function renderConversationList() {
  const listEl = byId('conversation-list');
  listEl.innerHTML = '';

  if (!state.conversations.length) {
    const empty = document.createElement('p');
    empty.className = 'chat-empty';
    empty.textContent = 'No saved conversations yet.';
    listEl.appendChild(empty);
    return;
  }

  for (const conversation of state.conversations) {
    const button = document.createElement('button');
    button.type = 'button';
    button.className = 'conversation-item';
    if (conversation.id === state.currentConversationId) {
      button.classList.add('active');
    }

    const title = document.createElement('p');
    title.className = 'conversation-title';
    title.textContent = conversation.title || 'Conversation';

    const preview = document.createElement('p');
    preview.className = 'conversation-preview';
    preview.textContent = truncate(conversation.last_message_preview || 'No assistant response yet.', 88);

    const updated = document.createElement('p');
    updated.className = 'conversation-updated';
    updated.textContent = `Updated ${fmtDate(conversation.updated_at)}`;

    button.appendChild(title);
    button.appendChild(preview);
    button.appendChild(updated);
    button.addEventListener('click', () => {
      loadCopilotConversation(conversation.id).catch((error) => {
        writeLog(`Conversation load failed: ${error.message}`, null, true);
      });
    });

    listEl.appendChild(button);
  }
}

function renderToolTraces(toolCalls) {
  const wrap = document.createElement('div');
  wrap.className = 'tool-trace-list';

  for (const toolCall of toolCalls) {
    const details = document.createElement('details');
    details.className = 'tool-trace';

    const summary = document.createElement('summary');
    const status = toolCall.error ? 'error' : 'ok';
    summary.textContent = `Tool: ${toolCall.name || 'unknown'} (${status})`;

    const pre = document.createElement('pre');
    pre.textContent = JSON.stringify(toolCall, null, 2);

    details.appendChild(summary);
    details.appendChild(pre);
    wrap.appendChild(details);
  }

  return wrap;
}

function renderChatMessages() {
  const chatEl = byId('chat-messages');
  chatEl.innerHTML = '';

  if (!state.currentMessages.length) {
    const empty = document.createElement('p');
    empty.className = 'chat-empty';
    empty.textContent =
      'Start a new conversation. Copilot will use your saved snapshot, sync status, and planning defaults as context.';
    chatEl.appendChild(empty);
    return;
  }

  for (const message of state.currentMessages) {
    const role = message.role === 'user' ? 'user' : 'assistant';
    const wrapper = document.createElement('article');
    wrapper.className = `message ${role}`;

    const meta = document.createElement('p');
    meta.className = 'message-meta';
    meta.textContent = `${role === 'user' ? 'You' : 'Copilot'} • ${fmtDate(message.created_at)}`;

    const content = document.createElement('p');
    content.className = 'message-content';
    content.textContent = String(message.content || '');

    wrapper.appendChild(meta);
    wrapper.appendChild(content);

    if (role === 'assistant') {
      const toolCalls = Array.isArray(message.metadata?.tool_calls) ? message.metadata.tool_calls : [];
      if (toolCalls.length) {
        wrapper.appendChild(renderToolTraces(toolCalls));
      }
    }

    chatEl.appendChild(wrapper);
  }

  chatEl.scrollTop = chatEl.scrollHeight;
}

function setCopilotBusy(isBusy) {
  state.copilotLoading = isBusy;

  const sendButton = byId('copilot-send');
  const questionInput = byId('copilot-question');
  const newConversationButton = byId('new-conversation');

  sendButton.disabled = isBusy;
  sendButton.textContent = isBusy ? 'Thinking...' : 'Ask Copilot';
  questionInput.disabled = isBusy;
  newConversationButton.disabled = isBusy;
}

async function loadStatus() {
  const status = await fetchJson('/api/sync/status');
  renderSyncStatus(status);
}

async function loadSnapshot() {
  try {
    const snapshot = await fetchJson('/api/snapshot/latest');
    renderSnapshot(snapshot);
  } catch (error) {
    byId('snapshot-total').textContent = `Snapshot unavailable: ${error.message}`;
    byId('holdings-body').innerHTML = '<tr><td colspan="4">Run a sync to generate a snapshot.</td></tr>';
  }
}

async function loadInbox() {
  const payload = await fetchJson('/api/import/files');
  renderInboxFiles(payload.files || []);
}

async function refreshAll() {
  await Promise.all([loadStatus(), loadSnapshot(), loadInbox()]);
}

async function loadCopilotConversations(autoSelect = true) {
  const conversations = await fetchJson('/api/copilot/conversations?limit=80');
  state.conversations = Array.isArray(conversations) ? conversations : [];

  if (
    state.currentConversationId &&
    !state.conversations.some((conversation) => conversation.id === state.currentConversationId)
  ) {
    state.currentConversationId = null;
    state.currentMessages = [];
  }

  if (autoSelect && !state.currentConversationId && state.conversations.length) {
    state.currentConversationId = state.conversations[0].id;
  }

  renderConversationList();

  if (state.currentConversationId) {
    await loadCopilotConversation(state.currentConversationId);
  } else {
    renderChatMessages();
  }
}

async function loadCopilotConversation(conversationId) {
  if (!conversationId) return;
  const payload = await fetchJson(`/api/copilot/conversations/${encodeURIComponent(conversationId)}`);
  state.currentConversationId = payload.id;
  state.currentMessages = Array.isArray(payload.messages) ? payload.messages : [];

  renderConversationList();
  renderChatMessages();
}

function startNewConversation() {
  state.currentConversationId = null;
  state.currentMessages = [];
  renderConversationList();
  renderChatMessages();
  byId('copilot-question').focus();
}

async function runSync() {
  writeLog('Running manual sync...');
  try {
    const result = await fetchJson('/api/snapshot/sync', { method: 'POST' });
    writeLog('Sync completed.', result);
    await refreshAll();
  } catch (error) {
    writeLog(`Sync failed: ${error.message}`, null, true);
  }
}

async function importInboxFile() {
  const file = byId('inbox-file').value;
  if (!file) {
    writeLog('Select a CSV file from inbox first.', null, true);
    return;
  }

  const body = {
    path: file,
    dry_run: byId('inbox-dry-run').checked,
    archive_after_success: byId('inbox-archive').checked,
  };

  writeLog(`Importing inbox file ${file}...`, body);
  try {
    const result = await fetchJson('/api/import/csv', {
      method: 'POST',
      headers: { 'content-type': 'application/json' },
      body: JSON.stringify(body),
    });
    writeLog('Inbox import completed.', result);
    await refreshAll();
  } catch (error) {
    writeLog(`Inbox import failed: ${error.message}`, null, true);
  }
}

async function uploadAndImport(event) {
  event.preventDefault();
  const fileInput = byId('upload-file');
  const file = fileInput.files?.[0];

  if (!file) {
    writeLog('Choose a CSV file to upload.', null, true);
    return;
  }

  const formData = new FormData();
  formData.append('file', file);
  formData.append('dry_run', String(byId('upload-dry-run').checked));
  formData.append('archive_after_success', String(byId('upload-archive').checked));
  formData.append('delimiter', byId('upload-delimiter').value || ',');
  formData.append('default_data_source', byId('upload-source').value || 'YAHOO');
  formData.append('default_currency', byId('upload-currency').value || 'USD');

  writeLog(`Uploading and importing ${file.name}...`);
  try {
    const result = await fetchJson('/api/import/upload-csv', {
      method: 'POST',
      body: formData,
    });
    writeLog('Upload import completed.', result);
    fileInput.value = '';
    await refreshAll();
  } catch (error) {
    writeLog(`Upload import failed: ${error.message}`, null, true);
  }
}

async function submitCopilotQuestion(event) {
  event.preventDefault();
  if (state.copilotLoading) return;

  const questionInput = byId('copilot-question');
  const question = questionInput.value.trim();
  if (!question) return;

  const localCreatedAt = new Date().toISOString();
  state.currentMessages.push({
    role: 'user',
    content: question,
    created_at: localCreatedAt,
    metadata: {},
  });
  renderChatMessages();
  questionInput.value = '';

  const payload = {
    question,
    conversation_id: state.currentConversationId,
    use_live_snapshot: byId('copilot-live-context').checked,
  };

  setCopilotBusy(true);
  writeLog('Sending Copilot request...', payload);

  try {
    const result = await fetchJson('/api/copilot/chat', {
      method: 'POST',
      headers: { 'content-type': 'application/json' },
      body: JSON.stringify(payload),
    });

    state.currentConversationId = result.conversation_id;
    state.currentMessages.push({
      role: 'assistant',
      content: result.answer || '',
      created_at: result.created_at || new Date().toISOString(),
      metadata: {
        tool_calls: Array.isArray(result.tool_calls) ? result.tool_calls : [],
        model: result.model || null,
      },
    });
    renderChatMessages();

    writeLog('Copilot response received.', {
      conversation_id: result.conversation_id,
      tool_calls: Array.isArray(result.tool_calls) ? result.tool_calls.length : 0,
      model: result.model || null,
    });

    await loadCopilotConversations(false);
    await loadCopilotConversation(state.currentConversationId);
  } catch (error) {
    state.currentMessages.push({
      role: 'assistant',
      content: `Copilot request failed: ${error.message}`,
      created_at: new Date().toISOString(),
      metadata: {},
    });
    renderChatMessages();
    writeLog(`Copilot request failed: ${error.message}`, null, true);
  } finally {
    setCopilotBusy(false);
  }
}

function wireEvents() {
  byId('refresh-all').addEventListener('click', () => {
    refreshAll().catch((error) => writeLog(error.message, null, true));
  });
  byId('run-sync').addEventListener('click', runSync);
  byId('reload-inbox').addEventListener('click', () => {
    loadInbox().catch((error) => writeLog(error.message, null, true));
  });
  byId('reload-snapshot').addEventListener('click', () => {
    loadSnapshot().catch((error) => writeLog(error.message, null, true));
  });
  byId('import-inbox').addEventListener('click', importInboxFile);
  byId('upload-form').addEventListener('submit', uploadAndImport);
  byId('clear-log').addEventListener('click', () => {
    logEl.innerHTML = '';
  });

  byId('reload-conversations').addEventListener('click', () => {
    loadCopilotConversations(false).catch((error) => writeLog(error.message, null, true));
  });
  byId('new-conversation').addEventListener('click', startNewConversation);
  byId('copilot-form').addEventListener('submit', submitCopilotQuestion);
}

async function boot() {
  wireEvents();
  renderChatMessages();
  await Promise.all([refreshAll(), loadCopilotConversations(true)]);
  writeLog('BuildWealth UI ready with Copilot chat.');
}

boot().catch((error) => {
  writeLog(`Initialization failed: ${error.message}`, null, true);
});
