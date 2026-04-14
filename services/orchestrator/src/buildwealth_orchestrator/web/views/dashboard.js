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
    <div class="kpi-row">
      <article class="kpi-card"><p class="kpi-label">Enabled Engines</p><p class="kpi-value" id="today-engine-enabled">-</p></article>
      <article class="kpi-card"><p class="kpi-label">Reachable Engines</p><p class="kpi-value" id="today-engine-reachable">-</p></article>
      <article class="kpi-card"><p class="kpi-label">Degraded Events</p><p class="kpi-value" id="today-engine-degraded">-</p></article>
      <article class="kpi-card"><p class="kpi-label">Engine Probe Age</p><p class="kpi-value" id="today-engine-probe-age">-</p></article>
    </div>
    <section class="panel">
      <div class="panel-head-inline">
        <h3 class="panel-title">Recommendation Quality Trend</h3>
        <button class="ghost small" id="today-refresh-recommendation-trend" type="button">Refresh Trend</button>
      </div>
      <p class="hint" id="today-recommendation-trend-summary">Trend data unavailable.</p>
      <div id="today-recommendation-trend-list" class="item-list"></div>
    </section>
    <div class="three-col">
      <section class="panel">
        <h3 class="panel-title">Checklist</h3>
        <div id="today-checklist" class="item-list"></div>
      </section>
      <section class="panel">
        <div class="panel-head-inline">
          <h3 class="panel-title">Top 3 Next Actions</h3>
          <button class="ghost small" id="today-open-recommendations" type="button">Open Inbox</button>
        </div>
        <div id="today-top-next-actions" class="item-list"></div>
      </section>
      <section class="panel">
        <h3 class="panel-title">Workflow</h3>
        <ol id="today-workflow" class="workflow-steps"></ol>
        <div class="panel-actions">
          <button class="ghost small" id="today-run-sync" type="button">Run Sync Now</button>
          <button class="primary small" id="today-ask-copilot" type="button">Ask Copilot Review</button>
        </div>
      </section>
    </div>
    <section class="panel">
      <div class="panel-head-inline">
        <h3 class="panel-title">Engine Status</h3>
        <button class="ghost small" id="today-refresh-engines" type="button">Refresh Engine Status</button>
      </div>
      <p class="hint" id="today-engines-as-of">Loading engine status...</p>
      <div id="today-engines-list" class="item-list"></div>
    </section>`;
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

  const topNextActions = Array.isArray(payload.top_next_actions) && payload.top_next_actions.length
    ? payload.top_next_actions
    : (Array.isArray(payload.recommendations) ? payload.recommendations : []);

  renderItemList('today-top-next-actions', topNextActions, (item) => {
    const el = document.createElement('article');
    const p = String(item.priority || 'medium').toLowerCase();
    const scoreTotal = Number(item.score_total);
    const scoreRank = Number(item.score_rank);
    const metaParts = [`Priority: ${String(item.priority || 'medium').toUpperCase()}`];
    if (Number.isFinite(scoreRank) && scoreRank > 0) metaParts.push(`Rank: #${Math.trunc(scoreRank)}`);
    if (Number.isFinite(scoreTotal)) metaParts.push(`Score: ${scoreTotal.toFixed(1)}`);
    if (item.recommendation_type) metaParts.push(`Type: ${String(item.recommendation_type)}`);
    if (item.source) metaParts.push(`Source: ${String(item.source)}`);
    const scoreReasons = Array.isArray(item.score_reasons)
      ? item.score_reasons.filter(Boolean).slice(0, 2).join(' ')
      : '';
    el.className = `list-item ${p === 'high' ? 'attention' : p === 'low' ? 'complete' : 'incomplete'}`;
    el.innerHTML = `<p class="list-item-title">${item.title || '-'}</p><p class="list-item-meta">${metaParts.join(' • ')}</p><p class="list-item-meta">${item.detail || ''}</p>${scoreReasons ? `<p class="list-item-meta">${scoreReasons}</p>` : ''}${item.action_hint ? `<p class="list-item-meta">Action: ${item.action_hint}</p>` : ''}`;
    return el;
  });

  const wl = byId('today-workflow');
  wl.innerHTML = '';
  const steps = Array.isArray(payload.workflow_steps) ? payload.workflow_steps : [];
  if (!steps.length) { wl.innerHTML = '<li>No workflow steps available.</li>'; }
  else { for (const s of steps) { const li = document.createElement('li'); li.textContent = s; wl.appendChild(li); } }
}

function formatPct(value) {
  const num = Number(value);
  if (!Number.isFinite(num)) return 'n/a';
  return `${num.toFixed(1)}%`;
}

