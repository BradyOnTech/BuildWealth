// Movement IID - Plan timeline.
// Compact structure editor for retirement timing, withdrawal posture, and major events.

import { html, raw, esc } from '../../lib/dom.js';
import { fmtUsd } from '../../lib/format.js';

export const TIMELINE_RETIREMENT_FIELDS = [
  { key: 'target_retirement_age', label: 'Retirement age', type: 'integer' },
  { key: 'target_retirement_year', label: 'Retirement year', type: 'integer' },
  {
    key: 'withdrawal_strategy',
    label: 'Withdrawal strategy',
    type: 'select',
    options: [
      ['', 'Unspecified'],
      ['guardrails', 'Guardrails'],
      ['fixed_real', 'Fixed real'],
      ['fixed_percent', 'Fixed percent'],
      ['bucket', 'Bucket'],
      ['four_percent_rule', '4% rule'],
      ['cashflow_only', 'Cashflow only'],
    ],
  },
  {
    key: 'drawdown_order',
    label: 'Drawdown order',
    type: 'select',
    options: [
      ['', 'Unspecified'],
      ['taxable_first', 'Taxable first'],
      ['tax_deferred_first', 'Tax deferred first'],
      ['roth_first', 'Roth first'],
      ['pro_rata', 'Pro rata'],
      ['age_aware', 'Age aware'],
    ],
  },
];

export function buildTimelinePayload(timeline = {}, draft = {}) {
  const normalized = normalizeTimeline(timeline);
  const retirement = { ...normalized.retirement };
  for (const field of TIMELINE_RETIREMENT_FIELDS) {
    if (!Object.prototype.hasOwnProperty.call(draft, field.key)) continue;
    retirement[field.key] = parseTimelineValue(field, draft[field.key]);
  }
  return {
    schema_version: Number(normalized.schema_version || 2),
    events: normalized.events,
    retirement,
  };
}

export function renderTimeline(plan = {}, state = {}) {
  const timeline = normalizeTimeline(state.timeline);
  const draft = objectValue(state.draft);
  const events = timeline.events.slice(0, 6);
  const editing = Boolean(state.editing);

  return html`
    <section class="plan-timeline" data-plan-section="timeline">
      <header class="section-head compact">
        <span class="section-eyebrow">Timeline</span>
        <h2 class="section-title">Plan timeline</h2>
        <p class="section-lede">Keep the major timing assumptions that shape retirement and drawdown reviews in one place.</p>
      </header>

      ${state.error ? html`<p class="error-banner">${esc(state.error)}</p>` : ''}

      <div class="structure-summary">
        ${raw(summaryItem('Retirement age', fieldDisplay('target_retirement_age', timeline.retirement.target_retirement_age)))}
        ${raw(summaryItem('Retirement year', fieldDisplay('target_retirement_year', timeline.retirement.target_retirement_year)))}
        ${raw(summaryItem('Withdrawal', optionLabel('withdrawal_strategy', timeline.retirement.withdrawal_strategy)))}
        ${raw(summaryItem('Drawdown', optionLabel('drawdown_order', timeline.retirement.drawdown_order)))}
      </div>

      ${editing ? html`
        <div class="structure-form" data-form="plan-timeline">
          ${raw(TIMELINE_RETIREMENT_FIELDS.map(field => renderTimelineField(field, timeline, draft)).join(''))}
        </div>
        <div class="structure-actions">
          <button class="btn btn-primary" data-timeline-action="save" ${state.saving ? 'disabled' : ''}>
            ${state.saving ? 'Saving...' : 'Save timeline'}
          </button>
          <button class="btn btn-ghost" data-timeline-action="cancel" ${state.saving ? 'disabled' : ''}>Cancel</button>
          ${state.dirty ? html`<span class="marginalia">Timeline edits are staged.</span>` : html`<span class="marginalia">Adjust retirement timing or drawdown posture.</span>`}
        </div>
      ` : html`
        <div class="structure-actions">
          <button class="action-link" data-timeline-action="edit">Edit timeline <span class="arrow">&rsaquo;</span></button>
          ${state.busy ? html`<span class="marginalia">Loading timeline...</span>` : ''}
        </div>
      `}

      <div class="structure-list">
        <span class="story-block-eyebrow">Major events</span>
        ${events.length ? html`
          ${raw(events.map(renderEventRow).join(''))}
        ` : html`<p class="marginalia">No major events saved yet.</p>`}
      </div>
    </section>
  `;
}

