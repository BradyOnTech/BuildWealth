import { fetchJson } from '../lib/api.js';
import { state } from '../lib/state.js';
import { byId, fmtCurrency, fmtPct, fmtDate, writeLog } from '../lib/utils.js';
import { planSelectOptions } from '../lib/components.js';

export const id = 'tracking';
export const label = 'Tracking';
export const icon = '<svg viewBox="0 0 20 20" fill="none" stroke="currentColor" stroke-width="1.6"><path d="M3 17l4-6 4 3 6-10"/><circle cx="17" cy="4" r="2"/></svg>';

export function template() {
  return `
    <div class="view-header"><h2>Plan vs Actual</h2><button class="ghost small" id="reload-tracking">Reload</button></div>
    <p class="hint">Compare your plan assumptions against actual portfolio performance to see if you're on track.</p>
    <div class="filter-bar">
      <label class="field compact-field"><span>Plan</span><select id="tracking-plan"></select></label>
      <button class="primary small" id="run-tracking">Load Tracking</button>
    </div>
    <div id="tracking-content">
      <p class="empty-text">Select a plan and click Load Tracking to see your plan-vs-actual comparison.</p>
    </div>`;
}

function statusClass(status) {
  if (status === 'ahead') return 'complete';
  if (status === 'behind') return 'incomplete';
  if (status === 'on_track') return 'on-track';
  return 'attention';
}

function render(data) {
  const container = byId('tracking-content');

  if (data.status === 'insufficient_data') {
    container.innerHTML = `
      <div class="context-banner warning">
        <strong>Insufficient Data</strong> \u2014 ${data.status_detail}
      </div>`;
    return;
  }

  const driftSign = data.value_drift_usd >= 0 ? '+' : '';
  const returnDriftSign = data.return_drift_pct >= 0 ? '+' : '';
  const contribClass = data.contribution_pace_pct >= 90 ? 'complete' : data.contribution_pace_pct >= 50 ? 'attention' : 'incomplete';

  container.innerHTML = `
    <div class="context-banner ${statusClass(data.status)}">
      <strong>${data.status.replace('_', ' ').toUpperCase()}</strong> \u2014 ${data.status_detail}
    </div>

    <div class="kpi-row">
      <article class="kpi-card">
        <p class="kpi-label">Current Value</p>
        <p class="kpi-value">${fmtCurrency(data.current_value_usd)}</p>
      </article>
      <article class="kpi-card">
        <p class="kpi-label">Projected Value</p>
        <p class="kpi-value">${fmtCurrency(data.projected_value_usd)}</p>
      </article>
      <article class="kpi-card">
        <p class="kpi-label">Value Drift</p>
        <p class="kpi-value ${data.value_drift_usd >= 0 ? 'drift-pos' : 'drift-neg'}">${driftSign}${fmtCurrency(data.value_drift_usd)}</p>
      </article>
      <article class="kpi-card">
        <p class="kpi-label">Tracking Window</p>
        <p class="kpi-value">${data.tracking_window_days}d</p>
      </article>
    </div>

    <h3 class="section-title">Return Comparison</h3>
    <div class="tracking-table">
      <div class="tracking-row header"><span>Metric</span><span>Plan Assumption</span><span>Actual</span><span>Drift</span></div>
      <div class="tracking-row">
        <span>Annualized Return</span>
        <span>${fmtPct(data.expected_annualized_return_pct)}</span>
        <span>${fmtPct(data.actual_annualized_return_pct)}</span>
        <span class="${data.return_drift_pct >= 0 ? 'drift-pos' : 'drift-neg'}">${returnDriftSign}${fmtPct(data.return_drift_pct)}</span>
      </div>
      <div class="tracking-row">
        <span>Portfolio Value</span>
        <span>${fmtCurrency(data.projected_value_usd)}</span>
        <span>${fmtCurrency(data.current_value_usd)}</span>
        <span class="${data.value_drift_usd >= 0 ? 'drift-pos' : 'drift-neg'}">${driftSign}${fmtCurrency(data.value_drift_usd)} (${data.value_drift_pct > 0 ? '+' : ''}${fmtPct(data.value_drift_pct)})</span>
      </div>
    </div>

    <h3 class="section-title">Contribution Tracking</h3>
    <div class="tracking-table">
      <div class="tracking-row header"><span>Metric</span><span>Expected</span><span>Actual</span><span>Pace</span></div>
      <div class="tracking-row">
        <span>Contributions (${data.tracking_window_days}d window)</span>
        <span>${fmtCurrency(data.expected_contributions_usd)}</span>
        <span>${fmtCurrency(data.actual_contributions_usd)}</span>
        <span class="status-badge ${contribClass}">${data.contribution_pace_pct.toFixed(0)}%</span>
      </div>
      <div class="tracking-row">
        <span>Market Growth</span>
        <span>\u2014</span>
        <span class="${data.market_growth_usd >= 0 ? 'drift-pos' : 'drift-neg'}">${data.market_growth_usd >= 0 ? '+' : ''}${fmtCurrency(data.market_growth_usd)}</span>
        <span>\u2014</span>
      </div>
    </div>

    <h3 class="section-title">Window Details</h3>
    <dl class="meta">
      <div><dt>Starting Value</dt><dd>${fmtCurrency(data.starting_value_usd)}</dd></div>
      <div><dt>Window Start</dt><dd>${fmtDate(data.window_start)}</dd></div>
      <div><dt>Window End</dt><dd>${fmtDate(data.window_end)}</dd></div>
      <div><dt>Snapshots Used</dt><dd>${data.snapshot_count}</dd></div>
    </dl>`;
}

async function load() {
  const planId = byId('tracking-plan').value;
  if (!planId) {
    // Try to use active plan
    const active = state.plans.find(p => p.is_active);
    if (!active) {
      byId('tracking-content').innerHTML = '<p class="empty-text">No active plan. Create and activate a plan first.</p>';
      return;
    }
    byId('tracking-plan').value = active.id;
    return load();
  }

  byId('tracking-content').innerHTML = '<p class="empty-text">Loading tracking data...</p>';
  try {
    const data = await fetchJson(`/api/plans/${encodeURIComponent(planId)}/tracking`);
    render(data);
    writeLog('Tracking loaded.', { plan_id: planId, status: data.status });
  } catch (e) {
    byId('tracking-content').innerHTML = `<div class="context-banner critical">Tracking failed: ${e.message}</div>`;
    writeLog(`Tracking failed: ${e.message}`, null, true);
  }
}

export function init() {
  planSelectOptions('tracking-plan', state.copilotPlanId);
  byId('reload-tracking').addEventListener('click', load);
  byId('run-tracking').addEventListener('click', load);
  load();
}
