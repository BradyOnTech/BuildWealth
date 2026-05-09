// Movement IIB — Simulations.
// Bounded comparison surface for reviewing plan-setting changes before decisions.

import { html, raw, esc } from '../../lib/dom.js';
import { fmtPctSigned, fmtUsd, fmtUsdSigned } from '../../lib/format.js';

export const SCENARIO_FIELDS = [
  { key: 'annual_contribution_usd', label: 'Annual contribution', type: 'money' },
  { key: 'expected_return_baseline', label: 'Expected return', type: 'percent' },
  { key: 'inflation_rate', label: 'Inflation', type: 'percent' },
  { key: 'marginal_tax_rate', label: 'Marginal tax', type: 'percent' },
  { key: 'years', label: 'Years horizon', type: 'integer' },
  { key: 'current_portfolio_value_usd', label: 'Portfolio value override', type: 'money', requestKey: 'current_portfolio_value_usd' },
];

const COMPARE_FIELD_KEYS = new Set([
  'annual_contribution_usd',
  'expected_return_baseline',
  'inflation_rate',
  'marginal_tax_rate',
  'years',
]);

export function buildScenarioDiffPayload(draft = {}) {
  const payload = { compare_settings: {} };
  for (const field of SCENARIO_FIELDS) {
    if (!Object.prototype.hasOwnProperty.call(draft, field.key)) continue;
    const value = parseScenarioValue(field, draft[field.key]);
    if (value == null) continue;
    if (COMPARE_FIELD_KEYS.has(field.key)) {
      payload.compare_settings[field.key] = value;
    } else if (field.requestKey) {
      payload[field.requestKey] = value;
    }
  }

  const assumptionSetId = clean(draft.assumption_set_id);
  const candidateAssumptionSetId = clean(draft.candidate_assumption_set_id);
  if (assumptionSetId) payload.assumption_set_id = assumptionSetId;
  if (candidateAssumptionSetId) payload.candidate_assumption_set_id = candidateAssumptionSetId;
  return payload;
}

export function renderScenarios(plan = {}, state = {}, assumptionState = {}) {
  const draft = objectValue(state.draft);
  const result = objectValue(state.result);
  const assumptionSets = normalizeAssumptionSets(assumptionState.assumptionSets);
  const savedState = state.savedSimulations || {};
  const hasResult = Boolean(Object.keys(result).length);
  const focusId = clean(state.focusedRecommendationId);
  const planId = clean(plan.id);

  return html`
    <section class="plan-scenarios" data-plan-section="scenarios">
      <header class="section-head compact">
        <span class="section-eyebrow">Simulations</span>
        <h2 class="section-title">Experiment before deciding.</h2>
        <p class="section-lede">Test a bounded assumption change against the current plan. Saving a result creates an immutable Saved Simulation.</p>
      </header>

      ${state.error ? html`<p class="error-banner">${esc(state.error)}</p>` : ''}

      <div class="scenario-grid" data-form="plan-scenario-diff">
        ${raw(SCENARIO_FIELDS.map(field => renderScenarioField(field, plan, draft)).join(''))}
        ${renderAssumptionPicker('assumption_set_id', 'Base assumption set', assumptionSets, draft)}
        ${renderAssumptionPicker('candidate_assumption_set_id', 'Candidate assumption set', assumptionSets, draft)}
      </div>

      <div class="scenario-actions">
        <button class="btn btn-primary" data-scenario-action="run" ${state.busy ? 'disabled' : ''}>
          ${state.busy ? 'Running...' : 'Run simulation'}
        </button>
        ${state.dirty ? html`<span class="marginalia">Simulation inputs are staged for review.</span>` : html`<span class="marginalia">Stage an override to compare.</span>`}
      </div>

      ${hasResult ? raw(renderScenarioResult(plan, result, { focusId, planId })) : ''}
      ${raw(renderSavedSimulations(planId, savedState))}
    </section>
  `;
}

function renderScenarioField(field, plan = {}, draft = {}) {
  const value = draftValue(field, plan, draft);
  const current = currentValueLabel(field, plan);
  return html`
    <label class="scenario-field">
      <span class="assumption-label">${esc(field.label)}</span>
      <input
        data-scenario-field="${esc(field.key)}"
        type="number"
        step="${field.type === 'integer' ? '1' : '0.1'}"
        inputmode="decimal"
        value="${esc(value)}"
      />
      <span class="assumption-current">${esc(current)}</span>
    </label>
  `;
}

function renderAssumptionPicker(key, label, assumptionSets, draft = {}) {
  const value = clean(draft[key]);
  const sets = assumptionSets.sets.length
    ? assumptionSets.sets
    : [{ id: '', name: 'Current plan settings' }];
  return html`
    <label class="scenario-field">
      <span class="assumption-label">${esc(label)}</span>
      <select data-scenario-field="${esc(key)}">
        <option value="">Current plan settings</option>
        ${sets.map(set => {
          const id = clean(set.id);
          if (!id) return '';
          return html`<option value="${esc(id)}" ${id === value ? 'selected' : ''}>${esc(clean(set.name) || id)}</option>`;
        })}
      </select>
      <span class="assumption-current">${assumptionSets.sets.length} saved set${assumptionSets.sets.length === 1 ? '' : 's'}</span>
    </label>
  `;
}

