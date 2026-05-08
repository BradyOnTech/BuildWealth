// WORKFLOWS.
// A discoverable list of registered workflow templates with a one-click run
// against the latest snapshot. The full workflow editor (parameter tuning,
// preview, save-to-plan) stays in classic for now — this surface answers
// "what's available?" and "let me try one with the defaults".

import { api } from '../lib/api.js';
import { state } from '../lib/state.js';
import { html, raw, $, esc, setView, delegate } from '../lib/dom.js';
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
    const templates = await api.workflowTemplates();
    ui.templates = Array.isArray(templates) ? templates : (templates?.items || []);
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
    ${raw(handoffCard())}
  `);
}

function masthead() {
  return html`
    <header class="settings-masthead">
      <p class="settings-eyebrow">§ Automation · Workflows</p>
      <h1 class="settings-title">Workflows</h1>
      <p class="settings-lede">
        Pre-built routines that read your latest snapshot and write a structured
        artifact. Run with defaults to inspect the output, then tune parameters
        in the classic editor when you want to save it to a plan.
      </p>
    </header>
  `;
}

function workflowCard(t) {
  const result = ui.results.get(t.id);
  const isRunning = ui.runId === t.id;
  const defaults = t.default_params || {};
  return `
    <article class="workflow-card">
      <header class="workflow-card-head">
        <h3 class="workflow-card-title">${esc(t.title || t.id)}</h3>
        <code class="workflow-card-id">${esc(t.id)}</code>
      </header>
      <p class="workflow-card-desc">${esc(t.description || '')}</p>
      ${Object.keys(defaults).length ? `
        <dl class="workflow-card-params">
          ${Object.entries(defaults).slice(0, 6).map(([key, value]) => `
            <div>
              <dt>${esc(humanWord(key))}</dt>
              <dd>${esc(formatParamValue(value))}</dd>
            </div>
          `).join('')}
        </dl>
      ` : ''}
      <footer class="workflow-card-foot">
        <button class="btn btn-primary btn-sm"
                data-workflow-run="${esc(t.id)}"
                ${isRunning ? 'disabled' : ''}>
          ${isRunning ? 'Running…' : 'Run with defaults'}
        </button>
        ${result ? renderResultLine(result) : ''}
      </footer>
    </article>
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

function handoffCard() {
  return html`
    <aside class="settings-handoff">
      <p class="settings-handoff-eyebrow">Need parameter tuning or save-to-plan?</p>
      <p class="settings-handoff-body">
        The workflow editor with parameter overrides, preview, and save-to-plan
        flow lives in <a href="/classic" class="link-editorial">Classic UI</a>. v2 will
        absorb it once the input shape is stable.
      </p>
    </aside>
  `;
}

/* ─────────────  Events  ───────────── */

function attachHandlers() {
  const root = $('#workflows-page');
  if (!root) return;
  delegate(root, 'click', '[data-workflow-run]', (e, el) => {
    e.preventDefault();
    const id = el.getAttribute('data-workflow-run');
    if (id) runWorkflow(id);
  });
}

async function runWorkflow(workflowId) {
  if (ui.runId) return;
  ui.runId = workflowId;
  ui.results.delete(workflowId);
  render();
  try {
    const result = await api.runWorkflow({
      workflow_id: workflowId,
      params: {},
      use_live_snapshot: true,
      save_to_plan: false,
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

function skeleton() {
  return html`${raw(masthead())}${raw(skeletonBody())}`;
}

function skeletonBody() {
  return html`<div class="skeleton" style="height: 240px;">.</div>`;
}
