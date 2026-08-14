// Profile page chrome — the compact header's readiness meter and the grouped
// section rail's status vocabulary. This module had no coverage when it replaced
// the masthead and the 13-tab strip, which is how a broken aria idref and three
// permanently-stuck rail marks shipped green.

import test from 'node:test';
import assert from 'node:assert/strict';

const { renderHeader, renderRail, SECTION_GROUPS } = await import('../views/profile/shell.js');

// Mirrors views/profile.js SECTIONS. Routing validates ?section= against these
// ids, so the rail must not invent any.
const SECTIONS = [
  { id: 'overview',     label: 'Overview',     kind: 'overview' },
  { id: 'household',    label: 'Household',    kind: 'table', tableKey: 'household_members' },
  { id: 'income',       label: 'Income',       kind: 'table', tableKey: 'income_items' },
  { id: 'benefits',     label: 'Benefits',     kind: 'table', tableKey: 'benefit_items' },
  { id: 'expenses',     label: 'Expenses',     kind: 'table', tableKey: 'expense_items' },
  { id: 'debt',         label: 'Debt',         kind: 'table', tableKey: 'debt_items' },
  { id: 'goals',        label: 'Goals',        kind: 'goals', tableKey: 'goal_items' },
  { id: 'taxes',        label: 'Taxes & status', kind: 'taxes' },
  { id: 'investing',    label: 'Investing',    kind: 'investing' },
  { id: 'assets',       label: 'Property & vehicles', kind: 'table', tableKey: 'physical_assets' },
  { id: 'insurance',    label: 'Insurance',    kind: 'table', tableKey: 'insurance_policies' },
  { id: 'estate',       label: 'Estate',       kind: 'estate' },
  { id: 'data-quality', label: 'Data quality', kind: 'data-quality' },
];

const sections = (statuses = {}) => [
  'household', 'income', 'expenses', 'debt', 'goals',
  'tax_profile', 'investment_policy', 'physical_assets',
].map(key => ({ key, status: statuses[key] || 'incomplete', detail: '' }));

const baseUi = (extra = {}) => ({
  section: 'overview',
  candidates: [],
  profile: { household_members: [], income_items: [], physical_assets: [] },
  onboarding: { profile_readiness: { status: 'partial', sections: sections() } },
  ...extra,
});

/* ─────────────  Header  ───────────── */

test('header meter reports the real section count and the next gap', () => {
  const markup = String(renderHeader(baseUi({
    onboarding: {
      profile_readiness: {
        status: 'partial',
        next_gap_title: 'Income profile',
        sections: sections({ household: 'complete', debt: 'complete' }),
      },
    },
  })));
  assert.match(markup, /2 of 8 sections/);
  assert.match(markup, /Next: Income profile/);
  assert.match(markup, /Resume setup/);
  // The meter must be driven by the count, not hardcoded.
  assert.match(markup, /width:25%/);
  // The arrow comes from .link-editorial::after; emitting one too would double it.
  assert.doesNotMatch(markup, /Resume setup <span aria-hidden="true">→/);
});

test('header survives a readiness payload with no sections at all', () => {
  // Several callers send only a status; a bare .sections.filter() here would
  // throw and take the whole page down.
  const markup = String(renderHeader(baseUi({
    onboarding: { profile_readiness: { status: 'partial', completion_percent: 40 } },
  })));
  assert.match(markup, /In progress/);
  assert.match(markup, /width:0%/);
  assert.doesNotMatch(markup, /NaN|undefined|Infinity/);

  const noOnboarding = String(renderHeader(baseUi({ onboarding: null })));
  assert.match(noOnboarding, /In progress/);
  assert.doesNotMatch(noOnboarding, /NaN|undefined/);
});

test('header reports a ready profile as ready, not as 100% of nothing', () => {
  const markup = String(renderHeader(baseUi({
    onboarding: { profile_readiness: { status: 'ready' } },
  })));
  assert.match(markup, /Ready/);
  assert.match(markup, /Core evidence ready/);
  assert.match(markup, /Review setup/);
});

