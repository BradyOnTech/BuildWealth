import test from 'node:test';
import assert from 'node:assert/strict';
import { normalizeAllocationRows, humanizeAllocationKey } from '../views/portfolio/composition.js';

test('normalizeAllocationRows merges case-duplicate keys and humanizes labels', () => {
  const rows = normalizeAllocationRows([
    { key: 'Cash', value: 39000, allocation: 7.3 },
    { key: 'cash', value: 2011, allocation: 0.4 },
    { key: 'real_estate', value: 420000, allocation: 78.1 },
    { key: 'fixed_income', value: 7697, allocation: 1.4 },
  ]);

  assert.equal(rows.length, 3);
  const cash = rows.find(row => row.key === 'Cash');
  assert.equal(cash.value, 41011);
  assert.ok(Math.abs(cash.allocation - 7.7) < 1e-9);
  assert.ok(rows.some(row => row.key === 'Real Estate'));
  assert.ok(rows.some(row => row.key === 'Fixed Income'));
});

test('humanizeAllocationKey preserves short acronyms', () => {
  assert.equal(humanizeAllocationKey('US'), 'US');
  assert.equal(humanizeAllocationKey('global_ex_us'), 'Global Ex Us');
  assert.equal(humanizeAllocationKey(''), '—');
});
