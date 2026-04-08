const byId = (id) => document.getElementById(id);

const logEl = byId('log');

const state = {
  conversations: [],
  currentConversationId: null,
  currentMessages: [],
  copilotLoading: false,
  plans: [],
  currentPlanId: null,
  currentPlanDetail: null,
  copilotPlanId: '',
  workflowTemplates: [],
};

const PLAN_SETTING_FIELDS = [
  { key: 'annual_contribution_usd', inputId: 'setting-annual-contribution', scale: 1, integer: false },
  { key: 'years', inputId: 'setting-years', scale: 1, integer: true },
  { key: 'hsa_extra_contribution_usd', inputId: 'setting-hsa-extra', scale: 1, integer: false },
  { key: 'marginal_tax_rate', inputId: 'setting-marginal-tax-rate', scale: 100, integer: false },
  { key: 'expected_return_baseline', inputId: 'setting-return-baseline', scale: 100, integer: false },
  { key: 'expected_return_optimistic', inputId: 'setting-return-optimistic', scale: 100, integer: false },
  { key: 'expected_return_conservative', inputId: 'setting-return-conservative', scale: 100, integer: false },
];

const DIFF_SETTING_FIELDS = [
  { key: 'annual_contribution_usd', inputId: 'diff-annual-contribution', scale: 1, integer: false },
  { key: 'years', inputId: 'diff-years', scale: 1, integer: true },
  { key: 'hsa_extra_contribution_usd', inputId: 'diff-hsa-extra', scale: 1, integer: false },
  { key: 'marginal_tax_rate', inputId: 'diff-marginal-tax-rate', scale: 100, integer: false },
  { key: 'expected_return_baseline', inputId: 'diff-return-baseline', scale: 100, integer: false },
  { key: 'expected_return_optimistic', inputId: 'diff-return-optimistic', scale: 100, integer: false },
  { key: 'expected_return_conservative', inputId: 'diff-return-conservative', scale: 100, integer: false },
];

function stamp() {
  return new Date().toLocaleTimeString();
}

function writeLog(message, payload = null, isError = false) {
  const lines = [`[${stamp()}] ${message}`];
  if (payload !== null) {
    lines.push(JSON.stringify(payload, null, 2));
  }

  const block = document.createElement('div');
  if (isError) block.classList.add('error');
  block.textContent = `${lines.join('\n')}\n`;
  logEl.prepend(block);
}

function fmtCurrency(value) {
  if (typeof value !== 'number' || Number.isNaN(value)) return '-';
  return new Intl.NumberFormat('en-US', { style: 'currency', currency: 'USD', maximumFractionDigits: 0 }).format(value);
}

function fmtPct(value) {
  if (typeof value !== 'number' || Number.isNaN(value)) return '-';
  return `${value.toFixed(2)}%`;
}

function fmtDate(value) {
  if (!value) return '-';
  const dateValue = new Date(value);
  if (Number.isNaN(dateValue.getTime())) return String(value);
  return dateValue.toLocaleString();
}

function truncate(value, maxLength = 120) {
  const text = String(value || '').trim();
  if (text.length <= maxLength) return text;
  return `${text.slice(0, maxLength - 3)}...`;
}

function parseOptionalNumericField(rawValue, fieldLabel, asInteger = false) {
  const text = String(rawValue || '').trim();
  if (!text) return { present: false, value: null };

  const numeric = Number(text);
  if (Number.isNaN(numeric)) {
    throw new Error(`${fieldLabel} must be numeric.`);
  }
  if (asInteger && !Number.isInteger(numeric)) {
    throw new Error(`${fieldLabel} must be an integer.`);
  }

  return { present: true, value: numeric };
}

function formatNumericInput(value, maxDecimals = 6) {
  if (typeof value !== 'number' || Number.isNaN(value)) return '';
  if (Number.isInteger(value)) return String(value);
  return String(Number(value.toFixed(maxDecimals)));
}

function collectSettingsPayload(fields, { includeNulls }) {
  const payload = {};

  for (const field of fields) {
    const input = byId(field.inputId);
    if (!input) continue;
    const parsed = parseOptionalNumericField(input.value, field.key, Boolean(field.integer));
    if (!parsed.present) {
      if (includeNulls) payload[field.key] = null;
      continue;
    }

    const divisor = field.scale || 1;
    const normalized = parsed.value / divisor;
    payload[field.key] = field.integer ? Math.trunc(normalized) : normalized;
  }

  return payload;
}

function setSettingsInputs(fields, settingsPayload) {
  const settings = settingsPayload && typeof settingsPayload === 'object' ? settingsPayload : {};

  for (const field of fields) {
    const input = byId(field.inputId);
    if (!input) continue;
    const rawValue = settings[field.key];
    if (rawValue === null || rawValue === undefined || rawValue === '') {
      input.value = '';
      continue;
    }
    const multiplier = field.scale || 1;
    const displayValue = Number(rawValue) * multiplier;
    input.value = formatNumericInput(displayValue);
  }
}

async function fetchJson(url, options = {}) {
  const response = await fetch(url, options);
  const data = await response.json().catch(() => ({}));

  if (!response.ok) {
    const detail = data.detail || data.message || response.statusText;
    throw new Error(detail);
  }

  return data;
}

