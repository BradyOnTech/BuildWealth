// Movement IIC — Life-event branches.
// Template-driven what-if previews for real-world planning changes.

import { html, raw, esc } from '../../lib/dom.js';
import { fmtPctSigned, fmtUsd, fmtUsdSigned } from '../../lib/format.js';

const BRANCH_COMPARE_FIELDS = [
  { key: 'annual_contribution_usd', label: 'Annual contribution', type: 'money' },
  { key: 'expected_return_baseline', label: 'Expected return', type: 'percent' },
  { key: 'inflation_rate', label: 'Inflation', type: 'percent' },
  { key: 'marginal_tax_rate', label: 'Marginal tax', type: 'percent' },
  { key: 'years', label: 'Years horizon', type: 'integer' },
];

export function buildScenarioBranchPayload(template = {}, draft = {}) {
  const payload = {
    branch_name: clean(draft.branch_name) || clean(template.branch_name) || clean(template.name) || 'What-If Branch',
    branch_template_id: clean(template.id) || null,
    compare_settings: objectValue(template.compare_settings),
    branch_events: Array.isArray(template.branch_events) ? template.branch_events : [],
  };

  const currentPortfolio = parseBranchValue({ type: 'money' }, draft.current_portfolio_value_usd);
  if (currentPortfolio != null) payload.current_portfolio_value_usd = currentPortfolio;

  const assumptionSetId = clean(draft.assumption_set_id || template.assumption_set_id);
  if (assumptionSetId) payload.assumption_set_id = assumptionSetId;

  for (const field of BRANCH_COMPARE_FIELDS) {
    if (!Object.prototype.hasOwnProperty.call(draft, field.key)) continue;
    const value = parseBranchValue(field, draft[field.key]);
    if (value != null) payload.compare_settings[field.key] = value;
  }

  return payload;
}

export function renderBranches(plan = {}, state = {}, assumptionState = {}) {
  const templatesPayload = normalizeTemplates(state.branchTemplates);
  const templates = templatesPayload.templates;
  const selected = selectedTemplate(templatesPayload, clean(state.selectedTemplateId));
  const draft = objectValue(state.draft);
  const result = objectValue(state.result);
  const planId = clean(plan.id);
  const hasResult = Boolean(Object.keys(result).length);

  return html`
    <section class="plan-branches" data-plan-section="branches">
      <header class="section-head compact">
        <span class="section-eyebrow">What-ifs</span>
        <h2 class="section-title">Preview a real-world change.</h2>
        <p class="section-lede">Start from a common life event, preview the assumptions, then run it as a simulation before touching the active plan.</p>
      </header>

      ${state.error ? html`<p class="error-banner">${esc(state.error)}</p>` : ''}

      ${templates.length ? html`
        <div class="scenario-grid" data-form="plan-scenario-branch">
          <label class="scenario-field">
            <span class="assumption-label">Template</span>
            <select data-branch-field="template_id">
              ${templates.map(template => {
                const id = clean(template.id);
                return html`<option value="${esc(id)}" ${id === clean(selected.id) ? 'selected' : ''}>${esc(clean(template.name) || id)}</option>`;
              })}
            </select>
            <span class="assumption-current">${templates.length} saved template${templates.length === 1 ? '' : 's'}</span>
          </label>
          <label class="scenario-field">
            <span class="assumption-label">Branch name</span>
            <input data-branch-field="branch_name" type="text" value="${esc(draftValue('branch_name', draft, selected.branch_name || selected.name || ''))}" />
            <span class="assumption-current">${esc(clean(selected.description) || 'Template branch')}</span>
          </label>
          <label class="scenario-field">
            <span class="assumption-label">Portfolio value override</span>
            <input data-branch-field="current_portfolio_value_usd" type="number" step="1000" inputmode="decimal" value="${esc(draft.current_portfolio_value_usd ?? '')}" />
            <span class="assumption-current">Optional</span>
          </label>
          ${renderAssumptionPicker(assumptionState, draft, selected)}
          ${raw(BRANCH_COMPARE_FIELDS.map(field => renderCompareField(field, draft, selected)).join(''))}
        </div>

        ${raw(renderTemplateSummary(selected))}

        <div class="scenario-actions">
          <button class="btn btn-primary" data-branch-action="run" ${state.busy ? 'disabled' : ''}>
            ${state.busy ? 'Running...' : 'Run what-if simulation'}
          </button>
          ${state.dirty ? html`<span class="marginalia">What-if inputs are staged for review.</span>` : html`<span class="marginalia">Choose a template or stage an override.</span>`}
        </div>
      ` : html`
        <div class="empty-block">
          <span class="glyph">⌁</span>
          <p>No branch templates are saved for this plan yet.</p>
        </div>
      `}

      ${hasResult ? raw(renderBranchResult(planId, result)) : ''}
    </section>
  `;
}

