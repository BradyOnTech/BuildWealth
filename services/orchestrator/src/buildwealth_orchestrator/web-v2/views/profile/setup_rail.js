// Profile · Guided setup rail (Workstream C).
// Five steps — Household → Money in & out → Debt & goals → Taxes → Guardrails —
// rendered above the tab strip whenever readiness says something is missing.
// Each step reuses the existing section editors (tables / taxes / investing)
// and offers three inline alternates: photograph a document, hand off to
// Copilot, or accept the smart-defaults estimates in one tap.
//
// The rail is additive: tabs keep working, nothing is gated behind it, and
// "Skip for now" is module state only — no step is ever marked on the server
// by skipping past it.

import { api } from '../../lib/api.js';
import { html, raw, esc } from '../../lib/dom.js';
import { ensureShape, persist, render as renderProfile } from '../profile.js';
import { renderTable, sectionForKey } from './tables.js';
import { renderTaxes } from './taxes.js';
import { renderInvesting } from './investing.js';
import { renderDocumentCapture } from './document_capture.js';
import { getSuggestion } from './suggestions.js';

const STEP_DEFS = [
  { id: 'household',  title: 'Household',      sectionKeys: ['household'] },
  { id: 'money',      title: 'Money in & out', sectionKeys: ['income', 'expenses'] },
  { id: 'debt-goals', title: 'Debt & goals',   sectionKeys: ['debt', 'goals'] },
  { id: 'taxes',      title: 'Taxes',          sectionKeys: ['tax_profile'] },
  { id: 'guardrails', title: 'Guardrails',     sectionKeys: ['investment_policy'] },
];

// readiness section key → profile list key renderTable edits.
const SECTION_TABLE_KEYS = {
  household: 'household_members',
  income:    'income_items',
  expenses:  'expense_items',
  debt:      'debt_items',
  goals:     'goal_items',
};

// readiness section key → profile tab id, used to avoid rendering the same
// editor twice (duplicate input ids would make saves read the wrong copy).
const SECTION_TABS = {
  household: 'household',
  income:    'income',
  expenses:  'expenses',
  debt:      'debt',
  goals:     'goals',
  tax_profile: 'taxes',
  investment_policy: 'investing',
};

// "Use the estimates" per step: required blanks must all be covered by the
// suggestion map before the button shows; optional blanks ride along when a
// suggestion exists but never block the button (state rate is legitimately
// blank in no-income-tax states; the target mix is a starting point).
const STEP_ESTIMATE_FIELDS = {
  taxes: {
    required: [
      'tax_profile.marginal_tax_rate',
      'tax_profile.effective_tax_rate',
    ],
    optional: ['tax_profile.state_tax_rate'],
  },
  guardrails: {
    required: [
      'investment_policy.risk_tolerance',
      'investment_policy.tax_sensitivity',
      'investment_policy.simplicity_preference',
      'investment_policy.minimum_research_confidence',
      'investment_policy.minimum_cash_runway_months',
      'investment_policy.max_single_symbol_exposure_pct',
      'investment_policy.max_sector_exposure_pct',
    ],
    optional: ['investment_policy.target_asset_class_allocation_pct'],
  },
};

// Inference candidates that belong inside a step rather than only in Inbox.
const STEP_CANDIDATE_MATCHERS = {
  household:    c => patchKind(c) === 'household_members',
  money:        c => patchKind(c) === 'income_items' || patchKind(c) === 'expense_items',
  'debt-goals': c => patchKind(c) === 'debt_items' || patchKind(c) === 'goal_items',
  taxes:        c => targetField(c).startsWith('tax_profile.'),
  guardrails:   c => targetField(c).startsWith('investment_policy.'),
};

// Exported for tests: skip/dismiss/doc-capture toggles live here so the rail
// survives full view re-renders without writing anything to the server.
export const railState = {
  skipped: new Set(), // step ids the user stepped past this session
  dismissed: false,   // the all-complete line was clicked away
  docOpen: false,     // "From a document" card expanded inside the step
  busy: false,
  error: null,
};

/* ─────────────  Step derivation (pure)  ───────────── */

export function deriveSetupSteps(readiness) {
  const sections = Array.isArray(readiness?.sections) ? readiness.sections
    : Array.isArray(readiness) ? readiness : [];
  const byKey = new Map(sections.map(s => [s.key, s]));
  let currentAssigned = false;
  return STEP_DEFS.map(def => {
    // Attention and missing both count as incomplete — the rail's job is to
    // get every section to a confident "complete".
    const complete = def.sectionKeys.every(key => byKey.get(key)?.status === 'complete');
    const current = !complete && !currentAssigned;
    if (current) currentAssigned = true;
    return { ...def, status: complete ? 'complete' : 'incomplete', current };
  });
}

