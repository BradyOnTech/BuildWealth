// Profile · "Needs you" band.
//
// Replaces the embedded setup rail. The rail rendered a whole section editor
// above the tab strip — which pushed the page's only navigation ~1700px down,
// and on mobile reduced to a single sentence telling you the editor was
// somewhere below. This says the same thing in three rows and keeps every
// action the rail owned: accepting suggested estimates, declaring debt-free or
// not-ready-for-goals, applying an inference candidate, and document capture.
//
// At most three rows. A gap list longer than that is a backlog, not a prompt.
//
// Overview is the hub, sections are workbenches. The full band belongs on
// Overview, where "what should I do next" is the question the page exists to
// answer. On a section you have already answered it — you are mid-form — so the
// band collapses to one line, and it never names the section you are standing
// in. (Before this split, opening Income greeted you with "Add what comes in
// each month" above the income form.)

import { api } from '../../lib/api.js';
import { html, raw, esc } from '../../lib/dom.js';
import { ensureShape, persist, render as renderProfile } from '../profile.js';
import { renderDocumentCapture } from './document_capture.js';
import {
  deriveSetupSteps,
  filterStepCandidates,
  stepEstimates,
  readinessSections,
  SECTION_TABS,
  readPath,
  writePath,
} from './readiness.js';

const MAX_ROWS = 3;

// What each gap unlocks. Production named the gap but never said why it
// mattered, which makes every gap look equally skippable.
const UNLOCKS = {
  household: 'Unlocks dependent-aware tax and goal logic.',
  income:    'Unlocks surplus, savings rate, and every tax estimate.',
  expenses:  'Unlocks accurate runway and category insight.',
  debt:      'Unlocks payoff ordering in the plan.',
  goals:     'Unlocks plan trajectory and saving recommendations.',
  tax_profile: 'Unlocks tax-aware suggestions and Roth-conversion math.',
  investment_policy: 'Unlocks investment-fit checks against your own limits.',
  physical_assets: 'Unlocks net worth beyond accounts, and property as plan funding.',
};

const SECTION_LABELS = {
  household: 'household',
  income: 'income',
  expenses: 'expenses',
  debt: 'debt',
  goals: 'goals',
  tax_profile: 'tax status',
  investment_policy: 'guardrails',
  physical_assets: 'property',
};

export const needsState = {
  dismissed: false,   // the all-complete line was clicked away
  docOpen: false,     // document capture expanded inside the band
  busy: false,
  error: null,
};

/* ─────────────  Derivation (pure)  ───────────── */

// Ranked gaps: incomplete sections in readiness order, capped. Each carries the
// section it edits so a row can link straight at the editor.
export function deriveNeeds(ui) {
  const sections = readinessSections(ui.onboarding)
    .filter(s => s.status !== 'complete')
    // A key with no tab has no editor to send anyone to, and its raw snake_case
    // name would surface as button text. Drop it rather than ship a dead end.
    .filter(s => Boolean(SECTION_TABS[s.key]))
    // Never prompt for the section currently open — that gap is being worked.
    .filter(s => SECTION_TABS[s.key] !== ui.section);
  return sections.slice(0, MAX_ROWS).map(section => ({
    key: section.key,
    tab: SECTION_TABS[section.key],
    label: SECTION_LABELS[section.key] || humanKey(section.key),
    detail: section.detail || '',
    unlocks: UNLOCKS[section.key] || '',
    attention: section.status === 'attention',
  }));
}

function humanKey(key) {
  return String(key).replace(/_/g, ' ');
}

/* ─────────────  Render  ───────────── */

export function renderNeedsBand(ui) {
  const sections = readinessSections(ui.onboarding);
  if (!sections.length) return '';

  const needs = deriveNeeds(ui);
  const remaining = countRemaining(ui, sections);

  // On a workbench, one line. Silent when the only thing left is what you are
  // already doing.
  if (ui.section !== 'overview') {
    return needs.length ? renderNeedsLine(needs[0], remaining) : '';
  }

  if (!needs.length) return completeLine();
  const steps = deriveSetupSteps(ui.onboarding?.profile_readiness);
  const activeStep = steps.find(step => step.current);
  const estimates = activeStep ? stepEstimates(ui, activeStep.id) : null;
  const found = activeStep ? filterStepCandidates(ui.candidates, activeStep.id).slice(0, 2) : [];

  return html`
    <aside class="profile-needs" aria-label="What your profile still needs">
      <div class="profile-needs-head">
        <p class="profile-needs-eyebrow">Needs you</p>
        <h2 class="profile-needs-title">
          ${remaining === 1 ? 'One thing is holding the plan back' : `${countWord(remaining)} things are holding the plan back`}
        </h2>
        ${remaining > needs.length ? html`
          <p class="profile-needs-more">
            Showing the ${countWord(needs.length).toLowerCase()} that unlock the most —
            the rest are marked in the section list.
          </p>
        ` : ''}
      </div>
      <ol class="profile-needs-list">
        ${raw(needs.map((need, index) => html`
          <li class="profile-needs-item ${need.attention ? 'attention' : ''}">
            <span class="profile-needs-copy">
              <strong>${esc(need.detail || `Add your ${need.label}.`)}</strong>
              ${need.unlocks ? html`<small>${need.unlocks}</small>` : ''}
            </span>
            <a class="${index === 0 ? 'btn btn-primary btn-sm' : 'link-editorial'}"
               href="#profile?section=${esc(need.tab)}" data-route data-needs-goto="${esc(need.tab)}">
              Open ${esc(need.label)}
            </a>
          </li>
        `).join(''))}
      </ol>

      ${found.length ? raw(renderFound(found)) : ''}

      <div class="profile-needs-alternates" role="group" aria-label="Other ways to fill this in">
        <button type="button" class="chip" data-needs-action="toggle-doc"
                aria-expanded="${needsState.docOpen ? 'true' : 'false'}">From a document</button>
        <a class="chip" href="#copilot?intent=profile-setup" data-route>Ask me in chat</a>
        ${estimates ? html`
          <button type="button" class="chip chip-accent" data-needs-use-estimates
                  data-needs-action="use-estimates" ${needsState.busy ? 'disabled' : ''}>
            ${needsState.busy ? 'Applying…' : 'Use the estimates'}
          </button>
        ` : ''}
        ${!(ui.profile?.debt_items || []).length && !ui.profile?.flags?.no_debt ? html`
          <button type="button" class="chip" data-needs-action="mark-no-debt" ${needsState.busy ? 'disabled' : ''}>I have no debt</button>
        ` : ''}
        ${!(ui.profile?.goal_items || []).length && !ui.profile?.flags?.no_goals ? html`
          <button type="button" class="chip" data-needs-action="defer-goals" ${needsState.busy ? 'disabled' : ''}>I’m not ready to set a goal</button>
        ` : ''}
      </div>

      ${needsState.docOpen ? raw(renderDocumentCapture()) : ''}
      ${needsState.error ? html`<p class="inline-warning">${esc(needsState.error)}</p>` : ''}
    </aside>
  `;
}

