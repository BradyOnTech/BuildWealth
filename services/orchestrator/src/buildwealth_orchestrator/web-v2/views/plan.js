// PLAN — masthead + reading surface + workbench folds + look-closer footer.
// The reading surface stays open (story, baseline trajectory, plan-vs-actual
// tracking). The nine workbench tools fold into one-line rows whose summaries
// carry the key fact, so the closed page still informs:
//   IA.  The assumptions  — durable assumptions, active set, weak fields
//   IB.  The health       — confidence and review gaps
//   IIA. The evidence     — typed artifacts and citations
//   IIB. The simulations  — simulation review surface
//   IIC. The what-ifs     — life-event branch templates
//   IID. The withdrawals  — retirement drawdown strategy comparison
//   IIE. The timeline     — retirement timing, drawdown posture, events
//   IIF. The contributions — account priority and target rules
//   III. The decisions    — decision log + append form
// Deep links (?section=) and post-save focus open the matching fold.
// Footer — Look closer (v2-first, with advanced planning fallbacks).

import { api } from '../lib/api.js';
import { state } from '../lib/state.js';
import { html, raw, esc, $, delegate } from '../lib/dom.js';
import { renderStory } from './plan/story.js';
import {
  PLAN_ASSUMPTION_FIELDS,
  buildAssumptionSetsPayload,
  buildPlanSettingsPatch,
  renderAssumptions,
} from './plan/assumptions.js';
import { derivePlanHealth, renderPlanHealth } from './plan/health.js';
import { renderTrajectory } from './plan/trajectory.js';
import { renderArtifacts } from './plan/artifacts.js';
import { buildScenarioBranchPayload, renderBranches } from './plan/branches.js';
import {
  buildScenarioDiffPayload,
  renderScenarios,
  renderTrajectoryPreview,
  setPeerBenchmark,
  setPlanTimelineEvents,
} from './plan/scenarios.js';
import { buildWithdrawalComparePayload, renderWithdrawals } from './plan/withdrawals.js';
import { buildTimelinePayload, renderTimeline } from './plan/timeline.js';
import { buildContributionRulesPayload, renderContributions } from './plan/contributions.js';
import { renderDecisions } from './plan/decisions.js';

export const meta = {
  id: 'plan',
  label: 'Plan',
  numeral: 'III',
  group: 'primary',
};

const ui = {
  selectedId: null,
  assumptionDefaults: null,
  section: '',
  openFolds: new Set(),
  plan: null,
  assumptions: { busy: false, assumptionSets: null, draft: {}, dirty: false, saving: false, error: null },
  health: { busy: false, recommendations: [], error: null },
  trajectory: { busy: false, tracking: null, error: null },
  trajectoryPreview: { busy: false, result: null, planId: '' },
  artifacts: { focusedArtifactId: '', focusedArtifact: null, busy: false, error: null },
  scenarios: { draft: {}, dirty: false, busy: false, saveBusy: false, result: null, explanation: null, reviewLevel: null, lastPayload: null, error: null, focusedRecommendationId: '' },
  branches: { busy: false, saveBusy: false, branchTemplates: null, selectedTemplateId: '', draft: {}, dirty: false, result: null, explanation: null, reviewLevel: null, lastPayload: null, error: null },
  savedSimulations: { busy: false, payload: null, error: null, focusedComparison: null, rerun: null },
  withdrawals: { busy: false, selectedStrategies: ['four_percent_rule', 'dynamic_guardrails', 'bucket_strategy'], draft: {}, dirty: false, result: null, error: null },
  timeline: { busy: false, timeline: null, draft: {}, dirty: false, editing: false, saving: false, error: null },
  contributions: { busy: false, contributionRules: null, draft: {}, dirty: false, editing: false, saving: false, error: null },
  decisions: { appendOpen: false, appendBusy: false, appendError: null },
};

export function template() {
  return html`
    <section class="page" id="plan-page">
      <div class="plan-shell" id="plan-shell">
        <div id="plan-masthead"></div>
        <div id="plan-body"></div>
      </div>
    </section>
  `;
}

export async function init(params = {}) {
  ui.selectedId = params.id || pickInitialPlanId();
  ui.section = String(params.section || '').trim().toLowerCase();
  ui.artifacts.focusedArtifactId = String(params.artifact || '').trim();
  ui.scenarios.focusedRecommendationId = String(params.focus || params.recommendation || '').trim();
  ui.savedSimulations.focusedSimulationId = String(params.saved || '').trim();
  ui.previewEvent = parsePreviewEvent(params);
  seedOpenFolds(params);
  attachHandlers();
  // Peer context for trajectory overlays — best-effort, before the fans draw.
  try {
    setPeerBenchmark(await api.peerBenchmark());
  } catch {
    setPeerBenchmark(null);
  }

  if (!ui.selectedId) {
    renderEmptyState();
    return;
  }
  await loadPlan(ui.selectedId);
  await loadAssumptionSets(ui.selectedId);
  await loadPlanHealth(ui.selectedId);
  await loadFocusedArtifact(ui.selectedId, params.artifact);
  await loadBranchTemplates(ui.selectedId);
  await loadSavedSimulations(ui.selectedId);
  if (ui.savedSimulations.focusedSimulationId) {
    await compareSavedSimulationCurrentById(ui.savedSimulations.focusedSimulationId, { render: false });
  }
  await loadTimeline(ui.selectedId);
  await loadContributionRules(ui.selectedId);
  rerenderAll();
  focusRequestedSection(params.section);
  loadTrajectory(ui.selectedId);
  loadTrajectoryPreview(ui.selectedId);
}

