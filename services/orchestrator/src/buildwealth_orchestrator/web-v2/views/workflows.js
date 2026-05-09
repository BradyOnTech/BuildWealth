// WORKFLOWS.
// Registered workflow templates with native parameter tuning, preview, and
// optional save-to-plan output.

import { api } from '../lib/api.js';
import { state } from '../lib/state.js';
import { html, raw, $, esc, setView } from '../lib/dom.js';
import { fmtRelative } from '../lib/format.js';

export const meta = {
  id: 'workflows',
  label: 'Workflows',
  numeral: '·',
  group: 'utility',
};

const ui = {
  loaded:    false,
  loadError: null,
  templates: [],
  plans:     [],
  runId:     null,            // id of the workflow currently running
  results:   new Map(),       // workflow_id → last result (or error)
};

export function template() {
  return html`
    <section class="page" id="workflows-page">
      <div class="workflows-shell" id="workflows-shell">
        ${raw(skeleton())}
      </div>
    </section>
  `;
}

export async function init() {
  attachHandlers();
  await load();
}

async function load() {
  ui.loaded = false;
  ui.loadError = null;
  try {
    const [templates, plans] = await Promise.all([
      api.workflowTemplates(),
      api.plans(100).catch(() => ({ plans: [] })),
    ]);
    ui.templates = Array.isArray(templates) ? templates : (templates?.items || []);
    ui.plans = Array.isArray(plans?.plans) ? plans.plans : (Array.isArray(plans) ? plans : []);
    ui.loaded = true;
  } catch (err) {
    ui.loadError = err.message || 'Could not load workflows.';
    state.lastError = ui.loadError;
  }
  render();
}

function render() {
  const shell = $('#workflows-shell');
  if (!shell) return;
  if (ui.loadError) {
    setView(shell, html`${raw(masthead())}<p class="error-banner">${ui.loadError}</p>`);
    return;
  }
  if (!ui.loaded) {
    setView(shell, html`${raw(masthead())}${raw(skeletonBody())}`);
    return;
  }
  setView(shell, html`
    ${raw(masthead())}
    ${ui.templates.length
      ? html`<div class="workflow-grid">${raw(ui.templates.map(workflowCard).join(''))}</div>`
      : html`<p class="profile-card-empty">No workflow templates registered.</p>`}
  `);
}

function masthead() {
  return html`
    <header class="settings-masthead">
      <p class="settings-eyebrow">§ Automation · Workflows</p>
      <h1 class="settings-title">Workflows</h1>
      <p class="settings-lede">
        Pre-built routines that read your latest snapshot and write a structured
        artifact. Tune the inputs, preview the report, and save the output to a
        plan when it is useful.
      </p>
    </header>
  `;
}

function workflowCard(t) {
  const result = ui.results.get(t.id);
  const isRunning = ui.runId === t.id;
  const defaults = t.default_params || {};
  return `
    <article class="workflow-card" data-workflow-card="${esc(t.id)}">
      <header class="workflow-card-head">
        <h3 class="workflow-card-title">${esc(t.title || t.id)}</h3>
        <code class="workflow-card-id">${esc(t.id)}</code>
      </header>
      <p class="workflow-card-desc">${esc(t.description || '')}</p>
      <form class="workflow-run-form" data-workflow-form="${esc(t.id)}">
        ${Object.entries(defaults).map(([key, value]) => renderParamField(key, value)).join('')}
        <label class="settings-field-toggle workflow-option">
          <input type="checkbox" name="use_live_snapshot" checked>
          <span>
            <span class="settings-label">Use live snapshot</span>
            <span class="settings-hint">Refresh portfolio state before the workflow runs.</span>
          </span>
        </label>
        <label class="settings-field-toggle workflow-option">
          <input type="checkbox" name="save_to_plan">
          <span>
            <span class="settings-label">Save report to plan</span>
            <span class="settings-hint">Keeps the generated report with the selected plan.</span>
          </span>
        </label>
        <label class="settings-field workflow-plan-field">
          <span class="settings-label">Plan</span>
          <select class="settings-input" name="plan_id">
            <option value="">Active plan</option>
            ${planOptions()}
          </select>
        </label>
        <footer class="workflow-card-foot">
          <button class="btn btn-primary btn-sm"
                  type="submit"
                  ${isRunning ? 'disabled' : ''}>
            ${isRunning ? 'Running...' : 'Run workflow'}
          </button>
          ${result ? renderResultLine(result) : ''}
        </footer>
      </form>
      ${result ? renderResultPreview(result) : ''}
    </article>
  `;
}

function renderParamField(key, value) {
  if (typeof value === 'boolean') {
    return `
      <label class="settings-field-toggle workflow-param workflow-option">
        <input type="checkbox" name="${esc(key)}" ${value ? 'checked' : ''}>
        <span>
          <span class="settings-label">${esc(humanWord(key))}</span>
          <span class="settings-hint">Boolean workflow option.</span>
        </span>
      </label>
    `;
  }
  if (Array.isArray(value)) {
    return `
      <label class="settings-field workflow-param">
        <span class="settings-label">${esc(humanWord(key))}</span>
        <input class="settings-input mono" type="text" name="${esc(key)}" value="${esc(value.join(', '))}">
        <span class="settings-hint">Comma-separated values.</span>
      </label>
    `;
  }
  const type = typeof value === 'number' ? 'number' : 'text';
  const step = Number.isInteger(value) ? '1' : '0.01';
  return `
    <label class="settings-field workflow-param">
      <span class="settings-label">${esc(humanWord(key))}</span>
      <input class="settings-input mono" type="${type}" ${type === 'number' ? `step="${step}"` : ''} name="${esc(key)}" value="${esc(formatParamValue(value))}">
    </label>
  `;
}