function renderScenarioResult(plan, result, { focusId = '', planId = '' } = {}) {
  const deltas = Array.isArray(result.scenario_deltas) ? result.scenario_deltas : [];
  const monte = objectValue(result.monte_carlo_delta);
  const simulation = objectValue(result.simulation_delta);
  const changedSettings = changedSettingRows(result.base_settings, result.candidate_settings);

  return html`
    <div class="scenario-result">
      <header class="section-head compact">
        <span class="section-eyebrow">Simulation result</span>
        <h3 class="section-title">Simulation compared.</h3>
      </header>

      ${changedSettings.length ? html`
        <dl class="scenario-change-list">
          ${raw(changedSettings.map(row => html`
            <div>
              <dt>${row.label}</dt>
              <dd>${row.base} -> ${row.candidate}</dd>
            </div>
          `).join(''))}
        </dl>
      ` : html`<p class="marginalia">No setting differences were returned.</p>`}

      ${deltas.length ? html`
        <div class="scenario-delta-table">
          ${raw(deltas.map(row => renderDeltaRow(row)).join(''))}
        </div>
      ` : ''}

      ${Object.keys(monte).length ? raw(renderMetricBlock('Monte Carlo', monte)) : ''}
      ${Object.keys(simulation).length ? raw(renderMetricBlock('Simulation', simulation)) : ''}

      <div class="scenario-handoff">
        <a class="link-editorial" href="#copilot?intent=plan-scenario&amp;plan=${encodeURIComponent(planId || clean(plan.id))}">Discuss in Copilot</a>
        <button class="action-link" data-scenario-action="save-simulation">Save simulation <span class="arrow">›</span></button>
        <button class="action-link" data-scenario-action="save-decision">Save decision note <span class="arrow">›</span></button>
        ${focusId ? html`<a class="link-editorial" href="#inbox?focus=${encodeURIComponent(focusId)}">Open related Inbox recommendation</a>` : ''}
      </div>
    </div>
  `;
}

function renderSavedSimulations(planId = '', state = {}) {
  const payload = objectValue(state.payload);
  const simulations = Array.isArray(payload.simulations) ? payload.simulations.slice(0, 8) : [];
  return html`
    <div class="saved-simulations">
      <header class="section-head compact">
        <span class="section-eyebrow">Saved Simulations</span>
        <h3 class="section-title">Experiments you can return to.</h3>
        <p class="section-lede">Saved results do not change when plan assumptions change later.</p>
      </header>
      ${state.error ? html`<p class="error-banner">${esc(state.error)}</p>` : ''}
      ${state.busy ? html`<p class="marginalia">Loading saved simulations...</p>` : ''}
      ${simulations.length ? html`
        <div class="saved-simulation-list">
          ${raw(simulations.map(item => renderSavedSimulation(planId, item)).join(''))}
        </div>
      ` : html`<p class="marginalia">No Saved Simulations yet. Run a simulation, then save the result.</p>`}
    </div>
  `;
}

function renderSavedSimulation(planId = '', item = {}) {
  const id = clean(item.id);
  const source = simulationSourceLabel(item.source || 'simulation');
  const title = clean(item.title) || 'Saved Simulation';
  const summary = clean(item.summary) || 'Saved simulation output.';
  const delta = savedSimulationDeltaText(item);
  return html`
    <article class="saved-simulation-card">
      <div>
        <span class="story-block-eyebrow">${esc(source)}</span>
        <h4>${esc(title)}</h4>
        <p>${esc(summary)}</p>
        ${delta ? html`<p class="saved-simulation-delta">${delta}</p>` : ''}
        <span class="marginalia">${esc(formatDate(item.created_at))} · immutable</span>
      </div>
      <div class="scenario-handoff">
        <a class="link-editorial" href="#copilot?intent=plan-scenario&amp;plan=${encodeURIComponent(planId)}">Discuss</a>
        <button class="action-link" data-saved-simulation-action="decision" data-saved-simulation-id="${esc(id)}">
          Attach decision <span class="arrow">›</span>
        </button>
      </div>
    </article>
  `;
}

function simulationSourceLabel(source = '') {
  const normalized = clean(source).toLowerCase();
  if (normalized === 'scenario_diff') return 'Simulation';
  if (normalized === 'scenario_branch') return 'What-if simulation';
  if (normalized === 'withdrawal_strategy') return 'Strategy comparison';
  return 'Simulation';
}

function savedSimulationDeltaText(item = {}) {
  const result = objectValue(item.result_payload);
  const deltas = Array.isArray(result.scenario_deltas) ? result.scenario_deltas : [];
  const baseline = deltas.find(row => clean(row?.label) === 'baseline') || deltas[0];
  if (!baseline) return '';
  const future = Number(baseline.delta_future_value_usd);
  const real = Number(baseline.delta_real_value_usd);
  const parts = [];
  if (Number.isFinite(future)) parts.push(`Future ${fmtUsdSigned(future)}`);
  if (Number.isFinite(real)) parts.push(`Real ${fmtUsdSigned(real)}`);
  return parts.join(' · ');
}

