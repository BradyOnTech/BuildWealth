import { fetchJson } from '../lib/api.js';
import { state } from '../lib/state.js';
import { byId, fmtCurrency, fmtDate, formatNumericInput, parseOptionalNumericField, writeLog } from '../lib/utils.js';
import { recommendationStatusClass, planSelectOptions } from '../lib/components.js';

export const id = 'recommendations';
export const label = 'Inbox';
export const icon = '<svg viewBox="0 0 20 20" fill="none" stroke="currentColor" stroke-width="1.6"><path d="M3 4l3 7h8l3-7"/><path d="M3 11v5a1 1 0 001 1h12a1 1 0 001-1v-5"/><path d="M6 11a2 2 0 002 2h4a2 2 0 002-2"/></svg>';

export function template() {
  return `
    <div class="view-header"><h2>Recommendation Inbox</h2><button class="ghost small" id="reload-recommendations">Reload</button></div>
    <p class="hint">Review, edit, apply, reject, or archive recommendations. Ranked mode prioritizes highest-impact next actions first.</p>
    <div class="filter-bar">
      <label class="field compact-field"><span>Status</span><select id="recommendation-status-filter">
        <option value="proposed" selected>Proposed</option><option value="applied">Applied</option><option value="rejected">Rejected</option><option value="archived">Archived</option><option value="all">All</option>
      </select></label>
      <label class="field compact-field"><span>Plan</span><select id="recommendation-plan-filter"></select></label>
      <label class="field compact-field"><span>Sort</span><select id="recommendation-sort-filter">
        <option value="ranked" selected>Ranked</option>
        <option value="created_at">Newest</option>
      </select></label>
    </div>
    <div class="form-section">
      <div class="view-header"><h3>Closure Analytics</h3><button class="ghost small" id="reload-recommendation-analytics">Refresh Analytics</button></div>
      <p class="hint" id="recommendation-analytics-summary">No closure analytics loaded yet.</p>
      <div id="recommendation-analytics-details" class="item-list"></div>
    </div>
    <div class="form-section">
      <div class="view-header"><h3>Recommendation Factory</h3>
        <div class="header-actions"><button class="ghost small" id="preview-portfolio-risk-recommendations">Preview Portfolio Risk Recommendations</button><button class="primary small" id="create-portfolio-risk-recommendations">Create Recommendations</button></div>
      </div>
      <p class="hint">Turn active portfolio risk alerts into specific, evidence-backed recommendation rows. Preview first; create only when the candidates look useful.</p>
      <div class="settings-grid">
        <label class="field"><span>Generation Limit</span><input type="number" min="1" max="50" step="1" id="recommendation-factory-limit" value="10" /></label>
        <label class="field"><span>Attach to Plan</span><select id="recommendation-factory-plan"></select></label>
      </div>
      <p class="hint" id="recommendation-factory-summary">No generated recommendation preview yet.</p>
      <div id="recommendation-factory-results" class="item-list"></div>
    </div>
    <div class="form-section">
      <div class="view-header"><h3>Outcome Tracker</h3>
        <div class="header-actions"><button class="ghost small" id="recommendation-outcome-next">Log Next Outcome</button></div>
      </div>
      <p class="hint" id="recommendation-outcome-tracker-summary">Learning loop follow-ups load with recommendations.</p>
      <div id="recommendation-outcome-tracker-list" class="item-list"></div>
      <div class="settings-grid" id="recommendation-outcome-form" hidden>
        <label class="field form-span"><span>Tracking Recommendation</span><input type="text" id="recommendation-outcome-current" readonly /></label>
        <label class="field"><span>Realized Future-Value Delta</span><input type="number" step="0.01" id="recommendation-outcome-future" placeholder="2500" /></label>
        <label class="field"><span>Realized Real-Value Delta</span><input type="number" step="0.01" id="recommendation-outcome-real" placeholder="1800" /></label>
        <label class="field"><span>Observed At</span><input type="datetime-local" id="recommendation-outcome-observed-at" /></label>
        <label class="field"><span>Window Days</span><input type="number" min="0" step="1" id="recommendation-outcome-window-days" placeholder="30" /></label>
        <label class="field"><span>Measurement Source</span><input type="text" id="recommendation-outcome-source" placeholder="manual-review" /></label>
        <label class="field form-span"><span>Outcome Note</span><textarea id="recommendation-outcome-note" rows="3" placeholder="What actually happened, and what should the system learn?"></textarea></label>
        <div class="header-actions form-span"><button class="ghost small" id="recommendation-outcome-cancel">Cancel</button><button class="primary small" id="recommendation-outcome-save">Save Outcome</button></div>
      </div>
    </div>
    <div class="table-wrap"><table><thead><tr><th>When</th><th>Status</th><th>Score</th><th>Priority</th><th>Type</th><th>Recommendation</th><th>Plan</th><th>Source</th><th>Actions</th></tr></thead><tbody id="recommendation-body"></tbody></table></div>
    <div class="form-section">
      <div class="view-header"><h3>Pre-Apply Preview</h3></div>
      <p class="hint" id="recommendation-preview-summary">Select a proposed recommendation and click Preview.</p>
      <div id="recommendation-preview-details" class="item-list"></div>
    </div>
    <div class="form-section">
      <div class="view-header"><h3 id="recommendation-form-title">Create Recommendation</h3>
        <div class="header-actions"><button class="ghost small" id="recommendation-cancel-edit" hidden>Cancel</button><button class="primary small" id="recommendation-save">Save</button></div>
      </div>
      <div class="settings-grid">
        <label class="field"><span>Title</span><input type="text" id="recommendation-title" placeholder="Recommendation title" /></label>
        <label class="field"><span>Priority</span><select id="recommendation-priority"><option value="high">High</option><option value="medium" selected>Medium</option><option value="low">Low</option></select></label>
        <label class="field"><span>Type</span><select id="recommendation-type"><option value="general" selected>General</option><option value="workflow_action">Workflow Action</option><option value="plan_settings_update">Plan Settings Update</option></select></label>
        <label class="field"><span>Plan</span><select id="recommendation-plan"></select></label>
        <label class="field"><span>Source</span><input type="text" id="recommendation-source" value="manual-ui" /></label>
        <label class="field form-span"><span>Detail</span><textarea id="recommendation-detail" rows="3" placeholder="Why this recommendation matters."></textarea></label>
        <label class="field form-span"><span>Action Payload (JSON, optional)</span><textarea id="recommendation-action-payload" rows="3" placeholder='{"plan_settings_updates":{"annual_contribution_usd":22000}}'></textarea></label>
      </div>
    </div>`;
}

function resetForm() {
  state.recommendationEditingId = null;
  byId('recommendation-form-title').textContent = 'Create Recommendation';
  byId('recommendation-save').textContent = 'Save';
  byId('recommendation-cancel-edit').hidden = true;
  byId('recommendation-title').value = '';
  byId('recommendation-detail').value = '';
  byId('recommendation-priority').value = 'medium';
  byId('recommendation-type').value = 'general';
  byId('recommendation-source').value = 'manual-ui';
  byId('recommendation-action-payload').value = '';
  byId('recommendation-plan').value = '';
}