function renderSyncStatus(status) {
  byId('sync-running').textContent = status.running ? 'Running' : 'Idle';
  byId('sync-runs').textContent = String(status.runs_total ?? 0);
  byId('sync-failed').textContent = String(status.runs_failed ?? 0);

  byId('meta-trigger').textContent = status.last_trigger || '-';
  byId('meta-started').textContent = fmtDate(status.last_started_at);
  byId('meta-completed').textContent = fmtDate(status.last_completed_at);
}

function renderSnapshot(snapshot) {
  byId('snapshot-total').textContent =
    `Total Value ${fmtCurrency(snapshot.total_value_usd)} | Net ${fmtCurrency(snapshot.net_performance_usd)} (${fmtPct(snapshot.net_performance_percent)})`;

  const tbody = byId('holdings-body');
  tbody.innerHTML = '';
  const top = (snapshot.holdings || []).slice(0, 12);

  for (const row of top) {
    const tr = document.createElement('tr');
    tr.innerHTML = `
      <td>${row.symbol || '-'}</td>
      <td>${row.name || '-'}</td>
      <td>${fmtCurrency(row.value_usd)}</td>
      <td>${fmtPct(row.allocation_percent)}</td>
    `;
    tbody.appendChild(tr);
  }

  if (top.length === 0) {
    const tr = document.createElement('tr');
    tr.innerHTML = '<td colspan="4">No holdings in latest snapshot.</td>';
    tbody.appendChild(tr);
  }
}

function renderSnapshotHistory(historyPayload) {
  const summaryEl = byId('snapshot-history-summary');
  const tbody = byId('snapshot-history-body');
  tbody.innerHTML = '';

  const points = Array.isArray(historyPayload?.points) ? historyPayload.points : [];
  if (!points.length) {
    summaryEl.textContent = 'No snapshot history is available yet.';
    const tr = document.createElement('tr');
    tr.innerHTML = '<td colspan="3">Run sync multiple times to build trend history.</td>';
    tbody.appendChild(tr);
    return;
  }

  const deltaValue = historyPayload.delta_total_value_usd;
  const deltaPct = historyPayload.delta_total_value_percent;
  summaryEl.textContent =
    `Window: ${historyPayload.window_points || points.length} points | ` +
    `Delta total value: ${fmtCurrency(deltaValue)} (${fmtPct(deltaPct)})`;

  for (const point of points.slice(0, 10)) {
    const tr = document.createElement('tr');
    tr.innerHTML = `
      <td>${fmtDate(point.as_of)}</td>
      <td>${fmtCurrency(point.total_value_usd)}</td>
      <td>${fmtCurrency(point.net_performance_usd)}</td>
    `;
    tbody.appendChild(tr);
  }
}

function renderInboxFiles(files) {
  const select = byId('inbox-file');
  select.innerHTML = '';

  if (!files.length) {
    const option = document.createElement('option');
    option.value = '';
    option.textContent = 'No CSV files in inbox';
    select.appendChild(option);
    return;
  }

  for (const file of files) {
    const option = document.createElement('option');
    option.value = file;
    option.textContent = file;
    select.appendChild(option);
  }
}

function setPlanControlsEnabled(enabled) {
  byId('activate-plan').disabled = !enabled;
  byId('refresh-plan-context').disabled = !enabled;
  byId('save-plan').disabled = !enabled;
  byId('save-plan-settings').disabled = !enabled;
  byId('run-scenario-diff').disabled = !enabled;
  byId('apply-scenario-overrides').disabled = !enabled;
  byId('add-decision').disabled = !enabled;
  byId('plan-markdown').disabled = !enabled;
  byId('plan-tasks').disabled = !enabled;
  byId('decision-summary').disabled = !enabled;
  byId('decision-rationale').disabled = !enabled;
  byId('decision-status').disabled = !enabled;
  for (const field of PLAN_SETTING_FIELDS) {
    const input = byId(field.inputId);
    if (input) input.disabled = !enabled;
  }
  for (const field of DIFF_SETTING_FIELDS) {
    const input = byId(field.inputId);
    if (input) input.disabled = !enabled;
  }
}

function clearPlanDetail() {
  state.currentPlanDetail = null;
  byId('plan-meta').textContent = 'Select a plan to view details.';
  byId('plan-settings-meta').textContent = 'Blank values use global defaults from planner configuration.';
  byId('plan-markdown').value = '';
  byId('plan-tasks').value = '';
  byId('plan-context').value = '';
  byId('scenario-diff-summary').textContent = 'No scenario diff run yet.';
  byId('scenario-diff-output').value = '';
  byId('plan-decisions-body').innerHTML = '<tr><td colspan="4">No decisions yet.</td></tr>';
  byId('plan-artifacts-body').innerHTML = '<tr><td colspan="4">No artifacts yet.</td></tr>';
  byId('artifact-content').value = '';
  setSettingsInputs(PLAN_SETTING_FIELDS, {});
  setSettingsInputs(DIFF_SETTING_FIELDS, {});
  setPlanControlsEnabled(false);
}

function renderPlanDecisions(decisions) {
  const tbody = byId('plan-decisions-body');
  tbody.innerHTML = '';

  if (!decisions.length) {
    const tr = document.createElement('tr');
    tr.innerHTML = '<td colspan="4">No decisions yet.</td>';
    tbody.appendChild(tr);
    return;
  }

  for (const decision of decisions) {
    const tr = document.createElement('tr');
    tr.innerHTML = `
      <td>${fmtDate(decision.created_at)}</td>
      <td>${decision.status || 'proposed'}</td>
      <td>${decision.summary || '-'}</td>
      <td>${decision.rationale || '-'}</td>
    `;
    tbody.appendChild(tr);
  }
}

