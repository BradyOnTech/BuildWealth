// PLAN — masthead + movements + look-closer footer.
//   I.   The story        — title, lede, key assumptions, top actions
//   IA.  The assumptions  — durable assumptions, active set, weak fields
//   IB.  The health       — confidence and review gaps
//   II.  The trajectory   — plan vs actual tracking
//   IIA. The evidence     — typed artifacts and citations
//   IIB. The scenarios    — scenario diff review surface
//   IID. The timeline     — retirement timing, drawdown posture, events
//   IIE. The contributions — account priority and target rules
//   III. The decisions    — decision log + append form
// Footer — Look closer (links to advanced classic surfaces during migration).

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
import { buildScenarioDiffPayload, renderScenarios } from './plan/scenarios.js';
import { buildTimelinePayload, renderTimeline } from './plan/timeline.js';
import { buildContributionRulesPayload, renderContributions } from './plan/contributions.js';
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
  scenarios: { draft: {}, dirty: false, busy: false, result: null, error: null, focusedRecommendationId: '' },
  timeline: { busy: false, timeline: null, draft: {}, dirty: false, editing: false, saving: false, error: null },
  contributions: { busy: false, contributionRules: null, draft: {}, dirty: false, editing: false, saving: false, error: null },
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
  ui.scenarios.focusedRecommendationId = String(params.focus || params.recommendation || '').trim();
  attachHandlers();

  if (!ui.selectedId) {
    renderEmptyState();
    return;
  }
  await loadPlan(ui.selectedId);
  await loadAssumptionSets(ui.selectedId);
  await loadPlanHealth(ui.selectedId);
  await loadTimeline(ui.selectedId);
  await loadContributionRules(ui.selectedId);
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

async function loadTimeline(id) {
  ui.timeline = {
    busy: true,
    timeline: null,
    draft: {},
    dirty: false,
    editing: false,
    saving: false,
    error: null,
  };
  try {
    ui.timeline = {
      busy: false,
      timeline: await api.planTimeline(id),
      draft: {},
      dirty: false,
      editing: false,
      saving: false,
      error: null,
    };
  } catch (err) {
    ui.timeline = {
      busy: false,
      timeline: null,
      draft: {},
      dirty: false,
      editing: false,
      saving: false,
      error: err.message,
    };
  }
}

