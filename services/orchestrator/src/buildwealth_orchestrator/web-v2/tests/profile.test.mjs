import test from 'node:test';
import assert from 'node:assert/strict';
import { renderOverview } from '../views/profile/overview.js';
import { TABLE_SECTIONS, sectionForKey, renderTable } from '../views/profile/tables.js';

test('overview: renders household snapshot from filled income and expense rows', () => {
  const ui = {
    profile: {
      household_members: [
        { id: 'm1', display_name: 'Alex', relationship: 'self', dependent: false },
        { id: 'm2', display_name: 'Jordan', relationship: 'partner', dependent: false },
        { id: 'm3', display_name: 'Riley', relationship: 'child', dependent: true },
      ],
      income_items: [
        { id: 'a', monthly_amount_usd: 9500, label: 'Salary', source_type: 'salary' },
        { id: 'b', monthly_amount_usd: 1000, label: 'Side',   source_type: 'business' },
      ],
      expense_items: [
        { id: 'x', monthly_amount_usd: 4200, category: 'rent', label: 'Rent' },
        { id: 'y', monthly_amount_usd:  800, category: 'food', label: 'Food' },
      ],
      debt_items: [{ id: 'd1', balance_usd: 12000 }],
      goal_items: [],
      tax_profile: { filing_status: 'single', marginal_tax_rate: 0.24 },
      flags: { no_goals: true },
      investment_policy: {},
    },
    candidates: [],
  };
  const markup = String(renderOverview(ui));
  // monthly income/expenses/surplus/debt should appear
  assert.match(markup, /\$10,500/);             // income total
  assert.match(markup, /2 adults, 1 dependent/);
  assert.match(markup, /\$5,000/);              // expense total
  assert.match(markup, /\$5,500/);              // surplus
  assert.match(markup, /\$12,000/);             // debt total
  assert.match(markup, /Not tracking yet/);     // goals flag honored
  assert.match(markup, /single/);               // filing status
  assert.match(markup, /24\.00%/);              // marginal rate
});

test('overview: empty profile shows em-dashes for unknown values', () => {
  const ui = { profile: { income_items: [], expense_items: [] }, candidates: [] };
  const markup = String(renderOverview(ui));
  assert.match(markup, /Monthly income/);
  // no formatted dollar value should appear when there are no items
  assert.doesNotMatch(markup, /\$\d/);
});

test('overview: surfaces pending context candidates in the Needs Review card', () => {
  const ui = {
    profile: { income_items: [], expense_items: [] },
    candidates: [
      { id: 'c1', headline: 'Confirm marginal tax rate', kind: 'tax_profile', detail: 'Plan uses 32%; profile says 24%.' },
    ],
  };
  const markup = String(renderOverview(ui));
  assert.match(markup, /Needs review/);
  assert.match(markup, /Confirm marginal tax rate/);
});

test('tables: defines all five editable sections', () => {
  const keys = TABLE_SECTIONS.map(s => s.key).sort();
  assert.deepEqual(keys, ['debt_items', 'expense_items', 'goal_items', 'income_items', 'physical_assets']);
});

test('tables: sectionForKey returns the right declarative spec', () => {
  const income = sectionForKey('income_items');
  assert.equal(income.title, 'Income');
  assert.equal(income.singular, 'income');
  assert.ok(income.columns.find(c => c.key === 'monthly_amount_usd'));
  assert.ok(income.composer.find(c => c.key === 'label'));
});

test('tables: income build() validates label and converts percent to decimal', () => {
  const income = sectionForKey('income_items');
  assert.throws(() => income.build({ label: '', monthly_amount_usd: 1000 }), /required/i);
  assert.throws(() => income.build({ label: 'X', monthly_amount_usd: -1 }), /0 or greater/i);
  const row = income.build({
    label: 'Salary',
    monthly_amount_usd: 9500,
    source_type: 'salary',
    is_pre_tax: true,
    annual_growth_rate: '3',
  });
  assert.equal(row.label, 'Salary');
  assert.equal(row.monthly_amount_usd, 9500);
  assert.equal(row.is_pre_tax, true);
  // 3% entered → 0.03 stored, matching the on-disk schema.
  assert.equal(row.annual_growth_rate, 0.03);
  assert.match(String(row.id), /\S/);
});

