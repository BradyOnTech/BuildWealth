// IMPORT & REVIEW.
// Bring raw statement data into BuildWealth, review what was understood,
// then apply the clean rows to Portfolio with an import report for evidence.

import { api } from '../lib/api.js';
import { state } from '../lib/state.js';
import { html, raw, $, esc, setView, delegate } from '../lib/dom.js';
import { fmtRelative, fmtUsd } from '../lib/format.js';
import { skeleton } from '../lib/skeleton.js';
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
  connections:    null,
  connectionError: null,
  connectionBusy:  null,
  connectionNotice: null,
  connectionPreviews: new Map(),
  disconnecting:  null,
};

export const PLAID_LINK_SCRIPT_SRC = 'https://cdn.plaid.com/link/v2/stable/link-initialize.js';
const PLAID_OAUTH_SESSION_KEY = 'buildwealth.plaid.oauth-session';
let plaidLinkScriptPromise = null;

// Plaid is intentionally absent from the initial page load. The official Link
// script is requested only after the user chooses Connect or Repair.
export function loadPlaidLink({ documentRef = globalThis.document, windowRef = globalThis.window } = {}) {
  if (windowRef?.Plaid?.create) return Promise.resolve(windowRef.Plaid);
  if (plaidLinkScriptPromise) return plaidLinkScriptPromise;
  plaidLinkScriptPromise = new Promise((resolve, reject) => {
    const existing = documentRef?.querySelector?.(`script[src="${PLAID_LINK_SCRIPT_SRC}"]`);
    const script = existing || documentRef?.createElement?.('script');
    if (!script) {
      plaidLinkScriptPromise = null;
      reject(new Error('Plaid Link cannot load in this browser.'));
      return;
    }
    const loaded = () => {
      if (windowRef?.Plaid?.create) resolve(windowRef.Plaid);
      else {
        plaidLinkScriptPromise = null;
        reject(new Error('Plaid Link loaded without its browser API.'));
      }
    };
    const failed = () => {
      plaidLinkScriptPromise = null;
      reject(new Error('Could not load Plaid Link. Check your connection and try again.'));
    };
    script.addEventListener('load', loaded, { once: true });
    script.addEventListener('error', failed, { once: true });
    if (!existing) {
      script.src = PLAID_LINK_SCRIPT_SRC;
      script.async = true;
      script.dataset.buildwealthPlaidLink = 'true';
      documentRef.head.appendChild(script);
    }
  });
  return plaidLinkScriptPromise;
}

export function template() {
  return html`
    <section class="page" id="import-sync-page">
      <div class="import-shell" id="import-shell">
        ${raw(masthead())}${raw(skeletonBody())}
      </div>
    </section>
  `;
}

export async function init(params = {}) {
  ui.focusReportId = String(params.report || '').trim() || null;
  attachHandlers();
  await load();
  await resumePlaidOAuthIfNeeded();
  if (ui.focusReportId) await openReport(ui.focusReportId);
}

