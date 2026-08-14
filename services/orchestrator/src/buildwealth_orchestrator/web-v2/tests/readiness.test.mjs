// Profile readiness — step derivation, estimates gating, per-step
// inference-candidate filtering, and the "Needs you" band markup that replaced
// the embedded setup rail. Pure string assertions; no DOM.

import test from 'node:test';
import assert from 'node:assert/strict';

const storage = new Map();
globalThis.window = globalThis.window || {
  sessionStorage: {
    getItem: key => storage.get(key) || '',
    setItem: (key, value) => storage.set(key, String(value)),
    removeItem: key => storage.delete(key),
  },
};

const {
  deriveSetupSteps,
  filterStepCandidates,
  stepEstimates,
  readinessCount,
} = await import('../views/profile/readiness.js');

const {
  renderNeedsBand,
  deriveNeeds,
  needsState,
} = await import('../views/profile/needs.js');

function resetRail() {
  needsState.dismissed = false;
  needsState.docOpen = false;
  needsState.busy = false;
  needsState.error = null;
}

const readiness = (statuses = {}) => ({
  sections: [
    ['household', 'Household'],
    ['income', 'Income'],
    ['expenses', 'Expenses'],
    ['debt', 'Debt'],
    ['goals', 'Goals'],
    ['tax_profile', 'Tax profile'],
    ['investment_policy', 'Investment policy'],
    ['physical_assets', 'Physical assets'],
  ].map(([key, title]) => ({
    key,
    title,
    status: statuses[key] || 'incomplete',
    detail: statuses[`${key}_detail`] || '',
  })),
});

const emptyProfile = () => ({
  household_members: [],
  income_items: [],
  expense_items: [],
  debt_items: [],
  goal_items: [],
  physical_assets: [],
  tax_profile: {},
  flags: {},
});

const uiWith = (statuses = {}, extra = {}) => ({
  profile: emptyProfile(),
  onboarding: { profile_readiness: readiness(statuses) },
  suggestions: {},
  candidates: [],
  section: 'overview',
  ...extra,
});

const TAX_SUGGESTIONS = {
  'tax_profile.marginal_tax_rate': {
    field_path: 'tax_profile.marginal_tax_rate',
    value: 0.22, display: '22%', basis: 'computed',
    explanation: 'Estimated from your income and filing status.',
  },
  'tax_profile.effective_tax_rate': {
    field_path: 'tax_profile.effective_tax_rate',
    value: 0.15, display: '15%', basis: 'computed',
    explanation: 'Average federal rate across your income.',
  },
  'tax_profile.state_tax_rate': {
    field_path: 'tax_profile.state_tax_rate',
    value: 0.05, display: '5%', basis: 'typical',
    explanation: 'Flat approximation for your state.',
  },
};

/* ─────────────  deriveSetupSteps  ───────────── */

test('deriveSetupSteps: five steps in rail order, first incomplete is current', () => {
  const steps = deriveSetupSteps(readiness());
  assert.deepEqual(steps.map(s => s.id), ['household', 'money', 'debt-goals', 'taxes', 'guardrails']);
  assert.deepEqual(steps.map(s => s.title), ['Household', 'Money in & out', 'Debt & goals', 'Taxes', 'Guardrails']);
  assert.ok(steps.every(s => s.status === 'incomplete'));
  assert.deepEqual(steps.map(s => s.current), [true, false, false, false, false]);
});

test('deriveSetupSteps: a step is complete only when ALL its sections are complete', () => {
  const steps = deriveSetupSteps(readiness({
    household: 'complete',
    income: 'complete',
    expenses: 'attention', // attention counts as incomplete
  }));
  const byId = new Map(steps.map(s => [s.id, s]));
  assert.equal(byId.get('household').status, 'complete');
  assert.equal(byId.get('money').status, 'incomplete');
  assert.equal(byId.get('money').current, true);
  assert.equal(byId.get('household').current, false);
});

test('deriveSetupSteps: all complete yields no current step', () => {
  const steps = deriveSetupSteps(readiness({
    household: 'complete', income: 'complete', expenses: 'complete',
    debt: 'complete', goals: 'complete', tax_profile: 'complete',
    investment_policy: 'complete',
  }));
  assert.ok(steps.every(s => s.status === 'complete'));
  assert.ok(steps.every(s => !s.current));
});