function renderCompareField(field, draft = {}, template = {}) {
  const value = Object.prototype.hasOwnProperty.call(draft, field.key) ? draft[field.key] : '';
  const current = formatCompareValue(field, objectValue(template.compare_settings)[field.key]);
  return html`
    <label class="scenario-field">
      <span class="assumption-label">${esc(field.label)}</span>
      <input
        data-branch-field="${esc(field.key)}"
        type="number"
        step="${field.type === 'integer' ? '1' : '0.1'}"
        inputmode="decimal"
        value="${esc(value)}"
      />
      <span class="assumption-current">${esc(current || 'Template default')}</span>
    </label>
  `;
}

function renderAssumptionPicker(assumptionState = {}, draft = {}, template = {}) {
  const assumptionSets = normalizeAssumptionSets(assumptionState.assumptionSets);
  const value = clean(draft.assumption_set_id || template.assumption_set_id);
  const sets = assumptionSets.sets.length
    ? assumptionSets.sets
    : [{ id: '', name: 'Current plan settings' }];
  return html`
    <label class="scenario-field">
      <span class="assumption-label">Assumption set</span>
      <select data-branch-field="assumption_set_id">
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

function renderTemplateSummary(template = {}) {
  const events = Array.isArray(template.branch_events) ? template.branch_events : [];
  const settings = objectValue(template.compare_settings);
  const settingRows = Object.entries(settings).filter(([, value]) => value != null && value !== '');
  return html`
    <div class="scenario-result branch-template-summary">
      <header class="section-head compact">
        <span class="section-eyebrow">Template details</span>
        <h3 class="section-title">${esc(clean(template.name) || 'Selected branch')}</h3>
      </header>
      ${events.length ? html`
        <div class="scenario-delta-table">
          ${raw(events.slice(0, 4).map(event => html`
            <article class="scenario-delta-row">
              <h4>${esc(clean(event.label) || 'Life event')}</h4>
              <dl>
                <div>
                  <dt>Impact</dt>
                  <dd>${esc(titleText(event.impact_type || event.event_type || 'event'))}</dd>
                </div>
                <div>
                  <dt>Amount</dt>
                  <dd>${fmtUsd(Number(event.amount_usd))} ${esc(clean(event.recurring_frequency || 'one_time').replace(/_/g, ' '))}</dd>
                </div>
                ${event.duration_months ? html`
                  <div>
                    <dt>Duration</dt>
                    <dd>${Number(event.duration_months)} months</dd>
                  </div>
                ` : ''}
              </dl>
            </article>
          `).join(''))}
        </div>
      ` : html`<p class="marginalia">This template only changes plan settings.</p>`}
      ${settingRows.length ? html`
        <dl class="scenario-change-list">
          ${raw(settingRows.map(([key, value]) => html`
            <div>
              <dt>${esc(humanText(key))}</dt>
              <dd>${esc(String(value))}</dd>
            </div>
          `).join(''))}
        </dl>
      ` : ''}
    </div>
  `;
}

function renderBranchResult(planId = '', result = {}) {
  const deltas = Array.isArray(result.scenario_deltas) ? result.scenario_deltas : [];
  const monte = objectValue(result.monte_carlo_delta);
  const simulation = objectValue(result.simulation_delta);
  const name = clean(result.branch_name || result.branch_template_name || 'Branch');

  return html`
    <div class="scenario-result">
      <header class="section-head compact">
        <span class="section-eyebrow">What-if result</span>
        <h3 class="section-title">Simulation compared.</h3>
        <p class="section-lede">${esc(name)}</p>
      </header>

      ${deltas.length ? html`
        <div class="scenario-delta-table">
          ${raw(deltas.map(row => renderDeltaRow(row)).join(''))}
        </div>
      ` : html`<p class="marginalia">No branch deltas were returned.</p>`}

      ${Object.keys(monte).length ? raw(renderMetricBlock('Monte Carlo', monte)) : ''}
      ${Object.keys(simulation).length ? raw(renderMetricBlock('Simulation', simulation)) : ''}

      <div class="scenario-handoff">
        <a class="link-editorial" href="#copilot?intent=plan-branch&amp;plan=${encodeURIComponent(planId)}">Discuss in Copilot</a>
        <button class="action-link" data-branch-action="save-simulation">Save simulation <span class="arrow">›</span></button>
        <button class="action-link" data-branch-action="save-decision">Save decision note <span class="arrow">›</span></button>
      </div>
    </div>
  `;
}

function renderDeltaRow(row = {}) {
  const label = titleText(row.label || 'scenario');
  const candidateFuture = row.candidate_future_value_usd ?? row.branch_future_value_usd;
  const candidateReal = row.candidate_real_value_usd ?? row.branch_real_value_usd;
  return html`
    <article class="scenario-delta-row">
      <h4>${esc(label)}</h4>
      <dl>
        <div>
          <dt>Future value</dt>
          <dd>${fmtUsd(row.base_future_value_usd)} -> ${fmtUsd(candidateFuture)} <span>${fmtUsdSigned(row.delta_future_value_usd)}</span></dd>
        </div>
        <div>
          <dt>Real value</dt>
          <dd>${fmtUsd(row.base_real_value_usd)} -> ${fmtUsd(candidateReal)} <span>${fmtUsdSigned(row.delta_real_value_usd)}</span></dd>
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

function selectedTemplate(payload = {}, requestedId = '') {
  const templates = Array.isArray(payload.templates) ? payload.templates : [];
  const defaultId = clean(requestedId || payload.default_template_id);
  return templates.find(template => clean(template.id) === defaultId) || templates[0] || {};
}

function normalizeTemplates(payload = {}) {
  return {
    default_template_id: clean(payload?.default_template_id),
    templates: Array.isArray(payload?.templates) ? payload.templates.filter(item => item && typeof item === 'object') : [],
  };
}

function normalizeAssumptionSets(payload = {}) {
  return {
    active_assumption_set_id: clean(payload?.active_assumption_set_id),
    sets: Array.isArray(payload?.sets) ? payload.sets.filter(item => item && typeof item === 'object') : [],
  };
}

function parseBranchValue(field, raw) {
  const text = clean(raw);
  if (!text) return null;
  const value = Number(text);
  if (!Number.isFinite(value)) return null;
  if (field.type === 'percent') return value / 100;
  if (field.type === 'integer') return Math.trunc(value);
  return value;
}

function formatCompareValue(field, value) {
  if (value == null || value === '') return '';
  if (field.type === 'money') return fmtUsd(Number(value));
  if (field.type === 'percent') return `${Number(value) * 100}%`;
  return String(value);
}

function formatMetricValue(key, value) {
  const numeric = Number(value);
  if (Number.isFinite(numeric)) {
    if (String(key).includes('probability') || String(key).includes('rate')) {
      return fmtPctSigned(numeric, { fromFraction: true });
    }
    if (String(key).includes('usd') || String(key).includes('value')) {
      return fmtUsdSigned(numeric);
    }
  }
  if (typeof value === 'string') return value.replace(/_/g, ' ');
  return String(value);
}

function draftValue(key, draft = {}, fallback = '') {
  if (Object.prototype.hasOwnProperty.call(draft, key)) return draft[key];
  return fallback;
}

function objectValue(value) {
  return value && typeof value === 'object' && !Array.isArray(value) ? value : {};
}

function humanText(value) {
  return clean(value)
    .replace(/_/g, ' ')
    .replace(/\b\w/g, char => char.toUpperCase());
}

function titleText(value) {
  return humanText(value || '');
}

function clean(value) {
  return String(value ?? '').trim();
}