function renderPlanArtifacts(artifacts) {
  const tbody = byId('plan-artifacts-body');
  tbody.innerHTML = '';

  if (!artifacts.length) {
    const tr = document.createElement('tr');
    tr.innerHTML = '<td colspan="4">No artifacts yet.</td>';
    tbody.appendChild(tr);
    return;
  }

  for (const artifact of artifacts) {
    const tr = document.createElement('tr');
    const actionButton = document.createElement('button');
    actionButton.type = 'button';
    actionButton.className = 'ghost small';
    actionButton.textContent = 'Open';
    actionButton.addEventListener('click', () => {
      loadPlanArtifact(artifact.id).catch((error) => {
        writeLog(`Artifact load failed: ${error.message}`, null, true);
      });
    });

    tr.innerHTML = `
      <td>${fmtDate(artifact.created_at)}</td>
      <td>${artifact.title || '-'}</td>
      <td>${artifact.file_name || '-'}</td>
      <td></td>
    `;
    tr.children[3].appendChild(actionButton);
    tbody.appendChild(tr);
  }
}

async function loadPlanArtifact(artifactId) {
  if (!state.currentPlanId || !artifactId) return;
  const artifact = await fetchJson(
    `/api/plans/${encodeURIComponent(state.currentPlanId)}/artifacts/${encodeURIComponent(artifactId)}`
  );
  byId('artifact-content').value = artifact.content || '';
}

function renderPlanDetail() {
  const detail = state.currentPlanDetail;
  if (!detail) {
    clearPlanDetail();
    return;
  }

  byId('plan-meta').textContent =
    `${detail.title || 'Untitled'} • ${detail.is_active ? 'Active Plan' : 'Inactive'} • Updated ${fmtDate(detail.updated_at)}`;
  byId('plan-markdown').value = detail.files?.plan_markdown || '';
  byId('plan-tasks').value = detail.files?.tasks_markdown || '';
  byId('plan-context').value = detail.files?.context_markdown || '';
  byId('scenario-diff-summary').textContent = 'No scenario diff run yet.';
  byId('scenario-diff-output').value = '';
  setSettingsInputs(PLAN_SETTING_FIELDS, detail.settings || {});
  const settingsUpdatedAt = detail.settings?.updated_at ? fmtDate(detail.settings.updated_at) : null;
  byId('plan-settings-meta').textContent = settingsUpdatedAt
    ? `Settings updated ${settingsUpdatedAt}`
    : 'Blank values use global defaults from planner configuration.';
  renderPlanDecisions(Array.isArray(detail.decisions) ? detail.decisions : []);
  renderPlanArtifacts(Array.isArray(detail.artifacts) ? detail.artifacts : []);
  if (Array.isArray(detail.artifacts) && detail.artifacts.length > 0) {
    byId('artifact-content').value = '';
  }
  setPlanControlsEnabled(true);
}

function renderPlanList() {
  const listEl = byId('plan-list');
  listEl.innerHTML = '';

  if (!state.plans.length) {
    const empty = document.createElement('p');
    empty.className = 'chat-empty';
    empty.textContent = 'No plans yet.';
    listEl.appendChild(empty);
    return;
  }

  for (const plan of state.plans) {
    const button = document.createElement('button');
    button.type = 'button';
    button.className = 'plan-item';
    if (plan.id === state.currentPlanId) {
      button.classList.add('active');
    }

    const title = document.createElement('p');
    title.className = 'plan-item-title';
    title.textContent = plan.is_active ? `${plan.title} (Active)` : plan.title;

    const meta = document.createElement('p');
    meta.className = 'plan-item-meta';
    meta.textContent = `Updated ${fmtDate(plan.updated_at)}`;

    button.appendChild(title);
    button.appendChild(meta);
    button.addEventListener('click', () => {
      loadPlan(plan.id).catch((error) => writeLog(`Plan load failed: ${error.message}`, null, true));
    });

    listEl.appendChild(button);
  }
}

function renderPlanSelectOptions(selectId, currentValue = '') {
  const select = byId(selectId);
  const current = currentValue || '';
  select.innerHTML = '';

  const defaultOption = document.createElement('option');
  defaultOption.value = '';
  defaultOption.textContent = 'Active plan (default)';
  select.appendChild(defaultOption);

  for (const plan of state.plans) {
    const option = document.createElement('option');
    option.value = plan.id;
    option.textContent = plan.is_active ? `${plan.title} (Active)` : plan.title;
    select.appendChild(option);
  }

  const hasCurrent = [...select.options].some((option) => option.value === current);
  if (hasCurrent) {
    select.value = current;
  } else if (state.currentPlanId && [...select.options].some((option) => option.value === state.currentPlanId)) {
    select.value = state.currentPlanId;
  } else {
    select.value = '';
  }
}

function renderCopilotPlanOptions() {
  renderPlanSelectOptions('copilot-plan', state.copilotPlanId);
  if (![...byId('copilot-plan').options].some((option) => option.value === state.copilotPlanId)) {
    state.copilotPlanId = byId('copilot-plan').value || '';
  }
}

function renderWorkflowPlanOptions() {
  renderPlanSelectOptions('workflow-plan', state.copilotPlanId);
}

