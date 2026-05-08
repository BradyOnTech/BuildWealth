// IMPORT & SYNC.
// Three honest concerns:
//   I.   Sync — what does the orchestrator know, and how fresh is it?
//   II.  Inbox — what files have you dropped that haven't been imported yet?
//   III. Templates — the canonical CSV shapes; everything else routes to
//        classic for the deeper statement-import workflow.

import { api } from '../lib/api.js';
import { state } from '../lib/state.js';
import { html, raw, $, esc, setView, delegate } from '../lib/dom.js';
import { fmtRelative } from '../lib/format.js';

export const meta = {
  id: 'import-sync',
  label: 'Import & Sync',
  numeral: '·',
  group: 'utility',
};

const ui = {
  loaded:    false,
  loadError: null,
  syncing:   false,
  syncError: null,
  sync:      null,
  files:     [],
  templates: [],
};

export function template() {
  return html`
    <section class="page" id="import-sync-page">
      <div class="import-shell" id="import-shell">
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
    const [sync, files, templates] = await Promise.all([
      api.syncStatus(),
      api.importFiles().catch(() => ({ items: [] })),
      api.csvTemplates().catch(() => ({ templates: [] })),
    ]);
    ui.sync = sync || null;
    ui.files = Array.isArray(files?.items) ? files.items : (Array.isArray(files) ? files : []);
    ui.templates = Array.isArray(templates?.templates) ? templates.templates : (Array.isArray(templates) ? templates : []);
    ui.loaded = true;
  } catch (err) {
    ui.loadError = err.message || 'Could not load sync state.';
    state.lastError = ui.loadError;
  }
  render();
}

function render() {
  const shell = $('#import-shell');
  if (!shell) return;
  if (ui.loadError) {
    setView(shell, html`
      ${raw(masthead())}
      <p class="error-banner">${ui.loadError}</p>
    `);
    return;
  }
  if (!ui.loaded) {
    setView(shell, html`${raw(masthead())}${raw(skeletonBody())}`);
    return;
  }
  setView(shell, html`
    ${raw(masthead())}
    ${raw(syncCard())}
    ${raw(inboxCard())}
    ${raw(templatesCard())}
    ${raw(handoffCard())}
  `);
}

/* ─────────────  Composition  ───────────── */

function masthead() {
  return html`
    <header class="settings-masthead">
      <p class="settings-eyebrow">§ Data · Import &amp; sync</p>
      <h1 class="settings-title">Import &amp; sync</h1>
      <p class="settings-lede">
        Pull holdings and prices from upstream sources, drop CSVs into the inbox,
        and inspect what's queued for the next reconciliation.
      </p>
    </header>
  `;
}

function syncCard() {
  const s = ui.sync || {};
  const last = s.last_completed_at || s.last_started_at;
  const lastLabel = last ? fmtRelative(last) : 'Never';
  const status = s.running ? 'running' : (s.last_error ? 'failed' : (last ? 'ok' : 'idle'));
  const statusLabel = ({
    running: 'Running…',
    failed:  'Last sync failed',
    ok:      'Last sync succeeded',
    idle:    'No sync recorded',
  })[status];
  const tone = ({ running: 'proposed', failed: 'rejected', ok: 'applied', idle: 'archived' })[status];

  return html`
    <section class="settings-card">
      <header class="settings-card-head">
        <h2 class="settings-card-title">Sync</h2>
        <p class="settings-card-lede">
          One-tap snapshot reconciliation. Brings holdings, prices, and FX up to date
          from whatever upstream sources you have configured.
        </p>
      </header>
      <div class="settings-grid">
        ${raw(statusRow('Status', statusLabel, tone))}
        ${raw(statusRow('Last sync', lastLabel, last ? 'archived' : 'archived'))}
        ${raw(statusRow('Total runs', String(s.runs_total ?? 0), 'archived', { mono: true }))}
        ${raw(statusRow('Failed runs', String(s.runs_failed ?? 0), (s.runs_failed ?? 0) > 0 ? 'rejected' : 'archived', { mono: true }))}
      </div>

      ${s.last_error ? html`
        <div class="settings-test-block fail">
          <p class="settings-test-headline">Last error</p>
          <p class="settings-test-detail">${esc(String(s.last_error).slice(0, 240))}</p>
        </div>
      ` : ''}

      <footer class="settings-actions">
        <button class="btn btn-primary" id="import-sync-run" ${ui.syncing ? 'disabled' : ''}>
          ${ui.syncing ? 'Running…' : 'Run sync now'}
        </button>
        ${ui.syncError ? html`<p class="inline-warning">${ui.syncError}</p>` : ''}
      </footer>
    </section>
  `;
}

function inboxCard() {
  const files = ui.files || [];
  return html`
    <section class="settings-card settings-card-quiet">
      <header class="settings-card-head">
        <h2 class="settings-card-title">Inbox</h2>
        <p class="settings-card-lede">
          Files you've dropped into <code>data/imports/inbox</code>. Each one is queued
          for processing on the next reconciliation pass.
        </p>
      </header>
      ${files.length
        ? html`
          <ul class="import-file-list">
            ${raw(files.slice(0, 12).map(f => `
              <li class="import-file">
                <span class="import-file-name">${esc(f.name || f.filename || f.path || '—')}</span>
                <span class="import-file-meta">${esc(humanFileSize(f.size_bytes))} · ${esc(f.modified_at ? fmtRelative(f.modified_at) : '')}</span>
              </li>
            `).join(''))}
          </ul>
        `
        : html`<p class="profile-card-empty">No files queued. Drop a statement or CSV into the inbox to import it.</p>`}
    </section>
  `;
}

function templatesCard() {
  const templates = ui.templates || [];
  return html`
    <section class="settings-card settings-card-quiet">
      <header class="settings-card-head">
        <h2 class="settings-card-title">CSV templates</h2>
        <p class="settings-card-lede">
          Canonical shapes the orchestrator already understands. Match these column
          names and types to skip statement parsing.
        </p>
      </header>
      ${templates.length
        ? html`
          <ul class="import-template-list">
            ${raw(templates.slice(0, 8).map(t => `
              <li class="import-template">
                <span class="import-template-name">${esc(t.name || t.id || 'template')}</span>
                ${t.description ? `<span class="import-template-desc">${esc(t.description)}</span>` : ''}
                ${Array.isArray(t.columns)
                  ? `<code class="import-template-cols">${esc(t.columns.join(', '))}</code>`
                  : ''}
              </li>
            `).join(''))}
          </ul>
        `
        : html`<p class="profile-card-empty">No templates registered.</p>`}
    </section>
  `;
}

function handoffCard() {
  return html`
    <aside class="settings-handoff">
      <p class="settings-handoff-eyebrow">Need full statement parsing or upload UI?</p>
      <p class="settings-handoff-body">
        The full v1 importer with file upload, statement parsing, and apply-preview
        flows lives in <a href="/classic" class="link-editorial">Classic UI</a>.
        v2 will absorb it next; for now, this page keeps the daily controls
        (sync + inbox watch) close at hand.
      </p>
    </aside>
  `;
}

function statusRow(label, value, tone, opts = {}) {
  const valueClass = `settings-context-value${opts.mono ? ' mono' : ''}`;
  return html`
    <div class="settings-context-row settings-field span-2">
      <span class="status-pill ${tone}"><span class="dot"></span></span>
      <span class="settings-context-label">${label}</span>
      <span class="${valueClass}">${value}</span>
    </div>
  `;
}

/* ─────────────  Events  ───────────── */

function attachHandlers() {
  const root = $('#import-sync-page');
  if (!root) return;
  delegate(root, 'click', '#import-sync-run', (e) => { e.preventDefault(); runSync(); });
}

async function runSync() {
  if (ui.syncing) return;
  ui.syncing = true;
  ui.syncError = null;
  render();
  try {
    await api.triggerSync();
    // Refetch sync state — POST /api/snapshot/sync may finish synchronously
    // on a small dataset and we want the user to see the new last_completed_at.
    await load();
  } catch (err) {
    ui.syncError = err?.message || 'Sync failed.';
  } finally {
    ui.syncing = false;
    render();
  }
}

/* ─────────────  Helpers  ───────────── */

function humanFileSize(bytes) {
  const n = Number(bytes);
  if (!Number.isFinite(n) || n <= 0) return '';
  if (n < 1024) return `${n} B`;
  if (n < 1024 * 1024) return `${(n / 1024).toFixed(1)} KB`;
  if (n < 1024 * 1024 * 1024) return `${(n / 1024 / 1024).toFixed(1)} MB`;
  return `${(n / 1024 / 1024 / 1024).toFixed(1)} GB`;
}

/* ─────────────  Skeletons  ───────────── */

function skeleton() {
  return html`${raw(masthead())}${raw(skeletonBody())}`;
}

function skeletonBody() {
  return html`
    <div class="skeleton" style="height: 120px;">.</div>
    <div class="skeleton" style="height: 120px; margin-top: 12px;">.</div>
  `;
}
