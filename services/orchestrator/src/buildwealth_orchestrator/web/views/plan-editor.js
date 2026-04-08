import { fetchJson } from '../lib/api.js';
import { state, PLAN_SETTING_FIELDS, DIFF_SETTING_FIELDS } from '../lib/state.js';
import { byId, fmtCurrency, fmtDate, writeLog } from '../lib/utils.js';
import { collectSettingsPayload, setSettingsInputs } from '../lib/components.js';

function setControlsEnabled(enabled) {
  ['activate-plan', 'refresh-plan-context', 'save-plan', 'save-plan-settings', 'run-scenario-diff', 'apply-scenario-overrides', 'add-decision', 'plan-markdown', 'plan-tasks', 'decision-summary', 'decision-rationale', 'decision-status'].forEach(id => { const el = byId(id); if (el) el.disabled = !enabled; });
  for (const f of [...PLAN_SETTING_FIELDS, ...DIFF_SETTING_FIELDS]) { const el = byId(f.inputId); if (el) el.disabled = !enabled; }
}

export function clearDetail() {
  state.currentPlanDetail = null;
  byId('plan-meta').textContent = 'Select a plan to view details.';
  byId('plan-settings-meta').textContent = 'Blank values use global defaults from planner configuration.';
  ['plan-markdown', 'plan-tasks', 'plan-context', 'scenario-diff-output', 'artifact-content'].forEach(id => { const el = byId(id); if (el) el.value = ''; });
  byId('scenario-diff-summary').textContent = 'No scenario diff run yet.';
  byId('plan-decisions-body').innerHTML = '<tr><td colspan="4">No decisions yet.</td></tr>';
  byId('plan-artifacts-body').innerHTML = '<tr><td colspan="4">No artifacts yet.</td></tr>';
  setSettingsInputs(PLAN_SETTING_FIELDS, {});
  setSettingsInputs(DIFF_SETTING_FIELDS, {});
  setControlsEnabled(false);
}

export function renderDetail() {
  const d = state.currentPlanDetail;
  if (!d) { clearDetail(); return; }
  byId('plan-meta').textContent = `${d.title || 'Untitled'} \u2022 ${d.is_active ? 'Active Plan' : 'Inactive'} \u2022 Updated ${fmtDate(d.updated_at)}`;
  byId('plan-markdown').value = d.files?.plan_markdown || '';
  byId('plan-tasks').value = d.files?.tasks_markdown || '';
  byId('plan-context').value = d.files?.context_markdown || '';
  byId('scenario-diff-summary').textContent = 'No scenario diff run yet.';
  byId('scenario-diff-output').value = '';
  setSettingsInputs(PLAN_SETTING_FIELDS, d.settings || {});
  const su = d.settings?.updated_at ? fmtDate(d.settings.updated_at) : null;
  byId('plan-settings-meta').textContent = su ? `Settings updated ${su}` : 'Blank values use global defaults from planner configuration.';
  renderDecisions(Array.isArray(d.decisions) ? d.decisions : []);
  renderArtifacts(Array.isArray(d.artifacts) ? d.artifacts : []);
  byId('artifact-content').value = '';
  setControlsEnabled(true);
}

function renderDecisions(decisions) {
  const tbody = byId('plan-decisions-body');
  tbody.innerHTML = '';
  if (!decisions.length) { tbody.innerHTML = '<tr><td colspan="4">No decisions yet.</td></tr>'; return; }
  for (const d of decisions) {
    const tr = document.createElement('tr');
    tr.innerHTML = `<td>${fmtDate(d.created_at)}</td><td>${d.status || 'proposed'}</td><td>${d.summary || '-'}</td><td>${d.rationale || '-'}</td>`;
    tbody.appendChild(tr);
  }
}