async function loadPlans(autoSelect = true) {
  const plans = await fetchJson('/api/plans?limit=200');
  state.plans = Array.isArray(plans) ? plans : [];

  if (state.currentPlanId && !state.plans.some((plan) => plan.id === state.currentPlanId)) {
    state.currentPlanId = null;
    state.currentPlanDetail = null;
  }

  if (autoSelect && !state.currentPlanId && state.plans.length) {
    const active = state.plans.find((plan) => plan.is_active);
    state.currentPlanId = active ? active.id : state.plans[0].id;
  }

  renderPlanList();
  renderCopilotPlanOptions();
  renderWorkflowPlanOptions();

  if (state.currentPlanId) {
    await loadPlan(state.currentPlanId, true);
  } else {
    clearPlanDetail();
  }
}

async function loadPlan(planId, skipListRefresh = false) {
  if (!planId) return;
  const detail = await fetchJson(`/api/plans/${encodeURIComponent(planId)}`);
  state.currentPlanId = detail.id;
  state.currentPlanDetail = detail;
  state.copilotPlanId = detail.id;

  if (!skipListRefresh) {
    renderPlanList();
  } else {
    renderPlanList();
  }
  renderCopilotPlanOptions();
  renderWorkflowPlanOptions();
  renderPlanDetail();
}

async function createPlan(event) {
  event.preventDefault();
  const titleInput = byId('new-plan-title');
  const descriptionInput = byId('new-plan-description');
  const title = titleInput.value.trim();
  if (!title) return;

  const payload = {
    title,
    description: descriptionInput.value.trim(),
  };

  writeLog('Creating plan...', payload);
  try {
    const detail = await fetchJson('/api/plans', {
      method: 'POST',
      headers: { 'content-type': 'application/json' },
      body: JSON.stringify(payload),
    });

    titleInput.value = '';
    descriptionInput.value = '';
    state.currentPlanId = detail.id;
    state.currentPlanDetail = detail;
    state.copilotPlanId = detail.id;
    await loadPlans(false);
    renderPlanDetail();
    writeLog('Plan created.', { id: detail.id, title: detail.title });
  } catch (error) {
    writeLog(`Create plan failed: ${error.message}`, null, true);
  }
}

async function savePlan() {
  if (!state.currentPlanId) {
    writeLog('Select a plan before saving.', null, true);
    return;
  }

  const payload = {
    plan_markdown: byId('plan-markdown').value,
    tasks_markdown: byId('plan-tasks').value,
  };

  writeLog(`Saving plan ${state.currentPlanId}...`);
  try {
    const detail = await fetchJson(`/api/plans/${encodeURIComponent(state.currentPlanId)}`, {
      method: 'PUT',
      headers: { 'content-type': 'application/json' },
      body: JSON.stringify(payload),
    });
    state.currentPlanDetail = detail;
    await loadPlans(false);
    renderPlanDetail();
    writeLog('Plan saved.', { plan_id: state.currentPlanId });
  } catch (error) {
    writeLog(`Save plan failed: ${error.message}`, null, true);
  }
}

function formatScenarioDiffOutput(diffPayload) {
  const rows = Array.isArray(diffPayload?.scenario_deltas) ? diffPayload.scenario_deltas : [];
  const lines = [
    `Plan: ${diffPayload?.plan_id || '-'}`,
    `Current Portfolio Value: ${fmtCurrency(diffPayload?.current_portfolio_value_usd)}`,
    '',
    'Scenario Delta (Candidate - Base):',
  ];

  if (!rows.length) {
    lines.push('- No scenario deltas available.');
  } else {
    for (const row of rows) {
      lines.push(
        `- ${row.label}: Future ${fmtCurrency(row.delta_future_value_usd)}, Real ${fmtCurrency(row.delta_real_value_usd)}`
      );
    }
  }

  const monte = diffPayload?.monte_carlo_delta || {};
  lines.push('', 'Monte Carlo Delta:');
  lines.push(`- P10: ${fmtCurrency(monte.delta_p10_future_value_usd)}`);
  lines.push(`- P50: ${fmtCurrency(monte.delta_p50_future_value_usd)}`);
  lines.push(`- P90: ${fmtCurrency(monte.delta_p90_future_value_usd)}`);
  lines.push('', 'Raw Payload:');
  lines.push(JSON.stringify(diffPayload, null, 2));
  return lines.join('\n');
}

async function savePlanSettings() {
  if (!state.currentPlanId) {
    writeLog('Select a plan before saving settings.', null, true);
    return;
  }

  let payload;
  try {
    payload = collectSettingsPayload(PLAN_SETTING_FIELDS, { includeNulls: true });
  } catch (error) {
    writeLog(`Plan settings validation failed: ${error.message}`, null, true);
    return;
  }

  writeLog(`Saving plan settings for ${state.currentPlanId}...`, payload);
  try {
    const detail = await fetchJson(`/api/plans/${encodeURIComponent(state.currentPlanId)}/settings`, {
      method: 'PATCH',
      headers: { 'content-type': 'application/json' },
      body: JSON.stringify(payload),
    });
    state.currentPlanDetail = detail;
    renderPlanDetail();
    await loadPlans(false);
    writeLog('Plan settings saved.', { plan_id: state.currentPlanId });
  } catch (error) {
    writeLog(`Save plan settings failed: ${error.message}`, null, true);
  }
}

