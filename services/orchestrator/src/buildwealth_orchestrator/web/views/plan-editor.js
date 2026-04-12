import { fetchJson } from '../lib/api.js';
import { state, PLAN_SETTING_FIELDS, DIFF_SETTING_FIELDS } from '../lib/state.js';
import { byId, fmtCurrency, fmtDate, writeLog } from '../lib/utils.js';
import { collectSettingsPayload, setSettingsInputs } from '../lib/components.js';

function setControlsEnabled(enabled) {
  ['activate-plan', 'refresh-plan-context', 'save-plan', 'save-plan-timeline', 'save-plan-settings', 'run-scenario-diff', 'apply-scenario-overrides', 'add-decision', 'plan-markdown', 'plan-tasks', 'plan-timeline', 'decision-summary', 'decision-rationale', 'decision-status'].forEach(id => { const el = byId(id); if (el) el.disabled = !enabled; });
  for (const f of [...PLAN_SETTING_FIELDS, ...DIFF_SETTING_FIELDS]) { const el = byId(f.inputId); if (el) el.disabled = !enabled; }
}

export function clearDetail() {
  state.currentPlanDetail = null;
  byId('plan-meta').textContent = 'Select a plan to view details.';
  byId('plan-settings-meta').textContent = 'Blank values use global defaults from planner configuration.';
  ['plan-markdown', 'plan-tasks', 'plan-timeline', 'plan-context', 'scenario-diff-output', 'artifact-content'].forEach(id => { const el = byId(id); if (el) el.value = ''; });
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
  byId('plan-timeline').value = d.files?.timeline_json || '';
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

  const baseIncome = diff?.base_result?.income_projection;
  const candidateIncome = diff?.candidate_result?.income_projection;
  lines.push('', 'Income Projection Context:');
  if (!baseIncome && !candidateIncome) {
    lines.push('- Not available.');
  } else {
    lines.push(`- Base: ${describeIncomeProjection(baseIncome)}`);
    lines.push(`- Candidate: ${describeIncomeProjection(candidateIncome)}`);
  }

  const baseExpenses = diff?.base_result?.expense_projection;
  const candidateExpenses = diff?.candidate_result?.expense_projection;
  lines.push('', 'Expense Projection Context:');
  if (!baseExpenses && !candidateExpenses) {
    lines.push('- Not available.');
  } else {
    lines.push(`- Base: ${describeExpenseProjection(baseExpenses)}`);
    lines.push(`- Candidate: ${describeExpenseProjection(candidateExpenses)}`);
  }

  const baseDebt = diff?.base_result?.debt_projection;
  const candidateDebt = diff?.candidate_result?.debt_projection;
  lines.push('', 'Debt Projection Context:');
  if (!baseDebt && !candidateDebt) {
    lines.push('- Not available.');
  } else {
    lines.push(`- Base: ${describeDebtProjection(baseDebt)}`);
    lines.push(`- Candidate: ${describeDebtProjection(candidateDebt)}`);
  }

  const baseTimeline = diff?.base_result?.timeline_projection;
  const candidateTimeline = diff?.candidate_result?.timeline_projection;
  lines.push('', 'Timeline Impact Context:');
  if (!baseTimeline && !candidateTimeline) {
    lines.push('- Not available.');
  } else {
    lines.push(`- Base: ${describeTimelineProjection(baseTimeline)}`);
    lines.push(`- Candidate: ${describeTimelineProjection(candidateTimeline)}`);
  }

  const baseSocialSecurity = diff?.base_result?.social_security_projection;
  const candidateSocialSecurity = diff?.candidate_result?.social_security_projection;
  lines.push('', 'Social Security Context:');
  if (!baseSocialSecurity && !candidateSocialSecurity) {
    lines.push('- Not available.');
  } else {
    lines.push(`- Base: ${describeSocialSecurityProjection(baseSocialSecurity)}`);
    lines.push(`- Candidate: ${describeSocialSecurityProjection(candidateSocialSecurity)}`);
  }

  const baseRmd = diff?.base_result?.rmd_projection;
  const candidateRmd = diff?.candidate_result?.rmd_projection;
  lines.push('', 'RMD Context:');
  if (!baseRmd && !candidateRmd) {
    lines.push('- Not available.');
  } else {
    lines.push(`- Base: ${describeRmdProjection(baseRmd)}`);
    lines.push(`- Candidate: ${describeRmdProjection(candidateRmd)}`);
  }

  const mc = diff?.monte_carlo_delta || {};
  lines.push('', 'Monte Carlo Delta:', `- P10: ${fmtCurrency(mc.delta_p10_future_value_usd)}`, `- P50: ${fmtCurrency(mc.delta_p50_future_value_usd)}`, `- P90: ${fmtCurrency(mc.delta_p90_future_value_usd)}`);
  lines.push('', 'Raw Payload:', JSON.stringify(diff, null, 2));
  return lines.join('\n');
}