function planOptions() {
  return (ui.plans || []).map(plan => `
    <option value="${esc(plan.id || '')}">${esc(plan.title || plan.name || plan.id || 'Untitled plan')}</option>
  `).join('');
}

function renderResultPreview(result) {
  if (result.error) return '';
  const rawResult = result.raw || {};
  const markdown = String(rawResult.report_markdown || '').trim();
  const excerpt = markdown
    .split('\n')
    .filter(line => line.trim())
    .slice(0, 10)
    .join('\n');
  const recommendations = Array.isArray(rawResult.recommendations) ? rawResult.recommendations : [];
  const artifact = rawResult.artifact || null;
  return `
    <div class="workflow-result-preview">
      ${artifact ? `<p class="workflow-result ok">Saved to plan · ${esc(artifact.title || artifact.id || 'Artifact')}</p>` : ''}
      ${recommendations.length ? `<p class="workflow-result ok">${recommendations.length} recommendation${recommendations.length === 1 ? '' : 's'} created</p>` : ''}
      ${excerpt ? `<pre>${esc(excerpt)}</pre>` : '<p class="profile-card-empty">Workflow completed without a report preview.</p>'}
    </div>
  `;
}

function renderResultLine(result) {
  if (result.error) {
    return `<span class="workflow-result fail">Failed · ${esc(String(result.error).slice(0, 120))}</span>`;
  }
  const at = result.completed_at ? fmtRelative(result.completed_at) : 'just now';
  const summary = result.summary || result.headline || 'Completed';
  return `<span class="workflow-result ok">${esc(summary)} · ${esc(at)}</span>`;
}

/* ─────────────  Events  ───────────── */

function attachHandlers() {
  const root = $('#workflows-page');
  if (!root) return;
  root.addEventListener('submit', (e) => {
    const form = e.target.closest('[data-workflow-form]');
    if (!form) return;
    e.preventDefault();
    const id = form.getAttribute('data-workflow-form');
    if (id) runWorkflow(id, form);
  });
}

async function runWorkflow(workflowId, form = null) {
  if (ui.runId) return;
  const options = workflowRunOptions(workflowId, form);
  ui.runId = workflowId;
  ui.results.delete(workflowId);
  render();
  try {
    const result = await api.runWorkflow({
      workflow_id: workflowId,
      params: options.params,
      plan_id: options.planId || null,
      use_live_snapshot: options.useLiveSnapshot,
      save_to_plan: options.saveToPlan,
      create_recommendations: true,
    });
    ui.results.set(workflowId, {
      summary: result?.summary || result?.title || 'Completed',
      completed_at: new Date().toISOString(),
      raw: result,
    });
  } catch (err) {
    ui.results.set(workflowId, { error: err?.message || 'Workflow failed.' });
  } finally {
    ui.runId = null;
    render();
  }
}

function workflowRunOptions(workflowId, form) {
  const template = ui.templates.find(item => item.id === workflowId) || {};
  const defaults = template.default_params || {};
  const params = {};
  if (form) {
    const formData = new FormData(form);
    for (const [key, defaultValue] of Object.entries(defaults)) {
      if (typeof defaultValue === 'boolean') {
        params[key] = Boolean(form.elements[key]?.checked);
      } else {
        params[key] = parseParamValue(formData.get(key), defaultValue);
      }
    }
    return {
      params,
      useLiveSnapshot: Boolean(form.querySelector('[name="use_live_snapshot"]')?.checked),
      saveToPlan: Boolean(form.querySelector('[name="save_to_plan"]')?.checked),
      planId: String(formData.get('plan_id') || '').trim(),
    };
  }
  return {
    params: defaults,
    useLiveSnapshot: true,
    saveToPlan: false,
    planId: '',
  };
}

/* ─────────────  Helpers  ───────────── */

function humanWord(value) {
  return String(value || '').replace(/_/g, ' ');
}

function formatParamValue(value) {
  if (value == null) return '—';
  if (typeof value === 'number') return String(value);
  if (typeof value === 'boolean') return value ? 'Yes' : 'No';
  if (Array.isArray(value)) {
    if (!value.length) return '—';
    return value.slice(0, 4).map(formatParamValue).join(', ') + (value.length > 4 ? '…' : '');
  }
  if (typeof value === 'object') return JSON.stringify(value).slice(0, 60);
  return String(value);
}

function parseParamValue(value, defaultValue) {
  const text = String(value ?? '').trim();
  if (Array.isArray(defaultValue)) {
    if (!text) return [];
    return text.split(',').map(part => parseArrayItem(part.trim())).filter(item => item !== '');
  }
  if (typeof defaultValue === 'number') {
    const parsed = Number(text);
    return Number.isFinite(parsed) ? parsed : defaultValue;
  }
  if (typeof defaultValue === 'boolean') return Boolean(value);
  if (defaultValue && typeof defaultValue === 'object') {
    try { return JSON.parse(text); }
    catch { return defaultValue; }
  }
  return text;
}

function parseArrayItem(value) {
  if (!value) return '';
  const numeric = Number(value);
  return Number.isFinite(numeric) && /^-?\d+(\.\d+)?$/.test(value) ? numeric : value;
}

function skeleton() {
  return html`${raw(masthead())}${raw(skeletonBody())}`;
}

function skeletonBody() {
  return html`<div class="skeleton" style="height: 240px;">.</div>`;
}
