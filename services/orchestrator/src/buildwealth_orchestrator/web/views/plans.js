import { fetchJson } from '../lib/api.js';
import { state, PLAN_SETTING_FIELDS, DIFF_SETTING_FIELDS } from '../lib/state.js';
import { byId, fmtCurrency, fmtDate, writeLog, formatNumericInput } from '../lib/utils.js';
import { settingsGridHtml, collectSettingsPayload, setSettingsInputs } from '../lib/components.js';
import { initEditor, renderDetail, clearDetail } from './plan-editor.js';

export const id = 'plans';
export const label = 'Plans';
export const icon = '<svg viewBox="0 0 20 20" fill="none" stroke="currentColor" stroke-width="1.6"><path d="M5 2h10a1 1 0 011 1v14a1 1 0 01-1 1H5a1 1 0 01-1-1V3a1 1 0 011-1z"/><path d="M7 6h6M7 9h6M7 12h4"/></svg>';

export function template() {
  return `
    <div class="view-header"><h2>Plan Workspace</h2><button class="ghost small" id="reload-plans">Reload</button></div>
    <p class="hint">Create and maintain long-lived planning documents. Copilot can use the active or selected plan as context.</p>
    <form id="create-plan-form" class="create-plan-row">
      <label class="field"><span>New Plan Title</span><input type="text" id="new-plan-title" placeholder="e.g. 2026 Contribution Optimization" required /></label>
      <label class="field"><span>Description</span><input type="text" id="new-plan-description" placeholder="One-line objective" /></label>
      <button class="primary" type="submit">Create Plan</button>
    </form>
    <div class="split-layout">
      <aside class="sidebar-panel">
        <p class="sidebar-label">Plans</p>
        <div id="plan-list" class="sidebar-list"></div>
      </aside>
      <section class="main-panel plan-editor">
        <div class="plan-meta-row"><p id="plan-meta" class="hint">Select a plan to view details.</p>
          <div class="header-actions"><button class="ghost small" id="activate-plan" disabled>Set Active</button><button class="ghost small" id="refresh-plan-context" disabled>Refresh Context</button><button class="primary small" id="save-plan" disabled>Save Plan</button></div>
        </div>
        <div class="view-header"><h3>Top 3 Next Actions</h3><button class="ghost small" id="open-plan-recommendations" disabled>Open Inbox</button></div>
        <p class="hint tight" id="plan-next-actions-summary">Select a plan to load ranked next actions.</p>
        <div id="plan-next-actions" class="item-list"></div>
        <div class="view-header"><h3>Closure Calibration Summary</h3><button class="ghost small" id="generate-plan-closure-summary" disabled>Generate Artifact</button></div>
        <p class="hint tight" id="plan-closure-summary-status">Select a plan to generate recommendation closure analytics.</p>
        <div id="plan-closure-summary-details" class="item-list"></div>
        <label class="field"><span>Plan Markdown</span><textarea id="plan-markdown" rows="12" placeholder="Plan markdown will appear here." disabled></textarea></label>
        <label class="field"><span>Tasks Markdown</span><textarea id="plan-tasks" rows="6" placeholder="Task checklist markdown." disabled></textarea></label>
        <div class="view-header"><h3>Timeline Events</h3><button class="primary small" id="save-plan-timeline" disabled>Save Timeline</button></div>
        <p class="hint tight">Use the event editor for common timeline modeling, or edit JSON directly for advanced payloads.</p>
        <div class="inline-builder">
          <input type="date" id="timeline-event-date" disabled />
          <input type="text" id="timeline-event-label" placeholder="Event label" disabled />
          <select id="timeline-event-type" disabled>
            <option value="milestone">Milestone</option>
            <option value="purchase">Purchase</option>
            <option value="windfall">Windfall</option>
            <option value="job_change">Job Change</option>
            <option value="retirement">Retirement</option>
          </select>
          <select id="timeline-event-impact-type" disabled>
            <option value="">Impact (Auto)</option>
            <option value="income">Income</option>
            <option value="expense">Expense</option>
            <option value="portfolio">Portfolio</option>
            <option value="contribution">Contribution</option>
            <option value="debt_payment">Debt Payment</option>
          </select>
          <input type="number" id="timeline-event-amount" step="0.01" placeholder="Amount USD" disabled />
          <select id="timeline-event-frequency" disabled>
            <option value="one_time">One Time</option>
            <option value="monthly">Monthly</option>
            <option value="yearly">Yearly</option>
          </select>
          <input type="date" id="timeline-event-end-date" disabled />
          <input type="text" id="timeline-event-account-id" placeholder="Account ID (optional)" disabled />
          <input type="text" id="timeline-event-notes" placeholder="Notes (optional)" disabled />
          <button class="ghost small" id="add-timeline-event" type="button" disabled>Add Event</button>
        </div>
        <div class="table-wrap">
          <table>
            <thead><tr><th>Date</th><th>Label</th><th>Type</th><th>Impact</th><th>Amount</th><th>Frequency</th><th>End</th><th>Account</th><th>Notes</th><th></th></tr></thead>
            <tbody id="plan-timeline-events-body"><tr><td colspan="10">No timeline events yet.</td></tr></tbody>
          </table>
        </div>
        <h4 class="section-title">Retirement Timeline Inputs</h4>
        <div class="settings-grid">
          <label class="field"><span>Target Retirement Age</span><input type="number" id="timeline-retirement-age" min="18" max="100" step="1" placeholder="Optional" disabled /></label>
          <label class="field"><span>Withdrawal Strategy</span><input type="text" id="timeline-withdrawal-strategy" placeholder="e.g. four_percent_rule" disabled /></label>
          <label class="field"><span>SS Birth Year</span><input type="number" id="timeline-ss-birth-year" min="1900" max="2500" step="1" placeholder="Optional" disabled /></label>
          <label class="field"><span>SS Claiming Age</span><input type="number" id="timeline-ss-claiming-age" min="62" max="70" step="1" placeholder="Optional" disabled /></label>
          <label class="field"><span>SS Life Expectancy Age</span><input type="number" id="timeline-ss-life-expectancy-age" min="67" max="120" step="1" placeholder="Optional" disabled /></label>
          <label class="field"><span>SS FRA Monthly Benefit</span><input type="number" id="timeline-ss-fra-benefit" min="0" step="0.01" placeholder="Optional" disabled /></label>
          <label class="field"><span>SS Estimated Annual Earnings</span><input type="number" id="timeline-ss-annual-earnings" min="0" step="0.01" placeholder="Optional" disabled /></label>
          <label class="field"><span>RMD Birth Year</span><input type="number" id="timeline-rmd-birth-year" min="1900" max="2500" step="1" placeholder="Optional" disabled /></label>
          <label class="field"><span>RMD Start Age</span><input type="number" id="timeline-rmd-start-age" min="72" max="120" step="1" placeholder="Optional" disabled /></label>
        </div>
        <label class="field"><span>Timeline JSON (Advanced)</span><textarea id="plan-timeline" rows="10" placeholder='{"events":[...],"retirement":{...}}' disabled></textarea></label>
        <div class="view-header"><h3>Assumption Sets</h3><button class="primary small" id="save-plan-assumption-sets" disabled>Save Assumption Sets</button></div>
        <p class="hint tight">Edit named assumption sets JSON. Active set is applied by default when running scenarios.</p>
        <label class="field"><span>Assumption Sets JSON</span><textarea id="plan-assumption-sets" rows="10" placeholder='{"active_assumption_set_id":"default","sets":[...]}' disabled></textarea></label>
        <div class="view-header"><h3>Contribution Rules</h3><button class="primary small" id="save-plan-contribution-rules" disabled>Save Contribution Rules</button></div>
        <p class="hint tight">Ignidash-style ranked allocation rules. Use the editor for common cases, or JSON for advanced payloads.</p>
        <div class="settings-grid">
          <label class="field"><span>Base Rule</span><select id="contribution-base-rule" disabled><option value="save">Save</option><option value="spend">Spend</option></select></label>
          <label class="field"><span>Profile ID</span><input type="text" id="contribution-profile-id" placeholder="Optional profile override" disabled /></label>
          <label class="field"><span>Employer Match Target (USD)</span><input type="number" id="contribution-employer-match-target" min="0" step="0.01" placeholder="6000" disabled /></label>
          <label class="field"><span>Age</span><input type="number" id="contribution-age" min="0" max="120" step="1" placeholder="35" disabled /></label>
        </div>
        <div class="inline-builder">
          <input type="text" id="contribution-rule-account-id" placeholder="Account ID" disabled />
          <input type="number" id="contribution-rule-rank" min="1" step="1" placeholder="Rank" disabled />
          <select id="contribution-rule-amount-type" disabled>
            <option value="unlimited">Unlimited</option>
            <option value="dollarAmount">Dollar Amount</option>
            <option value="percentRemaining">Percent Remaining</option>
          </select>
          <input type="number" id="contribution-rule-amount-value" min="0" step="0.01" placeholder="Amount / %" disabled />
          <input type="number" id="contribution-rule-employer-match" min="0" step="0.01" placeholder="Employer Match (optional)" disabled />
          <input type="number" id="contribution-rule-max-balance" min="0" step="0.01" placeholder="Max Balance (optional)" disabled />
          <label class="inline-check"><input type="checkbox" id="contribution-rule-mega-backdoor" disabled /> Mega Backdoor</label>
          <label class="inline-check"><input type="checkbox" id="contribution-rule-disabled" disabled /> Disabled</label>
          <button class="ghost small" id="add-contribution-rule" type="button" disabled>Add Rule</button>
        </div>
        <div class="table-wrap">
          <table>
            <thead><tr><th>Rank</th><th>Account</th><th>Type</th><th>Value</th><th>Employer Match</th><th>Max Balance</th><th>Mega</th><th>Disabled</th><th></th></tr></thead>
            <tbody id="plan-contribution-rules-body"><tr><td colspan="9">No contribution rules yet.</td></tr></tbody>
          </table>
        </div>
        <label class="field"><span>Contribution Rules JSON (Advanced)</span><textarea id="plan-contribution-rules" rows="10" placeholder='{"base_rule":{"type":"save"},"rules":[...]}' disabled></textarea></label>
        <label class="field"><span>Context Snapshot</span><textarea id="plan-context" rows="6" readonly></textarea></label>
        <div class="view-header"><h3>Plan Settings</h3><button class="primary small" id="save-plan-settings" disabled>Save Settings</button></div>
        <p class="hint tight" id="plan-settings-meta">Blank values use global defaults from planner configuration.</p>
        <div class="settings-grid">${settingsGridHtml(PLAN_SETTING_FIELDS)}</div>
        <div class="view-header"><h3>Scenario Diff</h3>
          <div class="header-actions"><button class="primary small" id="run-scenario-diff" disabled>Run Diff</button><button class="ghost small" id="apply-scenario-overrides" disabled>Apply Overrides</button></div>
        </div>
        <p class="hint tight">Enter only fields you want to compare. Overrides do not persist unless applied.</p>
        <div class="settings-grid">
          <label class="field"><span>Base Assumption Set</span><select id="diff-assumption-set-id" disabled></select></label>
          <label class="field"><span>Candidate Assumption Set</span><select id="diff-candidate-assumption-set-id" disabled></select></label>
        </div>
        <div class="settings-grid">${settingsGridHtml(DIFF_SETTING_FIELDS)}</div>
        <p class="hint tight" id="scenario-diff-summary">No scenario diff run yet.</p>
        <label class="field"><span>Scenario Diff Output</span><textarea id="scenario-diff-output" rows="8" readonly></textarea></label>
        <div class="view-header"><h3>Withdrawal Strategy Compare</h3><button class="primary small" id="run-withdrawal-strategy-compare" disabled>Run Compare</button></div>
        <p class="hint tight">Compare retirement withdrawal strategies using the active plan settings, timeline, and selected assumption set.</p>
        <div class="settings-grid">
          <label class="field"><span>Assumption Set</span><select id="withdrawal-assumption-set-id" disabled></select></label>
          <label class="field"><span>Portfolio Value Override</span><input type="number" id="withdrawal-current-portfolio-value" step="0.01" placeholder="Optional current portfolio value" disabled /></label>
          <label class="field"><span>Strategies</span><input type="text" id="withdrawal-strategies" placeholder="cashflow_only,four_percent_rule,dynamic_guardrails,bond_tent,bucket_strategy" disabled /></label>
        </div>
        <label class="field"><span>Include Raw Scenario Payloads</span><input type="checkbox" id="withdrawal-include-raw-results" disabled /></label>
        <p class="hint tight" id="withdrawal-strategy-compare-summary">No withdrawal strategy comparison run yet.</p>
        <label class="field"><span>Withdrawal Strategy Compare Output</span><textarea id="withdrawal-strategy-compare-output" rows="8" readonly></textarea></label>
        <div class="view-header"><h3>Scenario Branch (Life Events)</h3><div class="header-actions"><button class="ghost small" id="load-branch-template" disabled>Load Template</button><button class="primary small" id="run-scenario-branch" disabled>Run Branch</button></div></div>
        <p class="hint tight">Model uncertain life events and compare branch outcomes against the base plan.</p>
        <div class="settings-grid">
          <label class="field"><span>Saved Template</span><select id="branch-template-id" disabled><option value="">None</option></select></label>
          <label class="field"><span>Branch Name</span><input type="text" id="scenario-branch-name" placeholder="e.g. Job Loss 6 Months" disabled /></label>
          <label class="field"><span>Assumption Set</span><select id="branch-assumption-set-id" disabled></select></label>
        </div>
        <label class="field"><span>Branch Events JSON</span><textarea id="scenario-branch-events" rows="8" placeholder='[{"label":"Job Loss","event_type":"job_change","impact_type":"income","amount_usd":-7500,"recurring_frequency":"monthly","start_year_offset":0,"duration_months":6}]' disabled></textarea></label>
        <div class="view-header"><h4>Branch Templates</h4><button class="primary small" id="save-plan-branch-templates" disabled>Save Branch Templates</button></div>
        <p class="hint tight">Persist reusable branch presets to avoid retyping common life-event scenarios.</p>
        <div class="inline-builder">
          <input type="text" id="research-bridge-symbols" placeholder="Optional symbols (e.g. NVDA,VTI)" disabled />
          <button class="ghost small" id="pin-watchlist-branch-template" type="button" disabled>Pin Watchlist Research</button>
          <button class="ghost small" id="open-latest-research-bridge-artifact" type="button" disabled>Open Latest Bridge Artifact</button>
        </div>
        <p class="hint tight">Pins watchlist thesis, target-price, and tag context into the selected branch template (or a research bridge template).</p>
        <p class="hint tight" id="research-bridge-summary">No watchlist research bridge activity recorded yet.</p>
        <label class="field"><span>Branch Templates JSON</span><textarea id="plan-branch-templates" rows="10" placeholder='{"default_template_id":"job_loss_6_months","templates":[...]}' disabled></textarea></label>
        <p class="hint tight" id="scenario-branch-summary">No scenario branch run yet.</p>
        <label class="field"><span>Scenario Branch Output</span><textarea id="scenario-branch-output" rows="8" readonly></textarea></label>
        <div class="view-header"><h3>Projection Visuals</h3><div class="header-actions"><button class="ghost small" id="refresh-projection-profile" disabled>Refresh Profile Inputs</button></div></div>
        <p class="hint tight">Visualize long-range net worth and account-level balance projections from the latest scenario run.</p>
        <div class="settings-grid">
          <label class="field"><span>Projection Source</span><select id="projection-source" disabled><option value="">No scenario data yet</option></select></label>
          <label class="field"><span>Scenario Label</span><select id="projection-scenario-label" disabled><option value="baseline">Baseline</option><option value="optimistic">Optimistic</option><option value="conservative">Conservative</option><option value="hsa_delta">HSA Delta</option></select></label>
          <label class="field"><span>Account Metric</span><select id="projection-account-metric" disabled><option value="ending_balance_usd">Ending Balance</option><option value="contribution_usd">Contributions</option><option value="growth_usd">Growth</option></select></label>
        </div>
        <p class="hint tight" id="projection-summary">Run a scenario diff or branch to populate projection visuals.</p>
        <div class="history-chart-card projection-chart-card">
          <p class="hint tight">Net worth view includes portfolio balance, debt trajectory, and projected physical asset value.</p>
          <svg id="plan-net-worth-chart" viewBox="0 0 760 220" role="img" aria-label="Plan net worth projection chart"></svg>
        </div>
        <div class="history-chart-card projection-chart-card">
          <p class="hint tight">Stacked account-type projections by selected metric.</p>
          <svg id="plan-account-type-chart" viewBox="0 0 760 220" role="img" aria-label="Plan account-type projection chart"></svg>
          <div id="plan-account-type-legend" class="projection-legend"></div>
        </div>
        <h3 class="section-title">Per-Account Projection Summary</h3>
        <div class="table-wrap"><table><thead><tr><th>Account</th><th>Type</th><th>Final Balance</th><th>Contributions</th><th>Growth</th><th>Withdrawals</th></tr></thead><tbody id="projection-account-body"><tr><td colspan="6">No projection data yet.</td></tr></tbody></table></div>
        <h3 class="section-title">Decisions</h3>
        <div class="decision-form">
          <label class="field"><span>Decision</span><input type="text" id="decision-summary" placeholder="Decision summary" disabled /></label>
          <label class="field"><span>Rationale</span><input type="text" id="decision-rationale" placeholder="Why" disabled /></label>
          <label class="field"><span>Status</span><input type="text" id="decision-status" value="proposed" disabled /></label>
          <button class="ghost small" id="add-decision" disabled>Add</button>
        </div>
        <div class="table-wrap"><table><thead><tr><th>When</th><th>Status</th><th>Decision</th><th>Rationale</th></tr></thead><tbody id="plan-decisions-body"></tbody></table></div>
        <h3 class="section-title">Artifacts</h3>
        <div class="table-wrap"><table><thead><tr><th>When</th><th>Title</th><th>File</th><th>Action</th></tr></thead><tbody id="plan-artifacts-body"></tbody></table></div>
        <label class="field"><span>Artifact Content</span><textarea id="artifact-content" rows="8" readonly></textarea></label>
      </section>
    </div>`;
}

