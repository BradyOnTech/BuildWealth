// Profile tables — inline row editing + composer redesign, pure-helper tests.
// DOM-free: exercises the section specs and the row_edit helpers directly.

import test from 'node:test';
import assert from 'node:assert/strict';
import { TABLE_SECTIONS, sectionForKey, composerFieldSplit } from '../views/profile/tables.js';
import {
  AMOUNT_FIELD_KEY,
  applyAmountUnit,
  buildRowDraft,
  convertAmount,
  fromMonthlyAmount,
  getAmountUnit,
  rebuildRow,
  sectionHasAmount,
  setAmountUnit,
  toMonthlyAmount,
} from '../views/profile/row_edit.js';

/* ─────────────  Section specs: primary fields  ───────────── */

const EXPECTED_PRIMARY = {
  household_members: ['display_name', 'relationship', 'birth_year'],
  income_items:      ['label', 'monthly_amount_usd'],
  expense_items:     ['label', 'monthly_amount_usd'],
  debt_items:        ['label', 'balance_usd'],
  goal_items:        ['label', 'target_amount_usd', 'target_date'],
  physical_assets:   ['label', 'current_value_usd', 'asset_subtype'],
  insurance_policies:['label', 'coverage_type', 'coverage_amount_usd'],
  benefit_items:     ['label', 'benefit_type', 'owner_member_id'],
};

test('every table section declares its primary composer fields', () => {
  assert.equal(TABLE_SECTIONS.length, Object.keys(EXPECTED_PRIMARY).length);
  for (const section of TABLE_SECTIONS) {
    assert.deepEqual(section.primary, EXPECTED_PRIMARY[section.key], section.key);
    for (const key of section.primary) {
      assert.ok(section.composer.some(f => f.key === key), `${section.key}: primary key ${key} missing from composer`);
    }
  }
});

test('composerFieldSplit separates primary from more-detail fields', () => {
  const income = sectionForKey('income_items');
  const { primary, more } = composerFieldSplit(income);
  assert.deepEqual(primary.map(f => f.key), ['label', 'monthly_amount_usd']);
  assert.deepEqual(more.map(f => f.key), [
    'source_type', 'owner_member_id', 'linked_asset_id', 'employer_name', 'variability',
    'is_pre_tax', 'annual_growth_rate', 'start_date', 'end_date',
  ]);
  // Every composer field lands in exactly one bucket.
  assert.equal(primary.length + more.length, income.composer.length);
});

/* ─────────────  Row-edit draft round-trips  ───────────── */

test('income: buildRowDraft/rebuildRow round-trip preserves semantics and id', () => {
  const income = sectionForKey('income_items');
  const item = {
    id: 'inc-1',
    label: 'Salary',
    monthly_amount_usd: 8000,
    source_type: 'salary',
    owner_member_id: null,
    linked_asset_id: null,
    employer_name: null,
    variability: 'fixed',
    is_pre_tax: true,
    annual_growth_rate: 0.03,
    start_date: '2024-01-01',
    end_date: null,
  };
  const draft = buildRowDraft(income, item);
  assert.equal(draft.annual_growth_rate, 3);      // ratio → percent for the input
  assert.equal(draft.monthly_amount_usd, 8000);   // amounts stay monthly in the draft
  assert.equal(draft.is_pre_tax, true);
  assert.equal(draft.end_date, '');               // null → empty input
  const rebuilt = rebuildRow(income, draft, item.id);
  assert.deepEqual(rebuilt, item);                // id preserved, values identical
});

test('rebuildRow overrides the fresh id build() generates', () => {
  const income = sectionForKey('income_items');
  const rebuilt = rebuildRow(income, { label: 'Side gig', monthly_amount_usd: 500 }, 'keep-me');
  assert.equal(rebuilt.id, 'keep-me');
});