test('tables: debt build() defaults strategy and stores rate as decimal fraction', () => {
  const debt = sectionForKey('debt_items');
  const row = debt.build({ label: 'Card', balance_usd: 5000, interest_rate: '21.99' });
  assert.equal(row.payoff_strategy, 'minimum');
  assert.equal(row.balance_usd, 5000);
  // 21.99% → 0.2199 (allow tiny float epsilon)
  assert.ok(Math.abs(row.interest_rate - 0.2199) < 1e-9);
});

test('tables: renderTable shows empty hint when there are no entries', () => {
  const ui = { profile: { income_items: [] } };
  const markup = String(renderTable(ui, sectionForKey('income_items')));
  assert.match(markup, /No income entries yet/);
  assert.match(markup, /Add income/);
});

test('tables: renderTable lists existing rows with formatted currency and pre-tax label', () => {
  const ui = {
    profile: {
      income_items: [
        { id: 'i1', label: 'Salary', monthly_amount_usd: 9500, source_type: 'salary', is_pre_tax: true },
      ],
    },
  };
  const markup = String(renderTable(ui, sectionForKey('income_items')));
  assert.match(markup, /Salary/);
  assert.match(markup, /\$9,500/);
  assert.match(markup, /Yes/);  // pre-tax → "Yes" in the human column
});

/* ─────────────  Life-plans interview  ───────────── */

test('life-plans interview: closed card invites and stays honest about state', async () => {
  const { renderLifeInterview } = await import('../views/profile/life_plans.js');
  const empty = String(renderLifeInterview({ profile: { goal_items: [] } }));
  assert.match(empty, /Sit for the interview/);
  assert.match(empty, /Nothing dated yet/);
  assert.match(empty, /nothing is saved until you say so/);

  const dated = String(renderLifeInterview({
    profile: { goal_items: [{ id: 'g1', label: 'House', target_date: '2028-06-01' }] },
  }));
  assert.match(dated, /1 dated goal on file/);
});

test('life-plans interview: profile view wires actions, fields, and drafts', async () => {
  const { readFileSync } = await import('node:fs');
  const { resolve } = await import('node:path');
  const profileSource = readFileSync(resolve(import.meta.dirname, '../views/profile.js'), 'utf8');
  assert.match(profileSource, /renderLifeInterview/);
  assert.match(profileSource, /data-interview-action/);
  assert.match(profileSource, /data-interview-field/);
  assert.match(profileSource, /data-draft-pick/);
  assert.match(profileSource, /data-draft-field/);

  const moduleSource = readFileSync(resolve(import.meta.dirname, '../views/profile/life_plans.js'), 'utf8');
  // Drafts come from the backend and are applied through the human gate.
  assert.match(moduleSource, /api\.lifeInterview/);
  assert.match(moduleSource, /api\.lifePlanDrafts/);
  assert.match(moduleSource, /persist\(\{ optimistic: false \}\)/);
  // Applied goals carry ids (GoalItem.id is required server-side) and a
  // failed save rolls the optimistic push back instead of claiming success.
  assert.match(moduleSource, /id: uid\(\)/);
  assert.match(moduleSource, /goal_items = goalsBefore/);
  // Timeline twins: per-draft opt-out, appended to the active plan after the
  // goals save, and a timeline failure never undoes the saved goals.
  assert.match(profileSource, /data-draft-timeline/);
  assert.match(moduleSource, /api\.planTimeline/);
  assert.match(moduleSource, /api\.updatePlanTimeline/);
  assert.match(moduleSource, /Goals saved, but the Plan timeline/);
  // "Not now" across the board can pause goal nudges honestly.
  assert.match(moduleSource, /no_goals: true/);
  // Covered questions default to "not now" instead of asking again.
  assert.match(moduleSource, /already_covered/);
});