function windowRowText(row) {
  if (!row || typeof row !== 'object') return 'n/a';
  const measured = Number(row.measured_count || 0);
  const count = Number(row.count || 0);
  return `${row.window || row.key || '-'}: measured ${measured}/${count}, coverage ${formatPct(row.realized_coverage_pct)}, match ${formatPct(row.future_value_direction_match_rate_pct)}`;
}

function renderRecommendationTrend(payload, { activePlanTitle = '' } = {}) {
  state.dashboardClosureTrend = payload && typeof payload === 'object' ? payload : null;
  const summaryEl = byId('today-recommendation-trend-summary');
  const listEl = byId('today-recommendation-trend-list');
  const globalPayload = payload?.global && typeof payload.global === 'object' ? payload.global : null;
  const planPayload = payload?.plan && typeof payload.plan === 'object' ? payload.plan : null;
  const planLabel = activePlanTitle || 'active plan';
  if (!globalPayload) {
    summaryEl.textContent = 'Recommendation trend data unavailable.';
    listEl.innerHTML = '<article class="list-item incomplete"><p class="list-item-title">No trend analytics available.</p></article>';
    return;
  }

  const globalWindows = Array.isArray(globalPayload.calibration_windows) ? globalPayload.calibration_windows : [];
  const global30 = globalWindows.find((row) => row && row.window === '30d') || {};
  const global90 = globalWindows.find((row) => row && row.window === '90d') || {};
  const globalSummaryParts = [
    `Global closed ${Number(globalPayload.count || 0)}`,
    windowRowText(global30),
    windowRowText(global90),
  ];
  summaryEl.textContent = globalSummaryParts.join(' • ');

  const cards = [];
  cards.push(`<article class="list-item"><p class="list-item-title">Global Trend</p><p class="list-item-meta">${windowRowText(global30)} • ${windowRowText(global90)}</p></article>`);

  if (planPayload) {
    const planWindows = Array.isArray(planPayload.calibration_windows) ? planPayload.calibration_windows : [];
    const plan30 = planWindows.find((row) => row && row.window === '30d') || {};
    const plan90 = planWindows.find((row) => row && row.window === '90d') || {};
    cards.push(`<article class="list-item"><p class="list-item-title">${planLabel} Trend</p><p class="list-item-meta">${windowRowText(plan30)} • ${windowRowText(plan90)}</p></article>`);
  } else {
    cards.push('<article class="list-item"><p class="list-item-title">Plan Trend</p><p class="list-item-meta">No active plan selected for plan-scoped trend analytics.</p></article>');
  }

  listEl.innerHTML = cards.join('');
}

async function loadRecommendationTrend(dashboardPayload) {
  const activePlanId = String(dashboardPayload?.active_plan?.id || '').trim();
  const activePlanTitle = String(dashboardPayload?.active_plan?.title || '').trim();
  const baseParams = new URLSearchParams();
  baseParams.set('limit', '300');
  baseParams.set('statuses', 'applied,rejected');
  baseParams.set('include_pending_realized', 'true');
  const globalUrl = `/api/recommendations/closure-analytics?${baseParams.toString()}`;
  const globalPromise = fetchJson(globalUrl);
  const planPromise = activePlanId
    ? fetchJson(`${globalUrl}&plan_id=${encodeURIComponent(activePlanId)}`)
    : Promise.resolve(null);

  const [globalResult, planResult] = await Promise.allSettled([globalPromise, planPromise]);
  const globalPayload = globalResult.status === 'fulfilled' ? globalResult.value : null;
  const planPayload = planResult.status === 'fulfilled' ? planResult.value : null;
  renderRecommendationTrend({ global: globalPayload, plan: planPayload }, { activePlanTitle });
}

function engineProbeAgeMinutes(asOf) {
  if (!asOf) return null;
  const parsed = new Date(asOf);
  if (Number.isNaN(parsed.getTime())) return null;
  const deltaMs = Date.now() - parsed.getTime();
  return Math.max(0, Math.floor(deltaMs / 60000));
}