test('household: round-trip recomputes dependent from relationship', () => {
  const household = sectionForKey('household_members');
  const item = {
    id: 'm-1',
    display_name: 'Brady',
    relationship: 'self',
    birth_year: 1988,
    retirement_age: 60,
    dependent: false,
    notes: '',
  };
  const rebuilt = rebuildRow(household, buildRowDraft(household, item), item.id);
  assert.deepEqual(rebuilt, item);

  const kid = { ...item, id: 'm-2', display_name: 'Riley', relationship: 'child', retirement_age: null, dependent: true };
  const rebuiltKid = rebuildRow(household, buildRowDraft(household, kid), kid.id);
  assert.deepEqual(rebuiltKid, kid);
});

test('debt: APR percent input round-trips through the stored decimal fraction', () => {
  const debt = sectionForKey('debt_items');
  const item = {
    id: 'd-1',
    label: 'Card',
    balance_usd: 4200,
    debt_type: 'other',
    linked_asset_id: null,
    original_principal_usd: null,
    term_months: null,
    opened_at: null,
    maturity_date: null,
    interest_rate: 0.2299,
    minimum_payment_usd: 85,
    payoff_strategy: 'avalanche',
    custom_monthly_payment_usd: null,
  };
  const draft = buildRowDraft(debt, item);
  assert.equal(draft.interest_rate, 22.99);
  assert.deepEqual(rebuildRow(debt, draft, item.id), item);
});

/* ─────────────  Annual ↔ monthly conversion  ───────────── */

test('annual amounts convert to monthly, rounded to 2dp', () => {
  assert.equal(toMonthlyAmount(96000, 'annual'), 8000);
  assert.equal(toMonthlyAmount(100000, 'annual'), 8333.33);
  assert.equal(toMonthlyAmount(8000, 'monthly'), 8000);
  assert.equal(toMonthlyAmount('', 'annual'), '');          // empty passes through to build()
  assert.equal(toMonthlyAmount('abc', 'annual'), 'abc');    // non-numeric passes through
  assert.equal(fromMonthlyAmount(8000, 'annual'), 96000);
  assert.equal(fromMonthlyAmount(8000, 'monthly'), 8000);
  assert.equal(convertAmount(96000, 'annual', 'monthly'), 8000);
  assert.equal(convertAmount(8000, 'monthly', 'annual'), 96000);
  assert.equal(convertAmount(1234, 'monthly', 'monthly'), 1234);
});

test('applyAmountUnit converts only the amount field, on a copy', () => {
  const income = sectionForKey('income_items');
  const draft = { label: 'Salary', [AMOUNT_FIELD_KEY]: 96000 };
  const converted = applyAmountUnit(income, draft, 'annual');
  assert.equal(converted[AMOUNT_FIELD_KEY], 8000);
  assert.equal(converted.label, 'Salary');
  assert.equal(draft[AMOUNT_FIELD_KEY], 96000);             // original untouched

  const debt = sectionForKey('debt_items');
  assert.equal(sectionHasAmount(debt), false);
  const debtDraft = { label: 'Card', balance_usd: 1200 };
  assert.deepEqual(applyAmountUnit(debt, debtDraft, 'annual'), debtDraft);
});

test('amount unit is module state with a monthly default', () => {
  assert.equal(getAmountUnit(), 'monthly');
  setAmountUnit('annual');
  assert.equal(getAmountUnit(), 'annual');
  assert.equal(toMonthlyAmount(96000), 8000);               // default unit = remembered choice
  setAmountUnit('monthly');
  assert.equal(getAmountUnit(), 'monthly');
  setAmountUnit('bogus');
  assert.equal(getAmountUnit(), 'monthly');                 // invalid input falls back
});

test('annual entry produces a build()-valid income row at monthly scale', () => {
  const income = sectionForKey('income_items');
  const draft = { label: 'Salary', [AMOUNT_FIELD_KEY]: '96000', source_type: 'salary' };
  const row = rebuildRow(income, applyAmountUnit(income, draft, 'annual'), 'inc-9');
  assert.equal(row.monthly_amount_usd, 8000);
  assert.equal(row.id, 'inc-9');
  assert.equal(row.label, 'Salary');
});