async function runScenarioDiff() {
  if (!state.currentPlanId) {
    writeLog('Select a plan first.', null, true);
    return;
  }

  let compareSettings;
  try {
    compareSettings = collectSettingsPayload(DIFF_SETTING_FIELDS, { includeNulls: false });
  } catch (error) {
    writeLog(`Scenario override validation failed: ${error.message}`, null, true);
    return;
  }

  const payload = { compare_settings: compareSettings };
  writeLog(`Running scenario diff for ${state.currentPlanId}...`, payload);

  try {
    const result = await fetchJson(`/api/plans/${encodeURIComponent(state.currentPlanId)}/scenario-diff`, {
      method: 'POST',
      headers: { 'content-type': 'application/json' },
      body: JSON.stringify(payload),
    });

    const baseline = (result.scenario_deltas || []).find((row) => row.label === 'baseline');
    byId('scenario-diff-summary').textContent = baseline
      ? `Baseline future value delta: ${fmtCurrency(baseline.delta_future_value_usd)} (real: ${fmtCurrency(
          baseline.delta_real_value_usd
        )})`
      : 'Scenario diff completed.';
    byId('scenario-diff-output').value = formatScenarioDiffOutput(result);
    writeLog('Scenario diff completed.', {
      plan_id: state.currentPlanId,
      overrides_count: Object.keys(compareSettings).length,
    });
  } catch (error) {
    writeLog(`Scenario diff failed: ${error.message}`, null, true);
    byId('scenario-diff-summary').textContent = `Scenario diff failed: ${error.message}`;
  }
}

async function applyScenarioOverrides() {
  if (!state.currentPlanId) {
    writeLog('Select a plan first.', null, true);
    return;
  }

  let payload;
  try {
    payload = collectSettingsPayload(DIFF_SETTING_FIELDS, { includeNulls: false });
  } catch (error) {
    writeLog(`Scenario override validation failed: ${error.message}`, null, true);
    return;
  }

  if (!Object.keys(payload).length) {
    writeLog('Enter at least one override before applying.', null, true);
    return;
  }

  writeLog(`Applying scenario overrides to ${state.currentPlanId}...`, payload);
  try {
    const detail = await fetchJson(`/api/plans/${encodeURIComponent(state.currentPlanId)}/settings`, {
      method: 'PATCH',
      headers: { 'content-type': 'application/json' },
      body: JSON.stringify(payload),
    });
    state.currentPlanDetail = detail;
    renderPlanDetail();
    setSettingsInputs(DIFF_SETTING_FIELDS, {});
    byId('scenario-diff-summary').textContent = 'Overrides applied to plan settings.';
    await loadPlans(false);
    writeLog('Scenario overrides applied.', { plan_id: state.currentPlanId });
  } catch (error) {
    writeLog(`Apply overrides failed: ${error.message}`, null, true);
  }
}

async function activatePlan() {
  if (!state.currentPlanId) {
    writeLog('Select a plan first.', null, true);
    return;
  }

  try {
    const summary = await fetchJson(`/api/plans/${encodeURIComponent(state.currentPlanId)}/activate`, {
      method: 'POST',
    });
    await loadPlans(false);
    await loadPlan(summary.id, true);
    writeLog('Plan activated.', { plan_id: summary.id, title: summary.title });
  } catch (error) {
    writeLog(`Activate plan failed: ${error.message}`, null, true);
  }
}

async function refreshPlanContext() {
  if (!state.currentPlanId) {
    writeLog('Select a plan first.', null, true);
    return;
  }

  try {
    const detail = await fetchJson(`/api/plans/${encodeURIComponent(state.currentPlanId)}/refresh-context`, {
      method: 'POST',
    });
    state.currentPlanDetail = detail;
    renderPlanDetail();
    await loadPlans(false);
    writeLog('Plan context refreshed.', { plan_id: state.currentPlanId });
  } catch (error) {
    writeLog(`Refresh context failed: ${error.message}`, null, true);
  }
}

async function addPlanDecision() {
  if (!state.currentPlanId) {
    writeLog('Select a plan first.', null, true);
    return;
  }

  const summaryInput = byId('decision-summary');
  const rationaleInput = byId('decision-rationale');
  const statusInput = byId('decision-status');

  const summary = summaryInput.value.trim();
  if (!summary) {
    writeLog('Decision summary is required.', null, true);
    return;
  }

  const payload = {
    summary,
    rationale: rationaleInput.value.trim(),
    status: statusInput.value.trim() || 'proposed',
  };

  try {
    const detail = await fetchJson(`/api/plans/${encodeURIComponent(state.currentPlanId)}/decisions`, {
      method: 'POST',
      headers: { 'content-type': 'application/json' },
      body: JSON.stringify(payload),
    });
    summaryInput.value = '';
    rationaleInput.value = '';
    state.currentPlanDetail = detail;
    renderPlanDetail();
    await loadPlans(false);
    writeLog('Decision added.', { plan_id: state.currentPlanId, status: payload.status });
  } catch (error) {
    writeLog(`Add decision failed: ${error.message}`, null, true);
  }
}

