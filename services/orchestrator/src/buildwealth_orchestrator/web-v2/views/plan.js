// PLAN — masthead + four movements + look-closer footer.
//   I.   The story        — title, lede, key assumptions, top actions
//   II.  The trajectory   — plan vs actual tracking
//   III. The decisions    — decision log + append form
// Footer — Look closer (links to classic for timeline, contribution rules, scenarios).

import { api } from '../lib/api.js';
import { state } from '../lib/state.js';
import { html, raw, esc, $, setView, delegate } from '../lib/dom.js';
import { renderStory } from './plan/story.js';
import { renderTrajectory } from './plan/trajectory.js';
import { renderDecisions } from './plan/decisions.js';

export const meta = {
  id: 'plan',
  label: 'Plan',
  numeral: 'III',
  group: 'daily',
};

const ui = {
  selectedId: null,
  plan: null,
  trajectory: { busy: false, tracking: null, error: null },
  decisions: { appendOpen: false, appendBusy: false, appendError: null },
};

export function template() {
  return html`
    <section class="page" id="plan-page">
      <div id="plan-masthead"></div>
      <div id="plan-body"></div>
    </section>
  `;
}

export async function init(params = {}) {
  ui.selectedId = params.id || pickInitialPlanId();
  attachHandlers();

  if (!ui.selectedId) {
    renderEmptyState();
    return;
  }
  await loadPlan(ui.selectedId);
  rerenderAll();
  loadTrajectory(ui.selectedId);
}

/* ─────────────  data  ───────────── */

function pickInitialPlanId() {
  if (state.activePlanId) return state.activePlanId;
  if (state.plans?.length) return state.plans[0].id;
  return null;
}

async function loadPlan(id) {
  try {
    ui.plan = await api.plan(id);
    state.plan = ui.plan;
  } catch (err) {
    ui.plan = null;
    ui.error = err.message;
  }
}

async function loadTrajectory(id) {
  ui.trajectory = { busy: true, tracking: null, error: null };
  rerenderTrajectory();
  try {
    ui.trajectory = { busy: false, tracking: await api.planTracking(id), error: null };
  } catch (err) {
    ui.trajectory = { busy: false, tracking: null, error: err.message };
  }
  rerenderTrajectory();
}

async function refreshPlanList() {
  try {
    state.plans = await api.plans();
  } catch { /* keep what we have */ }
}

/* ─────────────  rendering  ───────────── */

function rerenderAll() {
  rerenderMasthead();
  rerenderBody();
}

function rerenderMasthead() {
  const root = $('#plan-masthead');
  if (!root) return;
  root.innerHTML = renderMasthead();
}

function renderMasthead() {
  const plans = state.plans || [];
  const active = plans.find(p => p.is_active);
  const isActive = ui.plan && active && ui.plan.id === active.id;

  return html`
    <header class="plan-masthead">
      <div class="plan-masthead-left">
        <span class="plan-masthead-eyebrow">Plan</span>
        ${plans.length > 1 ? html`
          <select class="plan-picker" id="plan-select">
            ${plans.map(p => html`
              <option value="${p.id}" ${p.id === ui.selectedId ? 'selected' : ''}>${esc(p.title || 'Untitled')}</option>
            `)}
          </select>
        ` : html`
          <span class="plan-picker" style="cursor:default;background:none;padding-right:4px;">${esc(ui.plan?.title || (plans[0]?.title || 'No plan'))}</span>
        `}
        ${isActive ? html`<span class="plan-active-badge">active</span>` : ''}
      </div>
      <div class="entry-actions">
        ${ui.plan && !isActive ? html`<button class="action-link" data-plan-action="set-active">Make active <span class="arrow">›</span></button>` : ''}
        <button class="action-link muted" data-plan-action="create">New plan <span class="arrow">›</span></button>
      </div>
    </header>
  `;
}

function rerenderBody() {
  const root = $('#plan-body');
  if (!root) return;
  if (!ui.plan) {
    root.innerHTML = ui.error
      ? html`<p class="error-banner">${esc(ui.error)}</p>`
      : html`<div class="skeleton" style="height: 320px;">.</div>`;
    return;
  }

  root.innerHTML = html`
    ${raw(renderStory(ui.plan))}
    <div id="plan-trajectory">${raw(renderTrajectory(ui.trajectory))}</div>
    <div id="plan-decisions">${raw(renderDecisions(ui.plan, ui.decisions))}</div>
    ${raw(renderLookCloser(ui.plan))}
  `;
}