async function load() {
  ui.loaded = false;
  ui.loadError = null;
  try {
    const [sync, files, templates, reports, connections] = await Promise.all([
      api.syncStatus(),
      api.importFiles().catch(() => ({ items: [] })),
      api.csvTemplates().catch(() => ({ templates: [] })),
      api.importReports(12).catch(() => ({ reports: [] })),
      api.financialConnections().catch(err => ({
        enabled: true,
        configured: true,
        items: [],
        _loadError: err?.message || 'Could not load financial connections.',
      })),
    ]);
    ui.sync = sync || null;
    ui.files = Array.isArray(files?.items) ? files.items : (Array.isArray(files) ? files : []);
    ui.templates = Array.isArray(templates?.templates) ? templates.templates : (Array.isArray(templates) ? templates : []);
    ui.reports = Array.isArray(reports?.reports) ? reports.reports : [];
    ui.connections = connections || { enabled: false, configured: false, items: [] };
    ui.connectionError = connections?._loadError || null;
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
    ${raw(connectionsCard())}
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
        Connect a read-only investment account, enter information manually, or
        upload a CSV. You always review new connected accounts before they become portfolio truth.
      </p>
    </header>
  `;
}

function connectionsCard() {
  const response = ui.connections || {};
  const items = Array.isArray(response.items) ? response.items : [];
  const enabled = response.enabled !== false;
  const configured = response.configured !== false;

  return html`
    <section class="settings-card connection-card" id="financial-connections">
      <header class="connection-card-head">
        <div class="settings-card-head">
          <p class="settings-eyebrow">Read-only connection</p>
          <h2 class="settings-card-title">Connect investment account</h2>
          <p class="settings-card-lede">
            Plaid connects to your institution and sends BuildWealth the accounts,
            balances, cash, and holdings you approve. BuildWealth never receives
            your bank password and cannot trade or move money.
          </p>
        </div>
        ${enabled && configured ? html`
          <button class="btn btn-primary" id="connection-start" type="button"
            ${ui.connectionBusy ? 'disabled' : ''}>
            ${ui.connectionBusy === 'new' ? 'Opening Plaid...' : 'Connect with Plaid'}
          </button>
        ` : ''}
      </header>

      <div class="connection-consent-note">
        <strong>Before you connect</strong>
        <span>
          Connected data is stored for household planning and updates automatically
          until you disconnect. At disconnect, you choose whether to keep a frozen
          copy or remove the connected data.
        </span>
      </div>

      ${!enabled ? raw(connectionUnavailable(
        'Connections are turned off',
        'This deployment has financial connections disabled. Manual entry and CSV import still work normally.',
      )) : ''}
      ${enabled && !configured ? raw(connectionUnavailable(
        'Plaid needs to be configured',
        'The connection feature is available, but its server credentials are not configured. No financial data has been shared.',
      )) : ''}
      ${ui.connectionError ? html`<p class="error-banner" role="alert">${ui.connectionError}</p>` : ''}
      ${ui.connectionNotice ? html`<p class="success-banner" role="status">${ui.connectionNotice}</p>` : ''}

      ${enabled && configured && items.length
        ? html`<div class="connection-list">${raw(items.map(connectionItem).join(''))}</div>`
        : ''}
      ${enabled && configured && !items.length && !ui.connectionError
        ? html`<p class="profile-card-empty">No connected institutions yet.</p>`
        : ''}

      <footer class="connection-alternatives">
        <span>Prefer not to connect?</span>
        <a class="link-editorial" href="#portfolio?section=accounts">Enter an account manually</a>
        <a class="link-editorial" href="#import-workbench">Use the CSV workbench below</a>
      </footer>
    </section>
  `;
}

function connectionUnavailable(title, detail) {
  return html`
    <div class="connection-state-note">
      <span class="status-pill archived"><span class="dot"></span>Unavailable</span>
      <div><strong>${title}</strong><p>${detail}</p></div>
    </div>
  `;
}

function connectionItem(connection) {
  const id = connectionId(connection);
  const status = String(connection?.status || connection?.health?.status || 'active').toLowerCase();
  const preview = ui.connectionPreviews.get(id) || connection?.preview || null;
  const disconnectPreview = ui.disconnecting?.connectionId === id ? ui.disconnecting.preview : null;
  const institution = connection?.institution_name || connection?.institution?.name || 'Connected institution';
  const mask = connection?.mask || connection?.account_mask || '';
  const busy = ui.connectionBusy === id;
  const health = connectionStatus(status, connection);
  const freshness = connectionFreshness(connection, status);

  return html`
    <article class="connection-item" data-connection-id="${id}">
      <header class="connection-item-head">
        <div>
          <h3>${institution}${mask ? ` •••• ${mask}` : ''}</h3>
          <p>${connectionAccountSummary(connection)}</p>
        </div>
        <span class="status-pill ${health.tone}"><span class="dot"></span>${health.label}</span>
      </header>
      <div class="connection-meta">
        <span><strong>Source</strong> Plaid · read-only</span>
        <span class="${freshness.stale ? 'is-stale' : ''}"><strong>Freshness</strong> ${freshness.label}</span>
        ${connection?.connected_by_name ? html`<span><strong>Connected by</strong> ${connection.connected_by_name}</span>` : ''}
      </div>
      ${connection?.last_error?.message || connection?.last_error_message || connection?.error_message ? html`
        <p class="inline-warning" role="status">${connection?.last_error?.message || connection?.last_error_message || connection?.error_message}</p>
      ` : ''}
      ${status === 'pending_review' ? html`
        <p class="inline-warning">For security, an unapproved connection is automatically revoked ${pendingReviewDeadline(connection)}.</p>
      ` : ''}
      ${status === 'disconnect_pending' ? html`
        <p class="inline-warning" role="status">Plaid revocation is pending and will be retried automatically. Connected data remains stale until cleanup finishes.</p>
      ` : ''}

      ${status === 'pending_review' && !disconnectPreview ? raw(connectionReview(connection, preview, busy)) : ''}
      ${disconnectPreview ? raw(disconnectPanel(connection, disconnectPreview, busy)) : ''}

      ${['active', 'needs_attention', 'error'].includes(status) && !disconnectPreview ? html`
        <footer class="connection-actions">
          ${['needs_attention', 'error'].includes(status) ? html`
            <button class="btn btn-primary connection-repair" type="button" data-connection-id="${id}" ${busy ? 'disabled' : ''}>
              ${busy ? 'Opening...' : 'Repair connection'}
            </button>
          ` : ''}
          ${status !== 'error' ? html`
            <button class="btn btn-quiet connection-sync" type="button" data-connection-id="${id}" ${busy ? 'disabled' : ''}>
              ${busy ? 'Checking...' : 'Check for updates'}
            </button>
          ` : ''}
          <button class="btn btn-quiet connection-disconnect" type="button" data-connection-id="${id}" ${busy ? 'disabled' : ''}>
            Disconnect
          </button>
        </footer>
      ` : ''}
    </article>
  `;
}

function pendingReviewDeadline(connection = {}) {
  const created = new Date(connection.created_at || '');
  if (Number.isNaN(created.getTime())) return 'after 72 hours';
  return `on ${new Date(created.getTime() + 72 * 3600 * 1000).toLocaleString('en-US', {
    month: 'short', day: 'numeric', hour: 'numeric', minute: '2-digit',
  })}`;
}

function connectionReview(connection, preview, busy) {
  const id = connectionId(connection);
  if (!preview) {
    return html`
      <div class="connection-review-empty">
        <p>This connection is waiting for account matching and your approval.</p>
        <div class="connection-actions">
          <button class="btn btn-primary connection-resume" type="button" data-connection-id="${id}" ${busy ? 'disabled' : ''}>
            ${busy ? 'Loading...' : 'Resume review'}
          </button>
          <button class="btn btn-quiet connection-disconnect" type="button" data-connection-id="${id}" ${busy ? 'disabled' : ''}>Cancel connection</button>
        </div>
      </div>
    `;
  }

  const accounts = previewAccounts(preview);
  return html`
    <section class="connection-review">
      <header>
        <div>
          <p class="settings-eyebrow">Review before import</p>
          <h4>Choose accounts and confirm every match</h4>
        </div>
        <span>${accounts.length} account${accounts.length === 1 ? '' : 's'}</span>
      </header>
      <p class="settings-card-lede">
        Suggestions are only suggestions. Nothing is merged or added until you activate this connection.
      </p>
      ${accounts.length ? html`
        <div class="connection-account-list">
          ${raw(accounts.map((account, index) => connectionAccountRow(account, preview, index)).join(''))}
        </div>
      ` : html`<p class="inline-warning">Plaid did not return any investment accounts to review.</p>`}
      <footer class="connection-actions">
        <button class="btn btn-primary connection-activate" type="button" data-connection-id="${id}"
          ${busy || !accounts.length ? 'disabled' : ''}>
          ${busy ? 'Activating...' : 'Approve and activate'}
        </button>
        <button class="btn btn-quiet connection-disconnect" type="button" data-connection-id="${id}" ${busy ? 'disabled' : ''}>
          Cancel connection
        </button>
      </footer>
    </section>
  `;
}

function connectionAccountRow(account, preview, index) {
  const providerId = providerAccountId(account);
  const suggested = account?.suggested_match || account?.match || {};
  const suggestedId = suggested?.buildwealth_account_id || suggested?.account_id || account?.buildwealth_account_id || '';
  const options = accountMatchOptions(account, preview, suggested);
  const balance = account?.current_balance ?? account?.balances?.current;
  const holdingCount = account?.holdings_count ?? account?.holding_count;
  const mask = account?.mask ? `•••• ${account.mask}` : '';
  return html`
    <article class="connection-account-row" data-provider-account-id="${providerId}">
      <label class="connection-account-include">
        <input type="checkbox" class="connection-account-checkbox" ${account?.include === false ? '' : 'checked'} />
        <span>
          <strong>${account?.name || account?.official_name || `Investment account ${index + 1}`}</strong>
          <small>${[account?.account_subtype || account?.subtype || account?.account_type || account?.type, mask].filter(Boolean).join(' · ')}</small>
        </span>
      </label>
      <div class="connection-account-evidence">
        ${balance != null ? `<span>${esc(fmtUsd(Number(balance)))}</span>` : ''}
        ${holdingCount != null ? `<span>${esc(holdingCount)} holding${Number(holdingCount) === 1 ? '' : 's'}</span>` : ''}
      </div>
      <label class="settings-field connection-match-field">
        <span class="settings-label">BuildWealth account</span>
        <select class="settings-input connection-account-match">
          <option value="">Create a new account</option>
          ${raw(options.map(option => `
            <option value="${esc(option.id)}" ${String(option.id) === String(suggestedId) ? 'selected' : ''}>
              ${esc(option.name)}${option.id === suggestedId ? ' — suggested' : ''}
            </option>
          `).join(''))}
        </select>
        <span class="settings-hint">
          ${suggestedId ? `BuildWealth suggested this match${suggested?.reason ? ` because ${suggested.reason}` : ''}. Confirm it or choose another.` : 'No confident match was found. A new account will be created.'}
        </span>
      </label>
    </article>
  `;
}

function disconnectPanel(connection, preview, busy) {
  const id = connectionId(connection);
  const pending = String(connection?.status || '').toLowerCase() === 'pending_review';
  const accountCount = preview?.account_count ?? preview?.connected_account_count ?? connection?.account_count;
  const holdingCount = preview?.holding_count ?? preview?.connected_holding_count;
  return html`
    <section class="connection-disconnect-panel">
      <header>
        <div>
          <p class="settings-eyebrow">Disconnect preview</p>
          <h4>${pending ? 'Cancel this pending connection?' : 'What should happen to connected data?'}</h4>
        </div>
        ${accountCount != null ? `<span>${esc(accountCount)} account${Number(accountCount) === 1 ? '' : 's'}${holdingCount != null ? ` · ${esc(holdingCount)} holdings` : ''}</span>` : ''}
      </header>
      <p class="settings-card-lede">
        Plaid access is revoked in either case. Manual accounts and CSV history are never removed by this action.
      </p>
      ${pending ? html`
        <label class="connection-retention-choice">
          <input type="radio" name="retention-${id}" value="remove_connected_data" checked />
          <span><strong>Cancel and remove connected data</strong><small>Remove this unfinished preview and its Plaid connection.</small></span>
        </label>
      ` : html`
        <div class="connection-retention-options">
          <label class="connection-retention-choice">
            <input type="radio" name="retention-${id}" value="keep_frozen" checked />
            <span><strong>Keep a frozen copy</strong><small>Keep the last imported snapshot, clearly marked disconnected and stale.</small></span>
          </label>
          <label class="connection-retention-choice">
            <input type="radio" name="retention-${id}" value="remove_connected_data" />
            <span><strong>Remove connected data</strong><small>Delete Plaid observations and mappings while preserving unrelated manual data.</small></span>
          </label>
        </div>
      `}
      ${preview?.warning ? html`<p class="inline-warning">${preview.warning}</p>` : ''}
      <footer class="connection-actions">
        <button class="btn btn-danger connection-disconnect-confirm" type="button" data-connection-id="${id}" ${busy ? 'disabled' : ''}>
          ${busy ? 'Disconnecting...' : (pending ? 'Cancel connection' : 'Disconnect from Plaid')}
        </button>
        <button class="btn btn-quiet connection-disconnect-cancel" type="button" data-connection-id="${id}" ${busy ? 'disabled' : ''}>Go back</button>
      </footer>
    </section>
  `;
}

function connectionStatus(status, connection) {
  if (status === 'pending_review') return { label: 'Pending review', tone: 'proposed' };
  if (status === 'needs_attention' || status === 'error') return { label: 'Needs attention', tone: 'rejected' };
  if (status === 'disconnect_pending') return { label: 'Disconnecting', tone: 'proposed' };
  if (status === 'disconnected') return { label: 'Disconnected', tone: 'archived' };
  if (status === 'stale') return { label: 'Active · stale', tone: 'proposed' };
  if (connection?.stale) return { label: 'Active · stale', tone: 'proposed' };
  return { label: 'Active', tone: 'applied' };
}

function connectionFreshness(connection, status) {
  const last = connection?.last_successful_sync_at || connection?.last_synced_at || connection?.last_observed_at;
  const stale = Boolean(connection?.stale) || ['needs_attention', 'error', 'stale', 'disconnected'].includes(status);
  if (!last) return { stale: true, label: status === 'pending_review' ? 'Not imported yet' : 'No successful update yet' };
  const relative = fmtRelative(last);
  return { stale, label: `${relative || 'Unknown'}${stale ? ' · stale' : ''}` };
}

function connectionAccountSummary(connection) {
  const count = connection?.account_count ?? (Array.isArray(connection?.accounts) ? connection.accounts.length : null);
  if (count == null) return 'Investment connection';
  return `${count} approved account${Number(count) === 1 ? '' : 's'}`;
}

function connectionId(connection) {
  return String(connection?.connection_id || connection?.id || '');
}

function previewAccounts(preview) {
  return Array.isArray(preview?.accounts) ? preview.accounts : [];
}

function providerAccountId(account) {
  return String(account?.provider_account_id || account?.account_id || account?.id || '');
}

function accountMatchOptions(account, preview, suggested) {
  const candidates = [
    ...(Array.isArray(account?.match_candidates) ? account.match_candidates : []),
    ...(Array.isArray(preview?.buildwealth_accounts) ? preview.buildwealth_accounts : []),
    ...(Array.isArray(preview?.available_buildwealth_accounts) ? preview.available_buildwealth_accounts : []),
  ];
  if (suggested && Object.keys(suggested).length) candidates.unshift(suggested);
  const seen = new Set();
  return candidates.flatMap(candidate => {
    const id = candidate?.buildwealth_account_id || candidate?.account_id || candidate?.id;
    if (!id || seen.has(String(id))) return [];
    seen.add(String(id));
    return [{ id: String(id), name: candidate?.name || candidate?.account_name || String(id) }];
  });
}

function workbenchCard() {
  return html`
    <section class="settings-card import-workbench-card" id="import-workbench">
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
  delegate(root, 'click', '#connection-start', (e) => { e.preventDefault(); startPlaidConnection(); });
  delegate(root, 'click', '.connection-resume', (e, target) => {
    e.preventDefault();
    loadConnectionPreview(target.dataset.connectionId);
  });
  delegate(root, 'click', '.connection-activate', (e, target) => {
    e.preventDefault();
    activateConnection(target.dataset.connectionId);
  });
  delegate(root, 'click', '.connection-sync', (e, target) => {
    e.preventDefault();
    checkConnection(target.dataset.connectionId);
  });
  delegate(root, 'click', '.connection-repair', (e, target) => {
    e.preventDefault();
    repairConnection(target.dataset.connectionId);
  });
  delegate(root, 'click', '.connection-disconnect', (e, target) => {
    e.preventDefault();
    beginDisconnect(target.dataset.connectionId);
  });
  delegate(root, 'click', '.connection-disconnect-cancel', (e) => {
    e.preventDefault();
    ui.disconnecting = null;
    render();
  });
  delegate(root, 'click', '.connection-disconnect-confirm', (e, target) => {
    e.preventDefault();
    confirmDisconnect(target.dataset.connectionId);
  });
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

async function startPlaidConnection() {
  if (ui.connectionBusy) return;
  ui.connectionBusy = 'new';
  ui.connectionError = null;
  ui.connectionNotice = null;
  render();
  try {
    const [Plaid, tokenResponse] = await Promise.all([
      loadPlaidLink(),
      api.createPlaidLinkToken(),
    ]);
    savePlaidOAuthSession({ mode: 'new', linkToken: tokenResponse?.link_token });
    const result = await openPlaidSession(
      Plaid,
      tokenResponse?.link_token,
      exchangePlaidSuccess,
    );
    if (result?.exited) {
      clearPlaidOAuthSession();
      return;
    }
    clearPlaidOAuthSession();
    const connection = result?.connection || {};
    const id = connectionId(connection) || String(result?.preview?.connection_id || '');
    if (id && result?.preview) ui.connectionPreviews.set(id, result.preview);
    ui.connectionNotice = 'Plaid connected. Review every account and match before activation.';
    await reloadConnections();
  } catch (err) {
    ui.connectionError = err?.message || 'Could not start the Plaid connection.';
  } finally {
    ui.connectionBusy = null;
    render();
  }
}

async function loadConnectionPreview(connectionIdValue) {
  const id = String(connectionIdValue || '');
  if (!id || ui.connectionBusy) return;
  ui.connectionBusy = id;
  ui.connectionError = null;
  render();
  try {
    const preview = await api.financialConnectionPreview(id);
    ui.connectionPreviews.set(id, preview?.preview || preview);
  } catch (err) {
    ui.connectionError = err?.message || 'Could not load this account review.';
  } finally {
    ui.connectionBusy = null;
    render();
  }
}

async function activateConnection(connectionIdValue) {
  const id = String(connectionIdValue || '');
  if (!id || ui.connectionBusy) return;
  const item = connectionItemElement(id);
  const rows = Array.from(item?.querySelectorAll('.connection-account-row') || []);
  const accounts = rows.map(row => ({
    provider_account_id: String(row.dataset.providerAccountId || ''),
    include: Boolean(row.querySelector('.connection-account-checkbox')?.checked),
    buildwealth_account_id: String(row.querySelector('.connection-account-match')?.value || '') || null,
  }));
  if (!accounts.some(account => account.include)) {
    ui.connectionError = 'Choose at least one account before activation.';
    render();
    return;
  }
  ui.connectionBusy = id;
  ui.connectionError = null;
  ui.connectionNotice = null;
  render();
  try {
    await api.activateFinancialConnection(id, { accounts });
    ui.connectionPreviews.delete(id);
    ui.connectionNotice = 'Connection activated. Approved accounts will update automatically each day.';
    await reloadConnections();
  } catch (err) {
    ui.connectionError = err?.message || 'Could not activate this connection.';
  } finally {
    ui.connectionBusy = null;
    render();
  }
}

async function checkConnection(connectionIdValue) {
  const id = String(connectionIdValue || '');
  if (!id || ui.connectionBusy) return;
  ui.connectionBusy = id;
  ui.connectionError = null;
  ui.connectionNotice = null;
  render();
  try {
    await api.syncFinancialConnection(id);
    ui.connectionNotice = 'Connection checked using currently available provider data.';
    await reloadConnections();
  } catch (err) {
    ui.connectionError = err?.message || 'Could not check this connection.';
  } finally {
    ui.connectionBusy = null;
    render();
  }
}

async function repairConnection(connectionIdValue) {
  const id = String(connectionIdValue || '');
  if (!id || ui.connectionBusy) return;
  ui.connectionBusy = id;
  ui.connectionError = null;
  ui.connectionNotice = null;
  render();
  try {
    const [Plaid, tokenResponse] = await Promise.all([
      loadPlaidLink(),
      api.createFinancialConnectionUpdateLinkToken(id),
    ]);
    savePlaidOAuthSession({ mode: 'repair', linkToken: tokenResponse?.link_token, connectionId: id });
    const result = await openPlaidSession(Plaid, tokenResponse?.link_token, async () => {
      return api.syncFinancialConnection(id);
    });
    if (result?.exited) {
      clearPlaidOAuthSession();
      return;
    }
    clearPlaidOAuthSession();
    ui.connectionNotice = result?.connection?.status === 'active'
      ? 'Connection repaired and checked for updates.'
      : 'Plaid sign-in finished, but the institution still needs attention.';
    await reloadConnections();
  } catch (err) {
    ui.connectionError = err?.message || 'Could not repair this connection.';
  } finally {
    ui.connectionBusy = null;
    render();
  }
}

async function beginDisconnect(connectionIdValue) {
  const id = String(connectionIdValue || '');
  if (!id || ui.connectionBusy) return;
  ui.connectionBusy = id;
  ui.connectionError = null;
  render();
  try {
    const response = await api.financialConnectionDisconnectPreview(id);
    ui.disconnecting = { connectionId: id, preview: response?.preview || response || {} };
  } catch (err) {
    ui.connectionError = err?.message || 'Could not prepare the disconnect preview.';
  } finally {
    ui.connectionBusy = null;
    render();
  }
}

async function confirmDisconnect(connectionIdValue) {
  const id = String(connectionIdValue || '');
  if (!id || ui.connectionBusy) return;
  const item = connectionItemElement(id);
  const retention = item?.querySelector('.connection-disconnect-panel input[type="radio"]:checked')?.value;
  if (!['keep_frozen', 'remove_connected_data'].includes(retention)) {
    ui.connectionError = 'Choose what should happen to connected data.';
    render();
    return;
  }
  ui.connectionBusy = id;
  ui.connectionError = null;
  ui.connectionNotice = null;
  render();
  try {
    await api.disconnectFinancialConnection(id, retention);
    ui.connectionPreviews.delete(id);
    ui.disconnecting = null;
    ui.connectionNotice = retention === 'keep_frozen'
      ? 'Plaid access was revoked. The last snapshot remains as a frozen, stale copy.'
      : 'Plaid access and connected data were removed. Manual and CSV data were preserved.';
    await reloadConnections();
  } catch (err) {
    ui.connectionError = err?.message || 'Could not disconnect this connection.';
  } finally {
    ui.connectionBusy = null;
    render();
  }
}

async function reloadConnections() {
  const response = await api.financialConnections();
  ui.connections = response || { enabled: false, configured: false, items: [] };
}

function connectionItemElement(id) {
  return Array.from(globalThis.document?.querySelectorAll?.('.connection-item') || [])
    .find(item => item.dataset.connectionId === id) || null;
}

function openPlaidSession(Plaid, linkToken, onSuccess, { receivedRedirectUri = '' } = {}) {
  if (!linkToken) return Promise.reject(new Error('The server did not return a Plaid Link token.'));
  return new Promise((resolve, reject) => {
    let handler;
    let settled = false;
    const finish = (callback, value) => {
      if (settled) return;
      settled = true;
      try { handler?.destroy?.(); } catch { /* Plaid owns its frame cleanup. */ }
      callback(value);
    };
    try {
      handler = Plaid.create({
        token: linkToken,
        ...(receivedRedirectUri ? { receivedRedirectUri } : {}),
        onSuccess: (publicToken, metadata) => {
          Promise.resolve(onSuccess(publicToken, metadata))
            .then(value => finish(resolve, value))
            .catch(error => finish(reject, error));
        },
        onExit: (error) => {
          if (error) finish(reject, new Error(error.display_message || error.error_message || 'Plaid Link closed with an error.'));
          else finish(resolve, { exited: true });
        },
      });
      handler.open();
    } catch (err) {
      finish(reject, err);
    }
  });
}

async function exchangePlaidSuccess(publicToken, metadata) {
  const institution = metadata?.institution ? {
    institution_id: metadata.institution.institution_id || null,
    name: metadata.institution.name || null,
  } : undefined;
  const existing = Array.isArray(ui.connections?.items) ? ui.connections.items : [];
  if (institution?.institution_id && existing.some(connection => (
    connection?.institution_id === institution.institution_id
    && connection?.status !== 'disconnected'
  ))) {
    throw new Error('This institution is already connected. Use Repair or manage the existing connection instead.');
  }
  return api.exchangePlaidPublicToken({ public_token: publicToken, institution });
}

function savePlaidOAuthSession(value) {
  if (!value?.linkToken) return;
  try {
    globalThis.sessionStorage?.setItem(PLAID_OAUTH_SESSION_KEY, JSON.stringify(value));
  } catch { /* Storage may be unavailable in hardened browsers. */ }
}

function clearPlaidOAuthSession() {
  try { globalThis.sessionStorage?.removeItem(PLAID_OAUTH_SESSION_KEY); } catch { /* no-op */ }
}

function readPlaidOAuthSession() {
  try {
    const rawValue = globalThis.sessionStorage?.getItem(PLAID_OAUTH_SESSION_KEY);
    const value = rawValue ? JSON.parse(rawValue) : null;
    return value && typeof value === 'object' ? value : null;
  } catch {
    return null;
  }
}

async function resumePlaidOAuthIfNeeded() {
  const locationRef = globalThis.location;
  if (!locationRef?.href) return;
  const currentUrl = new URL(locationRef.href);
  if (!currentUrl.searchParams.has('oauth_state_id')) return;
  const saved = readPlaidOAuthSession();
  if (!saved?.linkToken) {
    ui.connectionError = 'Plaid returned from sign-in, but the original session expired. Start the connection again.';
    render();
    return;
  }
  ui.connectionBusy = saved.connectionId || 'new';
  render();
  try {
    const Plaid = await loadPlaidLink();
    const onSuccess = saved.mode === 'repair'
      ? async () => {
        return api.syncFinancialConnection(saved.connectionId);
      }
      : exchangePlaidSuccess;
    const result = await openPlaidSession(Plaid, saved.linkToken, onSuccess, {
      receivedRedirectUri: currentUrl.href,
    });
    if (!result?.exited) {
      clearPlaidOAuthSession();
      ui.connectionNotice = saved.mode === 'repair'
        ? (result?.connection?.status === 'active'
          ? 'Connection repaired and checked for updates.'
          : 'Plaid sign-in finished, but the institution still needs attention.')
        : 'Plaid connected. Review every account and match before activation.';
      if (result?.preview) {
        const id = connectionId(result?.connection || {}) || String(result.preview.connection_id || '');
        if (id) ui.connectionPreviews.set(id, result.preview);
      }
      currentUrl.searchParams.delete('oauth_state_id');
      globalThis.history?.replaceState?.({}, '', `${currentUrl.pathname}${currentUrl.search}${currentUrl.hash}`);
      await reloadConnections();
    }
  } catch (err) {
    ui.connectionError = err?.message || 'Could not finish Plaid sign-in.';
  } finally {
    ui.connectionBusy = null;
    render();
  }
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

function skeletonBody() {
  return html`
    ${skeleton('180px')}
    ${skeleton('120px', { marginTop: '12px' })}
  `;
}