function resetPreview() {
  state.recommendationPreview = null;
  byId('recommendation-preview-summary').textContent = 'Select a proposed recommendation and click Preview.';
  byId('recommendation-preview-details').innerHTML = '';
}

function resetClosureAnalytics() {
  state.recommendationClosureAnalytics = null;
  byId('recommendation-analytics-summary').textContent = 'No closure analytics loaded yet.';
  byId('recommendation-analytics-details').innerHTML = '';
}

function resetRecommendationFactory() {
  state.recommendationFactoryResult = null;
  byId('recommendation-factory-summary').textContent = 'No generated recommendation preview yet.';
  byId('recommendation-factory-results').innerHTML = '';
}

function resetOutcomeForm() {
  state.recommendationOutcomeEditingId = null;
  byId('recommendation-outcome-form').hidden = true;
  byId('recommendation-outcome-current').value = '';
  byId('recommendation-outcome-future').value = '';
  byId('recommendation-outcome-real').value = '';
  byId('recommendation-outcome-observed-at').value = '';
  byId('recommendation-outcome-window-days').value = '';
  byId('recommendation-outcome-source').value = 'manual-review';
  byId('recommendation-outcome-note').value = '';
}

function getDecisionClosure(recommendation) {
  const directClosure = recommendation?.decision_closure;
  if (directClosure && typeof directClosure === 'object') return directClosure;
  const payloadClosure = recommendation?.action_payload?.decision_closure;
  return payloadClosure && typeof payloadClosure === 'object' ? payloadClosure : null;
}

function getOutcomeTrackingStatus(recommendation) {
  const closure = getDecisionClosure(recommendation);
  const metrics = closure?.expected_vs_realized && typeof closure.expected_vs_realized === 'object'
    ? closure.expected_vs_realized
    : null;
  const explicitStatus = String(metrics?.status || '').trim().toLowerCase();
  if (explicitStatus) return explicitStatus;
  const realized = closure?.realized_outcome && typeof closure.realized_outcome === 'object'
    ? closure.realized_outcome
    : null;
  if (realized && (
    Number.isFinite(Number(realized.realized_delta_future_value_usd))
    || Number.isFinite(Number(realized.realized_delta_real_value_usd))
  )) return 'measured';
  if (recommendation?.status === 'applied' || recommendation?.status === 'rejected') {
    const expected = closure?.expected_outcome && typeof closure.expected_outcome === 'object'
      ? closure.expected_outcome
      : null;
    return expected ? 'pending_realized' : 'untracked';
  }
  return 'not_closed';
}

function outcomeCandidateSort(a, b) {
  const aPending = getOutcomeTrackingStatus(a) === 'pending_realized';
  const bPending = getOutcomeTrackingStatus(b) === 'pending_realized';
  if (aPending !== bPending) return aPending ? -1 : 1;
  return String(b.created_at || '').localeCompare(String(a.created_at || ''));
}

function outcomeMeta(recommendation) {
  const closure = getDecisionClosure(recommendation) || {};
  const expected = closure.expected_outcome && typeof closure.expected_outcome === 'object' ? closure.expected_outcome : null;
  const realized = closure.realized_outcome && typeof closure.realized_outcome === 'object' ? closure.realized_outcome : null;
  const metrics = closure.expected_vs_realized && typeof closure.expected_vs_realized === 'object' ? closure.expected_vs_realized : null;
  const parts = [`${String(recommendation.status || 'closed').toUpperCase()}`];
  if (expected) {
    const expectedFuture = Number(expected.expected_delta_future_value_usd);
    const expectedReal = Number(expected.expected_delta_real_value_usd);
    const expectedParts = [];
    if (Number.isFinite(expectedFuture)) expectedParts.push(`future ${fmtCurrency(expectedFuture)}`);
    if (Number.isFinite(expectedReal)) expectedParts.push(`real ${fmtCurrency(expectedReal)}`);
    if (expectedParts.length) parts.push(`expected ${expectedParts.join(', ')}`);
  }
  if (realized) {
    const realizedFuture = Number(realized.realized_delta_future_value_usd);
    const realizedReal = Number(realized.realized_delta_real_value_usd);
    const realizedParts = [];
    if (Number.isFinite(realizedFuture)) realizedParts.push(`future ${fmtCurrency(realizedFuture)}`);
    if (Number.isFinite(realizedReal)) realizedParts.push(`real ${fmtCurrency(realizedReal)}`);
    if (realized.observed_at) realizedParts.push(`observed ${fmtDate(realized.observed_at)}`);
    if (realizedParts.length) parts.push(`realized ${realizedParts.join(', ')}`);
  }
  if (metrics) {
    const gapFuture = Number(metrics.future_value_gap_usd);
    const gapReal = Number(metrics.real_value_gap_usd);
    if (Number.isFinite(gapFuture)) parts.push(`future gap ${fmtCurrency(gapFuture)}`);
    if (Number.isFinite(gapReal)) parts.push(`real gap ${fmtCurrency(gapReal)}`);
    if (typeof metrics.future_value_direction_match === 'boolean') {
      parts.push(`direction ${metrics.future_value_direction_match ? 'match' : 'mismatch'}`);
    }
  }
  return parts.join(' • ');
}

function renderOutcomeTracker() {
  const candidates = [...(state.recommendationOutcomeCandidates || [])].sort(outcomeCandidateSort);
  const pending = candidates.filter((recommendation) => getOutcomeTrackingStatus(recommendation) === 'pending_realized');
  const measured = candidates.filter((recommendation) => getOutcomeTrackingStatus(recommendation) === 'measured');
  const untracked = candidates.filter((recommendation) => getOutcomeTrackingStatus(recommendation) === 'untracked');
  const summaryParts = [
    `Pending outcomes: ${pending.length}`,
    `Measured: ${measured.length}`,
    `Untracked closed: ${untracked.length}`,
  ];
  const analyticsSummary = state.recommendationClosureAnalytics?.summary;
  const directionRate = Number(analyticsSummary?.future_value_direction_match_rate_pct);
  if (Number.isFinite(directionRate)) summaryParts.push(`Direction match: ${directionRate.toFixed(1)}%`);
  byId('recommendation-outcome-tracker-summary').textContent = summaryParts.join(' • ');

  const list = byId('recommendation-outcome-tracker-list');
  list.innerHTML = '';
  const visible = pending.length ? pending.slice(0, 6) : measured.slice(0, 4);
  if (!visible.length) {
    list.innerHTML = '<article class="list-item"><p class="list-item-title">No closed recommendation outcomes to track yet.</p><p class="list-item-meta">Apply or reject a recommendation, then record the realized outcome once enough time has passed.</p></article>';
    return;
  }
  for (const recommendation of visible) {
    const article = document.createElement('article');
    article.className = `list-item ${getOutcomeTrackingStatus(recommendation) === 'pending_realized' ? 'attention' : ''}`.trim();
    const title = document.createElement('p');
    title.className = 'list-item-title';
    title.textContent = recommendation.title || recommendation.id || 'Recommendation';
    const meta = document.createElement('p');
    meta.className = 'list-item-meta';
    meta.textContent = outcomeMeta(recommendation);
    const actions = document.createElement('div');
    actions.className = 'table-actions';
    const button = document.createElement('button');
    button.className = getOutcomeTrackingStatus(recommendation) === 'pending_realized' ? 'primary small' : 'ghost small';
    button.textContent = getOutcomeTrackingStatus(recommendation) === 'pending_realized' ? 'Log Outcome' : 'Update Outcome';
    button.addEventListener('click', () => openOutcomeForm(recommendation));
    actions.appendChild(button);
    article.appendChild(title);
    article.appendChild(meta);
    article.appendChild(actions);
    list.appendChild(article);
  }
}

