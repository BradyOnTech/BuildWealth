import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';

const storage = new Map();
globalThis.window = globalThis.window || {
  sessionStorage: {
    getItem: key => storage.get(key) || '',
    setItem: (key, value) => storage.set(key, String(value)),
    removeItem: key => storage.delete(key),
  },
};

const { resolveLedgerValue, renderStory } = await import('../views/plan/story.js');

const DEFAULTS = {
  marginal_tax_rate: { value: 0.22, source: 'profile' },
  inflation_rate: { value: 0.025, source: 'buildwealth_default' },
  withdrawal_strategy: { value: 'cashflow_only', source: 'buildwealth_default' },
};

const pct = v => `${(Math.abs(Number(v)) < 1 ? Number(v) * 100 : Number(v)).toFixed(1)}%`;

test('resolveLedgerValue prefers the plan value', () => {
  const row = resolveLedgerValue(0.24, 'marginal_tax_rate', DEFAULTS, pct);
  assert.deepEqual(row, { text: '24.0%', resolved: true, fromDefault: false });
});

test('resolveLedgerValue falls back to the resolved default with provenance', () => {
  const fromProfile = resolveLedgerValue(null, 'marginal_tax_rate', DEFAULTS, pct);
  assert.equal(fromProfile.text, '22.0% · from your profile');
  assert.equal(fromProfile.fromDefault, true);

  const engine = resolveLedgerValue(undefined, 'inflation_rate', DEFAULTS, pct);
  assert.equal(engine.text, '2.5% · BuildWealth default');
});

test('resolveLedgerValue says "not set" only when nothing is resolvable', () => {
  const row = resolveLedgerValue(null, 'years', DEFAULTS, v => String(v));
  assert.deepEqual(row, { text: 'not set', resolved: false, fromDefault: true });
});

test('the ledger never renders the phrase "app default"', () => {
  const markup = String(renderStory(
    { title: 'T', settings: {} },
    {},
    {},
    DEFAULTS,
  ));
  assert.doesNotMatch(markup, /app default/);
  assert.match(markup, /22\.0% · from your profile/);
  assert.match(markup, /cashflow only · BuildWealth default/);

  const source = readFileSync(resolve(import.meta.dirname, '../views/plan/story.js'), 'utf8');
  assert.doesNotMatch(source, /'app default'/);
});