test('deriveSetupSteps: missing readiness sections count as incomplete', () => {
  const steps = deriveSetupSteps({ sections: [{ key: 'household', status: 'complete' }] });
  assert.equal(steps[0].status, 'complete');
  assert.ok(steps.slice(1).every(s => s.status === 'incomplete'));
});

/* ─────────────  renderNeedsBand markup  ─────────────
   The band replaced the embedded setup rail. It keeps every action the rail
   owned (estimates, debt-free, defer-goals, apply-candidate, document capture)
   but renders at most three gaps and no section editor, so the page's own
   navigation stays above the fold. */

test('band names the gaps, says what each unlocks, and offers the alternates', () => {
  resetRail();
  const markup = String(renderNeedsBand(uiWith({
    household: 'complete',
    income_detail: 'Add the income streams BuildWealth should plan around.',
  })));
  assert.match(markup, /Needs you/);
  // Human detail sentence from readiness renders
  assert.match(markup, /Add the income streams BuildWealth should plan around\./);
  // Each gap states its consequence — the rail never did
  assert.match(markup, /Unlocks surplus, savings rate, and every tax estimate\./);
  // Alternates row
  assert.match(markup, /From a document/);
  assert.match(markup, /href="#copilot\?intent=profile-setup"/);
  assert.match(markup, /Ask me in chat/);
  // Money step has no estimate map — no Use-the-estimates button
  assert.doesNotMatch(markup, /data-needs-use-estimates/);
  // Rows link at the editor; the band never embeds one
  assert.match(markup, /href="#profile\?section=income"/);
  assert.doesNotMatch(markup, /data-table-add=/);
});