function renderEngineStatus(payload, errorMessage = null) {
  const enabledEl = byId('today-engine-enabled');
  const reachableEl = byId('today-engine-reachable');
  const degradedEl = byId('today-engine-degraded');
  const probeAgeEl = byId('today-engine-probe-age');
  const asOfEl = byId('today-engines-as-of');
  const listEl = byId('today-engines-list');

  if (!payload || !Array.isArray(payload.engines)) {
    enabledEl.textContent = '-';
    reachableEl.textContent = '-';
    degradedEl.textContent = '-';
    probeAgeEl.textContent = '-';
    asOfEl.textContent = errorMessage ? `Engine status unavailable: ${errorMessage}` : 'Engine status unavailable.';
    listEl.innerHTML = '<article class="list-item incomplete"><p class="list-item-title">No engine telemetry available.</p></article>';
    return;
  }

  const engines = payload.engines;
  const enabled = engines.filter((item) => item.enabled).length;
  const reachable = engines.filter((item) => item.enabled && item.reachable).length;
  const degradedTotal = engines.reduce((acc, item) => acc + Number(item.degraded_count || 0), 0);
  const probeAge = engineProbeAgeMinutes(payload.as_of);

  enabledEl.textContent = String(enabled);
  reachableEl.textContent = `${reachable}/${enabled}`;
  reachableEl.className = `kpi-value ${enabled > 0 && reachable === enabled ? 'drift-pos' : enabled > 0 ? 'drift-neg' : ''}`;
  degradedEl.textContent = String(degradedTotal);
  degradedEl.className = `kpi-value ${degradedTotal > 0 ? 'drift-neg' : 'drift-pos'}`;
  probeAgeEl.textContent = probeAge == null ? '-' : fmtAgeMinutes(probeAge);
  asOfEl.textContent = `Last probe: ${fmtDate(payload.as_of)}`;

  if (!engines.length) {
    listEl.innerHTML = '<article class="list-item incomplete"><p class="list-item-title">No engines configured.</p></article>';
    return;
  }

  listEl.innerHTML = '';
  for (const engine of engines) {
    const row = document.createElement('article');
    const contractMismatch = engine.enabled && engine.reachable && engine.contract_compatible === false;
    const statusLabel = !engine.enabled
      ? 'DISABLED'
      : contractMismatch
        ? 'CONTRACT MISMATCH'
        : engine.reachable
        ? 'HEALTHY'
        : 'UNREACHABLE';
    const statusClass = !engine.enabled
      ? 'attention'
      : contractMismatch
        ? 'incomplete'
      : engine.reachable
        ? 'complete'
        : 'incomplete';
    const engineName = String(engine.name || 'engine').replace(/_/g, ' ');
    const expectedVersionText = engine.expected_contract_version != null
      ? `v${engine.expected_contract_version}`
      : 'n/a';
    const actualVersionText = engine.contract_version != null ? `v${engine.contract_version}` : 'n/a';
    const versionText = `actual ${actualVersionText} / expected ${expectedVersionText}`;
    const checkedText = engine.last_checked_at ? fmtDate(engine.last_checked_at) : 'never';
    row.className = `list-item ${statusClass}`;
    row.innerHTML = `
      <p class="list-item-title">${engineName} <span class="status-badge ${statusClass}">${statusLabel}</span></p>
      <p class="list-item-meta">Version: ${versionText} • Degraded count: ${Number(engine.degraded_count || 0)} • Checked: ${checkedText}</p>
      ${engine.last_error ? `<p class="list-item-meta">Last error: ${engine.last_error}</p>` : ''}
    `;
    listEl.appendChild(row);
  }
}

export async function load(options = {}) {
  const refreshEngines = Boolean(options.refreshEngines);
  try {
    const [dashboardResult, enginesResult] = await Promise.allSettled([
      fetchJson('/api/dashboard/today'),
      fetchJson(`/api/engines/status${refreshEngines ? '?refresh=true' : ''}`),
    ]);

    if (dashboardResult.status === 'fulfilled') {
      render(dashboardResult.value);
      await loadRecommendationTrend(dashboardResult.value);
    } else {
      throw dashboardResult.reason;
    }

    if (enginesResult.status === 'fulfilled') {
      renderEngineStatus(enginesResult.value);
    } else {
      renderEngineStatus(null, enginesResult.reason?.message || 'unknown error');
    }
  } catch (error) {
    byId('today-generated').textContent = `Dashboard unavailable: ${error.message}`;
    byId('today-context-banner').className = 'context-banner warning';
    byId('today-context-banner').textContent = 'Context readiness unavailable.';
    ['today-total-value', 'today-snapshot-freshness', 'today-concentration', 'today-active-plan'].forEach(id => { const el = byId(id); if (el) el.textContent = '-'; });
    renderRecommendationTrend(null);
    renderEngineStatus(null, error.message);
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
  byId('today-refresh-engines').addEventListener('click', () => load({ refreshEngines: true }).catch(e => writeLog(e.message, null, true)));
  byId('today-refresh-recommendation-trend').addEventListener('click', () => load().catch(e => writeLog(e.message, null, true)));
  byId('today-run-sync').addEventListener('click', runSync);
  byId('today-open-recommendations').addEventListener('click', () => {
    location.hash = 'recommendations';
  });
  byId('today-ask-copilot').addEventListener('click', () => {
    location.hash = 'copilot?dailyReview=1';
  });
  load();
}
