// PLAN — masthead + movements + look-closer footer.
//   I.   The story        — title, lede, key assumptions, top actions
//   IA.  The assumptions  — durable assumptions, active set, weak fields
//   IB.  The health       — confidence and review gaps
//   II.  The trajectory   — plan vs actual tracking
//   IIA. The evidence     — typed artifacts and citations
//   III. The decisions    — decision log + append form
// Footer — Look closer (links to classic for timeline, contribution rules, scenarios).

import { api } from '../lib/api.js';
import { state } from '../lib/state.js';
import { html, raw, esc, $, delegate } from '../lib/dom.js';
import { renderStory } from './plan/story.js';
import {
  buildAssumptionSetsPayload,
  buildPlanSettingsPatch,
  renderAssumptions,
} from './plan/assumptions.js';
import { derivePlanHealth, renderPlanHealth } from './plan/health.js';
import { renderTrajectory } from './plan/trajectory.js';
import { renderArtifacts } from './plan/artifacts.js';
import { renderDecisions } from './plan/decisions.js';

export const meta = {
  id: 'plan',
  label: 'Plan',
  numeral: 'III',
  group: 'daily',
};

const ui = {
  selectedId: null,
  section: '',
  plan: null,
  assumptions: { busy: false, assumptionSets: null, draft: {}, dirty: false, saving: false, error: null },
  health: { busy: false, recommendations: [], error: null },
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
  ui.section = String(params.section || '').trim().toLowerCase();
  attachHandlers();

  if (!ui.selectedId) {
    renderEmptyState();
    return;
  }
  await loadPlan(ui.selectedId);
  await loadAssumptionSets(ui.selectedId);
  await loadPlanHealth(ui.selectedId);
  rerenderAll();
  focusRequestedSection(params.section);
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

async function loadAssumptionSets(id) {
  ui.assumptions = {
    busy: true,
    assumptionSets: null,
    draft: {},
    dirty: false,
    saving: false,
    error: null,
  };
  try {
    ui.assumptions = {
      busy: false,
      assumptionSets: await api.planAssumptionSets(id),
      draft: {},
      dirty: false,
      saving: false,
      error: null,
    };
  } catch (err) {
    ui.assumptions = {
      busy: false,
      assumptionSets: null,
      draft: {},
      dirty: false,
      saving: false,
      error: err.message,
    };
  }
}

async function loadPlanHealth(id) {
  ui.health = { busy: true, recommendations: [], error: null };
  try {
    ui.health = {
      busy: false,
      recommendations: await api.recommendations({ planId: id, status: 'proposed', limit: 200 }),
      error: null,
    };
  } catch (err) {
    ui.health = { busy: false, recommendations: [], error: err.message };
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
  rerenderHealth();
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
    <div id="plan-assumptions">${raw(renderAssumptions(ui.plan, ui.assumptions))}</div>
    <div id="plan-health" data-plan-section="health">${raw(renderPlanHealth(ui.plan, currentPlanHealth()))}</div>
    <div id="plan-trajectory" data-plan-section="trajectory">${raw(renderTrajectory(ui.trajectory))}</div>
    <div id="plan-artifacts" data-plan-section="artifacts">${raw(renderArtifacts(ui.plan))}</div>
    <div id="plan-decisions" data-plan-section="decisions">${raw(renderDecisions(ui.plan, ui.decisions))}</div>
    ${raw(renderLookCloser(ui.plan))}
  `;
}

function currentPlanHealth() {
  return derivePlanHealth(ui.plan, {
    recommendations: ui.health.recommendations,
    tracking: ui.trajectory.tracking,
  });
}

function rerenderAssumptions() {
  const root = $('#plan-assumptions');
  if (!root || !ui.plan) return;
  root.innerHTML = renderAssumptions(ui.plan, ui.assumptions);
}

function rerenderHealth() {
  const root = $('#plan-health');
  if (!root || !ui.plan) return;
  root.innerHTML = renderPlanHealth(ui.plan, currentPlanHealth());
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

function planResearchDossierArtifacts(plan) {
  const artifacts = Array.isArray(plan?.artifacts) ? plan.artifacts : [];
  return artifacts.filter(artifact => {
    const id = String(artifact?.id || '').trim();
    if (!id) return false;
    const fileName = String(artifact?.file_name || '').toLowerCase();
    const title = String(artifact?.title || '').trim();
    return fileName.includes('-research-dossier-') || title.toLowerCase().startsWith('research dossier');
  }).slice(0, 3);
}

export function renderLookCloser(plan) {
  const id = encodeURIComponent(plan.id);
  const researchArtifacts = planResearchDossierArtifacts(plan);
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
      ${researchArtifacts.length ? html`
        <div class="look-closer-row">
          ${raw(researchArtifacts.map(artifact => {
            const artifactId = encodeURIComponent(String(artifact.id || '').trim());
            const title = esc(artifact.title || artifact.file_name || artifact.id);
            return html`
              <span class="link-cluster">
                <span class="muted">${title}</span>
                <a class="link-editorial" href="#research?dossier=${artifactId}&plan=${id}">Dossier</a>
                <a class="link-editorial" href="#research?thesisReview=${artifactId}&plan=${id}">Review thesis</a>
              </span>
            `;
          }).join(''))}
        </div>
      ` : ''}
      <p class="look-closer-note">The remaining settings links open the classic plan workspace while those surfaces move into v2.</p>
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
    ui.section = '';
    ui.plan = null;
    ui.assumptions = { busy: false, assumptionSets: null, draft: {}, dirty: false, saving: false, error: null };
    ui.health = { busy: false, recommendations: [], error: null };
    rerenderBody();
    await loadPlan(id);
    await loadAssumptionSets(id);
    await loadPlanHealth(id);
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

  delegate(page, 'change', '[data-assumption-field]', (_, el) => stageAssumptionEdit(el));
  delegate(page, 'click', '[data-assumption-action="reset"]', () => resetAssumptionEdits());
  delegate(page, 'click', '[data-assumption-action="save"]', () => saveAssumptions());

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
    await loadAssumptionSets(created.id);
    await loadPlanHealth(created.id);
    rerenderAll();
    loadTrajectory(created.id);
  } catch (err) {
    window.alert(`Could not create plan: ${err.message}`);
  }
}

function stageAssumptionEdit(el) {
  const field = String(el.dataset.assumptionField || '').trim();
  if (!field) return;
  ui.assumptions.draft = {
    ...(ui.assumptions.draft || {}),
    [field]: el.value,
  };
  ui.assumptions.dirty = true;
  ui.assumptions.error = null;
  rerenderAssumptions();
}

function resetAssumptionEdits() {
  ui.assumptions.draft = {};
  ui.assumptions.dirty = false;
  ui.assumptions.error = null;
  rerenderAssumptions();
}

async function saveAssumptions() {
  if (!ui.plan || !ui.assumptions.dirty || ui.assumptions.saving) return;

  const draft = ui.assumptions.draft || {};
  const settingsPatch = buildPlanSettingsPatch(ui.plan, draft);
  const currentAssumptionSets = ui.assumptions.assumptionSets || {};
  const activeSetId = String(draft.active_assumption_set_id || '').trim();
  const activeSetChanged = Boolean(activeSetId)
    && activeSetId !== String(currentAssumptionSets.active_assumption_set_id || '').trim();

  if (!Object.keys(settingsPatch).length && !activeSetChanged) {
    resetAssumptionEdits();
    return;
  }

  ui.assumptions.saving = true;
  ui.assumptions.error = null;
  rerenderAssumptions();

  try {
    if (Object.keys(settingsPatch).length) {
      ui.plan = await api.planSettings(ui.plan.id, settingsPatch);
      state.plan = ui.plan;
      await loadPlanHealth(ui.plan.id);
    }
    if (activeSetChanged) {
      ui.assumptions.assumptionSets = await api.updatePlanAssumptionSets(
        ui.plan.id,
        buildAssumptionSetsPayload(currentAssumptionSets, activeSetId),
      );
      ui.plan = await api.plan(ui.plan.id);
      state.plan = ui.plan;
    }
    ui.assumptions.draft = {};
    ui.assumptions.dirty = false;
    ui.assumptions.saving = false;
    ui.assumptions.error = null;
    rerenderAll();
    focusRequestedSection(ui.section);
  } catch (err) {
    ui.assumptions.saving = false;
    ui.assumptions.error = err.message;
    rerenderAssumptions();
  }
}

function focusRequestedSection(section) {
  const requested = String(section || '').trim().toLowerCase();
  if (!requested) return;
  const target = document.querySelector(`[data-plan-section="${requested}"]`);
  if (!target) return;
  target.scrollIntoView({ block: 'start', behavior: 'smooth' });
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