test('header links pending candidates at the Inbox that resolves them', () => {
  const none = String(renderHeader(baseUi()));
  assert.match(none, /nothing pending review/);

  const some = String(renderHeader(baseUi({ candidates: [{ id: 'c1' }, { id: 'c2' }] })));
  assert.match(some, /2 to review/);
  assert.match(some, /href="#inbox"/);
});

/* ─────────────  Rail  ───────────── */

test('rail renders every section exactly once, grouped, with routable ids', () => {
  const markup = String(renderRail(baseUi(), SECTIONS));
  for (const section of SECTIONS) {
    assert.equal(
      (markup.match(new RegExp(`data-tab="${section.id}"`, 'g')) || []).length, 1,
      `${section.id} should appear exactly once in the rail`,
    );
    assert.match(markup, new RegExp(`href="#profile\\?section=${section.id.replace('-', '-')}"`));
  }
  // Grouping is what lets the list stay scannable past a dozen entries.
  for (const group of SECTION_GROUPS) assert.match(markup, new RegExp(group.label));
  // Every id the rail offers must be one routing accepts.
  const ids = [...markup.matchAll(/data-tab="([^"]+)"/g)].map(m => m[1]);
  const known = new Set(SECTIONS.map(s => s.id));
  for (const id of ids) assert.ok(known.has(id), `rail emitted unroutable section id "${id}"`);
});

test('rail marks follow server readiness, and "0" alone never reads as attention', () => {
  const markup = String(renderRail(baseUi({
    profile: { household_members: [{ id: 'h1' }], income_items: [], physical_assets: [] },
    onboarding: {
      profile_readiness: {
        status: 'partial',
        sections: sections({ household: 'complete', income: 'attention' }),
      },
    },
  }), SECTIONS));
  const markOf = id => {
    const row = markup.slice(markup.indexOf(`data-tab="${id}"`));
    return (row.match(/profile-mark-(\w+)/) || [])[1];
  };
  assert.equal(markOf('household'), 'complete');
  assert.equal(markOf('income'), 'attention');
  assert.equal(markOf('expenses'), 'todo');
  // Benefits has no readiness section and no rows: empty, but not a warning.
  assert.equal(markOf('benefits'), 'todo');
  assert.match(markup, /profile-rail-count zero/);
});

test('assets takes the server opinion instead of guessing from row count', () => {
  // physical_assets is the eighth readiness section. Reading it off row length
  // silently downgraded an explicit "attention" to a quiet empty dot.
  const markup = String(renderRail(baseUi({
    onboarding: {
      profile_readiness: { status: 'partial', sections: sections({ physical_assets: 'attention' }) },
    },
  }), SECTIONS));
  const row = markup.slice(markup.indexOf('data-tab="assets"'));
  assert.match(row, /profile-mark-attention/);
});

test('estate and data quality resolve from the profile, not a frozen default', () => {
  const complete = {
    will_status: 'complete', trust_status: 'complete',
    power_of_attorney_status: 'complete', healthcare_directive_status: 'complete',
  };
  const markFor = (ui, id) => {
    const markup = String(renderRail(ui, SECTIONS));
    return (markup.slice(markup.indexOf(`data-tab="${id}"`)).match(/profile-mark-(\w+)/) || [])[1];
  };

  assert.equal(markFor(baseUi({ profile: { estate_readiness: complete } }), 'estate'), 'complete');
  assert.equal(markFor(baseUi({ profile: { estate_readiness: { will_status: 'complete' } } }), 'estate'), 'attention');
  assert.equal(markFor(baseUi({ profile: {} }), 'estate'), 'todo');
  assert.equal(markFor(baseUi({ profile: { estate_readiness: { will_status: 'unknown' } } }), 'estate'), 'todo');

  assert.equal(markFor(baseUi(), 'data-quality'), 'complete');
  assert.equal(markFor(baseUi({ candidates: [{ id: 'c1' }] }), 'data-quality'), 'attention');
});

test('rail marks the active section for both pointer and assistive users', () => {
  const markup = String(renderRail(baseUi({ section: 'income' }), SECTIONS));
  const row = markup.slice(markup.indexOf('data-tab="income"') - 200, markup.indexOf('data-tab="income"') + 200);
  assert.match(row, /profile-rail-item active/);
  assert.match(row, /aria-current="page"/);
  assert.equal((markup.match(/aria-current="page"/g) || []).length, 1);
});
