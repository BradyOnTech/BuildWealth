import test from 'node:test';
import assert from 'node:assert/strict';
import { targetsCard } from '../views/profile/investing.js';

test('target mix card renders classes, values, and the never-trades promise', () => {
  const markup = String(targetsCard({
    target_asset_class_allocation_pct: { equity: 70, fixed_income: 20, cash: 10 },
  }));

  assert.match(markup, /Target mix/);
  assert.match(markup, /Stocks & stock funds|Stocks &amp; stock funds/);
  assert.match(markup, /data-investing-target-class="equity"[^>]*value="70"/);
  assert.match(markup, /data-investing-target-class="fixed_income"[^>]*value="20"/);
  assert.match(markup, /guidance only, it never trades/);
  assert.doesNotMatch(markup, /Targets add to/); // 100% exactly: no nag
});

test('target mix card nags gently when totals stray from 100', () => {
  const markup = String(targetsCard({ target_asset_class_allocation_pct: { equity: 70, cash: 10 } }));
  assert.match(markup, /Targets add to 80%/);

  const empty = String(targetsCard({}));
  assert.doesNotMatch(empty, /Targets add to/);
});
