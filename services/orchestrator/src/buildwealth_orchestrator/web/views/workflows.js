import { fetchJson } from '../lib/api.js';
import { state } from '../lib/state.js';
import { byId, writeLog } from '../lib/utils.js';
import { planSelectOptions } from '../lib/components.js';

export const id = 'workflows';
export const label = 'Workflows';
export const icon = '<svg viewBox="0 0 20 20" fill="none" stroke="currentColor" stroke-width="1.6"><circle cx="10" cy="4" r="2"/><circle cx="10" cy="16" r="2"/><circle cx="4" cy="10" r="2"/><circle cx="16" cy="10" r="2"/><path d="M10 6v4M10 14v-4M6 10h4M14 10h-4" stroke-width="1.2"/></svg>';

export function template() {
  return `
    <div class="view-header"><h2>Workflow Templates</h2></div>
    <p class="hint">Run guided financial workflows that generate structured reports and optionally save them into your current plan.</p>
    <form id="workflow-form" class="workflow-grid">
      <label class="field"><span>Template</span><select id="workflow-template"></select></label>
      <label class="field"><span>Plan Target</span><select id="workflow-plan"></select></label>
      <div class="inline-options form-span">
        <label><input type="checkbox" id="workflow-live-snapshot" /> Use live snapshot</label>
        <label><input type="checkbox" id="workflow-save-to-plan" checked /> Save as plan artifact</label>
        <label><input type="checkbox" id="workflow-create-recommendations" checked /> Create recommendations</label>
      </div>
      <label class="field form-span"><span>Template Params (JSON)</span><textarea id="workflow-params" rows="6" placeholder="{}"></textarea></label>
      <button class="primary" id="run-workflow" type="submit">Run Workflow</button>
    </form>
    <h3 class="section-title">Report Output</h3>
    <p class="hint" id="workflow-summary">No workflow run yet.</p>
    <label class="field"><span>Workflow Report</span><textarea id="workflow-report" rows="16" readonly></textarea></label>`;
}

function renderTemplates() {
  const select = byId('workflow-template');
  const prev = select.value;
  select.innerHTML = '';
  if (!state.workflowTemplates.length) { select.innerHTML = '<option value="">No templates available</option>'; return; }
  for (const t of state.workflowTemplates) { const o = document.createElement('option'); o.value = t.id; o.textContent = t.title; select.appendChild(o); }
  if ([...select.options].some(o => o.value === prev)) select.value = prev;
  updateParams(true);
}

function selectedTemplate() {
  return state.workflowTemplates.find(t => t.id === byId('workflow-template').value) || null;
}

function updateParams(preserve = false) {
  const ta = byId('workflow-params');
  if (preserve && ta.value.trim()) return;
  const t = selectedTemplate();
  ta.value = JSON.stringify(t?.default_params || {}, null, 2);
}

async function loadTemplates() {
  const list = await fetchJson('/api/workflows/templates');
  state.workflowTemplates = Array.isArray(list) ? list : [];
  renderTemplates();
}

async function run(event) {
  event.preventDefault();
  const workflowId = byId('workflow-template').value;
  if (!workflowId) { writeLog('Select a workflow template first.', null, true); return; }
  const raw = byId('workflow-params').value.trim();
  let params = {};
  if (raw) {
    try { const p = JSON.parse(raw); if (!p || typeof p !== 'object' || Array.isArray(p)) throw new Error('Must be a JSON object.'); params = p; }
    catch (e) { writeLog(`Params parse failed: ${e.message}`, null, true); byId('workflow-summary').textContent = `Parse failed: ${e.message}`; return; }
  }
  const payload = {
    workflow_id: workflowId,
    plan_id: byId('workflow-plan').value || null,
    use_live_snapshot: byId('workflow-live-snapshot').checked,
    save_to_plan: byId('workflow-save-to-plan').checked,
    create_recommendations: byId('workflow-create-recommendations').checked,
    params,
  };
  const btn = byId('run-workflow');
  btn.disabled = true; btn.textContent = 'Running...';
  writeLog('Running workflow...', payload);
  try {
    const result = await fetchJson('/api/workflows/run', { method: 'POST', headers: { 'content-type': 'application/json' }, body: JSON.stringify(payload) });
    const created = Array.isArray(result.recommendations) ? result.recommendations.length : 0;
    byId('workflow-summary').textContent = `${result.summary || 'Workflow complete.'} \u2022 ${created} recommendation(s) created.`;
    byId('workflow-report').value = result.report_markdown || '';
    writeLog('Workflow completed.', { workflow_id: result.workflow_id, artifact_id: result.artifact?.id || null, recommendations_created: created });
  } catch (e) {
    writeLog(`Workflow failed: ${e.message}`, null, true);
    byId('workflow-summary').textContent = `Workflow failed: ${e.message}`;
  } finally { btn.disabled = false; btn.textContent = 'Run Workflow'; }
}

export function init() {
  planSelectOptions('workflow-plan', state.copilotPlanId);
  byId('workflow-form').addEventListener('submit', run);
  byId('workflow-template').addEventListener('change', () => updateParams(false));
  byId('workflow-plan').addEventListener('change', (e) => { state.copilotPlanId = e.target.value || ''; });
  loadTemplates();
}
