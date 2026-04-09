import { fetchJson } from '../lib/api.js';
import { state } from '../lib/state.js';
import { byId, fmtCurrency, fmtAgeMinutes, fmtDate, writeLog } from '../lib/utils.js';
import { renderItemList } from '../lib/components.js';

export const id = 'dashboard';
export const label = 'Today';
export const icon = '<svg viewBox="0 0 20 20" fill="none" stroke="currentColor" stroke-width="1.6"><rect x="3" y="3" width="6" height="6" rx="1.5"/><rect x="11" y="3" width="6" height="6" rx="1.5"/><rect x="3" y="11" width="6" height="6" rx="1.5"/><rect x="11" y="11" width="6" height="6" rx="1.5"/></svg>';

export function template() {
  return `
    <div class="view-header"><h2>Today Dashboard</h2><button class="ghost small" id="reload-today">Reload</button></div>
    <p class="hint" id="today-generated">Loading dashboard...</p>
    <p class="context-banner warning" id="today-context-banner">Context readiness unavailable.</p>
    <div class="kpi-row">
      <article class="kpi-card"><p class="kpi-label">Net Worth</p><p class="kpi-value" id="today-net-worth">-</p></article>
      <article class="kpi-card"><p class="kpi-label">Portfolio Value</p><p class="kpi-value" id="today-total-value">-</p></article>
      <article class="kpi-card"><p class="kpi-label">Monthly Surplus</p><p class="kpi-value" id="today-surplus">-</p></article>
      <article class="kpi-card"><p class="kpi-label">Savings Rate</p><p class="kpi-value" id="today-savings-rate">-</p></article>
    </div>
    <div class="kpi-row">
      <article class="kpi-card"><p class="kpi-label">Snapshot Freshness</p><p class="kpi-value" id="today-snapshot-freshness">-</p></article>
      <article class="kpi-card"><p class="kpi-label">Concentration Risk</p><p class="kpi-value" id="today-concentration">-</p></article>
      <article class="kpi-card"><p class="kpi-label">Financial Health</p><p class="kpi-value" id="today-health-status">-</p></article>
      <article class="kpi-card"><p class="kpi-label">Active Plan</p><p class="kpi-value" id="today-active-plan">-</p></article>
    </div>
    <div class="three-col">
      <section class="panel">
        <h3 class="panel-title">Checklist</h3>
        <div id="today-checklist" class="item-list"></div>
      </section>
      <section class="panel">
        <h3 class="panel-title">Recommendations</h3>
        <div id="today-recommendations" class="item-list"></div>
      </section>
      <section class="panel">
        <h3 class="panel-title">Workflow</h3>
        <ol id="today-workflow" class="workflow-steps"></ol>
        <div class="panel-actions">
          <button class="ghost small" id="today-run-sync" type="button">Run Sync Now</button>
          <button class="primary small" id="today-ask-copilot" type="button">Ask Copilot Review</button>
        </div>
      </section>
    </div>`;
}

function render(payload) {
  state.todayDashboard = payload;
  const onPct = typeof payload.onboarding_completion_percent === 'number' ? `${payload.onboarding_completion_percent.toFixed(1)}%` : '-';
  const inboxOpen = Number(payload.inbox_open_count || 0);
  const inboxHigh = Number(payload.inbox_high_priority_count || 0);
  byId('today-generated').textContent = `Generated ${fmtDate(payload.generated_at)} \u2022 ${payload.state} \u2022 ${payload.currency} \u2022 Onboarding ${onPct} \u2022 Inbox ${inboxOpen} open (${inboxHigh} high)`;

  const cs = String(payload.context_state || 'warning').toLowerCase();
  const banner = byId('today-context-banner');
  banner.className = `context-banner ${cs}`;
  const notes = Array.isArray(payload.context_notes) ? payload.context_notes : [];
  banner.textContent = notes.length ? notes.join(' ') : 'Context readiness unavailable.';

  byId('today-net-worth').textContent = payload.net_worth_usd != null ? fmtCurrency(payload.net_worth_usd) : '-';
  byId('today-total-value').textContent = fmtCurrency(payload.total_value_usd);
  byId('today-surplus').textContent = payload.monthly_surplus_usd != null ? fmtCurrency(payload.monthly_surplus_usd) : '-';
  byId('today-savings-rate').textContent = payload.savings_rate_pct != null ? `${payload.savings_rate_pct.toFixed(1)}%` : '-';
  byId('today-snapshot-freshness').textContent = fmtAgeMinutes(payload.snapshot_age_minutes);
  byId('today-concentration').textContent = `${String(payload.concentration_risk || '-').toUpperCase()} ${payload.top_holding_symbol ? `(${payload.top_holding_symbol})` : ''}`;
  byId('today-health-status').textContent = payload.financial_health_status ? payload.financial_health_status.replace('_', ' ').toUpperCase() : '-';
  byId('today-active-plan').textContent = payload.active_plan?.title || 'No active plan';

  renderItemList('today-checklist', payload.checklist, (item) => {
    const el = document.createElement('article');
    el.className = `list-item ${item.status || 'incomplete'}`;
    el.innerHTML = `<p class="list-item-title">${item.title || '-'}</p><p class="list-item-meta">${item.detail || ''}</p>${item.action_hint ? `<p class="list-item-meta">Action: ${item.action_hint}</p>` : ''}`;
    return el;
  });

  renderItemList('today-recommendations', payload.recommendations, (item) => {
    const el = document.createElement('article');
    const p = String(item.priority || 'medium').toLowerCase();
    el.className = `list-item ${p === 'high' ? 'attention' : p === 'low' ? 'complete' : 'incomplete'}`;
    el.innerHTML = `<p class="list-item-title">${item.title || '-'}</p><p class="list-item-meta">Priority: ${String(item.priority || 'medium').toUpperCase()}</p><p class="list-item-meta">${item.detail || ''}</p>`;
    return el;
  });

  const wl = byId('today-workflow');
  wl.innerHTML = '';
  const steps = Array.isArray(payload.workflow_steps) ? payload.workflow_steps : [];
  if (!steps.length) { wl.innerHTML = '<li>No workflow steps available.</li>'; }
  else { for (const s of steps) { const li = document.createElement('li'); li.textContent = s; wl.appendChild(li); } }
}

export async function load() {
  try {
    render(await fetchJson('/api/dashboard/today'));
  } catch (error) {
    byId('today-generated').textContent = `Dashboard unavailable: ${error.message}`;
    byId('today-context-banner').className = 'context-banner warning';
    byId('today-context-banner').textContent = 'Context readiness unavailable.';
    ['today-total-value', 'today-snapshot-freshness', 'today-concentration', 'today-active-plan'].forEach(id => { const el = byId(id); if (el) el.textContent = '-'; });
  }
}

async function runSync() {
  writeLog('Running manual sync...');
  try {
    const result = await fetchJson('/api/snapshot/sync', { method: 'POST' });
    writeLog('Sync completed.', result);
    await load();
  } catch (error) { writeLog(`Sync failed: ${error.message}`, null, true); }
}

export function init() {
  byId('reload-today').addEventListener('click', () => load().catch(e => writeLog(e.message, null, true)));
  byId('today-run-sync').addEventListener('click', runSync);
  byId('today-ask-copilot').addEventListener('click', () => {
    location.hash = 'copilot?dailyReview=1';
  });
  load();
}
