// SETUP · profile patches.
// Turns the three quick-start forms into editable Profile records. These are
// pure builders: they never touch the network and never mutate the profile they
// are handed, so a failed save leaves the caller's copy intact.

export function missingFoundationKeys(onboarding = {}) {
  const sections = sectionMap(onboarding);
  return ['household', 'income', 'expenses', 'debt']
    .filter(key => sections.get(key)?.status !== 'complete');
}

export function sectionMap(onboarding) {
  const sections = Array.isArray(onboarding?.profile_readiness?.sections)
    ? onboarding.profile_readiness.sections
    : [];
  return new Map(sections.map(section => [section.key, section]));
}

export function buildFoundationProfile(profile = {}, fields = {}, missing = []) {
  const next = editableProfile(profile);
  const needs = new Set(missing);
  if (needs.has('household')) {
    const displayName = requiredText(fields.display_name, 'Enter the name you want BuildWealth to use.');
    next.household_members.push({
      id: uid(), display_name: displayName, relationship: 'self', birth_year: null,
      retirement_age: null, dependent: false, notes: '',
    });
  }
  if (needs.has('income')) {
    const annual = setupAmount(fields.annual_income_usd, 'Enter annual household income.');
    next.income_items.push({
      id: uid(), label: 'Household income', monthly_amount_usd: Math.round((annual / 12) * 100) / 100,
      source_type: 'setup_estimate', is_pre_tax: true, annual_growth_rate: null,
      start_date: null, end_date: null,
    });
  }
  if (needs.has('expenses')) {
    const monthly = setupAmount(fields.monthly_expenses_usd, 'Enter typical monthly spending.');
    next.expense_items.push({
      id: uid(), label: 'Representative household spending', monthly_amount_usd: monthly,
      category: 'general', is_fixed: false, inflation_rate: null, start_date: null, end_date: null,
    });
    next.flags.expenses_complete = true;
  }
  if (needs.has('debt')) {
    const balance = setupAmount(fields.debt_balance_usd, 'Enter a debt balance, or 0 if debt-free.');
    next.flags.no_debt = balance === 0;
    if (balance > 0) {
      next.debt_items.push({
        id: uid(), label: 'Current debt', balance_usd: balance, interest_rate: null,
        minimum_payment_usd: null, payoff_strategy: 'minimum', custom_monthly_payment_usd: null,
      });
    }
  }
  return next;
}

export function buildSetupPortfolioBody(fields = {}) {
  const kind = String(fields.kind || 'cash');
  const accountName = requiredText(fields.account_name, 'Enter a name for this account.');
  const value = setupAmount(fields.value_usd, 'Enter the current account value.');
  if (value <= 0) throw new Error('Current value must be greater than 0.');
  if (kind === 'investment') {
    const symbol = requiredText(fields.symbol, 'Enter the ticker symbol for the main investment.').toUpperCase();
    return {
      flow: 'investment', symbol, value_usd: value,
      new_account: { name: accountName, type: 'taxable' },
    };
  }
  return {
    flow: 'cash', amount_usd: value,
    new_account: { name: accountName, type: 'cash' },
  };
}

export function buildFutureProfile(profile = {}, fields = {}) {
  const next = editableProfile(profile);
  const label = requiredText(fields.goal_label, 'Describe what you are working toward.');
  const amount = setupAmount(fields.target_amount_usd, 'Enter a rough target amount.');
  next.goal_items.push({
    id: uid(), label, target_amount_usd: amount,
    target_date: String(fields.target_date || '').trim() || null,
    priority: 'medium', notes: 'Added during first-time Setup.',
  });
  next.flags.no_goals = false;
  return next;
}

function editableProfile(profile = {}) {
  const list = key => Array.isArray(profile?.[key]) ? profile[key].map(item => ({ ...item })) : [];
  return {
    household_members: list('household_members'),
    income_items: list('income_items'),
    expense_items: list('expense_items'),
    debt_items: list('debt_items'),
    goal_items: list('goal_items'),
    physical_assets: list('physical_assets'),
    tax_profile: { ...(profile?.tax_profile || {}) },
    investment_policy: { ...(profile?.investment_policy || {}) },
    flags: { ...(profile?.flags || {}) },
    notes: String(profile?.notes || ''),
    profile_metadata: { ...(profile?.profile_metadata || {}) },
  };
}

function requiredText(value, message) {
  const text = String(value || '').trim();
  if (!text) throw new Error(message);
  return text;
}

function setupAmount(value, message) {
  const text = String(value ?? '').trim();
  const amount = Number(text);
  if (!text || !Number.isFinite(amount) || amount < 0) throw new Error(message);
  return Math.round(amount * 100) / 100;
}

function uid() {
  if (typeof crypto !== 'undefined' && typeof crypto.randomUUID === 'function') return crypto.randomUUID();
  return `setup-${Math.random().toString(36).slice(2)}-${Date.now().toString(36)}`;
}
