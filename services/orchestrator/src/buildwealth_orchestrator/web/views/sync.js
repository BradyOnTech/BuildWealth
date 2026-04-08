import { fetchJson } from '../lib/api.js';
import { byId, fmtDate, writeLog } from '../lib/utils.js';

export const id = 'sync';
export const label = 'Sync & Import';
export const icon = '<svg viewBox="0 0 20 20" fill="none" stroke="currentColor" stroke-width="1.6"><path d="M14 3l3 3-3 3"/><path d="M6 17l-3-3 3-3"/><path d="M17 6H8a4 4 0 00-4 4"/><path d="M3 14h9a4 4 0 004-4"/></svg>';

export function template() {
  return `
    <div class="view-header"><h2>Sync & Import</h2><button class="ghost small" id="refresh-all">Refresh</button></div>
    <div class="stat-row">
      <article class="kpi-card"><p class="kpi-label">Sync State</p><p class="kpi-value" id="sync-running">Unknown</p></article>
      <article class="kpi-card"><p class="kpi-label">Total Runs</p><p class="kpi-value" id="sync-runs">0</p></article>
      <article class="kpi-card"><p class="kpi-label">Failed Runs</p><p class="kpi-value" id="sync-failed">0</p></article>
    </div>
    <div class="two-col">
      <section class="card">
        <h3 class="section-title">Portfolio Sync</h3>
        <p class="hint">Pull latest holdings/performance from Ghostfolio and regenerate planning payloads.</p>
        <button class="primary" id="run-sync">Run Sync Now</button>
        <dl class="meta" id="sync-meta">
          <div><dt>Last Trigger</dt><dd id="meta-trigger">-</dd></div>
          <div><dt>Last Started</dt><dd id="meta-started">-</dd></div>
          <div><dt>Last Completed</dt><dd id="meta-completed">-</dd></div>
        </dl>
      </section>
      <section class="card">
        <h3 class="section-title">Inbox Import</h3>
        <p class="hint">Import a CSV already in <code>data/imports/inbox</code>.</p>
        <label class="field"><span>CSV File</span><select id="inbox-file"></select></label>
        <div class="inline-options">
          <label><input type="checkbox" id="inbox-dry-run" checked /> Dry run</label>
          <label><input type="checkbox" id="inbox-archive" /> Archive after success</label>
        </div>
        <button class="primary" id="import-inbox">Import File</button>
      </section>
    </div>
    <section class="card">
      <h3 class="section-title">Upload CSV</h3>
      <p class="hint">Upload directly from your machine and import immediately.</p>
      <form id="upload-form">
        <div class="four-col compact">
          <label class="field file-field"><span>CSV</span><input type="file" id="upload-file" accept=".csv,text/csv" required /></label>
          <label class="field"><span>Delimiter</span><input type="text" id="upload-delimiter" value="," maxlength="1" /></label>
          <label class="field"><span>Data Source</span><input type="text" id="upload-source" value="YAHOO" /></label>
          <label class="field"><span>Currency</span><input type="text" id="upload-currency" value="USD" /></label>
        </div>
        <div class="inline-options">
          <label><input type="checkbox" id="upload-dry-run" checked /> Dry run</label>
          <label><input type="checkbox" id="upload-archive" /> Archive after success</label>
        </div>
        <button class="primary" type="submit">Upload & Import</button>
      </form>
    </section>`;
}

function renderSyncStatus(status) {
  byId('sync-running').textContent = status.running ? 'Running' : 'Idle';
  byId('sync-runs').textContent = String(status.runs_total ?? 0);
  byId('sync-failed').textContent = String(status.runs_failed ?? 0);
  byId('meta-trigger').textContent = status.last_trigger || '-';
  byId('meta-started').textContent = fmtDate(status.last_started_at);
  byId('meta-completed').textContent = fmtDate(status.last_completed_at);
}

function renderInboxFiles(files) {
  const select = byId('inbox-file');
  select.innerHTML = '';
  if (!files.length) { select.innerHTML = '<option value="">No CSV files in inbox</option>'; return; }
  for (const f of files) { const o = document.createElement('option'); o.value = f; o.textContent = f; select.appendChild(o); }
}

async function loadAll() {
  try { renderSyncStatus(await fetchJson('/api/sync/status')); } catch (e) { writeLog(e.message, null, true); }
  try { const p = await fetchJson('/api/import/files'); renderInboxFiles(p.files || []); } catch (e) { writeLog(e.message, null, true); }
}

async function runSync() {
  writeLog('Running manual sync...');
  try {
    const result = await fetchJson('/api/snapshot/sync', { method: 'POST' });
    writeLog('Sync completed.', result);
    await loadAll();
  } catch (e) { writeLog(`Sync failed: ${e.message}`, null, true); }
}

async function importInboxFile() {
  const file = byId('inbox-file').value;
  if (!file) { writeLog('Select a CSV file from inbox first.', null, true); return; }
  const body = { path: file, dry_run: byId('inbox-dry-run').checked, archive_after_success: byId('inbox-archive').checked };
  writeLog(`Importing ${file}...`, body);
  try {
    const result = await fetchJson('/api/import/csv', { method: 'POST', headers: { 'content-type': 'application/json' }, body: JSON.stringify(body) });
    writeLog('Import completed.', result);
    await loadAll();
  } catch (e) { writeLog(`Import failed: ${e.message}`, null, true); }
}

async function uploadAndImport(event) {
  event.preventDefault();
  const fileInput = byId('upload-file');
  const file = fileInput.files?.[0];
  if (!file) { writeLog('Choose a CSV file.', null, true); return; }
  const fd = new FormData();
  fd.append('file', file);
  fd.append('dry_run', String(byId('upload-dry-run').checked));
  fd.append('archive_after_success', String(byId('upload-archive').checked));
  fd.append('delimiter', byId('upload-delimiter').value || ',');
  fd.append('default_data_source', byId('upload-source').value || 'YAHOO');
  fd.append('default_currency', byId('upload-currency').value || 'USD');
  writeLog(`Uploading ${file.name}...`);
  try {
    const result = await fetchJson('/api/import/upload-csv', { method: 'POST', body: fd });
    writeLog('Upload import completed.', result);
    fileInput.value = '';
    await loadAll();
  } catch (e) { writeLog(`Upload failed: ${e.message}`, null, true); }
}

export function init() {
  byId('refresh-all').addEventListener('click', () => loadAll().catch(e => writeLog(e.message, null, true)));
  byId('run-sync').addEventListener('click', runSync);
  byId('import-inbox').addEventListener('click', importInboxFile);
  byId('upload-form').addEventListener('submit', uploadAndImport);
  loadAll();
}