function renderTimelineField(field, timeline, draft) {
  const value = draftValue(field, timeline.retirement, draft);
  const current = fieldDisplay(field.key, timeline.retirement[field.key]);
  return html`
    <label class="structure-field">
      <span class="assumption-label">${esc(field.label)}</span>
      ${field.type === 'select' ? renderSelect(field, value) : renderInput(field, value)}
      <span class="assumption-current">Current ${esc(current)}</span>
    </label>
  `;
}

function renderInput(field, value) {
  return html`
    <input
      data-timeline-field="${esc(field.key)}"
      type="number"
      step="1"
      inputmode="numeric"
      value="${esc(value)}"
    />
  `;
}

function renderSelect(field, value) {
  return html`
    <select data-timeline-field="${esc(field.key)}">
      ${(field.options || []).map(([optionValue, label]) => html`
        <option value="${esc(optionValue)}" ${String(optionValue) === String(value) ? 'selected' : ''}>${esc(label)}</option>
      `)}
    </select>
  `;
}

function renderEventRow(event = {}) {
  const title = clean(event.label) || titleText(event.event_type) || 'Timeline event';
  const date = clean(event.date) || 'Unscheduled';
  const amount = event.amount_usd == null ? '' : fmtUsd(event.amount_usd);
  const details = [
    titleText(event.event_type),
    titleText(event.impact_type),
    titleText(event.recurring_frequency),
    amount,
  ].filter(Boolean).join(' - ');
  return html`
    <article class="structure-row">
      <div>
        <strong>${esc(title)}</strong>
        <span>${esc(date)}</span>
      </div>
      <p>${esc(details || clean(event.notes) || 'Saved plan event')}</p>
    </article>
  `;
}

function summaryItem(label, value) {
  return html`
    <div class="structure-summary-item">
      <dt>${esc(label)}</dt>
      <dd>${esc(value || 'Unset')}</dd>
    </div>
  `;
}

function draftValue(field, retirement = {}, draft = {}) {
  if (Object.prototype.hasOwnProperty.call(draft, field.key)) return clean(draft[field.key]);
  const value = retirement[field.key];
  return value == null ? '' : String(value);
}

function optionLabel(fieldKey, value) {
  const field = TIMELINE_RETIREMENT_FIELDS.find(item => item.key === fieldKey);
  const option = field?.options?.find(([optionValue]) => String(optionValue) === String(value ?? ''));
  return option?.[1] || titleText(value) || 'Unset';
}

function fieldDisplay(fieldKey, value) {
  if (value == null || value === '') return 'Unset';
  if (fieldKey === 'withdrawal_strategy' || fieldKey === 'drawdown_order') return optionLabel(fieldKey, value);
  return String(value);
}

function parseTimelineValue(field, rawValue) {
  const text = clean(rawValue);
  if (!text) return null;
  if (field.type === 'integer') {
    const number = Number(text);
    return Number.isFinite(number) ? Math.round(number) : null;
  }
  return text;
}

function normalizeTimeline(timeline = {}) {
  const source = timeline && typeof timeline === 'object' ? timeline : {};
  return {
    schema_version: Number(source.schema_version || 2),
    retirement: source.retirement && typeof source.retirement === 'object' ? source.retirement : {},
    events: Array.isArray(source.events) ? source.events.filter(event => event && typeof event === 'object') : [],
  };
}

function objectValue(value) {
  return value && typeof value === 'object' ? value : {};
}

function clean(value) {
  return String(value ?? '').trim();
}

function titleText(value) {
  return clean(value)
    .replace(/[_-]+/g, ' ')
    .replace(/\b\w/g, char => char.toUpperCase());
}
