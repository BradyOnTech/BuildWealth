// Movement IID — Withdrawal strategy comparison.
// Retirement drawdown tradeoff review using the existing Plan Workspace compare contract.

import { html, raw, esc } from '../../lib/dom.js';
import { fmtPct, fmtUsd } from '../../lib/format.js';

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
