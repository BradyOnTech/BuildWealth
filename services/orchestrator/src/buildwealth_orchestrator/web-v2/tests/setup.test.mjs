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
  buildFoundationProfile,
  buildFutureProfile,
  buildSetupPortfolioBody,
  deriveSetupJourney,
  renderSetup,
} = await import('../views/setup.js');

function onboardingWith(statuses = {}, snapshotStatus = 'incomplete') {
  return {
    steps: [{ id: 'snapshot', status: snapshotStatus, detail: 'Snapshot evidence.' }],
    profile_readiness: {
      status: statuses.profile || 'incomplete',
      next_gap_title: statuses.nextGap || 'Income profile',
      sections: [
        ['household', 'Household'],
        ['income', 'Income'],
        ['expenses', 'Expenses'],
        ['debt', 'Debt'],
        ['goals', 'Goals'],
      ].map(([key, title]) => ({
        key,
        title,
        status: statuses[key] || 'incomplete',
        detail: `${title} detail.`,
      })),
    },
  };
}

const progressAt = (currentStep, extra = {}) => ({
  started: true,
  needs_setup: true,
  status: 'active',
  current_step: currentStep,
  completed_steps: [],
  skipped_steps: [],
  ...extra,
});

test('deriveSetupJourney keeps journey progress separate from financial evidence', () => {
  const journey = deriveSetupJourney({
    progress: progressAt('foundation', { skipped_steps: ['portfolio'] }),
    onboarding: onboardingWith({
      household: 'complete',
      income: 'complete',
      expenses: 'complete',
      debt: 'complete',
      goals: 'complete',
    }, 'complete'),
    today: { net_worth_usd: 120000 },
    health: { net_worth_usd: 120000, gross_monthly_income_usd: 8000 },
  });

  const byId = new Map(journey.map(step => [step.id, step]));
  assert.equal(byId.get('foundation').current, true);
  assert.equal(byId.get('foundation').evidenceReady, true);
  assert.equal(byId.get('portfolio').evidenceReady, true);
  assert.equal(byId.get('portfolio').skipped, true);
  assert.equal(byId.get('portfolio').completed, false);
  assert.equal(byId.get('first_picture').evidenceReady, true);
});

test('welcome renders the trust contract and an always-visible exit', () => {
  const markup = String(renderSetup({
    progress: progressAt('welcome'),
    onboarding: onboardingWith(),
  }));

  assert.match(markup, /Private by design/);
  assert.match(markup, /Confirmation over interrogation/);
  assert.match(markup, /Evidence before confidence/);
  assert.match(markup, /href="#today"/);
  assert.match(markup, /data-setup-next="foundation"/);
});

test('foundation offers direct editors and does not gate the journey', () => {
  const markup = String(renderSetup({
    progress: progressAt('foundation'),
    onboarding: onboardingWith({ income: 'complete' }),
  }));

  assert.match(markup, /href="#profile\?section=household"/);
  assert.match(markup, /href="#profile\?section=expenses"/);
  assert.match(markup, /data-setup-foundation-form/);
  assert.match(markup, /Your name/);
  assert.doesNotMatch(markup, /Annual household income/);
  assert.match(markup, /Leave this for later/);
  assert.match(markup, /data-setup-skip="portfolio"/);
  assert.doesNotMatch(markup, /data-setup-next="portfolio"/);
});

test('foundation quick entry adds only missing evidence and preserves detailed records', () => {
  const existingIncome = { id: 'salary-1', label: 'Salary', monthly_amount_usd: 5000 };
  const result = buildFoundationProfile({
    household_members: [],
    income_items: [existingIncome],
    expense_items: [],
    debt_items: [],
    goal_items: [],
    physical_assets: [],
    flags: {},
    tax_profile: { filing_status: 'single' },
    investment_policy: { risk_tolerance: 'moderate' },
  }, {
    display_name: 'Taylor',
    monthly_expenses_usd: '4200',
    debt_balance_usd: '0',
  }, ['household', 'expenses', 'debt']);

  assert.deepEqual(result.income_items, [existingIncome]);
  assert.equal(result.household_members[0].display_name, 'Taylor');
  assert.equal(result.expense_items[0].monthly_amount_usd, 4200);
  assert.equal(result.flags.expenses_complete, true);
  assert.equal(result.flags.no_debt, true);
  assert.equal(result.tax_profile.filing_status, 'single');
  assert.equal(result.investment_policy.risk_tolerance, 'moderate');
});

test('quick portfolio and future inputs translate to existing canonical APIs', () => {
  assert.deepEqual(buildSetupPortfolioBody({
    kind: 'cash', account_name: 'Emergency fund', value_usd: '12500',
  }), {
    flow: 'cash', amount_usd: 12500,
    new_account: { name: 'Emergency fund', type: 'cash' },
  });
  assert.deepEqual(buildSetupPortfolioBody({
    kind: 'investment', account_name: 'Roth IRA', value_usd: '25000', symbol: 'vti',
  }), {
    flow: 'investment', symbol: 'VTI', value_usd: 25000,
    new_account: { name: 'Roth IRA', type: 'taxable' },
  });

  const result = buildFutureProfile({ flags: { no_goals: true }, goal_items: [] }, {
    goal_label: 'Work optionality', target_amount_usd: '50000', target_date: '',
  });
  assert.equal(result.goal_items[0].label, 'Work optionality');
  assert.equal(result.goal_items[0].target_amount_usd, 50000);
  assert.equal(result.goal_items[0].target_date, null);
  assert.equal(result.flags.no_goals, false);
});

test('ready foundation can continue without falsely finishing setup', () => {
  const complete = {
    household: 'complete', income: 'complete', expenses: 'complete', debt: 'complete',
  };
  const markup = String(renderSetup({
    progress: progressAt('foundation'),
    onboarding: onboardingWith(complete),
  }));

  assert.match(markup, /data-setup-next="portfolio"/);
  assert.match(markup, /data-setup-current="foundation"/);
  assert.doesNotMatch(markup, /Leave this for later/);
});

test('first picture labels incomplete evidence instead of manufacturing confidence', () => {
  const markup = String(renderSetup({
    progress: progressAt('first_picture'),
    onboarding: onboardingWith({ nextGap: 'Expense profile' }),
    today: { net_worth_usd: 0, profile_readiness: { status: 'incomplete', next_gap_title: 'Expense profile' } },
    health: { net_worth_usd: 0, gross_monthly_income_usd: 0 },
  }));

  assert.match(markup, /Not enough data/);
  assert.match(markup, /early baseline, not a finished plan/i);
  assert.match(markup, /Expense profile/);
  assert.match(markup, /data-setup-finish/);
});