async function loadContributionRules(id) {
  ui.contributions = {
    busy: true,
    contributionRules: null,
    draft: {},
    dirty: false,
    editing: false,
    saving: false,
    error: null,
  };
  try {
    ui.contributions = {
      busy: false,
      contributionRules: await api.planContributionRules(id),
      draft: {},
      dirty: false,
      editing: false,
      saving: false,
      error: null,
    };
  } catch (err) {
    ui.contributions = {
      busy: false,
      contributionRules: null,
      draft: {},
      dirty: false,
      editing: false,
      saving: false,
      error: err.message,
    };
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
    <div id="plan-scenarios" data-plan-section="scenarios">${raw(renderScenarios(ui.plan, ui.scenarios, ui.assumptions))}</div>
    <div id="plan-timeline" data-plan-section="timeline">${raw(renderTimeline(ui.plan, ui.timeline))}</div>
    <div id="plan-contributions" data-plan-section="contributions">${raw(renderContributions(ui.plan, ui.contributions))}</div>
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

function rerenderScenarios() {
  const root = $('#plan-scenarios');
  if (!root || !ui.plan) return;
  root.innerHTML = renderScenarios(ui.plan, ui.scenarios, ui.assumptions);
}

function rerenderTimelineWorkspace() {
  const root = $('#plan-timeline');
  if (!root || !ui.plan) return;
  root.innerHTML = renderTimeline(ui.plan, ui.timeline);
}

function rerenderContributionsWorkspace() {
  const root = $('#plan-contributions');
  if (!root || !ui.plan) return;
  root.innerHTML = renderContributions(ui.plan, ui.contributions);
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
        <a class="link-editorial" href="#plan?id=${id}&amp;section=timeline">Timeline events</a>
        <a class="link-editorial" href="#plan?id=${id}&amp;section=contributions">Contribution rules</a>
        <a class="link-editorial" href="#plan?id=${id}&amp;section=scenarios">Run a scenario diff</a>
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
    ui.scenarios = { draft: {}, dirty: false, busy: false, result: null, error: null, focusedRecommendationId: '' };
    ui.timeline = { busy: false, timeline: null, draft: {}, dirty: false, editing: false, saving: false, error: null };
    ui.contributions = { busy: false, contributionRules: null, draft: {}, dirty: false, editing: false, saving: false, error: null };
    rerenderBody();
    await loadPlan(id);
    await loadAssumptionSets(id);
    await loadPlanHealth(id);
    await loadTimeline(id);
    await loadContributionRules(id);
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

  delegate(page, 'change', '[data-scenario-field]', (_, el) => stageScenarioEdit(el));
  delegate(page, 'click', '[data-scenario-action="run"]', () => runScenarioDiff());
  delegate(page, 'click', '[data-scenario-action="save-decision"]', () => saveScenarioDecisionNote());

  delegate(page, 'change', '[data-timeline-field]', (_, el) => stageTimelineEdit(el));
  delegate(page, 'click', '[data-timeline-action="edit"]', () => openTimelineEditor());
  delegate(page, 'click', '[data-timeline-action="cancel"]', () => resetTimelineEditor());
  delegate(page, 'click', '[data-timeline-action="save"]', () => saveTimeline());

  delegate(page, 'change', '[data-contribution-field]', (_, el) => stageContributionEdit(el));
  delegate(page, 'click', '[data-contribution-action="edit"]', () => openContributionEditor());
  delegate(page, 'click', '[data-contribution-action="cancel"]', () => resetContributionEditor());
  delegate(page, 'click', '[data-contribution-action="save"]', () => saveContributionRules());

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
    await loadTimeline(created.id);
    await loadContributionRules(created.id);
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

function stageScenarioEdit(el) {
  const field = String(el.dataset.scenarioField || '').trim();
  if (!field) return;
  ui.scenarios.draft = {
    ...(ui.scenarios.draft || {}),
    [field]: el.value,
  };
  ui.scenarios.dirty = true;
  ui.scenarios.error = null;
  rerenderScenarios();
}

async function runScenarioDiff() {
  if (!ui.plan || ui.scenarios.busy) return;
  const payload = buildScenarioDiffPayload(ui.scenarios.draft || {});
  const hasCompareSettings = Object.keys(payload.compare_settings || {}).length > 0;
  const hasOtherContext = Boolean(payload.current_portfolio_value_usd || payload.assumption_set_id || payload.candidate_assumption_set_id);
  if (!hasCompareSettings && !hasOtherContext) {
    ui.scenarios.error = 'Stage at least one setting or assumption-set comparison.';
    rerenderScenarios();
    return;
  }

  ui.scenarios.busy = true;
  ui.scenarios.error = null;
  rerenderScenarios();
  try {
    ui.scenarios.result = await api.planScenarioDiff(ui.plan.id, payload);
    ui.scenarios.busy = false;
    ui.scenarios.dirty = false;
    rerenderScenarios();
  } catch (err) {
    ui.scenarios.busy = false;
    ui.scenarios.error = err.message;
    rerenderScenarios();
  }
}

async function saveScenarioDecisionNote() {
  if (!ui.plan || !ui.scenarios.result || ui.scenarios.busy) return;
  ui.scenarios.busy = true;
  ui.scenarios.error = null;
  rerenderScenarios();
  try {
    await api.appendDecision(ui.plan.id, {
      summary: 'Reviewed scenario diff',
      rationale: scenarioDecisionRationale(ui.scenarios.result),
      status: 'proposed',
    });
    ui.plan = await api.plan(ui.plan.id);
    state.plan = ui.plan;
    ui.scenarios.busy = false;
    rerenderAll();
    focusRequestedSection('scenarios');
  } catch (err) {
    ui.scenarios.busy = false;
    ui.scenarios.error = err.message;
    rerenderScenarios();
  }
}

function openTimelineEditor() {
  ui.timeline.editing = true;
  ui.timeline.error = null;
  rerenderTimelineWorkspace();
}

function resetTimelineEditor() {
  ui.timeline.draft = {};
  ui.timeline.dirty = false;
  ui.timeline.editing = false;
  ui.timeline.saving = false;
  ui.timeline.error = null;
  rerenderTimelineWorkspace();
}

function stageTimelineEdit(el) {
  const field = String(el.dataset.timelineField || '').trim();
  if (!field) return;
  ui.timeline.draft = {
    ...(ui.timeline.draft || {}),
    [field]: el.value,
  };
  ui.timeline.dirty = true;
  ui.timeline.error = null;
  rerenderTimelineWorkspace();
}

async function saveTimeline() {
  if (!ui.plan || ui.timeline.saving) return;
  const payload = buildTimelinePayload(ui.timeline.timeline || {}, ui.timeline.draft || {});
  ui.timeline.saving = true;
  ui.timeline.error = null;
  rerenderTimelineWorkspace();
  try {
    ui.timeline.timeline = await api.updatePlanTimeline(ui.plan.id, payload);
    ui.plan = await api.plan(ui.plan.id);
    state.plan = ui.plan;
    ui.timeline.draft = {};
    ui.timeline.dirty = false;
    ui.timeline.editing = false;
    ui.timeline.saving = false;
    rerenderAll();
    focusRequestedSection('timeline');
  } catch (err) {
    ui.timeline.saving = false;
    ui.timeline.error = err.message;
    rerenderTimelineWorkspace();
  }
}

function openContributionEditor() {
  ui.contributions.editing = true;
  ui.contributions.error = null;
  rerenderContributionsWorkspace();
}

function resetContributionEditor() {
  ui.contributions.draft = {};
  ui.contributions.dirty = false;
  ui.contributions.editing = false;
  ui.contributions.saving = false;
  ui.contributions.error = null;
  rerenderContributionsWorkspace();
}

function stageContributionEdit(el) {
  const field = String(el.dataset.contributionField || '').trim();
  if (!field) return;
  ui.contributions.draft = {
    ...(ui.contributions.draft || {}),
    [field]: el.value,
  };
  ui.contributions.dirty = true;
  ui.contributions.error = null;
  rerenderContributionsWorkspace();
}

async function saveContributionRules() {
  if (!ui.plan || ui.contributions.saving) return;
  const payload = buildContributionRulesPayload(
    ui.contributions.contributionRules || {},
    ui.contributions.draft || {},
  );
  ui.contributions.saving = true;
  ui.contributions.error = null;
  rerenderContributionsWorkspace();
  try {
    ui.contributions.contributionRules = await api.updatePlanContributionRules(ui.plan.id, payload);
    ui.plan = await api.plan(ui.plan.id);
    state.plan = ui.plan;
    ui.contributions.draft = {};
    ui.contributions.dirty = false;
    ui.contributions.editing = false;
    ui.contributions.saving = false;
    rerenderAll();
    focusRequestedSection('contributions');
  } catch (err) {
    ui.contributions.saving = false;
    ui.contributions.error = err.message;
    rerenderContributionsWorkspace();
  }
}

function scenarioDecisionRationale(result = {}) {
  const baseline = Array.isArray(result.scenario_deltas)
    ? result.scenario_deltas.find(row => String(row?.label || '') === 'baseline') || result.scenario_deltas[0]
    : null;
  if (!baseline) return 'Scenario diff reviewed in v2 Plan.';
  const future = Number(baseline.delta_future_value_usd);
  const real = Number(baseline.delta_real_value_usd);
  const parts = ['Scenario diff reviewed in v2 Plan.'];
  if (Number.isFinite(future)) parts.push(`Future-value delta: ${future}.`);
  if (Number.isFinite(real)) parts.push(`Real-value delta: ${real}.`);
  return parts.join(' ');
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