function factoryPlanId() {
  return byId('recommendation-factory-plan')?.value || byId('recommendation-plan-filter')?.value || null;
}

function factoryLimit() {
  const raw = Number(byId('recommendation-factory-limit')?.value || 10);
  if (!Number.isFinite(raw)) return 10;
  return Math.max(1, Math.min(Math.trunc(raw), 50));
}

function candidateMeta(candidate) {
  const payload = candidate?.action_payload && typeof candidate.action_payload === 'object' ? candidate.action_payload : {};
  const generator = payload.generator && typeof payload.generator === 'object' ? payload.generator : {};
  const action = payload.suggested_action && typeof payload.suggested_action === 'object' ? payload.suggested_action : {};
  const parts = [
    `Priority ${String(candidate?.priority || 'medium').toUpperCase()}`,
    `Source ${candidate?.source || 'generator:portfolio_risk'}`,
  ];
  const severity = String(generator.severity || '').trim();
  if (severity) parts.push(`Signal ${severity}`);
  const amount = Number(action.estimated_rebalance_usd);
  if (Number.isFinite(amount) && amount > 0) parts.push(`estimated rebalance ${fmtCurrency(amount)}`);
  if (generator.dedupe_key) parts.push(`dedupe ${generator.dedupe_key}`);
  return parts.join(' • ');
}

function renderRecommendationFactoryResult(payload) {
  const result = payload && typeof payload === 'object' ? payload : {};
  state.recommendationFactoryResult = result;
  const candidates = Array.isArray(result.candidates) ? result.candidates : [];
  const created = Array.isArray(result.created) ? result.created : [];
  const skipped = Array.isArray(result.skipped) ? result.skipped : [];
  const dryRun = result.dry_run !== false;
  const generatedCount = Number(result.generated_count || 0);
  const skippedCount = Number(result.skipped_count || skipped.length || 0);
  const modeLabel = dryRun ? 'Preview' : 'Created';
  byId('recommendation-factory-summary').textContent = `${modeLabel}: ${generatedCount} recommendation${generatedCount === 1 ? '' : 's'} • skipped ${skippedCount}.`;

  const cards = [];
  for (const candidate of candidates.slice(0, 8)) {
    cards.push(`<article class="list-item"><p class="list-item-title">${candidate.title || 'Generated recommendation'}</p><p class="list-item-meta">${candidateMeta(candidate)}</p><p class="list-item-meta">${candidate.detail || ''}</p></article>`);
  }
  for (const item of created.slice(0, 8)) {
    cards.push(`<article class="list-item"><p class="list-item-title">Created: ${item.title || item.id || 'Recommendation'}</p><p class="list-item-meta">${item.id || ''} • ${String(item.priority || 'medium').toUpperCase()} • ${item.source || 'generator:portfolio_risk'}</p></article>`);
  }
  for (const item of skipped.slice(0, 6)) {
    cards.push(`<article class="list-item attention"><p class="list-item-title">Skipped: ${item.title || item.signal_key || 'Portfolio risk signal'}</p><p class="list-item-meta">${item.reason || 'skipped'}${item.dedupe_key ? ` • ${item.dedupe_key}` : ''}</p></article>`);
  }
  byId('recommendation-factory-results').innerHTML = cards.length
    ? cards.join('')
    : '<article class="list-item"><p class="list-item-title">No portfolio risk signals need recommendations.</p><p class="list-item-meta">Risk alerts are either clear or already have active generated recommendations.</p></article>';
}

function renderClosureAnalytics(payload) {
  state.recommendationClosureAnalytics = payload && typeof payload === 'object' ? payload : null;
  const summary = payload && typeof payload.summary === 'object' ? payload.summary : {};
  const calibrationSummary = payload && typeof payload.calibration_summary === 'object' ? payload.calibration_summary : {};
  const count = Number(payload?.count || 0);
  const measured = Number(summary?.measured_count || 0);
  const coverage = Number(summary?.realized_coverage_pct || 0);
  const directionRate = Number(summary?.future_value_direction_match_rate_pct);
  const meanAbsError = Number(summary?.mean_future_value_abs_error_usd);
  const coverageLabel = Number.isFinite(coverage) ? coverage.toFixed(1) : '0.0';
  const summaryParts = [
    `Closed tracked: ${count}`,
    `Measured: ${measured}`,
    `Realized coverage: ${coverageLabel}%`,
  ];
  if (Number.isFinite(directionRate)) summaryParts.push(`Direction match: ${directionRate.toFixed(1)}%`);
  if (Number.isFinite(meanAbsError)) summaryParts.push(`Mean abs error: ${fmtCurrency(meanAbsError)}`);
  if (calibrationSummary?.future_value_bias) {
    summaryParts.push(`Bias: ${String(calibrationSummary.future_value_bias).replace('_', ' ')}`);
  }
  byId('recommendation-analytics-summary').textContent = summaryParts.join(' • ');

  const fmtPct = (value) => {
    const num = Number(value);
    return Number.isFinite(num) ? `${num.toFixed(1)}%` : 'n/a';
  };
  const fmtMoney = (value) => {
    const num = Number(value);
    return Number.isFinite(num) ? fmtCurrency(num) : 'n/a';
  };

  const cards = [];
  const byStatus = Array.isArray(payload?.by_status) ? payload.by_status : [];
  if (byStatus.length) {
    cards.push(`<article class="list-item"><p class="list-item-title">By Status</p><p class="list-item-meta">${byStatus.slice(0, 4).map((row) => `${row.key}: ${row.count}`).join(' • ')}</p></article>`);
  }
  const byType = Array.isArray(payload?.by_type) ? payload.by_type : [];
  if (byType.length) {
    cards.push(`<article class="list-item"><p class="list-item-title">By Type</p><p class="list-item-meta">${byType.slice(0, 4).map((row) => `${row.key}: ${row.count}`).join(' • ')}</p></article>`);
  }
  const bySource = Array.isArray(payload?.by_source) ? payload.by_source : [];
  if (bySource.length) {
    cards.push(`<article class="list-item"><p class="list-item-title">By Source</p><p class="list-item-meta">${bySource.slice(0, 4).map((row) => `${row.key}: ${row.count}`).join(' • ')}</p></article>`);
  }
  const calibrationByType = Array.isArray(payload?.calibration_by_type) ? payload.calibration_by_type : [];
  if (calibrationByType.length) {
    cards.push(`<article class="list-item"><p class="list-item-title">Calibration by Type</p><p class="list-item-meta">${calibrationByType.slice(0, 3).map((row) => `${row.key}: measured ${row.measured_count}/${row.count}, match ${fmtPct(row.future_value_direction_match_rate_pct)}, MAE ${fmtMoney(row.mean_future_value_abs_error_usd)}`).join(' • ')}</p></article>`);
  }
  const calibrationBySource = Array.isArray(payload?.calibration_by_source) ? payload.calibration_by_source : [];
  if (calibrationBySource.length) {
    cards.push(`<article class="list-item"><p class="list-item-title">Calibration by Source</p><p class="list-item-meta">${calibrationBySource.slice(0, 3).map((row) => `${row.key}: measured ${row.measured_count}/${row.count}, match ${fmtPct(row.future_value_direction_match_rate_pct)}, MAE ${fmtMoney(row.mean_future_value_abs_error_usd)}`).join(' • ')}</p></article>`);
  }
  const calibrationWindows = Array.isArray(payload?.calibration_windows) ? payload.calibration_windows : [];
  if (calibrationWindows.length) {
    cards.push(`<article class="list-item"><p class="list-item-title">Calibration Trend Windows</p><p class="list-item-meta">${calibrationWindows.slice(0, 3).map((row) => `${row.window || row.key}: measured ${row.measured_count}/${row.count}, match ${fmtPct(row.future_value_direction_match_rate_pct)}, MAE ${fmtMoney(row.mean_future_value_abs_error_usd)}`).join(' • ')}</p></article>`);
  }

  byId('recommendation-analytics-details').innerHTML = cards.length
    ? cards.join('')
    : '<article class="list-item"><p class="list-item-title">No closure analytics yet.</p></article>';
}