// Remaining gaps excluding the one being edited, so the count and the row list
// agree with each other.
function countRemaining(ui, sections) {
  return sections.filter(s =>
    s.status !== 'complete'
    && SECTION_TABS[s.key]
    && SECTION_TABS[s.key] !== ui.section).length;
}

function renderNeedsLine(next, remaining) {
  return html`
    <aside class="profile-needs-line" aria-label="What your profile still needs">
      <span class="profile-mark profile-mark-attention" aria-hidden="true">!</span>
      <span class="profile-needs-line-text">
        ${remaining > 1
          ? html`<strong>${remaining} other sections still need you.</strong>`
          : html`<strong>One other section still needs you.</strong>`}
        ${next.unlocks ? html`<span class="profile-needs-line-next">Next: ${esc(next.label)} — ${next.unlocks.replace(/^Unlocks /, 'unlocks ')}</span>` : ''}
      </span>
      <a class="link-editorial" href="#profile?section=${esc(next.tab)}" data-route data-needs-goto="${esc(next.tab)}">
        Open ${esc(next.label)}
      </a>
    </aside>
  `;
}

function renderFound(found) {
  return html`
    <div class="profile-needs-found">
      <p class="profile-needs-found-title">BuildWealth found this</p>
      <ul class="profile-needs-found-list">
        ${raw(found.map(c => html`
          <li class="profile-needs-found-item">
            <span>${esc(c.headline || c.title || 'A suggested profile update')}</span>
            <button type="button" class="btn btn-quiet profile-needs-apply" data-needs-action="apply-candidate"
                    data-candidate-id="${esc(c.id || '')}" ${needsState.busy ? 'disabled' : ''}>
              Apply
            </button>
          </li>
        `).join(''))}
      </ul>
    </div>
  `;
}

function completeLine() {
  if (needsState.dismissed) return '';
  return html`
    <aside class="profile-needs profile-needs-complete">
      <button type="button" class="profile-needs-done" data-needs-action="dismiss">
        Core profile ready — optional details can improve future advice, and everything stays editable.
      </button>
    </aside>
  `;
}

function countWord(n) {
  return ['Zero', 'One', 'Two', 'Three'][n] || String(n);
}

/* ─────────────  Actions  ───────────── */

export async function onNeedsAction(ui, action, dataset = {}) {
  if (action === 'dismiss') {
    needsState.dismissed = true;
    renderProfile();
    return;
  }
  if (action === 'toggle-doc') {
    needsState.docOpen = !needsState.docOpen;
    renderProfile();
    return;
  }
  if (action === 'use-estimates')   return applyStepEstimates(ui);
  if (action === 'apply-candidate') return applyCandidate(ui, dataset.candidateId);
  if (action === 'mark-no-debt')    return saveFlag(ui, 'no_debt', true);
  if (action === 'defer-goals')     return saveFlag(ui, 'no_goals', true);
}

async function saveFlag(ui, key, value) {
  if (needsState.busy || !ui.profile) return;
  const prior = { ...(ui.profile.flags || {}) };
  ui.profile.flags = { ...prior, [key]: value };
  needsState.busy = true;
  needsState.error = null;
  renderProfile();
  try {
    const saved = await persist();
    if (!saved) {
      ui.profile.flags = prior;
      needsState.error = 'Could not save that answer — nothing was changed.';
    }
  } finally {
    needsState.busy = false;
    renderProfile();
  }
}

async function applyStepEstimates(ui) {
  if (needsState.busy || !ui.profile) return;
  const step = deriveSetupSteps(ui.onboarding?.profile_readiness).find(s => s.current);
  const entries = stepEstimates(ui, step?.id);
  if (!entries || !entries.length) return;

  const prior = entries.map(({ path }) => ({ path, value: readPath(ui.profile, path) }));
  for (const { path, value } of entries) writePath(ui.profile, path, value);
  needsState.busy = true;
  needsState.error = null;
  renderProfile();
  try {
    const saved = await persist();
    if (!saved) {
      for (const { path, value } of prior) writePath(ui.profile, path, value);
      needsState.error = 'Could not save the estimates — nothing was changed.';
    }
  } finally {
    needsState.busy = false;
    renderProfile();
  }
}

async function applyCandidate(ui, id) {
  if (!id || needsState.busy) return;
  needsState.busy = true;
  needsState.error = null;
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
    needsState.error = err?.message || 'Could not apply the suggestion.';
  } finally {
    needsState.busy = false;
    renderProfile();
  }
}
