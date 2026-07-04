// Movement I — The story.
// Plan title + lede, two-column reading layout: settings ledger on the left,
// top next actions on the right.

import { html, raw, esc, stripHtml } from '../../lib/dom.js';
import { fmtUsd, fmtPctSigned, roman } from '../../lib/format.js';

export function renderStory(plan, assumptionState = {}, timelineState = {}) {
  return html`
    <section>
      <header class="section-head">
        <span class="section-eyebrow">Movement I</span>
        <h2 class="section-title" style="display:none;">The story.</h2>
      </header>
      <h1 class="plan-title">${esc(plan.title || 'Untitled plan')}</h1>
      ${plan.description ? html`<p class="plan-lede">${esc(plan.description)}</p>` : ''}
      <div class="story-grid">
        <div>
          <span class="story-block-eyebrow">Key assumptions</span>
          ${renderLedger(effectivePlanSettings(plan, assumptionState, timelineState))}
        </div>
        <div class="story-actions">
          <span class="story-block-eyebrow">You should know</span>
          ${renderTopActions(plan.top_next_actions || [])}
        </div>
      </div>
    </section>
  `;
}

// What the engine will actually use: plan settings overlaid with the active
// assumption set, plus retirement fields from the timeline. Without this the
// ledger renders the raw (often empty) base settings as a wall of dashes.
export function effectivePlanSettings(plan = {}, assumptionState = {}, timelineState = {}) {
  const merged = { ...(plan.settings || {}) };
  const sets = assumptionState?.assumptionSets;
  const activeId = String(sets?.active_assumption_set_id || '').trim();
  const active = Array.isArray(sets?.sets)
    ? sets.sets.find(item => String(item?.id || '') === activeId) || null
    : null;
  if (active) {
    for (const [key, value] of Object.entries(active)) {
      if (key === 'id' || key === 'name' || value == null) continue;
      merged[key] = value;
    }
  }
  const retirement = timelineState?.timeline?.retirement || timelineState?.retirement || {};
  for (const key of ['withdrawal_strategy', 'drawdown_order']) {
    if (merged[key] == null && retirement[key] != null) merged[key] = retirement[key];
  }
  return merged;
}

function renderLedger(settings) {
  const rows = [
    ['Annual contribution', fmtMoneyOrDash(settings.annual_contribution_usd)],
    ['Years horizon',       fmtIntOrDash(settings.years)],
    ['Expected return',     fmtPctOrDash(settings.expected_return_baseline)],
    ['Inflation',           fmtPctOrDash(settings.inflation_rate)],
    ['Marginal tax',        fmtPctOrDash(settings.marginal_tax_rate)],
    ['Withdrawal strategy', humanText(settings.withdrawal_strategy) || dash()],
    ['Drawdown order',      humanText(settings.drawdown_order) || dash()],
    ['Filing status',       humanText(settings.filing_status) || dash()],
    ['Simulation',          humanText(settings.simulation_mode) || dash()],
  ];
  const optional = [
    ['Roth conversions',
      settings.roth_conversion_annual_amount_usd
        ? `${fmtUsd(settings.roth_conversion_annual_amount_usd)}/yr`
        : null],
    ['Household mode',      humanText(settings.household_mode)],
  ];
  for (const [label, value] of optional) {
    if (value) rows.push([label, value]);
  }

  return html`
    <ul class="ledger-list">
      ${rows.map(([label, value]) => html`
        <li class="ledger-row">
          <span class="ledger-label">${label}</span>
          <span class="ledger-value ${value === 'app default' ? 'muted' : ''}">${value}</span>
        </li>
      `)}
    </ul>
  `;
}

function renderTopActions(actions) {
  if (!actions || !actions.length) {
    return html`<p class="marginalia">Nothing pressing for this plan today.</p>`;
  }
  return html`
    <ol class="entry-list">
      ${actions.slice(0, 3).map((a, i) => renderActionEntry(a, i + 1))}
    </ol>
  `;
}

function renderActionEntry(action, index) {
  const priority = (action.priority || 'medium').toLowerCase();
  const target = action.recommendation_id
    ? `#inbox?focus=${encodeURIComponent(action.recommendation_id)}`
    : '#inbox';
  return html`
    <li class="entry">
      <span class="entry-numeral">${roman(index)}.</span>
      <div class="entry-body">
        <span class="entry-tag">
          <span class="priority ${priority}"></span>${priority} priority
        </span>
        <h3 class="entry-title">${stripHtml(action.title)}</h3>
        ${action.detail ? html`<p class="entry-rationale">${stripHtml(action.detail)}</p>` : ''}
        <div class="entry-meta">
          <a class="link-editorial" href="${target}">Open in inbox</a>
        </div>
      </div>
    </li>
  `;
}

function fmtMoneyOrDash(v) {
  if (v == null) return dash();
  const n = Number(v);
  if (!Number.isFinite(n)) return dash();
  return fmtUsd(n);
}

function fmtIntOrDash(v) {
  if (v == null) return dash();
  const n = Number(v);
  if (!Number.isFinite(n)) return dash();
  return `${n}`;
}

function fmtPctOrDash(v) {
  if (v == null) return dash();
  const n = Number(v);
  if (!Number.isFinite(n)) return dash();
  // settings store rates as fractions (0.07 == 7%) historically, but some
  // are entered as percentages (7). Use a small heuristic: if abs(v) < 1, treat as fraction.
  const pct = Math.abs(n) < 1 ? n * 100 : n;
  return `${pct.toFixed(1)}%`;
}

function humanText(v) {
  if (!v) return '';
  return String(v).replace(/_/g, ' ');
}

// An unset assumption is not missing data — the engine falls back to app
// defaults. Say that, instead of a dash a normal person can't interpret.
function dash() { return 'app default'; }