export function filterStepCandidates(candidates, stepId) {
  const match = STEP_CANDIDATE_MATCHERS[stepId];
  if (!match) return [];
  return (Array.isArray(candidates) ? candidates : []).filter(c => {
    try { return match(c); } catch { return false; }
  });
}

// The step's applicable estimates, or null when the button should not show.
export function stepEstimates(ui, stepId) {
  const fields = STEP_ESTIMATE_FIELDS[stepId];
  if (!fields) return null;
  const suggestions = ui.suggestions || {};
  const requiredBlanks = fields.required.filter(path => isBlank(readPath(ui.profile, path)));
  if (!requiredBlanks.length) return null;
  if (!requiredBlanks.every(path => getSuggestion(suggestions, path))) return null;
  const optionalBlanks = fields.optional.filter(path =>
    isBlank(readPath(ui.profile, path)) && getSuggestion(suggestions, path));
  return [...requiredBlanks, ...optionalBlanks]
    .map(path => ({ path, value: getSuggestion(suggestions, path).value }));
}

/* ─────────────  Render  ───────────── */

export function renderSetupRail(ui) {
  const readiness = ui.onboarding?.profile_readiness;
  const sections = Array.isArray(readiness?.sections) ? readiness.sections : [];
  if (!sections.length) return '';

  const steps = deriveSetupSteps(readiness);
  if (steps.every(s => s.status === 'complete')) return completeLine();

  const step = activeStep(steps);
  if (!step) return pausedLine(steps);

  const stepNumber = steps.findIndex(s => s.id === step.id) + 1;
  const byKey = new Map(sections.map(s => [s.key, s]));
  const detailItems = step.sectionKeys
    .map(key => byKey.get(key))
    .filter(s => s && s.status !== 'complete' && s.detail)
    .map(s => `<li>${esc(s.detail)}</li>`)
    .join('');
  const estimates = stepEstimates(ui, step.id);

  return html`
    <aside class="setup-rail" aria-label="Guided profile setup">
      <header class="setup-rail-head">
        <p class="setup-rail-eyebrow">§ Set up your picture · step ${stepNumber} of ${steps.length}</p>
        <div class="setup-rail-dots" role="img"
             aria-label="Step ${stepNumber} of ${steps.length}: ${step.title}">
          ${raw(steps.map(s => `
            <span class="setup-rail-dot ${s.status === 'complete' ? 'done' : ''} ${s.id === step.id ? 'current' : ''}"
                  title="${esc(s.title)}"></span>
          `).join(''))}
        </div>
      </header>
      <h2 class="setup-rail-title">${step.title}</h2>
      ${detailItems ? html`<ul class="setup-rail-details">${raw(detailItems)}</ul>` : ''}

      <div class="setup-rail-alternates" role="group" aria-label="Other ways to fill this in">
        <button type="button" class="chip" data-rail-action="toggle-doc"
                aria-expanded="${railState.docOpen ? 'true' : 'false'}">📷 From a document</button>
        <a class="chip" href="#copilot?intent=profile-setup" data-route>💬 Ask me in chat</a>
        ${estimates ? html`
          <button type="button" class="chip chip-accent" data-rail-use-estimates
                  data-rail-action="use-estimates" ${railState.busy ? 'disabled' : ''}>
            ${railState.busy ? 'Applying…' : 'Use the estimates'}
          </button>
        ` : ''}
      </div>

      ${railState.docOpen ? raw(renderDocumentCapture()) : ''}
      ${raw(foundList(ui, step))}
      ${railState.error ? html`<p class="inline-warning">${railState.error}</p>` : ''}

      <div class="setup-rail-editor">${raw(stepEditor(ui, step))}</div>

      <footer class="setup-rail-foot">
        <button type="button" class="link-quiet" data-rail-action="skip">Skip for now</button>
        <span class="setup-rail-foot-note">Nothing here is locked in — every tab below stays editable.</span>
      </footer>
    </aside>
  `;
}

function completeLine() {
  if (railState.dismissed) return '';
  return html`
    <aside class="setup-rail setup-rail-complete">
      <button type="button" class="setup-rail-done" data-rail-action="dismiss">
        Setup complete — everything below stays editable.
      </button>
    </aside>
  `;
}

// Every remaining step was skipped this session: collapse instead of looping
// the user back through steps they just stepped past.
function pausedLine(steps) {
  const remaining = steps.filter(s => s.status !== 'complete').length;
  return html`
    <aside class="setup-rail setup-rail-complete">
      <button type="button" class="setup-rail-done" data-rail-action="resume">
        Setup paused — ${remaining} step${remaining === 1 ? '' : 's'} left whenever you're ready. Resume
      </button>
    </aside>
  `;
}