test('band caps at three gaps so a prompt never becomes a backlog', () => {
  resetRail();
  const ui = uiWith({});   // every section incomplete
  const needs = deriveNeeds(ui);
  assert.equal(needs.length, 3);
  const markup = String(renderNeedsBand(ui));
  // The heading reports the true remaining count — capping the list must not
  // understate the work — and the cap is stated rather than silent.
  assert.match(markup, /8 things are holding the plan back/);
  assert.match(markup, /Showing the three that unlock the most/);
  assert.equal((markup.match(/class="profile-needs-item/g) || []).length, 3);
});

test('band hides entirely when readiness has not arrived', () => {
  resetRail();
  assert.equal(String(renderNeedsBand(uiWith({}, { onboarding: null }))), '');
  assert.equal(String(renderNeedsBand(uiWith({}, { onboarding: { profile_readiness: {} } }))), '');
});

test('readinessCount tolerates a readiness payload carrying no sections', () => {
  assert.deepEqual(readinessCount({ profile_readiness: { status: 'partial' } }), { complete: 0, total: 0 });
  assert.deepEqual(readinessCount(null), { complete: 0, total: 0 });
  assert.deepEqual(readinessCount({ profile_readiness: readiness({ household: 'complete' }) }),
    { complete: 1, total: 8 });
});

test('taxes step: Use-the-estimates appears only when suggestions cover the blanks', () => {
  resetRail();
  const complete = {
    household: 'complete', income: 'complete', expenses: 'complete',
    debt: 'complete', goals: 'complete',
  };
  const without = String(renderNeedsBand(uiWith(complete)));
  assert.doesNotMatch(without, /data-needs-use-estimates/);

  const withSuggestions = String(renderNeedsBand(uiWith(complete, { suggestions: TAX_SUGGESTIONS })));
  assert.match(withSuggestions, /data-needs-use-estimates/);
  assert.match(withSuggestions, /Use the estimates/);
});

test('taxes step: filled rates mean nothing to estimate — no button', () => {
  resetRail();
  const ui = uiWith({
    household: 'complete', income: 'complete', expenses: 'complete',
    debt: 'complete', goals: 'complete',
  }, { suggestions: TAX_SUGGESTIONS });
  ui.profile.tax_profile = { marginal_tax_rate: 0.24, effective_tax_rate: 0.18 };
  assert.doesNotMatch(String(renderNeedsBand(ui)), /data-needs-use-estimates/);
  assert.equal(stepEstimates(ui, 'taxes'), null);
});

test('stepEstimates returns decimal values straight from the suggestion map', () => {
  resetRail();
  const ui = uiWith({}, { suggestions: TAX_SUGGESTIONS });
  const entries = stepEstimates(ui, 'taxes');
  assert.deepEqual(entries, [
    { path: 'tax_profile.marginal_tax_rate', value: 0.22 },
    { path: 'tax_profile.effective_tax_rate', value: 0.15 },
    { path: 'tax_profile.state_tax_rate', value: 0.05 },
  ]);
  assert.equal(stepEstimates(ui, 'money'), null, 'table steps have no estimate map');
});

test('debt and goals step offers honest not-applicable and not-yet answers', () => {
  resetRail();
  const markup = String(renderNeedsBand(uiWith({
    household: 'complete', income: 'complete', expenses: 'complete',
  })));
  assert.match(markup, /I have no debt/);
  assert.match(markup, /I’m not ready to set a goal/);
  assert.match(markup, /data-needs-action="mark-no-debt"/);
  assert.match(markup, /data-needs-action="defer-goals"/);
});

test('all core steps complete: readiness milestone stays honest about optional context', () => {
  resetRail();
  const done = {
    household: 'complete', income: 'complete', expenses: 'complete',
    debt: 'complete', goals: 'complete', tax_profile: 'complete',
    investment_policy: 'complete', physical_assets: 'complete',
  };
  const markup = String(renderNeedsBand(uiWith(done)));
  assert.match(markup, /Core profile ready/);
  assert.match(markup, /optional details can improve/i);
  assert.doesNotMatch(markup, /Setup complete/);
  assert.match(markup, /data-needs-action="dismiss"/);

  needsState.dismissed = true;
  assert.equal(String(renderNeedsBand(uiWith(done))), '');
});

/* ─────────────  Candidate filtering  ───────────── */

test('filterStepCandidates routes candidates to their matching step', () => {
  const income = { id: 'c1', metadata: { profile_patch_kind: 'income_items' }, headline: 'Salary from paystub' };
  const expense = { id: 'c2', metadata: { profile_patch_kind: 'expense_items' } };
  const household = { id: 'c3', metadata: { profile_patch_kind: 'household_members' } };
  const tax = { id: 'c4', target_field: 'tax_profile.marginal_tax_rate' };
  const policy = { id: 'c5', target_field: 'investment_policy.risk_tolerance' };
  const unrelated = { id: 'c6', target_field: 'timeline.retirement.target_retirement_age' };
  const all = [income, expense, household, tax, policy, unrelated];

  assert.deepEqual(filterStepCandidates(all, 'money').map(c => c.id), ['c1', 'c2']);
  assert.deepEqual(filterStepCandidates(all, 'household').map(c => c.id), ['c3']);
  assert.deepEqual(filterStepCandidates(all, 'taxes').map(c => c.id), ['c4']);
  assert.deepEqual(filterStepCandidates(all, 'guardrails').map(c => c.id), ['c5']);
  assert.deepEqual(filterStepCandidates(all, 'debt-goals'), []);
  assert.deepEqual(filterStepCandidates(null, 'money'), []);
  assert.deepEqual(filterStepCandidates(all, 'nonsense-step'), []);
});

test('matching candidates render inside the band as an apply list', () => {
  resetRail();
  const markup = String(renderNeedsBand(uiWith({ household: 'complete' }, {
    candidates: [
      { id: 'cand-9', metadata: { profile_patch_kind: 'income_items' }, headline: 'Salary $7,500/mo from your paystub' },
      { id: 'cand-x', target_field: 'tax_profile.marginal_tax_rate', headline: 'Marginal rate 22%' },
    ],
  })));
  assert.match(markup, /BuildWealth found this/);
  assert.match(markup, /Salary \$7,500\/mo from your paystub/);
  assert.match(markup, /data-candidate-id="cand-9"/);
  // The tax candidate belongs to the taxes step, not the money step.
  assert.doesNotMatch(markup, /data-candidate-id="cand-x"/);
});