function renderDeltaRow(row = {}) {
  const label = titleText(row.label || 'scenario');
  return html`
    <article class="scenario-delta-row">
      <h4>${esc(label)}</h4>
      <dl>
        <div>
          <dt>Future value</dt>
          <dd>${fmtUsd(row.base_future_value_usd)} -> ${fmtUsd(row.candidate_future_value_usd)} <span>${fmtUsdSigned(row.delta_future_value_usd)}</span></dd>
        </div>
        <div>
          <dt>Real value</dt>
          <dd>${fmtUsd(row.base_real_value_usd)} -> ${fmtUsd(row.candidate_real_value_usd)} <span>${fmtUsdSigned(row.delta_real_value_usd)}</span></dd>
        </div>
      </dl>
    </article>
  `;
}

function renderMetricBlock(title, metrics = {}) {
  const rows = Object.entries(metrics)
    .filter(([, value]) => value != null && value !== '')
    .slice(0, 6);
  if (!rows.length) return '';
  return html`
    <div class="scenario-metric-block">
      <span class="story-block-eyebrow">${esc(title)}</span>
      <dl>
        ${raw(rows.map(([key, value]) => html`
          <div>
            <dt>${esc(humanText(key))}</dt>
            <dd>${esc(formatMetricValue(key, value))}</dd>
          </div>
        `).join(''))}
      </dl>
    </div>
  `;
}

function changedSettingRows(base = {}, candidate = {}) {
  const rows = [];
  const fields = [
    { key: 'annual_contribution_usd', label: 'Annual contribution', type: 'money' },
    { key: 'expected_return_baseline', label: 'Expected return', type: 'percent_fraction' },
    { key: 'inflation_rate', label: 'Inflation', type: 'percent_fraction' },
    { key: 'marginal_tax_rate', label: 'Marginal tax', type: 'percent_fraction' },
    { key: 'years', label: 'Years horizon', type: 'integer' },
  ];
  for (const field of fields) {
    const left = base?.[field.key];
    const right = candidate?.[field.key];
    if (left == null && right == null) continue;
    if (String(left) === String(right)) continue;
    rows.push({
      label: field.label,
      base: displayValue(field, left),
      candidate: displayValue(field, right),
    });
  }
  return rows;
}

function draftValue(field, plan = {}, draft = {}) {
  if (Object.prototype.hasOwnProperty.call(draft, field.key)) return clean(draft[field.key]);
  return '';
}

function currentValueLabel(field, plan = {}) {
  const settings = objectValue(plan.settings);
  if (field.key === 'current_portfolio_value_usd') return 'Optional override';
  const value = settings[field.key];
  return value == null || value === '' ? 'Current unset' : `Current ${displayValue(field, value)}`;
}

function parseScenarioValue(field, rawValue) {
  const text = clean(rawValue);
  if (!text) return null;
  const number = Number(text);
  if (!Number.isFinite(number)) return null;
  if (field.type === 'integer') return Math.round(number);
  if (field.type === 'percent') return Number((number / 100).toFixed(6));
  return number;
}

function displayValue(field, value) {
  if (value == null || value === '') return 'Unset';
  if (field.type === 'money') return fmtUsd(Number(value));
  if (field.type === 'percent' || field.type === 'percent_fraction') return `${trimNumber(Number(value) * 100)}%`;
  return String(value);
}

function formatMetricValue(key, value) {
  if (typeof value === 'number' && key.toLowerCase().includes('probability')) {
    return fmtPctSigned(value, { fromFraction: true });
  }
  if (typeof value === 'number' && key.toLowerCase().includes('delta')) {
    return fmtUsdSigned(value);
  }
  if (typeof value === 'number') return String(Number(value.toFixed(3)));
  return String(value);
}

function normalizeAssumptionSets(assumptionSets = {}) {
  const sets = Array.isArray(assumptionSets?.sets)
    ? assumptionSets.sets.filter(item => item && typeof item === 'object')
    : [];
  return {
    active_assumption_set_id: clean(assumptionSets?.active_assumption_set_id || 'default') || 'default',
    sets,
  };
}

function trimNumber(value) {
  if (!Number.isFinite(value)) return '';
  return String(Number(value.toFixed(3)));
}

function humanText(value) {
  return clean(value).replace(/_/g, ' ');
}

function titleText(value) {
  const text = humanText(value);
  return text ? text[0].toUpperCase() + text.slice(1) : '';
}

function formatDate(value) {
  const date = value ? new Date(value) : null;
  if (!date || Number.isNaN(date.getTime())) return 'Saved';
  return date.toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' });
}

function objectValue(value) {
  return value && typeof value === 'object' && !Array.isArray(value) ? value : {};
}

function clean(value) {
  return String(value ?? '').trim();
}
