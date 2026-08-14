// Profile · readiness derivation (pure).
//
// Five steps — Household → Money in & out → Debt & goals → Taxes → Guardrails —
// derived from the server's profile_readiness. This is the *data* half of what
// used to be the embedded setup rail; the rendering half now lives in needs.js
// as a compact band, because the rail pushed the page's real navigation ~1700px
// below the fold to say what a meter can say in one line.
//
// Nothing here reads or writes the network, so the whole readiness model stays
// testable without a DOM.

import { getSuggestion } from './suggestions.js';

const STEP_DEFS = [
  { id: 'household',  title: 'Household',      sectionKeys: ['household'] },
  { id: 'money',      title: 'Money in & out', sectionKeys: ['income', 'expenses'] },
  { id: 'debt-goals', title: 'Debt & goals',   sectionKeys: ['debt', 'goals'] },
  { id: 'taxes',      title: 'Taxes',          sectionKeys: ['tax_profile'] },
  { id: 'guardrails', title: 'Guardrails',     sectionKeys: ['investment_policy'] },
];

// readiness section key → the profile tab that edits it.
export const SECTION_TABS = {
  household: 'household',
  income:    'income',
  expenses:  'expenses',
  debt:      'debt',
  goals:     'goals',
  tax_profile: 'taxes',
  investment_policy: 'investing',
  physical_assets: 'assets',
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

// Inference candidates that belong to a step rather than only to Inbox.
const STEP_CANDIDATE_MATCHERS = {
  household:    c => patchKind(c) === 'household_members',
  money:        c => patchKind(c) === 'income_items' || patchKind(c) === 'expense_items',
  'debt-goals': c => patchKind(c) === 'debt_items' || patchKind(c) === 'goal_items',
  taxes:        c => targetField(c).startsWith('tax_profile.'),
  guardrails:   c => targetField(c).startsWith('investment_policy.'),
};

export function deriveSetupSteps(readiness) {
  const sections = Array.isArray(readiness?.sections) ? readiness.sections
    : Array.isArray(readiness) ? readiness : [];
  const byKey = new Map(sections.map(s => [s.key, s]));
  let currentAssigned = false;
  return STEP_DEFS.map(def => {
    // Attention and missing both count as incomplete — the goal is to get every
    // section to a confident "complete".
    const complete = def.sectionKeys.every(key => byKey.get(key)?.status === 'complete');
    const current = !complete && !currentAssigned;
    if (current) currentAssigned = true;
    return { ...def, status: complete ? 'complete' : 'incomplete', current };
  });
}

// Section rows straight off the payload, tolerant of a readiness object that
// carries only a status (several callers send no sections at all).
export function readinessSections(onboarding) {
  const sections = onboarding?.profile_readiness?.sections;
  return Array.isArray(sections) ? sections : [];
}

export function readinessCount(onboarding) {
  const sections = readinessSections(onboarding);
  const complete = sections.filter(s => s.status === 'complete').length;
  return { complete, total: sections.length };
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

/* ─────────────  Path helpers  ───────────── */

export function readPath(obj, path) {
  return path.split('.').reduce(
    (node, key) => (node && typeof node === 'object' ? node[key] : undefined),
    obj || {},
  );
}

export function writePath(obj, path, value) {
  const keys = path.split('.');
  let node = obj;
  for (let i = 0; i < keys.length - 1; i++) {
    if (!node[keys[i]] || typeof node[keys[i]] !== 'object') node[keys[i]] = {};
    node = node[keys[i]];
  }
  node[keys[keys.length - 1]] = value;
}

function isBlank(value) {
  if (value == null || value === '') return true;
  if (typeof value === 'object' && !Array.isArray(value)) return !Object.keys(value).length;
  return false;
}

function patchKind(candidate) {
  return String(candidate?.metadata?.profile_patch_kind || '').trim();
}

function targetField(candidate) {
  return String(candidate?.target_field || '').trim();
}