function renderWorkflowTemplates() {
  const select = byId('workflow-template');
  const previousValue = select.value;
  select.innerHTML = '';

  if (!state.workflowTemplates.length) {
    const option = document.createElement('option');
    option.value = '';
    option.textContent = 'No templates available';
    select.appendChild(option);
    return;
  }

  for (const template of state.workflowTemplates) {
    const option = document.createElement('option');
    option.value = template.id;
    option.textContent = template.title;
    select.appendChild(option);
  }

  if ([...select.options].some((option) => option.value === previousValue)) {
    select.value = previousValue;
  }
  updateWorkflowParamsEditor(true);
}

async function loadWorkflowTemplates() {
  const templates = await fetchJson('/api/workflows/templates');
  state.workflowTemplates = Array.isArray(templates) ? templates : [];
  renderWorkflowTemplates();
}

function selectedWorkflowTemplate() {
  const selectedId = byId('workflow-template').value;
  return state.workflowTemplates.find((item) => item.id === selectedId) || null;
}

function updateWorkflowParamsEditor(preserveIfPopulated = false) {
  const textarea = byId('workflow-params');
  if (!textarea) return;

  const current = textarea.value.trim();
  if (preserveIfPopulated && current) {
    return;
  }

  const template = selectedWorkflowTemplate();
  const defaults = template?.default_params || {};
  textarea.value = JSON.stringify(defaults, null, 2);
}

async function runWorkflow(event) {
  event.preventDefault();

  const workflowId = byId('workflow-template').value;
  if (!workflowId) {
    writeLog('Select a workflow template first.', null, true);
    return;
  }

  const selectedPlanId = byId('workflow-plan').value || null;
  const rawParams = byId('workflow-params').value.trim();
  let params = {};
  if (rawParams) {
    try {
      const parsed = JSON.parse(rawParams);
      if (parsed && typeof parsed === 'object' && !Array.isArray(parsed)) {
        params = parsed;
      } else {
        writeLog('Workflow params must be a JSON object.', null, true);
        byId('workflow-summary').textContent = 'Workflow params must be a JSON object.';
        return;
      }
    } catch (error) {
      writeLog(`Workflow params JSON parse failed: ${error.message}`, null, true);
      byId('workflow-summary').textContent = `Workflow params JSON parse failed: ${error.message}`;
      return;
    }
  }

  const payload = {
    workflow_id: workflowId,
    plan_id: selectedPlanId,
    use_live_snapshot: byId('workflow-live-snapshot').checked,
    save_to_plan: byId('workflow-save-to-plan').checked,
    params,
  };

  byId('run-workflow').disabled = true;
  byId('run-workflow').textContent = 'Running...';
  writeLog('Running workflow...', payload);

  try {
    const result = await fetchJson('/api/workflows/run', {
      method: 'POST',
      headers: { 'content-type': 'application/json' },
      body: JSON.stringify(payload),
    });

    byId('workflow-summary').textContent = result.summary || 'Workflow complete.';
    byId('workflow-report').value = result.report_markdown || '';

    if (result.artifact && selectedPlanId) {
      await loadPlan(selectedPlanId, true);
      byId('artifact-content').value = result.report_markdown || '';
    } else if (result.artifact) {
      await loadPlans(false);
    }

    writeLog('Workflow completed.', {
      workflow_id: result.workflow_id,
      artifact_id: result.artifact?.id || null,
    });
  } catch (error) {
    writeLog(`Workflow failed: ${error.message}`, null, true);
    byId('workflow-summary').textContent = `Workflow failed: ${error.message}`;
  } finally {
    byId('run-workflow').disabled = false;
    byId('run-workflow').textContent = 'Run Workflow';
  }
}

function renderConversationList() {
  const listEl = byId('conversation-list');
  listEl.innerHTML = '';

  if (!state.conversations.length) {
    const empty = document.createElement('p');
    empty.className = 'chat-empty';
    empty.textContent = 'No saved conversations yet.';
    listEl.appendChild(empty);
    return;
  }

  for (const conversation of state.conversations) {
    const button = document.createElement('button');
    button.type = 'button';
    button.className = 'conversation-item';
    if (conversation.id === state.currentConversationId) {
      button.classList.add('active');
    }

    const title = document.createElement('p');
    title.className = 'conversation-title';
    title.textContent = conversation.title || 'Conversation';

    const preview = document.createElement('p');
    preview.className = 'conversation-preview';
    preview.textContent = truncate(conversation.last_message_preview || 'No assistant response yet.', 88);

    const updated = document.createElement('p');
    updated.className = 'conversation-updated';
    updated.textContent = `Updated ${fmtDate(conversation.updated_at)}`;

    button.appendChild(title);
    button.appendChild(preview);
    button.appendChild(updated);
    button.addEventListener('click', () => {
      loadCopilotConversation(conversation.id).catch((error) => {
        writeLog(`Conversation load failed: ${error.message}`, null, true);
      });
    });

    listEl.appendChild(button);
  }
}

function renderToolTraces(toolCalls) {
  const wrap = document.createElement('div');
  wrap.className = 'tool-trace-list';

  for (const toolCall of toolCalls) {
    const details = document.createElement('details');
    details.className = 'tool-trace';

    const summary = document.createElement('summary');
    const status = toolCall.error ? 'error' : 'ok';
    summary.textContent = `Tool: ${toolCall.name || 'unknown'} (${status})`;

    const pre = document.createElement('pre');
    pre.textContent = JSON.stringify(toolCall, null, 2);

    details.appendChild(summary);
    details.appendChild(pre);
    wrap.appendChild(details);
  }

  return wrap;
}