function renderPreview(result) {
  state.recommendationPreview = result;
  const preview = result && typeof result.preview === 'object' ? result.preview : {};
  const recommendation = result && typeof result.recommendation === 'object' ? result.recommendation : {};
  const actionPreview = preview && typeof preview.action_preview === 'object' ? preview.action_preview : {};
  const scenarioPreview = preview && typeof preview.scenario_diff_preview === 'object' ? preview.scenario_diff_preview : {};
  const warnings = Array.isArray(preview?.warnings) ? preview.warnings : [];
  const suggestedSymbols = Array.isArray(result?.suggested_research_symbols) ? result.suggested_research_symbols : [];

  const status = String(preview.status || 'unknown');
  const recommendationType = String(preview.recommendation_type || recommendation.recommendation_type || 'general');
  const title = String(recommendation.title || recommendation.id || 'Recommendation');
  byId('recommendation-preview-summary').textContent = `${title} • ${recommendationType} • preview status ${status}.`;

  const cards = [];
  if (actionPreview?.decision_log_summary) {
    cards.push(`<article class="list-item"><p class="list-item-title">Action Preview</p><p class="list-item-meta">${actionPreview.decision_log_summary}</p></article>`);
  }

  if (scenarioPreview && typeof scenarioPreview === 'object') {
    const scenarioStatus = String(scenarioPreview.status || 'unknown');
    const deltas = Array.isArray(scenarioPreview.scenario_deltas) ? scenarioPreview.scenario_deltas : [];
    const baseline = deltas.find((item) => item && item.label === 'baseline') || deltas[0];
    if (scenarioStatus === 'captured' && baseline && typeof baseline === 'object') {
      cards.push(`<article class="list-item"><p class="list-item-title">Scenario Delta</p><p class="list-item-meta">Baseline future-value delta ${fmtCurrency(Number(baseline.delta_future_value_usd || 0))}, real-value delta ${fmtCurrency(Number(baseline.delta_real_value_usd || 0))}.</p></article>`);
    } else {
      const reason = String(scenarioPreview.reason || '').trim();
      cards.push(`<article class="list-item"><p class="list-item-title">Scenario Preview</p><p class="list-item-meta">${scenarioStatus}${reason ? ` • ${reason}` : ''}</p></article>`);
    }
  }

  if (suggestedSymbols.length) {
    cards.push(`<article class="list-item"><p class="list-item-title">Suggested Research Symbols</p><p class="list-item-meta">${suggestedSymbols.join(', ')}</p></article>`);
  }

  if (warnings.length) {
    for (const warning of warnings.slice(0, 5)) {
      cards.push(`<article class="list-item attention"><p class="list-item-title">Warning</p><p class="list-item-meta">${warning}</p></article>`);
    }
  }

  byId('recommendation-preview-details').innerHTML = cards.length
    ? cards.join('')
    : '<article class="list-item"><p class="list-item-title">No preview details.</p></article>';
}

function formPayload() {
  const title = byId('recommendation-title').value.trim();
  const detail = byId('recommendation-detail').value.trim();
  if (!title || !detail) throw new Error('Title and detail are required.');
  const raw = byId('recommendation-action-payload').value.trim();
  let actionPayload = {};
  if (raw) { const p = JSON.parse(raw); if (!p || typeof p !== 'object' || Array.isArray(p)) throw new Error('Must be JSON object.'); actionPayload = p; }
  return { title, detail, priority: byId('recommendation-priority').value || 'medium', recommendation_type: byId('recommendation-type').value || 'general', source: byId('recommendation-source').value.trim() || 'manual-ui', plan_id: byId('recommendation-plan').value || null, action_payload: actionPayload };
}