function renderList() {
  const el = byId('plan-list');
  el.innerHTML = '';
  if (!state.plans.length) { el.innerHTML = '<p class="empty-text">No plans yet.</p>'; return; }
  for (const plan of state.plans) {
    const btn = document.createElement('button');
    btn.type = 'button';
    btn.className = `sidebar-item${plan.id === state.currentPlanId ? ' active' : ''}`;
    btn.innerHTML = `<p class="sidebar-item-title">${plan.is_active ? `${plan.title} (Active)` : plan.title}</p><p class="sidebar-item-meta">Updated ${fmtDate(plan.updated_at)}</p>`;
    btn.addEventListener('click', () => loadPlan(plan.id).catch(e => writeLog(`Plan load failed: ${e.message}`, null, true)));
    el.appendChild(btn);
  }
}

export async function loadPlans(autoSelect = true) {
  const plans = await fetchJson('/api/plans?limit=200');
  state.plans = Array.isArray(plans) ? plans : [];
  if (state.currentPlanId && !state.plans.some(p => p.id === state.currentPlanId)) { state.currentPlanId = null; state.currentPlanDetail = null; }
  if (autoSelect && !state.currentPlanId && state.plans.length) {
    const active = state.plans.find(p => p.is_active);
    state.currentPlanId = active ? active.id : state.plans[0].id;
  }
  renderList();
  if (state.currentPlanId) await loadPlan(state.currentPlanId);
  else clearDetail();
}