// Auto-run the baseline so the landing answers "am I going to be OK?"
// without a form. Cached per plan for the session; failures stay silent —
// the full Simulations section below is always available.
async function loadTrajectoryPreview(planId) {
  const id = String(planId || '').trim();
  if (!id) return;
  if (ui.trajectoryPreview.planId === id && (ui.trajectoryPreview.result || ui.trajectoryPreview.busy)) return;
  ui.trajectoryPreview = { busy: true, result: null, planId: id };
  rerenderTrajectoryPreview();
  try {
    const result = await api.planScenarioDiff(id, { compare_settings: {} });
    if (ui.trajectoryPreview.planId === id) {
      ui.trajectoryPreview = { busy: false, result, planId: id };
      rerenderTrajectoryPreview();
    }
  } catch {
    if (ui.trajectoryPreview.planId === id) {
      ui.trajectoryPreview = { busy: false, result: null, planId: id };
      rerenderTrajectoryPreview();
    }
  }
}

function rerenderTrajectoryPreview() {
  const root = $('#plan-trajectory-preview');
  if (!root || !ui.plan) return;
  root.innerHTML = renderTrajectoryPreview(ui.trajectoryPreview, ui.plan?.id);
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
  if (!ui.assumptionDefaults) {
    // Engine fallback values + provenance; the ledger shows real numbers
    // instead of the words "app default".
    api.planningAssumptionDefaults()
      .then((d) => {
        if (!d?.defaults) return;
        ui.assumptionDefaults = d.defaults;
        // Never clobber in-flight edits: the ledger provenance can wait a
        // render; a half-typed assumption draft cannot.
        if (!ui.assumptions?.dirty) rerenderAll();
      })
      .catch(() => { ui.assumptionDefaults = null; });
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

async function loadFocusedArtifact(planId, artifactId) {
  const focusedArtifactId = String(artifactId || '').trim();
  ui.artifacts = {
    focusedArtifactId,
    focusedArtifact: null,
    busy: Boolean(focusedArtifactId),
    error: null,
  };
  if (!focusedArtifactId) return;
  try {
    ui.artifacts = {
      focusedArtifactId,
      focusedArtifact: await api.planArtifact(planId, focusedArtifactId),
      busy: false,
      error: null,
    };
  } catch (err) {
    ui.artifacts = {
      focusedArtifactId,
      focusedArtifact: null,
      busy: false,
      error: err.message,
    };
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
  // Life events annotate the trajectory fans.
  setPlanTimelineEvents(ui.timeline.timeline?.events || []);
}

async function loadBranchTemplates(id) {
  ui.branches = {
    busy: true,
    branchTemplates: null,
    selectedTemplateId: '',
    draft: {},
    dirty: false,
    result: null,
    error: null,
  };
  try {
    let branchTemplates = await api.planBranchTemplates(id);
    let selectedTemplateId = String(branchTemplates?.default_template_id || '');
    // A life-plans preview arrives by deep link as an ephemeral template:
    // run it as a simulation, save nothing, close the tab, reality untouched.
    if (ui.previewEvent) {
      const previewTemplate = previewBranchTemplate(ui.previewEvent);
      branchTemplates = {
        ...branchTemplates,
        templates: [previewTemplate, ...(Array.isArray(branchTemplates?.templates) ? branchTemplates.templates : [])],
      };
      selectedTemplateId = previewTemplate.id;
    }
    ui.branches = {
      busy: false,
      branchTemplates,
      selectedTemplateId,
      draft: {},
      dirty: false,
      result: null,
      error: null,
    };
  } catch (err) {
    ui.branches = {
      busy: false,
      branchTemplates: null,
      selectedTemplateId: '',
      draft: {},
      dirty: false,
      result: null,
      error: err.message,
    };
  }
}

async function loadSavedSimulations(id) {
  const previous = ui.savedSimulations || {};
  ui.savedSimulations = { ...previous, busy: true, payload: previous.payload || null, error: null };
  try {
    ui.savedSimulations = {
      ...previous,
      busy: false,
      payload: await api.planSavedSimulations(id, 25),
      error: null,
    };
  } catch (err) {
    ui.savedSimulations = { ...previous, busy: false, payload: previous.payload || null, error: err.message };
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
    ${raw(renderStory(ui.plan, ui.assumptions, ui.timeline, ui.assumptionDefaults))}
    <div id="plan-trajectory-preview">${raw(renderTrajectoryPreview(ui.trajectoryPreview, ui.plan?.id))}</div>
    <div id="plan-trajectory" data-plan-section="trajectory">${raw(renderTrajectory(ui.trajectory))}</div>
    <div class="plan-workbench">
      <span class="section-eyebrow plan-workbench-eyebrow">The workbench</span>
      ${raw(FOLDS.map(fold => renderFold(fold)).join(''))}
    </div>
    ${raw(renderLookCloser(ui.plan))}
  `;
}

/* ─────────────  workbench folds  ─────────────
   Nine tools condensed to nine scannable rows — the rows are the table of
   contents. Bodies render up front (hidden while closed), so delegated
   handlers and targeted rerenders keep working and opening is instant. */

const FOLDS = [
  { key: 'assumptions', id: 'plan-assumptions', numeral: 'IA', title: 'The assumptions',
    summary: assumptionsFoldSummary,
    body: () => renderAssumptions(ui.plan, ui.assumptions) },
  { key: 'health', id: 'plan-health', numeral: 'IB', title: 'The health',
    summary: healthFoldSummary,
    body: () => renderPlanHealth(ui.plan, currentPlanHealth()) },
  { key: 'artifacts', id: 'plan-artifacts', numeral: 'IIA', title: 'The evidence',
    summary: artifactsFoldSummary,
    body: () => renderArtifacts(ui.plan, ui.artifacts) },
  { key: 'scenarios', id: 'plan-scenarios', numeral: 'IIB', title: 'The simulations',
    summary: scenariosFoldSummary,
    body: () => renderScenarios(ui.plan, { ...ui.scenarios, savedSimulations: ui.savedSimulations }, ui.assumptions) },
  { key: 'branches', id: 'plan-branches', numeral: 'IIC', title: 'The what-ifs',
    summary: branchesFoldSummary,
    body: () => renderBranches(ui.plan, ui.branches, ui.assumptions) },
  { key: 'withdrawals', id: 'plan-withdrawals', numeral: 'IID', title: 'The withdrawals',
    summary: () => '4% rule vs guardrails vs buckets',
    body: () => renderWithdrawals(ui.plan, ui.withdrawals, ui.assumptions) },
  { key: 'timeline', id: 'plan-timeline', numeral: 'IIE', title: 'The timeline',
    summary: timelineFoldSummary,
    body: () => renderTimeline(ui.plan, ui.timeline) },
  { key: 'contributions', id: 'plan-contributions', numeral: 'IIF', title: 'The contributions',
    summary: contributionsFoldSummary,
    body: () => renderContributions(ui.plan, ui.contributions) },
  { key: 'decisions', id: 'plan-decisions', numeral: 'III', title: 'The decisions',
    summary: decisionsFoldSummary,
    body: () => renderDecisions(ui.plan, ui.decisions) },
];

function renderFold(fold) {
  const open = ui.openFolds.has(fold.key);
  return html`
    <details class="plan-fold" data-plan-fold="${fold.key}" data-plan-section="${fold.key}" ${open ? 'open' : ''}>
      <summary>
        <span class="plan-fold-numeral">${fold.numeral}</span>
        <span class="plan-fold-title">${fold.title}</span>
        <span class="plan-fold-summary">${esc(foldSummaryText(fold))}</span>
        <span class="plan-fold-caret" aria-hidden="true">&rsaquo;</span>
      </summary>
      <div class="plan-fold-body" id="${fold.id}">${raw(fold.body())}</div>
    </details>
  `;
}

function foldSummaryText(fold) {
  try {
    return String(fold.summary() || '');
  } catch {
    return '';
  }
}

function seedOpenFolds(params = {}) {
  ui.openFolds = new Set();
  const section = String(params.section || '').trim().toLowerCase();
  if (section) ui.openFolds.add(section);
  if (String(params.artifact || '').trim()) ui.openFolds.add('artifacts');
  if (String(params.focus || params.recommendation || '').trim()) ui.openFolds.add('scenarios');
  if (String(params.saved || '').trim()) ui.openFolds.add('scenarios');
}

function openFold(key) {
  if (!FOLDS.some(fold => fold.key === key)) return;
  ui.openFolds.add(key);
  const details = document.querySelector(`details[data-plan-fold="${key}"]`);
  if (details) details.open = true;
}

// Targeted rerenders replace fold bodies without touching the summary rows;
// recompute the rows so closed folds never show stale counts.
function refreshFoldSummaries() {
  FOLDS.forEach(fold => {
    const el = document.querySelector(`details[data-plan-fold="${fold.key}"] .plan-fold-summary`);
    if (el) el.textContent = foldSummaryText(fold);
  });
}

function assumptionsFoldSummary() {
  const settings = ui.plan?.settings && typeof ui.plan.settings === 'object' ? ui.plan.settings : {};
  const set = PLAN_ASSUMPTION_FIELDS.filter(field => settings[field.key] != null && settings[field.key] !== '').length;
  return `${set} of ${PLAN_ASSUMPTION_FIELDS.length} set`;
}

function healthFoldSummary() {
  const health = currentPlanHealth();
  const count = Array.isArray(health.signals) ? health.signals.length : 0;
  return count ? `${health.label} · ${count} signal${count === 1 ? '' : 's'}` : (health.label || 'Ready');
}

function artifactsFoldSummary() {
  const count = Array.isArray(ui.plan?.artifacts) ? ui.plan.artifacts.length : 0;
  return count ? `${count} artifact${count === 1 ? '' : 's'} on file` : 'Nothing filed yet';
}

function scenariosFoldSummary() {
  const count = Array.isArray(ui.savedSimulations.payload?.simulations)
    ? ui.savedSimulations.payload.simulations.length
    : 0;
  return count ? `Run a comparison · ${count} saved` : 'Run a comparison';
}

function branchesFoldSummary() {
  const count = Array.isArray(ui.branches.branchTemplates?.templates)
    ? ui.branches.branchTemplates.templates.length
    : 0;
  return count ? `${count} life-event template${count === 1 ? '' : 's'}` : 'Life-event templates';
}

function timelineFoldSummary() {
  const retirement = ui.timeline.timeline?.retirement || {};
  const events = Array.isArray(ui.timeline.timeline?.events) ? ui.timeline.timeline.events.length : 0;
  const parts = [];
  const age = Number(retirement.target_retirement_age);
  const year = Number(retirement.target_retirement_year);
  if (Number.isFinite(age) && age > 0) parts.push(`Retire at ${age}`);
  else if (Number.isFinite(year) && year > 0) parts.push(`Retire in ${year}`);
  if (events) parts.push(`${events} event${events === 1 ? '' : 's'}`);
  return parts.length ? parts.join(' · ') : 'Retirement timing and major events';
}

function contributionsFoldSummary() {
  const count = Array.isArray(ui.contributions.contributionRules?.rules)
    ? ui.contributions.contributionRules.rules.length
    : 0;
  return count ? `${count} account rule${count === 1 ? '' : 's'}` : 'Account priorities and targets';
}

function decisionsFoldSummary() {
  const decisions = Array.isArray(ui.plan?.decisions) ? ui.plan.decisions : [];
  if (!decisions.length) return 'Nothing recorded yet';
  const measured = decisions.filter(item => item && item.outcome_captured).length;
  return `${decisions.length} recorded · ${measured} measured`;
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
  refreshFoldSummaries();
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
  refreshFoldSummaries();
}

function rerenderScenarios() {
  const root = $('#plan-scenarios');
  if (!root || !ui.plan) return;
  root.innerHTML = renderScenarios(ui.plan, { ...ui.scenarios, savedSimulations: ui.savedSimulations }, ui.assumptions);
  refreshFoldSummaries();
}

function rerenderBranches() {
  const root = $('#plan-branches');
  if (!root || !ui.plan) return;
  root.innerHTML = renderBranches(ui.plan, ui.branches, ui.assumptions);
  refreshFoldSummaries();
}

function rerenderWithdrawals() {
  const root = $('#plan-withdrawals');
  if (!root || !ui.plan) return;
  root.innerHTML = renderWithdrawals(ui.plan, ui.withdrawals, ui.assumptions);
}

function rerenderTimelineWorkspace() {
  const root = $('#plan-timeline');
  if (!root || !ui.plan) return;
  root.innerHTML = renderTimeline(ui.plan, ui.timeline);
  refreshFoldSummaries();
}

function rerenderContributionsWorkspace() {
  const root = $('#plan-contributions');
  if (!root || !ui.plan) return;
  root.innerHTML = renderContributions(ui.plan, ui.contributions);
  refreshFoldSummaries();
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
        <a class="link-editorial" href="#plan?id=${id}&amp;section=assumptions">Plan assumptions</a>
        <a class="link-editorial" href="#plan?id=${id}&amp;section=timeline">Timeline events</a>
        <a class="link-editorial" href="#plan?id=${id}&amp;section=contributions">Contribution rules</a>
        <a class="link-editorial" href="#plan?id=${id}&amp;section=scenarios">Run a simulation</a>
        <a class="link-editorial" href="#copilot?intent=review_plan_assumptions&amp;plan=${id}">Review with Copilot</a>
        <a class="link-editorial" href="#copilot?intent=explain_scenario_diff&amp;plan=${id}">Explain simulation</a>
        <a class="link-editorial" href="#plan?id=${id}&amp;section=artifacts">Plan evidence</a>
        <a class="link-editorial" href="#plan?id=${id}&amp;section=branches">What-if templates</a>
        <a class="link-editorial" href="#plan?id=${id}&amp;section=withdrawals">Withdrawal comparison</a>
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
      <p class="look-closer-note">Advanced tools remain available for deeper planning work.</p>
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

  // Manual toggle instead of the native <details> click behavior: fold state
  // must live in ui.openFolds so full rerenders preserve what the reader opened.
  delegate(page, 'click', '.plan-fold > summary', (event, el) => {
    event.preventDefault();
    const details = el.closest('details.plan-fold');
    const key = String(details?.dataset.planFold || '');
    if (!key) return;
    if (ui.openFolds.has(key)) {
      ui.openFolds.delete(key);
      details.open = false;
    } else {
      ui.openFolds.add(key);
      details.open = true;
    }
  });

  delegate(page, 'change', '#plan-select', async (_, el) => {
    const id = el.value;
    if (!id || id === ui.selectedId) return;
    ui.selectedId = id;
    ui.section = '';
    ui.openFolds = new Set();
    ui.previewEvent = null;
    ui.plan = null;
    ui.assumptions = { busy: false, assumptionSets: null, draft: {}, dirty: false, saving: false, error: null };
    ui.health = { busy: false, recommendations: [], error: null };
    ui.trajectoryPreview = { busy: false, result: null, planId: '' };
    ui.artifacts = { focusedArtifactId: '', focusedArtifact: null, busy: false, error: null };
    ui.scenarios = { draft: {}, dirty: false, busy: false, saveBusy: false, result: null, explanation: null, lastPayload: null, error: null, focusedRecommendationId: '' };
    ui.branches = { busy: false, saveBusy: false, branchTemplates: null, selectedTemplateId: '', draft: {}, dirty: false, result: null, explanation: null, lastPayload: null, error: null };
    ui.savedSimulations = { busy: false, payload: null, error: null, focusedComparison: null, rerun: null, focusedSimulationId: '' };
    ui.withdrawals = { busy: false, selectedStrategies: ['four_percent_rule', 'dynamic_guardrails', 'bucket_strategy'], draft: {}, dirty: false, result: null, error: null };
    ui.timeline = { busy: false, timeline: null, draft: {}, dirty: false, editing: false, saving: false, error: null };
    ui.contributions = { busy: false, contributionRules: null, draft: {}, dirty: false, editing: false, saving: false, error: null };
    rerenderBody();
    await loadPlan(id);
    await loadAssumptionSets(id);
    await loadPlanHealth(id);
    await loadFocusedArtifact(id, '');
    await loadBranchTemplates(id);
    await loadSavedSimulations(id);
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
  // 'input' stages without re-rendering: replacing the DOM mid-keystroke
  // destroys the focused field and silently drops the rest of the digits.
  delegate(page, 'input', '[data-scenario-field]', (_, el) => stageScenarioEdit(el, { rerender: false }));
  delegate(page, 'click', '[data-scenario-action="run"]', () => runScenarioDiff());
  delegate(page, 'click', '[data-scenario-action="save-simulation"]', () => saveScenarioSimulation());
  delegate(page, 'click', '[data-scenario-action="save-decision"]', () => saveScenarioDecisionNote());

  delegate(page, 'change', '[data-branch-field]', (_, el) => stageBranchEdit(el));
  delegate(page, 'input', '[data-branch-field]', (_, el) => stageBranchEdit(el, { rerender: false }));
  delegate(page, 'click', '[data-branch-action="run"]', () => runScenarioBranch());
  delegate(page, 'click', '[data-branch-action="save-simulation"]', () => saveBranchSimulation());
  delegate(page, 'click', '[data-branch-action="save-decision"]', () => saveBranchDecisionNote());
  delegate(page, 'click', '[data-saved-simulation-action="decision"]', (_, el) => attachSavedSimulationDecision(el));
  delegate(page, 'click', '[data-saved-simulation-action="compare"]', (_, el) => compareSavedSimulationCurrent(el));
  delegate(page, 'click', '[data-saved-simulation-action="rerun"]', (_, el) => rerunSavedSimulation(el));

  delegate(page, 'change', '[data-withdrawal-field]', (_, el) => stageWithdrawalEdit(el));
  delegate(page, 'change', '[data-withdrawal-strategy]', (_, el) => toggleWithdrawalStrategy(el));
  delegate(page, 'click', '[data-withdrawal-action="run"]', () => runWithdrawalComparison());
  delegate(page, 'click', '[data-withdrawal-action="save-decision"]', () => saveWithdrawalDecisionNote());

  delegate(page, 'change', '[data-timeline-field]', (_, el) => stageTimelineEdit(el));
  delegate(page, 'click', '[data-timeline-action="edit"]', () => openTimelineEditor());
  delegate(page, 'click', '[data-timeline-action="cancel"]', () => resetTimelineEditor());
  delegate(page, 'click', '[data-timeline-action="save"]', () => saveTimeline());
  delegate(page, 'click', '[data-timeline-action="remove-event"]', (_, el) => removeTimelineEvent(el));

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
    await loadFocusedArtifact(created.id, '');
    await loadBranchTemplates(created.id);
    await loadSavedSimulations(created.id);
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

function stageScenarioEdit(el, { rerender = true } = {}) {
  const field = String(el.dataset.scenarioField || '').trim();
  if (!field) return;
  ui.scenarios.draft = {
    ...(ui.scenarios.draft || {}),
    [field]: el.value,
  };
  ui.scenarios.dirty = true;
  ui.scenarios.error = null;
  if (rerender) rerenderScenarios();
}

function stageBranchEdit(el, { rerender = true } = {}) {
  const field = String(el.dataset.branchField || '').trim();
  if (!field) return;
  if (field === 'template_id') {
    ui.branches.selectedTemplateId = el.value;
    ui.branches.draft = {};
    ui.branches.result = null;
    ui.branches.dirty = false;
    ui.branches.error = null;
    rerenderBranches();
    return;
  }
  ui.branches.draft = {
    ...(ui.branches.draft || {}),
    [field]: el.value,
  };
  ui.branches.dirty = true;
  ui.branches.error = null;
  if (rerender) rerenderBranches();
}

function stageWithdrawalEdit(el) {
  const field = String(el.dataset.withdrawalField || '').trim();
  if (!field) return;
  const value = el.type === 'checkbox' ? Boolean(el.checked) : el.value;
  ui.withdrawals.draft = {
    ...(ui.withdrawals.draft || {}),
    [field]: value,
  };
  ui.withdrawals.dirty = true;
  ui.withdrawals.error = null;
  rerenderWithdrawals();
}

function toggleWithdrawalStrategy(el) {
  const strategy = String(el.dataset.withdrawalStrategy || '').trim();
  if (!strategy) return;
  const selected = new Set(ui.withdrawals.selectedStrategies || []);
  if (el.checked) selected.add(strategy);
  else selected.delete(strategy);
  ui.withdrawals.selectedStrategies = [...selected];
  ui.withdrawals.dirty = true;
  ui.withdrawals.error = null;
  rerenderWithdrawals();
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
    const result = await api.planScenarioDiff(ui.plan.id, payload);
    ui.scenarios.result = result;
    ui.scenarios.lastPayload = payload;
    ui.scenarios.explanation = { busy: true, payload: null, error: null };
    ui.scenarios.reviewLevel = { busy: true, payload: null, error: null };
    ui.scenarios.busy = false;
    ui.scenarios.dirty = false;
    rerenderScenarios();
    ui.scenarios.explanation = await explainSimulationResult('scenario_diff', payload, result);
    ui.scenarios.reviewLevel = await classifyWhatIfReviewLevel(
      'scenario_diff',
      payload,
      result,
      ui.scenarios.explanation?.payload || {},
    );
    rerenderScenarios();
  } catch (err) {
    ui.scenarios.busy = false;
    ui.scenarios.error = err.message;
    rerenderScenarios();
  }
}

async function runWithdrawalComparison() {
  if (!ui.plan || ui.withdrawals.busy) return;
  if ((ui.withdrawals.selectedStrategies || []).length < 2) {
    ui.withdrawals.error = 'Select at least two withdrawal strategies to compare.';
    rerenderWithdrawals();
    return;
  }
  const payload = buildWithdrawalComparePayload({
    ...(ui.withdrawals.draft || {}),
    selectedStrategies: ui.withdrawals.selectedStrategies || [],
    // Raw per-strategy results feed the drawdown trajectory chart.
    include_raw_results: true,
  });

  ui.withdrawals.busy = true;
  ui.withdrawals.error = null;
  rerenderWithdrawals();
  try {
    ui.withdrawals.result = await api.planWithdrawalStrategyCompare(ui.plan.id, payload);
    ui.withdrawals.busy = false;
    ui.withdrawals.dirty = false;
    rerenderWithdrawals();
  } catch (err) {
    ui.withdrawals.busy = false;
    ui.withdrawals.error = err.message;
    rerenderWithdrawals();
  }
}

async function saveWithdrawalDecisionNote() {
  if (!ui.plan || !ui.withdrawals.result || ui.withdrawals.busy) return;
  ui.withdrawals.busy = true;
  ui.withdrawals.error = null;
  rerenderWithdrawals();
  try {
    await api.appendDecision(ui.plan.id, {
      summary: 'Reviewed withdrawal strategy comparison',
      rationale: withdrawalDecisionRationale(ui.withdrawals.result),
      status: 'proposed',
      action_payload: {
        plan_id: ui.plan.id,
        source: 'withdrawal_strategy_comparison',
        recommended_strategy: ui.withdrawals.result?.explanation?.recommended_strategy || '',
        review_level: ui.withdrawals.result?.explanation?.review_level || {},
        compared_strategies: Array.isArray(ui.withdrawals.result?.strategies)
          ? ui.withdrawals.result.strategies
          : [],
        best_strategy_by_metric: ui.withdrawals.result?.best_strategy_by_metric || {},
      },
    });
    ui.plan = await api.plan(ui.plan.id);
    state.plan = ui.plan;
    ui.withdrawals.busy = false;
    rerenderAll();
    focusRequestedSection('withdrawals');
  } catch (err) {
    ui.withdrawals.busy = false;
    ui.withdrawals.error = err.message;
    rerenderWithdrawals();
  }
}

async function runScenarioBranch() {
  if (!ui.plan || ui.branches.busy) return;
  const template = selectedBranchTemplate();
  if (!template || !Object.keys(template).length) {
    ui.branches.error = 'Choose a branch template before running a preview.';
    rerenderBranches();
    return;
  }
  const payload = buildScenarioBranchPayload(template, ui.branches.draft || {});
  if (!payload.branch_events.length && !Object.keys(payload.compare_settings || {}).length) {
    ui.branches.error = 'The selected branch template needs at least one event or setting change.';
    rerenderBranches();
    return;
  }

  ui.branches.busy = true;
  ui.branches.error = null;
  rerenderBranches();
  try {
    const result = await api.planScenarioBranch(ui.plan.id, payload);
    ui.branches.result = result;
    ui.branches.lastPayload = payload;
    ui.branches.explanation = { busy: true, payload: null, error: null };
    ui.branches.reviewLevel = { busy: true, payload: null, error: null };
    ui.branches.busy = false;
    ui.branches.dirty = false;
    rerenderBranches();
    ui.branches.explanation = await explainSimulationResult('scenario_branch', payload, result);
    ui.branches.reviewLevel = await classifyWhatIfReviewLevel(
      'scenario_branch',
      payload,
      result,
      ui.branches.explanation?.payload || {},
    );
    rerenderBranches();
  } catch (err) {
    ui.branches.busy = false;
    ui.branches.error = err.message;
    rerenderBranches();
  }
}

async function explainSimulationResult(source, inputPayload, resultPayload) {
  try {
    return {
      busy: false,
      payload: await api.explainPlanSimulation(ui.plan.id, {
        source,
        input_payload: inputPayload,
        result_payload: resultPayload,
      }),
      error: null,
    };
  } catch (err) {
    return { busy: false, payload: null, error: err.message };
  }
}

async function classifyWhatIfReviewLevel(source, inputPayload, resultPayload, explanationPayload = {}) {
  try {
    return {
      busy: false,
      payload: await api.planWhatIfReviewLevel(ui.plan.id, {
        source,
        input_payload: inputPayload,
        result_payload: resultPayload,
        explanation_payload: explanationPayload,
      }),
      error: null,
    };
  } catch (err) {
    return { busy: false, payload: null, error: err.message };
  }
}

async function saveScenarioSimulation() {
  if (!ui.plan || !ui.scenarios.result || ui.scenarios.saveBusy) return;
  ui.scenarios.saveBusy = true;
  ui.scenarios.error = null;
  rerenderScenarios();
  try {
    await api.savePlanSimulation(ui.plan.id, {
      title: 'Simulation comparison',
      source: 'scenario_diff',
      summary: scenarioDecisionRationale(ui.scenarios.result),
      input_payload: ui.scenarios.lastPayload || {},
      result_payload: ui.scenarios.result,
    });
    await loadSavedSimulations(ui.plan.id);
    ui.scenarios.saveBusy = false;
    rerenderScenarios();
  } catch (err) {
    ui.scenarios.saveBusy = false;
    ui.scenarios.error = err.message;
    rerenderScenarios();
  }
}

async function saveBranchDecisionNote() {
  if (!ui.plan || !ui.branches.result || ui.branches.busy) return;
  ui.branches.busy = true;
  ui.branches.error = null;
  rerenderBranches();
  try {
    await api.appendDecision(ui.plan.id, {
      summary: `Reviewed what-if simulation: ${ui.branches.result.branch_name || 'What-if simulation'}`,
      rationale: branchDecisionRationale(ui.branches.result),
      status: 'proposed',
    });
    ui.plan = await api.plan(ui.plan.id);
    state.plan = ui.plan;
    ui.branches.busy = false;
    rerenderAll();
    focusRequestedSection('branches');
  } catch (err) {
    ui.branches.busy = false;
    ui.branches.error = err.message;
    rerenderBranches();
  }
}

async function saveBranchSimulation() {
  if (!ui.plan || !ui.branches.result || ui.branches.saveBusy) return;
  ui.branches.saveBusy = true;
  ui.branches.error = null;
  rerenderBranches();
  try {
    await api.savePlanSimulation(ui.plan.id, {
      title: ui.branches.result.branch_name || 'What-if simulation',
      source: 'scenario_branch',
      summary: branchDecisionRationale(ui.branches.result),
      input_payload: ui.branches.lastPayload || {},
      result_payload: ui.branches.result,
    });
    await loadSavedSimulations(ui.plan.id);
    ui.branches.saveBusy = false;
    rerenderScenarios();
    rerenderBranches();
  } catch (err) {
    ui.branches.saveBusy = false;
    ui.branches.error = err.message;
    rerenderBranches();
  }
}

async function attachSavedSimulationDecision(el) {
  if (!ui.plan) return;
  const savedSimulationId = String(el.dataset.savedSimulationId || '').trim();
  if (!savedSimulationId) return;
  ui.savedSimulations.busy = true;
  rerenderScenarios();
  try {
    await api.attachPlanSavedSimulationDecision(ui.plan.id, savedSimulationId, {
      status: 'proposed',
    });
    ui.plan = await api.plan(ui.plan.id);
    state.plan = ui.plan;
    await loadSavedSimulations(ui.plan.id);
    ui.savedSimulations.busy = false;
    rerenderAll();
    focusRequestedSection('scenarios');
  } catch (err) {
    ui.savedSimulations = { ...ui.savedSimulations, busy: false, error: err.message };
    rerenderScenarios();
  }
}

async function compareSavedSimulationCurrent(el) {
  if (!ui.plan) return;
  const savedSimulationId = String(el.dataset.savedSimulationId || '').trim();
  if (!savedSimulationId) return;
  await compareSavedSimulationCurrentById(savedSimulationId);
}

async function compareSavedSimulationCurrentById(savedSimulationId, { render = true } = {}) {
  if (!ui.plan) return;
  ui.savedSimulations = {
    ...ui.savedSimulations,
    busy: true,
    error: null,
    focusedSimulationId: savedSimulationId,
    focusedComparison: { busy: true, saved_simulation_id: savedSimulationId },
  };
  if (render) rerenderScenarios();
  try {
    const comparison = await api.comparePlanSavedSimulationCurrent(ui.plan.id, savedSimulationId);
    ui.savedSimulations = {
      ...ui.savedSimulations,
      busy: false,
      focusedSimulationId: savedSimulationId,
      focusedComparison: comparison,
      error: null,
    };
    if (render) rerenderScenarios();
  } catch (err) {
    ui.savedSimulations = {
      ...ui.savedSimulations,
      busy: false,
      focusedSimulationId: savedSimulationId,
      focusedComparison: null,
      error: err.message,
    };
    if (render) rerenderScenarios();
  }
}

async function rerunSavedSimulation(el) {
  if (!ui.plan) return;
  const savedSimulationId = String(el.dataset.savedSimulationId || '').trim();
  if (!savedSimulationId) return;
  ui.savedSimulations = {
    ...ui.savedSimulations,
    busy: true,
    error: null,
    rerun: { busy: true, saved_simulation_id: savedSimulationId },
  };
  rerenderScenarios();
  try {
    const result = await api.rerunPlanSavedSimulation(ui.plan.id, savedSimulationId, {
      save_result: true,
    });
    ui.savedSimulations = {
      ...ui.savedSimulations,
      busy: false,
      rerun: result,
      error: null,
    };
    await loadSavedSimulations(ui.plan.id);
    rerenderScenarios();
  } catch (err) {
    ui.savedSimulations = {
      ...ui.savedSimulations,
      busy: false,
      rerun: null,
      error: err.message,
    };
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
      summary: 'Reviewed simulation',
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
    setPlanTimelineEvents(ui.timeline.timeline?.events || []);
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

// Forecast freely, then return to reality: any saved event can be removed,
// and the fans redraw without it on the same rerender.
async function removeTimelineEvent(el) {
  if (!ui.plan || ui.timeline.saving) return;
  const eventId = String(el.dataset.eventId || '').trim();
  const timeline = ui.timeline.timeline || {};
  const events = Array.isArray(timeline.events) ? timeline.events : [];
  if (!eventId || !events.some(event => String(event?.id || '') === eventId)) return;
  ui.timeline.saving = true;
  ui.timeline.error = null;
  rerenderTimelineWorkspace();
  try {
    ui.timeline.timeline = await api.updatePlanTimeline(ui.plan.id, {
      events: events.filter(event => String(event?.id || '') !== eventId),
      retirement: timeline.retirement || {},
    });
    setPlanTimelineEvents(ui.timeline.timeline?.events || []);
    ui.timeline.saving = false;
    rerenderTimelineWorkspace();
    rerenderTrajectoryPreview();
    rerenderScenarios();
    rerenderBranches();
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
  if (!baseline) return 'Simulation comparison reviewed in v2 Plan.';
  const future = Number(baseline.delta_future_value_usd);
  const real = Number(baseline.delta_real_value_usd);
  const parts = ['Simulation comparison reviewed in v2 Plan.'];
  if (Number.isFinite(future)) parts.push(`Future-value delta: ${future}.`);
  if (Number.isFinite(real)) parts.push(`Real-value delta: ${real}.`);
  return parts.join(' ');
}

function branchDecisionRationale(result = {}) {
  const baseline = Array.isArray(result.scenario_deltas)
    ? result.scenario_deltas.find(row => String(row?.label || '') === 'baseline') || result.scenario_deltas[0]
    : null;
  const parts = [`What-if simulation reviewed in v2 Plan (${result.branch_name || 'What-if simulation'}).`];
  if (result.branch_template_name) parts.push(`Template: ${result.branch_template_name}.`);
  if (baseline) {
    const future = Number(baseline.delta_future_value_usd);
    const real = Number(baseline.delta_real_value_usd);
    if (Number.isFinite(future)) parts.push(`Future-value delta: ${future}.`);
    if (Number.isFinite(real)) parts.push(`Real-value delta: ${real}.`);
  }
  return parts.join(' ');
}

function withdrawalDecisionRationale(result = {}) {
  const best = result.best_strategy_by_metric || {};
  const parts = ['Withdrawal strategy comparison reviewed in v2 Plan.'];
  if (best.future_value) parts.push(`Best future value: ${best.future_value}.`);
  if (best.real_value) parts.push(`Best real value: ${best.real_value}.`);
  if (best.monte_carlo_p50) parts.push(`Best Monte Carlo p50: ${best.monte_carlo_p50}.`);
  if (Array.isArray(result.warnings) && result.warnings.length) {
    parts.push(`Warnings: ${result.warnings.slice(0, 2).join('; ')}.`);
  }
  return parts.join(' ');
}

function parsePreviewEvent(params = {}) {
  const label = String(params.pv_label || '').trim();
  const date = String(params.pv_date || '').trim();
  if (!label || !/^\d{4}/.test(date)) return null;
  const amount = Number(params.pv_amount);
  const impact = String(params.pv_impact || '').trim();
  return {
    label,
    event_type: String(params.pv_type || 'milestone').trim() || 'milestone',
    impact_type: impact || null,
    amount_usd: Number.isFinite(amount) ? amount : 0,
    recurring_frequency: String(params.pv_freq || 'one_time').trim() || 'one_time',
    start_year_offset: Math.max(0, Number(date.slice(0, 4)) - new Date().getFullYear()),
    duration_months: null,
    account_id: null,
    notes: 'From the life-plans interview — simulation preview only; nothing saved.',
  };
}

function previewBranchTemplate(event) {
  return {
    id: '__life_preview__',
    ephemeral: true,
    name: `Preview: ${event.label}`,
    description: 'From the life-plans interview. Runs as a simulation only — nothing lands on the plan timeline.',
    branch_name: `Preview: ${event.label}`,
    compare_settings: {},
    branch_events: [event],
  };
}

function selectedBranchTemplate() {
  const payload = ui.branches.branchTemplates || {};
  const templates = Array.isArray(payload.templates) ? payload.templates : [];
  const selectedId = String(ui.branches.selectedTemplateId || payload.default_template_id || '').trim();
  return templates.find(template => String(template?.id || '').trim() === selectedId) || templates[0] || {};
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
  openFold(requested);
  const target = document.querySelector(`[data-plan-section="${requested}"]`);
  if (!target) return;
  // Instant, not smooth: long smooth scrolls stall on busy pages.
  target.scrollIntoView({ block: 'start' });
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