function renderTable() {
  const tbody = byId('recommendation-body');
  tbody.innerHTML = '';
  if (!state.recommendations.length) { tbody.innerHTML = '<tr><td colspan="9">No recommendations for this filter.</td></tr>'; return; }
  for (const r of state.recommendations) {
    const tr = document.createElement('tr');
    const statusBadge = `<span class="status-badge ${recommendationStatusClass(r.status)}">${String(r.status || 'proposed').toUpperCase()}</span>`;
    const score = r.score && typeof r.score === 'object' ? r.score : null;
    const scoreTotal = Number(score?.total);
    const scoreRank = Number(score?.rank);
    const scoreCell = Number.isFinite(scoreTotal)
      ? `${scoreTotal.toFixed(1)}${Number.isFinite(scoreRank) && scoreRank > 0 ? ` (#${Math.trunc(scoreRank)})` : ''}`
      : '-';
    let recHtml = `<p class="rec-title">${r.title || '-'}</p><p class="rec-detail">${r.detail || ''}</p>`;
    if (score && Number.isFinite(Number(score.impact)) && Number.isFinite(Number(score.confidence)) && Number.isFinite(Number(score.urgency)) && Number.isFinite(Number(score.reversibility))) {
      recHtml += `<p class="rec-detail">Score breakdown: impact ${Number(score.impact).toFixed(1)} • confidence ${Number(score.confidence).toFixed(1)} • urgency ${Number(score.urgency).toFixed(1)} • reversibility ${Number(score.reversibility).toFixed(1)}</p>`;
      const calibration = score.calibration && typeof score.calibration === 'object' ? score.calibration : null;
      if (calibration && calibration.applied) {
        const confidenceDelta = Number(calibration.confidence_delta);
        const sourceBucket = calibration.source && typeof calibration.source === 'object' ? calibration.source : null;
        const typeBucket = calibration.type && typeof calibration.type === 'object' ? calibration.type : null;
        const sourceCount = Number(sourceBucket?.measured_count || 0);
        const sourceRate = Number(sourceBucket?.future_value_direction_match_rate_pct);
        const typeCount = Number(typeBucket?.measured_count || 0);
        const typeRate = Number(typeBucket?.future_value_direction_match_rate_pct);
        const calibrationParts = [];
        if (Number.isFinite(confidenceDelta)) calibrationParts.push(`confidence ${confidenceDelta >= 0 ? '+' : ''}${confidenceDelta.toFixed(1)}`);
        if (sourceCount >= 2 && Number.isFinite(sourceRate)) calibrationParts.push(`${calibration.source_key} ${sourceRate.toFixed(1)}% match over ${sourceCount} outcomes`);
        else if (typeCount >= 2 && Number.isFinite(typeRate)) calibrationParts.push(`${calibration.type_key} ${typeRate.toFixed(1)}% match over ${typeCount} outcomes`);
        if (calibrationParts.length) recHtml += `<p class="rec-detail">Learning loop: ${calibrationParts.join(' • ')}</p>`;
      }
      if (Array.isArray(score.reasons) && score.reasons.length) {
        recHtml += `<p class="rec-detail">Drivers: ${score.reasons.slice(0, 3).join(' • ')}</p>`;
      }
    }
    if (r.resolution_note) recHtml += `<p class="rec-detail">Resolution: ${r.resolution_note}</p>`;
    const generator = r.action_payload?.generator;
    if (generator && typeof generator === 'object') {
      const generatorParts = [];
      const generatorId = String(generator.id || '').trim();
      const signalType = String(generator.signal_type || '').trim().replaceAll('_', ' ');
      const signalKey = String(generator.signal_key || '').trim();
      const severity = String(generator.severity || '').trim();
      if (generatorId === 'portfolio_risk_recommendation_factory') generatorParts.push('Generated from portfolio risk alert');
      else if (generatorId) generatorParts.push(`Generated by ${generatorId}`);
      if (signalType) generatorParts.push(signalType);
      if (severity) generatorParts.push(`severity ${severity}`);
      if (signalKey) generatorParts.push(`signal ${signalKey}`);
      if (generatorParts.length) recHtml += `<p class="rec-detail">Factory: ${generatorParts.join(' • ')}</p>`;
    }
    const suggestedAction = r.action_payload?.suggested_action;
    if (suggestedAction && typeof suggestedAction === 'object') {
      const actionParts = [];
      const kind = String(suggestedAction.kind || '').trim().replaceAll('_', ' ');
      const subject = String(suggestedAction.subject || '').trim();
      const amount = Number(suggestedAction.estimated_rebalance_usd);
      const currentValue = Number(suggestedAction.current_value);
      const threshold = Number(suggestedAction.threshold);
      const unit = String(suggestedAction.unit || '').trim();
      if (kind) actionParts.push(kind);
      if (subject) actionParts.push(subject);
      if (Number.isFinite(amount) && amount > 0) actionParts.push(`estimated rebalance ${fmtCurrency(amount)}`);
      if (Number.isFinite(currentValue) && Number.isFinite(threshold)) {
        const suffix = unit === 'pct' ? '%' : '';
        actionParts.push(`current ${currentValue.toFixed(unit === 'pct' ? 1 : 2)}${suffix} vs threshold ${threshold.toFixed(unit === 'pct' ? 1 : 2)}${suffix}`);
      }
      if (actionParts.length) recHtml += `<p class="rec-detail">Suggested action: ${actionParts.join(' • ')}</p>`;
    }
    const evidence = r.action_payload?.evidence;
    if (evidence) {
      const parts = [];
      if (evidence.workflow_id) parts.push(`Workflow ${evidence.workflow_id}`);
      if (evidence.generated_at) parts.push(`Generated ${fmtDate(evidence.generated_at)}`);
      if (evidence.snapshot_as_of) parts.push(`Snapshot ${fmtDate(evidence.snapshot_as_of)}`);
      if (Array.isArray(evidence.data_keys) && evidence.data_keys.length) parts.push(`Data: ${evidence.data_keys.slice(0, 4).join(', ')}`);
      if (parts.length) recHtml += `<p class="rec-detail">Evidence: ${parts.join(' \u2022 ')}</p>`;
      const citation = evidence.citation_quality && typeof evidence.citation_quality === 'object' ? evidence.citation_quality : null;
      if (citation) {
        const status = String(citation.status || 'unknown');
        const cited = Array.isArray(citation.cited_symbols) ? citation.cited_symbols : [];
        const missing = Array.isArray(citation.missing_dossier_symbols) ? citation.missing_dossier_symbols : [];
        const citationParts = [`Citation ${status}`];
        if (cited.length) citationParts.push(`cited ${cited.join(', ')}`);
        if (missing.length) citationParts.push(`missing dossier ${missing.join(', ')}`);
        if (citation.required) citationParts.push('required');
        recHtml += `<p class="rec-detail">${citationParts.join(' \u2022 ')}</p>`;
      }
    }
    const suggestedSymbols = Array.isArray(r.action_payload?.suggested_research_symbols)
      ? r.action_payload.suggested_research_symbols
      : [];
    if (suggestedSymbols.length) {
      recHtml += `<p class="rec-detail">Suggested symbols: ${suggestedSymbols.join(', ')}</p>`;
    }
    const researchBridge = r.action_payload?.research_bridge;
    if (researchBridge && typeof researchBridge === 'object') {
      const bridgeStatus = String(researchBridge.status || '').trim() || 'unknown';
      const bridgeTemplate = String(researchBridge.template_id || '').trim();
      const pinnedSymbols = Array.isArray(researchBridge.pinned_symbols) ? researchBridge.pinned_symbols : [];
      const bridgeParts = [`Research bridge ${bridgeStatus}`];
      if (bridgeTemplate) bridgeParts.push(`template ${bridgeTemplate}`);
      if (pinnedSymbols.length) bridgeParts.push(`symbols ${pinnedSymbols.join(', ')}`);
      if (researchBridge.reason) bridgeParts.push(`reason: ${researchBridge.reason}`);
      recHtml += `<p class="rec-detail">${bridgeParts.join(' \u2022 ')}</p>`;
    }
    const decisionClosure = r.action_payload?.decision_closure;
    if (decisionClosure && typeof decisionClosure === 'object') {
      const closureWhen = decisionClosure.applied_at || decisionClosure.rejected_at;
      const closureStatus = String(decisionClosure.decision_status || r.status || '').toUpperCase();
      const closureParts = [];
      if (closureStatus) closureParts.push(closureStatus);
      if (closureWhen) closureParts.push(fmtDate(closureWhen));
      if (decisionClosure.rationale) closureParts.push(`rationale: ${decisionClosure.rationale}`);
      if (decisionClosure.reason) closureParts.push(`reason: ${decisionClosure.reason}`);
      if (closureParts.length) recHtml += `<p class="rec-detail">Closure: ${closureParts.join(' \u2022 ')}</p>`;

      const expectedOutcome = decisionClosure.expected_outcome && typeof decisionClosure.expected_outcome === 'object'
        ? decisionClosure.expected_outcome
        : null;
      if (expectedOutcome) {
        const expectedFuture = Number(expectedOutcome.expected_delta_future_value_usd);
        const expectedReal = Number(expectedOutcome.expected_delta_real_value_usd);
        const expectedParts = [];
        if (Number.isFinite(expectedFuture)) expectedParts.push(`future ${fmtCurrency(expectedFuture)}`);
        if (Number.isFinite(expectedReal)) expectedParts.push(`real ${fmtCurrency(expectedReal)}`);
        if (expectedParts.length) recHtml += `<p class="rec-detail">Expected outcome: ${expectedParts.join(' • ')}</p>`;
      }
      const realizedOutcome = decisionClosure.realized_outcome && typeof decisionClosure.realized_outcome === 'object'
        ? decisionClosure.realized_outcome
        : null;
      if (realizedOutcome) {
        const realizedFuture = Number(realizedOutcome.realized_delta_future_value_usd);
        const realizedReal = Number(realizedOutcome.realized_delta_real_value_usd);
        const realizedParts = [];
        if (Number.isFinite(realizedFuture)) realizedParts.push(`future ${fmtCurrency(realizedFuture)}`);
        if (Number.isFinite(realizedReal)) realizedParts.push(`real ${fmtCurrency(realizedReal)}`);
        if (realizedOutcome.observed_at) realizedParts.push(`observed ${fmtDate(realizedOutcome.observed_at)}`);
        if (realizedOutcome.measurement_source) realizedParts.push(`source ${realizedOutcome.measurement_source}`);
        if (realizedParts.length) recHtml += `<p class="rec-detail">Realized outcome: ${realizedParts.join(' • ')}</p>`;
      }
      const expectedVsRealized = decisionClosure.expected_vs_realized && typeof decisionClosure.expected_vs_realized === 'object'
        ? decisionClosure.expected_vs_realized
        : null;
      if (expectedVsRealized) {
        const trackingStatus = String(expectedVsRealized.status || '').trim();
        const gapFuture = Number(expectedVsRealized.future_value_gap_usd);
        const gapReal = Number(expectedVsRealized.real_value_gap_usd);
        const trackingParts = [];
        if (trackingStatus) trackingParts.push(trackingStatus);
        if (Number.isFinite(gapFuture)) trackingParts.push(`future gap ${fmtCurrency(gapFuture)}`);
        if (Number.isFinite(gapReal)) trackingParts.push(`real gap ${fmtCurrency(gapReal)}`);
        if (typeof expectedVsRealized.future_value_direction_match === 'boolean') {
          trackingParts.push(`direction ${expectedVsRealized.future_value_direction_match ? 'match' : 'mismatch'}`);
        }
        if (trackingParts.length) recHtml += `<p class="rec-detail">Outcome tracking: ${trackingParts.join(' • ')}</p>`;
      }

      const scenarioPreview = decisionClosure.scenario_diff_preview;
      if (scenarioPreview && typeof scenarioPreview === 'object') {
        const previewStatus = String(scenarioPreview.status || 'unknown');
        if (previewStatus === 'captured') {
          const deltas = Array.isArray(scenarioPreview.scenario_deltas) ? scenarioPreview.scenario_deltas : [];
          const baseline = deltas.find((item) => item && item.label === 'baseline') || deltas[0];
          if (baseline && typeof baseline === 'object') {
            recHtml += `<p class="rec-detail">Scenario preview: ${fmtCurrency(Number(baseline.delta_future_value_usd || 0))} future-value delta (${baseline.label || 'baseline'})</p>`;
          } else {
            recHtml += '<p class="rec-detail">Scenario preview: captured.</p>';
          }
        } else if (scenarioPreview.reason) {
          recHtml += `<p class="rec-detail">Scenario preview: ${previewStatus} (${scenarioPreview.reason})</p>`;
        } else {
          recHtml += `<p class="rec-detail">Scenario preview: ${previewStatus}</p>`;
        }
      }
    }
    const actionsCell = document.createElement('td');
    const wrap = document.createElement('div');
    wrap.className = 'table-actions';
    if (r.status === 'proposed') {
      wrap.innerHTML = `<button class="ghost small" data-action="preview">Preview</button><button class="primary small" data-action="apply">Apply</button><button class="ghost small" data-action="reject">Reject</button>`;
      wrap.querySelector('[data-action="preview"]').addEventListener('click', () => previewItem(r));
      wrap.querySelector('[data-action="apply"]').addEventListener('click', () => applyItem(r));
      wrap.querySelector('[data-action="reject"]').addEventListener('click', () => rejectItem(r));
    }
    if (r.status !== 'archived') {
      if (r.status === 'applied' || r.status === 'rejected') {
        const outcomeBtn = document.createElement('button'); outcomeBtn.className = 'ghost small'; outcomeBtn.textContent = 'Log Outcome';
        outcomeBtn.addEventListener('click', () => logOutcomeItem(r)); wrap.appendChild(outcomeBtn);
      }
      const editBtn = document.createElement('button'); editBtn.className = 'ghost small'; editBtn.textContent = 'Edit';
      editBtn.addEventListener('click', () => editItem(r)); wrap.appendChild(editBtn);
      const archBtn = document.createElement('button'); archBtn.className = 'ghost small'; archBtn.textContent = 'Archive';
      archBtn.addEventListener('click', () => archiveItem(r)); wrap.appendChild(archBtn);
    }
    actionsCell.appendChild(wrap);
    tr.innerHTML = `<td>${fmtDate(r.created_at)}</td><td>${statusBadge}</td><td>${scoreCell}</td><td>${String(r.priority || 'medium').toUpperCase()}</td><td>${r.recommendation_type || 'general'}</td><td>${recHtml}</td><td>${r.plan_id || 'active'}</td><td>${r.source || '-'}</td>`;
    tr.appendChild(actionsCell);
    tbody.appendChild(tr);
  }
}

function mergeRecommendationsById(recommendationGroups) {
  const merged = new Map();
  for (const group of recommendationGroups) {
    if (!Array.isArray(group)) continue;
    for (const recommendation of group) {
      if (recommendation?.id) merged.set(recommendation.id, recommendation);
    }
  }
  return [...merged.values()];
}

async function loadClosureAnalytics() {
  const plan = byId('recommendation-plan-filter').value || '';
  const params = new URLSearchParams();
  params.set('limit', '200');
  params.set('statuses', 'applied,rejected');
  params.set('include_pending_realized', 'true');
  if (plan) params.set('plan_id', plan);
  const payload = await fetchJson(`/api/recommendations/closure-analytics?${params.toString()}`);
  renderClosureAnalytics(payload && typeof payload === 'object' ? payload : {});
  renderOutcomeTracker();
}

async function runPortfolioRiskRecommendationFactory(dryRun = true) {
  const payload = {
    dry_run: dryRun,
    plan_id: factoryPlanId(),
    limit: factoryLimit(),
  };
  if (!payload.plan_id) payload.plan_id = null;
  writeLog(dryRun ? 'Previewing portfolio risk recommendations...' : 'Creating portfolio risk recommendations...', payload);
  const result = await fetchJson('/api/recommendations/generate/portfolio-risk', {
    method: 'POST',
    headers: { 'content-type': 'application/json' },
    body: JSON.stringify(payload),
  });
  renderRecommendationFactoryResult(result);
  if (!dryRun) {
    writeLog('Portfolio risk recommendation generation complete.', {
      generated_count: result?.generated_count || 0,
      skipped_count: result?.skipped_count || 0,
    });
    await load();
  }
}

async function load() {
  const status = byId('recommendation-status-filter').value || 'proposed';
  const plan = byId('recommendation-plan-filter').value || '';
  const sort = byId('recommendation-sort-filter').value || 'ranked';
  state.recommendationFilterStatus = status;
  state.recommendationFilterPlanId = plan;
  state.recommendationSort = sort;
  const params = new URLSearchParams();
  params.set('limit', '200');
  params.set('sort', sort);
  if (status === 'all') params.set('include_archived', 'true');
  else params.set('status', status);
  if (plan) params.set('plan_id', plan);
  const analyticsParams = new URLSearchParams();
  analyticsParams.set('limit', '200');
  analyticsParams.set('statuses', 'applied,rejected');
  analyticsParams.set('include_pending_realized', 'true');
  if (plan) analyticsParams.set('plan_id', plan);
  const appliedParams = new URLSearchParams();
  appliedParams.set('limit', '100');
  appliedParams.set('sort', 'created_at');
  appliedParams.set('status', 'applied');
  if (plan) appliedParams.set('plan_id', plan);
  const rejectedParams = new URLSearchParams(appliedParams);
  rejectedParams.set('status', 'rejected');
  const [recommendationsPayload, analyticsPayload, appliedPayload, rejectedPayload] = await Promise.all([
    fetchJson(`/api/recommendations?${params}`),
    fetchJson(`/api/recommendations/closure-analytics?${analyticsParams.toString()}`),
    fetchJson(`/api/recommendations?${appliedParams.toString()}`),
    fetchJson(`/api/recommendations?${rejectedParams.toString()}`),
  ]);
  state.recommendations = Array.isArray(recommendationsPayload) ? recommendationsPayload : [];
  state.recommendationOutcomeCandidates = mergeRecommendationsById([appliedPayload, rejectedPayload]);
  renderClosureAnalytics(analyticsPayload && typeof analyticsPayload === 'object' ? analyticsPayload : {});
  renderOutcomeTracker();
  renderTable();
}

function editItem(r) {
  state.recommendationEditingId = r.id;
  byId('recommendation-form-title').textContent = `Edit: ${r.id}`;
  byId('recommendation-save').textContent = 'Update';
  byId('recommendation-cancel-edit').hidden = false;
  byId('recommendation-title').value = r.title || '';
  byId('recommendation-detail').value = r.detail || '';
  byId('recommendation-priority').value = r.priority || 'medium';
  byId('recommendation-type').value = r.recommendation_type || 'general';
  byId('recommendation-source').value = r.source || 'manual-ui';
  byId('recommendation-plan').value = r.plan_id || '';
  byId('recommendation-action-payload').value = JSON.stringify(r.action_payload || {}, null, 2);
}

async function save() {
  let payload;
  try { payload = formPayload(); } catch (e) { writeLog(e.message, null, true); return; }
  const editId = state.recommendationEditingId;
  writeLog(editId ? `Updating ${editId}...` : 'Creating...', payload);
  try {
    if (editId) await fetchJson(`/api/recommendations/${encodeURIComponent(editId)}`, { method: 'PUT', headers: { 'content-type': 'application/json' }, body: JSON.stringify(payload) });
    else await fetchJson('/api/recommendations', { method: 'POST', headers: { 'content-type': 'application/json' }, body: JSON.stringify(payload) });
    resetForm(); await load();
  } catch (e) { writeLog(`Save failed: ${e.message}`, null, true); }
}

async function applyItem(r) {
  const rationale = window.prompt('Rationale for applying (optional):', '');
  if (rationale === null) return;
  const payload = { plan_id: r.plan_id || byId('recommendation-plan').value || state.currentPlanId || null, rationale: rationale.trim(), decision_status: 'accepted' };
  const result = await fetchJson(`/api/recommendations/${encodeURIComponent(r.id)}/apply`, { method: 'POST', headers: { 'content-type': 'application/json' }, body: JSON.stringify(payload) });
  if (result.plan?.id === state.currentPlanId) state.currentPlanDetail = result.plan;
  resetPreview();
  writeLog('Applied.', { id: r.id, decision_closure: result.decision_closure || null, research_bridge: result.research_bridge || null }); await load();
}

async function previewItem(r) {
  const payload = {
    plan_id: r.plan_id || byId('recommendation-plan').value || state.currentPlanId || null,
    capture_scenario_diff: true,
    decision_status: 'accepted',
  };
  const result = await fetchJson(`/api/recommendations/${encodeURIComponent(r.id)}/preview`, { method: 'POST', headers: { 'content-type': 'application/json' }, body: JSON.stringify(payload) });
  renderPreview(result);
  writeLog('Recommendation preview generated.', { id: r.id, status: result?.preview?.status, scenario_status: result?.preview?.scenario_diff_preview?.status || null });
}

async function rejectItem(r) {
  const reason = window.prompt('Reason (optional):', '');
  if (reason === null) return;
  const result = await fetchJson(`/api/recommendations/${encodeURIComponent(r.id)}/reject`, { method: 'POST', headers: { 'content-type': 'application/json' }, body: JSON.stringify({ reason: reason.trim() }) });
  resetPreview();
  writeLog('Rejected.', { id: r.id, decision_closure: result.decision_closure || null }); await load();
}

function toLocalDateTimeInput(value) {
  const date = value ? new Date(value) : new Date();
  if (Number.isNaN(date.getTime())) return '';
  const localDate = new Date(date.getTime() - (date.getTimezoneOffset() * 60000));
  return localDate.toISOString().slice(0, 16);
}

function openOutcomeForm(recommendation) {
  const closure = getDecisionClosure(recommendation) || {};
  const realized = closure.realized_outcome && typeof closure.realized_outcome === 'object'
    ? closure.realized_outcome
    : {};
  state.recommendationOutcomeEditingId = recommendation.id;
  byId('recommendation-outcome-current').value = `${recommendation.title || recommendation.id || 'Recommendation'} (${String(recommendation.status || 'closed').toUpperCase()})`;
  byId('recommendation-outcome-future').value = formatNumericInput(Number(realized.realized_delta_future_value_usd));
  byId('recommendation-outcome-real').value = formatNumericInput(Number(realized.realized_delta_real_value_usd));
  byId('recommendation-outcome-observed-at').value = toLocalDateTimeInput(realized.observed_at || new Date().toISOString());
  byId('recommendation-outcome-window-days').value = Number.isFinite(Number(realized.observation_window_days)) ? String(Math.trunc(Number(realized.observation_window_days))) : '';
  byId('recommendation-outcome-source').value = String(realized.measurement_source || 'manual-review');
  byId('recommendation-outcome-note').value = String(realized.note || '');
  byId('recommendation-outcome-form').hidden = false;
  byId('recommendation-outcome-form').scrollIntoView({ behavior: 'smooth', block: 'nearest' });
}

function outcomeFormPayload(recommendation) {
  const payload = {
    plan_id: recommendation.plan_id || byId('recommendation-plan').value || state.currentPlanId || null,
    measurement_source: byId('recommendation-outcome-source').value.trim() || 'manual-review',
    note: byId('recommendation-outcome-note').value.trim(),
  };
  const futureValue = parseOptionalNumericField(byId('recommendation-outcome-future').value, 'Realized future-value delta');
  const realValue = parseOptionalNumericField(byId('recommendation-outcome-real').value, 'Realized real-value delta');
  if (futureValue.present) payload.realized_delta_future_value_usd = futureValue.value;
  if (realValue.present) payload.realized_delta_real_value_usd = realValue.value;
  if (!futureValue.present && !realValue.present) throw new Error('Enter at least one realized outcome delta.');

  const windowDays = parseOptionalNumericField(byId('recommendation-outcome-window-days').value, 'Observation window days', true);
  if (windowDays.present) {
    if (windowDays.value < 0) throw new Error('Observation window days must be zero or greater.');
    payload.observation_window_days = windowDays.value;
  }
  const observedAt = byId('recommendation-outcome-observed-at').value.trim();
  if (observedAt) {
    const observedDate = new Date(observedAt);
    if (Number.isNaN(observedDate.getTime())) throw new Error('Observed at must be a valid date and time.');
    payload.observed_at = observedDate.toISOString();
  }
  return payload;
}

async function logOutcomeItem(recommendation) {
  openOutcomeForm(recommendation);
}

async function saveOutcomeForm() {
  const recommendationId = state.recommendationOutcomeEditingId;
  const recommendation = [...(state.recommendationOutcomeCandidates || []), ...(state.recommendations || [])]
    .find((item) => item?.id === recommendationId);
  if (!recommendation) {
    writeLog('Choose a recommendation before saving an outcome.', null, true);
    return;
  }
  let payload;
  try {
    payload = outcomeFormPayload(recommendation);
  } catch (error) {
    writeLog(error.message, null, true);
    return;
  }

  const result = await fetchJson(`/api/recommendations/${encodeURIComponent(recommendation.id)}/outcome`, {
    method: 'POST',
    headers: { 'content-type': 'application/json' },
    body: JSON.stringify(payload),
  });
  if (result.plan?.id === state.currentPlanId) state.currentPlanDetail = result.plan;
  resetOutcomeForm();
  writeLog('Outcome recorded.', {
    id: recommendation.id,
    expected_vs_realized: result?.decision_closure?.expected_vs_realized || null,
  });
  await load();
}

function openNextOutcome() {
  const pending = [...(state.recommendationOutcomeCandidates || [])]
    .filter((recommendation) => getOutcomeTrackingStatus(recommendation) === 'pending_realized')
    .sort(outcomeCandidateSort);
  if (!pending.length) {
    writeLog('No pending recommendation outcomes to log.');
    return;
  }
  openOutcomeForm(pending[0]);
}

async function archiveItem(r) {
  const reason = window.prompt('Archive note (optional):', '');
  if (reason === null) return;
  await fetchJson(`/api/recommendations/${encodeURIComponent(r.id)}/archive`, { method: 'POST', headers: { 'content-type': 'application/json' }, body: JSON.stringify({ reason: reason.trim() }) });
  writeLog('Archived.', { id: r.id }); await load();
}

function populatePlanFilters() {
  const filter = byId('recommendation-plan-filter');
  const editor = byId('recommendation-plan');
  const factory = byId('recommendation-factory-plan');
  const prev = state.recommendationFilterPlanId || '';
  filter.innerHTML = '<option value="">All plans</option>';
  editor.innerHTML = '<option value="">Active plan (default)</option>';
  factory.innerHTML = '<option value="">No plan attachment</option>';
  for (const p of state.plans) {
    const label = p.is_active ? `${p.title} (Active)` : p.title;
    filter.innerHTML += `<option value="${p.id}">${label}</option>`;
    editor.innerHTML += `<option value="${p.id}">${label}</option>`;
    factory.innerHTML += `<option value="${p.id}">${label}</option>`;
  }
  if ([...filter.options].some(o => o.value === prev)) filter.value = prev;
  if ([...factory.options].some(o => o.value === prev)) factory.value = prev;
}

export function init() {
  populatePlanFilters();
  resetForm();
  resetPreview();
  resetClosureAnalytics();
  resetRecommendationFactory();
  resetOutcomeForm();
  if ([...byId('recommendation-status-filter').options].some((option) => option.value === state.recommendationFilterStatus)) {
    byId('recommendation-status-filter').value = state.recommendationFilterStatus;
  }
  if ([...byId('recommendation-sort-filter').options].some((option) => option.value === state.recommendationSort)) {
    byId('recommendation-sort-filter').value = state.recommendationSort;
  }
  byId('reload-recommendations').addEventListener('click', () => load().catch(e => writeLog(e.message, null, true)));
  byId('reload-recommendation-analytics').addEventListener('click', () => loadClosureAnalytics().catch(e => writeLog(e.message, null, true)));
  byId('recommendation-status-filter').addEventListener('change', () => load().catch(e => writeLog(e.message, null, true)));
  byId('recommendation-plan-filter').addEventListener('change', () => load().catch(e => writeLog(e.message, null, true)));
  byId('recommendation-sort-filter').addEventListener('change', () => load().catch(e => writeLog(e.message, null, true)));
  byId('preview-portfolio-risk-recommendations').addEventListener('click', () => runPortfolioRiskRecommendationFactory(true).catch(e => writeLog(e.message, null, true)));
  byId('create-portfolio-risk-recommendations').addEventListener('click', () => runPortfolioRiskRecommendationFactory(false).catch(e => writeLog(e.message, null, true)));
  byId('recommendation-save').addEventListener('click', save);
  byId('recommendation-cancel-edit').addEventListener('click', resetForm);
  byId('recommendation-outcome-next').addEventListener('click', openNextOutcome);
  byId('recommendation-outcome-save').addEventListener('click', () => saveOutcomeForm().catch(error => writeLog(error.message, null, true)));
  byId('recommendation-outcome-cancel').addEventListener('click', resetOutcomeForm);
  load();
}