async function loadPlan(planId) {
  if (!planId) return;
  const detail = await fetchJson(`/api/plans/${encodeURIComponent(planId)}`);
  state.currentPlanId = detail.id;
  state.currentPlanDetail = detail;
  state.copilotPlanId = detail.id;
  renderList();
  renderDetail();
}

async function createPlan(event) {
  event.preventDefault();
  const titleEl = byId('new-plan-title');
  const descEl = byId('new-plan-description');
  const title = titleEl.value.trim();
  if (!title) return;
  writeLog('Creating plan...', { title });
  try {
    const detail = await fetchJson('/api/plans', { method: 'POST', headers: { 'content-type': 'application/json' }, body: JSON.stringify({ title, description: descEl.value.trim() }) });
    titleEl.value = ''; descEl.value = '';
    state.currentPlanId = detail.id;
    state.currentPlanDetail = detail;
    state.copilotPlanId = detail.id;
    await loadPlans(false);
    renderDetail();
    writeLog('Plan created.', { id: detail.id });
  } catch (e) { writeLog(`Create failed: ${e.message}`, null, true); }
}

export function init() {
  clearDetail();
  initEditor(() => loadPlans(false));
  byId('reload-plans').addEventListener('click', () => loadPlans(false).catch(e => writeLog(e.message, null, true)));
  byId('create-plan-form').addEventListener('submit', createPlan);
  loadPlans(true);
}
