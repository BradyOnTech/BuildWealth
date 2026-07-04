// Movement IID — Withdrawal strategy comparison.
// Retirement drawdown tradeoff review using the existing Plan Workspace compare contract.

import { html, raw, esc } from '../../lib/dom.js';
import { fmtPct, fmtUsd } from '../../lib/format.js';
import { fanChart, compactUsd } from '../../lib/chart.js';

export const WITHDRAWAL_STRATEGIES = [
  {
    id: 'cashflow_only',
    label: 'Cashflow Only',
    detail: 'Withdraw only what the plan needs.',
  },
  {
    id: 'four_percent_rule',
    label: '4% Rule',
    detail: 'Simple inflation-adjusted spending rule.',
  },
  {
    id: 'dynamic_guardrails',
    label: 'Dynamic Guardrails',
    detail: 'Adjust spending when portfolio conditions change.',
  },
  {
    id: 'bond_tent',
    label: 'Bond Tent',
    detail: 'More conservative around retirement transition.',
  },
  {
    id: 'bucket_strategy',
    label: 'Bucket Strategy',
    detail: 'Segment near-term cash and longer-term growth.',
  },
];

const DEFAULT_SELECTED = ['four_percent_rule', 'dynamic_guardrails', 'bucket_strategy'];

export function buildWithdrawalComparePayload(draft = {}) {
  const selected = Array.isArray(draft.selectedStrategies) ? draft.selectedStrategies : DEFAULT_SELECTED;
  const strategies = uniqueStrategies(selected);
  const payload = {
    strategies: strategies.length ? strategies : DEFAULT_SELECTED,
    include_raw_results: Boolean(draft.include_raw_results),
  };

  const currentPortfolio = parseMoney(draft.current_portfolio_value_usd);
  if (currentPortfolio != null) payload.current_portfolio_value_usd = currentPortfolio;

  const assumptionSetId = clean(draft.assumption_set_id);
  if (assumptionSetId) payload.assumption_set_id = assumptionSetId;

  return payload;
}

export function renderWithdrawals(plan = {}, state = {}, assumptionState = {}) {
  const draft = objectValue(state.draft);
  const selected = Array.isArray(state.selectedStrategies) && state.selectedStrategies.length
    ? state.selectedStrategies
    : DEFAULT_SELECTED;
  const result = objectValue(state.result);
  const hasResult = Boolean(Object.keys(result).length);
  const planId = clean(plan.id);

  return html`
    <section class="plan-withdrawals" data-plan-section="withdrawals">
      <header class="section-head compact">
        <span class="section-eyebrow">Withdrawal strategy comparison</span>
        <h2 class="section-title">Compare retirement drawdown paths.</h2>
        <p class="section-lede">Review spending, tax, and terminal-balance tradeoffs. This does not change the active plan.</p>
      </header>

      ${state.error ? html`<p class="error-banner">${esc(state.error)}</p>` : ''}

      <div class="scenario-grid" data-form="plan-withdrawal-compare">
        ${raw(WITHDRAWAL_STRATEGIES.map(strategy => renderStrategyToggle(strategy, selected)).join(''))}
        <label class="scenario-field">
          <span class="assumption-label">Portfolio value override</span>
          <input data-withdrawal-field="current_portfolio_value_usd" type="number" step="1000" inputmode="decimal" value="${esc(draft.current_portfolio_value_usd ?? '')}" />
          <span class="assumption-current">Optional</span>
        </label>
        ${renderAssumptionPicker(assumptionState, draft)}
      </div>

      <div class="scenario-actions">
        <button class="btn btn-primary" data-withdrawal-action="run" ${state.busy ? 'disabled' : ''}>
          ${state.busy ? 'Comparing...' : 'Compare withdrawal strategies'}
        </button>
        ${state.dirty ? html`<span class="marginalia">Withdrawal comparison edits are staged for review.</span>` : html`<span class="marginalia">Select two or more strategies to compare.</span>`}
      </div>

      ${hasResult ? raw(renderWithdrawalResult(planId, result)) : ''}
    </section>
  `;
}

