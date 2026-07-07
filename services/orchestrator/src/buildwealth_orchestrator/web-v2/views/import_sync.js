// IMPORT & REVIEW.
// Bring raw statement data into BuildWealth, review what was understood,
// then apply the clean rows to Portfolio with an import report for evidence.

import { api } from '../lib/api.js';
import { state } from '../lib/state.js';
import { html, raw, $, esc, setView, delegate } from '../lib/dom.js';
import { fmtRelative } from '../lib/format.js';
import { renderBudgetReaderCard, bindBudgetReader } from './import_sync/budget_reader.js';

export const meta = {
  id: 'import-sync',
  label: 'Import & Review',
  numeral: '·',
  group: 'utility',
};

const ui = {
  loaded:       false,
  loadError:    null,
  previewing:   false,
  applying:     false,
  previewError: null,
  applyError:   null,
  syncError:    null,
  syncing:      false,
  sync:         null,
  files:        [],
  templates:    [],
  reports:      [],
  preview:      null,
  applyResult:  null,
  selectedReport: null,
  reportLoading:  false,
  reportError:    null,
  focusReportId:  null,
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

export async function init(params = {}) {
  ui.focusReportId = String(params.report || '').trim() || null;
  attachHandlers();
  await load();
  if (ui.focusReportId) await openReport(ui.focusReportId);
}

async function load() {
  ui.loaded = false;
  ui.loadError = null;
  try {
    const [sync, files, templates, reports] = await Promise.all([
      api.syncStatus(),
      api.importFiles().catch(() => ({ items: [] })),
      api.csvTemplates().catch(() => ({ templates: [] })),
      api.importReports(12).catch(() => ({ reports: [] })),
    ]);
    ui.sync = sync || null;
    ui.files = Array.isArray(files?.items) ? files.items : (Array.isArray(files) ? files : []);
    ui.templates = Array.isArray(templates?.templates) ? templates.templates : (Array.isArray(templates) ? templates : []);
    ui.reports = Array.isArray(reports?.reports) ? reports.reports : [];
    ui.loaded = true;
  } catch (err) {
    ui.loadError = err.message || 'Could not load import state.';
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
    ${raw(workbenchCard())}
    ${raw(renderBudgetReaderCard())}
    ${raw(reportsCard())}
    ${raw(syncCard())}
    <div class="import-secondary-grid">
      ${raw(inboxCard())}
      ${raw(templatesCard())}
    </div>
  `);
}

/* ─────────────  Composition  ───────────── */

function masthead() {
  return html`
    <header class="settings-masthead">
      <p class="settings-eyebrow">§ Data · Import &amp; Review</p>
      <h1 class="settings-title">Import &amp; Review</h1>
      <p class="settings-lede">
        Upload a statement or CSV, review what BuildWealth understood, then apply
        only the rows that are ready for your portfolio history.
      </p>
    </header>
  `;
}

function workbenchCard() {
  return html`
    <section class="settings-card import-workbench-card">
      <header class="settings-card-head">
        <h2 class="settings-card-title">Import workbench</h2>
        <p class="settings-card-lede">
          Start with a preview. BuildWealth separates clean rows, duplicates,
          account review items, and unresolved rows before anything changes.
        </p>
      </header>

      <form class="import-workbench-form" id="import-workbench-form">
        <label class="settings-field span-2">
          <span class="settings-label">Statement or CSV file</span>
          <input class="settings-input" type="file" name="file" accept=".csv,text/csv" required />
          <span class="settings-hint">The preview copies the file into the local import inbox and leaves Portfolio unchanged.</span>
        </label>
        <label class="settings-field">
          <span class="settings-label">Template</span>
          <select class="settings-input" name="broker_template">
            <option value="auto">Auto-detect</option>
            ${raw((ui.templates || []).map(t => `
              <option value="${esc(t.id || t.name || '')}">${esc(t.name || t.id || 'Template')}</option>
            `).join(''))}
          </select>
        </label>
        <label class="settings-field">
          <span class="settings-label">Delimiter</span>
          <input class="settings-input mono" type="text" name="delimiter" value="," maxlength="4" />
        </label>
        <label class="settings-field">
          <span class="settings-label">Default source</span>
          <input class="settings-input mono" type="text" name="default_data_source" value="YAHOO" placeholder="YAHOO" />
        </label>
        <label class="settings-field">
          <span class="settings-label">Default currency</span>
          <input class="settings-input mono" type="text" name="default_currency" value="USD" placeholder="USD" maxlength="8" />
        </label>
        <footer class="settings-actions span-2">
          <button class="btn btn-primary" type="submit" ${ui.previewing ? 'disabled' : ''}>
            ${ui.previewing ? 'Previewing...' : 'Preview import'}
          </button>
          ${ui.previewError ? html`<p class="inline-warning">${ui.previewError}</p>` : ''}
        </footer>
      </form>

      ${ui.preview ? raw(previewPanel(ui.preview)) : raw(emptyPreview())}
    </section>
  `;
}

function emptyPreview() {
  return html`
    <div class="import-preview-empty">
      <p class="profile-card-empty">Preview results will appear here before any rows are applied.</p>
    </div>
  `;
}

function previewPanel(preview) {
  const summary = preview.summary || {};
  const response = preview.preview_response || {};
  const report = response.reconciliation_report || {};
  const canApply = Number(summary.accepted_count || 0) > 0 && preview.status !== 'applied';

  return html`
    <div class="import-preview-panel">
      <div class="import-preview-head">
        <div>
          <p class="settings-eyebrow">Preview ready</p>
          <h3 class="import-preview-title">${esc(preview.source_file?.name || 'Uploaded file')}</h3>
          <p class="settings-card-lede">
            Parser confidence is ${esc(confidenceLabel(summary.parser_confidence_flag))}
            (${esc(confidencePercent(summary.parser_confidence_score))}).
            Template: ${esc(templateLabel(response.selected_template, response.detected_template))}.
            Review unresolved rows before relying on the import.
          </p>
        </div>
        <span class="status-pill ${toneForConfidence(summary.parser_confidence_flag)}">
          <span class="dot"></span>${esc(confidenceLabel(summary.parser_confidence_flag))}
        </span>
      </div>

      <div class="import-metric-grid">
        ${raw(metricTile('Parsed', summary.parsed_rows))}
        ${raw(metricTile('Ready', summary.accepted_count, 'applied'))}
        ${raw(metricTile('Changed while reading', summary.normalized_count, summary.normalized_count ? 'proposed' : 'archived'))}
        ${raw(metricTile('Duplicates', summary.duplicate_count, summary.duplicate_count ? 'archived' : 'applied'))}
        ${raw(metricTile('Need review', summary.unresolved_count, summary.unresolved_count ? 'rejected' : 'applied'))}
        ${raw(metricTile('Asset review', summary.asset_review_count, summary.asset_review_count ? 'rejected' : 'applied'))}
        ${raw(metricTile('Account review', summary.account_review_count, summary.account_review_count ? 'proposed' : 'applied'))}
      </div>

      ${raw(messageList('Warnings', response.warnings || []))}
      ${raw(messageList('Errors', response.errors || []))}
      ${raw(previewReviewRoutes(preview))}
      ${raw(rowTable('Rows ready to apply', report.accepted_rows || [], 'No rows are ready yet.'))}
      ${raw(rowTable('Rows BuildWealth adjusted', report.normalized_rows || [], 'No rows needed normalization.'))}
      ${raw(rowTable('Rows that need review', report.rejected_rows || [], 'No unresolved rows found.'))}

      <footer class="settings-actions">
        <label class="settings-field-toggle import-apply-option">
          <input type="checkbox" id="import-archive-after-success" />
          <span>
            <span class="settings-label">Archive source file after apply</span>
            <span class="settings-hint">Keeps the inbox focused after a successful import.</span>
          </span>
        </label>
        <button class="btn btn-primary" id="import-workbench-apply" type="button" ${!canApply || ui.applying ? 'disabled' : ''}>
          ${ui.applying ? 'Applying...' : 'Apply ready rows'}
        </button>
        ${ui.applyError ? html`<p class="inline-warning">${ui.applyError}</p>` : ''}
      </footer>
      ${ui.applyResult ? raw(applyResultPanel(ui.applyResult)) : ''}
    </div>
  `;
}

function applyResultPanel(result) {
  const report = result.report || {};
  const summary = report.summary || {};
  const reviewItemCount = Array.isArray(report.review_items) ? report.review_items.length : 0;
  return html`
    <div class="settings-test-block pass import-apply-result">
      <p class="settings-test-headline">Import applied</p>
      <p class="settings-test-detail">
        ${Number(report.imported_activities || 0).toLocaleString('en-US')} portfolio activities were created.
        The import report is saved as source evidence${reviewItemCount ? `, with ${reviewItemCount} review item${reviewItemCount === 1 ? '' : 's'} sent to Inbox` : ''}.
      </p>
      <div class="import-report-mini">
        ${raw(metricTile('Ready rows', summary.accepted_count, 'applied'))}
        ${raw(metricTile('Need review', summary.unresolved_count, summary.unresolved_count ? 'rejected' : 'applied'))}
        ${raw(metricTile('Inbox review', reviewItemCount, reviewItemCount ? 'proposed' : 'applied'))}
        ${raw(metricTile('Report', report.report_id || 'Saved', 'archived'))}
      </div>
      ${report?.affected_links?.import_report ? html`
        <a class="link-editorial" href="${esc(report.affected_links.import_report)}">Open saved import report</a>
      ` : ''}
    </div>
  `;
}

function reportsCard() {
  const reports = ui.reports || [];
  return html`
    <section class="settings-card settings-card-quiet">
      <header class="settings-card-head">
        <h2 class="settings-card-title">Import reports</h2>
        <p class="settings-card-lede">
          A durable record of what was imported, what was skipped, and what still
          needs review. Reports support audit without becoming portfolio truth.
        </p>
      </header>
      ${reports.length
        ? html`
          <ul class="import-report-list">
            ${raw(reports.slice(0, 12).map(reportListItem).join(''))}
          </ul>
        `
        : html`<p class="profile-card-empty">No import reports yet.</p>`}
      ${ui.reportLoading ? html`<p class="profile-card-empty">Loading report...</p>` : ''}
      ${ui.reportError ? html`<p class="inline-warning">${ui.reportError}</p>` : ''}
      ${ui.selectedReport ? raw(reportDetailPanel(ui.selectedReport)) : ''}
    </section>
  `;
}

function reportListItem(report) {
  const summary = report.summary || {};
  const name = report.source_file?.name || report.report_id || 'Import report';
  const created = report.created_at ? fmtRelative(report.created_at) : '';
  return html`
    <li class="import-report-item">
      <span class="import-report-name">${esc(name)}</span>
      <span class="import-report-meta">
        ${Number(report.imported_activities || 0).toLocaleString('en-US')} applied
        · ${Number(summary.unresolved_count || 0).toLocaleString('en-US')} need review
        ${created ? ` · ${esc(created)}` : ''}
      </span>
      <code>${esc(report.report_id || '')}</code>
      <a class="action-link muted" href="#import-sync?report=${encodeURIComponent(report.report_id || '')}">
        Open report
      </a>
    </li>
  `;
}

function reportDetailPanel(report) {
  const summary = report.summary || {};
  const reconciliation = report.reconciliation_report || {};
  const sourceName = report.source_file?.name || 'Import report';
  const reviewItemCount = Array.isArray(report.review_items) ? report.review_items.length : 0;
  return html`
    <article class="import-report-detail">
      <header class="import-preview-head">
        <div>
          <p class="settings-eyebrow">Source evidence</p>
          <h3 class="import-preview-title">${esc(sourceName)}</h3>
          <p class="settings-card-lede">
            Applied ${Number(report.imported_activities || 0).toLocaleString('en-US')} activities.
            Kept ${Number(summary.unresolved_count || 0).toLocaleString('en-US')} rows visible for review.
            Template: ${esc(templateLabel(report.selected_template, report.detected_template))}.
          </p>
        </div>
        <button class="btn btn-quiet" type="button" id="import-report-close">Close</button>
      </header>
      <div class="import-metric-grid">
        ${raw(metricTile('Applied', report.imported_activities, 'applied'))}
        ${raw(metricTile('Ready rows', summary.accepted_count, 'applied'))}
        ${raw(metricTile('Duplicates', summary.duplicate_count, summary.duplicate_count ? 'archived' : 'applied'))}
        ${raw(metricTile('Need review', summary.unresolved_count, summary.unresolved_count ? 'rejected' : 'applied'))}
        ${raw(metricTile('Account review', summary.account_review_count, summary.account_review_count ? 'proposed' : 'applied'))}
        ${raw(metricTile('Inbox review', reviewItemCount, reviewItemCount ? 'proposed' : 'applied'))}
        ${raw(metricTile('Confidence', confidenceLabel(summary.parser_confidence_flag), toneForConfidence(summary.parser_confidence_flag)))}
        ${raw(metricTile('Confidence score', confidencePercent(summary.parser_confidence_score), toneForConfidence(summary.parser_confidence_flag)))}
      </div>
      ${raw(messageList('Warnings', report.warnings || []))}
      ${raw(messageList('Errors', report.errors || []))}
      ${raw(reviewItemsList(report.review_items || []))}
      ${raw(rowTable('Applied rows', reconciliation.accepted_rows || [], 'No applied rows in this report.'))}
      ${raw(rowTable('Rows that need review', reconciliation.rejected_rows || [], 'No unresolved rows in this report.'))}
      ${raw(reportLinks(report.affected_links || {}))}
    </article>
  `;
}

function reviewItemsList(items) {
  const rows = Array.isArray(items) ? items.slice(0, 8) : [];
  if (!rows.length) return '';
  return html`
    <section class="import-row-section">
      <div class="import-row-section-head">
        <h4>Sent to Inbox</h4>
        <span>${rows.length.toLocaleString('en-US')}</span>
      </div>
      <div class="import-review-item-list">
        ${raw(rows.map(item => `
          <article class="import-review-item">
            <span class="status-pill proposed"><span class="dot"></span>Review</span>
            <strong>${esc(item.title || 'Import review item')}</strong>
            <p>${esc(item.detail || '')}</p>
            ${reviewItemHref(item) ? `<a class="action-link muted" href="${esc(reviewItemHref(item))}">${esc(reviewItemLabel(item))}</a>` : ''}
          </article>
        `).join(''))}
      </div>
    </section>
  `;
}

function previewReviewRoutes(preview) {
  const items = Array.isArray(preview?.review_items) ? preview.review_items : [];
  if (!items.length) return '';
  return html`
    <section class="import-row-section import-review-before-apply">
      <div class="import-row-section-head">
        <h4>Resolve before apply</h4>
        <span>${items.length.toLocaleString('en-US')}</span>
      </div>
      <p class="settings-card-lede">
        BuildWealth keeps these rows out of Portfolio History until the investment or account is clear.
      </p>
      <div class="import-review-item-list">
        ${raw(items.slice(0, 8).map(item => `
          <article class="import-review-item">
            <span class="status-pill ${reviewItemTone(item)}"><span class="dot"></span>${esc(reviewItemKindLabel(item))}</span>
            <strong>${esc(item.title || 'Import row needs review')}</strong>
            <p>${esc(item.detail || '')}</p>
            ${reviewItemHref(item) ? `<a class="action-link muted" href="${esc(reviewItemHref(item))}">${esc(reviewItemLabel(item))}</a>` : ''}
          </article>
        `).join(''))}
      </div>
    </section>
  `;
}

function reportLinks(links) {
  const entries = Object.entries(links || {}).filter(([, href]) => href);
  if (!entries.length) return '';
  return html`
    <div class="import-report-links">
      ${raw(entries.map(([label, href]) => `
        <a class="link-editorial" href="${esc(href)}">${esc(humanText(label))}</a>
      `).join(''))}
    </div>
  `;
}

function syncCard() {
  const s = ui.sync || {};
  const last = s.last_completed_at || s.last_started_at;
  const lastLabel = last ? fmtRelative(last) : 'Never';
  const status = s.running ? 'running' : (s.last_error ? 'failed' : (last ? 'ok' : 'idle'));
  const statusLabel = ({
    running: 'Running...',
    failed:  'Last sync failed',
    ok:      'Last sync succeeded',
    idle:    'No sync recorded',
  })[status];
  const tone = ({ running: 'proposed', failed: 'rejected', ok: 'applied', idle: 'archived' })[status];

  return html`
    <section class="settings-card settings-card-quiet">
      <header class="settings-card-head">
        <h2 class="settings-card-title">Sync</h2>
        <p class="settings-card-lede">
          Refresh holdings, prices, and FX after imports or manual portfolio edits.
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
          ${ui.syncing ? 'Running...' : 'Run sync now'}
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
          Files currently staged in <code>data/imports/inbox</code>.
        </p>
      </header>
      ${files.length
        ? html`
          <ul class="import-file-list">
            ${raw(files.slice(0, 12).map(f => `
              <li class="import-file">
                <span class="import-file-name">${esc(f.name || f.filename || f.path || '-')}</span>
                <span class="import-file-meta">${esc(humanFileSize(f.size_bytes))} · ${esc(f.modified_at ? fmtRelative(f.modified_at) : '')}</span>
              </li>
            `).join(''))}
          </ul>
        `
        : html`<p class="profile-card-empty">No files queued.</p>`}
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
          Known column shapes BuildWealth can read directly.
        </p>
      </header>
      ${templates.length
        ? html`
          <ul class="import-template-list">
            ${raw(templates.slice(0, 8).map(t => `
              <li class="import-template">
                <span class="import-template-name">${esc(t.name || t.id || 'template')}</span>
                ${t.description ? `<span class="import-template-desc">${esc(t.description)}</span>` : ''}
                <span class="status-pill archived"><span class="dot"></span>Mapping confidence: ${esc(templateConfidenceLabel(t.mapping_confidence))}</span>
                ${Array.isArray(t.required_columns) && t.required_columns.length
                  ? `<code class="import-template-cols">Needs ${esc(t.required_columns.join(', '))}</code>`
                  : ''}
                ${Array.isArray(t.optional_columns) && t.optional_columns.length
                  ? `<code class="import-template-cols">Can use ${esc(t.optional_columns.slice(0, 5).join(', '))}</code>`
                  : ''}
              </li>
            `).join(''))}
          </ul>
        `
        : html`<p class="profile-card-empty">No templates registered.</p>`}
    </section>
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

function metricTile(label, value, tone = 'archived') {
  const display = typeof value === 'number' ? value.toLocaleString('en-US') : String(value ?? '-');
  return html`
    <div class="import-metric-tile">
      <span class="status-pill ${tone}"><span class="dot"></span></span>
      <span class="import-metric-label">${esc(label)}</span>
      <strong>${esc(display)}</strong>
    </div>
  `;
}

function messageList(title, messages) {
  const items = Array.isArray(messages) ? messages.filter(Boolean).slice(0, 8) : [];
  if (!items.length) return '';
  return html`
    <div class="import-message-list">
      <p class="settings-label">${esc(title)}</p>
      <ul>
        ${raw(items.map(item => `<li>${esc(item)}</li>`).join(''))}
      </ul>
    </div>
  `;
}

function rowTable(title, rows, emptyText) {
  const items = Array.isArray(rows) ? rows.slice(0, 8) : [];
  return html`
    <section class="import-row-section">
      <div class="import-row-section-head">
        <h4>${esc(title)}</h4>
        <span>${Number(Array.isArray(rows) ? rows.length : 0).toLocaleString('en-US')}</span>
      </div>
      ${items.length
        ? html`
          <div class="import-row-table" role="table">
            ${raw(items.map(renderImportRow).join(''))}
          </div>
        `
        : html`<p class="profile-card-empty">${emptyText}</p>`}
    </section>
  `;
}

function renderImportRow(row) {
  const normalized = row.normalized_row || {};
  const reasons = [
    ...(Array.isArray(row.rejection_reasons) ? row.rejection_reasons : []),
    ...(Array.isArray(row.normalization_flags) ? row.normalization_flags : []),
  ];
  const rowSummary = [
    normalized.date,
    normalized.action,
    normalized.symbol,
    normalized.quantity ? `qty ${normalized.quantity}` : '',
    normalized.unit_price ? `price ${normalized.unit_price}` : '',
    normalized.account_name ? `acct ${normalized.account_name}` : '',
  ].filter(Boolean).join(' · ');
  return html`
    <article class="import-row">
      <span class="import-row-number">Row ${esc(row.row_number || '-')}</span>
      <span class="status-pill ${toneForConfidence(row.confidence_flag)}">
        <span class="dot"></span>${esc(confidenceLabel(row.confidence_flag))}
      </span>
      <span class="import-row-summary">${esc(rowSummary || compactObject(row.raw_row || {}))}</span>
      <span class="import-row-reasons">${esc(reasons.length ? reasons.map(humanText).join(', ') : 'Ready')}</span>
    </article>
  `;
}

/* ─────────────  Events  ───────────── */

function attachHandlers() {
  const root = $('#import-sync-page');
  if (!root) return;
  bindBudgetReader(root, render);
  delegate(root, 'click', '#import-sync-run', (e) => { e.preventDefault(); runSync(); });
  delegate(root, 'click', '#import-workbench-apply', (e) => { e.preventDefault(); applyPreview(); });
  delegate(root, 'click', '[data-import-report-id]', (e, target) => {
    e.preventDefault();
    openReport(target.getAttribute('data-import-report-id'));
  });
  delegate(root, 'click', '#import-report-close', (e) => {
    e.preventDefault();
    ui.selectedReport = null;
    ui.reportError = null;
    render();
  });
  root.addEventListener('submit', (e) => {
    const form = e.target.closest('#import-workbench-form');
    if (!form) return;
    e.preventDefault();
    previewImport(form);
  });
}

async function openReport(reportId) {
  const id = String(reportId || '').trim();
  if (!id) return;
  ui.reportLoading = true;
  ui.reportError = null;
  render();
  try {
    ui.selectedReport = await api.importReport(id);
  } catch (err) {
    ui.reportError = err?.message || 'Could not load this import report.';
  } finally {
    ui.reportLoading = false;
    render();
  }
}

async function previewImport(form) {
  if (ui.previewing) return;
  const file = form.querySelector('input[name="file"]')?.files?.[0];
  if (!file) {
    ui.previewError = 'Choose a CSV file before previewing.';
    render();
    return;
  }

  const formData = new FormData();
  formData.set('file', file);
  for (const name of ['delimiter', 'broker_template', 'default_data_source', 'default_currency']) {
    const value = String(form.elements[name]?.value || '').trim();
    if (value) formData.set(name, value);
  }

  ui.previewing = true;
  ui.previewError = null;
  ui.applyError = null;
  ui.applyResult = null;
  render();
  try {
    ui.preview = await api.importWorkbenchPreview(formData);
    await refreshReports();
  } catch (err) {
    ui.previewError = err?.message || 'Import preview failed.';
  } finally {
    ui.previewing = false;
    render();
  }
}

async function applyPreview() {
  const sessionId = ui.preview?.session_id;
  if (!sessionId || ui.applying) return;
  ui.applying = true;
  ui.applyError = null;
  render();
  try {
    const archiveAfterSuccess = Boolean($('#import-archive-after-success')?.checked);
    ui.applyResult = await api.applyImportWorkbench(sessionId, {
      archive_after_success: archiveAfterSuccess,
      operator: 'user',
    });
    ui.preview = ui.applyResult.session || ui.preview;
    await refreshReports();
  } catch (err) {
    ui.applyError = err?.message || 'Could not apply this import.';
  } finally {
    ui.applying = false;
    render();
  }
}

async function runSync() {
  if (ui.syncing) return;
  ui.syncing = true;
  ui.syncError = null;
  render();
  try {
    await api.triggerSync();
    await load();
  } catch (err) {
    ui.syncError = err?.message || 'Sync failed.';
  } finally {
    ui.syncing = false;
    render();
  }
}

async function refreshReports() {
  const reports = await api.importReports(12).catch(() => ({ reports: [] }));
  ui.reports = Array.isArray(reports?.reports) ? reports.reports : [];
}

/* ─────────────  Helpers  ───────────── */

function confidenceLabel(value) {
  const v = String(value || '').toLowerCase();
  if (v === 'high') return 'High confidence';
  if (v === 'medium') return 'Medium confidence';
  return 'Low confidence';
}

function confidencePercent(value) {
  const n = Number(value);
  if (!Number.isFinite(n) || n <= 0) return '0%';
  return `${Math.round(Math.min(1, Math.max(0, n)) * 100)}%`;
}

function templateLabel(selected, detected) {
  const chosen = humanText(selected || 'auto');
  const found = humanText(detected || selected || 'generic');
  if (!selected || selected === detected) return found || 'Generic';
  return `${chosen} selected, ${found} detected`;
}

function templateConfidenceLabel(value) {
  const v = String(value || '').toLowerCase();
  if (v === 'auto') return 'Auto detect';
  if (v === 'flexible') return 'Flexible';
  return 'Known template';
}

function reviewItemPayload(item) {
  return item && typeof item.action_payload === 'object' ? item.action_payload : {};
}

function reviewItemHref(item) {
  const payload = reviewItemPayload(item);
  const route = payload.review_route && typeof payload.review_route === 'object' ? payload.review_route : {};
  if (route.route !== 'portfolio') return '';
  const params = new URLSearchParams();
  params.set('section', route.target || 'assets');
  if (payload.report_id) params.set('import_report', payload.report_id);
  if (payload.session_id) params.set('import_session', payload.session_id);
  if (payload.symbol) params.set('symbol', payload.symbol);
  if (payload.account_name) params.set('account', payload.account_name);
  return `#portfolio?${params.toString()}`;
}

function reviewItemLabel(item) {
  const payload = reviewItemPayload(item);
  const route = payload.review_route && typeof payload.review_route === 'object' ? payload.review_route : {};
  if (route.target === 'accounts') return 'Review in Portfolio Accounts';
  return 'Review in Investments & Assets';
}

function reviewItemKindLabel(item) {
  const payload = reviewItemPayload(item);
  return payload.kind === 'portfolio_account_review_item' ? 'Account review' : 'Asset review';
}

function reviewItemTone(item) {
  const payload = reviewItemPayload(item);
  return payload.kind === 'portfolio_account_review_item' ? 'proposed' : 'rejected';
}

function toneForConfidence(value) {
  const v = String(value || '').toLowerCase();
  if (v === 'high') return 'applied';
  if (v === 'medium') return 'proposed';
  return 'rejected';
}

function compactObject(obj) {
  return Object.entries(obj || {})
    .filter(([, value]) => value != null && String(value).trim())
    .slice(0, 4)
    .map(([key, value]) => `${humanText(key)} ${value}`)
    .join(' · ');
}

function humanText(value) {
  return String(value || '')
    .replace(/[_:]+/g, ' ')
    .replace(/\s+/g, ' ')
    .trim();
}

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
    <div class="skeleton" style="height: 180px;">.</div>
    <div class="skeleton" style="height: 120px; margin-top: 12px;">.</div>
  `;
}
