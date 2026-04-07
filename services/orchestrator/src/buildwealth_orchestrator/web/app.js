const byId = (id) => document.getElementById(id);

const logEl = byId('log');

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
  const d = new Date(value);
  if (Number.isNaN(d.getTime())) return String(value);
  return d.toLocaleString();
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

function wireEvents() {
  byId('refresh-all').addEventListener('click', () => refreshAll().catch((e) => writeLog(e.message, null, true)));
  byId('run-sync').addEventListener('click', runSync);
  byId('reload-inbox').addEventListener('click', () => loadInbox().catch((e) => writeLog(e.message, null, true)));
  byId('reload-snapshot').addEventListener('click', () => loadSnapshot().catch((e) => writeLog(e.message, null, true)));
  byId('import-inbox').addEventListener('click', importInboxFile);
  byId('upload-form').addEventListener('submit', uploadAndImport);
  byId('clear-log').addEventListener('click', () => {
    logEl.innerHTML = '';
  });
}

async function boot() {
  wireEvents();
  await refreshAll();
  writeLog('BuildWealth UI ready.');
}

boot().catch((error) => {
  writeLog(`Initialization failed: ${error.message}`, null, true);
});