function renderStrategyToggle(strategy, selected = []) {
  const checked = selected.includes(strategy.id);
  return html`
    <label class="scenario-field">
      <span class="assumption-label">
        <input
          data-withdrawal-strategy="${esc(strategy.id)}"
          type="checkbox"
          ${checked ? 'checked' : ''}
        />
        ${esc(strategy.label)}
      </span>
      <span class="assumption-current">${esc(strategy.detail)}</span>
    </label>
  `;
}

function renderAssumptionPicker(assumptionState = {}, draft = {}) {
  const assumptionSets = normalizeAssumptionSets(assumptionState.assumptionSets);
  const value = clean(draft.assumption_set_id);
  const sets = assumptionSets.sets.length
    ? assumptionSets.sets
    : [{ id: '', name: 'Current plan settings' }];
  return html`
    <label class="scenario-field">
      <span class="assumption-label">Assumption set</span>
      <select data-withdrawal-field="assumption_set_id">
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

function renderWithdrawalResult(planId = '', result = {}) {
  const comparisons = Array.isArray(result.comparisons) ? result.comparisons : [];
  const best = objectValue(result.best_strategy_by_metric);
  const warnings = [
    ...(Array.isArray(result.warnings) ? result.warnings : []),
    ...comparisons.flatMap(row => Array.isArray(row.warnings) ? row.warnings : []),
  ].map(clean).filter(Boolean);

  return html`
    <div class="scenario-result">
      <header class="section-head compact">
        <span class="section-eyebrow">Comparison result</span>
        <h3 class="section-title">Withdrawal strategies compared.</h3>
        <p class="section-lede">Portfolio value: ${fmtUsd(result.current_portfolio_value_usd)}</p>
      </header>

      ${Object.keys(best).length ? raw(renderBestStrategies(best)) : ''}
      ${raw(renderDrawdownTrajectories(result))}
      ${raw(renderStrategyExplanation(result.explanation))}

      ${warnings.length ? html`
        <div class="error-banner">
          ${raw([...new Set(warnings)].slice(0, 4).map(warning => html`<p>${esc(warning)}</p>`).join(''))}
        </div>
      ` : ''}

      ${comparisons.length ? html`
        <div class="scenario-delta-table">
          ${raw(comparisons.map(row => renderComparisonRow(row)).join(''))}
        </div>
      ` : html`<p class="marginalia">No withdrawal comparison rows were returned.</p>`}

      <div class="scenario-handoff">
        <a class="link-editorial" href="#copilot?intent=withdrawal-strategy&amp;plan=${encodeURIComponent(planId)}">Discuss in Copilot</a>
        <button class="action-link" data-withdrawal-action="save-decision">Save decision note <span class="arrow">›</span></button>
      </div>
    </div>
  `;
}

// Overlaid deterministic paths, one line per compared strategy: balances
// ("which path survives") and annual taxes ("what does each path cost in
// bracket creep, RMDs, and IRMAA"). Same colors across both charts.
function renderDrawdownTrajectories(result = {}) {
  const rawResults = objectValue(result.raw_results);
  const comparisons = Array.isArray(result.comparisons) ? result.comparisons : [];
  const ordered = comparisons.map(row => clean(row.strategy)).filter(id => rawResults[id]);
  if (ordered.length < 2) return '';

  const byYear = new Map();
  const series = [];
  let drawdownYear = null;
  let hasTaxes = false;
  ordered.forEach((strategy, index) => {
    const points = baselineTimelinePoints(rawResults[strategy]);
    if (!points.length) return;
    const cls = `chart-line-s${index % 5}`;
    series.push({ key: strategy, cls, label: strategyLabel(strategy) });
    for (const point of points) {
      const year = Number(point.year);
      const balance = Number(point.ending_balance_usd);
      if (!Number.isFinite(year) || !Number.isFinite(balance)) continue;
      if (!byYear.has(year)) byYear.set(year, { year });
      const row = byYear.get(year);
      row[strategy] = balance;
      const taxes = Number(point.taxes_usd);
      if (Number.isFinite(taxes)) {
        row[`tax_${strategy}`] = taxes;
        if (taxes > 0) hasTaxes = true;
      }
      if (drawdownYear == null && Number(point.withdrawals_usd) > 0) drawdownYear = year;
    }
  });
  if (series.length < 2) return '';
  const rows = [...byYear.values()].sort((a, b) => a.year - b.year);
  const markers = drawdownYear != null ? [{ x: drawdownYear, label: 'Drawdown' }] : [];

  const balanceChart = fanChart({
    rows,
    xKey: 'year',
    lines: series.map(({ key, cls }) => ({ key, cls })),
    markers,
    formatY: compactUsd,
    ariaLabel: 'Projected portfolio balance by year for each withdrawal strategy',
  });
  if (!balanceChart) return '';

  const taxChart = hasTaxes
    ? fanChart({
        rows,
        xKey: 'year',
        lines: series.map(({ key, cls }) => ({ key: `tax_${key}`, cls })),
        height: 200,
        formatY: compactUsd,
        ariaLabel: 'Projected annual taxes by year for each withdrawal strategy',
      })
    : '';

  return html`
    <figure class="chart-figure">
      <div class="chart-legend">
        ${raw(series.map(({ cls, label }) => html`<span><i class="legend-swatch line-swatch ${esc(cls)}"></i>${esc(label)}</span>`).join(''))}
      </div>
      ${raw(balanceChart)}
      <figcaption class="chart-caption">Nominal dollars · deterministic baseline path per strategy</figcaption>
    </figure>
    ${taxChart ? html`
      <figure class="chart-figure">
        <span class="story-block-eyebrow">Annual taxes</span>
        ${raw(taxChart)}
        <figcaption class="chart-caption">Federal + state + IRMAA per year · same strategy colors · spikes mark RMD and conversion years</figcaption>
      </figure>
    ` : ''}
  `.toString();
}

function baselineTimelinePoints(planningResult = {}) {
  const scenarios = Array.isArray(planningResult?.scenarios) ? planningResult.scenarios : [];
  const baseline = scenarios.find(item => clean(item?.label).toLowerCase() === 'baseline') || scenarios[0];
  return Array.isArray(baseline?.timeline_points)
    ? baseline.timeline_points.filter(point => point && typeof point === 'object')
    : [];
}

function renderStrategyExplanation(explanation = {}) {
  const payload = objectValue(explanation);
  const drivers = Array.isArray(payload.drivers) ? payload.drivers : [];
  const tradeoffs = Array.isArray(payload.tradeoffs) ? payload.tradeoffs.filter(Boolean) : [];
  const diagnostics = Array.isArray(payload.diagnostics) ? payload.diagnostics : [];
  const contributionOrdering = Array.isArray(payload.contribution_ordering)
    ? payload.contribution_ordering.filter(Boolean)
    : [];
  const reviewLevel = objectValue(payload.review_level);
  if (!Object.keys(payload).length) return '';
  return html`
    <article class="simulation-explainer">
      <header>
        <div>
          <span class="story-block-eyebrow">What this means</span>
          <h4>${esc(payload.recommended_strategy ? `${strategyLabel(payload.recommended_strategy)} stands out.` : 'The strategies have trade-offs.')}</h4>
        </div>
      </header>
      <p>${esc(payload.summary || 'Strategy explanation unavailable.')}</p>
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
      ${diagnostics.length ? html`
        <details class="simulation-trace" open>
          <summary>Diagnostics</summary>
          <ul>
            ${raw(diagnostics.slice(0, 6).map(item => html`
              <li>${esc(item.label)}: ${esc(item.summary)}${item.level ? html` (${esc(item.level)} review)` : ''}</li>
            `).join(''))}
          </ul>
        </details>
      ` : ''}
      ${contributionOrdering.length ? html`
        <details class="simulation-trace">
          <summary>Contribution ordering</summary>
          <ul>
            ${raw(contributionOrdering.slice(0, 4).map(item => html`<li>${esc(item)}</li>`).join(''))}
          </ul>
        </details>
      ` : ''}
      ${tradeoffs.length ? html`
        <details class="simulation-trace">
          <summary>Trade-offs</summary>
          <ul>
            ${raw(tradeoffs.slice(0, 5).map(item => html`<li>${esc(item)}</li>`).join(''))}
          </ul>
        </details>
      ` : ''}
      ${Object.keys(reviewLevel).length ? html`
        <details class="simulation-trace">
          <summary>Review level</summary>
          <p>${esc(reviewLevel.summary || 'Review this before changing the active strategy.')}</p>
          ${Array.isArray(reviewLevel.reasons) && reviewLevel.reasons.length ? html`
            <ul>
              ${raw(reviewLevel.reasons.slice(0, 5).map(item => html`<li>${esc(item)}</li>`).join(''))}
            </ul>
          ` : ''}
        </details>
      ` : ''}
    </article>
  `;
}

function renderBestStrategies(best = {}) {
  const rows = [
    ['Best future value', best.future_value],
    ['Best real value', best.real_value],
    ['Best Monte Carlo p50', best.monte_carlo_p50],
  ].filter(([, value]) => clean(value));
  if (!rows.length) return '';
  return html`
    <dl class="scenario-change-list">
      ${raw(rows.map(([label, value]) => html`
        <div>
          <dt>${esc(label)}</dt>
          <dd>${esc(strategyLabel(value))}</dd>
        </div>
      `).join(''))}
    </dl>
  `;
}

function renderComparisonRow(row = {}) {
  const status = clean(row.engine_status);
  return html`
    <article class="scenario-delta-row">
      <h4>${esc(strategyLabel(row.strategy))}</h4>
      <dl>
        <div>
          <dt>Future value</dt>
          <dd>${fmtUsd(row.baseline_future_value_usd)}</dd>
        </div>
        <div>
          <dt>Real value</dt>
          <dd>${fmtUsd(row.baseline_real_value_usd)}</dd>
        </div>
        <div>
          <dt>Withdrawals</dt>
          <dd>${fmtUsd(row.total_withdrawals_usd)}</dd>
        </div>
        <div>
          <dt>Taxes</dt>
          <dd>${fmtUsd(row.total_taxes_usd)}</dd>
        </div>
        <div>
          <dt>Roth conversions</dt>
          <dd>${fmtUsd(row.total_roth_conversions_usd)}</dd>
        </div>
        <div>
          <dt>RMDs</dt>
          <dd>${fmtUsd(row.total_rmds_usd)}</dd>
        </div>
        <div>
          <dt>Terminal balance</dt>
          <dd>${fmtUsd(row.terminal_balance_usd)}${row.terminal_age ? ` at ${Number(row.terminal_age)}` : ''}</dd>
        </div>
        <div>
          <dt>Monte Carlo p50</dt>
          <dd>${fmtUsd(row.monte_carlo_p50_future_value_usd)}</dd>
        </div>
        <div>
          <dt>Effective tax</dt>
          <dd>${fmtPct(row.average_effective_tax_rate, { fromFraction: true })}</dd>
        </div>
        ${status ? html`
          <div>
            <dt>Engine</dt>
            <dd>${esc(status.replace(/_/g, ' '))}</dd>
          </div>
        ` : ''}
      </dl>
    </article>
  `;
}

function uniqueStrategies(values = []) {
  const allowed = new Set(WITHDRAWAL_STRATEGIES.map(item => item.id));
  const seen = new Set();
  const result = [];
  for (const value of values) {
    const strategy = clean(value);
    if (!allowed.has(strategy) || seen.has(strategy)) continue;
    seen.add(strategy);
    result.push(strategy);
  }
  return result;
}

function parseMoney(raw) {
  const text = clean(raw);
  if (!text) return null;
  const value = Number(text);
  return Number.isFinite(value) ? value : null;
}

function normalizeAssumptionSets(payload = {}) {
  return {
    active_assumption_set_id: clean(payload?.active_assumption_set_id),
    sets: Array.isArray(payload?.sets) ? payload.sets.filter(item => item && typeof item === 'object') : [],
  };
}

function strategyLabel(value) {
  const id = clean(value);
  return WITHDRAWAL_STRATEGIES.find(item => item.id === id)?.label || humanText(id);
}

function objectValue(value) {
  return value && typeof value === 'object' && !Array.isArray(value) ? value : {};
}

function humanText(value) {
  return clean(value)
    .replace(/_/g, ' ')
    .replace(/\b\w/g, char => char.toUpperCase());
}

function clean(value) {
  return String(value ?? '').trim();
}