function describeIncomeProjection(projection) {
  if (!projection || typeof projection !== 'object') return 'Not available';
  const firstYear = fmtCurrency(projection.first_year_gross_income_usd);
  const finalYear = fmtCurrency(projection.final_year_gross_income_usd);
  const years = Number(projection.years);
  const yearsLabel = Number.isFinite(years) && years > 0 ? `${Math.trunc(years)}y` : 'n/a';
  const growth = Number(projection.annualized_income_growth_rate);
  const growthLabel = Number.isFinite(growth) ? `${(growth * 100).toFixed(2)}%` : 'n/a';
  return `${firstYear} -> ${finalYear} (${yearsLabel}, annualized ${growthLabel})`;
}

function describeExpenseProjection(projection) {
  if (!projection || typeof projection !== 'object') return 'Not available';
  const firstYear = fmtCurrency(projection.first_year_expenses_usd);
  const finalYear = fmtCurrency(projection.final_year_expenses_usd);
  const years = Number(projection.years);
  const yearsLabel = Number.isFinite(years) && years > 0 ? `${Math.trunc(years)}y` : 'n/a';
  const growth = Number(projection.annualized_expense_growth_rate);
  const growthLabel = Number.isFinite(growth) ? `${(growth * 100).toFixed(2)}%` : 'n/a';
  return `${firstYear} -> ${finalYear} (${yearsLabel}, annualized ${growthLabel})`;
}

function describeDebtProjection(projection) {
  if (!projection || typeof projection !== 'object') return 'Not available';
  const selected = projection.selected_scenario || {};
  const strategy = String(projection.strategy || selected.strategy || 'minimum');
  const months = Number(selected.months_to_payoff);
  const remaining = fmtCurrency(selected.remaining_balance_usd);
  const interest = fmtCurrency(selected.total_interest_paid_usd);
  const paidOffLabel = selected.paid_off ? 'paid off' : `remaining ${remaining}`;
  const monthsLabel = Number.isFinite(months) && months > 0 ? `${Math.trunc(months)}m` : 'n/a';
  return `${strategy} (${monthsLabel}, ${paidOffLabel}, interest ${interest})`;
}

function describeTimelineProjection(projection) {
  if (!projection || typeof projection !== 'object') return 'Not available';
  const eventsCount = Number(projection.events_count);
  const years = Number(projection.years);
  const firstYearNet = fmtCurrency(projection.yearly_points?.[0]?.net_cashflow_impact_usd);
  const cumulative = fmtCurrency(projection.cumulative_net_cashflow_impact_usd);
  const eventsLabel = Number.isFinite(eventsCount) ? `${Math.trunc(eventsCount)} event(s)` : 'n/a events';
  const yearsLabel = Number.isFinite(years) ? `${Math.trunc(years)}y` : 'n/a';
  return `${eventsLabel}, first-year net ${firstYearNet}, cumulative net ${cumulative} (${yearsLabel})`;
}

function describeSocialSecurityProjection(projection) {
  if (!projection || typeof projection !== 'object') return 'Not available';
  const selectedAge = Number(projection.selected_claiming_age);
  const optimalAge = Number(projection.optimal_claiming_age);
  const annual = fmtCurrency(projection.selected_annual_benefit_usd);
  const fraMonthly = fmtCurrency(projection.fra_monthly_benefit_usd);
  const selectedAgeLabel = Number.isFinite(selectedAge) ? `age ${Math.trunc(selectedAge)}` : 'n/a';
  const optimalAgeLabel = Number.isFinite(optimalAge) ? `optimal ${Math.trunc(optimalAge)}` : 'optimal n/a';
  return `${selectedAgeLabel} (${optimalAgeLabel}), annual ${annual}, FRA monthly ${fraMonthly}`;
}

function describeRmdProjection(projection) {
  if (!projection || typeof projection !== 'object') return 'Not available';
  const startAge = Number(projection.rmd_start_age);
  const totalProjected = fmtCurrency(projection.total_projected_rmds_usd);
  const firstYear = fmtCurrency(projection.yearly_points?.[0]?.total_rmd_usd);
  const eligibleAccounts = Number(projection.eligible_account_count);
  const startAgeLabel = Number.isFinite(startAge) ? `start age ${Math.trunc(startAge)}` : 'start age n/a';
  const accountLabel = Number.isFinite(eligibleAccounts) ? `${Math.trunc(eligibleAccounts)} account(s)` : 'n/a account(s)';
  return `${startAgeLabel}, first-year ${firstYear}, projected total ${totalProjected}, ${accountLabel}`;
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

  byId('save-plan-timeline').addEventListener('click', async () => {
    if (!state.currentPlanId) { writeLog('Select a plan first.', null, true); return; }
    const raw = byId('plan-timeline').value.trim();
    let payload;
    try {
      payload = raw ? JSON.parse(raw) : { events: [], retirement: {} };
    } catch (e) {
      writeLog(`Timeline JSON is invalid: ${e.message}`, null, true);
      return;
    }
    writeLog('Saving timeline...', payload);
    try {
      await fetchJson(`/api/plans/${encodeURIComponent(state.currentPlanId)}/timeline`, {
        method: 'PUT',
        headers: { 'content-type': 'application/json' },
        body: JSON.stringify(payload),
      });
      state.currentPlanDetail = await fetchJson(`/api/plans/${encodeURIComponent(state.currentPlanId)}`);
      renderDetail();
      await refreshPlans();
      writeLog('Timeline saved.');
    } catch (e) {
      writeLog(`Save timeline failed: ${e.message}`, null, true);
    }
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