function rerenderTrajectory() {
  const root = $('#plan-trajectory');
  if (!root) return;
  root.innerHTML = renderTrajectory(ui.trajectory);
}

function rerenderDecisions() {
  const root = $('#plan-decisions');
  if (!root || !ui.plan) return;
  root.innerHTML = renderDecisions(ui.plan, ui.decisions);
}

function renderLookCloser(plan) {
  const id = encodeURIComponent(plan.id);
  return html`
    <footer class="look-closer">
      <span class="section-eyebrow">Look closer</span>
      <div class="look-closer-row">
        <a class="link-editorial" href="/#plans?id=${id}">Edit settings</a>
        <a class="link-editorial" href="/#plans?id=${id}">Timeline events</a>
        <a class="link-editorial" href="/#plans?id=${id}">Contribution rules</a>
        <a class="link-editorial" href="/#plans?id=${id}">Run a scenario diff</a>
        <a class="link-editorial" href="/#plans?id=${id}">Branch on a life event</a>
        <a class="link-editorial" href="/#plans?id=${id}">Compare withdrawal strategies</a>
        <a class="link-editorial" href="/#plans?id=${id}">Browse artifacts</a>
      </div>
      <p class="look-closer-note">Each opens the classic plan workspace — these surfaces haven't been re-set in the new vocabulary yet.</p>
    </footer>
  `;
}

function renderEmptyState() {
  const root = $('#plan-body');
  if (!root) return;
  root.innerHTML = html`
    <div class="placeholder">
      <span class="glyph">∮</span>
      <h2>No plan yet.</h2>
      <p>Create a plan to start modelling a long-horizon trajectory. Once it exists you'll be able to track actual against expected here.</p>
      <div class="entry-actions">
        <button class="action-link" data-plan-action="create">Create your first plan <span class="arrow">›</span></button>
      </div>
    </div>
  `;
}

/* ─────────────  events  ───────────── */

function attachHandlers() {
  const page = $('#plan-page');
  if (!page) return;

  delegate(page, 'change', '#plan-select', async (_, el) => {
    const id = el.value;
    if (!id || id === ui.selectedId) return;
    ui.selectedId = id;
    ui.plan = null;
    rerenderBody();
    await loadPlan(id);
    rerenderAll();
    loadTrajectory(id);
  });

  delegate(page, 'click', '[data-plan-action="set-active"]', async () => {
    if (!ui.plan) return;
    try {
      await api.setActivePlan(ui.plan.id);
      await refreshPlanList();
      rerenderMasthead();
    } catch (err) {
      ui.error = err.message;
      rerenderMasthead();
    }
  });

  delegate(page, 'click', '[data-plan-action="create"]', () => {
    const title = window.prompt('Title for the new plan:');
    if (!title) return;
    createPlan({ title: title.trim(), description: '' });
  });

  delegate(page, 'click', '[data-decision-action="open-append"]',  () => { ui.decisions.appendOpen = true;  rerenderDecisions(); });
  delegate(page, 'click', '[data-decision-action="cancel-append"]', () => { ui.decisions = { appendOpen: false, appendBusy: false, appendError: null }; rerenderDecisions(); });
  delegate(page, 'click', '[data-decision-action="submit-append"]', () => submitAppendDecision());
}

async function createPlan(body) {
  try {
    const created = await api.createPlan(body);
    await refreshPlanList();
    ui.selectedId = created.id;
    await loadPlan(created.id);
    rerenderAll();
    loadTrajectory(created.id);
  } catch (err) {
    window.alert(`Could not create plan: ${err.message}`);
  }
}

async function submitAppendDecision() {
  if (!ui.plan) return;
  const form = document.querySelector('[data-form="append-decision"]');
  if (!form) return;
  const summary = form.querySelector('[name="summary"]').value.trim();
  if (!summary) {
    ui.decisions.appendError = 'Summary is required.';
    rerenderDecisions();
    return;
  }
  const body = {
    summary,
    rationale: form.querySelector('[name="rationale"]').value.trim(),
    status: form.querySelector('[name="status"]').value || 'proposed',
  };
  ui.decisions.appendBusy = true;
  ui.decisions.appendError = null;
  rerenderDecisions();
  try {
    ui.plan = await api.appendDecision(ui.plan.id, body);
    ui.decisions = { appendOpen: false, appendBusy: false, appendError: null };
    rerenderDecisions();
  } catch (err) {
    ui.decisions.appendBusy = false;
    ui.decisions.appendError = err.message;
    rerenderDecisions();
  }
}
