import { fetchJson } from '../lib/api.js';
import { state } from '../lib/state.js';
import { byId, fmtCurrency, fmtDate, writeLog } from '../lib/utils.js';
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
    <div class="table-wrap"><table><thead><tr><th>When</th><th>Status</th><th>Score</th><th>Priority</th><th>Type</th><th>Recommendation</th><th>Plan</th><th>Source</th><th>Actions</th></tr></thead><tbody id="recommendation-body"></tbody></table></div>
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
      if (Array.isArray(score.reasons) && score.reasons.length) {
        recHtml += `<p class="rec-detail">Drivers: ${score.reasons.slice(0, 3).join(' • ')}</p>`;
      }
    }
    if (r.resolution_note) recHtml += `<p class="rec-detail">Resolution: ${r.resolution_note}</p>`;
    const evidence = r.action_payload?.evidence;
    if (evidence) {
      const parts = [];
      if (evidence.workflow_id) parts.push(`Workflow ${evidence.workflow_id}`);
      if (evidence.generated_at) parts.push(`Generated ${fmtDate(evidence.generated_at)}`);
      if (evidence.snapshot_as_of) parts.push(`Snapshot ${fmtDate(evidence.snapshot_as_of)}`);
      if (Array.isArray(evidence.data_keys) && evidence.data_keys.length) parts.push(`Data: ${evidence.data_keys.slice(0, 4).join(', ')}`);
      if (parts.length) recHtml += `<p class="rec-detail">Evidence: ${parts.join(' \u2022 ')}</p>`;
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
      wrap.innerHTML = `<button class="primary small" data-action="apply">Apply</button><button class="ghost small" data-action="reject">Reject</button>`;
      wrap.querySelector('[data-action="apply"]').addEventListener('click', () => applyItem(r));
      wrap.querySelector('[data-action="reject"]').addEventListener('click', () => rejectItem(r));
    }
    if (r.status !== 'archived') {
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
  state.recommendations = await fetchJson(`/api/recommendations?${params}`).then(r => Array.isArray(r) ? r : []);
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
  writeLog('Applied.', { id: r.id, decision_closure: result.decision_closure || null, research_bridge: result.research_bridge || null }); await load();
}

async function rejectItem(r) {
  const reason = window.prompt('Reason (optional):', '');
  if (reason === null) return;
  const result = await fetchJson(`/api/recommendations/${encodeURIComponent(r.id)}/reject`, { method: 'POST', headers: { 'content-type': 'application/json' }, body: JSON.stringify({ reason: reason.trim() }) });
  writeLog('Rejected.', { id: r.id, decision_closure: result.decision_closure || null }); await load();
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
  const prev = state.recommendationFilterPlanId || '';
  filter.innerHTML = '<option value="">All plans</option>';
  editor.innerHTML = '<option value="">Active plan (default)</option>';
  for (const p of state.plans) {
    const label = p.is_active ? `${p.title} (Active)` : p.title;
    filter.innerHTML += `<option value="${p.id}">${label}</option>`;
    editor.innerHTML += `<option value="${p.id}">${label}</option>`;
  }
  if ([...filter.options].some(o => o.value === prev)) filter.value = prev;
}

export function init() {
  populatePlanFilters();
  resetForm();
  if ([...byId('recommendation-status-filter').options].some((option) => option.value === state.recommendationFilterStatus)) {
    byId('recommendation-status-filter').value = state.recommendationFilterStatus;
  }
  if ([...byId('recommendation-sort-filter').options].some((option) => option.value === state.recommendationSort)) {
    byId('recommendation-sort-filter').value = state.recommendationSort;
  }
  byId('reload-recommendations').addEventListener('click', () => load().catch(e => writeLog(e.message, null, true)));
  byId('recommendation-status-filter').addEventListener('change', () => load().catch(e => writeLog(e.message, null, true)));
  byId('recommendation-plan-filter').addEventListener('change', () => load().catch(e => writeLog(e.message, null, true)));
  byId('recommendation-sort-filter').addEventListener('change', () => load().catch(e => writeLog(e.message, null, true)));
  byId('recommendation-save').addEventListener('click', save);
  byId('recommendation-cancel-edit').addEventListener('click', resetForm);
  load();
}
