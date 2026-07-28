import test from 'node:test';
import assert from 'node:assert/strict';
import {
  firstDrawdownYear,
  crossoverYear,
  coastFireYear,
  milestoneAges,
} from '../views/plan/milestones.js';

function makeTimeline({
  initialBalance = 100000,
  contributions = 20000,
  withdrawals = 60000,
  growthRate = 0.06,
} = {}) {
  let balance = initialBalance;
  return Array.from({ length: 30 }, (_, index) => {
    const year = 2026 + index;
    const contributions_usd = index < 20 ? contributions : 0;
    const withdrawals_usd = index < 20 ? 0 : withdrawals;
    const starting_balance_usd = balance;
    balance += contributions_usd;
    balance -= withdrawals_usd;
    const growth_usd = balance * growthRate;
    balance += growth_usd;

    return {
      year,
      age: 35 + index,
      starting_balance_usd,
      ending_balance_usd: balance,
      contributions_usd,
      withdrawals_usd,
      growth_usd,
    };
  });
}

test('firstDrawdownYear returns the first withdrawal year', () => {
  assert.equal(firstDrawdownYear(makeTimeline()), 2046);
  assert.equal(firstDrawdownYear([]), null);
});

test('crossoverYear returns the first sustained year growth exceeds contributions', () => {
  const timeline = makeTimeline();
  const expected = timeline.find(point => (
    point.contributions_usd > 0
    && point.growth_usd > point.contributions_usd
  )).year;

  assert.equal(crossoverYear(timeline), expected);
  assert.equal(crossoverYear([]), null);
  assert.equal(crossoverYear(makeTimeline({ contributions: 0 })), null);
});

test('coastFireYear identifies healthy coast plans and rejects failing plans', () => {
  const healthy = makeTimeline();

  assert.ok(coastFireYear(healthy) < 2046);
  assert.equal(
    coastFireYear(makeTimeline({
      initialBalance: 1000,
      contributions: 2000,
      growthRate: 0.01,
    })),
    null,
  );

  const failingTimeline = makeTimeline();
  failingTimeline[20] = {
    ...failingTimeline[20],
    ending_balance_usd: 0,
  };

  assert.equal(coastFireYear(failingTimeline), null);
  assert.equal(coastFireYear([healthy[0]]), null);
  assert.equal(
    coastFireYear(makeTimeline({ withdrawals: 0 })),
    null,
    'a horizon with no retirement withdrawals cannot prove Coast FI',
  );
});

test('coastFireYear is monotonic with a larger starting balance', () => {
  const originalCoastYear = coastFireYear(makeTimeline());
  const doubledCoastYear = coastFireYear(makeTimeline({ initialBalance: 200000 }));

  assert.ok(doubledCoastYear <= originalCoastYear);
});

test('milestoneAges maps known years to ages and preserves null misses', () => {
  assert.deepEqual(
    milestoneAges(makeTimeline(), [2046, null, 1999]),
    [55, null, null],
  );
});