function renderArtifacts(artifacts) {
  const tbody = byId('plan-artifacts-body');
  tbody.innerHTML = '';
  if (!artifacts.length) { tbody.innerHTML = '<tr><td colspan="4">No artifacts yet.</td></tr>'; return; }
  for (const a of artifacts) {
    const tr = document.createElement('tr');
    const btn = document.createElement('button');
    btn.type = 'button'; btn.className = 'ghost small'; btn.textContent = 'Open';
    btn.addEventListener('click', () => loadArtifact(a.id).catch(e => writeLog(`Artifact load failed: ${e.message}`, null, true)));
    tr.innerHTML = `<td>${fmtDate(a.created_at)}</td><td>${a.title || '-'}</td><td>${a.file_name || '-'}</td><td></td>`;
    tr.lastElementChild.appendChild(btn);
    tbody.appendChild(tr);
  }
}

async function loadArtifact(artifactId) {
  if (!state.currentPlanId || !artifactId) return;
  const a = await fetchJson(`/api/plans/${encodeURIComponent(state.currentPlanId)}/artifacts/${encodeURIComponent(artifactId)}`);
  byId('artifact-content').value = a.content || '';
}

function formatDiffOutput(diff) {
  const rows = Array.isArray(diff?.scenario_deltas) ? diff.scenario_deltas : [];
  const lines = [`Plan: ${diff?.plan_id || '-'}`, `Current Portfolio: ${fmtCurrency(diff?.current_portfolio_value_usd)}`, '', 'Scenario Delta (Candidate - Base):'];
  if (!rows.length) lines.push('- No deltas.');
  else for (const r of rows) lines.push(`- ${r.label}: Future ${fmtCurrency(r.delta_future_value_usd)}, Real ${fmtCurrency(r.delta_real_value_usd)}`);
  const mc = diff?.monte_carlo_delta || {};
  lines.push('', 'Monte Carlo Delta:', `- P10: ${fmtCurrency(mc.delta_p10_future_value_usd)}`, `- P50: ${fmtCurrency(mc.delta_p50_future_value_usd)}`, `- P90: ${fmtCurrency(mc.delta_p90_future_value_usd)}`);
  lines.push('', 'Raw Payload:', JSON.stringify(diff, null, 2));
  return lines.join('\n');
}

