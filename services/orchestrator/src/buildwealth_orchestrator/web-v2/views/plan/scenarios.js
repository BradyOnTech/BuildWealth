// Movement IIB — Simulations.
// Bounded comparison surface for reviewing plan-setting changes before decisions.

import { html, raw, esc } from '../../lib/dom.js';
import { fmtPctSigned, fmtUsd, fmtUsdSigned } from '../../lib/format.js';
import { fanChart, barChart, compactUsd } from '../../lib/chart.js';
import { firstDrawdownYear, crossoverYear, coastFireYear } from './milestones.js';

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

      ${hasResult ? raw(renderScenarioResult(plan, result, { focusId, planId, explanation: state.explanation, reviewLevel: state.reviewLevel })) : ''}
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

function renderScenarioResult(plan, result, { focusId = '', planId = '', explanation = null, reviewLevel = null } = {}) {
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

      ${raw(renderTrajectoryFan(result.candidate_result, result.base_result, { planId: planId || clean(plan.id) }))}

      ${deltas.length ? html`
        <div class="scenario-delta-table">
          ${raw(deltas.map(row => renderDeltaRow(row)).join(''))}
        </div>
      ` : ''}

      ${Object.keys(monte).length ? raw(renderMetricBlock('Monte Carlo', monte)) : ''}
      ${Object.keys(simulation).length ? raw(renderMetricBlock('Simulation', simulation)) : ''}
      ${raw(renderSimulationExplanation(explanation))}
      ${raw(renderWhatIfReviewLevel(reviewLevel))}

      <div class="scenario-handoff">
        <a class="link-editorial" href="#copilot?intent=plan-scenario&amp;plan=${encodeURIComponent(planId || clean(plan.id))}">Discuss in Copilot</a>
        <button class="action-link" data-scenario-action="save-simulation">Save simulation <span class="arrow">›</span></button>
        <button class="action-link" data-scenario-action="save-decision">Save decision note <span class="arrow">›</span></button>
        ${focusId ? html`<a class="link-editorial" href="#inbox?focus=${encodeURIComponent(focusId)}">Open related Inbox recommendation</a>` : ''}
      </div>
    </div>
  `;
}

// The headline visual: candidate Monte Carlo fan (P10–P90) with the current
// plan's median dashed underneath, and a marker where drawdown begins.
// Shared by the Simulations and What-ifs surfaces.
export function renderTrajectoryFan(candidateResult, baseResult, { planId = '' } = {}) {
  const candidate = objectValue(candidateResult);
  const base = objectValue(baseResult);
  const candMonte = objectValue(candidate.monte_carlo);
  const rows = Array.isArray(candMonte.percentile_timeline) ? candMonte.percentile_timeline : [];
  if (rows.length < 2) return '';

  const baseMonte = objectValue(base.monte_carlo);
  const baseRows = Array.isArray(baseMonte.percentile_timeline) ? baseMonte.percentile_timeline : [];
  const baseByYear = new Map(
    baseRows.map(row => [Number(row.year), Number(row.p50_ending_balance_usd)]),
  );
  const merged = rows.map(row => ({
    ...row,
    base_p50_ending_balance_usd: baseByYear.get(Number(row.year)),
  }));
  const hasBaseline = merged.some(row => Number.isFinite(row.base_p50_ending_balance_usd));

  const timelinePoints = baselineTimelinePoints(candidate);
  const markers = [];
  const drawdownYear = firstDrawdownYear(timelinePoints);
  const coastYear = coastFireYear(timelinePoints);
  const crossover = crossoverYear(timelinePoints);
  if (coastYear != null && coastYear !== drawdownYear) {
    markers.push({ x: coastYear, label: 'Coast FI', cls: 'chart-marker-coast' });
  }
  if (drawdownYear != null) markers.push({ x: drawdownYear, label: 'Retirement' });

  const chart = fanChart({
    rows: merged,
    xKey: 'year',
    bands: [
      { lo: 'p10_ending_balance_usd', hi: 'p90_ending_balance_usd', cls: 'chart-band-outer' },
      { lo: 'p25_ending_balance_usd', hi: 'p75_ending_balance_usd', cls: 'chart-band-inner' },
    ],
    lines: [
      ...(hasBaseline ? [{ key: 'base_p50_ending_balance_usd', cls: 'chart-line-compare' }] : []),
      { key: 'p50_ending_balance_usd', cls: 'chart-line-median' },
    ],
    markers,
    formatY: compactUsd,
    ariaLabel: 'Projected portfolio balance range by year across Monte Carlo simulations',
  });
  if (!chart) return '';

  const runs = Number(candMonte.runs);
  const firstRow = merged[0];
  const lastRow = merged[merged.length - 1];
  const ageSpan = Number.isFinite(Number(firstRow.age)) && Number(firstRow.age) > 0
    ? ` · ages ${firstRow.age}–${lastRow.age}`
    : '';
  return html`
    <figure class="chart-figure">
      <div class="chart-legend">
        <span><i class="legend-swatch band-outer"></i>10th–90th percentile</span>
        <span><i class="legend-swatch band-inner"></i>25th–75th</span>
        <span><i class="legend-swatch line-median"></i>Median (this simulation)</span>
        ${hasBaseline ? html`<span><i class="legend-swatch line-compare"></i>Current plan median</span>` : ''}
      </div>
      ${raw(chart)}
      <figcaption class="chart-caption">
        Nominal dollars${Number.isFinite(runs) && runs > 0 ? ` · ${runs.toLocaleString('en-US')} simulated paths` : ''}${ageSpan}${milestoneCaption(coastYear, crossover)}
        ${raw(explainChartLink('trajectory-fan', planId))}
      </figcaption>
    </figure>
  `.toString();
}

export function explainChartLink(chart, planId = '') {
  const params = new URLSearchParams({ intent: 'explain-chart', chart });
  if (clean(planId)) params.set('plan', clean(planId));
  return html` · <a class="link-editorial" href="#copilot?${params.toString()}">Explain this chart</a>`.toString();
}

function milestoneCaption(coastYear, crossover) {
  const parts = [];
  if (coastYear != null) parts.push(`coast estimate: contributions optional from ${coastYear}`);
  if (crossover != null) parts.push(`growth outpaces contributions from ${crossover}`);
  return parts.length ? ` · ${parts.join(' · ')}` : '';
}

function baselineTimelinePoints(planningResult = {}) {
  const scenarios = Array.isArray(planningResult.scenarios) ? planningResult.scenarios : [];
  const baseline = scenarios.find(item => clean(item?.label).toLowerCase() === 'baseline') || scenarios[0];
  return Array.isArray(baseline?.timeline_points)
    ? baseline.timeline_points.filter(point => point && typeof point === 'object')
    : [];
}

export function renderSimulationExplanation(state = {}) {
  state = objectValue(state);
  const payload = objectValue(state.payload || state);
  const drivers = Array.isArray(payload.drivers) ? payload.drivers : [];
  const assumptions = Array.isArray(payload.assumption_traces) ? payload.assumption_traces : [];
  const warnings = Array.isArray(payload.warnings) ? payload.warnings.filter(Boolean) : [];
  const reasons = Array.isArray(payload.confidence_reasons) ? payload.confidence_reasons : [];
  const yearly = Array.isArray(payload.yearly_metrics) ? payload.yearly_metrics : [];
  const phases = Array.isArray(payload.phase_summaries) ? payload.phase_summaries : [];
  const bands = Array.isArray(payload.percentile_bands) ? payload.percentile_bands : [];
  const planStrength = objectValue(payload.plan_strength);
  const failureAnalysis = objectValue(payload.failure_analysis);
  const reviewLinks = Array.isArray(payload.field_review_links) ? payload.field_review_links : [];
  if (state.busy) {
    return html`
      <article class="simulation-explainer">
        <span class="story-block-eyebrow">What this means</span>
        <p class="marginalia">Explaining the simulation...</p>
      </article>
    `;
  }
  if (state.error) {
    return html`
      <article class="simulation-explainer">
        <span class="story-block-eyebrow">What this means</span>
        <p class="error-banner">${esc(state.error)}</p>
      </article>
    `;
  }
  if (!Object.keys(payload).length) return '';
  return html`
    <article class="simulation-explainer">
      <header>
        <div>
          <span class="story-block-eyebrow">What this means</span>
          <h4>${esc(outcomeTitle(payload.outcome_label))}</h4>
        </div>
        <span class="simulation-confidence ${esc(clean(payload.confidence_level) || 'low')}">${esc(confidenceLabel(payload.confidence_level))}</span>
      </header>
      <p>${esc(payload.summary || 'Simulation explanation unavailable.')}</p>
      ${drivers.length ? html`
        <div class="simulation-explainer-grid">
          ${raw(drivers.slice(0, 4).map(driver => html`
            <div class="simulation-driver ${esc(clean(driver.direction) || 'neutral')}">
              <span>${esc(clean(driver.label) || 'Driver')}</span>
              <p>${esc(clean(driver.detail))}</p>
            </div>
          `).join(''))}
        </div>
      ` : ''}
      ${raw(renderSimulationDepth({ yearly, phases, bands, planStrength, failureAnalysis, reviewLinks }))}
      ${assumptions.length ? html`
        <details class="simulation-trace">
          <summary>Inputs used</summary>
          <ul>
            ${raw(assumptions.slice(0, 6).map(item => html`<li>${esc(item.explanation)}</li>`).join(''))}
          </ul>
        </details>
      ` : ''}
      ${warnings.length || reasons.length ? html`
        <details class="simulation-trace">
          <summary>Confidence notes</summary>
          <ul>
            ${raw([...reasons, ...warnings].slice(0, 8).map(item => html`<li>${esc(item)}</li>`).join(''))}
          </ul>
        </details>
      ` : ''}
    </article>
  `;
}

function renderSimulationDepth({ yearly = [], phases = [], bands = [], planStrength = {}, failureAnalysis = {}, reviewLinks = [] } = {}) {
  const hasPlanStrength = Object.keys(planStrength).length > 0;
  const failureModes = Array.isArray(failureAnalysis.failure_modes) ? failureAnalysis.failure_modes : [];
  const failureYears = Array.isArray(failureAnalysis.first_failure_year_distribution)
    ? failureAnalysis.first_failure_year_distribution
    : [];
  if (!yearly.length && !phases.length && !bands.length && !hasPlanStrength && !failureModes.length && !reviewLinks.length) return '';
  const first = yearly[0] || {};
  const last = yearly[yearly.length - 1] || {};
  return html`
    <div class="simulation-depth">
      ${hasPlanStrength ? html`
        <dl class="scenario-change-list">
          <div>
            <dt>Plan Strength</dt>
            <dd>${esc(clean(planStrength.label) || 'Needs review')}</dd>
          </div>
          <div>
            <dt>Funded simulations</dt>
            <dd>${formatPercentValue(planStrength.funded_trial_rate_pct)}</dd>
          </div>
          <div>
            <dt>Meaning</dt>
            <dd>${esc(clean(planStrength.summary) || 'Simulation funding strength needs review.')}</dd>
          </div>
        </dl>
      ` : ''}
      ${yearly.length ? html`
        <dl class="scenario-change-list">
          <div>
            <dt>Yearly metrics</dt>
            <dd>${yearly.length} year${yearly.length === 1 ? '' : 's'} · ${esc(first.year || '')} to ${esc(last.year || '')}</dd>
          </div>
          <div>
            <dt>Ending balance</dt>
            <dd>${fmtUsd(last.ending_balance_usd)}</dd>
          </div>
          <div>
            <dt>Net cash flow</dt>
            <dd>${fmtUsdSigned(sumMetric(yearly, 'net_cash_flow_usd'))}</dd>
          </div>
        </dl>
      ` : ''}
      ${phases.length ? html`
        <details class="simulation-trace" open>
          <summary>Life phases</summary>
          <ul>
            ${raw(phases.map(phase => html`
              <li>
                ${esc(phase.label)} (${esc(phase.start_year)}-${esc(phase.end_year)}):
                ending balance ${fmtUsd(phase.ending_balance_usd)},
                taxes ${fmtUsd(phase.total_taxes_usd)},
                withdrawals ${fmtUsd(phase.total_withdrawals_usd)}
              </li>
            `).join(''))}
          </ul>
        </details>
      ` : ''}
      ${bands.length ? html`
        <details class="simulation-trace">
          <summary>Monte Carlo range</summary>
          <ul>
            ${raw(bands.map(row => html`
              <li>${esc(row.percentile)}: future value ${fmtUsd(row.future_value_usd)}${row.real_value_usd != null ? html`, real value ${fmtUsd(row.real_value_usd)}` : ''}</li>
            `).join(''))}
          </ul>
        </details>
      ` : ''}
      ${failureModes.length ? html`
        <details class="simulation-trace" ${failureAnalysis.failed_trial_count ? 'open' : ''}>
          <summary>Failure-mode check</summary>
          <ul>
            ${raw(failureModes.map(mode => html`
              <li>${esc(clean(mode.label) || 'Result')}: ${esc(clean(mode.detail))}</li>
            `).join(''))}
            ${failureAnalysis.most_common_first_failure_year ? html`
              <li>Most common first shortfall year: ${esc(failureAnalysis.most_common_first_failure_year)}</li>
            ` : ''}
          </ul>
          ${raw(renderFailureHistogram(failureYears))}
        </details>
      ` : ''}
      ${reviewLinks.length ? html`
        <details class="simulation-trace">
          <summary>Fields to review</summary>
          <ul>
            ${raw(reviewLinks.map(link => html`<li><a href="${link.href}">${esc(link.label)}</a> - ${esc(link.reason)}</li>`).join(''))}
          </ul>
        </details>
      ` : ''}
    </div>
  `;
}

function renderFailureHistogram(failureYears = []) {
  const rows = failureYears.filter(row => Number.isFinite(Number(row?.trial_share_pct)));
  if (!rows.length) return '';
  const chart = barChart({
    rows,
    xKey: 'year',
    yKey: 'trial_share_pct',
    height: 160,
    formatY: value => `${value}%`,
    ariaLabel: 'Share of simulated paths first running short, by year',
  });
  if (!chart) return '';
  return html`
    <figure class="chart-figure">
      ${raw(chart)}
      <figcaption class="chart-caption">Share of simulated paths first running short, by year.${raw(explainChartLink('failure-histogram'))}</figcaption>
    </figure>
  `.toString();
}

function formatPercentValue(value) {
  const numeric = Number(value);
  if (!Number.isFinite(numeric)) return 'Needs review';
  return `${numeric.toFixed(numeric % 1 === 0 ? 0 : 1)}%`;
}

export function renderWhatIfReviewLevel(state = {}) {
  state = objectValue(state);
  const payload = objectValue(state.payload || state);
  const stageOne = objectValue(payload.stage_one);
  const stageTwo = objectValue(payload.stage_two);
  const actions = Array.isArray(payload.recommended_actions) ? payload.recommended_actions.filter(Boolean) : [];
  const stageOneReasons = Array.isArray(stageOne.reasons) ? stageOne.reasons.filter(Boolean) : [];
  const stageTwoReasons = Array.isArray(stageTwo.reasons) ? stageTwo.reasons.filter(Boolean) : [];
  if (state.busy) {
    return html`
      <article class="what-if-review-level">
        <span class="story-block-eyebrow">Review level</span>
        <p class="marginalia">Checking how much review this change needs...</p>
      </article>
    `;
  }
  if (state.error) {
    return html`
      <article class="what-if-review-level">
        <span class="story-block-eyebrow">Review level</span>
        <p class="error-banner">${esc(state.error)}</p>
      </article>
    `;
  }
  if (!Object.keys(payload).length) return '';
  return html`
    <article class="what-if-review-level ${esc(clean(payload.review_level) || 'low')}">
      <header>
        <div>
          <span class="story-block-eyebrow">Review level</span>
          <h4>${esc(reviewLevelTitle(payload.review_level))}</h4>
        </div>
        <span class="simulation-confidence ${esc(clean(payload.review_level) || 'low')}">${esc(reviewLevelBadge(payload.review_level))}</span>
      </header>
      <p>${esc(payload.summary || 'Review guidance unavailable.')}</p>
      <div class="review-stage-grid">
        ${raw(renderReviewStage(stageOne, stageOneReasons))}
        ${raw(renderReviewStage(stageTwo, stageTwoReasons))}
      </div>
      ${actions.length ? html`
        <details class="simulation-trace">
          <summary>Suggested next steps</summary>
          <ul>
            ${raw(actions.slice(0, 5).map(item => html`<li>${esc(item)}</li>`).join(''))}
          </ul>
        </details>
      ` : ''}
    </article>
  `;
}

function renderReviewStage(stage = {}, reasons = []) {
  const level = clean(stage.level) || 'low';
  return html`
    <div class="review-stage ${esc(level)}">
      <span>${esc(clean(stage.name) || 'Review stage')} · ${esc(reviewLevelBadge(level))}</span>
      <p>${esc(clean(stage.summary) || 'No extra review notes.')}</p>
      ${reasons.length ? html`
        <ul>
          ${raw(reasons.slice(0, 4).map(reason => html`<li>${esc(reason)}</li>`).join(''))}
        </ul>
      ` : ''}
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
      ${raw(renderSavedSimulationReview(state.focusedComparison, state.rerun))}
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
        <button class="action-link" data-saved-simulation-action="compare" data-saved-simulation-id="${esc(id)}">
          Compare current <span class="arrow">›</span>
        </button>
        <button class="action-link" data-saved-simulation-action="rerun" data-saved-simulation-id="${esc(id)}">
          Rerun and save <span class="arrow">›</span>
        </button>
        <button class="action-link" data-saved-simulation-action="decision" data-saved-simulation-id="${esc(id)}">
          Attach decision <span class="arrow">›</span>
        </button>
      </div>
    </article>
  `;
}

function renderSavedSimulationReview(comparison = null, rerun = null) {
  const comparisonPayload = objectValue(comparison);
  const rerunPayload = objectValue(rerun);
  if (comparisonPayload.busy || rerunPayload.busy) {
    return html`
      <article class="simulation-explainer">
        <span class="story-block-eyebrow">Saved Simulation Detail</span>
        <p class="marginalia">${comparisonPayload.busy ? 'Comparing against the current plan...' : 'Rerunning saved inputs...'}</p>
      </article>
    `;
  }
  if (!Object.keys(comparisonPayload).length && !Object.keys(rerunPayload).length) return '';

  const differences = Array.isArray(comparisonPayload.setting_differences)
    ? comparisonPayload.setting_differences
    : [];
  const metrics = objectValue(comparisonPayload.saved_metrics);
  const rerunSaved = objectValue(rerunPayload.saved_simulation);
  return html`
    <article class="simulation-explainer">
      <header>
        <div>
          <span class="story-block-eyebrow">Saved Simulation Detail</span>
          <h4>${esc(comparisonPayload.changed_since_saved ? 'Current plan has changed.' : 'Saved assumptions still line up.')}</h4>
        </div>
      </header>
      ${comparisonPayload.summary ? html`<p>${esc(comparisonPayload.summary)}</p>` : ''}
      ${differences.length ? html`
        <details class="simulation-trace" open>
          <summary>Changed since saved</summary>
          <ul>
            ${raw(differences.slice(0, 6).map(item => html`
              <li>${esc(item.label)} moved from ${esc(item.saved_value)} to ${esc(item.current_value)}.</li>
            `).join(''))}
          </ul>
        </details>
      ` : ''}
      ${Object.keys(metrics).length ? html`
        <dl class="scenario-change-list">
          ${raw(savedMetricRows(metrics).map(([label, value]) => html`
            <div>
              <dt>${esc(label)}</dt>
              <dd>${esc(value)}</dd>
            </div>
          `).join(''))}
        </dl>
      ` : ''}
      ${Object.keys(rerunPayload).length ? html`
        <p>${rerunSaved.id
          ? html`Rerun saved as ${esc(clean(rerunSaved.title) || rerunSaved.id)}.`
          : html`Rerun completed with current plan data.`}</p>
      ` : ''}
    </article>
  `;
}

function savedMetricRows(metrics = {}) {
  const rows = [];
  const future = Number(metrics.delta_future_value_usd);
  const real = Number(metrics.delta_real_value_usd);
  const success = Number(metrics.success_probability_delta);
  if (Number.isFinite(future)) rows.push(['Saved future change', fmtUsdSigned(future)]);
  if (Number.isFinite(real)) rows.push(['Saved real change', fmtUsdSigned(real)]);
  if (Number.isFinite(success)) rows.push(['Saved success change', fmtPctSigned(success, { fromFraction: true })]);
  return rows;
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
    .filter(([, value]) => isDisplayableMetricValue(value))
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
  if (typeof value === 'boolean') return value ? 'Yes' : 'No';
  if (typeof value === 'string') return value.replace(/_/g, ' ');
  const lowerKey = String(key || '').toLowerCase();
  if (typeof value === 'number' && lowerKey.includes('probability')) {
    return fmtPctSigned(value, { fromFraction: true });
  }
  if (typeof value === 'number' && lowerKey.includes('delta')) {
    return fmtUsdSigned(value);
  }
  if (typeof value === 'number' && (lowerKey.includes('usd') || lowerKey.includes('value'))) {
    return fmtUsd(value);
  }
  if (typeof value === 'number') return String(Number(value.toFixed(3)));
  return String(value);
}

function isDisplayableMetricValue(value) {
  if (value == null || value === '') return false;
  if (Array.isArray(value)) return false;
  if (typeof value === 'object') return false;
  return true;
}

function sumMetric(rows = [], key = '') {
  return rows.reduce((total, row) => {
    const value = Number(row?.[key]);
    return total + (Number.isFinite(value) ? value : 0);
  }, 0);
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

function outcomeTitle(value = '') {
  const normalized = clean(value).toLowerCase();
  if (normalized === 'better') return 'Looks better than the active plan.';
  if (normalized === 'worse') return 'Looks weaker than the active plan.';
  if (normalized === 'mixed') return 'Shows trade-offs.';
  return 'Needs more context.';
}

function confidenceLabel(value = '') {
  const normalized = clean(value).toLowerCase();
  if (normalized === 'high') return 'High confidence';
  if (normalized === 'medium') return 'Medium confidence';
  return 'Low confidence';
}

function reviewLevelTitle(value = '') {
  return clean(value).toLowerCase() === 'high'
    ? 'Slow down before applying this.'
    : 'Normal review is enough.';
}

function reviewLevelBadge(value = '') {
  return clean(value).toLowerCase() === 'high' ? 'High review' : 'Low review';
}

function objectValue(value) {
  return value && typeof value === 'object' && !Array.isArray(value) ? value : {};
}

function clean(value) {
  return String(value ?? '').trim();
}