function renderChatMessages() {
  const chatEl = byId('chat-messages');
  chatEl.innerHTML = '';

  if (!state.currentMessages.length) {
    const empty = document.createElement('p');
    empty.className = 'chat-empty';
    empty.textContent =
      'Start a new conversation. Copilot will use your snapshot, sync status, and selected plan context.';
    chatEl.appendChild(empty);
    return;
  }

  for (const message of state.currentMessages) {
    const role = message.role === 'user' ? 'user' : 'assistant';
    const wrapper = document.createElement('article');
    wrapper.className = `message ${role}`;

    const meta = document.createElement('p');
    meta.className = 'message-meta';
    meta.textContent = `${role === 'user' ? 'You' : 'Copilot'} • ${fmtDate(message.created_at)}`;

    const content = document.createElement('p');
    content.className = 'message-content';
    content.textContent = String(message.content || '');

    wrapper.appendChild(meta);
    wrapper.appendChild(content);

    if (role === 'assistant') {
      const toolCalls = Array.isArray(message.metadata?.tool_calls) ? message.metadata.tool_calls : [];
      if (toolCalls.length) {
        wrapper.appendChild(renderToolTraces(toolCalls));
      }
    }

    chatEl.appendChild(wrapper);
  }

  chatEl.scrollTop = chatEl.scrollHeight;
}

function setCopilotBusy(isBusy) {
  state.copilotLoading = isBusy;
  byId('copilot-send').disabled = isBusy;
  byId('copilot-send').textContent = isBusy ? 'Thinking...' : 'Ask Copilot';
  byId('copilot-question').disabled = isBusy;
  byId('new-conversation').disabled = isBusy;
}

async function loadStatus() {
  const status = await fetchJson('/api/sync/status');
  renderSyncStatus(status);
}

async function loadSnapshot() {
  try {
    const snapshot = await fetchJson('/api/snapshot/latest');
    renderSnapshot(snapshot);
  } catch (error) {
    byId('snapshot-total').textContent = `Snapshot unavailable: ${error.message}`;
    byId('holdings-body').innerHTML = '<tr><td colspan="4">Run a sync to generate a snapshot.</td></tr>';
  }
}

async function loadSnapshotHistory() {
  try {
    const payload = await fetchJson('/api/snapshot/history?limit=20');
    renderSnapshotHistory(payload);
  } catch (error) {
    byId('snapshot-history-summary').textContent = `Snapshot history unavailable: ${error.message}`;
    byId('snapshot-history-body').innerHTML = '<tr><td colspan="3">Snapshot history unavailable.</td></tr>';
  }
}

async function loadInbox() {
  const payload = await fetchJson('/api/import/files');
  renderInboxFiles(payload.files || []);
}

async function refreshAll() {
  await Promise.all([loadStatus(), loadSnapshot(), loadSnapshotHistory(), loadInbox()]);
}

async function loadCopilotConversations(autoSelect = true) {
  const conversations = await fetchJson('/api/copilot/conversations?limit=80');
  state.conversations = Array.isArray(conversations) ? conversations : [];

  if (
    state.currentConversationId &&
    !state.conversations.some((conversation) => conversation.id === state.currentConversationId)
  ) {
    state.currentConversationId = null;
    state.currentMessages = [];
  }

  if (autoSelect && !state.currentConversationId && state.conversations.length) {
    state.currentConversationId = state.conversations[0].id;
  }

  renderConversationList();

  if (state.currentConversationId) {
    await loadCopilotConversation(state.currentConversationId);
  } else {
    renderChatMessages();
  }
}

async function loadCopilotConversation(conversationId) {
  if (!conversationId) return;
  const payload = await fetchJson(`/api/copilot/conversations/${encodeURIComponent(conversationId)}`);
  state.currentConversationId = payload.id;
  state.currentMessages = Array.isArray(payload.messages) ? payload.messages : [];
  renderConversationList();
  renderChatMessages();
}

function startNewConversation() {
  state.currentConversationId = null;
  state.currentMessages = [];
  renderConversationList();
  renderChatMessages();
  byId('copilot-question').focus();
}

async function runSync() {
  writeLog('Running manual sync...');
  try {
    const result = await fetchJson('/api/snapshot/sync', { method: 'POST' });
    writeLog('Sync completed.', result);
    await refreshAll();
  } catch (error) {
    writeLog(`Sync failed: ${error.message}`, null, true);
  }
}

async function importInboxFile() {
  const file = byId('inbox-file').value;
  if (!file) {
    writeLog('Select a CSV file from inbox first.', null, true);
    return;
  }

  const body = {
    path: file,
    dry_run: byId('inbox-dry-run').checked,
    archive_after_success: byId('inbox-archive').checked,
  };

  writeLog(`Importing inbox file ${file}...`, body);
  try {
    const result = await fetchJson('/api/import/csv', {
      method: 'POST',
      headers: { 'content-type': 'application/json' },
      body: JSON.stringify(body),
    });
    writeLog('Inbox import completed.', result);
    await refreshAll();
  } catch (error) {
    writeLog(`Inbox import failed: ${error.message}`, null, true);
  }
}

