// Movement I — The story.
// Plan title + lede, two-column reading layout: settings ledger on the left,
// top next actions on the right.

import { html, raw, esc, stripHtml } from '../../lib/dom.js';
import { fmtUsd, fmtPctSigned, roman } from '../../lib/format.js';

export function renderStory(plan, assumptionState = {}, timelineState = {}, assumptionDefaults = null) {
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
          ${renderLedger(effectivePlanSettings(plan, assumptionState, timelineState), assumptionDefaults)}
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

// Sources the resolved-fallback payload reports, in user words.
const SOURCE_LABELS = {
  profile: 'from your profile',
  buildwealth_default: 'BuildWealth default',
};

/* A ledger row never says "app default": if the plan leaves a value unset we
   show the number the engine will actually use, tagged with where it came
   from. Returns {text, resolved} so unresolved rows can stay muted. */
export function resolveLedgerValue(rawValue, key, defaults, formatValue) {
  if (rawValue != null && rawValue !== '') {
    return { text: formatValue(rawValue), resolved: true, fromDefault: false };
  }
  const entry = defaults?.[key];
  if (entry && entry.value != null) {
    const source = SOURCE_LABELS[entry.source] || entry.source;
    return { text: `${formatValue(entry.value)} · ${source}`, resolved: true, fromDefault: true };
  }
  return { text: 'not set', resolved: false, fromDefault: true };
}

function renderLedger(settings, defaults = null) {
  const row = (label, key, formatValue) =>
    [label, resolveLedgerValue(settings[key], key, defaults, formatValue)];
  const rows = [
    row('Annual contribution', 'annual_contribution_usd', v => fmtUsd(v)),
    row('Years horizon',       'years', v => `${Number(v)}`),
    row('Expected return',     'expected_return_baseline', fmtPctValue),
    row('Inflation',           'inflation_rate', fmtPctValue),
    row('Marginal tax',        'marginal_tax_rate', fmtPctValue),
    row('Withdrawal strategy', 'withdrawal_strategy', v => humanText(v)),
    row('Drawdown order',      'drawdown_order', v => humanText(v)),
    row('Filing status',       'filing_status', v => humanText(v)),
    row('Simulation',          'simulation_mode', v => humanText(v)),
  ];
  const optional = [
    ['Roth conversions',
      settings.roth_conversion_annual_amount_usd
        ? `${fmtUsd(settings.roth_conversion_annual_amount_usd)}/yr`
        : null],
    ['Household mode',      humanText(settings.household_mode)],
  ];
  for (const [label, value] of optional) {
    if (value) rows.push([label, { text: value, resolved: true, fromDefault: false }]);
  }

  return html`
    <ul class="ledger-list">
      ${rows.map(([label, value]) => html`
        <li class="ledger-row">
          <span class="ledger-label">${label}</span>
          <span class="ledger-value ${value.fromDefault ? 'muted' : ''}">${value.text}</span>
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

// Deliberately local, not lib/format.js's: plan settings mix fraction (0.07)
// and percent-point (7) entries, so this applies a fraction-vs-percent
// heuristic and prints 1 decimal.
function fmtPctValue(v) {
  const n = Number(v);
  if (!Number.isFinite(n)) return String(v);
  const pct = Math.abs(n) < 1 ? n * 100 : n;
  return `${pct.toFixed(1)}%`;
}

function humanText(v) {
  if (!v) return '';
  return String(v).replace(/_/g, ' ');
}