function stepEditor(ui, step) {
  // The rail sits above the tab strip; if the user is already on this step's
  // tab, rendering the editor twice would duplicate input ids and make saves
  // read the wrong copy. Point at the one below instead.
  if (step.sectionKeys.some(key => SECTION_TABS[key] === ui.section)) {
    return `<p class="setup-rail-note">You're on this step's tab — the editor below is the same one.</p>`;
  }
  if (step.id === 'taxes')      return String(renderTaxes(ui));
  if (step.id === 'guardrails') return String(renderInvesting(ui));
  return step.sectionKeys
    .map(key => String(renderTable(ui, sectionForKey(SECTION_TABLE_KEYS[key]))))
    .join('');
}

function foundList(ui, step) {
  const matches = filterStepCandidates(ui.candidates, step.id);
  if (!matches.length) return '';
  const rows = matches.slice(0, 4).map(c => `
    <li class="setup-rail-found-item">
      <span class="setup-rail-found-text">${esc(c.headline || c.title || 'A suggested profile update')}</span>
      <button type="button" class="btn btn-quiet" data-rail-action="apply-candidate"
              data-candidate-id="${esc(c.id || '')}" ${railState.busy ? 'disabled' : ''}>
        Apply
      </button>
    </li>
  `).join('');
  return `
    <aside class="setup-rail-found">
      <p class="setup-rail-found-title">BuildWealth found this</p>
      <ul class="setup-rail-found-list">${rows}</ul>
    </aside>
  `;
}

/* ─────────────  Actions  ───────────── */

export async function onRailAction(ui, action, dataset = {}) {
  if (action === 'dismiss') {
    railState.dismissed = true;
    renderProfile();
    return;
  }
  if (action === 'resume') {
    railState.skipped.clear();
    renderProfile();
    return;
  }
  if (action === 'toggle-doc') {
    railState.docOpen = !railState.docOpen;
    renderProfile();
    return;
  }
  if (action === 'skip') {
    const step = activeStep(deriveSetupSteps(ui.onboarding?.profile_readiness));
    if (step) railState.skipped.add(step.id);
    renderProfile();
    return;
  }
  if (action === 'use-estimates')   return applyStepEstimates(ui);
  if (action === 'apply-candidate') return applyCandidate(ui, dataset.candidateId);
}

async function applyStepEstimates(ui) {
  if (railState.busy || !ui.profile) return;
  const step = activeStep(deriveSetupSteps(ui.onboarding?.profile_readiness));
  const entries = stepEstimates(ui, step?.id);
  if (!entries || !entries.length) return;

  const prior = entries.map(({ path }) => ({ path, value: readPath(ui.profile, path) }));
  for (const { path, value } of entries) writePath(ui.profile, path, value);
  railState.busy = true;
  railState.error = null;
  renderProfile();
  try {
    const saved = await persist();
    if (!saved) {
      for (const { path, value } of prior) writePath(ui.profile, path, value);
      railState.error = 'Could not save the estimates — nothing was changed.';
    }
  } finally {
    railState.busy = false;
    renderProfile();
  }
}

async function applyCandidate(ui, id) {
  if (!id || railState.busy) return;
  railState.busy = true;
  railState.error = null;
  renderProfile();
  try {
    await api.applyContextCandidate(id);
    const [profile, candidates, onboarding] = await Promise.all([
      api.profile(),
      api.contextCandidates({ lifecycleState: 'proposed' }).catch(() => []),
      api.onboarding().catch(() => null),
    ]);
    ui.profile = ensureShape(profile);
    ui.candidates = Array.isArray(candidates) ? candidates : (candidates?.items || []);
    if (onboarding) ui.onboarding = onboarding;
  } catch (err) {
    railState.error = err?.message || 'Could not apply the suggestion.';
  } finally {
    railState.busy = false;
    renderProfile();
  }
}

/* ─────────────  Helpers  ───────────── */

function activeStep(steps) {
  const eligible = steps.filter(s => s.status !== 'complete');
  return eligible.find(s => !railState.skipped.has(s.id)) || null;
}

function patchKind(candidate) {
  return String(candidate?.metadata?.profile_patch_kind || '').trim();
}

function targetField(candidate) {
  return String(candidate?.target_field || '').trim();
}

function isBlank(value) {
  if (value == null || value === '') return true;
  if (typeof value === 'object' && !Array.isArray(value)) return !Object.keys(value).length;
  return false;
}

function readPath(obj, path) {
  return path.split('.').reduce(
    (node, key) => (node && typeof node === 'object' ? node[key] : undefined),
    obj || {},
  );
}

function writePath(obj, path, value) {
  const keys = path.split('.');
  let node = obj;
  for (let i = 0; i < keys.length - 1; i++) {
    if (!node[keys[i]] || typeof node[keys[i]] !== 'object') node[keys[i]] = {};
    node = node[keys[i]];
  }
  node[keys[keys.length - 1]] = value;
}