async function uploadAndImport(event) {
  event.preventDefault();
  const fileInput = byId('upload-file');
  const file = fileInput.files?.[0];

  if (!file) {
    writeLog('Choose a CSV file to upload.', null, true);
    return;
  }

  const formData = new FormData();
  formData.append('file', file);
  formData.append('dry_run', String(byId('upload-dry-run').checked));
  formData.append('archive_after_success', String(byId('upload-archive').checked));
  formData.append('delimiter', byId('upload-delimiter').value || ',');
  formData.append('default_data_source', byId('upload-source').value || 'YAHOO');
  formData.append('default_currency', byId('upload-currency').value || 'USD');

  writeLog(`Uploading and importing ${file.name}...`);
  try {
    const result = await fetchJson('/api/import/upload-csv', {
      method: 'POST',
      body: formData,
    });
    writeLog('Upload import completed.', result);
    fileInput.value = '';
    await refreshAll();
  } catch (error) {
    writeLog(`Upload import failed: ${error.message}`, null, true);
  }
}

async function submitCopilotQuestion(event) {
  event.preventDefault();
  if (state.copilotLoading) return;

  const questionInput = byId('copilot-question');
  const question = questionInput.value.trim();
  if (!question) return;

  state.currentMessages.push({
    role: 'user',
    content: question,
    created_at: new Date().toISOString(),
    metadata: {},
  });
  renderChatMessages();
  questionInput.value = '';

  const selectedPlanId = byId('copilot-plan').value || null;
  state.copilotPlanId = selectedPlanId || '';

  const payload = {
    question,
    conversation_id: state.currentConversationId,
    use_live_snapshot: byId('copilot-live-context').checked,
    plan_id: selectedPlanId,
  };

  setCopilotBusy(true);
  writeLog('Sending Copilot request...', payload);

  try {
    const result = await fetchJson('/api/copilot/chat', {
      method: 'POST',
      headers: { 'content-type': 'application/json' },
      body: JSON.stringify(payload),
    });

    state.currentConversationId = result.conversation_id;
    state.currentMessages.push({
      role: 'assistant',
      content: result.answer || '',
      created_at: result.created_at || new Date().toISOString(),
      metadata: {
        tool_calls: Array.isArray(result.tool_calls) ? result.tool_calls : [],
        model: result.model || null,
      },
    });
    renderChatMessages();

    writeLog('Copilot response received.', {
      conversation_id: result.conversation_id,
      tool_calls: Array.isArray(result.tool_calls) ? result.tool_calls.length : 0,
      model: result.model || null,
    });

    await loadCopilotConversations(false);
    await loadCopilotConversation(state.currentConversationId);
  } catch (error) {
    state.currentMessages.push({
      role: 'assistant',
      content: `Copilot request failed: ${error.message}`,
      created_at: new Date().toISOString(),
      metadata: {},
    });
    renderChatMessages();
    writeLog(`Copilot request failed: ${error.message}`, null, true);
  } finally {
    setCopilotBusy(false);
  }
}

function wireEvents() {
  byId('refresh-all').addEventListener('click', () => {
    refreshAll().catch((error) => writeLog(error.message, null, true));
  });
  byId('run-sync').addEventListener('click', runSync);
  byId('reload-inbox').addEventListener('click', () => {
    loadInbox().catch((error) => writeLog(error.message, null, true));
  });
  byId('reload-snapshot').addEventListener('click', () => {
    Promise.all([loadSnapshot(), loadSnapshotHistory()]).catch((error) => writeLog(error.message, null, true));
  });
  byId('import-inbox').addEventListener('click', importInboxFile);
  byId('upload-form').addEventListener('submit', uploadAndImport);
  byId('clear-log').addEventListener('click', () => {
    logEl.innerHTML = '';
  });

  byId('reload-conversations').addEventListener('click', () => {
    loadCopilotConversations(false).catch((error) => writeLog(error.message, null, true));
  });
  byId('new-conversation').addEventListener('click', startNewConversation);
  byId('copilot-form').addEventListener('submit', submitCopilotQuestion);

  byId('reload-plans').addEventListener('click', () => {
    loadPlans(false).catch((error) => writeLog(error.message, null, true));
  });
  byId('create-plan-form').addEventListener('submit', createPlan);
  byId('save-plan').addEventListener('click', savePlan);
  byId('save-plan-settings').addEventListener('click', savePlanSettings);
  byId('run-scenario-diff').addEventListener('click', runScenarioDiff);
  byId('apply-scenario-overrides').addEventListener('click', applyScenarioOverrides);
  byId('activate-plan').addEventListener('click', activatePlan);
  byId('refresh-plan-context').addEventListener('click', refreshPlanContext);
  byId('add-decision').addEventListener('click', addPlanDecision);
  byId('copilot-plan').addEventListener('change', (event) => {
    state.copilotPlanId = event.target.value || '';
    byId('workflow-plan').value = state.copilotPlanId;
  });
  byId('workflow-plan').addEventListener('change', (event) => {
    state.copilotPlanId = event.target.value || '';
    byId('copilot-plan').value = state.copilotPlanId;
  });
  byId('workflow-form').addEventListener('submit', runWorkflow);
  byId('workflow-template').addEventListener('change', () => updateWorkflowParamsEditor(false));
}

async function boot() {
  wireEvents();
  clearPlanDetail();
  renderChatMessages();
  await Promise.all([refreshAll(), loadCopilotConversations(true), loadPlans(true), loadWorkflowTemplates()]);
  writeLog('BuildWealth UI ready with Copilot, Plan Workspace, and Workflow Templates.');
}

boot().catch((error) => {
  writeLog(`Initialization failed: ${error.message}`, null, true);
});