export function initEditor(refreshPlans) {
  byId('save-plan').addEventListener('click', async () => {
    if (!state.currentPlanId) { writeLog('Select a plan first.', null, true); return; }
    writeLog(`Saving plan ${state.currentPlanId}...`);
    try {
      state.currentPlanDetail = await fetchJson(`/api/plans/${encodeURIComponent(state.currentPlanId)}`, { method: 'PUT', headers: { 'content-type': 'application/json' }, body: JSON.stringify({ plan_markdown: byId('plan-markdown').value, tasks_markdown: byId('plan-tasks').value }) });
      await refreshPlans(); renderDetail(); writeLog('Plan saved.');
    } catch (e) { writeLog(`Save failed: ${e.message}`, null, true); }
  });

  byId('save-plan-settings').addEventListener('click', async () => {
    if (!state.currentPlanId) { writeLog('Select a plan first.', null, true); return; }
    let payload; try { payload = collectSettingsPayload(PLAN_SETTING_FIELDS, { includeNulls: true }); } catch (e) { writeLog(e.message, null, true); return; }
    writeLog(`Saving settings...`, payload);
    try {
      state.currentPlanDetail = await fetchJson(`/api/plans/${encodeURIComponent(state.currentPlanId)}/settings`, { method: 'PATCH', headers: { 'content-type': 'application/json' }, body: JSON.stringify(payload) });
      renderDetail(); await refreshPlans(); writeLog('Settings saved.');
    } catch (e) { writeLog(`Save settings failed: ${e.message}`, null, true); }
  });

  byId('run-scenario-diff').addEventListener('click', async () => {
    if (!state.currentPlanId) { writeLog('Select a plan first.', null, true); return; }
    let compare; try { compare = collectSettingsPayload(DIFF_SETTING_FIELDS, { includeNulls: false }); } catch (e) { writeLog(e.message, null, true); return; }
    writeLog(`Running scenario diff...`, compare);
    try {
      const result = await fetchJson(`/api/plans/${encodeURIComponent(state.currentPlanId)}/scenario-diff`, { method: 'POST', headers: { 'content-type': 'application/json' }, body: JSON.stringify({ compare_settings: compare }) });
      const bl = (result.scenario_deltas || []).find(r => r.label === 'baseline');
      byId('scenario-diff-summary').textContent = bl ? `Baseline delta: ${fmtCurrency(bl.delta_future_value_usd)} (real: ${fmtCurrency(bl.delta_real_value_usd)})` : 'Diff completed.';
      byId('scenario-diff-output').value = formatDiffOutput(result);
      writeLog('Scenario diff completed.');
    } catch (e) { writeLog(`Diff failed: ${e.message}`, null, true); byId('scenario-diff-summary').textContent = `Failed: ${e.message}`; }
  });

  byId('apply-scenario-overrides').addEventListener('click', async () => {
    if (!state.currentPlanId) { writeLog('Select a plan first.', null, true); return; }
    let payload; try { payload = collectSettingsPayload(DIFF_SETTING_FIELDS, { includeNulls: false }); } catch (e) { writeLog(e.message, null, true); return; }
    if (!Object.keys(payload).length) { writeLog('Enter at least one override.', null, true); return; }
    writeLog(`Applying overrides...`, payload);
    try {
      state.currentPlanDetail = await fetchJson(`/api/plans/${encodeURIComponent(state.currentPlanId)}/settings`, { method: 'PATCH', headers: { 'content-type': 'application/json' }, body: JSON.stringify(payload) });
      renderDetail(); setSettingsInputs(DIFF_SETTING_FIELDS, {});
      byId('scenario-diff-summary').textContent = 'Overrides applied to plan settings.';
      await refreshPlans(); writeLog('Overrides applied.');
    } catch (e) { writeLog(`Apply failed: ${e.message}`, null, true); }
  });

  byId('activate-plan').addEventListener('click', async () => {
    if (!state.currentPlanId) { writeLog('Select a plan first.', null, true); return; }
    try {
      const s = await fetchJson(`/api/plans/${encodeURIComponent(state.currentPlanId)}/activate`, { method: 'POST' });
      await refreshPlans(); writeLog('Plan activated.', { id: s.id });
    } catch (e) { writeLog(`Activate failed: ${e.message}`, null, true); }
  });

  byId('refresh-plan-context').addEventListener('click', async () => {
    if (!state.currentPlanId) { writeLog('Select a plan first.', null, true); return; }
    try {
      state.currentPlanDetail = await fetchJson(`/api/plans/${encodeURIComponent(state.currentPlanId)}/refresh-context`, { method: 'POST' });
      renderDetail(); await refreshPlans(); writeLog('Context refreshed.');
    } catch (e) { writeLog(`Refresh failed: ${e.message}`, null, true); }
  });

  byId('add-decision').addEventListener('click', async () => {
    if (!state.currentPlanId) { writeLog('Select a plan first.', null, true); return; }
    const sumEl = byId('decision-summary');
    const ratEl = byId('decision-rationale');
    const summary = sumEl.value.trim();
    if (!summary) { writeLog('Decision summary required.', null, true); return; }
    try {
      state.currentPlanDetail = await fetchJson(`/api/plans/${encodeURIComponent(state.currentPlanId)}/decisions`, { method: 'POST', headers: { 'content-type': 'application/json' }, body: JSON.stringify({ summary, rationale: ratEl.value.trim(), status: byId('decision-status').value.trim() || 'proposed' }) });
      sumEl.value = ''; ratEl.value = '';
      renderDetail(); await refreshPlans(); writeLog('Decision added.');
    } catch (e) { writeLog(`Add decision failed: ${e.message}`, null, true); }
  });
}
